#!/usr/bin/env python3
"""
HEAVY-0A — Prepare/reconcile Speth ETISplus freight flows relevant to FVG.

Purpose
-------
Reproduce the exploratory FVG extraction performed during HEAVY-0A from the
Speth et al. synthetic European road-freight dataset (ETISplus-based).

Definitions frozen for this exploratory reproduction
----------------------------------------------------
FVG ETISplus zones:
    118130401  Pordenone
    118130402  Udine
    118130403  Gorizia
    118130404  Trieste

FVG network nodes:
    rows in 03_network-nodes.csv whose ETISplus_Zone_ID is one of the four
    FVG zones.

FVG-touching network edges:
    rows in 04_network-edges.csv with at least one endpoint among the FVG
    network nodes. This deliberately includes boundary cases such as
    external -> FVG node -> external.

OD_FVG:
    flows whose origin OR destination ETISplus zone is in FVG.

TRANSIT_FVG:
    flows whose origin AND destination are outside FVG, but whose
    Edge_path_E_road contains at least one FVG-touching edge.

positive_both:
    Traffic_flow_trucks_2019 > 0 AND Traffic_flow_trucks_2030 > 0.

The script never modifies the source files. Build mode refuses to overwrite
existing derived outputs unless --overwrite is explicitly supplied. Files are
written to temporary paths and promoted only after all baseline checks pass.

Historical HEAVY-0A reproduction counts for Speth/Mendeley V1:
    FVG network nodes                 47
    FVG-touching edges                53
    OD_FVG rows                    10,875
    OD_FVG positive_both           10,340
    TRANSIT_FVG rows               70,682
    TRANSIT_FVG positive_both      59,530
    combined positive_both         69,870

Use --skip-baseline-count-check only when intentionally applying the same
logic to a different dataset/version.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Callable, Iterable

FVG_ZONES = {
    "118130401",  # Pordenone
    "118130402",  # Udine
    "118130403",  # Gorizia
    "118130404",  # Trieste
}

INPUT_FILES = {
    "flows": "01_Trucktrafficflow.csv",
    "regions": "02_NUTS-3-Regions.csv",
    "nodes": "03_network-nodes.csv",
    "edges": "04_network-edges.csv",
}

OUTPUT_FILES = {
    "od": "01_Trucktrafficflow_FVG.csv",
    "od_positive": "01_Trucktrafficflow_FVG_positive_both.csv",
    "transit": "01_Trucktrafficflow_FVG_transit.csv",
    "transit_positive": "01_Trucktrafficflow_FVG_transit_positive_both.csv",
    "combined": "01_Trucktrafficflow_FVG_all_relevant_positive_both.csv",
}

EXPECTED = {
    "fvg_nodes": 47,
    "fvg_edges": 53,
    "od": 10875,
    "od_positive": 10340,
    "transit": 70682,
    "transit_positive": 59530,
    "combined": 69870,
}

REQUIRED_FLOW_FIELDS = {
    "ID_origin_region",
    "ID_destination_region",
    "Edge_path_E_road",
    "Traffic_flow_trucks_2019",
    "Traffic_flow_trucks_2030",
}

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def norm(value: object) -> str:
    return "" if value is None else str(value).strip()


def require_files(root: Path, names: Iterable[str]) -> None:
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        raise SystemExit(
            "STOP: missing required file(s):\n  - " + "\n  - ".join(missing)
        )


def check_fields(fieldnames: list[str] | None, required: set[str], label: str) -> None:
    available = set(fieldnames or [])
    missing = sorted(required - available)
    if missing:
        raise SystemExit(
            f"STOP: {label} is missing required field(s): {', '.join(missing)}"
        )


def load_fvg_network(data_root: Path) -> tuple[set[str], set[str], re.Pattern[str]]:
    nodes_path = data_root / INPUT_FILES["nodes"]
    edges_path = data_root / INPUT_FILES["edges"]

    fvg_nodes: set[str] = set()
    with nodes_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        check_fields(reader.fieldnames, {"Network_Node_ID", "ETISplus_Zone_ID"}, nodes_path.name)
        for row in reader:
            if norm(row["ETISplus_Zone_ID"]) in FVG_ZONES:
                fvg_nodes.add(norm(row["Network_Node_ID"]))

    fvg_edges: set[str] = set()
    with edges_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        check_fields(
            reader.fieldnames,
            {"Network_Edge_ID", "Network_Node_A_ID", "Network_Node_B_ID"},
            edges_path.name,
        )
        for row in reader:
            node_a = norm(row["Network_Node_A_ID"])
            node_b = norm(row["Network_Node_B_ID"])
            if node_a in fvg_nodes or node_b in fvg_nodes:
                fvg_edges.add(norm(row["Network_Edge_ID"]))

    if not fvg_edges:
        raise SystemExit("STOP: no FVG-touching network edges were identified.")

    alternatives = "|".join(
        re.escape(edge_id)
        for edge_id in sorted(fvg_edges, key=lambda x: (-len(x), x))
    )
    edge_pattern = re.compile(rf"(?<!\d)(?:{alternatives})(?!\d)")

    return fvg_nodes, fvg_edges, edge_pattern


def is_positive_both(row: dict[str, str]) -> bool:
    try:
        return (
            float(row["Traffic_flow_trucks_2019"]) > 0
            and float(row["Traffic_flow_trucks_2030"]) > 0
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Non-numeric truck flow encountered: "
            f"2019={row.get('Traffic_flow_trucks_2019')!r}, "
            f"2030={row.get('Traffic_flow_trucks_2030')!r}"
        ) from exc


def is_od_fvg(row: dict[str, str]) -> bool:
    return (
        norm(row["ID_origin_region"]) in FVG_ZONES
        or norm(row["ID_destination_region"]) in FVG_ZONES
    )


def is_transit_fvg(row: dict[str, str], edge_pattern: re.Pattern[str]) -> bool:
    return (not is_od_fvg(row)) and bool(edge_pattern.search(norm(row["Edge_path_E_road"])))


def assert_count(name: str, actual: int, skip: bool) -> None:
    if skip:
        return
    expected = EXPECTED[name]
    if actual != expected:
        raise SystemExit(
            f"STOP: baseline count mismatch for {name}: {actual:,} != {expected:,}"
        )


def output_paths(output_root: Path) -> dict[str, Path]:
    return {key: output_root / name for key, name in OUTPUT_FILES.items()}


def build(data_root: Path, output_root: Path, overwrite: bool, skip_baseline_count_check: bool) -> None:
    require_files(data_root, INPUT_FILES.values())
    output_root.mkdir(parents=True, exist_ok=True)

    paths = output_paths(output_root)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise SystemExit(
            "STOP: derived output(s) already exist. Use --reconcile-existing to verify them, "
            "or --overwrite to intentionally rebuild all outputs.\n  - "
            + "\n  - ".join(str(p) for p in existing)
        )

    fvg_nodes, fvg_edges, edge_pattern = load_fvg_network(data_root)
    print(f"FVG network nodes : {len(fvg_nodes)}")
    print(f"FVG-touching edges: {len(fvg_edges)}")
    assert_count("fvg_nodes", len(fvg_nodes), skip_baseline_count_check)
    assert_count("fvg_edges", len(fvg_edges), skip_baseline_count_check)

    flow_path = data_root / INPUT_FILES["flows"]
    tmp_paths = {key: path.with_name(path.name + ".tmp") for key, path in paths.items()}
    for tmp in tmp_paths.values():
        if tmp.exists():
            tmp.unlink()

    counts = {"od": 0, "od_positive": 0, "transit": 0, "transit_positive": 0, "combined": 0}

    try:
        with flow_path.open("r", encoding="utf-8-sig", newline="") as src, ExitStack() as stack:
            reader = csv.DictReader(src)
            check_fields(reader.fieldnames, REQUIRED_FLOW_FIELDS, flow_path.name)
            source_fields = list(reader.fieldnames or [])
            combined_fields = source_fields + ["FVG_FLOW_TYPE"]

            handles = {
                key: stack.enter_context(tmp_paths[key].open("w", encoding="utf-8", newline=""))
                for key in tmp_paths
            }
            writers = {
                "od": csv.DictWriter(handles["od"], fieldnames=source_fields),
                "od_positive": csv.DictWriter(handles["od_positive"], fieldnames=source_fields),
                "transit": csv.DictWriter(handles["transit"], fieldnames=source_fields),
                "transit_positive": csv.DictWriter(handles["transit_positive"], fieldnames=source_fields),
                "combined": csv.DictWriter(handles["combined"], fieldnames=combined_fields),
            }
            for writer in writers.values():
                writer.writeheader()

            for row in reader:
                positive = is_positive_both(row)

                if is_od_fvg(row):
                    writers["od"].writerow(row)
                    counts["od"] += 1
                    if positive:
                        writers["od_positive"].writerow(row)
                        counts["od_positive"] += 1
                        combined_row = dict(row)
                        combined_row["FVG_FLOW_TYPE"] = "OD_FVG"
                        writers["combined"].writerow(combined_row)
                        counts["combined"] += 1
                    continue

                if is_transit_fvg(row, edge_pattern):
                    writers["transit"].writerow(row)
                    counts["transit"] += 1
                    if positive:
                        writers["transit_positive"].writerow(row)
                        counts["transit_positive"] += 1
                        combined_row = dict(row)
                        combined_row["FVG_FLOW_TYPE"] = "TRANSIT_FVG"
                        writers["combined"].writerow(combined_row)
                        counts["combined"] += 1

        for key, actual in counts.items():
            assert_count(key, actual, skip_baseline_count_check)

        for key in OUTPUT_FILES:
            os.replace(tmp_paths[key], paths[key])

    except BaseException:
        for tmp in tmp_paths.values():
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    print(f"OD_FVG rows                : {counts['od']}")
    print(f"OD_FVG positive_both       : {counts['od_positive']}")
    print(f"TRANSIT_FVG rows           : {counts['transit']}")
    print(f"TRANSIT_FVG positive_both  : {counts['transit_positive']}")
    print(f"Combined positive_both     : {counts['combined']}")
    print("BUILD STATUS = PASS")


def count_and_validate(path: Path, required_fields: set[str], validator: Callable[[dict[str, str]], None]) -> int:
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        check_fields(reader.fieldnames, required_fields, path.name)
        for row in reader:
            validator(row)
            count += 1
    return count


def reconcile(data_root: Path, output_root: Path, skip_baseline_count_check: bool) -> None:
    require_files(data_root, INPUT_FILES.values())
    paths = output_paths(output_root)
    require_files(output_root, OUTPUT_FILES.values())

    fvg_nodes, fvg_edges, edge_pattern = load_fvg_network(data_root)
    print(f"FVG network nodes : {len(fvg_nodes)}")
    print(f"FVG-touching edges: {len(fvg_edges)}")
    assert_count("fvg_nodes", len(fvg_nodes), skip_baseline_count_check)
    assert_count("fvg_edges", len(fvg_edges), skip_baseline_count_check)

    def validate_od(row: dict[str, str]) -> None:
        if not is_od_fvg(row):
            raise SystemExit("STOP: OD_FVG contains a row with neither O nor D in FVG.")

    def validate_od_positive(row: dict[str, str]) -> None:
        validate_od(row)
        if not is_positive_both(row):
            raise SystemExit("STOP: OD_FVG positive_both contains a non-positive row.")

    def validate_transit(row: dict[str, str]) -> None:
        if is_od_fvg(row):
            raise SystemExit("STOP: TRANSIT_FVG contains an O/D-FVG row.")
        if not edge_pattern.search(norm(row["Edge_path_E_road"])):
            raise SystemExit("STOP: TRANSIT_FVG contains a path with no FVG-touching edge.")

    def validate_transit_positive(row: dict[str, str]) -> None:
        validate_transit(row)
        if not is_positive_both(row):
            raise SystemExit("STOP: TRANSIT_FVG positive_both contains a non-positive row.")

    combined_type_counts = {"OD_FVG": 0, "TRANSIT_FVG": 0}

    def validate_combined(row: dict[str, str]) -> None:
        if not is_positive_both(row):
            raise SystemExit("STOP: combined file contains a non-positive row.")
        flow_type = norm(row.get("FVG_FLOW_TYPE"))
        if flow_type == "OD_FVG":
            validate_od(row)
        elif flow_type == "TRANSIT_FVG":
            validate_transit(row)
        else:
            raise SystemExit(f"STOP: invalid FVG_FLOW_TYPE in combined file: {flow_type!r}")
        combined_type_counts[flow_type] += 1

    validations = {
        "od": (REQUIRED_FLOW_FIELDS, validate_od),
        "od_positive": (REQUIRED_FLOW_FIELDS, validate_od_positive),
        "transit": (REQUIRED_FLOW_FIELDS, validate_transit),
        "transit_positive": (REQUIRED_FLOW_FIELDS, validate_transit_positive),
        "combined": (REQUIRED_FLOW_FIELDS | {"FVG_FLOW_TYPE"}, validate_combined),
    }

    counts: dict[str, int] = {}
    for key, (fields, validator) in validations.items():
        counts[key] = count_and_validate(paths[key], fields, validator)
        assert_count(key, counts[key], skip_baseline_count_check)
        print(f"[OK] {paths[key].name}: {counts[key]} rows")

    if combined_type_counts["OD_FVG"] != counts["od_positive"]:
        raise SystemExit("STOP: combined OD_FVG count does not match OD_FVG positive_both.")
    if combined_type_counts["TRANSIT_FVG"] != counts["transit_positive"]:
        raise SystemExit("STOP: combined TRANSIT_FVG count does not match TRANSIT_FVG positive_both.")

    print(
        "Combined types: "
        f"OD_FVG={combined_type_counts['OD_FVG']}, "
        f"TRANSIT_FVG={combined_type_counts['TRANSIT_FVG']}"
    )
    print("RECONCILIATION STATUS = PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or reconcile HEAVY-0A Speth FVG freight flows.")
    parser.add_argument("--data-root", required=True, type=Path, help="Directory containing the four original Speth CSV files.")
    parser.add_argument("--output-root", type=Path, default=None, help="Directory for derived CSVs (default: --data-root).")
    parser.add_argument("--reconcile-existing", action="store_true", help="Verify existing derived outputs instead of rebuilding them.")
    parser.add_argument("--overwrite", action="store_true", help="Allow build mode to replace existing derived outputs.")
    parser.add_argument("--skip-baseline-count-check", action="store_true", help="Do not enforce historical Speth/Mendeley V1 row counts.")
    args = parser.parse_args()

    if args.reconcile_existing and args.overwrite:
        parser.error("--overwrite cannot be combined with --reconcile-existing.")

    args.data_root = args.data_root.expanduser().resolve()
    args.output_root = args.output_root.expanduser().resolve() if args.output_root is not None else args.data_root
    return args


def main() -> None:
    args = parse_args()
    print("=" * 72)
    print("HEAVY-0A — SPETH FVG")
    print("=" * 72)
    print(f"Data root  : {args.data_root}")
    print(f"Output root: {args.output_root}")

    if args.reconcile_existing:
        print("Mode        : RECONCILE EXISTING")
        reconcile(args.data_root, args.output_root, args.skip_baseline_count_check)
    else:
        print("Mode        : BUILD")
        build(args.data_root, args.output_root, args.overwrite, args.skip_baseline_count_check)


if __name__ == "__main__":
    main()
