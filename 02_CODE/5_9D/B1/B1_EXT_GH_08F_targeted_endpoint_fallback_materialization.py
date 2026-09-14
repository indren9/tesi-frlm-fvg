#!/usr/bin/env python3
"""
B1-EXT-GH 08F — TARGETED ENDPOINT FALLBACK MATERIALIZATION

Purpose
-------
Close the GH08 blocker append-only, without rerunning the expensive
34,202 already-valid external candidate routes and without recomputing B5.

Frozen/established endpoint rule
--------------------------------
PRIMARY:
    GraphHopper default LocationIndex search.

FALLBACK:
    ONLY for the 19 external destinations proven by GH08D/GH08E to fail
    with PointNotFound under the default search:
        index.max_region_search = 64

ACCEPTANCE:
    - same existing Italy graph
    - same profile
    - same external municipal geometric centroid
    - same blank snap_prevention
    - crossing snap <= 5 m
    - destination snap <= 10 km
    - finite positive route metrics
    - both IE and EI route semantics
    - no added connector-time term (preserves GH08 endpoint semantics)

The 10 km destination-snap threshold is NOT introduced by this script:
it is the existing GH06/GH08 QA threshold.

Append-only correction
----------------------
GH08 v01 remains preserved as a historical NOT_READY materialization.
This script creates a new v02 package and replaces ONLY the 1,862
PointNotFound candidate rows (19 destinations x 49 crossings x 2 directions).

NO:
- Italy PBF import
- B5 Dijkstra
- modification of GH08 v01
- modification of frozen FVG artifacts
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
import socket
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Authoritative helper implementation / lineage
# ======================================================================================

GH08_TOOL_REL = r"tools\B1_EXT_GH_08_hybrid_routing_materialization.py"
GH08_TOOL_SHA256 = "e60b6655644e50d554c1399a0c7a61cae590ed7add4d12b4970d816c8ee1fe38"

GH08_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v01"
)
GH08_MANIFEST = "B1_EXT_GH_08_hybrid_routing_materialization_manifest_v01.json"
GH08_MANIFEST_SHA256 = "cc47279a8a47b9c69621d1ae71af12adfca48c230b21c0db434b465c8015512c"
GH08_SUMMARY = "B1_EXT_GH_08_hybrid_routing_materialization_summary_v01.json"
GH08_SUMMARY_SHA256 = "2240eb16c11e3b0732814b8f17d9f3f8efcaa94302851948213137a8b411a1f5"

GH08D_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_blocking_diagnostics_v01"
)
GH08D_DEST = "B1_EXT_GH_08D_unreachable_destinations_v01.csv"
GH08D_DEST_SHA256 = "9f7254562d6e92888e23183279badefc5439dfbb4fe6066efa0d9652aaea44a0"
GH08D_MANIFEST = "B1_EXT_GH_08D_blocking_diagnostics_manifest_v01.json"
GH08D_MANIFEST_SHA256 = "b3c401029ed31cbc557dbbe74a1c4ad2292904c60b80b28b58ae0e237a78e5f0"

GH08E_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_endpoint_snap_radius_probe_v01"
)
GH08E_RESULT = "B1_EXT_GH_08E_endpoint_snap_radius_probe_v01.csv"
GH08E_RESULT_SHA256 = "a27684e0fdf062c86b0d3aa9b3517a9e24a30a949a5dd05728efcac52214927d"
GH08E_SUMMARY = "B1_EXT_GH_08E_endpoint_snap_radius_probe_summary_v01.json"
GH08E_SUMMARY_SHA256 = "adced3e8ad936dda437b3bd230bdb7508737e93c2230e32b981eb6dea0adfaea"
GH08E_MANIFEST = "B1_EXT_GH_08E_endpoint_snap_radius_probe_manifest_v01.json"
GH08E_MANIFEST_SHA256 = "9812047d1c207d39667b9219e2cf5fafff2f6af49cb1ba32efe28498172a5fa5"

# ======================================================================================
# Project inputs reused read-only
# ======================================================================================

GH07_MAPPING_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01\B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
)
GH07_MAPPING_SHA256 = "57026868b57e29944d1234fad43078db2c0b15a565039d07a4c1d30ed20ce2cc"

FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"

PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"

# ======================================================================================
# Expected GH08 package files
# ======================================================================================

B1_V01 = "B1_EXT_GH_08_b1_normalized_v01.csv"
INTERNAL_ACCESS_V01 = "B1_EXT_GH_08_internal_access_crossing_costs_v01.csv"
INTERNAL_COMMUNE_V01 = "B1_EXT_GH_08_internal_commune_crossing_costs_v01.csv"
EXTERNAL_V01 = "B1_EXT_GH_08_external_crossing_route_cache_v01.csv"
ENDPOINT_V01 = "B1_EXT_GH_08_endpoint_snap_v01.csv"
IE_V01 = "B1_EXT_GH_08_IE_routing_v01.csv"
EI_V01 = "B1_EXT_GH_08_EI_routing_v01.csv"
CROSSING_FLOW_V01 = "B1_EXT_GH_08_crossing_flow_attribution_v01.csv"
GATEWAY_FLOW_V01 = "B1_EXT_GH_08_gateway_flow_attribution_v01.csv"

# ======================================================================================
# Corrected v02 package
# ======================================================================================

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v02_endpoint_fallback"
)

B1_V02 = "B1_EXT_GH_08F_b1_normalized_v02.csv"
INTERNAL_ACCESS_V02 = "B1_EXT_GH_08F_internal_access_crossing_costs_v02.csv"
INTERNAL_COMMUNE_V02 = "B1_EXT_GH_08F_internal_commune_crossing_costs_v02.csv"
EXTERNAL_V02 = "B1_EXT_GH_08F_external_crossing_route_cache_v02.csv"
ENDPOINT_V02 = "B1_EXT_GH_08F_endpoint_snap_v02.csv"
IE_V02 = "B1_EXT_GH_08F_IE_routing_v02.csv"
EI_V02 = "B1_EXT_GH_08F_EI_routing_v02.csv"
CROSSING_FLOW_V02 = "B1_EXT_GH_08F_crossing_flow_attribution_v02.csv"
GATEWAY_FLOW_V02 = "B1_EXT_GH_08F_gateway_flow_attribution_v02.csv"
SERVER_CONFIG = "graphhopper_b1_ext_server_gh08f_v02.yml"
SERVER_LOG = "graphhopper_b1_ext_server_gh08f_v02.log"
SUMMARY_JSON = "B1_EXT_GH_08F_targeted_endpoint_fallback_summary_v02.json"
MANIFEST_JSON = "B1_EXT_GH_08F_targeted_endpoint_fallback_manifest_v02.json"

# ======================================================================================
# Frozen/controlled rule
# ======================================================================================

EXPECTED_B1_ROWS = 2_895
EXPECTED_DESTINATIONS = 368
EXPECTED_FALLBACK_DESTINATIONS = 19
EXPECTED_CROSSINGS = 49
EXPECTED_FALLBACK_CANDIDATES = 1_862
EXPECTED_ORIGINAL_PASS_CANDIDATES = 34_202
EXPECTED_RAW_FLOW = 14_458.0
EXPECTED_DAILY_FLOW = 6_195.97590

FALLBACK_MAX_REGION_SEARCH = 64
MAX_CROSSING_SNAP_M = 5.0
MAX_DESTINATION_SNAP_M = 10_000.0
FLOW_TOL = 1e-6
REGRESSION_TIME_TOL_S = 1e-9
NUMERIC_TIE_TOL_S = 1e-6

APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
HTTP_WORKERS_DEFAULT = 6

PRINT_LOCK = threading.Lock()


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
    print(f"{label:<30} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return obj


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    if not cols:
        raise RuntimeError(f"Missing CSV header: {path}")
    return rows, cols


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    if fieldnames is None:
        if not rows:
            raise RuntimeError(f"Cannot infer columns for empty CSV: {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def assert_close(actual: float, expected: float, label: str, tol: float) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(
            f"{label}: {actual} != {expected} (tol={tol})"
        )


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("gh08_authoritative_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_output_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    rows = manifest.get("outputs")
    if not isinstance(rows, list):
        raise RuntimeError("GH08 manifest missing outputs list")
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid GH08 manifest output item")
        name = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid GH08 manifest output item: {item}")
        if name in out:
            raise RuntimeError(f"Duplicate GH08 manifest output: {name}")
        out[name] = digest
    return out


def graph_inventory(graph_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(x for x in graph_dir.rglob("*") if x.is_file()):
        rows.append({
            "relative_path": p.relative_to(graph_dir).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return rows


def normalized_inventory(rows: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
    return sorted(
        (
            str(r["relative_path"]),
            int(r["size_bytes"]),
            str(r["sha256"]).lower(),
        )
        for r in rows
    )


def route_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["destination_key"]),
        str(row["geo_id"]),
        str(row["direction"]),
    )


def helper_self_tests() -> None:
    r = {
        "destination_key": "d",
        "geo_id": "g",
        "direction": "IE",
    }
    if route_key(r) != ("d", "g", "IE"):
        raise AssertionError("route_key self-test")
    assert_close(
        5860.84980 + 335.12610,
        EXPECTED_DAILY_FLOW,
        "flow arithmetic self-test",
        1e-9,
    )
    if EXPECTED_FALLBACK_DESTINATIONS * EXPECTED_CROSSINGS * 2 != EXPECTED_FALLBACK_CANDIDATES:
        raise AssertionError("fallback candidate identity self-test")


# ======================================================================================
# GraphHopper config/server
# ======================================================================================

def set_or_insert_graphhopper_yaml_int(
    text: str,
    key: str,
    value: int,
) -> tuple[str, str]:
    lines = text.splitlines()

    hits = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith(key + ":")
    ]
    if len(hits) > 1:
        raise RuntimeError(f"Multiple active '{key}:' lines")

    gh_hits = [i for i, line in enumerate(lines) if line == "graphhopper:"]
    if len(gh_hits) != 1:
        raise RuntimeError(
            f"Expected exactly one root-level graphhopper section; found {len(gh_hits)}"
        )
    gh_i = gh_hits[0]

    gh_end = len(lines)
    for i in range(gh_i + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent_len = len(lines[i]) - len(lines[i].lstrip())
        if indent_len == 0:
            gh_end = i
            break

    if len(hits) == 1:
        i = hits[0]
        if not (gh_i < i < gh_end):
            raise RuntimeError(
                f"Active '{key}:' exists outside graphhopper section"
            )
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        if not indent:
            raise RuntimeError(f"Unsafe root-level '{key}:'")
        old = lines[i].strip()
        lines[i] = f"{indent}{key}: {int(value)}"
        return "\n".join(lines) + "\n", f"REPLACED_IN_GRAPHHOPPER [{old}]"

    refs: list[tuple[int, str]] = []
    for ref_key in ("graph.location", "datareader.file"):
        for i in range(gh_i + 1, gh_end):
            if lines[i].lstrip().startswith(ref_key + ":"):
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                if indent:
                    refs.append((i, indent))
    if not refs:
        raise RuntimeError("Could not infer graphhopper scalar indentation")
    indents = {indent for _, indent in refs}
    if len(indents) != 1:
        raise RuntimeError(f"Inconsistent graphhopper scalar indentation: {indents}")
    indent = next(iter(indents))

    graph_location_hits = [
        i for i in range(gh_i + 1, gh_end)
        if lines[i].lstrip().startswith("graph.location:")
    ]
    if len(graph_location_hits) == 1:
        insert_at = graph_location_hits[0] + 1
    else:
        insert_at = max(i for i, _ in refs) + 1

    lines.insert(insert_at, f"{indent}{key}: {int(value)}")
    return "\n".join(lines) + "\n", "INSERTED_IN_GRAPHHOPPER_SECTION"


def make_fallback_server_config(
    gh08,
    profile_config: Path,
    graph_dir: Path,
    staging: Path,
) -> tuple[str, str]:
    # First create the exact GH08 safe existing-graph server config:
    # sentinel datareader + frozen graph.location + localhost server block.
    text = gh08.make_server_config(profile_config, graph_dir, staging)
    # Then change only the LocationIndex search region inside graphhopper:.
    text, action = set_or_insert_graphhopper_yaml_int(
        text,
        "index.max_region_search",
        FALLBACK_MAX_REGION_SEARCH,
    )
    return text, action


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for_server(proc: subprocess.Popen) -> None:
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"GraphHopper server exited early with code {proc.returncode}"
            )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", APP_PORT)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(
        f"GraphHopper server did not open port {APP_PORT}"
    )


def stop_server(proc: subprocess.Popen | None) -> str:
    if proc is None:
        return "NOT_STARTED"
    if proc.poll() is not None:
        return f"ALREADY_EXITED_{proc.returncode}"
    proc.terminate()
    try:
        proc.wait(timeout=20)
        return f"TERMINATED_{proc.returncode}"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        return f"KILLED_{proc.returncode}"


# ======================================================================================
# Regression checks
# ======================================================================================

def compare_previous_pass_rows(
    old_rows: list[dict[str, str]],
    new_rows: list[dict[str, Any]],
    direction: str,
) -> int:
    old_by_id = {parse_int(r["b1_row_id"]): r for r in old_rows}
    new_by_id = {parse_int(r["b1_row_id"]): r for r in new_rows}
    if set(old_by_id) != set(new_by_id):
        raise RuntimeError(f"{direction}: B1 row identity changed")

    compared = 0
    exact_fields = (
        "selected_geo_id",
        "selected_gateway_id",
        "route_status",
    )
    numeric_fields = (
        "internal_lambda_weighted_time_s",
        "external_time_s",
        "combined_time_s",
        "external_distance_m",
        "crossing_snap_m",
        "destination_snap_m",
    )

    for row_id, old in old_by_id.items():
        if old["route_status"] != "PASS":
            continue
        new = new_by_id[row_id]
        for field in exact_fields:
            if str(old[field]) != str(new[field]):
                raise RuntimeError(
                    f"{direction} regression row={row_id} field={field}: "
                    f"{old[field]!r} != {new[field]!r}"
                )
        for field in numeric_fields:
            assert_close(
                parse_float(new[field]),
                parse_float(old[field]),
                f"{direction} regression row={row_id} field={field}",
                REGRESSION_TIME_TOL_S,
            )
        compared += 1
    return compared


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument(
        "--http-workers",
        type=int,
        default=HTTP_WORKERS_DEFAULT,
    )
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_08F_HELPER_SELF_TESTS = PASS")
        return 0

    if not (1 <= args.http_workers <= 16):
        raise ValueError("--http-workers must be in [1, 16]")

    root = Path(args.root)
    gh08_tool = root / Path(GH08_TOOL_REL)
    gh08_dir = root / Path(GH08_DIR_REL)
    gh08d_dir = root / Path(GH08D_DIR_REL)
    gh08e_dir = root / Path(GH08E_DIR_REL)
    gh07_mapping = root / Path(GH07_MAPPING_REL)
    graph_dir = root / Path(FINAL_GRAPH_REL)
    gh_jar = root / Path(GH_JAR_REL)
    runtime_root = root / Path(RUNTIME_REL)
    profile_config = root / Path(PROFILE_CONFIG_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name
        + "_STAGING_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 08F — TARGETED ENDPOINT FALLBACK MATERIALIZATION")
    print("=" * 124)
    print(
        "APPEND-ONLY V02 / 19 POINTNOTFOUND DESTINATIONS ONLY / "
        "NO B5 RERUN / NO PBF IMPORT"
    )
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Strict evidence and authoritative helper identity
    # ------------------------------------------------------------------
    print("A. STRICT EVIDENCE / LINEAGE IDENTITY")
    strict_hash("GH08 tool", gh08_tool, GH08_TOOL_SHA256)
    strict_hash(
        "GH08 manifest",
        gh08_dir / GH08_MANIFEST,
        GH08_MANIFEST_SHA256,
    )
    strict_hash(
        "GH08 summary",
        gh08_dir / GH08_SUMMARY,
        GH08_SUMMARY_SHA256,
    )
    strict_hash(
        "GH08D destinations",
        gh08d_dir / GH08D_DEST,
        GH08D_DEST_SHA256,
    )
    strict_hash(
        "GH08D manifest",
        gh08d_dir / GH08D_MANIFEST,
        GH08D_MANIFEST_SHA256,
    )
    strict_hash(
        "GH08E result",
        gh08e_dir / GH08E_RESULT,
        GH08E_RESULT_SHA256,
    )
    strict_hash(
        "GH08E summary",
        gh08e_dir / GH08E_SUMMARY,
        GH08E_SUMMARY_SHA256,
    )
    strict_hash(
        "GH08E manifest",
        gh08e_dir / GH08E_MANIFEST,
        GH08E_MANIFEST_SHA256,
    )
    strict_hash("GH07 mapping", gh07_mapping, GH07_MAPPING_SHA256)
    strict_hash("GH JAR", gh_jar, GH_JAR_SHA256)
    strict_hash(
        "profile config",
        profile_config,
        PROFILE_CONFIG_SHA256,
    )

    gh08 = load_module(gh08_tool)
    gh08.helper_self_tests()
    if abs(float(gh08.MAX_CROSSING_SNAP_M) - MAX_CROSSING_SNAP_M) > 1e-12:
        raise RuntimeError("Crossing snap threshold drift from GH08")
    if abs(float(gh08.MAX_DESTINATION_SNAP_M) - MAX_DESTINATION_SNAP_M) > 1e-12:
        raise RuntimeError("Destination snap threshold drift from GH08")
    if int(gh08.EXPECTED_B1_ROWS) != EXPECTED_B1_ROWS:
        raise RuntimeError("GH08 B1 row contract drift")
    print("GH08 helper self-tests       PASS")
    print("endpoint QA thresholds       PASS")

    gh08_manifest = read_json(gh08_dir / GH08_MANIFEST)
    gh08_summary = read_json(gh08_dir / GH08_SUMMARY)
    if gh08_summary.get("verdict") != "NOT_READY":
        raise RuntimeError("Expected GH08 v01 verdict NOT_READY")

    output_hashes = manifest_output_hashes(gh08_manifest)
    for filename, digest in sorted(output_hashes.items()):
        p = gh08_dir / filename
        if not p.is_file():
            raise FileNotFoundError(p)
        if sha256(p) != digest:
            raise RuntimeError(f"GH08 v01 output changed: {filename}")
    print(f"GH08 v01 outputs verified   = {len(output_hashes)}")

    gh08e_summary = read_json(gh08e_dir / GH08E_SUMMARY)
    if gh08e_summary.get("verdict") != "PASS":
        raise RuntimeError("GH08E verdict is not PASS")
    if gh08e_summary.get("cause_classification") != "LOCATION_INDEX_SEARCH_RADIUS_LIMIT":
        raise RuntimeError(
            f"Unexpected GH08E cause: "
            f"{gh08e_summary.get('cause_classification')}"
        )
    if int(gh08e_summary.get("destinations_pass_both_directions", -1)) != EXPECTED_FALLBACK_DESTINATIONS:
        raise RuntimeError("GH08E did not pass all 19 destinations")
    if float(gh08e_summary["destination_snap_m"]["max"]) > MAX_DESTINATION_SNAP_M:
        raise RuntimeError("GH08E max destination snap exceeds 10 km contract")
    print("GH08E causal chain           PASS")

    # ------------------------------------------------------------------
    # B. Verify old package and fallback set
    # ------------------------------------------------------------------
    print()
    print("B. GH08 V01 CACHE / FALLBACK SET AUDIT")

    b1_rows, b1_cols = read_csv(gh08_dir / B1_V01)
    internal_access_rows, internal_access_cols = read_csv(
        gh08_dir / INTERNAL_ACCESS_V01
    )
    internal_commune_rows, internal_commune_cols = read_csv(
        gh08_dir / INTERNAL_COMMUNE_V01
    )
    external_old, external_cols = read_csv(gh08_dir / EXTERNAL_V01)
    ie_old, ie_old_cols = read_csv(gh08_dir / IE_V01)
    ei_old, ei_old_cols = read_csv(gh08_dir / EI_V01)

    if len(b1_rows) != EXPECTED_B1_ROWS:
        raise RuntimeError(f"B1 v01 rows = {len(b1_rows)}")
    if len(external_old) != EXPECTED_DESTINATIONS * EXPECTED_CROSSINGS * 2:
        raise RuntimeError(f"External v01 rows = {len(external_old)}")

    fallback_dest_rows, _ = read_csv(gh08d_dir / GH08D_DEST)
    fallback_dest_keys = {
        str(r["destination_key"]) for r in fallback_dest_rows
    }
    if len(fallback_dest_keys) != EXPECTED_FALLBACK_DESTINATIONS:
        raise RuntimeError(
            f"Fallback destinations = {len(fallback_dest_keys)}"
        )

    status_counts = Counter(str(r["status"]) for r in external_old)
    if status_counts != Counter({
        "PASS": EXPECTED_ORIGINAL_PASS_CANDIDATES,
        "UNREACHABLE": EXPECTED_FALLBACK_CANDIDATES,
    }):
        raise RuntimeError(
            f"Unexpected GH08 external status counts: {dict(status_counts)}"
        )

    failed_old = [
        r for r in external_old if str(r["status"]) == "UNREACHABLE"
    ]
    failed_keys = {route_key(r) for r in failed_old}
    if len(failed_keys) != EXPECTED_FALLBACK_CANDIDATES:
        raise RuntimeError("Fallback route-key count mismatch")
    if {
        str(r["destination_key"]) for r in failed_old
    } != fallback_dest_keys:
        raise RuntimeError(
            "GH08 failed destination set != GH08D 19-destination set"
        )
    if any("cannot find point" not in str(r.get("error", "")).lower() for r in failed_old):
        raise RuntimeError(
            "At least one GH08 fallback candidate is not PointNotFound"
        )

    per_destination_failed = Counter(
        str(r["destination_key"]) for r in failed_old
    )
    if set(per_destination_failed.values()) != {EXPECTED_CROSSINGS * 2}:
        raise RuntimeError(
            f"Fallback rows are not exactly 49x2 per destination: "
            f"{sorted(set(per_destination_failed.values()))}"
        )

    unique_dest_keys = {str(r["destination_key"]) for r in b1_rows}
    if len(unique_dest_keys) != EXPECTED_DESTINATIONS:
        raise RuntimeError(
            f"Unique B1 destinations = {len(unique_dest_keys)}"
        )

    print(f"original PASS candidates    = {status_counts['PASS']:,}")
    print(f"fallback candidates         = {status_counts['UNREACHABLE']:,}")
    print(f"fallback destinations       = {len(fallback_dest_keys)}")
    print("failure mechanism           = POINT_NOT_FOUND only")

    # ------------------------------------------------------------------
    # C. Load frozen crossing definitions and target destination objects
    # ------------------------------------------------------------------
    print()
    print("C. TARGETED FALLBACK TASK MATERIALIZATION")

    crossings = gh08.load_crossings(gh07_mapping)
    if len(crossings) != EXPECTED_CROSSINGS:
        raise RuntimeError("Crossing count mismatch")

    dest_by_key: dict[str, dict[str, Any]] = {}
    for r in b1_rows:
        key = str(r["destination_key"])
        if key not in fallback_dest_keys:
            continue
        candidate = {
            "destination_key": key,
            "dest_code_raw": str(r["dest_code_raw"]),
            "dest_code_join": str(r["dest_code_join"]),
            "dest_COMUNE": str(r["dest_COMUNE"]),
            "dest_lon": parse_float(r["dest_lon"]),
            "dest_lat": parse_float(r["dest_lat"]),
        }
        prev = dest_by_key.get(key)
        if prev is not None and prev != candidate:
            raise RuntimeError(f"Inconsistent destination identity: {key}")
        dest_by_key[key] = candidate
    if len(dest_by_key) != EXPECTED_FALLBACK_DESTINATIONS:
        raise RuntimeError(
            f"Materialized fallback destination objects = {len(dest_by_key)}"
        )

    tasks = [
        (dest_by_key[key], crossing, direction)
        for key in sorted(dest_by_key)
        for crossing in crossings
        for direction in ("IE", "EI")
    ]
    if len(tasks) != EXPECTED_FALLBACK_CANDIDATES:
        raise RuntimeError(f"Fallback tasks = {len(tasks)}")
    print(f"fallback route calls        = {len(tasks):,}")
    print(f"HTTP workers                = {args.http_workers}")
    print(f"index.max_region_search     = {FALLBACK_MAX_REGION_SEARCH}")
    print(f"destination snap hard cap m = {MAX_DESTINATION_SNAP_M:.0f}")

    # ------------------------------------------------------------------
    # D. Start existing graph with controlled fallback search
    # ------------------------------------------------------------------
    print()
    print("D. SAFE EXISTING-GRAPH FALLBACK SERVER")

    graph_manifest_path, graph_manifest = gh08.find_graph_manifest(root)
    graph_before = gh08.graph_inventory(graph_dir)
    if gh08.normalized_inventory(graph_before) != gh08.normalized_inventory(
        graph_manifest.get("files", [])
    ):
        raise RuntimeError("Italy graph differs from frozen manifest")

    if not port_is_free(APP_PORT):
        raise RuntimeError(f"Application port {APP_PORT} already in use")
    if not port_is_free(ADMIN_PORT):
        raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")

    staging.mkdir(parents=True, exist_ok=False)

    server_config_path = staging / SERVER_CONFIG
    server_text, config_action = make_fallback_server_config(
        gh08,
        profile_config,
        graph_dir,
        staging,
    )
    server_config_path.write_text(server_text, encoding="utf-8")
    print(f"config action               = {config_action}")
    print("snap_prevention             = BLANK")
    print("national PBF passed         = NO")
    print("bind host                   = localhost")

    java_exe = gh08.find_java(runtime_root)
    server_log_path = staging / SERVER_LOG
    server_log_handle = server_log_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    )

    cmd = [
        str(java_exe),
        f"-Xms{SERVER_XMS_MIB}m",
        f"-Xmx{SERVER_XMX_GIB}g",
        "-XX:+UseParallelGC",
        "-jar",
        str(gh_jar),
        "server",
        str(server_config_path),
    ]

    proc: subprocess.Popen | None = None
    stop_status = "NOT_STARTED"
    fallback_new: list[dict[str, Any]] = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=staging,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_server(proc)
        print("SERVER_LOAD                 = PASS")

        # --------------------------------------------------------------
        # E. Reroute ONLY the failed candidate keys
        # --------------------------------------------------------------
        print()
        print("E. TARGETED 1,862-CANDIDATE FALLBACK ROUTING")

        started = time.time()
        completed = 0

        with ThreadPoolExecutor(
            max_workers=args.http_workers
        ) as pool:
            futures = {
                pool.submit(
                    gh08.evaluate_external_task,
                    dest,
                    crossing,
                    direction,
                ): (
                    str(dest["destination_key"]),
                    str(crossing["geo_id"]),
                    direction,
                )
                for dest, crossing, direction in tasks
            }

            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    dest_key, geo_id, direction = key
                    row = {
                        "destination_key": dest_key,
                        "dest_code_raw": "",
                        "dest_code_join": "",
                        "dest_COMUNE": "",
                        "dest_lon": None,
                        "dest_lat": None,
                        "gateway_id": "",
                        "geo_id": geo_id,
                        "crossing_lon": None,
                        "crossing_lat": None,
                        "direction": direction,
                        "external_time_s": None,
                        "external_distance_m": None,
                        "external_weight": None,
                        "crossing_snap_m": None,
                        "destination_snap_m": None,
                        "http_status": None,
                        "status": "ERROR",
                        "error": repr(exc),
                    }
                fallback_new.append(row)
                completed += 1
                if completed % 100 == 0 or completed == len(tasks):
                    elapsed = max(time.time() - started, 1e-9)
                    rate = completed / elapsed
                    remain = (
                        len(tasks) - completed
                    ) / max(rate, 1e-9)
                    with PRINT_LOCK:
                        print(
                            f"  fallback {completed:,}/{len(tasks):,} "
                            f"({100.0*completed/len(tasks):5.1f}%) "
                            f"rate={rate:6.1f}/s "
                            f"ETA={remain/60:5.1f} min"
                        )

        fallback_new.sort(key=route_key)
        fallback_counts = Counter(
            str(r["status"]) for r in fallback_new
        )

        fallback_max_cross = max(
            parse_float(r["crossing_snap_m"])
            for r in fallback_new
            if r["crossing_snap_m"] is not None
        )
        fallback_max_dest = max(
            parse_float(r["destination_snap_m"])
            for r in fallback_new
            if r["destination_snap_m"] is not None
        )

        print(f"fallback status counts      = {dict(fallback_counts)}")
        print(f"fallback max crossing snap  = {fallback_max_cross:.3f} m")
        print(f"fallback max destination snap = {fallback_max_dest:.3f} m")

        if fallback_counts != Counter({
            "PASS": EXPECTED_FALLBACK_CANDIDATES
        }):
            raise RuntimeError(
                f"Fallback did not close all candidates: "
                f"{dict(fallback_counts)}"
            )
        if fallback_max_cross > MAX_CROSSING_SNAP_M:
            raise RuntimeError("Fallback crossing snap exceeds 5 m")
        if fallback_max_dest > MAX_DESTINATION_SNAP_M:
            raise RuntimeError("Fallback destination snap exceeds 10 km")

        new_keys = {route_key(r) for r in fallback_new}
        if new_keys != failed_keys:
            raise RuntimeError(
                "Targeted fallback route-key set differs from GH08 failures"
            )

        # --------------------------------------------------------------
        # F. Merge cache append-only and recompute only downstream selection
        # --------------------------------------------------------------
        print()
        print("F. APPEND-ONLY V02 CACHE MERGE / ROUTE SELECTION")

        replacement = {
            route_key(r): r for r in fallback_new
        }
        merged: list[dict[str, Any]] = []
        preserved_original_pass = 0
        replaced = 0

        for old in external_old:
            key = route_key(old)
            if key in replacement:
                merged.append(replacement[key])
                replaced += 1
            else:
                # preserve the original valid row verbatim at dict/value level
                merged.append(old)
                preserved_original_pass += 1

        merged.sort(key=route_key)

        if replaced != EXPECTED_FALLBACK_CANDIDATES:
            raise RuntimeError(f"Replaced rows = {replaced}")
        if preserved_original_pass != EXPECTED_ORIGINAL_PASS_CANDIDATES:
            raise RuntimeError(
                f"Preserved original PASS rows = {preserved_original_pass}"
            )
        if Counter(str(r["status"]) for r in merged) != Counter({
            "PASS": EXPECTED_DESTINATIONS * EXPECTED_CROSSINGS * 2
        }):
            raise RuntimeError("Merged external cache is not 100% PASS")

        # Ensure all 34,202 previously-valid rows are dict-identical.
        old_by_key = {route_key(r): r for r in external_old}
        merged_by_key = {route_key(r): r for r in merged}
        for key, old in old_by_key.items():
            if str(old["status"]) != "PASS":
                continue
            if merged_by_key[key] != old:
                raise RuntimeError(
                    f"Previously valid external cache row changed: {key}"
                )

        ie_new, ei_new, selection_diag = gh08.select_routes(
            b1_rows,
            crossings,
            internal_commune_rows,
            merged,
        )

        if len(ie_new) != EXPECTED_B1_ROWS or len(ei_new) != EXPECTED_B1_ROWS:
            raise RuntimeError("IE/EI v02 row count mismatch")

        ie_pass = sum(
            1 for r in ie_new if r["route_status"] == "PASS"
        )
        ei_pass = sum(
            1 for r in ei_new if r["route_status"] == "PASS"
        )
        ie_daily = sum(
            parse_float(r["flow_daily"])
            for r in ie_new
            if r["route_status"] == "PASS"
        )
        ei_daily = sum(
            parse_float(r["flow_daily"])
            for r in ei_new
            if r["route_status"] == "PASS"
        )

        prior_ie_regression = compare_previous_pass_rows(
            ie_old,
            ie_new,
            "IE",
        )
        prior_ei_regression = compare_previous_pass_rows(
            ei_old,
            ei_new,
            "EI",
        )

        crossing_flow, gateway_flow = gh08.aggregate_flow_attribution(
            ie_new,
            ei_new,
        )

        print(f"IE routed                  = {ie_pass}/{EXPECTED_B1_ROWS}")
        print(f"EI routed                  = {ei_pass}/{EXPECTED_B1_ROWS}")
        print(f"IE daily flow              = {ie_daily:.5f}")
        print(f"EI daily flow              = {ei_daily:.5f}")
        print(f"prior IE PASS unchanged    = {prior_ie_regression}")
        print(f"prior EI PASS unchanged    = {prior_ei_regression}")
        print(
            f"cross-gateway ties IE/EI   = "
            f"{selection_diag['IE_cross_gateway_numeric_ties']}/"
            f"{selection_diag['EI_cross_gateway_numeric_ties']}"
        )

        # --------------------------------------------------------------
        # G. Materialize v02 in staging
        # --------------------------------------------------------------
        print()
        print("G. MATERIALIZE CORRECTED V02 PACKAGE")

        # byte-identical copies of unchanged expensive/internal materializations
        copy_pairs = [
            (gh08_dir / B1_V01, staging / B1_V02),
            (
                gh08_dir / INTERNAL_ACCESS_V01,
                staging / INTERNAL_ACCESS_V02,
            ),
            (
                gh08_dir / INTERNAL_COMMUNE_V01,
                staging / INTERNAL_COMMUNE_V02,
            ),
        ]
        for src, dst in copy_pairs:
            shutil.copyfile(src, dst)
            if sha256(src) != sha256(dst):
                raise RuntimeError(
                    f"Copied immutable materialization changed: {src.name}"
                )

        external_path = staging / EXTERNAL_V02
        endpoint_path = staging / ENDPOINT_V02
        ie_path = staging / IE_V02
        ei_path = staging / EI_V02
        crossing_flow_path = staging / CROSSING_FLOW_V02
        gateway_flow_path = staging / GATEWAY_FLOW_V02

        write_csv(
            external_path,
            merged,
            fieldnames=external_cols,
        )
        write_csv(
            endpoint_path,
            gh08.endpoint_snap_rows(merged),
        )
        write_csv(ie_path, ie_new)
        write_csv(ei_path, ei_new)
        write_csv(
            crossing_flow_path,
            crossing_flow,
            fieldnames=[
                "direction",
                "gateway_id",
                "geo_id",
                "b1_rows",
                "Pendolari_raw_sum",
                "flow_daily_sum",
            ],
        )
        write_csv(
            gateway_flow_path,
            gateway_flow,
            fieldnames=[
                "direction",
                "gateway_id",
                "b1_rows",
                "Pendolari_raw_sum",
                "flow_daily_sum",
            ],
        )

        # --------------------------------------------------------------
        # H. Gate + integrity
        # --------------------------------------------------------------
        blockers: list[str] = []
        if fallback_counts != Counter({
            "PASS": EXPECTED_FALLBACK_CANDIDATES
        }):
            blockers.append("FALLBACK_CANDIDATE_FAILURE")
        if ie_pass != EXPECTED_B1_ROWS:
            blockers.append("IE_RELATION_UNREACHABLE")
        if ei_pass != EXPECTED_B1_ROWS:
            blockers.append("EI_RELATION_UNREACHABLE")
        if abs(ie_daily - EXPECTED_DAILY_FLOW) > FLOW_TOL:
            blockers.append("IE_FLOW_NOT_CONSERVED")
        if abs(ei_daily - EXPECTED_DAILY_FLOW) > FLOW_TOL:
            blockers.append("EI_FLOW_NOT_CONSERVED")
        if prior_ie_regression != EXPECTED_B1_ROWS - 162:
            blockers.append("IE_PREVIOUS_PASS_REGRESSION")
        if prior_ei_regression != EXPECTED_B1_ROWS - 162:
            blockers.append("EI_PREVIOUS_PASS_REGRESSION")
        if selection_diag["IE_cross_gateway_numeric_ties"] != 0:
            blockers.append("IE_CROSS_GATEWAY_NUMERIC_TIE")
        if selection_diag["EI_cross_gateway_numeric_ties"] != 0:
            blockers.append("EI_CROSS_GATEWAY_NUMERIC_TIE")
        if selection_diag["IE_min_valid_crossing_candidates"] != EXPECTED_CROSSINGS:
            blockers.append("IE_NOT_ALL_49_CANDIDATES_VALID")
        if selection_diag["EI_min_valid_crossing_candidates"] != EXPECTED_CROSSINGS:
            blockers.append("EI_NOT_ALL_49_CANDIDATES_VALID")

        stop_status = stop_server(proc)
        proc = None
        server_log_handle.close()

        graph_after = gh08.graph_inventory(graph_dir)
        graph_unchanged = (
            gh08.normalized_inventory(graph_before)
            == gh08.normalized_inventory(graph_after)
        )
        if not graph_unchanged:
            blockers.append("ITALY_GRAPH_CHANGED")

        # Re-hash ALL GH08 v01 outputs after the correction run.
        gh08_v01_unchanged = True
        for filename, digest in sorted(output_hashes.items()):
            p = gh08_dir / filename
            if sha256(p) != digest:
                gh08_v01_unchanged = False
                blockers.append(f"GH08_V01_CHANGED:{filename}")
        if not gh08_v01_unchanged:
            raise RuntimeError(
                "Historical GH08 v01 materialization changed"
            )

        verdict = "PASS" if not blockers else "NOT_READY"
        next_gate = (
            "B1_SELECTED_ROUTE_DIAGNOSTICS_FINAL_GATE"
            if verdict == "PASS"
            else "REVIEW_GH08F_BLOCKERS"
        )

        print()
        print("H. BYTE-INTEGRITY / GATE")
        print(f"server shutdown            = {stop_status}")
        print(
            f"Italy graph unchanged      = "
            f"{'PASS' if graph_unchanged else 'FAIL'}"
        )
        print("GH08 v01 preserved         = PASS")

        summary = {
            "schema": "B1_EXT_GH_08F_TARGETED_ENDPOINT_FALLBACK_SUMMARY_V02",
            "verdict": verdict,
            "blocking_reasons": blockers,
            "lineage": {
                "supersedes_for_closure_evidence": (
                    "B1_EXT_GH_08_HYBRID_ROUTING_MATERIALIZATION_V01_NOT_READY"
                ),
                "historical_v01_preserved": True,
                "rerun_scope": "ONLY_1862_POINTNOTFOUND_EXTERNAL_CANDIDATES",
                "b5_recomputed": False,
                "original_external_pass_candidates_reused": EXPECTED_ORIGINAL_PASS_CANDIDATES,
            },
            "endpoint_rule": {
                "primary": "GRAPHHOPPER_DEFAULT_LOCATION_INDEX_SEARCH",
                "fallback_trigger": "POINT_NOT_FOUND_ONLY",
                "fallback_index_max_region_search": FALLBACK_MAX_REGION_SEARCH,
                "fallback_destinations": EXPECTED_FALLBACK_DESTINATIONS,
                "fallback_candidates": EXPECTED_FALLBACK_CANDIDATES,
                "crossing_snap_threshold_m": MAX_CROSSING_SNAP_M,
                "destination_snap_threshold_m": MAX_DESTINATION_SNAP_M,
                "external_endpoint": "MUNICIPAL_GEOMETRIC_CENTROID",
                "snap_prevention": "BLANK",
                "connector_time_added": False,
                "semantics": (
                    "PRESERVE_GH08_SNAPPED_ENDPOINT_REPRESENTATION; "
                    "SNAP_DISTANCE_IS_QA_DIAGNOSTIC"
                ),
            },
            "external_cache": {
                "rows": len(merged),
                "status_counts": dict(
                    sorted(
                        Counter(
                            str(r["status"]) for r in merged
                        ).items()
                    )
                ),
                "original_pass_rows_preserved": preserved_original_pass,
                "fallback_rows_replaced": replaced,
                "fallback_max_crossing_snap_m": fallback_max_cross,
                "fallback_max_destination_snap_m": fallback_max_dest,
            },
            "selection": {
                **selection_diag,
                "IE_routed": ie_pass,
                "EI_routed": ei_pass,
                "IE_daily_flow": ie_daily,
                "EI_daily_flow": ei_daily,
                "expected_daily_flow_each": EXPECTED_DAILY_FLOW,
                "prior_IE_PASS_rows_unchanged": prior_ie_regression,
                "prior_EI_PASS_rows_unchanged": prior_ei_regression,
            },
            "integrity": {
                "italy_graph_byte_identical_after_run": graph_unchanged,
                "gh08_v01_outputs_unchanged": gh08_v01_unchanged,
                "frozen_fvg_artifacts_modified": False,
            },
            "scope_guardrail": {
                "pbf_import": "NOT_STARTED",
                "b5_dijkstra": "NOT_STARTED",
                "gravity_reopened": False,
                "selected_route_external_subgraph_diagnostics": "NOT_STARTED",
                "ignored_restriction_intersection_audit": "NOT_STARTED",
            },
            "next_gate": next_gate,
        }
        summary_path = staging / SUMMARY_JSON
        write_json(summary_path, summary)

        outputs = [
            staging / B1_V02,
            staging / INTERNAL_ACCESS_V02,
            staging / INTERNAL_COMMUNE_V02,
            external_path,
            endpoint_path,
            ie_path,
            ei_path,
            crossing_flow_path,
            gateway_flow_path,
            server_config_path,
            server_log_path,
            summary_path,
        ]

        manifest = {
            "schema": "B1_EXT_GH_08F_TARGETED_ENDPOINT_FALLBACK_MANIFEST_V02",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "inputs": {
                "gh08_tool": {
                    "path": str(gh08_tool),
                    "sha256": sha256(gh08_tool),
                },
                "gh08_manifest": {
                    "path": str(gh08_dir / GH08_MANIFEST),
                    "sha256": sha256(gh08_dir / GH08_MANIFEST),
                },
                "gh08d_manifest": {
                    "path": str(gh08d_dir / GH08D_MANIFEST),
                    "sha256": sha256(gh08d_dir / GH08D_MANIFEST),
                },
                "gh08e_manifest": {
                    "path": str(gh08e_dir / GH08E_MANIFEST),
                    "sha256": sha256(gh08e_dir / GH08E_MANIFEST),
                },
                "gh07_mapping": {
                    "path": str(gh07_mapping),
                    "sha256": sha256(gh07_mapping),
                },
                "graph_manifest": {
                    "path": str(graph_manifest_path),
                    "sha256": sha256(graph_manifest_path),
                },
            },
            "historical_v01_output_hashes": output_hashes,
            "outputs": [
                {
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "sha256": sha256(p),
                }
                for p in outputs
            ],
            "blocking_reasons": blockers,
            "next_gate": next_gate,
        }
        manifest_path = staging / MANIFEST_JSON
        write_json(manifest_path, manifest)

        staging.rename(final_dir)

        print()
        print("=" * 124)
        print(
            f"B1_EXT_GH_08F_TARGETED_ENDPOINT_FALLBACK_MATERIALIZATION = "
            f"{verdict}"
        )
        print("SOURCE_GH08_V01 = PRESERVED_NOT_READY_HISTORY")
        print("CORRECTED_PACKAGE = V02_APPEND_ONLY")
        print(f"B1_RELATIONS = {EXPECTED_B1_ROWS}")
        print(f"EXTERNAL_DESTINATIONS = {EXPECTED_DESTINATIONS}")
        print(f"PHYSICAL_CROSSINGS = {EXPECTED_CROSSINGS}")
        print(f"ORIGINAL_PASS_CANDIDATES_REUSED = {preserved_original_pass}")
        print(f"FALLBACK_DESTINATIONS = {EXPECTED_FALLBACK_DESTINATIONS}")
        print(f"FALLBACK_CANDIDATES_REROUTED = {replaced}")
        print(f"FALLBACK_CANDIDATES_PASS = {fallback_counts.get('PASS', 0)}/{EXPECTED_FALLBACK_CANDIDATES}")
        print(f"FALLBACK_MAX_DESTINATION_SNAP_M = {fallback_max_dest:.3f}")
        print(f"IE_ROUTED = {ie_pass}/{EXPECTED_B1_ROWS}")
        print(f"EI_ROUTED = {ei_pass}/{EXPECTED_B1_ROWS}")
        print(f"IE_UNREACHABLE = {selection_diag['IE_unreachable']}")
        print(f"EI_UNREACHABLE = {selection_diag['EI_unreachable']}")
        print(f"IE_DAILY_FLOW = {ie_daily:.5f}")
        print(f"EI_DAILY_FLOW = {ei_daily:.5f}")
        print(f"EXPECTED_DAILY_FLOW_EACH = {EXPECTED_DAILY_FLOW:.5f}")
        print(f"IE_MIN_VALID_CROSSING_CANDIDATES = {selection_diag['IE_min_valid_crossing_candidates']}")
        print(f"EI_MIN_VALID_CROSSING_CANDIDATES = {selection_diag['EI_min_valid_crossing_candidates']}")
        print(f"CROSS_GATEWAY_NUMERIC_TIES_IE = {selection_diag['IE_cross_gateway_numeric_ties']}")
        print(f"CROSS_GATEWAY_NUMERIC_TIES_EI = {selection_diag['EI_cross_gateway_numeric_ties']}")
        print(f"PREVIOUS_IE_PASS_REGRESSION = {prior_ie_regression}/{EXPECTED_B1_ROWS - 162} UNCHANGED")
        print(f"PREVIOUS_EI_PASS_REGRESSION = {prior_ei_regression}/{EXPECTED_B1_ROWS - 162} UNCHANGED")
        print(
            f"ITALY_GRAPH_BYTE_IDENTICAL_AFTER_RUN = "
            f"{'YES' if graph_unchanged else 'NO'}"
        )
        print("GH08_V01_OUTPUTS_MODIFIED = NO")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print("PBF_IMPORT = NOT_STARTED")
        print("B5_DIJKSTRA = NOT_STARTED")
        print("GRAVITY_REOPENED = NO")
        print("SELECTED_ROUTE_EXTERNAL_SUBGRAPH_DIAGNOSTICS = NOT_STARTED")
        print("IGNORED_RESTRICTION_INTERSECTION_AUDIT = NOT_STARTED")
        print(f"NEXT_GATE = {next_gate}")
        print(f"{EXTERNAL_V02} SHA256 = {sha256(final_dir / EXTERNAL_V02)}")
        print(f"{IE_V02} SHA256 = {sha256(final_dir / IE_V02)}")
        print(f"{EI_V02} SHA256 = {sha256(final_dir / EI_V02)}")
        print(f"{GATEWAY_FLOW_V02} SHA256 = {sha256(final_dir / GATEWAY_FLOW_V02)}")
        print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
        print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
        print("=== RUN COMPLETATA ===")

        return 0 if verdict == "PASS" else 2

    except Exception as exc:
        stop_status = stop_server(proc)
        proc = None
        try:
            server_log_handle.close()
        except Exception:
            pass

        print()
        print("=" * 124)
        print("B1_EXT_GH_08F_TARGETED_ENDPOINT_FALLBACK_MATERIALIZATION = FAIL")
        print(f"ERROR = {exc}")
        print(f"SERVER_SHUTDOWN = {stop_status}")
        print(f"DIAGNOSTIC_STAGING = {staging if staging.exists() else 'NOT_CREATED'}")
        print("GH08_V01_OUTPUTS_MODIFIED = NO_INTENT")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO_INTENT")
        print("=== RUN COMPLETATA ===")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
