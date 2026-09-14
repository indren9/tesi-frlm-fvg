#!/usr/bin/env python3
"""
B1-EXT-GH 10D — TARGETED EXTERNAL ROUTE OVERRIDE MATERIALIZATION

Purpose
-------
Materialize, append-only, the one confirmed correction resulting from GH10C:

    OSM relation 9242335
    Castelfranco Veneto
    direction EI
    external candidate GEO_0484 / gateway VE01

The frozen GraphHopper Italy graph ignored a malformed ``no_left_turn``
restriction (missing TO member) and used an illegal local shortcut. Manual
Google Maps validation established the legal movement: continue to the nearby
roundabout and return. GH10C produced and validated a legal counterfactual
route through that roundabout.

GH10D does NOT reroute and does NOT start GraphHopper.

It:
1. strictly verifies GH08F v02 + GH10C lineage and all source output hashes;
2. reproduces the frozen v02 IE/EI selection before any correction;
3. applies exactly ONE in-memory external-cache override:
       Castelfranco Veneto / EI / GEO_0484
   using the already-frozen GH10C legal counterfactual metrics;
4. recomputes exact route selection with the authoritative GH08 selector;
5. requires exactly three EI B1 rows to switch GEO_0484 -> GEO_0475,
   while gateway VE01 remains unchanged;
6. requires every other EI row and every IE row to remain unchanged;
7. requires gateway flow attribution to remain unchanged;
8. materializes a new append-only v03 package plus an explicit override ledger.

The frozen Italy graph, PBF, B5, GH08F v02, GH10B and GH10C remain untouched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Frozen authoritative lineage
# ======================================================================================

GH08_TOOL_REL = r"tools\B1_EXT_GH_08_hybrid_routing_materialization.py"
GH08_TOOL_SHA256 = "e60b6655644e50d554c1399a0c7a61cae590ed7add4d12b4970d816c8ee1fe38"

GH08F_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v02_endpoint_fallback"
)
GH08F_MANIFEST = "B1_EXT_GH_08F_targeted_endpoint_fallback_manifest_v02.json"
GH08F_MANIFEST_SHA256 = "1e6b53f93db0219f6ee5b6a961c96a5bf6eb1332ede8a4037dded6f7e4aa1433"
GH08F_SUMMARY = "B1_EXT_GH_08F_targeted_endpoint_fallback_summary_v02.json"
GH08F_SUMMARY_SHA256 = "08341355f95fd1bcc17a85db74a276888376b1f729db2e07ae014d4fe9aebac3"

GH07_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01"
)
GH07_MAPPING = "B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
GH07_MAPPING_SHA256 = "57026868b57e29944d1234fad43078db2c0b15a565039d07a4c1d30ed20ce2cc"

GH10C_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_counterfactual_v01"
)
GH10C_MANIFEST = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_manifest_v01.json"
GH10C_MANIFEST_SHA256 = "1ebcb0746a3581411a6ac4cb708d72123846746833979e63852486faa5c22c76"
GH10C_SUMMARY = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_summary_v01.json"
GH10C_SUMMARY_SHA256 = "f8271d04e4bf626d235bc064993f19f9cd571aa0b6b59b09b7611d41cb49f0c5"
GH10C_ROUTE = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_route_v01.json"
GH10C_ROUTE_SHA256 = "26d32d84d3789d24f4184a6613b7674da27d3a48b3807b831d2b14f619fce7e2"
GH10C_AFFECTED = "B1_EXT_GH_10C_affected_b1_rows_v01.csv"
GH10C_AFFECTED_SHA256 = "de7fa8efb40473102e5187d2db586e4992f5c5f0782b3a86d1eb34ffc01fa0c5"

# Frozen v02 files
B1_V02 = "B1_EXT_GH_08F_b1_normalized_v02.csv"
INTERNAL_ACCESS_V02 = "B1_EXT_GH_08F_internal_access_crossing_costs_v02.csv"
INTERNAL_COMMUNE_V02 = "B1_EXT_GH_08F_internal_commune_crossing_costs_v02.csv"
EXTERNAL_V02 = "B1_EXT_GH_08F_external_crossing_route_cache_v02.csv"
ENDPOINT_V02 = "B1_EXT_GH_08F_endpoint_snap_v02.csv"
IE_V02 = "B1_EXT_GH_08F_IE_routing_v02.csv"
EI_V02 = "B1_EXT_GH_08F_EI_routing_v02.csv"
CROSSING_FLOW_V02 = "B1_EXT_GH_08F_crossing_flow_attribution_v02.csv"
GATEWAY_FLOW_V02 = "B1_EXT_GH_08F_gateway_flow_attribution_v02.csv"

EXPECTED_B1_ROWS = 2895
EXPECTED_EXTERNAL_ROWS = 36064
EXPECTED_DAILY_FLOW = 6195.97590

# ======================================================================================
# Confirmed override contract
# ======================================================================================

RELATION_ID = 9242335
DESTINATION_KEY = "5bfd49535005893012d8"
DESTINATION_NAME = "Castelfranco Veneto"
DIRECTION = "EI"
OVERRIDDEN_GEO = "GEO_0484"
RESULT_GEO = "GEO_0475"
GATEWAY_ID = "VE01"

ILLEGAL_FROM_WAY = 110879921
ILLEGAL_NEXT_WAY = 1271839041

EXPECTED_AFFECTED_B1_IDS = {321, 445, 741}
EXPECTED_AFFECTED_RAW = 3.0
EXPECTED_AFFECTED_DAILY = 1.28565
EXPECTED_COUNTERFACTUAL_TIME_S = 4737.901
EXPECTED_COUNTERFACTUAL_DISTANCE_M = 102406.823
EXPECTED_COUNTERFACTUAL_WEIGHT = 4737.899065
EXPECTED_COUNTERFACTUAL_DEST_SNAP_M = 20.669053345624224
EXPECTED_COUNTERFACTUAL_CROSSING_SNAP_M = 0.20253768620884866
EXPECTED_EXTERNAL_DELTA_S = 11.975
EXPECTED_EXTERNAL_DELTA_M = 133.073

FLOAT_TOL = 1e-6
DIST_TOL = 1e-3

# ======================================================================================
# Output v03
# ======================================================================================

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_external_route_override_materialization_v03"
)

B1_V03 = "B1_EXT_GH_10D_b1_normalized_v03.csv"
INTERNAL_ACCESS_V03 = "B1_EXT_GH_10D_internal_access_crossing_costs_v03.csv"
INTERNAL_COMMUNE_V03 = "B1_EXT_GH_10D_internal_commune_crossing_costs_v03.csv"
EXTERNAL_V03 = "B1_EXT_GH_10D_external_crossing_route_cache_v03.csv"
ENDPOINT_V03 = "B1_EXT_GH_10D_endpoint_snap_v03.csv"
IE_V03 = "B1_EXT_GH_10D_IE_routing_v03.csv"
EI_V03 = "B1_EXT_GH_10D_EI_routing_v03.csv"
CROSSING_FLOW_V03 = "B1_EXT_GH_10D_crossing_flow_attribution_v03.csv"
GATEWAY_FLOW_V03 = "B1_EXT_GH_10D_gateway_flow_attribution_v03.csv"
OVERRIDE_LEDGER = "B1_EXT_GH_10D_external_route_override_ledger_v03.csv"
SUMMARY_JSON = "B1_EXT_GH_10D_targeted_external_route_override_summary_v03.json"
MANIFEST_JSON = "B1_EXT_GH_10D_targeted_external_route_override_manifest_v03.json"

# ======================================================================================
# Generic helpers
# ======================================================================================

def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def strict_hash(label: str, path: Path, expected: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    ok = actual == expected.lower()
    print(f"{label:<42} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    if not cols:
        raise RuntimeError(f"Missing CSV header: {path}")
    return rows, cols


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: Any) -> float:
    x = float(str(value).strip())
    if not math.isfinite(x):
        raise ValueError(value)
    return x


def parse_int(value: Any) -> int:
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        x = float(s)
        if not math.isfinite(x) or abs(x - round(x)) > 1e-9:
            raise
        return int(round(x))


def assert_close(actual: float, expected: float, label: str, tol: float = FLOAT_TOL) -> None:
    if abs(float(actual) - float(expected)) > tol:
        raise RuntimeError(
            f"{label}: {actual} != {expected} within tol={tol}"
        )


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_output_map(manifest: dict[str, Any]) -> dict[str, str]:
    rows = manifest.get("outputs")
    if not isinstance(rows, list):
        raise RuntimeError("Manifest missing outputs list")
    out: dict[str, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid manifest output item")
        filename = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not filename or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid manifest output item: {item}")
        if filename in out:
            raise RuntimeError(f"Duplicate manifest output: {filename}")
        out[filename] = digest
    return out


def verify_manifest_outputs(
    label: str,
    base_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, str]:
    outputs = manifest_output_map(manifest)
    for filename, digest in sorted(outputs.items()):
        p = base_dir / filename
        if not p.is_file():
            raise FileNotFoundError(p)
        if sha256(p) != digest:
            raise RuntimeError(f"{label} output changed: {filename}")
    print(f"{label} outputs verified{'':<16} = {len(outputs)}")
    return outputs


def route_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["destination_key"]),
        str(row["geo_id"]),
        str(row["direction"]),
    )


def compare_route_rows_semantic(
    old_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    *,
    allowed_changed_ids: set[int],
    label: str,
) -> tuple[set[int], set[int]]:
    old = {parse_int(r["b1_row_id"]): r for r in old_rows}
    new = {parse_int(r["b1_row_id"]): r for r in new_rows}
    if set(old) != set(new):
        raise RuntimeError(f"{label}: B1 row identities changed")

    exact_fields = [
        "route_status",
        "selected_geo_id",
        "selected_gateway_id",
        "valid_crossing_candidates",
        "tie_count",
        "tie_gateway_count",
    ]
    numeric_fields = [
        "internal_lambda_weighted_time_s",
        "external_time_s",
        "combined_time_s",
        "external_distance_m",
        "crossing_snap_m",
        "destination_snap_m",
        "second_best_combined_time_s",
        "gap_to_second_s",
    ]

    changed_ids: set[int] = set()
    unexpected_ids: set[int] = set()

    for row_id in sorted(old):
        a, b = old[row_id], new[row_id]
        changed = False
        for field in exact_fields:
            if str(a.get(field, "")) != str(b.get(field, "")):
                changed = True
        if str(a.get("route_status")) == "PASS" and str(b.get("route_status")) == "PASS":
            for field in numeric_fields:
                av = a.get(field)
                bv = b.get(field)
                if str(av).strip() == "" and str(bv).strip() == "":
                    continue
                if abs(parse_float(av) - parse_float(bv)) > FLOAT_TOL:
                    changed = True
        elif str(a) != str(b):
            changed = True

        if changed:
            changed_ids.add(row_id)
            if row_id not in allowed_changed_ids:
                unexpected_ids.add(row_id)

    return changed_ids, unexpected_ids


def flow_lookup(
    rows: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> dict[tuple[str, ...], dict[str, Any]]:
    out: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in rows:
        k = tuple(str(r[x]) for x in keys)
        if k in out:
            raise RuntimeError(f"Duplicate flow key {k}")
        out[k] = r
    return out


def compare_gateway_flows_exact_semantic(
    old_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> None:
    old = flow_lookup(old_rows, ("direction", "gateway_id"))
    new = flow_lookup(new_rows, ("direction", "gateway_id"))
    if set(old) != set(new):
        raise RuntimeError("Gateway flow keys changed")
    for key in sorted(old):
        a, b = old[key], new[key]
        if parse_int(a["b1_rows"]) != parse_int(b["b1_rows"]):
            raise RuntimeError(f"Gateway row count changed: {key}")
        assert_close(
            parse_float(a["Pendolari_raw_sum"]),
            parse_float(b["Pendolari_raw_sum"]),
            f"gateway raw {key}",
        )
        assert_close(
            parse_float(a["flow_daily_sum"]),
            parse_float(b["flow_daily_sum"]),
            f"gateway daily {key}",
        )


def helper_self_tests() -> None:
    assert route_key({
        "destination_key": "d",
        "geo_id": "g",
        "direction": "EI",
    }) == ("d", "g", "EI")

    fake = {
        "outputs": [
            {"filename": "x.csv", "sha256": "a" * 64},
            {"filename": "y.json", "sha256": "b" * 64},
        ]
    }
    assert manifest_output_map(fake)["x.csv"] == "a" * 64


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    args = parser.parse_args()

    helper_self_tests()

    root = Path(args.root)
    gh08_tool = root / Path(GH08_TOOL_REL)
    gh08f_dir = root / Path(GH08F_DIR_REL)
    gh07_dir = root / Path(GH07_DIR_REL)
    gh10c_dir = root / Path(GH10C_DIR_REL)

    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 10D — TARGETED EXTERNAL ROUTE OVERRIDE MATERIALIZATION")
    print("=" * 124)
    print("OFFLINE / APPEND-ONLY V03 / ONE OVERRIDE / NO GRAPHHOPPER / NO PBF / NO B5")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Strict lineage
    # ------------------------------------------------------------------
    print("A. STRICT LINEAGE / EVIDENCE IDENTITY")

    strict_hash("GH08 tool", gh08_tool, GH08_TOOL_SHA256)
    strict_hash("GH08F manifest", gh08f_dir / GH08F_MANIFEST, GH08F_MANIFEST_SHA256)
    strict_hash("GH08F summary", gh08f_dir / GH08F_SUMMARY, GH08F_SUMMARY_SHA256)
    strict_hash("GH07 crossing mapping", gh07_dir / GH07_MAPPING, GH07_MAPPING_SHA256)
    strict_hash("GH10C manifest", gh10c_dir / GH10C_MANIFEST, GH10C_MANIFEST_SHA256)
    strict_hash("GH10C summary", gh10c_dir / GH10C_SUMMARY, GH10C_SUMMARY_SHA256)
    strict_hash("GH10C route evidence", gh10c_dir / GH10C_ROUTE, GH10C_ROUTE_SHA256)
    strict_hash("GH10C affected rows", gh10c_dir / GH10C_AFFECTED, GH10C_AFFECTED_SHA256)

    gh08f_manifest = read_json(gh08f_dir / GH08F_MANIFEST)
    gh08f_outputs = verify_manifest_outputs("GH08F", gh08f_dir, gh08f_manifest)
    gh10c_manifest = read_json(gh10c_dir / GH10C_MANIFEST)
    gh10c_outputs = verify_manifest_outputs("GH10C", gh10c_dir, gh10c_manifest)

    required_v02 = [
        B1_V02, INTERNAL_ACCESS_V02, INTERNAL_COMMUNE_V02,
        EXTERNAL_V02, ENDPOINT_V02, IE_V02, EI_V02,
        CROSSING_FLOW_V02, GATEWAY_FLOW_V02,
    ]
    for filename in required_v02:
        if filename not in gh08f_outputs:
            raise RuntimeError(f"GH08F manifest missing {filename}")

    if GH10C_ROUTE not in gh10c_outputs or GH10C_AFFECTED not in gh10c_outputs:
        raise RuntimeError("GH10C manifest missing required counterfactual evidence")

    gh08 = load_module(gh08_tool, "b1_ext_gh08_for_gh10d")
    print("GH08 helper import                  = PASS")
    print("GH10D helper self-tests             = PASS")

    # ------------------------------------------------------------------
    # B. Validate GH10C counterfactual contract
    # ------------------------------------------------------------------
    print()
    print("B. GH10C COUNTERFACTUAL CONTRACT")

    route = read_json(gh10c_dir / GH10C_ROUTE)
    affected_evidence, _ = read_csv(gh10c_dir / GH10C_AFFECTED)
    gh10c_summary = read_json(gh10c_dir / GH10C_SUMMARY)

    if str(gh10c_summary.get("verdict")) != "PASS":
        raise RuntimeError("GH10C is not PASS")
    if int(gh10c_summary.get("relation_id")) != RELATION_ID:
        raise RuntimeError("GH10C relation identity mismatch")
    if not bool(gh10c_summary.get("illegal_transition_removed")):
        raise RuntimeError("GH10C did not remove illegal transition")

    ac = route["affected_candidate"]
    expected_identity = {
        "destination_key": DESTINATION_KEY,
        "dest_COMUNE": DESTINATION_NAME,
        "direction": DIRECTION,
        "gateway_id": GATEWAY_ID,
        "geo_id": OVERRIDDEN_GEO,
    }
    for field, expected in expected_identity.items():
        if str(ac[field]) != str(expected):
            raise RuntimeError(
                f"GH10C affected candidate mismatch {field}: "
                f"{ac[field]!r} != {expected!r}"
            )
    if [int(x) for x in ac["illegal_transition"]] != [
        ILLEGAL_FROM_WAY, ILLEGAL_NEXT_WAY
    ]:
        raise RuntimeError("GH10C illegal transition identity mismatch")

    baseline = route["baseline"]
    counterfactual = route["counterfactual"]
    snaps = route["counterfactual_snap_m"]
    delta = route["delta"]

    assert_close(
        parse_float(counterfactual["time_s"]),
        EXPECTED_COUNTERFACTUAL_TIME_S,
        "counterfactual time",
    )
    assert_close(
        parse_float(counterfactual["distance_m"]),
        EXPECTED_COUNTERFACTUAL_DISTANCE_M,
        "counterfactual distance",
        DIST_TOL,
    )
    assert_close(
        parse_float(counterfactual["weight"]),
        EXPECTED_COUNTERFACTUAL_WEIGHT,
        "counterfactual weight",
    )
    assert_close(
        parse_float(snaps["destination"]),
        EXPECTED_COUNTERFACTUAL_DEST_SNAP_M,
        "counterfactual destination snap",
    )
    assert_close(
        parse_float(snaps["crossing"]),
        EXPECTED_COUNTERFACTUAL_CROSSING_SNAP_M,
        "counterfactual crossing snap",
    )
    assert_close(
        parse_float(delta["external_time_s"]),
        EXPECTED_EXTERNAL_DELTA_S,
        "counterfactual time delta",
    )
    assert_close(
        parse_float(delta["external_distance_m"]),
        EXPECTED_EXTERNAL_DELTA_M,
        "counterfactual distance delta",
        DIST_TOL,
    )
    if bool(route.get("counterfactual_illegal_transition_present")):
        raise RuntimeError("GH10C counterfactual still reports illegal transition")

    evidence_ids = {parse_int(r["b1_row_id"]) for r in affected_evidence}
    if evidence_ids != EXPECTED_AFFECTED_B1_IDS:
        raise RuntimeError(
            f"GH10C affected B1 IDs {sorted(evidence_ids)} != "
            f"{sorted(EXPECTED_AFFECTED_B1_IDS)}"
        )
    for r in affected_evidence:
        if str(r["old_geo_id"]) != OVERRIDDEN_GEO:
            raise RuntimeError("Unexpected old GEO in GH10C affected evidence")
        if str(r["new_geo_id"]) != RESULT_GEO:
            raise RuntimeError("Unexpected new GEO in GH10C affected evidence")
        if str(r["old_gateway_id"]) != GATEWAY_ID or str(r["new_gateway_id"]) != GATEWAY_ID:
            raise RuntimeError("Gateway changed in GH10C evidence")

    print(f"relation                            = {RELATION_ID}")
    print(
        f"override candidate                  = "
        f"{DESTINATION_NAME} {DIRECTION} {GATEWAY_ID}/{OVERRIDDEN_GEO}"
    )
    print(
        f"legal counterfactual                = "
        f"{counterfactual['time_s']:.3f}s / "
        f"{counterfactual['distance_m']:.3f}m"
    )
    print(
        f"counterfactual external delta       = "
        f"+{delta['external_time_s']:.3f}s / "
        f"+{delta['external_distance_m']:.3f}m"
    )
    print("GH10C contract                       = PASS")

    # ------------------------------------------------------------------
    # C. Load v02 and reproduce frozen selection
    # ------------------------------------------------------------------
    print()
    print("C. FROZEN V02 REPRODUCTION")

    b1_rows, b1_cols = read_csv(gh08f_dir / B1_V02)
    internal_access_rows, internal_access_cols = read_csv(gh08f_dir / INTERNAL_ACCESS_V02)
    internal_commune_rows, internal_commune_cols = read_csv(gh08f_dir / INTERNAL_COMMUNE_V02)
    external_rows, external_cols = read_csv(gh08f_dir / EXTERNAL_V02)
    endpoint_old, endpoint_cols = read_csv(gh08f_dir / ENDPOINT_V02)
    ie_old, ie_cols = read_csv(gh08f_dir / IE_V02)
    ei_old, ei_cols = read_csv(gh08f_dir / EI_V02)
    crossing_flow_old, crossing_flow_cols = read_csv(gh08f_dir / CROSSING_FLOW_V02)
    gateway_flow_old, gateway_flow_cols = read_csv(gh08f_dir / GATEWAY_FLOW_V02)
    crossings, _ = read_csv(gh07_dir / GH07_MAPPING)

    if len(b1_rows) != EXPECTED_B1_ROWS:
        raise RuntimeError(f"B1 v02 rows={len(b1_rows)}")
    if len(external_rows) != EXPECTED_EXTERNAL_ROWS:
        raise RuntimeError(f"External v02 rows={len(external_rows)}")
    if len(ie_old) != EXPECTED_B1_ROWS or len(ei_old) != EXPECTED_B1_ROWS:
        raise RuntimeError("IE/EI v02 row count mismatch")

    ie_repro, ei_repro, repro_diag = gh08.select_routes(
        b1_rows,
        crossings,
        internal_commune_rows,
        external_rows,
    )
    ie_changes, ie_unexpected = compare_route_rows_semantic(
        ie_old, ie_repro,
        allowed_changed_ids=set(),
        label="IE reproduction",
    )
    ei_changes, ei_unexpected = compare_route_rows_semantic(
        ei_old, ei_repro,
        allowed_changed_ids=set(),
        label="EI reproduction",
    )
    if ie_changes or ie_unexpected or ei_changes or ei_unexpected:
        raise RuntimeError(
            f"Frozen selection reproduction drift: "
            f"IE={sorted(ie_changes)} EI={sorted(ei_changes)}"
        )

    crossing_repro, gateway_repro = gh08.aggregate_flow_attribution(
        ie_repro, ei_repro
    )
    compare_gateway_flows_exact_semantic(gateway_flow_old, gateway_repro)

    old_ie_daily = sum(parse_float(r["flow_daily"]) for r in ie_old if r["route_status"] == "PASS")
    old_ei_daily = sum(parse_float(r["flow_daily"]) for r in ei_old if r["route_status"] == "PASS")
    assert_close(old_ie_daily, EXPECTED_DAILY_FLOW, "old IE flow", 1e-5)
    assert_close(old_ei_daily, EXPECTED_DAILY_FLOW, "old EI flow", 1e-5)

    print("frozen IE reproduction              = PASS")
    print("frozen EI reproduction              = PASS")
    print("frozen gateway-flow reproduction    = PASS")

    # ------------------------------------------------------------------
    # D. Apply exactly one external-cache override
    # ------------------------------------------------------------------
    print()
    print("D. SINGLE EXTERNAL-CACHE OVERRIDE")

    target_key = (DESTINATION_KEY, OVERRIDDEN_GEO, DIRECTION)
    external_v03 = deepcopy(external_rows)
    patched = 0
    old_target: dict[str, Any] | None = None
    new_target: dict[str, Any] | None = None

    for row in external_v03:
        if route_key(row) != target_key:
            continue
        old_target = dict(row)

        row["external_time_s"] = f"{parse_float(counterfactual['time_s']):.9f}"
        row["external_distance_m"] = f"{parse_float(counterfactual['distance_m']):.9f}"
        row["external_weight"] = f"{parse_float(counterfactual['weight']):.12f}"
        row["destination_snap_m"] = f"{parse_float(snaps['destination']):.9f}"
        row["crossing_snap_m"] = f"{parse_float(snaps['crossing']):.9f}"
        row["http_status"] = "200"
        row["status"] = "PASS"
        row["error"] = ""

        new_target = dict(row)
        patched += 1

    if patched != 1 or old_target is None or new_target is None:
        raise RuntimeError(f"Expected exactly one override row; patched={patched}")

    # Every other external-cache row must remain dict-identical.
    old_by_key = {route_key(r): r for r in external_rows}
    new_by_key = {route_key(r): r for r in external_v03}
    if set(old_by_key) != set(new_by_key):
        raise RuntimeError("External-cache route keys changed")
    changed_external_keys = {
        k for k in old_by_key if old_by_key[k] != new_by_key[k]
    }
    if changed_external_keys != {target_key}:
        raise RuntimeError(
            f"External cache changed outside target: {sorted(changed_external_keys)}"
        )

    assert_close(
        parse_float(new_target["external_time_s"]),
        parse_float(counterfactual["time_s"]),
        "materialized override time",
    )
    assert_close(
        parse_float(new_target["external_distance_m"]),
        parse_float(counterfactual["distance_m"]),
        "materialized override distance",
        DIST_TOL,
    )

    print(f"external cache rows                 = {len(external_v03):,}")
    print("external rows changed               = 1")
    print(f"overridden key                      = {target_key}")
    print(
        f"candidate time                      = "
        f"{old_target['external_time_s']} -> {new_target['external_time_s']} s"
    )
    print(
        f"candidate distance                  = "
        f"{old_target['external_distance_m']} -> "
        f"{new_target['external_distance_m']} m"
    )

    # ------------------------------------------------------------------
    # E. Exact re-selection
    # ------------------------------------------------------------------
    print()
    print("E. EXACT IE/EI RE-SELECTION")

    ie_new, ei_new, selection_diag = gh08.select_routes(
        b1_rows,
        crossings,
        internal_commune_rows,
        external_v03,
    )

    ie_changed, ie_unexpected = compare_route_rows_semantic(
        ie_old, ie_new,
        allowed_changed_ids=set(),
        label="IE after override",
    )
    if ie_changed or ie_unexpected:
        raise RuntimeError(f"IE changed after EI-only override: {sorted(ie_changed)}")

    ei_changed, ei_unexpected = compare_route_rows_semantic(
        ei_old, ei_new,
        allowed_changed_ids=EXPECTED_AFFECTED_B1_IDS,
        label="EI after override",
    )
    if ei_unexpected:
        raise RuntimeError(
            f"Unexpected EI rows changed: {sorted(ei_unexpected)}"
        )
    if ei_changed != EXPECTED_AFFECTED_B1_IDS:
        raise RuntimeError(
            f"Changed EI IDs {sorted(ei_changed)} != "
            f"{sorted(EXPECTED_AFFECTED_B1_IDS)}"
        )

    old_ei_by_id = {parse_int(r["b1_row_id"]): r for r in ei_old}
    new_ei_by_id = {parse_int(r["b1_row_id"]): r for r in ei_new}
    evidence_by_id = {parse_int(r["b1_row_id"]): r for r in affected_evidence}

    selected_delta_values: list[float] = []

    for row_id in sorted(EXPECTED_AFFECTED_B1_IDS):
        old = old_ei_by_id[row_id]
        new = new_ei_by_id[row_id]
        ev = evidence_by_id[row_id]

        if str(old["selected_geo_id"]) != OVERRIDDEN_GEO:
            raise RuntimeError(f"row {row_id}: old GEO mismatch")
        if str(new["selected_geo_id"]) != RESULT_GEO:
            raise RuntimeError(f"row {row_id}: new GEO mismatch")
        if str(old["selected_gateway_id"]) != GATEWAY_ID:
            raise RuntimeError(f"row {row_id}: old gateway mismatch")
        if str(new["selected_gateway_id"]) != GATEWAY_ID:
            raise RuntimeError(f"row {row_id}: new gateway mismatch")

        for field in (
            "old_combined_time_s",
            "new_combined_time_s",
            "old_external_time_s",
            "new_external_time_s",
        ):
            side, actual_field = (
                ("old", field[4:]) if field.startswith("old_")
                else ("new", field[4:])
            )
            actual_row = old if side == "old" else new
            assert_close(
                parse_float(actual_row[actual_field]),
                parse_float(ev[field]),
                f"row {row_id} GH10C evidence {field}",
            )

        selected_delta = (
            parse_float(new["combined_time_s"]) -
            parse_float(old["combined_time_s"])
        )
        selected_delta_values.append(selected_delta)
        assert_close(
            selected_delta,
            parse_float(ev["combined_delta_s"]),
            f"row {row_id} selected combined delta",
        )

    new_ie_daily = sum(parse_float(r["flow_daily"]) for r in ie_new if r["route_status"] == "PASS")
    new_ei_daily = sum(parse_float(r["flow_daily"]) for r in ei_new if r["route_status"] == "PASS")
    assert_close(new_ie_daily, EXPECTED_DAILY_FLOW, "new IE flow", 1e-5)
    assert_close(new_ei_daily, EXPECTED_DAILY_FLOW, "new EI flow", 1e-5)

    if len(set(round(x, 9) for x in selected_delta_values)) != 1:
        raise RuntimeError("Affected selected impedance deltas are not identical")
    selected_combined_delta_s = selected_delta_values[0]

    affected_raw = sum(
        parse_float(new_ei_by_id[i]["Pendolari_raw"])
        for i in EXPECTED_AFFECTED_B1_IDS
    )
    affected_daily = sum(
        parse_float(new_ei_by_id[i]["flow_daily"])
        for i in EXPECTED_AFFECTED_B1_IDS
    )
    assert_close(affected_raw, EXPECTED_AFFECTED_RAW, "affected raw")
    assert_close(affected_daily, EXPECTED_AFFECTED_DAILY, "affected daily")

    print(f"IE rows changed                     = {len(ie_changed)}")
    print(f"EI rows changed                     = {len(ei_changed)}")
    print(f"EI rows unchanged                   = {EXPECTED_B1_ROWS - len(ei_changed)}")
    print(
        f"selected crossing                   = "
        f"{OVERRIDDEN_GEO} -> {RESULT_GEO}"
    )
    print(f"selected gateway                    = {GATEWAY_ID} -> {GATEWAY_ID}")
    print(
        f"selected combined-time delta        = "
        f"+{selected_combined_delta_s:.6f} s per affected row"
    )

    # ------------------------------------------------------------------
    # F. Flow attribution
    # ------------------------------------------------------------------
    print()
    print("F. CROSSING / GATEWAY FLOW ATTRIBUTION")

    crossing_flow_new, gateway_flow_new = gh08.aggregate_flow_attribution(
        ie_new, ei_new
    )
    compare_gateway_flows_exact_semantic(gateway_flow_old, gateway_flow_new)

    old_cross = flow_lookup(
        crossing_flow_old,
        ("direction", "gateway_id", "geo_id"),
    )
    new_cross = flow_lookup(
        crossing_flow_new,
        ("direction", "gateway_id", "geo_id"),
    )
    all_cross_keys = set(old_cross) | set(new_cross)
    crossing_changed_keys: set[tuple[str, ...]] = set()

    for key in sorted(all_cross_keys):
        a = old_cross.get(key, {})
        b = new_cross.get(key, {})
        old_rows_n = parse_int(a.get("b1_rows", 0))
        new_rows_n = parse_int(b.get("b1_rows", 0))
        old_raw = parse_float(a.get("Pendolari_raw_sum", 0.0))
        new_raw = parse_float(b.get("Pendolari_raw_sum", 0.0))
        old_daily = parse_float(a.get("flow_daily_sum", 0.0))
        new_daily = parse_float(b.get("flow_daily_sum", 0.0))

        if (
            old_rows_n != new_rows_n
            or abs(old_raw - new_raw) > FLOAT_TOL
            or abs(old_daily - new_daily) > FLOAT_TOL
        ):
            crossing_changed_keys.add(key)

    expected_crossing_changes = {
        (DIRECTION, GATEWAY_ID, OVERRIDDEN_GEO),
        (DIRECTION, GATEWAY_ID, RESULT_GEO),
    }
    if crossing_changed_keys != expected_crossing_changes:
        raise RuntimeError(
            f"Unexpected crossing-flow changes: {sorted(crossing_changed_keys)}"
        )

    def flow_triplet(mapping, key):
        r = mapping.get(key, {})
        return (
            parse_int(r.get("b1_rows", 0)),
            parse_float(r.get("Pendolari_raw_sum", 0.0)),
            parse_float(r.get("flow_daily_sum", 0.0)),
        )

    old_0484 = flow_triplet(old_cross, (DIRECTION, GATEWAY_ID, OVERRIDDEN_GEO))
    new_0484 = flow_triplet(new_cross, (DIRECTION, GATEWAY_ID, OVERRIDDEN_GEO))
    old_0475 = flow_triplet(old_cross, (DIRECTION, GATEWAY_ID, RESULT_GEO))
    new_0475 = flow_triplet(new_cross, (DIRECTION, GATEWAY_ID, RESULT_GEO))

    if new_0484[0] != old_0484[0] - 3:
        raise RuntimeError("GEO_0484 B1-row flow delta is not -3")
    assert_close(new_0484[1] - old_0484[1], -EXPECTED_AFFECTED_RAW, "GEO_0484 raw delta")
    assert_close(new_0484[2] - old_0484[2], -EXPECTED_AFFECTED_DAILY, "GEO_0484 daily delta")

    if new_0475[0] != old_0475[0] + 3:
        raise RuntimeError("GEO_0475 B1-row flow delta is not +3")
    assert_close(new_0475[1] - old_0475[1], EXPECTED_AFFECTED_RAW, "GEO_0475 raw delta")
    assert_close(new_0475[2] - old_0475[2], EXPECTED_AFFECTED_DAILY, "GEO_0475 daily delta")

    print("crossing-flow changed keys           = 2")
    print(
        f"  {OVERRIDDEN_GEO}                  = "
        f"-3 rows / -{EXPECTED_AFFECTED_RAW:.0f} raw / "
        f"-{EXPECTED_AFFECTED_DAILY:.5f} daily"
    )
    print(
        f"  {RESULT_GEO}                  = "
        f"+3 rows / +{EXPECTED_AFFECTED_RAW:.0f} raw / "
        f"+{EXPECTED_AFFECTED_DAILY:.5f} daily"
    )
    print("gateway-flow attribution            = UNCHANGED")

    # ------------------------------------------------------------------
    # G. Endpoint snap derivative audit
    # ------------------------------------------------------------------
    print()
    print("G. ENDPOINT SNAP DERIVATIVE AUDIT")

    endpoint_new = gh08.endpoint_snap_rows(external_v03)
    old_endpoint_lookup = {
        route_key(r): r for r in endpoint_old
    }
    new_endpoint_lookup = {
        route_key(r): r for r in endpoint_new
    }
    if set(old_endpoint_lookup) != set(new_endpoint_lookup):
        raise RuntimeError("Endpoint-snap keys changed")
    endpoint_changed = {
        k for k in old_endpoint_lookup
        if old_endpoint_lookup[k] != new_endpoint_lookup[k]
    }
    if endpoint_changed != {target_key}:
        raise RuntimeError(
            f"Endpoint-snap changes outside target: {sorted(endpoint_changed)}"
        )
    print("endpoint rows changed               = 1")

    # ------------------------------------------------------------------
    # H. Materialize append-only v03
    # ------------------------------------------------------------------
    print()
    print("H. MATERIALIZE APPEND-ONLY V03")

    staging.mkdir(parents=True, exist_ok=False)

    # Immutable materializations: copy bytes from v02, then verify.
    immutable_copy_pairs = [
        (gh08f_dir / B1_V02, staging / B1_V03),
        (gh08f_dir / INTERNAL_ACCESS_V02, staging / INTERNAL_ACCESS_V03),
        (gh08f_dir / INTERNAL_COMMUNE_V02, staging / INTERNAL_COMMUNE_V03),
        (gh08f_dir / IE_V02, staging / IE_V03),
        (gh08f_dir / GATEWAY_FLOW_V02, staging / GATEWAY_FLOW_V03),
    ]
    for src, dst in immutable_copy_pairs:
        shutil.copyfile(src, dst)
        if sha256(src) != sha256(dst):
            raise RuntimeError(f"Immutable copy changed: {src.name}")

    external_path = staging / EXTERNAL_V03
    endpoint_path = staging / ENDPOINT_V03
    ei_path = staging / EI_V03
    crossing_flow_path = staging / CROSSING_FLOW_V03

    write_csv(external_path, external_v03, external_cols)
    write_csv(endpoint_path, endpoint_new, endpoint_cols)
    write_csv(ei_path, ei_new, ei_cols)
    write_csv(crossing_flow_path, crossing_flow_new, crossing_flow_cols)

    # Explicit provenance / override ledger.
    manual = route["manual_evidence"]
    ledger_rows = [{
        "override_id": "B1_EXT_OVR_9242335_001",
        "relation_id": RELATION_ID,
        "reason": "CONFIRMED_IGNORED_MALFORMED_NO_LEFT_TURN",
        "manual_validation_source": manual["source"],
        "manual_validation_date": manual["date"],
        "manual_observation": manual["observation"],
        "destination_key": DESTINATION_KEY,
        "dest_COMUNE": DESTINATION_NAME,
        "direction": DIRECTION,
        "gateway_id": GATEWAY_ID,
        "overridden_geo_id": OVERRIDDEN_GEO,
        "result_selected_geo_id": RESULT_GEO,
        "illegal_from_way": ILLEGAL_FROM_WAY,
        "illegal_next_way": ILLEGAL_NEXT_WAY,
        "roundabout_center_lat": manual["roundabout_center_lat"],
        "roundabout_center_lon": manual["roundabout_center_lon"],
        "override_method": "GH10C_WAYPOINT_FORCED_LEGAL_ROUNDABOUT_COUNTERFACTUAL",
        "old_external_time_s": old_target["external_time_s"],
        "corrected_external_time_s": new_target["external_time_s"],
        "external_time_delta_s": parse_float(new_target["external_time_s"]) - parse_float(old_target["external_time_s"]),
        "old_external_distance_m": old_target["external_distance_m"],
        "corrected_external_distance_m": new_target["external_distance_m"],
        "external_distance_delta_m": parse_float(new_target["external_distance_m"]) - parse_float(old_target["external_distance_m"]),
        "affected_b1_row_ids": "|".join(map(str, sorted(EXPECTED_AFFECTED_B1_IDS))),
        "affected_b1_rows": len(EXPECTED_AFFECTED_B1_IDS),
        "affected_Pendolari_raw": EXPECTED_AFFECTED_RAW,
        "affected_flow_daily": EXPECTED_AFFECTED_DAILY,
        "selected_combined_time_delta_s_each": selected_combined_delta_s,
        "gateway_changed": False,
        "gateway_flow_changed": False,
        "graph_modified": False,
        "pbf_imported": False,
        "b5_rerun": False,
        "source_GH10C_route_sha256": GH10C_ROUTE_SHA256,
        "source_GH10C_affected_sha256": GH10C_AFFECTED_SHA256,
    }]
    ledger_path = staging / OVERRIDE_LEDGER
    write_csv(
        ledger_path,
        ledger_rows,
        [
            "override_id", "relation_id", "reason",
            "manual_validation_source", "manual_validation_date",
            "manual_observation", "destination_key", "dest_COMUNE",
            "direction", "gateway_id", "overridden_geo_id",
            "result_selected_geo_id", "illegal_from_way", "illegal_next_way",
            "roundabout_center_lat", "roundabout_center_lon",
            "override_method",
            "old_external_time_s", "corrected_external_time_s",
            "external_time_delta_s",
            "old_external_distance_m", "corrected_external_distance_m",
            "external_distance_delta_m",
            "affected_b1_row_ids", "affected_b1_rows",
            "affected_Pendolari_raw", "affected_flow_daily",
            "selected_combined_time_delta_s_each",
            "gateway_changed", "gateway_flow_changed",
            "graph_modified", "pbf_imported", "b5_rerun",
            "source_GH10C_route_sha256", "source_GH10C_affected_sha256",
        ],
    )

    # ------------------------------------------------------------------
    # I. Summary / manifest / final source integrity
    # ------------------------------------------------------------------
    print()
    print("I. FINAL INTEGRITY / GATE")

    # v02 + GH10C must remain byte-identical.
    verify_manifest_outputs("GH08F post-run", gh08f_dir, gh08f_manifest)
    verify_manifest_outputs("GH10C post-run", gh10c_dir, gh10c_manifest)

    summary = {
        "schema": "B1_EXT_GH_10D_TARGETED_EXTERNAL_ROUTE_OVERRIDE_SUMMARY_V03",
        "verdict": "PASS",
        "lineage": {
            "source_v02": "GH08F_TARGETED_ENDPOINT_FALLBACK_V02",
            "source_v02_preserved": True,
            "source_GH10C_preserved": True,
            "materialization": "V03_APPEND_ONLY",
        },
        "override": {
            "count": 1,
            "relation_id": RELATION_ID,
            "destination_key": DESTINATION_KEY,
            "dest_COMUNE": DESTINATION_NAME,
            "direction": DIRECTION,
            "gateway_id": GATEWAY_ID,
            "overridden_geo_id": OVERRIDDEN_GEO,
            "result_selected_geo_id": RESULT_GEO,
            "illegal_transition": [ILLEGAL_FROM_WAY, ILLEGAL_NEXT_WAY],
            "method": "GH10C_WAYPOINT_FORCED_LEGAL_ROUNDABOUT_COUNTERFACTUAL",
            "manual_evidence": route["manual_evidence"],
            "corrected_external_time_s": parse_float(new_target["external_time_s"]),
            "corrected_external_distance_m": parse_float(new_target["external_distance_m"]),
            "corrected_external_weight": parse_float(new_target["external_weight"]),
        },
        "selection_effect": {
            "IE_rows_changed": len(ie_changed),
            "EI_rows_changed": len(ei_changed),
            "EI_changed_b1_row_ids": sorted(ei_changed),
            "EI_rows_unchanged": EXPECTED_B1_ROWS - len(ei_changed),
            "old_geo_id": OVERRIDDEN_GEO,
            "new_geo_id": RESULT_GEO,
            "gateway_changed": False,
            "old_gateway_id": GATEWAY_ID,
            "new_gateway_id": GATEWAY_ID,
            "affected_Pendolari_raw": affected_raw,
            "affected_flow_daily": affected_daily,
            "selected_combined_time_delta_s_each": selected_combined_delta_s,
        },
        "flow_effect": {
            "crossing_flow_changed_keys": [
                list(k) for k in sorted(crossing_changed_keys)
            ],
            "gateway_flow_changed": False,
            "IE_daily_flow": new_ie_daily,
            "EI_daily_flow": new_ei_daily,
        },
        "integrity": {
            "external_cache_rows": len(external_v03),
            "external_cache_rows_changed": 1,
            "endpoint_rows_changed": 1,
            "all_IE_rows_unchanged": True,
            "all_nonaffected_EI_rows_unchanged": True,
            "GH08F_v02_modified": False,
            "GH10C_modified": False,
            "Italy_graph_modified": False,
            "PBF_import": "NOT_STARTED",
            "GraphHopper_server": "NOT_STARTED",
            "B5_routing": "NOT_STARTED",
        },
        "next_gate": "B1_FINAL_GATE_REASSESSMENT",
    }
    summary_path = staging / SUMMARY_JSON
    write_json(summary_path, summary)

    outputs = [
        staging / B1_V03,
        staging / INTERNAL_ACCESS_V03,
        staging / INTERNAL_COMMUNE_V03,
        external_path,
        endpoint_path,
        staging / IE_V03,
        ei_path,
        crossing_flow_path,
        staging / GATEWAY_FLOW_V03,
        ledger_path,
        summary_path,
    ]

    manifest = {
        "schema": "B1_EXT_GH_10D_TARGETED_EXTERNAL_ROUTE_OVERRIDE_MANIFEST_V03",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS",
        "inputs": {
            "GH08_tool": {
                "path": str(gh08_tool),
                "sha256": sha256(gh08_tool),
            },
            "GH08F_manifest": {
                "path": str(gh08f_dir / GH08F_MANIFEST),
                "sha256": sha256(gh08f_dir / GH08F_MANIFEST),
            },
            "GH10C_manifest": {
                "path": str(gh10c_dir / GH10C_MANIFEST),
                "sha256": sha256(gh10c_dir / GH10C_MANIFEST),
            },
            "GH10C_route_evidence": {
                "path": str(gh10c_dir / GH10C_ROUTE),
                "sha256": sha256(gh10c_dir / GH10C_ROUTE),
            },
            "GH10C_affected_evidence": {
                "path": str(gh10c_dir / GH10C_AFFECTED),
                "sha256": sha256(gh10c_dir / GH10C_AFFECTED),
            },
        },
        "source_v02_output_hashes": gh08f_outputs,
        "source_GH10C_output_hashes": gh10c_outputs,
        "outputs": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in outputs
        ],
        "override_count": 1,
        "next_gate": "B1_FINAL_GATE_REASSESSMENT",
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    staging.rename(final_dir)

    # ------------------------------------------------------------------
    # Final block
    # ------------------------------------------------------------------
    final_summary = read_json(final_dir / SUMMARY_JSON)

    print("GH08F v02 modified                  = NO")
    print("GH10C modified                      = NO")
    print("Italy graph modified                = NO")
    print()
    print("=" * 124)
    print("B1_EXT_GH_10D_TARGETED_EXTERNAL_ROUTE_OVERRIDE_MATERIALIZATION = PASS")
    print("MATERIALIZATION = V03_APPEND_ONLY")
    print("OVERRIDE_COUNT = 1")
    print(f"RELATION_ID = {RELATION_ID}")
    print(f"DESTINATION = {DESTINATION_NAME}")
    print(f"DIRECTION = {DIRECTION}")
    print(f"OVERRIDDEN_CANDIDATE = {GATEWAY_ID}/{OVERRIDDEN_GEO}")
    print(f"RESULT_SELECTED_CROSSING = {GATEWAY_ID}/{RESULT_GEO}")
    print(f"AFFECTED_B1_ROWS = {len(EXPECTED_AFFECTED_B1_IDS)}")
    print(f"AFFECTED_B1_ROW_IDS = {'|'.join(map(str, sorted(EXPECTED_AFFECTED_B1_IDS)))}")
    print(f"AFFECTED_PENDOLARI_RAW = {affected_raw:.5f}")
    print(f"AFFECTED_FLOW_DAILY = {affected_daily:.5f}")
    print(f"CORRECTED_CANDIDATE_EXTERNAL_TIME_S = {parse_float(new_target['external_time_s']):.3f}")
    print(f"CORRECTED_CANDIDATE_EXTERNAL_DISTANCE_M = {parse_float(new_target['external_distance_m']):.3f}")
    print(f"SELECTED_COMBINED_TIME_DELTA_S_EACH = {selected_combined_delta_s:.6f}")
    print(f"IE_ROWS_CHANGED = {len(ie_changed)}")
    print(f"EI_ROWS_CHANGED = {len(ei_changed)}")
    print(f"EI_ROWS_UNCHANGED = {EXPECTED_B1_ROWS - len(ei_changed)}")
    print("GATEWAY_CHANGED = NO")
    print("GATEWAY_FLOW_CHANGED = NO")
    print("EXTERNAL_CACHE_ROWS_CHANGED = 1")
    print("ENDPOINT_ROWS_CHANGED = 1")
    print("GH08F_V02_MODIFIED = NO")
    print("GH10C_MODIFIED = NO")
    print("ITALY_GRAPH_MODIFIED = NO")
    print("GRAPHHOPPER_SERVER = NOT_STARTED")
    print("PBF_IMPORT = NOT_STARTED")
    print("B5_ROUTING = NOT_STARTED")
    print("NEXT_GATE = B1_FINAL_GATE_REASSESSMENT")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print("=== RUN COMPLETATA ===")
    print(
        "HARD STOP — V03 OVERRIDE MATERIALIZED; "
        "RETURN THIS FINAL BLOCK FOR B1 FINAL GATE REASSESSMENT."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
