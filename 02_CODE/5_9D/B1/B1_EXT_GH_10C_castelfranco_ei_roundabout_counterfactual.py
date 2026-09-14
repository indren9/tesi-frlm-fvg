#!/usr/bin/env python3
"""
B1-EXT-GH 10C — CASTELFRANCO EI ROUNDABOUT COUNTERFACTUAL

Scope
-----
One confirmed local defect only:

    relation 9242335
    restriction=no_left_turn
    malformed OSM relation: missing TO member
    selected external candidate:
        destination = Castelfranco Veneto
        direction   = EI
        gateway     = VE01
        geo_id      = GEO_0484

Manual external validation (Google Maps, user-verified 2026-09-04):
Via P. Piazza may join Via Giacomo Matteotti only in the permitted direction;
to return on the opposite carriageway, the legal route continues to the
roundabout and comes back. GraphHopper's selected route instead used the local
shortcut created by the ignored malformed restriction.

This script does NOT modify GraphHopper, the Italy graph, the PBF, B5, GH08F,
GH09, GH10A, or GH10B.

It:
1. verifies exact frozen lineage;
2. reproduces the frozen GH08F route-selection result before any change;
3. starts the existing GraphHopper graph WITHOUT PBF import;
4. re-queries the affected frozen candidate as a baseline canary;
5. builds one counterfactual route by forcing passage through the manually
   validated roundabout area;
6. requires the illegal OSM-way transition 110879921 -> 1271839041 to be
   absent from the counterfactual route;
7. patches ONLY that external candidate in memory;
8. recomputes exact physical-crossing selection using the frozen GH08
   selection function;
9. materializes an append-only audit package and stops.

This is feasibility/counterfactual evidence only.
Formal override materialization is a later gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Confirmed manual case
# ======================================================================================

RELATION_ID = 9242335
DESTINATION_KEY = "5bfd49535005893012d8"
DESTINATION_NAME = "Castelfranco Veneto"
DIRECTION = "EI"
AFFECTED_GATEWAY = "VE01"
AFFECTED_GEO = "GEO_0484"

ILLEGAL_FROM_WAY = 110879921
ILLEGAL_NEXT_WAY = 1271839041

# User clicked the centre of the roundabout used by the legal Google route.
ROUNDABOUT_CENTER_LAT = 45.66843920366166
ROUNDABOUT_CENTER_LON = 11.928326770104913
MAX_ROUNDABOUT_CENTER_SNAP_M = 60.0

EXPECTED_AFFECTED_RAW_FLOW = 3.0
EXPECTED_AFFECTED_DAILY_FLOW = 1.28565
FLOW_TOL = 1e-6

MANUAL_EVIDENCE = {
    "source": "GOOGLE_MAPS_USER_MANUAL_VALIDATION",
    "date": "2026-09-04",
    "observation": (
        "Via P. Piazza joins Via Giacomo Matteotti only in the permitted "
        "direction; to return in the opposite direction Google routes to the "
        "roundabout and back. Direct shortcut is not allowed."
    ),
    "roundabout_center_lat": ROUNDABOUT_CENTER_LAT,
    "roundabout_center_lon": ROUNDABOUT_CENTER_LON,
}

# ======================================================================================
# Frozen lineage
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

B1_V02 = "B1_EXT_GH_08F_b1_normalized_v02.csv"
INTERNAL_COMMUNE_V02 = "B1_EXT_GH_08F_internal_commune_crossing_costs_v02.csv"
EXTERNAL_V02 = "B1_EXT_GH_08F_external_crossing_route_cache_v02.csv"
IE_V02 = "B1_EXT_GH_08F_IE_routing_v02.csv"
EI_V02 = "B1_EXT_GH_08F_EI_routing_v02.csv"

GH10B_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_topology_semantic_audit_v01"
)
GH10B_MANIFEST = "B1_EXT_GH_10B_targeted_restriction_topology_semantic_manifest_v01.json"
GH10B_MANIFEST_SHA256 = "8ecc369fcf59cdf80672797a128381e10ec3d3a9cf291b03cb0e7354cad7e129"
GH10B_SUMMARY = "B1_EXT_GH_10B_targeted_restriction_topology_semantic_summary_v01.json"
GH10B_SUMMARY_SHA256 = "35188f86563fed36ed0e103f0e13f05378ff078b6af105b0f954482031636e60"
GH10B_UNRESOLVED = "B1_EXT_GH_10B_unresolved_candidates_v01.csv"

GH07_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01"
)
GH07_MAPPING = "B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
GH07_MAPPING_SHA256 = "57026868b57e29944d1234fad43078db2c0b15a565039d07a4c1d30ed20ce2cc"

# GraphHopper / graph
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"
FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"
PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"
EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 90

# Re-query tolerances already used successfully in GH09.
TIME_TOL_S = 1e-6
DIST_TOL_M = 0.05
SELECTION_NUMERIC_TOL_S = 1e-6

# ======================================================================================
# Output
# ======================================================================================

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_counterfactual_v01"
)

ROUTE_JSON = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_route_v01.json"
AFFECTED_CSV = "B1_EXT_GH_10C_affected_b1_rows_v01.csv"
GATEWAY_DELTA_CSV = "B1_EXT_GH_10C_gateway_flow_delta_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_10C_castelfranco_ei_counterfactual_manifest_v01.json"
SERVER_CONFIG = "graphhopper_b1_ext_server_gh10c_v01.yml"
SERVER_LOG = "graphhopper_b1_ext_server_gh10c_v01.log"

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
    print(f"{label:<40} {'PASS' if ok else 'FAIL':<5} {actual}")
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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
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


def assert_close(a: float, b: float, label: str, tol: float) -> None:
    if abs(float(a) - float(b)) > tol:
        raise RuntimeError(f"{label}: {a} != {b} within {tol}")


def collapse_adjacent(seq: list[int]) -> list[int]:
    out: list[int] = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def contains_pair(seq: list[int], a: int, b: int) -> bool:
    return any(x == a and y == b for x, y in zip(seq[:-1], seq[1:]))


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
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Invalid manifest output row")
        fn = str(row.get("filename", ""))
        digest = str(row.get("sha256", "")).lower()
        if not fn or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid manifest output row: {row}")
        if fn in out:
            raise RuntimeError(f"Duplicate manifest output: {fn}")
        out[fn] = digest
    return out


def verify_manifest_outputs(label: str, base_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    outputs = manifest_output_map(manifest)
    for fn, digest in sorted(outputs.items()):
        p = base_dir / fn
        if not p.is_file():
            raise FileNotFoundError(p)
        if sha256(p) != digest:
            raise RuntimeError(f"{label} output changed: {fn}")
    print(f"{label} outputs verified{'':<14} = {len(outputs)}")
    return outputs


def compare_selection_to_frozen(
    calc_rows: list[dict[str, Any]],
    frozen_rows: list[dict[str, str]],
    direction: str,
) -> None:
    calc = {parse_int(r["b1_row_id"]): r for r in calc_rows}
    frozen = {parse_int(r["b1_row_id"]): r for r in frozen_rows}
    if set(calc) != set(frozen):
        raise RuntimeError(f"{direction}: B1 row identity mismatch")

    exact_fields = ("route_status", "selected_geo_id", "selected_gateway_id")
    numeric_fields = (
        "internal_lambda_weighted_time_s",
        "external_time_s",
        "combined_time_s",
        "external_distance_m",
    )
    for row_id in sorted(frozen):
        a = calc[row_id]
        b = frozen[row_id]
        for field in exact_fields:
            if str(a[field]) != str(b[field]):
                raise RuntimeError(
                    f"{direction} frozen reproduction row={row_id} "
                    f"{field}: {a[field]!r} != {b[field]!r}"
                )
        if str(b["route_status"]) == "PASS":
            for field in numeric_fields:
                assert_close(
                    parse_float(a[field]),
                    parse_float(b[field]),
                    f"{direction} frozen reproduction row={row_id} field={field}",
                    1e-6,
                )


def route_selection_signature(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["route_status"]),
        str(row["selected_gateway_id"]),
        str(row["selected_geo_id"]),
    )


# ======================================================================================
# GraphHopper route detail request
# ======================================================================================

def route_detail_request(
    points: list[tuple[float, float]],  # [(lat, lon), ...]
) -> dict[str, Any]:
    if len(points) < 2:
        raise ValueError("Need at least two route points")

    params: list[tuple[str, str]] = []
    for lat, lon in points:
        params.append(("point", f"{lat:.8f},{lon:.8f}"))
    params.extend([
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "true"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
        ("details", "edge_id"),
        ("details", "osm_way_id"),
        ("details", "distance"),
    ])

    url = f"http://127.0.0.1:{APP_PORT}/route?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-GH10C/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=ROUTE_TIMEOUT_S) as response:
            body = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GraphHopper HTTP {exc.code}: {body[:2000]}") from exc

    if status != 200:
        raise RuntimeError(f"Unexpected GraphHopper HTTP status={status}")

    data = json.loads(body)
    paths = data.get("paths", [])
    if len(paths) != 1:
        raise RuntimeError(f"Expected exactly one path; got {len(paths)}")
    path = paths[0]

    snapped = path.get("snapped_waypoints", {})
    snapped_coords = snapped.get("coordinates", [])
    if len(snapped_coords) != len(points):
        raise RuntimeError(
            f"Expected {len(points)} snapped waypoints; got {snapped_coords}"
        )

    route_time_s = parse_int(path["time"]) / 1000.0
    route_distance_m = parse_float(path["distance"])
    route_weight = parse_float(path["weight"])
    if route_time_s <= 0 or route_distance_m <= 0:
        raise RuntimeError("Non-positive route metrics")

    details = path.get("details", {})
    edge_details = details.get("edge_id")
    way_details = details.get("osm_way_id")
    distance_details = details.get("distance")
    if not isinstance(edge_details, list) or not edge_details:
        raise RuntimeError("edge_id path details missing/empty")
    if not isinstance(way_details, list) or not way_details:
        raise RuntimeError("osm_way_id path details missing/empty")
    if not isinstance(distance_details, list) or not distance_details:
        raise RuntimeError("distance path details missing/empty")

    raw_way_sequence: list[int] = []
    for item in way_details:
        if not isinstance(item, list) or len(item) != 3:
            raise RuntimeError(f"Invalid osm_way_id detail: {item}")
        if item[2] is None:
            raise RuntimeError("Null osm_way_id path detail")
        raw_way_sequence.append(parse_int(item[2]))
    way_sequence = collapse_adjacent(raw_way_sequence)
    if not way_sequence:
        raise RuntimeError("Empty collapsed OSM way sequence")

    return {
        "time_s": route_time_s,
        "distance_m": route_distance_m,
        "weight": route_weight,
        "snapped_waypoints": [
            {"lon": float(c[0]), "lat": float(c[1])}
            for c in snapped_coords
        ],
        "edge_detail_count": len(edge_details),
        "way_detail_count": len(raw_way_sequence),
        "distance_detail_count": len(distance_details),
        "way_sequence": way_sequence,
    }


def helper_self_tests() -> None:
    assert collapse_adjacent([1, 1, 2, 2, 3, 1]) == [1, 2, 3, 1]
    assert contains_pair([1, 2, 3], 1, 2)
    assert not contains_pair([1, 3, 2], 1, 2)

    fake = {
        "outputs": [
            {"filename": "a.csv", "sha256": "a" * 64},
            {"filename": "b.json", "sha256": "b" * 64},
        ]
    }
    m = manifest_output_map(fake)
    assert m["a.csv"] == "a" * 64
    assert m["b.json"] == "b" * 64


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
    gh10b_dir = root / Path(GH10B_DIR_REL)
    gh07_dir = root / Path(GH07_DIR_REL)

    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 10C — CASTELFRANCO EI ROUNDABOUT COUNTERFACTUAL")
    print("=" * 124)
    print("ONE CONFIRMED DEFECT / ONE EXTERNAL CANDIDATE / NO IMPORT / NO GRAPH MODIFICATION")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Strict lineage
    # ------------------------------------------------------------------
    print("A. STRICT LINEAGE / PRE-FLIGHT")

    strict_hash("GH08 tool", gh08_tool, GH08_TOOL_SHA256)
    strict_hash("GH08F manifest", gh08f_dir / GH08F_MANIFEST, GH08F_MANIFEST_SHA256)
    strict_hash("GH08F summary", gh08f_dir / GH08F_SUMMARY, GH08F_SUMMARY_SHA256)
    strict_hash("GH10B manifest", gh10b_dir / GH10B_MANIFEST, GH10B_MANIFEST_SHA256)
    strict_hash("GH10B summary", gh10b_dir / GH10B_SUMMARY, GH10B_SUMMARY_SHA256)
    strict_hash("GH07 crossing mapping", gh07_dir / GH07_MAPPING, GH07_MAPPING_SHA256)
    strict_hash("GraphHopper JAR", root / Path(GH_JAR_REL), GH_JAR_SHA256)
    strict_hash("profile config", root / Path(PROFILE_CONFIG_REL), PROFILE_CONFIG_SHA256)

    gh08f_manifest = read_json(gh08f_dir / GH08F_MANIFEST)
    gh08f_outputs = verify_manifest_outputs("GH08F", gh08f_dir, gh08f_manifest)
    gh10b_manifest = read_json(gh10b_dir / GH10B_MANIFEST)
    gh10b_outputs = verify_manifest_outputs("GH10B", gh10b_dir, gh10b_manifest)

    for required in (B1_V02, INTERNAL_COMMUNE_V02, EXTERNAL_V02, IE_V02, EI_V02):
        if required not in gh08f_outputs:
            raise RuntimeError(f"GH08F manifest missing required output {required}")
    if GH10B_UNRESOLVED not in gh10b_outputs:
        raise RuntimeError("GH10B manifest missing unresolved-candidates CSV")

    gh08 = load_module(gh08_tool, "b1_ext_gh08_for_gh10c")

    graph_dir = root / Path(FINAL_GRAPH_REL)
    graph_manifest_path, graph_manifest = gh08.find_graph_manifest(root)
    if sha256(graph_manifest_path) != EXPECTED_GRAPH_MANIFEST_SHA256:
        raise RuntimeError("Frozen graph manifest identity mismatch")
    graph_before = gh08.graph_inventory(graph_dir)
    if gh08.normalized_inventory(graph_before) != gh08.normalized_inventory(graph_manifest["files"]):
        raise RuntimeError("Italy graph does not match frozen graph manifest")
    print("Italy graph identity pre-run       PASS")
    print("helper self-tests                  PASS")

    # ------------------------------------------------------------------
    # B. Verify exact unresolved case + load frozen selection inputs
    # ------------------------------------------------------------------
    print()
    print("B. CONFIRMED CASE / FROZEN SELECTION REPRODUCTION")

    unresolved_rows, _ = read_csv(gh10b_dir / GH10B_UNRESOLVED)
    case_rows = [
        r for r in unresolved_rows
        if parse_int(r["relation_id"]) == RELATION_ID
    ]
    if len(case_rows) != 1:
        raise RuntimeError(f"Expected exactly one GH10B unresolved row for {RELATION_ID}; got {len(case_rows)}")
    case = case_rows[0]
    required_case = {
        "destination_key": DESTINATION_KEY,
        "dest_COMUNE": DESTINATION_NAME,
        "gateway_id": AFFECTED_GATEWAY,
        "geo_id": AFFECTED_GEO,
        "direction": DIRECTION,
        "classification": "UNRESOLVED_MISSING_TO",
    }
    for field, expected in required_case.items():
        if str(case[field]) != str(expected):
            raise RuntimeError(
                f"Case identity mismatch {field}: {case[field]!r} != {expected!r}"
            )

    b1_rows, _ = read_csv(gh08f_dir / B1_V02)
    internal_rows, _ = read_csv(gh08f_dir / INTERNAL_COMMUNE_V02)
    external_rows, external_cols = read_csv(gh08f_dir / EXTERNAL_V02)
    ie_frozen, _ = read_csv(gh08f_dir / IE_V02)
    ei_frozen, _ = read_csv(gh08f_dir / EI_V02)
    crossings, _ = read_csv(gh07_dir / GH07_MAPPING)

    ie_calc, ei_calc, frozen_diag = gh08.select_routes(
        b1_rows,
        crossings,
        internal_rows,
        external_rows,
    )
    compare_selection_to_frozen(ie_calc, ie_frozen, "IE")
    compare_selection_to_frozen(ei_calc, ei_frozen, "EI")
    print("frozen IE/EI selection reproduction = PASS")

    affected_frozen = [
        r for r in ei_frozen
        if str(r["destination_key"]) == DESTINATION_KEY
        and str(r["selected_geo_id"]) == AFFECTED_GEO
        and str(r["selected_gateway_id"]) == AFFECTED_GATEWAY
        and str(r["route_status"]) == "PASS"
    ]
    affected_ids = {parse_int(r["b1_row_id"]) for r in affected_frozen}
    if not affected_ids:
        raise RuntimeError("No frozen EI B1 rows use affected candidate")

    affected_raw = sum(parse_float(r["Pendolari_raw"]) for r in affected_frozen)
    affected_daily = sum(parse_float(r["flow_daily"]) for r in affected_frozen)
    assert_close(affected_raw, EXPECTED_AFFECTED_RAW_FLOW, "affected raw flow", FLOW_TOL)
    assert_close(affected_daily, EXPECTED_AFFECTED_DAILY_FLOW, "affected daily flow", FLOW_TOL)

    cache_hits = [
        r for r in external_rows
        if str(r["destination_key"]) == DESTINATION_KEY
        and str(r["geo_id"]) == AFFECTED_GEO
        and str(r["direction"]) == DIRECTION
    ]
    if len(cache_hits) != 1:
        raise RuntimeError(f"Expected one affected external cache row; got {len(cache_hits)}")
    cache_row = cache_hits[0]
    if str(cache_row["status"]) != "PASS":
        raise RuntimeError("Affected frozen external cache row is not PASS")

    print(f"affected frozen B1 rows            = {len(affected_frozen)}")
    print(f"affected raw / daily               = {affected_raw:.5f} / {affected_daily:.5f}")
    print(
        f"affected candidate                 = "
        f"{DESTINATION_NAME} {DIRECTION} {AFFECTED_GATEWAY}/{AFFECTED_GEO}"
    )

    # ------------------------------------------------------------------
    # C. Start existing graph safely
    # ------------------------------------------------------------------
    print()
    print("C. SAFE EXISTING-GRAPH SERVER START")

    if not gh08.port_is_free(APP_PORT):
        raise RuntimeError(f"Application port {APP_PORT} already in use")
    if not gh08.port_is_free(ADMIN_PORT):
        raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")

    staging.mkdir(parents=True, exist_ok=False)

    java_exe = gh08.find_java(root / Path(RUNTIME_REL))
    server_config_path = staging / SERVER_CONFIG
    server_config_path.write_text(
        gh08.make_server_config(
            root / Path(PROFILE_CONFIG_REL),
            graph_dir,
            staging,
        ),
        encoding="utf-8",
    )
    server_log_path = staging / SERVER_LOG
    server_log_handle = server_log_path.open("w", encoding="utf-8", errors="replace")

    cmd = [
        str(java_exe),
        f"-Xms{SERVER_XMS_MIB}m",
        f"-Xmx{SERVER_XMX_GIB}g",
        "-XX:+UseParallelGC",
        "-jar",
        str(root / Path(GH_JAR_REL)),
        "server",
        str(server_config_path),
    ]

    proc: subprocess.Popen | None = None
    shutdown_status = "NOT_STARTED"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=staging,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        gh08.wait_for_server(proc)
        print("SERVER_LOAD                        = PASS")
        print("national PBF passed                = NO")
        print("bind host                          = localhost")

        # --------------------------------------------------------------
        # D. Baseline route canary
        # --------------------------------------------------------------
        print()
        print("D. BASELINE ROUTE CANARY / ILLEGAL TRANSITION CONFIRMATION")

        start = (
            parse_float(cache_row["dest_lat"]),
            parse_float(cache_row["dest_lon"]),
        )
        end = (
            parse_float(cache_row["crossing_lat"]),
            parse_float(cache_row["crossing_lon"]),
        )

        baseline = route_detail_request([start, end])
        assert_close(
            baseline["time_s"],
            parse_float(cache_row["external_time_s"]),
            "baseline time regression",
            TIME_TOL_S,
        )
        assert_close(
            baseline["distance_m"],
            parse_float(cache_row["external_distance_m"]),
            "baseline distance regression",
            DIST_TOL_M,
        )
        if not contains_pair(
            baseline["way_sequence"],
            ILLEGAL_FROM_WAY,
            ILLEGAL_NEXT_WAY,
        ):
            raise RuntimeError(
                "Baseline re-query no longer contains the confirmed illegal "
                "transition; abort counterfactual."
            )

        print(
            f"baseline metrics                    = "
            f"{baseline['time_s']:.3f}s / {baseline['distance_m']:.3f}m"
        )
        print(
            f"baseline illegal pair               = "
            f"{ILLEGAL_FROM_WAY}->{ILLEGAL_NEXT_WAY} PRESENT"
        )
        print("BASELINE_CANARY                     = PASS")

        # --------------------------------------------------------------
        # E. Forced legal roundabout counterfactual
        # --------------------------------------------------------------
        print()
        print("E. ROUNDABOUT COUNTERFACTUAL")

        via = (ROUNDABOUT_CENTER_LAT, ROUNDABOUT_CENTER_LON)
        counterfactual = route_detail_request([start, via, end])

        cf_snaps = counterfactual["snapped_waypoints"]
        dest_snap_m = gh08.haversine_m(
            start[1], start[0],
            cf_snaps[0]["lon"], cf_snaps[0]["lat"],
        )
        via_snap_m = gh08.haversine_m(
            ROUNDABOUT_CENTER_LON, ROUNDABOUT_CENTER_LAT,
            cf_snaps[1]["lon"], cf_snaps[1]["lat"],
        )
        crossing_snap_m = gh08.haversine_m(
            end[1], end[0],
            cf_snaps[2]["lon"], cf_snaps[2]["lat"],
        )

        if dest_snap_m > gh08.MAX_DESTINATION_SNAP_M:
            raise RuntimeError(f"Counterfactual destination snap too large: {dest_snap_m}")
        if crossing_snap_m > gh08.MAX_CROSSING_SNAP_M:
            raise RuntimeError(f"Counterfactual crossing snap too large: {crossing_snap_m}")
        if via_snap_m > MAX_ROUNDABOUT_CENTER_SNAP_M:
            raise RuntimeError(
                f"Counterfactual via snap {via_snap_m:.3f}m exceeds "
                f"{MAX_ROUNDABOUT_CENTER_SNAP_M:.1f}m"
            )

        if contains_pair(
            counterfactual["way_sequence"],
            ILLEGAL_FROM_WAY,
            ILLEGAL_NEXT_WAY,
        ):
            raise RuntimeError(
                "Counterfactual still contains illegal transition "
                f"{ILLEGAL_FROM_WAY}->{ILLEGAL_NEXT_WAY}"
            )

        if counterfactual["time_s"] <= baseline["time_s"]:
            raise RuntimeError(
                "Counterfactual is not slower than illegal-shortcut baseline; "
                "roundabout forcing is not credible."
            )
        if counterfactual["distance_m"] <= baseline["distance_m"]:
            raise RuntimeError(
                "Counterfactual is not longer than illegal-shortcut baseline; "
                "roundabout forcing is not credible."
            )

        delta_time_s = counterfactual["time_s"] - baseline["time_s"]
        delta_distance_m = counterfactual["distance_m"] - baseline["distance_m"]

        print(
            f"via snap to roundabout centre       = {via_snap_m:.3f} m"
        )
        print(
            f"counterfactual metrics              = "
            f"{counterfactual['time_s']:.3f}s / "
            f"{counterfactual['distance_m']:.3f}m"
        )
        print(
            f"external delta                      = "
            f"+{delta_time_s:.3f}s / +{delta_distance_m:.3f}m"
        )
        print(
            f"illegal pair in counterfactual      = NO"
        )
        print("COUNTERFACTUAL_ROUTE                = PASS")

        # --------------------------------------------------------------
        # F. Patch exactly one cache row in memory and reselect
        # --------------------------------------------------------------
        print()
        print("F. EXACT B1 RE-SELECTION WITH ONE IN-MEMORY EXTERNAL OVERRIDE")

        external_cf = deepcopy(external_rows)
        patched = 0
        for row in external_cf:
            if (
                str(row["destination_key"]) == DESTINATION_KEY
                and str(row["geo_id"]) == AFFECTED_GEO
                and str(row["direction"]) == DIRECTION
            ):
                row["external_time_s"] = f"{counterfactual['time_s']:.9f}"
                row["external_distance_m"] = f"{counterfactual['distance_m']:.9f}"
                row["external_weight"] = f"{counterfactual['weight']:.12f}"
                row["destination_snap_m"] = f"{dest_snap_m:.9f}"
                row["crossing_snap_m"] = f"{crossing_snap_m:.9f}"
                row["http_status"] = "200"
                row["status"] = "PASS"
                row["error"] = ""
                patched += 1
        if patched != 1:
            raise RuntimeError(f"Expected exactly one in-memory cache patch; got {patched}")

        ie_new, ei_new, cf_diag = gh08.select_routes(
            b1_rows,
            crossings,
            internal_rows,
            external_cf,
        )

        # IE must remain byte-semantically unchanged.
        compare_selection_to_frozen(ie_new, ie_frozen, "IE")

        frozen_ei_by_id = {parse_int(r["b1_row_id"]): r for r in ei_frozen}
        new_ei_by_id = {parse_int(r["b1_row_id"]): r for r in ei_new}
        if set(frozen_ei_by_id) != set(new_ei_by_id):
            raise RuntimeError("EI row identity changed")

        changed_selection_ids: set[int] = set()
        changed_numeric_ids: set[int] = set()

        for row_id in sorted(frozen_ei_by_id):
            old = frozen_ei_by_id[row_id]
            new = new_ei_by_id[row_id]

            if route_selection_signature(old) != route_selection_signature(new):
                changed_selection_ids.add(row_id)

            if str(old["route_status"]) == "PASS" and str(new["route_status"]) == "PASS":
                old_combined = parse_float(old["combined_time_s"])
                new_combined = parse_float(new["combined_time_s"])
                if abs(old_combined - new_combined) > SELECTION_NUMERIC_TOL_S:
                    changed_numeric_ids.add(row_id)

        unexpected = (changed_selection_ids | changed_numeric_ids) - affected_ids
        if unexpected:
            raise RuntimeError(
                f"Unexpected EI rows changed outside affected set: {sorted(unexpected)}"
            )

        affected_rows_out: list[dict[str, Any]] = []
        for row_id in sorted(affected_ids):
            old = frozen_ei_by_id[row_id]
            new = new_ei_by_id[row_id]
            affected_rows_out.append({
                "b1_row_id": row_id,
                "origin_PRO_COM": old["origin_PRO_COM"],
                "origin_COMUNE": old["origin_COMUNE"],
                "dest_COMUNE": old["dest_COMUNE"],
                "Pendolari_raw": old["Pendolari_raw"],
                "flow_daily": old["flow_daily"],
                "old_gateway_id": old["selected_gateway_id"],
                "old_geo_id": old["selected_geo_id"],
                "old_internal_time_s": old["internal_lambda_weighted_time_s"],
                "old_external_time_s": old["external_time_s"],
                "old_combined_time_s": old["combined_time_s"],
                "old_second_best_combined_time_s": old["second_best_combined_time_s"],
                "old_gap_to_second_s": old["gap_to_second_s"],
                "new_gateway_id": new["selected_gateway_id"],
                "new_geo_id": new["selected_geo_id"],
                "new_internal_time_s": new["internal_lambda_weighted_time_s"],
                "new_external_time_s": new["external_time_s"],
                "new_combined_time_s": new["combined_time_s"],
                "new_second_best_combined_time_s": new["second_best_combined_time_s"],
                "new_gap_to_second_s": new["gap_to_second_s"],
                "gateway_changed": str(old["selected_gateway_id"]) != str(new["selected_gateway_id"]),
                "geo_changed": str(old["selected_geo_id"]) != str(new["selected_geo_id"]),
                "combined_delta_s": (
                    parse_float(new["combined_time_s"]) -
                    parse_float(old["combined_time_s"])
                ),
            })

        affected_selection_changes = sum(
            1 for r in affected_rows_out if r["geo_changed"]
        )
        affected_gateway_changes = sum(
            1 for r in affected_rows_out if r["gateway_changed"]
        )

        print(f"affected B1 rows recomputed          = {len(affected_rows_out)}")
        print(f"affected crossing changes            = {affected_selection_changes}")
        print(f"affected gateway changes             = {affected_gateway_changes}")
        print(f"unexpected EI row changes            = 0")
        print("IE unchanged                         = PASS")

        # --------------------------------------------------------------
        # G. Gateway-flow delta
        # --------------------------------------------------------------
        print()
        print("G. GATEWAY FLOW DELTA")

        old_crossing_flow, old_gateway_flow = gh08.aggregate_flow_attribution(
            ie_frozen,
            ei_frozen,
        )
        new_crossing_flow, new_gateway_flow = gh08.aggregate_flow_attribution(
            ie_new,
            ei_new,
        )

        old_g = {
            (str(r["direction"]), str(r["gateway_id"])): r
            for r in old_gateway_flow
        }
        new_g = {
            (str(r["direction"]), str(r["gateway_id"])): r
            for r in new_gateway_flow
        }
        keys = sorted(set(old_g) | set(new_g))
        gateway_delta_rows: list[dict[str, Any]] = []
        for key in keys:
            o = old_g.get(key, {})
            n = new_g.get(key, {})
            old_raw = parse_float(o.get("Pendolari_raw_sum", 0.0))
            new_raw = parse_float(n.get("Pendolari_raw_sum", 0.0))
            old_daily = parse_float(o.get("flow_daily_sum", 0.0))
            new_daily = parse_float(n.get("flow_daily_sum", 0.0))
            if abs(new_raw - old_raw) > FLOW_TOL or abs(new_daily - old_daily) > FLOW_TOL:
                gateway_delta_rows.append({
                    "direction": key[0],
                    "gateway_id": key[1],
                    "old_Pendolari_raw_sum": old_raw,
                    "new_Pendolari_raw_sum": new_raw,
                    "delta_Pendolari_raw": new_raw - old_raw,
                    "old_flow_daily_sum": old_daily,
                    "new_flow_daily_sum": new_daily,
                    "delta_flow_daily": new_daily - old_daily,
                })

        print(f"gateway rows with flow delta          = {len(gateway_delta_rows)}")

        # --------------------------------------------------------------
        # H. Materialize append-only audit
        # --------------------------------------------------------------
        print()
        print("H. MATERIALIZE APPEND-ONLY COUNTERFACTUAL AUDIT")

        route_payload = {
            "schema": "B1_EXT_GH_10C_CASTELFRANCO_EI_COUNTERFACTUAL_ROUTE_V01",
            "relation_id": RELATION_ID,
            "manual_evidence": MANUAL_EVIDENCE,
            "affected_candidate": {
                "destination_key": DESTINATION_KEY,
                "dest_COMUNE": DESTINATION_NAME,
                "direction": DIRECTION,
                "gateway_id": AFFECTED_GATEWAY,
                "geo_id": AFFECTED_GEO,
                "illegal_transition": [ILLEGAL_FROM_WAY, ILLEGAL_NEXT_WAY],
            },
            "baseline": baseline,
            "counterfactual": counterfactual,
            "counterfactual_snap_m": {
                "destination": dest_snap_m,
                "roundabout_center": via_snap_m,
                "crossing": crossing_snap_m,
            },
            "delta": {
                "external_time_s": delta_time_s,
                "external_distance_m": delta_distance_m,
            },
            "counterfactual_illegal_transition_present": False,
        }
        route_path = staging / ROUTE_JSON
        write_json(route_path, route_payload)

        affected_path = staging / AFFECTED_CSV
        write_csv(
            affected_path,
            affected_rows_out,
            [
                "b1_row_id", "origin_PRO_COM", "origin_COMUNE", "dest_COMUNE",
                "Pendolari_raw", "flow_daily",
                "old_gateway_id", "old_geo_id",
                "old_internal_time_s", "old_external_time_s",
                "old_combined_time_s", "old_second_best_combined_time_s",
                "old_gap_to_second_s",
                "new_gateway_id", "new_geo_id",
                "new_internal_time_s", "new_external_time_s",
                "new_combined_time_s", "new_second_best_combined_time_s",
                "new_gap_to_second_s",
                "gateway_changed", "geo_changed", "combined_delta_s",
            ],
        )

        gateway_delta_path = staging / GATEWAY_DELTA_CSV
        write_csv(
            gateway_delta_path,
            gateway_delta_rows,
            [
                "direction", "gateway_id",
                "old_Pendolari_raw_sum", "new_Pendolari_raw_sum",
                "delta_Pendolari_raw",
                "old_flow_daily_sum", "new_flow_daily_sum",
                "delta_flow_daily",
            ],
        )

        next_gate = "TARGETED_EXTERNAL_ROUTE_OVERRIDE_MATERIALIZATION"
        summary = {
            "schema": "B1_EXT_GH_10C_CASTELFRANCO_EI_COUNTERFACTUAL_SUMMARY_V01",
            "verdict": "PASS",
            "relation_id": RELATION_ID,
            "defect_status": "TRUE_ROUTING_DEFECT_CONFIRMED_MANUALLY",
            "manual_evidence": MANUAL_EVIDENCE,
            "affected_candidate": {
                "destination_key": DESTINATION_KEY,
                "dest_COMUNE": DESTINATION_NAME,
                "direction": DIRECTION,
                "gateway_id": AFFECTED_GATEWAY,
                "geo_id": AFFECTED_GEO,
            },
            "affected_b1_rows": len(affected_rows_out),
            "affected_Pendolari_raw": affected_raw,
            "affected_flow_daily": affected_daily,
            "baseline_external_time_s": baseline["time_s"],
            "counterfactual_external_time_s": counterfactual["time_s"],
            "external_time_delta_s": delta_time_s,
            "baseline_external_distance_m": baseline["distance_m"],
            "counterfactual_external_distance_m": counterfactual["distance_m"],
            "external_distance_delta_m": delta_distance_m,
            "counterfactual_via_snap_m": via_snap_m,
            "illegal_transition_removed": True,
            "affected_crossing_changes": affected_selection_changes,
            "affected_gateway_changes": affected_gateway_changes,
            "gateway_flow_delta_rows": len(gateway_delta_rows),
            "unexpected_ei_rows_changed": 0,
            "ie_unchanged": True,
            "formal_override_materialization": "NOT_STARTED",
            "graph_modified": False,
            "PBF_import": "NOT_STARTED",
            "B5_routing": "NOT_STARTED",
            "next_gate": next_gate,
        }
        summary_path = staging / SUMMARY_JSON
        write_json(summary_path, summary)

    finally:
        if proc is not None:
            shutdown_status = gh08.stop_server(proc)
        server_log_handle.close()
        print(f"server shutdown                     = {shutdown_status}")

    # ------------------------------------------------------------------
    # I. Post-run byte integrity + manifest
    # ------------------------------------------------------------------
    print()
    print("I. BYTE-INTEGRITY / FINAL COUNTERFACTUAL GATE")

    # Verify source packages still untouched.
    verify_manifest_outputs("GH08F post-run", gh08f_dir, gh08f_manifest)
    verify_manifest_outputs("GH10B post-run", gh10b_dir, gh10b_manifest)

    graph_after = gh08.graph_inventory(graph_dir)
    if gh08.normalized_inventory(graph_after) != gh08.normalized_inventory(graph_before):
        raise RuntimeError("Italy graph changed during GH10C")
    print("Italy graph unchanged                = PASS")

    # server config/log are evidence too.
    outputs = [
        staging / ROUTE_JSON,
        staging / AFFECTED_CSV,
        staging / GATEWAY_DELTA_CSV,
        staging / SUMMARY_JSON,
        staging / SERVER_CONFIG,
        staging / SERVER_LOG,
    ]
    manifest = {
        "schema": "B1_EXT_GH_10C_CASTELFRANCO_EI_COUNTERFACTUAL_MANIFEST_V01",
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
            "GH10B_manifest": {
                "path": str(gh10b_dir / GH10B_MANIFEST),
                "sha256": sha256(gh10b_dir / GH10B_MANIFEST),
            },
            "graph_manifest": {
                "path": str(graph_manifest_path),
                "sha256": sha256(graph_manifest_path),
            },
        },
        "manual_evidence": MANUAL_EVIDENCE,
        "outputs": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in outputs
        ],
        "next_gate": "TARGETED_EXTERNAL_ROUTE_OVERRIDE_MATERIALIZATION",
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    staging.rename(final_dir)

    summary_final = read_json(final_dir / SUMMARY_JSON)

    print()
    print("=" * 124)
    print("B1_EXT_GH_10C_CASTELFRANCO_EI_ROUNDABOUT_COUNTERFACTUAL = PASS")
    print(f"RELATION_ID = {RELATION_ID}")
    print("CONFIRMED_ROUTING_DEFECT = YES")
    print(f"AFFECTED_B1_ROWS = {summary_final['affected_b1_rows']}")
    print(f"AFFECTED_PENDOLARI_RAW = {summary_final['affected_Pendolari_raw']:.5f}")
    print(f"AFFECTED_FLOW_DAILY = {summary_final['affected_flow_daily']:.5f}")
    print(f"BASELINE_EXTERNAL_TIME_S = {summary_final['baseline_external_time_s']:.3f}")
    print(f"COUNTERFACTUAL_EXTERNAL_TIME_S = {summary_final['counterfactual_external_time_s']:.3f}")
    print(f"EXTERNAL_TIME_DELTA_S = {summary_final['external_time_delta_s']:.3f}")
    print(f"BASELINE_EXTERNAL_DISTANCE_M = {summary_final['baseline_external_distance_m']:.3f}")
    print(f"COUNTERFACTUAL_EXTERNAL_DISTANCE_M = {summary_final['counterfactual_external_distance_m']:.3f}")
    print(f"EXTERNAL_DISTANCE_DELTA_M = {summary_final['external_distance_delta_m']:.3f}")
    print(f"ROUNDABOUT_CENTER_SNAP_M = {summary_final['counterfactual_via_snap_m']:.3f}")
    print("ILLEGAL_TRANSITION_REMOVED = YES")
    print(f"AFFECTED_CROSSING_CHANGES = {summary_final['affected_crossing_changes']}")
    print(f"AFFECTED_GATEWAY_CHANGES = {summary_final['affected_gateway_changes']}")
    print("UNEXPECTED_EI_ROWS_CHANGED = 0")
    print("IE_UNCHANGED = YES")
    print("ITALY_GRAPH_BYTE_IDENTICAL_AFTER_RUN = YES")
    print("GH08F_OUTPUTS_MODIFIED = NO")
    print("GH10B_OUTPUTS_MODIFIED = NO")
    print("PBF_IMPORT = NOT_STARTED")
    print("B5_ROUTING = NOT_STARTED")
    print("FORMAL_OVERRIDE_MATERIALIZATION = NOT_STARTED")
    print("NEXT_GATE = TARGETED_EXTERNAL_ROUTE_OVERRIDE_MATERIALIZATION")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print("=== RUN COMPLETATA ===")
    print(
        "HARD STOP — COUNTERFACTUAL ONLY; DO NOT MODIFY THE FROZEN ITALY GRAPH. "
        "RETURN THE FINAL BLOCK TO THIS CHAT."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
