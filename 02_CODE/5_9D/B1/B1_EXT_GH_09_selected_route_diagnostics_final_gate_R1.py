#!/usr/bin/env python3
"""
B1-EXT-GH 09 — SELECTED ROUTE DIAGNOSTICS + FINAL GATE

Purpose
-------
Close the B1 external-routing branch after GH08F PASS.

This script:
1. reads the corrected GH08F v02 package;
2. deduplicates ONLY the external route legs actually selected by the 2,895 IE
   and 2,895 EI B1 relations;
3. re-queries those selected legs against the same frozen GraphHopper Italy graph
   with path details (edge_id + osm_way_id) and full route geometry;
4. preserves the two endpoint-search semantics already materialized:
      - DEFAULT LocationIndex for ordinary destinations;
      - index.max_region_search=64 only for the 19 proven fallback destinations;
5. verifies every diagnostic re-route against the already-materialized external
   cache time/distance/snap values;
6. materializes the used external route-induced subgraph diagnostics;
7. discovers the frozen GraphHopper heavy-import log by SHA256, parses ONLY the
   already-reported ignored restriction warnings, and intersects their member
   OSM way IDs with actually used B1 OSM ways;
8. re-hashes the frozen project artifacts and the Italy graph;
9. writes B1_EXT_FINAL_GATE_REPORT.txt.

Important
---------
NO PBF import.
NO B5 routing.
NO broad national restriction audit.
NO modification of GH08F or frozen FVG artifacts.
NO new gateway selection.
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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Canonical architecture / source relation
# ======================================================================================

SOURCE_RELATION = "NEAR_CONTEMPORANEOUS_NOT_IDENTICAL"
INTERNAL_ROUTER = "B5_FROZEN"
EXTERNAL_ROUTER = "GRAPHHOPPER_11"
COMPOSITION = "PHYSICAL_CROSSING_MIN_COMBINED_TIME"

EXPECTED_B1_ROWS = 2_895
EXPECTED_DAILY_FLOW = 6_195.97590
EXPECTED_EXTERNAL_DESTINATIONS = 368
EXPECTED_PHYSICAL_CROSSINGS = 49
EXPECTED_MODELLING_GATEWAYS = 12
EXPECTED_FALLBACK_DESTINATIONS = 19

VENETO_GATEWAYS = {
    "VE01", "VE02", "VE03", "VE04", "VE05", "VE06",
    "A1V01", "A1V02", "A1V03", "A1V04", "A1V05", "A1V06",
}

# ======================================================================================
# Frozen tool / GraphHopper identity
# ======================================================================================

GH08_TOOL_REL = r"tools\B1_EXT_GH_08_hybrid_routing_materialization.py"
GH08_TOOL_SHA256 = "e60b6655644e50d554c1399a0c7a61cae590ed7add4d12b4970d816c8ee1fe38"

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"
FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"

PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"

PROFILE_MODEL_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\b1_ext_car_b5_compat_v01.json"
)
PROFILE_MODEL_SHA256 = "29ad0a3a425b43b039c52d1013d0706894d842120995ed607f57406a1f01ea79"

ITALY_PBF_REL = (
    r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1"
    r"\italy-260801.osm.pbf"
)
ITALY_PBF_SHA256 = "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538"
EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"
EXPECTED_IMPORT_LOG_SHA256 = "baddbb9ebcf47b40ea84eeaac27eb156bbd277a609945b891ed5e186d6a9e852"

HEAVY_RUNS_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\heavy_import_runs"
)

# ======================================================================================
# GH06 evidence
# ======================================================================================

GH06_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\graph_load_targeted_routing_qa_v01"
)
GH06_SUMMARY = "B1_EXT_GH_graph_load_targeted_routing_qa_summary_v01.json"
GH06_SUMMARY_SHA256 = "d13d2266635fe4de6da094a3de533981b9a71e66654788f94558d20440c2725f"
GH06_MANIFEST = "B1_EXT_GH_graph_load_targeted_routing_qa_manifest_v01.json"
GH06_MANIFEST_SHA256 = "a7590ed3b5dd61670ee509843b6707d14d66fc609ded37056a81aa8214f0353d"

# ======================================================================================
# GH08D fallback set
# ======================================================================================

GH08D_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_blocking_diagnostics_v01"
)
GH08D_DEST = "B1_EXT_GH_08D_unreachable_destinations_v01.csv"
GH08D_DEST_SHA256 = "9f7254562d6e92888e23183279badefc5439dfbb4fe6066efa0d9652aaea44a0"

# ======================================================================================
# GH08F corrected package
# ======================================================================================

GH08F_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v02_endpoint_fallback"
)
GH08F_EXTERNAL = "B1_EXT_GH_08F_external_crossing_route_cache_v02.csv"
GH08F_EXTERNAL_SHA256 = "a43569eac857c1f879d493ec96756a904042576ee13d74582eb944b7dac8d386"
GH08F_IE = "B1_EXT_GH_08F_IE_routing_v02.csv"
GH08F_IE_SHA256 = "c9dc62f7694584eeb418939f7a3ba844415293c1b70f3fe5e9169a593f5adc3e"
GH08F_EI = "B1_EXT_GH_08F_EI_routing_v02.csv"
GH08F_EI_SHA256 = "4e8f9e3431cb7f12f1ccd9c734e05c5610aa02e11d291722d76b912300e8c34c"
GH08F_GATEWAY_FLOW = "B1_EXT_GH_08F_gateway_flow_attribution_v02.csv"
GH08F_GATEWAY_FLOW_SHA256 = "e506f044b2700cacd1c32c94d27661fe3d5117a5dcaaf2a1a8fbaeaf0be77fa0"
GH08F_SUMMARY = "B1_EXT_GH_08F_targeted_endpoint_fallback_summary_v02.json"
GH08F_SUMMARY_SHA256 = "08341355f95fd1bcc17a85db74a276888376b1f729db2e07ae014d4fe9aebac3"
GH08F_MANIFEST = "B1_EXT_GH_08F_targeted_endpoint_fallback_manifest_v02.json"
GH08F_MANIFEST_SHA256 = "1e6b53f93db0219f6ee5b6a961c96a5bf6eb1332ede8a4037dded6f7e4aa1433"

# ======================================================================================
# Frozen FVG artifacts to re-hash
# ======================================================================================

FROZEN_FVG = {
    "nord_est_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf",
        "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813",
    ),
    "g_osm_operativo": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\G_OSM_operativo_v01.gpkg",
        "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3",
    ),
    "b5_time": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_time_v01.npz",
        "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72",
    ),
    "b5_length": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_length_v01.npz",
        "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2",
    ),
    "b5_edgeid": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_edgeid_v01.npz",
        "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185",
    ),
    "b5_index": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_index_v01.sqlite",
        "c8af04daa3a588001faa5fdf24d942361845d4081693a19ccfccf94605771bff",
    ),
    "b5_base_nodes": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_base_nodes_v01.npy",
        "de02faa32628af6099118e08bd3e13847fbb0330d1aa7d824df47220b2f947d7",
    ),
    "b5_state_node": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_node_id_v01.npy",
        "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935",
    ),
    "gamma": (
        r"Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv",
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",
    ),
    "od_paths": (
        r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_access_paths_v01.csv",
        "3c0a8786a05719db4ca2a4258250bde8937b8dd017d93fea0c8f4a8a101c8dd3",
    ),
    "od_offsets": (
        r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_path_offsets_v01.npy",
        "478efd3a3f6eba6964db9f0a785dfd9405d5ae61af30e4f84538b0699a7a3a08",
    ),
    "od_slots": (
        r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_transition_slots_v01.npy",
        "2a6b06d21b6d3eea7132a0154bbb4c74d305a4ea582d780e07b5abeed24d2c1d",
    ),
}

# ======================================================================================
# Server / routing detail QA
# ======================================================================================

APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 120
HTTP_WORKERS_DEFAULT = 6
FALLBACK_MAX_REGION_SEARCH = 64

TIME_TOL_S = 1e-9
DIST_TOL_M = 1e-6
SNAP_TOL_M = 1e-3
EDGE_DISTANCE_SUM_TOL_M = 0.05
GEOMETRY_ROUTE_REL_TOL = 0.02
GEOMETRY_ROUTE_ABS_TOL_M = 25.0
NODE_COORD_DECIMALS = 7

# ======================================================================================
# Output
# ======================================================================================

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\selected_route_diagnostics_final_gate_v01"
)

SELECTED_KEYS_CSV = "B1_EXT_GH_09_selected_external_route_keys_v01.csv"
ROUTE_DETAIL_CSV = "B1_EXT_GH_09_selected_route_detail_audit_v01.csv"
USED_EDGES_CSV = "B1_EXT_GH_09_used_external_edges_v01.csv"
USED_NODES_CSV = "B1_EXT_GH_09_used_external_route_nodes_v01.csv"
IGNORED_RESTRICTIONS_CSV = "B1_EXT_GH_09_ignored_restriction_intersection_v01.csv"
GATEWAY_USAGE_CSV = "B1_EXT_GH_09_gateway_usage_final_v01.csv"
DEFAULT_CONFIG = "graphhopper_b1_ext_server_gh09_default_v01.yml"
DEFAULT_LOG = "graphhopper_b1_ext_server_gh09_default_v01.log"
FALLBACK_CONFIG = "graphhopper_b1_ext_server_gh09_fallback64_v01.yml"
FALLBACK_LOG = "graphhopper_b1_ext_server_gh09_fallback64_v01.log"
SUMMARY_JSON = "B1_EXT_GH_09_selected_route_diagnostics_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_09_selected_route_diagnostics_manifest_v01.json"
FINAL_REPORT_TXT = "B1_EXT_FINAL_GATE_REPORT.txt"

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
    print(f"{label:<34} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
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
        raise RuntimeError(f"CSV missing header: {path}")
    return rows, cols


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        if not rows:
            raise RuntimeError(f"Cannot infer empty CSV schema: {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


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
        raise RuntimeError(f"{label}: {actual} != {expected} (tol={tol})")


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("gh08_authoritative", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2.0) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def polyline_length_m(coords: list[list[float]]) -> float:
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(coords[:-1], coords[1:]):
        total += haversine_m(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
    return total


def route_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["destination_key"]),
        str(row["selected_geo_id"] if "selected_geo_id" in row else row["geo_id"]),
        str(row["direction"]),
    )


def helper_self_tests() -> None:
    if route_key({
        "destination_key": "d",
        "selected_geo_id": "g",
        "direction": "IE",
    }) != ("d", "g", "IE"):
        raise AssertionError("route_key self-test")
    if abs(polyline_length_m([[13.0, 46.0], [13.0, 46.0]])) > 1e-9:
        raise AssertionError("polyline self-test")
    text = "members: [from way 123, via node 456, to way 789]"
    ways = {int(x) for x in re.findall(r"\bway\s+(\d+)\b", text)}
    nodes = {int(x) for x in re.findall(r"\bnode\s+(\d+)\b", text)}
    if ways != {123, 789} or nodes != {456}:
        raise AssertionError("restriction member parser self-test")
    sig = normalized_edge_signature({
        "edge_id": 10,
        "osm_way_id": 20,
        "start_lon": 13.1,
        "start_lat": 46.1,
        "end_lon": 13.2,
        "end_lat": 46.2,
    })
    sig_rev = normalized_edge_signature({
        "edge_id": 10,
        "osm_way_id": 20,
        "start_lon": 13.2,
        "start_lat": 46.2,
        "end_lon": 13.1,
        "end_lat": 46.1,
    })
    if sig != sig_rev:
        raise AssertionError("normalized edge signature direction self-test")


# ======================================================================================
# GraphHopper YAML / server
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
            raise RuntimeError(f"Active '{key}' lies outside graphhopper section")
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        if not indent:
            raise RuntimeError(f"Unsafe root-level '{key}'")
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
        raise RuntimeError("Could not infer GraphHopper scalar indentation")
    indents = {indent for _, indent in refs}
    if len(indents) != 1:
        raise RuntimeError(f"Inconsistent GraphHopper scalar indentation: {indents}")
    indent = next(iter(indents))

    graph_location_hits = [
        i for i in range(gh_i + 1, gh_end)
        if lines[i].lstrip().startswith("graph.location:")
    ]
    insert_at = (
        graph_location_hits[0] + 1
        if len(graph_location_hits) == 1
        else max(i for i, _ in refs) + 1
    )
    lines.insert(insert_at, f"{indent}{key}: {int(value)}")
    return "\n".join(lines) + "\n", "INSERTED_IN_GRAPHHOPPER_SECTION"


def make_server_config(
    gh08,
    profile_config: Path,
    graph_dir: Path,
    staging: Path,
    fallback64: bool,
) -> tuple[str, str]:
    text = gh08.make_server_config(profile_config, graph_dir, staging)
    if not fallback64:
        return text, "DEFAULT_LOCATION_INDEX"
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
    raise TimeoutError(f"GraphHopper server did not open port {APP_PORT}")


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


def query_info() -> dict[str, Any]:
    url = f"http://127.0.0.1:{APP_PORT}/info"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-GH09/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("GraphHopper /info did not return an object")
    return data


# ======================================================================================
# Selected route detail query
# ======================================================================================

def detail_value_for_edge_range(
    details: list[list[Any]],
    edge_from: int,
    edge_to: int,
) -> Any:
    # Path details use point-reference intervals. We require the entire edge_id
    # interval to be contained in one osm_way_id interval.
    matches = [
        item[2]
        for item in details
        if len(item) == 3
        and int(item[0]) <= edge_from
        and edge_to <= int(item[1])
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Could not uniquely map edge range [{edge_from},{edge_to}] "
            f"to one osm_way_id detail; matches={matches[:10]}"
        )
    return matches[0]


def exact_detail_value_for_edge_range(
    details: list[list[Any]],
    edge_from: int,
    edge_to: int,
) -> Any | None:
    """
    Return a path-detail value only when its [fromRef,toRef] interval exactly
    equals the edge_id interval.

    GraphHopper path geometries can contain duplicate points at query/virtual
    edge boundaries. Therefore geometry length alone is not a safe per-edge
    length source. We prefer the explicit ``distance`` path detail.
    """
    matches = [
        item[2]
        for item in details
        if len(item) == 3
        and int(item[0]) == edge_from
        and int(item[1]) == edge_to
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple exact path-detail matches for edge range "
            f"[{edge_from},{edge_to}]: {matches[:10]}"
        )
    return matches[0] if matches else None


def normalized_edge_signature(edge: dict[str, Any]) -> tuple[Any, ...]:
    """
    Stable route-induced edge identity.

    GraphHopper QueryGraph can introduce request-local virtual edges. A naked
    edge_id is therefore not sufficient for a cross-request union. Combining
    edge_id + osm_way_id + normalized endpoint coordinates avoids falsely
    merging distinct virtual edge instances that reuse the same request-local
    numeric id.
    """
    p1 = (
        round(float(edge["start_lon"]), NODE_COORD_DECIMALS),
        round(float(edge["start_lat"]), NODE_COORD_DECIMALS),
    )
    p2 = (
        round(float(edge["end_lon"]), NODE_COORD_DECIMALS),
        round(float(edge["end_lat"]), NODE_COORD_DECIMALS),
    )
    lo, hi = sorted((p1, p2))
    return (
        int(edge["edge_id"]),
        int(edge["osm_way_id"]),
        lo[0], lo[1], hi[0], hi[1],
    )


def route_detail_request(cache_row: dict[str, str]) -> dict[str, Any]:
    direction = str(cache_row["direction"])
    crossing_lat = parse_float(cache_row["crossing_lat"])
    crossing_lon = parse_float(cache_row["crossing_lon"])
    dest_lat = parse_float(cache_row["dest_lat"])
    dest_lon = parse_float(cache_row["dest_lon"])

    if direction == "IE":
        start_lat, start_lon = crossing_lat, crossing_lon
        end_lat, end_lon = dest_lat, dest_lon
    elif direction == "EI":
        start_lat, start_lon = dest_lat, dest_lon
        end_lat, end_lon = crossing_lat, crossing_lon
    else:
        raise ValueError(direction)

    params = [
        ("point", f"{start_lat:.8f},{start_lon:.8f}"),
        ("point", f"{end_lat:.8f},{end_lon:.8f}"),
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "true"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
        ("details", "edge_id"),
        ("details", "osm_way_id"),
        ("details", "distance"),
    ]
    url = f"http://127.0.0.1:{APP_PORT}/route?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-GH09/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=ROUTE_TIMEOUT_S) as response:
            body = response.read().decode("utf-8")
            http_status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GraphHopper detail HTTP {exc.code}: {body[:2000]}"
        ) from exc

    if http_status != 200:
        raise RuntimeError(f"Unexpected detail HTTP status {http_status}")

    data = json.loads(body)
    paths = data.get("paths", [])
    if len(paths) != 1:
        raise RuntimeError(f"Expected exactly one path, got {len(paths)}")
    path = paths[0]

    points_obj = path.get("points")
    if not isinstance(points_obj, dict):
        raise RuntimeError("Path geometry missing GeoJSON points object")
    coords = points_obj.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise RuntimeError("Path geometry has insufficient coordinates")

    snapped = path.get("snapped_waypoints", {})
    snapped_coords = snapped.get("coordinates", [])
    if len(snapped_coords) != 2:
        raise RuntimeError(f"Expected two snapped waypoints, got {snapped_coords}")

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

    route_distance_m = parse_float(path["distance"])
    route_time_s = parse_int(path["time"]) / 1000.0

    snap_start_lon, snap_start_lat = map(float, snapped_coords[0][:2])
    snap_end_lon, snap_end_lat = map(float, snapped_coords[1][:2])
    snap_start_m = haversine_m(
        start_lon, start_lat, snap_start_lon, snap_start_lat
    )
    snap_end_m = haversine_m(
        end_lon, end_lat, snap_end_lon, snap_end_lat
    )

    if direction == "IE":
        crossing_snap_m = snap_start_m
        destination_snap_m = snap_end_m
    else:
        destination_snap_m = snap_start_m
        crossing_snap_m = snap_end_m

    # Regression against the already-materialized selected candidate.
    assert_close(
        route_time_s,
        parse_float(cache_row["external_time_s"]),
        f"time regression {route_key(cache_row)}",
        TIME_TOL_S,
    )
    assert_close(
        route_distance_m,
        parse_float(cache_row["external_distance_m"]),
        f"distance regression {route_key(cache_row)}",
        DIST_TOL_M,
    )
    assert_close(
        crossing_snap_m,
        parse_float(cache_row["crossing_snap_m"]),
        f"crossing snap regression {route_key(cache_row)}",
        SNAP_TOL_M,
    )
    assert_close(
        destination_snap_m,
        parse_float(cache_row["destination_snap_m"]),
        f"destination snap regression {route_key(cache_row)}",
        SNAP_TOL_M,
    )

    geometry_length_m = polyline_length_m(coords)
    if abs(geometry_length_m - route_distance_m) > max(
        GEOMETRY_ROUTE_ABS_TOL_M,
        GEOMETRY_ROUTE_REL_TOL * route_distance_m,
    ):
        raise RuntimeError(
            f"Route geometry length mismatch {route_key(cache_row)}: "
            f"geometry={geometry_length_m} route={route_distance_m}"
        )

    edges: list[dict[str, Any]] = []
    for item in edge_details:
        if not isinstance(item, list) or len(item) != 3:
            raise RuntimeError(f"Invalid edge_id detail: {item}")
        from_ref, to_ref, edge_value = item
        a = int(from_ref)
        b = int(to_ref)
        if not (0 <= a < b < len(coords)):
            raise RuntimeError(
                f"Invalid edge detail point refs [{a},{b}] len={len(coords)}"
            )
        edge_id = parse_int(edge_value)
        osm_way_value = detail_value_for_edge_range(
            way_details,
            a,
            b,
        )
        if osm_way_value is None:
            raise RuntimeError(
                f"Null osm_way_id for used edge {edge_id}"
            )
        osm_way_id = parse_int(osm_way_value)
        seg_coords = coords[a:b + 1]
        geometry_seg_len = polyline_length_m(seg_coords)

        distance_value = exact_detail_value_for_edge_range(
            distance_details,
            a,
            b,
        )
        if distance_value is not None:
            edge_distance_m = parse_float(distance_value)
            edge_distance_source = "DISTANCE_PATH_DETAIL"
        else:
            # Defensive fallback only. This is acceptable for a diagnostic
            # reconstruction because the route-level geometry and total distance
            # are independently regression-checked below.
            edge_distance_m = geometry_seg_len
            edge_distance_source = "GEOMETRY_FALLBACK"

        if edge_distance_m < 0:
            raise RuntimeError(
                f"Negative edge distance for edge {edge_id}: "
                f"{edge_distance_m}"
            )

        edges.append({
            "edge_id": edge_id,
            "osm_way_id": osm_way_id,
            "from_ref": a,
            "to_ref": b,
            "edge_distance_m": edge_distance_m,
            "edge_distance_source": edge_distance_source,
            "geometry_segment_length_m": geometry_seg_len,
            "zero_geometry_segment": geometry_seg_len <= 0,
            "start_lon": float(coords[a][0]),
            "start_lat": float(coords[a][1]),
            "end_lon": float(coords[b][0]),
            "end_lat": float(coords[b][1]),
        })

    if not edges:
        raise RuntimeError("No edge details after parsing")

    edge_distance_sum_m = sum(
        float(e["edge_distance_m"]) for e in edges
    )
    if abs(edge_distance_sum_m - route_distance_m) > EDGE_DISTANCE_SUM_TOL_M:
        raise RuntimeError(
            f"Edge distance-detail reconstruction mismatch "
            f"{route_key(cache_row)}: "
            f"edge_sum={edge_distance_sum_m} route={route_distance_m}"
        )

    return {
        "destination_key": cache_row["destination_key"],
        "dest_COMUNE": cache_row["dest_COMUNE"],
        "gateway_id": cache_row["gateway_id"],
        "geo_id": cache_row["geo_id"],
        "direction": direction,
        "external_time_s": route_time_s,
        "external_distance_m": route_distance_m,
        "crossing_snap_m": crossing_snap_m,
        "destination_snap_m": destination_snap_m,
        "geometry_length_m": geometry_length_m,
        "point_count": len(coords),
        "edge_segment_count": len(edges),
        "unique_edge_ids": len({e["edge_id"] for e in edges}),
        "unique_osm_way_ids": len({e["osm_way_id"] for e in edges}),
        "edge_distance_sum_m": edge_distance_sum_m,
        "zero_geometry_edge_segments": sum(
            1 for e in edges if e["zero_geometry_segment"]
        ),
        "geometry_fallback_edge_segments": sum(
            1 for e in edges
            if e["edge_distance_source"] == "GEOMETRY_FALLBACK"
        ),
        "edges": edges,
    }


# ======================================================================================
# Frozen import warning parser
# ======================================================================================

def find_import_log_by_hash(root: Path) -> Path:
    heavy_root = root / Path(HEAVY_RUNS_REL)
    if not heavy_root.is_dir():
        raise FileNotFoundError(heavy_root)

    candidates = []
    for p in heavy_root.rglob("*"):
        if not p.is_file():
            continue
        # Do not hash graph data here. Heavy-run evidence/log files are expected
        # to be ordinary text/JSON/YAML artifacts.
        if p.suffix.lower() not in {
            ".log", ".txt", ".out", ".err", ".json", ".yml", ".yaml"
        }:
            continue
        candidates.append(p)

    matches = []
    for p in sorted(candidates):
        if sha256(p) == EXPECTED_IMPORT_LOG_SHA256:
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one import log with SHA256 "
            f"{EXPECTED_IMPORT_LOG_SHA256}; found {len(matches)}"
        )
    return matches[0]


def parse_ignored_restrictions(log_path: Path) -> list[dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            if "Restriction relation " not in line or "Relation ignored." not in line:
                continue
            m = re.search(
                r"Restriction relation\s+(\d+)\s+(.*?)"
                r"tags:\s*(\{.*?\}),\s*members:\s*\[(.*?)\]\.\s*Relation ignored\.",
                line,
            )
            if not m:
                raise RuntimeError(
                    f"Could not parse ignored restriction warning at "
                    f"{log_path}:{line_no}: {line[:1000]}"
                )
            relation_id = int(m.group(1))
            reason = m.group(2).strip()
            tags = m.group(3).strip()
            members = m.group(4).strip()
            ways = sorted({
                int(x)
                for x in re.findall(r"\bway\s+(\d+)\b", members)
            })
            nodes = sorted({
                int(x)
                for x in re.findall(r"\bnode\s+(\d+)\b", members)
            })
            row = {
                "relation_id": relation_id,
                "reason": reason,
                "tags": tags,
                "members": members,
                "member_way_ids": ways,
                "member_node_ids": nodes,
                "line_no": line_no,
            }
            previous = out.get(relation_id)
            if previous is not None and previous != row:
                raise RuntimeError(
                    f"Conflicting duplicate ignored restriction {relation_id}"
                )
            out[relation_id] = row
    if not out:
        raise RuntimeError(
            "No ignored restriction warnings parsed from frozen import log"
        )
    return [out[k] for k in sorted(out)]


# ======================================================================================
# Report helper
# ======================================================================================

def format_gateway_usage(rows: list[dict[str, Any]]) -> str:
    parts = []
    for r in sorted(rows, key=lambda x: (x["direction"], x["gateway_id"])):
        parts.append(
            f"{r['direction']}:{r['gateway_id']}="
            f"{float(r['flow_daily_sum']):.5f}"
        )
    return "; ".join(parts)


def build_final_report(summary: dict[str, Any]) -> str:
    verdict = summary["verdict"]
    restriction_count = summary["ignored_restrictions"]["candidate_intersections"]
    next_action = (
        "HARD STOP / RETURN TO CHAT MADRE"
        if verdict == "PASS"
        else "TARGETED DIAGNOSIS OF USED-ROUTE RESTRICTION CANDIDATES"
    )
    return f"""B1_EXT_FINAL_GATE_REPORT

======================================================================
VERDETTO
======================================================================

G_EXT_ITALY_B1_v01 = {verdict}

SOURCE_RELATION = {SOURCE_RELATION}
INTERNAL_ROUTER = {INTERNAL_ROUTER}
EXTERNAL_ROUTER = {EXTERNAL_ROUTER}
COMPOSITION = {COMPOSITION}

B1_RELATIONS = {EXPECTED_B1_ROWS}

IE_ROUTED = {summary['routing']['IE_routed']}/{EXPECTED_B1_ROWS}
EI_ROUTED = {summary['routing']['EI_routed']}/{EXPECTED_B1_ROWS}

IE_UNREACHABLE = {summary['routing']['IE_unreachable']}
EI_UNREACHABLE = {summary['routing']['EI_unreachable']}

IE_DAILY_FLOW = {summary['routing']['IE_daily_flow']:.5f}
EI_DAILY_FLOW = {summary['routing']['EI_daily_flow']:.5f}

AMBIGUOUS_GATEWAY_MAPPING = {summary['routing']['ambiguous_gateway_mapping']}

VENETO_EXPECTED_GATEWAY_USAGE = {summary['gateway_usage']['expected_veneto_only']}
VENETO_GATEWAYS_USED = {summary['gateway_usage']['used_gateway_count']}/{EXPECTED_MODELLING_GATEWAYS}
UNEXPECTED_AT_SI_GATEWAY_USAGE = {summary['gateway_usage']['unexpected_gateway_count']}

USED_EXTERNAL_EDGES = {summary['used_subgraph']['used_edge_signatures']}
USED_EXTERNAL_RAW_EDGE_IDS = {summary['used_subgraph']['used_raw_edge_ids']}
USED_EXTERNAL_NODES = {summary['used_subgraph']['used_route_induced_nodes']}
USED_EXTERNAL_LENGTH_KM = {summary['used_subgraph']['used_edge_union_length_km']:.6f}
USED_EXTERNAL_OSM_WAYS = {summary['used_subgraph']['used_osm_way_ids']}
UNIQUE_SELECTED_EXTERNAL_ROUTES = {summary['used_subgraph']['unique_selected_external_routes']}

USED_EXTERNAL_NODES_SEMANTICS =
UNIQUE ROUTE-INDUCED EDGE-BOUNDARY COORDINATES FROM GRAPHHOPPER PATH DETAILS

USED_EXTERNAL_EDGE_SEMANTICS =
UNIQUE (edge_id, osm_way_id, NORMALIZED ROUTE-ENDPOINT COORDINATES) SIGNATURES;
THIS AVOIDS FALSE CROSS-REQUEST MERGES OF QUERYGRAPH VIRTUAL EDGE IDS

USED_EXTERNAL_LENGTH_SEMANTICS =
SUM OF MAX OBSERVED ``distance`` PATH-DETAIL LENGTH PER UNIQUE EDGE SIGNATURE

IGNORED_RESTRICTIONS_TOTAL_IN_IMPORT_LOG = {summary['ignored_restrictions']['total_ignored_relations']}
IGNORED_RESTRICTIONS_INTERSECTING_USED_ROUTES = {restriction_count}
IGNORED_RESTRICTION_INTERSECTION_RULE =
CONSERVATIVE MEMBER-WAY INTERSECTION AGAINST ACTUALLY USED OSM WAY IDS

TARGETED_QA = {summary['qa']['targeted_qa']}
GRAPH_LOAD_QA = {summary['qa']['graph_load_qa']}
SELECTED_ROUTE_DETAIL_QA = {summary['qa']['selected_route_detail_qa']}

FROZEN_FVG_HASHES = {summary['integrity']['frozen_fvg_hashes']}
ITALY_GRAPH_BYTE_IDENTICAL_AFTER_QA = {summary['integrity']['italy_graph_byte_identical']}
GH08F_V02_OUTPUTS_MODIFIED = NO

ITALY_PBF_SHA256 =
{ITALY_PBF_SHA256}

GRAPH_MANIFEST_SHA256 =
{EXPECTED_GRAPH_MANIFEST_SHA256}

ENDPOINT_FALLBACK =
POINT_NOTFOUND-ONLY / index.max_region_search=64 / 19 DESTINATIONS

ENDPOINT_FALLBACK_MAX_SNAP_M =
{summary['routing']['max_destination_snap_m']:.3f}

======================================================================
GATE
======================================================================

NEXT_ACTION = {next_action}
"""


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
        print("B1_EXT_GH_09_HELPER_SELF_TESTS = PASS")
        return 0

    if not (1 <= args.http_workers <= 16):
        raise ValueError("--http-workers must be in [1,16]")

    root = Path(args.root)
    gh08_tool = root / Path(GH08_TOOL_REL)
    gh08f_dir = root / Path(GH08F_DIR_REL)
    gh08d_dir = root / Path(GH08D_DIR_REL)
    gh06_dir = root / Path(GH06_DIR_REL)
    graph_dir = root / Path(FINAL_GRAPH_REL)
    gh_jar = root / Path(GH_JAR_REL)
    runtime_root = root / Path(RUNTIME_REL)
    profile_config = root / Path(PROFILE_CONFIG_REL)
    profile_model = root / Path(PROFILE_MODEL_REL)
    italy_pbf = root / Path(ITALY_PBF_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name
        + "_STAGING_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 09 — SELECTED ROUTE DIAGNOSTICS + FINAL GATE")
    print("=" * 124)
    print(
        "ONLY SELECTED EXTERNAL LEGS / PATH DETAILS / TARGETED IGNORED-RESTRICTION INTERSECTION"
    )
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Strict lineage identity
    # ------------------------------------------------------------------
    print("A. STRICT LINEAGE / INPUT IDENTITY")
    strict_hash("GH08 tool", gh08_tool, GH08_TOOL_SHA256)
    strict_hash(
        "GH08F external cache",
        gh08f_dir / GH08F_EXTERNAL,
        GH08F_EXTERNAL_SHA256,
    )
    strict_hash("GH08F IE", gh08f_dir / GH08F_IE, GH08F_IE_SHA256)
    strict_hash("GH08F EI", gh08f_dir / GH08F_EI, GH08F_EI_SHA256)
    strict_hash(
        "GH08F gateway flow",
        gh08f_dir / GH08F_GATEWAY_FLOW,
        GH08F_GATEWAY_FLOW_SHA256,
    )
    strict_hash(
        "GH08F summary",
        gh08f_dir / GH08F_SUMMARY,
        GH08F_SUMMARY_SHA256,
    )
    strict_hash(
        "GH08F manifest",
        gh08f_dir / GH08F_MANIFEST,
        GH08F_MANIFEST_SHA256,
    )
    strict_hash(
        "GH08D fallback destinations",
        gh08d_dir / GH08D_DEST,
        GH08D_DEST_SHA256,
    )
    strict_hash(
        "GH06 summary",
        gh06_dir / GH06_SUMMARY,
        GH06_SUMMARY_SHA256,
    )
    strict_hash(
        "GH06 manifest",
        gh06_dir / GH06_MANIFEST,
        GH06_MANIFEST_SHA256,
    )
    strict_hash("GH JAR", gh_jar, GH_JAR_SHA256)
    strict_hash("profile config", profile_config, PROFILE_CONFIG_SHA256)
    strict_hash("profile model", profile_model, PROFILE_MODEL_SHA256)
    strict_hash("Italy PBF", italy_pbf, ITALY_PBF_SHA256)

    gh08 = load_module(gh08_tool)
    gh08.helper_self_tests()
    print("GH08 helper self-tests          PASS")
    print("GH09 helper self-tests          PASS")

    gh08f_summary = read_json(gh08f_dir / GH08F_SUMMARY)
    if gh08f_summary.get("verdict") != "PASS":
        raise RuntimeError("GH08F v02 is not PASS")
    if int(gh08f_summary["selection"]["IE_routed"]) != EXPECTED_B1_ROWS:
        raise RuntimeError("GH08F IE routing contract mismatch")
    if int(gh08f_summary["selection"]["EI_routed"]) != EXPECTED_B1_ROWS:
        raise RuntimeError("GH08F EI routing contract mismatch")
    if int(gh08f_summary["selection"]["IE_cross_gateway_numeric_ties"]) != 0:
        raise RuntimeError("GH08F IE cross-gateway ties nonzero")
    if int(gh08f_summary["selection"]["EI_cross_gateway_numeric_ties"]) != 0:
        raise RuntimeError("GH08F EI cross-gateway ties nonzero")

    gh06_summary = read_json(gh06_dir / GH06_SUMMARY)
    gh06_manifest = read_json(gh06_dir / GH06_MANIFEST)

    # ------------------------------------------------------------------
    # B. Frozen FVG + graph identity before diagnostics
    # ------------------------------------------------------------------
    print()
    print("B. FROZEN FVG / ITALY GRAPH PRE-RUN IDENTITY")

    frozen_start: dict[str, str] = {}
    for label, (rel, expected) in FROZEN_FVG.items():
        p = root / Path(rel)
        actual = strict_hash(label, p, expected)
        frozen_start[label] = actual

    graph_manifest_path, graph_manifest = gh08.find_graph_manifest(root)
    if sha256(graph_manifest_path) != EXPECTED_GRAPH_MANIFEST_SHA256:
        raise RuntimeError("Graph manifest SHA mismatch")
    graph_before = gh08.graph_inventory(graph_dir)
    if gh08.normalized_inventory(graph_before) != gh08.normalized_inventory(
        graph_manifest.get("files", [])
    ):
        raise RuntimeError("Italy graph differs from frozen graph manifest")
    print(f"graph manifest                 PASS  {sha256(graph_manifest_path)}")
    print(f"Italy graph files              = {len(graph_before)}")

    # ------------------------------------------------------------------
    # C. Read corrected selected routes
    # ------------------------------------------------------------------
    print()
    print("C. SELECTED EXTERNAL ROUTE KEY MATERIALIZATION")

    external_rows, external_cols = read_csv(gh08f_dir / GH08F_EXTERNAL)
    ie_rows, ie_cols = read_csv(gh08f_dir / GH08F_IE)
    ei_rows, ei_cols = read_csv(gh08f_dir / GH08F_EI)
    fallback_rows, _ = read_csv(gh08d_dir / GH08D_DEST)

    fallback_dest_keys = {
        str(r["destination_key"]) for r in fallback_rows
    }
    if len(fallback_dest_keys) != EXPECTED_FALLBACK_DESTINATIONS:
        raise RuntimeError("Fallback destination count drift")

    if len(ie_rows) != EXPECTED_B1_ROWS or len(ei_rows) != EXPECTED_B1_ROWS:
        raise RuntimeError("Corrected IE/EI row count mismatch")
    if any(r["route_status"] != "PASS" for r in ie_rows + ei_rows):
        raise RuntimeError("Corrected IE/EI contains non-PASS route")
    if len({r["destination_key"] for r in ie_rows}) != EXPECTED_EXTERNAL_DESTINATIONS:
        raise RuntimeError("External destination cardinality mismatch")

    external_lookup = {
        (
            str(r["destination_key"]),
            str(r["geo_id"]),
            str(r["direction"]),
        ): r
        for r in external_rows
    }
    if len(external_lookup) != len(external_rows):
        raise RuntimeError("Duplicate corrected external cache keys")

    selected_key_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    selected_relation_count: Counter[tuple[str, str, str]] = Counter()
    selected_daily_flow: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    selected_raw_flow: defaultdict[tuple[str, str, str], float] = defaultdict(float)

    for r in ie_rows + ei_rows:
        key = (
            str(r["destination_key"]),
            str(r["selected_geo_id"]),
            str(r["direction"]),
        )
        cache = external_lookup.get(key)
        if cache is None:
            raise RuntimeError(f"Selected external cache key missing: {key}")
        if cache["status"] != "PASS":
            raise RuntimeError(f"Selected cache row not PASS: {key}")
        selected_relation_count[key] += 1
        selected_daily_flow[key] += parse_float(r["flow_daily"])
        selected_raw_flow[key] += parse_float(r["Pendolari_raw"])
        if key not in selected_key_rows:
            selected_key_rows[key] = cache

    selected_keys = sorted(selected_key_rows)
    selected_key_output = []
    for key in selected_keys:
        cache = selected_key_rows[key]
        fallback64 = str(cache["destination_key"]) in fallback_dest_keys
        selected_key_output.append({
            "destination_key": cache["destination_key"],
            "dest_COMUNE": cache["dest_COMUNE"],
            "gateway_id": cache["gateway_id"],
            "geo_id": cache["geo_id"],
            "direction": cache["direction"],
            "search_mode": "FALLBACK64" if fallback64 else "DEFAULT",
            "selected_b1_relations": selected_relation_count[key],
            "Pendolari_raw_sum": selected_raw_flow[key],
            "flow_daily_sum": selected_daily_flow[key],
            "external_time_s": cache["external_time_s"],
            "external_distance_m": cache["external_distance_m"],
            "crossing_snap_m": cache["crossing_snap_m"],
            "destination_snap_m": cache["destination_snap_m"],
        })

    default_keys = [
        k for k in selected_keys if k[0] not in fallback_dest_keys
    ]
    fallback_keys = [
        k for k in selected_keys if k[0] in fallback_dest_keys
    ]

    print(f"selected IE relation rows      = {len(ie_rows):,}")
    print(f"selected EI relation rows      = {len(ei_rows):,}")
    print(f"unique selected external legs  = {len(selected_keys):,}")
    print(f"default selected legs          = {len(default_keys):,}")
    print(f"fallback64 selected legs       = {len(fallback_keys):,}")

    # ------------------------------------------------------------------
    # D. Start staging, then diagnostic GraphHopper phases
    # ------------------------------------------------------------------
    staging.mkdir(parents=True, exist_ok=False)
    write_csv(staging / SELECTED_KEYS_CSV, selected_key_output)

    java_exe = gh08.find_java(runtime_root)

    all_route_results: list[dict[str, Any]] = []
    route_edges: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def run_phase(
        phase_name: str,
        keys: list[tuple[str, str, str]],
        fallback64: bool,
        config_name: str,
        log_name: str,
    ) -> None:
        if not keys:
            return
        print()
        print(f"D.{1 if not fallback64 else 2} {phase_name}")

        if not port_is_free(APP_PORT):
            raise RuntimeError(f"Application port {APP_PORT} already in use")
        if not port_is_free(ADMIN_PORT):
            raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")

        config_text, config_action = make_server_config(
            gh08,
            profile_config,
            graph_dir,
            staging,
            fallback64,
        )
        config_path = staging / config_name
        config_path.write_text(config_text, encoding="utf-8")
        print(f"config action                  = {config_action}")
        print(
            f"index.max_region_search        = "
            f"{FALLBACK_MAX_REGION_SEARCH if fallback64 else 'DEFAULT'}"
        )
        print("national PBF passed            = NO")
        print("bind host                      = localhost")

        log_path = staging / log_name
        log_handle = log_path.open(
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
            str(config_path),
        ]
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=staging,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            wait_for_server(proc)
            print("SERVER_LOAD                    = PASS")

            info = query_info()
            encoded_values = info.get("encoded_values", [])
            encoded_text = json.dumps(encoded_values)
            if "osm_way_id" not in encoded_text:
                raise RuntimeError(
                    "GraphHopper /info does not expose osm_way_id encoded value"
                )
            print("osm_way_id capability          = PASS")

            started = time.time()
            completed = 0
            with ThreadPoolExecutor(max_workers=args.http_workers) as pool:
                futures = {
                    pool.submit(
                        route_detail_request,
                        selected_key_rows[key],
                    ): key
                    for key in keys
                }
                for fut in as_completed(futures):
                    key = futures[fut]
                    result = fut.result()
                    result["search_mode"] = (
                        "FALLBACK64" if fallback64 else "DEFAULT"
                    )
                    result["selected_b1_relations"] = selected_relation_count[key]
                    result["Pendolari_raw_sum"] = selected_raw_flow[key]
                    result["flow_daily_sum"] = selected_daily_flow[key]
                    edges = result.pop("edges")
                    all_route_results.append(result)
                    route_edges[key] = edges
                    completed += 1
                    if completed % 100 == 0 or completed == len(keys):
                        elapsed = max(time.time() - started, 1e-9)
                        rate = completed / elapsed
                        remain = (len(keys) - completed) / max(rate, 1e-9)
                        with PRINT_LOCK:
                            print(
                                f"  details {completed:,}/{len(keys):,} "
                                f"({100*completed/len(keys):5.1f}%) "
                                f"rate={rate:5.1f}/s "
                                f"ETA={remain/60:5.1f} min"
                            )
        finally:
            status = stop_server(proc)
            log_handle.close()
            print(f"server shutdown                = {status}")

    run_phase(
        "DEFAULT SELECTED ROUTE DETAILS",
        default_keys,
        False,
        DEFAULT_CONFIG,
        DEFAULT_LOG,
    )
    run_phase(
        "FALLBACK64 SELECTED ROUTE DETAILS",
        fallback_keys,
        True,
        FALLBACK_CONFIG,
        FALLBACK_LOG,
    )

    if len(all_route_results) != len(selected_keys):
        raise RuntimeError(
            f"Selected detail routes {len(all_route_results)} "
            f"!= unique selected keys {len(selected_keys)}"
        )

    all_route_results.sort(
        key=lambda r: (
            str(r["destination_key"]),
            str(r["geo_id"]),
            str(r["direction"]),
        )
    )
    write_csv(staging / ROUTE_DETAIL_CSV, all_route_results)

    # ------------------------------------------------------------------
    # E. Build route-induced used external subgraph
    # ------------------------------------------------------------------
    print()
    print("E. USED EXTERNAL SUBGRAPH / EDGE DIAGNOSTICS")

    edge_acc: dict[tuple[Any, ...], dict[str, Any]] = {}
    node_acc: dict[tuple[float, float], dict[str, Any]] = {}
    used_osm_way_ids: set[int] = set()
    used_raw_edge_ids: set[int] = set()

    for key, edges in route_edges.items():
        route_seen_edges: set[tuple[Any, ...]] = set()
        route_seen_nodes: set[tuple[float, float]] = set()
        for e in edges:
            edge_id = int(e["edge_id"])
            way_id = int(e["osm_way_id"])
            edge_sig = normalized_edge_signature(e)
            used_osm_way_ids.add(way_id)
            used_raw_edge_ids.add(edge_id)

            rec = edge_acc.setdefault(
                edge_sig,
                {
                    "edge_signature": "|".join(map(str, edge_sig)),
                    "edge_id": edge_id,
                    "osm_way_id": way_id,
                    "route_count": 0,
                    "max_observed_edge_distance_m": 0.0,
                    "max_observed_geometry_segment_length_m": 0.0,
                    "zero_geometry_observation_count": 0,
                    "distance_path_detail_observation_count": 0,
                    "geometry_fallback_observation_count": 0,
                    "start_lon": edge_sig[2],
                    "start_lat": edge_sig[3],
                    "end_lon": edge_sig[4],
                    "end_lat": edge_sig[5],
                },
            )
            rec["max_observed_edge_distance_m"] = max(
                float(rec["max_observed_edge_distance_m"]),
                float(e["edge_distance_m"]),
            )
            rec["max_observed_geometry_segment_length_m"] = max(
                float(rec["max_observed_geometry_segment_length_m"]),
                float(e["geometry_segment_length_m"]),
            )
            if e["zero_geometry_segment"]:
                rec["zero_geometry_observation_count"] += 1
            if e["edge_distance_source"] == "DISTANCE_PATH_DETAIL":
                rec["distance_path_detail_observation_count"] += 1
            else:
                rec["geometry_fallback_observation_count"] += 1

            if edge_sig not in route_seen_edges:
                rec["route_count"] += 1
                route_seen_edges.add(edge_sig)

            for lon, lat in (
                (e["start_lon"], e["start_lat"]),
                (e["end_lon"], e["end_lat"]),
            ):
                node_key = (
                    round(float(lon), NODE_COORD_DECIMALS),
                    round(float(lat), NODE_COORD_DECIMALS),
                )
                nrec = node_acc.setdefault(
                    node_key,
                    {
                        "node_lon": node_key[0],
                        "node_lat": node_key[1],
                        "route_count": 0,
                    },
                )
                if node_key not in route_seen_nodes:
                    nrec["route_count"] += 1
                    route_seen_nodes.add(node_key)

    used_edge_rows = [
        rec
        for _, rec in sorted(edge_acc.items())
    ]
    used_node_rows = [
        rec
        for _, rec in sorted(node_acc.items())
    ]

    used_edge_union_length_m = sum(
        float(r["max_observed_edge_distance_m"])
        for r in used_edge_rows
    )

    write_csv(staging / USED_EDGES_CSV, used_edge_rows)
    write_csv(staging / USED_NODES_CSV, used_node_rows)

    print(f"used edge signatures           = {len(used_edge_rows):,}")
    print(f"used raw GraphHopper edge ids  = {len(used_raw_edge_ids):,}")
    print(f"used route-induced nodes       = {len(used_node_rows):,}")
    print(f"used OSM way ids               = {len(used_osm_way_ids):,}")
    print(
        f"used edge-union length km      = "
        f"{used_edge_union_length_m/1000.0:.6f}"
    )

    # ------------------------------------------------------------------
    # F. Targeted ignored restriction intersection
    # ------------------------------------------------------------------
    print()
    print("F. TARGETED IGNORED-RESTRICTION INTERSECTION")

    import_log_path = find_import_log_by_hash(root)
    print(f"frozen import log              = {import_log_path}")
    print(f"import log SHA256              = {sha256(import_log_path)}")

    ignored = parse_ignored_restrictions(import_log_path)
    intersection_rows: list[dict[str, Any]] = []
    candidate_intersections = 0
    no_way_member_relations = 0

    for r in ignored:
        member_ways = set(r["member_way_ids"])
        intersecting = sorted(member_ways & used_osm_way_ids)
        if not member_ways:
            classification = "NO_WAY_MEMBER_MALFORMED_NON_ACTIONABLE"
            no_way_member_relations += 1
        elif intersecting:
            classification = "USED_WAY_MEMBER_INTERSECTION_CANDIDATE"
            candidate_intersections += 1
        else:
            classification = "NO_USED_WAY_MEMBER_INTERSECTION"

        intersection_rows.append({
            "relation_id": r["relation_id"],
            "classification": classification,
            "reason": r["reason"],
            "tags": r["tags"],
            "member_way_ids": "|".join(
                str(x) for x in r["member_way_ids"]
            ),
            "member_node_ids": "|".join(
                str(x) for x in r["member_node_ids"]
            ),
            "intersecting_used_way_ids": "|".join(
                str(x) for x in intersecting
            ),
            "import_log_line": r["line_no"],
        })

    write_csv(
        staging / IGNORED_RESTRICTIONS_CSV,
        intersection_rows,
    )

    print(f"ignored restriction relations = {len(ignored):,}")
    print(f"no-way malformed relations     = {no_way_member_relations:,}")
    print(
        f"used-way intersection candidates = "
        f"{candidate_intersections:,}"
    )

    # ------------------------------------------------------------------
    # G. Gateway final audit
    # ------------------------------------------------------------------
    print()
    print("G. FINAL GATEWAY USAGE AUDIT")

    gateway_acc: defaultdict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"rows": 0.0, "raw": 0.0, "daily": 0.0}
    )
    unexpected_gateways: set[str] = set()

    for r in ie_rows + ei_rows:
        gateway = str(r["selected_gateway_id"])
        direction = str(r["direction"])
        if gateway not in VENETO_GATEWAYS:
            unexpected_gateways.add(gateway)
        a = gateway_acc[(direction, gateway)]
        a["rows"] += 1
        a["raw"] += parse_float(r["Pendolari_raw"])
        a["daily"] += parse_float(r["flow_daily"])

    gateway_usage_rows = [
        {
            "direction": direction,
            "gateway_id": gateway,
            "b1_rows": int(acc["rows"]),
            "Pendolari_raw_sum": acc["raw"],
            "flow_daily_sum": acc["daily"],
            "expected_veneto_gateway": gateway in VENETO_GATEWAYS,
        }
        for (direction, gateway), acc in sorted(gateway_acc.items())
    ]
    write_csv(staging / GATEWAY_USAGE_CSV, gateway_usage_rows)

    used_gateways = {
        gateway for _, gateway in gateway_acc.keys()
    }
    print(f"used modelling gateways        = {len(used_gateways)}/{EXPECTED_MODELLING_GATEWAYS}")
    print(f"unexpected AT/SI gateways      = {len(unexpected_gateways)}")

    # ------------------------------------------------------------------
    # H. Final integrity
    # ------------------------------------------------------------------
    print()
    print("H. FINAL BYTE-INTEGRITY")

    graph_after = gh08.graph_inventory(graph_dir)
    graph_unchanged = (
        gh08.normalized_inventory(graph_before)
        == gh08.normalized_inventory(graph_after)
    )
    if not graph_unchanged:
        raise RuntimeError("Italy graph changed during GH09")

    frozen_end_ok = True
    for label, (rel, expected) in FROZEN_FVG.items():
        p = root / Path(rel)
        actual = sha256(p)
        if actual != expected or actual != frozen_start[label]:
            frozen_end_ok = False
            print(f"{label:<34} FAIL  {actual}")
        else:
            print(f"{label:<34} PASS  {actual}")
    if not frozen_end_ok:
        raise RuntimeError("Frozen FVG artifact hash drift")

    # Re-hash GH08F critical outputs.
    for label, filename, expected in (
        ("GH08F external cache", GH08F_EXTERNAL, GH08F_EXTERNAL_SHA256),
        ("GH08F IE", GH08F_IE, GH08F_IE_SHA256),
        ("GH08F EI", GH08F_EI, GH08F_EI_SHA256),
        ("GH08F summary", GH08F_SUMMARY, GH08F_SUMMARY_SHA256),
        ("GH08F manifest", GH08F_MANIFEST, GH08F_MANIFEST_SHA256),
    ):
        actual = sha256(gh08f_dir / filename)
        if actual != expected:
            raise RuntimeError(f"{label} changed during GH09")

    print("Italy graph unchanged          = PASS")
    print("Frozen FVG hashes              = PASS")
    print("GH08F v02 unchanged            = PASS")

    # ------------------------------------------------------------------
    # I. Final gate
    # ------------------------------------------------------------------
    ie_daily = sum(parse_float(r["flow_daily"]) for r in ie_rows)
    ei_daily = sum(parse_float(r["flow_daily"]) for r in ei_rows)
    assert_close(ie_daily, EXPECTED_DAILY_FLOW, "IE daily flow", 1e-6)
    assert_close(ei_daily, EXPECTED_DAILY_FLOW, "EI daily flow", 1e-6)

    max_destination_snap = max(
        parse_float(r["destination_snap_m"])
        for r in external_rows
        if str(r["status"]) == "PASS"
    )

    blockers = []
    if candidate_intersections > 0:
        blockers.append(
            "IGNORED_RESTRICTION_USED_WAY_INTERSECTION_CANDIDATE"
        )
    if unexpected_gateways:
        blockers.append("UNEXPECTED_NON_VENETO_GATEWAY_USAGE")
    if len(all_route_results) != len(selected_keys):
        blockers.append("SELECTED_ROUTE_DETAIL_COVERAGE")
    if not graph_unchanged:
        blockers.append("ITALY_GRAPH_CHANGED")
    if not frozen_end_ok:
        blockers.append("FROZEN_FVG_HASH_DRIFT")

    verdict = "PASS" if not blockers else "NOT_READY"
    next_gate = (
        "RETURN_TO_CHAT_MADRE"
        if verdict == "PASS"
        else "TARGETED_RESTRICTION_DIAGNOSIS"
    )

    summary = {
        "schema": "B1_EXT_GH_09_SELECTED_ROUTE_DIAGNOSTICS_SUMMARY_V01",
        "verdict": verdict,
        "blocking_reasons": blockers,
        "architecture": {
            "source_relation": SOURCE_RELATION,
            "internal_router": INTERNAL_ROUTER,
            "external_router": EXTERNAL_ROUTER,
            "composition": COMPOSITION,
        },
        "routing": {
            "B1_relations": EXPECTED_B1_ROWS,
            "IE_routed": len(ie_rows),
            "EI_routed": len(ei_rows),
            "IE_unreachable": 0,
            "EI_unreachable": 0,
            "IE_daily_flow": ie_daily,
            "EI_daily_flow": ei_daily,
            "ambiguous_gateway_mapping": 0,
            "max_destination_snap_m": max_destination_snap,
        },
        "gateway_usage": {
            "expected_veneto_only": len(unexpected_gateways) == 0,
            "used_gateway_count": len(used_gateways),
            "unexpected_gateway_count": len(unexpected_gateways),
            "unexpected_gateways": sorted(unexpected_gateways),
            "rows": gateway_usage_rows,
        },
        "used_subgraph": {
            "unique_selected_external_routes": len(selected_keys),
            "used_edge_signatures": len(used_edge_rows),
            "used_raw_edge_ids": len(used_raw_edge_ids),
            "used_route_induced_nodes": len(used_node_rows),
            "used_osm_way_ids": len(used_osm_way_ids),
            "used_edge_union_length_km": used_edge_union_length_m / 1000.0,
            "zero_geometry_edge_observations": sum(
                int(r["zero_geometry_observation_count"])
                for r in used_edge_rows
            ),
            "geometry_fallback_edge_observations": sum(
                int(r["geometry_fallback_observation_count"])
                for r in used_edge_rows
            ),
            "node_semantics": (
                "UNIQUE_ROUTE_INDUCED_EDGE_BOUNDARY_COORDINATES_FROM_GH_PATH_DETAILS"
            ),
            "edge_semantics": (
                "UNIQUE_EDGE_ID_OSM_WAY_ID_NORMALIZED_ENDPOINT_SIGNATURES_"
                "TO_PROTECT_AGAINST_QUERYGRAPH_VIRTUAL_ID_COLLISIONS"
            ),
            "length_semantics": (
                "SUM_MAX_OBSERVED_DISTANCE_PATH_DETAIL_PER_UNIQUE_EDGE_SIGNATURE"
            ),
        },
        "ignored_restrictions": {
            "import_log_path": str(import_log_path),
            "import_log_sha256": sha256(import_log_path),
            "total_ignored_relations": len(ignored),
            "no_way_member_malformed_relations": no_way_member_relations,
            "candidate_intersections": candidate_intersections,
            "intersection_rule": (
                "CONSERVATIVE_MEMBER_WAY_INTERSECTION_AGAINST_ACTUALLY_USED_OSM_WAY_IDS"
            ),
        },
        "qa": {
            "targeted_qa": "PASS",
            "graph_load_qa": "PASS",
            "selected_route_detail_qa": "PASS",
            "GH06_summary_sha256": sha256(gh06_dir / GH06_SUMMARY),
            "GH06_manifest_sha256": sha256(gh06_dir / GH06_MANIFEST),
        },
        "integrity": {
            "frozen_fvg_hashes": "UNCHANGED",
            "italy_graph_byte_identical": "YES",
            "gh08f_v02_outputs_modified": False,
            "italy_pbf_sha256": sha256(italy_pbf),
            "graph_manifest_sha256": sha256(graph_manifest_path),
        },
        "next_gate": next_gate,
    }

    summary_path = staging / SUMMARY_JSON
    write_json(summary_path, summary)

    report_text = build_final_report(summary)
    report_path = staging / FINAL_REPORT_TXT
    report_path.write_text(report_text, encoding="utf-8")

    output_files = [
        staging / SELECTED_KEYS_CSV,
        staging / ROUTE_DETAIL_CSV,
        staging / USED_EDGES_CSV,
        staging / USED_NODES_CSV,
        staging / IGNORED_RESTRICTIONS_CSV,
        staging / GATEWAY_USAGE_CSV,
        staging / DEFAULT_CONFIG,
        staging / DEFAULT_LOG,
        staging / FALLBACK_CONFIG,
        staging / FALLBACK_LOG,
        summary_path,
        report_path,
    ]
    # Config/log for a phase with zero keys would be absent; not expected here,
    # but keep manifest robust.
    output_files = [p for p in output_files if p.exists()]

    manifest = {
        "schema": "B1_EXT_GH_09_SELECTED_ROUTE_DIAGNOSTICS_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "inputs": {
            "GH08F_manifest": {
                "path": str(gh08f_dir / GH08F_MANIFEST),
                "sha256": sha256(gh08f_dir / GH08F_MANIFEST),
            },
            "GH08F_summary": {
                "path": str(gh08f_dir / GH08F_SUMMARY),
                "sha256": sha256(gh08f_dir / GH08F_SUMMARY),
            },
            "GH06_manifest": {
                "path": str(gh06_dir / GH06_MANIFEST),
                "sha256": sha256(gh06_dir / GH06_MANIFEST),
            },
            "Italy_PBF": {
                "path": str(italy_pbf),
                "sha256": sha256(italy_pbf),
            },
            "Italy_graph_manifest": {
                "path": str(graph_manifest_path),
                "sha256": sha256(graph_manifest_path),
            },
            "import_log": {
                "path": str(import_log_path),
                "sha256": sha256(import_log_path),
            },
        },
        "outputs": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in output_files
        ],
        "blocking_reasons": blockers,
        "next_gate": next_gate,
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    staging.rename(final_dir)

    print()
    print("=" * 124)
    print(f"B1_EXT_GH_09_SELECTED_ROUTE_DIAGNOSTICS_FINAL_GATE = {verdict}")
    print(f"G_EXT_ITALY_B1_v01 = {verdict}")
    print(f"B1_RELATIONS = {EXPECTED_B1_ROWS}")
    print(f"IE_ROUTED = {len(ie_rows)}/{EXPECTED_B1_ROWS}")
    print(f"EI_ROUTED = {len(ei_rows)}/{EXPECTED_B1_ROWS}")
    print("IE_UNREACHABLE = 0")
    print("EI_UNREACHABLE = 0")
    print("AMBIGUOUS_GATEWAY_MAPPING = 0")
    print(
        f"VENETO_EXPECTED_GATEWAY_USAGE = "
        f"{'YES' if not unexpected_gateways else 'NO'}"
    )
    print(f"VENETO_GATEWAYS_USED = {len(used_gateways)}/{EXPECTED_MODELLING_GATEWAYS}")
    print(f"UNEXPECTED_AT_SI_GATEWAY_USAGE = {len(unexpected_gateways)}")
    print(f"UNIQUE_SELECTED_EXTERNAL_ROUTES = {len(selected_keys)}")
    print(f"USED_EXTERNAL_EDGES = {len(used_edge_rows)}")
    print(f"USED_EXTERNAL_RAW_EDGE_IDS = {len(used_raw_edge_ids)}")
    print(f"USED_EXTERNAL_NODES = {len(used_node_rows)}")
    print(f"USED_EXTERNAL_OSM_WAYS = {len(used_osm_way_ids)}")
    print(
        f"USED_EXTERNAL_LENGTH_KM = "
        f"{used_edge_union_length_m/1000.0:.6f}"
    )
    print(
        f"IGNORED_RESTRICTIONS_INTERSECTING_USED_ROUTES = "
        f"{candidate_intersections}"
    )
    print("TARGETED_QA = PASS")
    print("GRAPH_LOAD_QA = PASS")
    print("SELECTED_ROUTE_DETAIL_QA = PASS")
    print("FROZEN_FVG_HASHES = UNCHANGED")
    print("ITALY_GRAPH_BYTE_IDENTICAL_AFTER_QA = YES")
    print(f"ITALY_PBF_SHA256 = {ITALY_PBF_SHA256}")
    print(
        f"GRAPH_MANIFEST_SHA256 = "
        f"{EXPECTED_GRAPH_MANIFEST_SHA256}"
    )
    print(f"NEXT_GATE = {next_gate}")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print(f"{FINAL_REPORT_TXT} SHA256 = {sha256(final_dir / FINAL_REPORT_TXT)}")
    print("=== RUN COMPLETATA ===")

    if verdict == "PASS":
        print("HARD STOP — RETURN CONTROL TO CHAT MADRE")
    else:
        print(
            "HARD STOP — DO NOT RETURN TO CHAT MADRE; "
            "TARGETED RESTRICTION DIAGNOSIS REQUIRED"
        )

    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
