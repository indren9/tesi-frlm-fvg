#!/usr/bin/env python3
"""
HEAVY 6.0-G — Build operational Heavy OD + path-flow artifacts

Decision implemented
--------------------
SPETH_FOR_DELIVERY = ACCEPT_WITH_LIMITATIONS
BASELINE_YEAR = 2019
FORECAST_SCENARIO = 2030
ANNUAL_TO_DAILY = /365
ANAS = validation/sanity-check only; NO calibration applied.

Routing basis
-------------
Use the already-validated E4/E5 rerouted paths, excluding manual macro-edges:
2615952, 2616115.

OD_FVG:
  keep REROUTE_STATUS == CONNECTED_NO_MANUAL

TRANSIT_FVG:
  keep REROUTE_STATUS == CLEAN_ENTRY_INTERNAL_EXIT
  (therefore the 2 marginal false-positive FVG transits are excluded)

Required files
--------------
HEAVY_0A_audit/speth_fvg_od_reroute_exact_endpoints.csv
HEAVY_0A_audit/speth_fvg_transit_reroute_exact_endpoints.csv

Outputs
-------
HEAVY_0B_delivery/
  HEAVY_OD_VEHICLES_DAY_v01.csv
  HEAVY_PATH_FLOWS_v01.csv
  HEAVY_TRANSIT_EXCLUSIONS_v01.csv
  HEAVY_ARTIFACT_SUMMARY_v01.txt
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(".")
AUDIT = ROOT / "HEAVY_0A_audit"
OUT = ROOT / "HEAVY_0B_delivery"

OD_FILE = AUDIT / "speth_fvg_od_reroute_exact_endpoints.csv"
TRANSIT_FILE = AUDIT / "speth_fvg_transit_reroute_exact_endpoints.csv"

OUT_OD = OUT / "HEAVY_OD_VEHICLES_DAY_v01.csv"
OUT_PATH = OUT / "HEAVY_PATH_FLOWS_v01.csv"
OUT_EXCL = OUT / "HEAVY_TRANSIT_EXCLUSIONS_v01.csv"
OUT_SUMMARY = OUT / "HEAVY_ARTIFACT_SUMMARY_v01.txt"

REMOVED_MANUAL_EDGES = {2615952, 2616115}

EXPECTED_OD_ROWS = 10875
EXPECTED_TRANSIT_INPUT_ROWS = 70682
EXPECTED_TRANSIT_KEPT_ROWS = 70680
EXPECTED_TOTAL_ROWS = 81555

EXPECTED_TOTAL_2019 = 9388896.25
EXPECTED_TOTAL_2030 = 11659650.00
TOL = 1e-6

OD_FIELDS = [
    "od_id",
    "fvg_flow_type",
    "origin_region_id",
    "origin_region_name",
    "destination_region_id",
    "destination_region_name",
    "annual_trucks_2019",
    "heavy_vehicles_day_2019",
    "annual_trucks_2030",
    "heavy_vehicles_day_2030",
]

PATH_FIELDS = OD_FIELDS + [
    "path_start_node",
    "path_end_node",
    "path_distance_km",
    "rerouted_edge_path",
    "entry_boundary_edge",
    "exit_boundary_edge",
    "route_status",
    "route_method",
]

EXCLUSION_FIELDS = [
    "od_id",
    "origin_region_id",
    "origin_region_name",
    "destination_region_id",
    "destination_region_name",
    "annual_trucks_2019",
    "annual_trucks_2030",
    "reroute_status",
    "exclusion_reason",
]

def require(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"STOP: missing required file: {path}")

def ffloat(x) -> float:
    try:
        return float(str(x).strip())
    except Exception:
        return 0.0

def parse_edge_ids(text) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", str(text or ""))]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fmt_num(x: float) -> str:
    # Preserve exact quarter-truck annual values and non-rounded daily expectations.
    return f"{x:.12g}"

def check_required_fields(reader: csv.DictReader, path: Path) -> None:
    required = {
        "ID_origin_region",
        "Name_origin_region",
        "ID_destination_region",
        "Name_destination_region",
        "Traffic_flow_trucks_2019",
        "Traffic_flow_trucks_2030",
        "EXACT_ORIGINAL_PATH_START_NODE",
        "EXACT_ORIGINAL_PATH_END_NODE",
        "REROUTE_STATUS",
        "REROUTED_EXACT_EDGE_SUM_KM",
        "REROUTED_EDGE_PATH",
    }
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(
            f"STOP: {path} missing required columns: {sorted(missing)}"
        )

def make_common(row: dict[str, str], flow_type: str) -> dict[str, str]:
    o = str(row["ID_origin_region"]).strip()
    d = str(row["ID_destination_region"]).strip()
    f19 = ffloat(row["Traffic_flow_trucks_2019"])
    f30 = ffloat(row["Traffic_flow_trucks_2030"])

    if f19 < 0 or f30 < 0:
        raise SystemExit(f"STOP: negative flow on OD {o}>{d}")

    return {
        "od_id": f"{o}>{d}",
        "fvg_flow_type": flow_type,
        "origin_region_id": o,
        "origin_region_name": str(row["Name_origin_region"]).strip(),
        "destination_region_id": d,
        "destination_region_name": str(row["Name_destination_region"]).strip(),
        "annual_trucks_2019": fmt_num(f19),
        "heavy_vehicles_day_2019": fmt_num(f19 / 365.0),
        "annual_trucks_2030": fmt_num(f30),
        "heavy_vehicles_day_2030": fmt_num(f30 / 365.0),
    }

def make_path(row: dict[str, str], common: dict[str, str]) -> dict[str, str]:
    edge_path = str(row["REROUTED_EDGE_PATH"]).strip()
    eids = parse_edge_ids(edge_path)

    if not eids:
        raise SystemExit(f"STOP: blank rerouted path for {common['od_id']}")

    bad = REMOVED_MANUAL_EDGES.intersection(eids)
    if bad:
        raise SystemExit(
            f"STOP: removed manual edge(s) {sorted(bad)} still present "
            f"on {common['od_id']}"
        )

    return {
        **common,
        "path_start_node": str(row["EXACT_ORIGINAL_PATH_START_NODE"]).strip(),
        "path_end_node": str(row["EXACT_ORIGINAL_PATH_END_NODE"]).strip(),
        "path_distance_km": str(row["REROUTED_EXACT_EDGE_SUM_KM"]).strip(),
        "rerouted_edge_path": edge_path,
        "entry_boundary_edge": str(
            row.get("REROUTED_ENTRY_BOUNDARY_EDGE", "")
        ).strip(),
        "exit_boundary_edge": str(
            row.get("REROUTED_EXIT_BOUNDARY_EDGE", "")
        ).strip(),
        "route_status": str(row["REROUTE_STATUS"]).strip(),
        "route_method": "SPETH_EXACT_ENDPOINT_DIJKSTRA_NO_MANUAL_MACRO_EDGES",
    }

for p in (OD_FILE, TRANSIT_FILE):
    require(p)

OUT.mkdir(parents=True, exist_ok=True)

od_rows: list[dict[str, str]] = []
path_rows: list[dict[str, str]] = []
excluded: list[dict[str, str]] = []

input_od_count = 0
input_transit_count = 0
kept_od_count = 0
kept_transit_count = 0

# ---------------- OD_FVG ----------------
with OD_FILE.open("r", encoding="utf-8-sig", newline="") as f:
    r = csv.DictReader(f)
    check_required_fields(r, OD_FILE)

    for row in r:
        input_od_count += 1
        status = str(row["REROUTE_STATUS"]).strip()
        if status != "CONNECTED_NO_MANUAL":
            raise SystemExit(
                f"STOP: unexpected OD_FVG reroute status {status!r}"
            )

        common = make_common(row, "OD_FVG")
        path = make_path(row, common)
        od_rows.append(common)
        path_rows.append(path)
        kept_od_count += 1

# ---------------- TRANSIT_FVG ----------------
with TRANSIT_FILE.open("r", encoding="utf-8-sig", newline="") as f:
    r = csv.DictReader(f)
    check_required_fields(r, TRANSIT_FILE)

    for row in r:
        input_transit_count += 1
        status = str(row["REROUTE_STATUS"]).strip()

        if status == "CLEAN_ENTRY_INTERNAL_EXIT":
            common = make_common(row, "TRANSIT_FVG")
            path = make_path(row, common)
            od_rows.append(common)
            path_rows.append(path)
            kept_transit_count += 1
        else:
            o = str(row["ID_origin_region"]).strip()
            d = str(row["ID_destination_region"]).strip()
            excluded.append({
                "od_id": f"{o}>{d}",
                "origin_region_id": o,
                "origin_region_name": str(row["Name_origin_region"]).strip(),
                "destination_region_id": d,
                "destination_region_name":
                    str(row["Name_destination_region"]).strip(),
                "annual_trucks_2019":
                    fmt_num(ffloat(row["Traffic_flow_trucks_2019"])),
                "annual_trucks_2030":
                    fmt_num(ffloat(row["Traffic_flow_trucks_2030"])),
                "reroute_status": status,
                "exclusion_reason":
                    "NOT_A_TRUE_FVG_TRANSIT_AFTER_CLEAN_REROUTING",
            })

# ---------------- Hard validation ----------------
if input_od_count != EXPECTED_OD_ROWS:
    raise SystemExit(
        f"STOP: OD_FVG input rows {input_od_count}, expected {EXPECTED_OD_ROWS}"
    )
if input_transit_count != EXPECTED_TRANSIT_INPUT_ROWS:
    raise SystemExit(
        f"STOP: TRANSIT input rows {input_transit_count}, "
        f"expected {EXPECTED_TRANSIT_INPUT_ROWS}"
    )
if kept_od_count != EXPECTED_OD_ROWS:
    raise SystemExit(
        f"STOP: kept OD_FVG rows {kept_od_count}, expected {EXPECTED_OD_ROWS}"
    )
if kept_transit_count != EXPECTED_TRANSIT_KEPT_ROWS:
    raise SystemExit(
        f"STOP: kept transit rows {kept_transit_count}, "
        f"expected {EXPECTED_TRANSIT_KEPT_ROWS}"
    )
if len(excluded) != 2:
    raise SystemExit(
        f"STOP: transit exclusions {len(excluded)}, expected 2"
    )
if len(od_rows) != EXPECTED_TOTAL_ROWS:
    raise SystemExit(
        f"STOP: output OD rows {len(od_rows)}, expected {EXPECTED_TOTAL_ROWS}"
    )
if len(path_rows) != EXPECTED_TOTAL_ROWS:
    raise SystemExit(
        f"STOP: output path rows {len(path_rows)}, expected {EXPECTED_TOTAL_ROWS}"
    )

# Each source row is intended to be one directed NUTS-3 OD relation.
od_ids = [r["od_id"] for r in od_rows]
unique_od_ids = len(set(od_ids))
if unique_od_ids != len(od_ids):
    from collections import Counter
    c = Counter(od_ids)
    dup = [k for k, v in c.items() if v > 1][:10]
    raise SystemExit(
        f"STOP: duplicate directed OD identities found: {dup}"
    )

total19 = sum(float(r["annual_trucks_2019"]) for r in od_rows)
total30 = sum(float(r["annual_trucks_2030"]) for r in od_rows)

if abs(total19 - EXPECTED_TOTAL_2019) > TOL:
    raise SystemExit(
        f"STOP: 2019 annual total {total19}, expected {EXPECTED_TOTAL_2019}"
    )
if abs(total30 - EXPECTED_TOTAL_2030) > TOL:
    raise SystemExit(
        f"STOP: 2030 annual total {total30}, expected {EXPECTED_TOTAL_2030}"
    )

# Stable deterministic ordering.
od_rows.sort(
    key=lambda r: (
        r["fvg_flow_type"],
        r["origin_region_id"],
        r["destination_region_id"],
    )
)
path_rows.sort(
    key=lambda r: (
        r["fvg_flow_type"],
        r["origin_region_id"],
        r["destination_region_id"],
    )
)
excluded.sort(key=lambda r: r["od_id"])

# ---------------- Write outputs ----------------
with OUT_OD.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=OD_FIELDS)
    w.writeheader()
    w.writerows(od_rows)

with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=PATH_FIELDS)
    w.writeheader()
    w.writerows(path_rows)

with OUT_EXCL.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=EXCLUSION_FIELDS)
    w.writeheader()
    w.writerows(excluded)

hash_od = sha256(OUT_OD)
hash_path = sha256(OUT_PATH)
hash_excl = sha256(OUT_EXCL)

lines = []
add = lines.append
add("HEAVY 6.0-G — OPERATIONAL ARTIFACT BUILD")
add("=" * 78)
add("")
add("METHODOLOGICAL DECISION")
add("SPETH_FOR_DELIVERY = ACCEPT_WITH_LIMITATIONS")
add("BASELINE_YEAR = 2019")
add("FORECAST_SCENARIO = 2030")
add("ANNUAL_TO_DAILY = /365")
add("ANAS_CALIBRATION = NO")
add("ANAS_ROLE = SANITY_CHECK_ONLY")
add("REMOVED_MANUAL_EDGES = 2615952, 2616115")
add("")
add("ROW COUNTS")
add(f"OD_FVG_INPUT = {input_od_count}")
add(f"OD_FVG_KEPT = {kept_od_count}")
add(f"TRANSIT_FVG_INPUT = {input_transit_count}")
add(f"TRANSIT_FVG_KEPT = {kept_transit_count}")
add(f"TRANSIT_FVG_EXCLUDED = {len(excluded)}")
add(f"TOTAL_OPERATIONAL_OD_ROWS = {len(od_rows)}")
add(f"UNIQUE_DIRECTED_OD_IDS = {unique_od_ids}")
add("")
add("FLOW TOTALS — DO NOT INTERPRET AS SUM OF LINK COUNTS")
add(
    f"2019 = {total19:.2f} trucks/year = "
    f"{total19/365.0:.6f} expected trucks/day"
)
add(
    f"2030 = {total30:.2f} trucks/year = "
    f"{total30/365.0:.6f} expected trucks/day"
)
add("")
add("VALIDATION")
add("ALL_OD_FVG_CONNECTED_NO_MANUAL = PASS")
add("TRANSIT_FALSE_POSITIVES_REMOVED = 2")
add("REMOVED_MANUAL_EDGES_ABSENT_FROM_OPERATIONAL_PATHS = PASS")
add("DUPLICATE_DIRECTED_OD_IDS = 0")
add("FLOW_TOTAL_RECONCILIATION = PASS")
add("")
add("ARTIFACTS")
add(f"{OUT_OD} | SHA256={hash_od}")
add(f"{OUT_PATH} | SHA256={hash_path}")
add(f"{OUT_EXCL} | SHA256={hash_excl}")
add("")
add("STATUS")
add("HEAVY_OD_VEHICLES_DAY_v01 = CURRENT / CANDIDATE_FOR_FREEZE")
add("HEAVY_PATH_FLOWS_v01 = CURRENT / CANDIDATE_FOR_FREEZE")
add("")
add("KNOWN LIMITATIONS")
add("- Speth absolute corridor volumes show a systematic high bias vs the limited ANAS sanity check.")
add("- Local Heavy access/distribution is coarse, especially around Trieste.")
add("- A34 / Gorizia / Sant'Andrea representation is weak/materially incomplete.")
add("- 2030 is a forecast scenario, not locally calibrated with ANAS.")

OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
print()
print(f"OD artifact   : {OUT_OD}")
print(f"Path artifact : {OUT_PATH}")
print(f"Exclusions    : {OUT_EXCL}")
print(f"Summary       : {OUT_SUMMARY}")
