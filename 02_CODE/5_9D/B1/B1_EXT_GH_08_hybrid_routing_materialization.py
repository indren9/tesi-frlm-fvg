#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import re
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
from pyproj import Transformer

# ======================================================================================
# B1-EXT-GH 08 — HYBRID ROUTING MATERIALIZATION
#
# PURPOSE
#   Materialize the 2,895 B1 extra-region commuter relations with the frozen hybrid
#   routing contract:
#
#     IE: FVG commune -> Gamma weighted accesses -> B5 frozen -> physical crossing
#         -> GraphHopper Italy -> external destination
#
#     EI: external destination -> GraphHopper Italy -> physical crossing -> B5 frozen
#         -> Gamma weighted accesses of the FVG commune
#
#   Crossing selection is MINIMUM COMBINED TIME over the 49 frozen Veneto physical
#   crossing concepts. Only AFTER that minimization is the crossing aggregated to its
#   frozen modelling gateway.
#
# HARD GUARDRAILS
#   - frozen FVG routing/Gamma inputs are READ ONLY;
#   - existing imported Italy GraphHopper graph only;
#   - NO PBF import;
#   - NO end-to-end GraphHopper substitution for B5;
#   - IE and EI are routed separately;
#   - EI mirrors the B1 relation and uses the same B1 flow field as IE;
#   - no nearest-crossing or bearing heuristic;
#   - no gateway choice before physical-crossing minimization;
#   - no overwrite of a prior final materialization.
#
# THIS GATE DOES NOT YET
#   - extract the final used external subgraph in detail;
#   - audit ignored GraphHopper restriction relations against selected routes;
#   - modify G_OSM / Gamma_OSM / OD_PATH_SYSTEM_OSM;
#   - reopen Gravity.
#
# Those are reserved for the selected-route diagnostic/final gate after this run.
# ======================================================================================

ROOT_DEFAULT = r"C:\Tesi"

# ----- Frozen B5 -----------------------------------------------------------------------
B5_DIR_REL = r"Tesi_QGIS\02_package\grafo_operativo_osm"
B5_TIME_NAME = "osm_turn_state_time_v01.npz"
B5_TIME_SHA256 = "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"
B5_BASE_NODES_NAME = "osm_turn_state_base_nodes_v01.npy"
B5_BASE_NODES_SHA256 = "de02faa32628af6099118e08bd3e13847fbb0330d1aa7d824df47220b2f947d7"
B5_STATE_NODE_NAME = "osm_turn_state_node_id_v01.npy"
B5_STATE_NODE_SHA256 = "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935"
EXPECTED_B5_BASE_STATES = 897_857
EXPECTED_B5_TOTAL_STATES = 904_607
EXPECTED_B5_TRANSITIONS = 1_699_994

# ----- Frozen Gamma --------------------------------------------------------------------
GAMMA_REL = r"Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv"
GAMMA_SHA256 = "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
EXPECTED_GAMMA_ROWS = 645
EXPECTED_GAMMA_COMMUNES = 215
LAMBDA_SUM_TOL = 1e-12

# ----- GH07 frozen interface evidence --------------------------------------------------
GH07_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01"
)
GH07_MAPPING_NAME = "B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
GH07_MAPPING_SHA256 = "57026868b57e29944d1234fad43078db2c0b15a565039d07a4c1d30ed20ce2cc"
GH07_SUMMARY_NAME = "B1_EXT_GH_07_hybrid_runtime_preflight_summary_v01.json"
GH07_SUMMARY_SHA256 = "d80d7b18ad42a432e7fa3334390bb2063fc9fd43e0c3667f6eba3123972c0494"
GH07_MANIFEST_NAME = "B1_EXT_GH_07_hybrid_runtime_preflight_manifest_v01.json"
GH07_MANIFEST_SHA256 = "fa659688d17a47022a86d95476234d4e640cbf866b2dcceb7d1e90b5911beaea"
EXPECTED_VENETO_GEOS = 49
EXPECTED_VENETO_GATEWAYS = 12

# ----- GH06 evidence -------------------------------------------------------------------
GH06_MANIFEST_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\graph_load_targeted_routing_qa_v01"
    r"\B1_EXT_GH_graph_load_targeted_routing_qa_manifest_v01.json"
)
GH06_MANIFEST_SHA256 = "a7590ed3b5dd61670ee509843b6707d14d66fc609ded37056a81aa8214f0353d"

# ----- Existing Italy GraphHopper ------------------------------------------------------
PROFILE_NAME = "b1_ext_car_b5_compat_v01"
APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 90

FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"

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

HEAVY_RUNS_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\heavy_import_runs"
)
EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"

# ----- B1 input ------------------------------------------------------------------------
BASE_GPKG_REL = r"Tesi_QGIS\02_package\base_territoriale_fvg.gpkg"
B1_TABLE = "pendolari_extra_regione_fvg_2021_od_xy"
EXPECTED_B1_ROWS = 2_895
EXPECTED_B1_RAW_FLOW = 14_458.0
B1_DAILY_FACTOR = 0.42855
EXPECTED_B1_DAILY_FLOW = 6_195.97590
FLOW_TOL = 1e-6

# ----- Routing thresholds --------------------------------------------------------------
MAX_CROSSING_SNAP_M = 5.0
MAX_DESTINATION_SNAP_M = 10_000.0
NUMERIC_TIE_TOL_S = 1e-6
DEFAULT_HTTP_WORKERS = 6

# ----- Output --------------------------------------------------------------------------
OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v01"
)
SERVER_CONFIG = "graphhopper_b1_ext_server_gh08_v01.yml"
SERVER_LOG = "graphhopper_b1_ext_server_gh08_v01.log"

B1_NORMALIZED_CSV = "B1_EXT_GH_08_b1_normalized_v01.csv"
INTERNAL_ACCESS_CSV = "B1_EXT_GH_08_internal_access_crossing_costs_v01.csv"
INTERNAL_COMMUNE_CSV = "B1_EXT_GH_08_internal_commune_crossing_costs_v01.csv"
EXTERNAL_ROUTE_CSV = "B1_EXT_GH_08_external_crossing_route_cache_v01.csv"
ENDPOINT_SNAP_CSV = "B1_EXT_GH_08_endpoint_snap_v01.csv"
IE_ROUTING_CSV = "B1_EXT_GH_08_IE_routing_v01.csv"
EI_ROUTING_CSV = "B1_EXT_GH_08_EI_routing_v01.csv"
CROSSING_FLOW_CSV = "B1_EXT_GH_08_crossing_flow_attribution_v01.csv"
GATEWAY_FLOW_CSV = "B1_EXT_GH_08_gateway_flow_attribution_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_08_hybrid_routing_materialization_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_08_hybrid_routing_materialization_manifest_v01.json"

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


def write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def strict_hash_check(name: str, path: Path, expected: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    ok = actual == expected.lower()
    print(f"{name:<28} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {name}")
    return actual


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    if not columns:
        raise RuntimeError(f"CSV has no header: {path}")
    return rows, columns


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if not rows and fieldnames is None:
        raise RuntimeError(f"Cannot infer CSV fields for empty output: {path.name}")
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_intlike(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if any(ch in text.lower() for ch in (".", "e")):
            x = float(text)
            if not math.isfinite(x) or not x.is_integer():
                return None
            return int(x)
        return int(text)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        x = float(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def ci_column(columns: list[str], candidates: list[str], required: bool = False) -> str | None:
    lookup = {c.lower(): c for c in columns}
    for candidate in candidates:
        hit = lookup.get(candidate.lower())
        if hit is not None:
            return hit
    if required:
        raise RuntimeError(f"Missing required column among {candidates}; actual={columns}")
    return None


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def normalized_inventory(rows: list[dict[str, object]]) -> list[tuple[str, int, str]]:
    return sorted(
        (str(r["relative_path"]), int(r["size_bytes"]), str(r["sha256"]).lower())
        for r in rows
    )


def graph_inventory(graph_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for p in sorted(x for x in graph_dir.rglob("*") if x.is_file()):
        rows.append({
            "relative_path": p.relative_to(graph_dir).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return rows


def find_graph_manifest(root: Path) -> tuple[Path, dict]:
    runs_root = root / Path(HEAVY_RUNS_REL)
    if not runs_root.is_dir():
        raise FileNotFoundError(runs_root)
    candidates = sorted(runs_root.rglob("B1_EXT_GH_graph_file_manifest.json"))
    matches = [p for p in candidates if sha256(p) == EXPECTED_GRAPH_MANIFEST_SHA256]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one frozen Italy graph manifest with SHA256 "
            f"{EXPECTED_GRAPH_MANIFEST_SHA256}; found {len(matches)}"
        )
    path = matches[0]
    with path.open("r", encoding="utf-8-sig") as f:
        return path, json.load(f)


# ======================================================================================
# B5 helpers
# ======================================================================================

def load_csr_npz(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]:
    with np.load(path, allow_pickle=False) as z:
        required = {"indices", "indptr", "format", "shape", "data"}
        missing = required - set(z.files)
        if missing:
            raise RuntimeError(f"{path.name}: missing CSR keys {sorted(missing)}")
        fmt_raw = z["format"].item()
        fmt = fmt_raw.decode("ascii") if isinstance(fmt_raw, bytes) else str(fmt_raw)
        if fmt.lower() != "csr":
            raise RuntimeError(f"{path.name}: expected CSR, found {fmt!r}")
        shape_arr = np.asarray(z["shape"], dtype=np.int64)
        if shape_arr.shape != (2,):
            raise RuntimeError(f"{path.name}: invalid shape vector")
        indices = np.asarray(z["indices"], dtype=np.int32)
        indptr = np.asarray(z["indptr"], dtype=np.int32)
        data = np.asarray(z["data"], dtype=np.float64)
        shape = (int(shape_arr[0]), int(shape_arr[1]))
    if shape != (EXPECTED_B5_TOTAL_STATES, EXPECTED_B5_TOTAL_STATES):
        raise RuntimeError(f"B5 shape {shape} != expected")
    if len(indices) != EXPECTED_B5_TRANSITIONS or len(data) != EXPECTED_B5_TRANSITIONS:
        raise RuntimeError("B5 transition count mismatch")
    if len(indptr) != EXPECTED_B5_TOTAL_STATES + 1:
        raise RuntimeError("B5 indptr length mismatch")
    if int(indptr[0]) != 0 or int(indptr[-1]) != EXPECTED_B5_TRANSITIONS:
        raise RuntimeError("B5 indptr endpoint mismatch")
    if not np.all(np.isfinite(data)) or np.any(data < 0):
        raise RuntimeError("B5 time costs invalid")
    return indptr, indices, data, shape


def reverse_csr(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(indptr) - 1
    counts_out = np.diff(indptr).astype(np.int64, copy=False)
    src = np.repeat(np.arange(n, dtype=np.int32), counts_out)
    if len(src) != len(indices):
        raise RuntimeError("reverse_csr source vector length mismatch")
    dst = indices.astype(np.int32, copy=False)
    order = np.argsort(dst, kind="stable")
    rev_indices = src[order]
    rev_data = data[order]
    counts_in = np.bincount(dst, minlength=n).astype(np.int64, copy=False)
    rev_indptr64 = np.empty(n + 1, dtype=np.int64)
    rev_indptr64[0] = 0
    np.cumsum(counts_in, out=rev_indptr64[1:])
    if int(rev_indptr64[-1]) != len(indices):
        raise RuntimeError("reverse_csr edge count mismatch")
    if int(rev_indptr64[-1]) > np.iinfo(np.int32).max:
        raise RuntimeError("reverse_csr int32 indptr overflow")
    return rev_indptr64.astype(np.int32), rev_indices, rev_data


def dijkstra_multi_source_to_state_targets(
    indptr: np.ndarray,
    indices: np.ndarray,
    weights: np.ndarray,
    source_states: Iterable[int],
    target_states: Iterable[int],
) -> tuple[dict[int, float], int]:
    n = len(indptr) - 1
    sources = sorted({int(s) for s in source_states})
    targets = sorted({int(t) for t in target_states})
    if not sources or not targets:
        raise ValueError("Dijkstra sources/targets cannot be empty")
    if any(s < 0 or s >= n for s in sources) or any(t < 0 or t >= n for t in targets):
        raise ValueError("Dijkstra state out of range")

    target_mask = np.zeros(n, dtype=np.bool_)
    target_mask[targets] = True
    remaining = len(targets)
    result: dict[int, float] = {}

    dist = np.full(n, np.inf, dtype=np.float64)
    heap: list[tuple[float, int]] = []
    for s in sources:
        if dist[s] != 0.0:
            dist[s] = 0.0
            heapq.heappush(heap, (0.0, s))

    settled = 0
    while heap and remaining:
        d_u, u = heapq.heappop(heap)
        if d_u != float(dist[u]):
            continue
        settled += 1
        if target_mask[u]:
            result[u] = d_u
            target_mask[u] = False
            remaining -= 1
            if remaining == 0:
                break
        start = int(indptr[u])
        end = int(indptr[u + 1])
        for pos in range(start, end):
            v = int(indices[pos])
            alt = d_u + float(weights[pos])
            if alt < float(dist[v]):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))
    return result, settled


def dijkstra_to_physical_labels(
    indptr: np.ndarray,
    indices: np.ndarray,
    weights: np.ndarray,
    source_state: int,
    label_by_state: np.ndarray,
    label_count: int,
) -> tuple[np.ndarray, int]:
    n = len(indptr) - 1
    if not (0 <= source_state < n):
        raise ValueError("source_state out of range")
    if label_by_state.shape != (n,):
        raise ValueError("label_by_state shape mismatch")

    out = np.full(label_count, np.inf, dtype=np.float64)
    remaining = label_count
    dist = np.full(n, np.inf, dtype=np.float64)
    dist[source_state] = 0.0
    heap: list[tuple[float, int]] = [(0.0, source_state)]
    settled = 0

    while heap and remaining:
        d_u, u = heapq.heappop(heap)
        if d_u != float(dist[u]):
            continue
        settled += 1
        label = int(label_by_state[u])
        if label >= 0 and not math.isfinite(float(out[label])):
            out[label] = d_u
            remaining -= 1
            if remaining == 0:
                break
        start = int(indptr[u])
        end = int(indptr[u + 1])
        for pos in range(start, end):
            v = int(indices[pos])
            alt = d_u + float(weights[pos])
            if alt < float(dist[v]):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))
    return out, settled


def states_for_nodes(state_node_id: np.ndarray, nodes: set[int]) -> dict[int, list[int]]:
    result = {node: [] for node in nodes}
    for state_id, raw_node in enumerate(state_node_id):
        node = int(raw_node)
        if node in result:
            result[node].append(state_id)
    return result


# ======================================================================================
# Gamma / crossing / B1 input
# ======================================================================================

def load_gamma(path: Path, base_nodes: np.ndarray, state_node_id: np.ndarray) -> dict[str, object]:
    rows, columns = read_csv(path)
    required = {
        "PRO_COM", "COMUNE", "access_order", "structural_node_id", "base_state_id",
        "lambda_L", "weight_rule", "tau_m",
    }
    missing = required - set(columns)
    if missing:
        raise RuntimeError(f"Gamma missing columns: {sorted(missing)}")
    if len(rows) != EXPECTED_GAMMA_ROWS:
        raise RuntimeError(f"Gamma rows {len(rows)} != {EXPECTED_GAMMA_ROWS}")

    normalized: list[dict[str, object]] = []
    by_com: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        pro_com = parse_intlike(row["PRO_COM"])
        access_order = parse_intlike(row["access_order"])
        node = parse_intlike(row["structural_node_id"])
        base_state = parse_intlike(row["base_state_id"])
        lam = parse_float(row["lambda_L"])
        tau = parse_float(row["tau_m"])
        if None in (pro_com, access_order, node, base_state, lam, tau):
            raise RuntimeError(f"Gamma parse failure: {row}")
        assert pro_com is not None and access_order is not None and node is not None
        assert base_state is not None and lam is not None and tau is not None
        if not (lam > 0) or row["weight_rule"] != "EXP_REL_300" or abs(tau - 300.0) > 1e-9:
            raise RuntimeError(f"Gamma weight contract failure: {row}")
        if not (0 <= base_state < len(base_nodes)):
            raise RuntimeError("Gamma base state out of range")
        if int(base_nodes[base_state]) != node or int(state_node_id[base_state]) != node:
            raise RuntimeError(
                f"Gamma base-state node mismatch PRO_COM={pro_com} access={access_order}"
            )
        item = {
            "PRO_COM": pro_com,
            "COMUNE": str(row["COMUNE"]),
            "access_order": access_order,
            "physical_node_id": node,
            "base_state_id": base_state,
            "lambda_L": lam,
        }
        normalized.append(item)
        by_com[pro_com].append(item)

    if len(by_com) != EXPECTED_GAMMA_COMMUNES:
        raise RuntimeError(f"Gamma communes {len(by_com)} != {EXPECTED_GAMMA_COMMUNES}")
    max_err = 0.0
    for pro_com, items in by_com.items():
        if len(items) != 3 or {int(x["access_order"]) for x in items} != {1, 2, 3}:
            raise RuntimeError(f"Gamma access triplet failure PRO_COM={pro_com}")
        err = abs(sum(float(x["lambda_L"]) for x in items) - 1.0)
        max_err = max(max_err, err)
        if err > LAMBDA_SUM_TOL:
            raise RuntimeError(f"Gamma lambda sum failure PRO_COM={pro_com}: {err}")
    return {"rows": normalized, "by_com": by_com, "max_lambda_sum_error": max_err}


def load_crossings(path: Path) -> list[dict[str, object]]:
    rows, columns = read_csv(path)
    required = {
        "gateway_id", "geo_id", "physical_node_id", "b5_base_state_id",
        "best_anchor_lon", "best_anchor_lat", "best_anchor_distance_m", "status",
    }
    missing = required - set(columns)
    if missing:
        raise RuntimeError(f"GH07 mapping missing columns: {sorted(missing)}")
    if len(rows) != EXPECTED_VENETO_GEOS:
        raise RuntimeError(f"GH07 crossings {len(rows)} != {EXPECTED_VENETO_GEOS}")

    out: list[dict[str, object]] = []
    seen_geo: set[str] = set()
    for row in rows:
        geo = str(row["geo_id"]).strip()
        gateway = str(row["gateway_id"]).strip()
        node = parse_intlike(row["physical_node_id"])
        base_state = parse_intlike(row["b5_base_state_id"])
        lon = parse_float(row["best_anchor_lon"])
        lat = parse_float(row["best_anchor_lat"])
        anchor_m = parse_float(row["best_anchor_distance_m"])
        if not geo or not gateway or None in (node, base_state, lon, lat, anchor_m):
            raise RuntimeError(f"Invalid GH07 crossing row: {row}")
        if geo in seen_geo:
            raise RuntimeError(f"Duplicate geo_id in GH07 mapping: {geo}")
        seen_geo.add(geo)
        out.append({
            "gateway_id": gateway,
            "geo_id": geo,
            "physical_node_id": int(node),
            "b5_base_state_id": int(base_state),
            "lon": float(lon),
            "lat": float(lat),
            "a0_to_anchor_m": float(anchor_m),
        })
    if len({str(x["gateway_id"]) for x in out}) != EXPECTED_VENETO_GATEWAYS:
        raise RuntimeError("GH07 gateway count mismatch")
    return sorted(out, key=lambda x: (str(x["gateway_id"]), str(x["geo_id"])))


def load_b1_relations(gpkg: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    uri = gpkg.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        columns = [row[1] for row in con.execute(f'PRAGMA table_info("{B1_TABLE}")')]
        if not columns:
            raise RuntimeError(f"Missing B1 table: {B1_TABLE}")
        row_count = int(con.execute(f'SELECT COUNT(*) FROM "{B1_TABLE}"').fetchone()[0])
        if row_count != EXPECTED_B1_ROWS:
            raise RuntimeError(f"B1 rows {row_count} != {EXPECTED_B1_ROWS}")

        origin_code = ci_column(columns, ["procom_res_join", "Procom_res", "PRO_COM"], required=True)
        origin_name = ci_column(columns, ["orig_com_COMUNE", "Comune_res", "COMUNE"])
        dest_name = ci_column(columns, ["dest_COMUNE", "Comune_lav"], required=True)
        dest_x = ci_column(columns, ["dest_xcoord", "xcoord_lav"], required=True)
        dest_y = ci_column(columns, ["dest_ycoord", "ycoord_lav"], required=True)
        flow_col = ci_column(columns, ["Pendolari_uscita", "Pendolari"], required=True)
        dest_code_raw = ci_column(columns, ["Procom_lav"])
        dest_code_join = ci_column(columns, ["procom_lav_join"])
        orig_x = ci_column(columns, ["orig_x_com"])
        orig_y = ci_column(columns, ["orig_y_com"])
        fid_col = ci_column(columns, ["fid"])

        transformer = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
        sql = f'SELECT rowid AS __sqlite_rowid__, * FROM "{B1_TABLE}" ORDER BY rowid'
        raw_rows = con.execute(sql).fetchall()

        normalized: list[dict[str, object]] = []
        raw_sum = 0.0
        destination_identity: dict[str, tuple[float, float]] = {}
        for row in raw_rows:
            d = dict(row)
            pro_com = parse_intlike(d.get(origin_code))
            x = parse_float(d.get(dest_x))
            y = parse_float(d.get(dest_y))
            flow = parse_float(d.get(flow_col))
            if None in (pro_com, x, y, flow):
                raise RuntimeError(f"B1 required field parse failure rowid={d.get('__sqlite_rowid__')}")
            assert pro_com is not None and x is not None and y is not None and flow is not None
            if flow <= 0:
                raise RuntimeError(f"B1 non-positive flow rowid={d.get('__sqlite_rowid__')}: {flow}")
            lon, lat = transformer.transform(x, y)
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise RuntimeError(f"B1 transformed coordinate invalid rowid={d.get('__sqlite_rowid__')}")

            raw_code = str(d.get(dest_code_raw, "") or "").strip() if dest_code_raw else ""
            join_code = str(d.get(dest_code_join, "") or "").strip() if dest_code_join else ""
            dest_label = str(d.get(dest_name, "") or "").strip()
            key_seed = f"{join_code}|{raw_code}|{dest_label}|{x:.3f}|{y:.3f}"
            destination_key = hashlib.sha256(key_seed.encode("utf-8")).hexdigest()[:20]
            coord_pair = (float(x), float(y))
            previous = destination_identity.get(destination_key)
            if previous is not None and previous != coord_pair:
                raise RuntimeError(f"Destination key collision: {destination_key}")
            destination_identity[destination_key] = coord_pair

            row_id = d.get(fid_col) if fid_col else d.get("__sqlite_rowid__")
            row_id_int = parse_intlike(row_id)
            if row_id_int is None:
                raise RuntimeError(f"Invalid B1 row id: {row_id!r}")

            raw_sum += flow
            normalized.append({
                "b1_row_id": row_id_int,
                "origin_PRO_COM": pro_com,
                "origin_COMUNE": str(d.get(origin_name, "") or "") if origin_name else "",
                "dest_code_raw": raw_code,
                "dest_code_join": join_code,
                "dest_COMUNE": dest_label,
                "dest_x_epsg32632": x,
                "dest_y_epsg32632": y,
                "dest_lon": float(lon),
                "dest_lat": float(lat),
                "destination_key": destination_key,
                "Pendolari_raw": flow,
                "daily_factor": B1_DAILY_FACTOR,
                "flow_daily": flow * B1_DAILY_FACTOR,
                "orig_x_epsg32632": parse_float(d.get(orig_x)) if orig_x else None,
                "orig_y_epsg32632": parse_float(d.get(orig_y)) if orig_y else None,
            })

        daily_sum = sum(float(r["flow_daily"]) for r in normalized)
        if abs(raw_sum - EXPECTED_B1_RAW_FLOW) > FLOW_TOL:
            raise RuntimeError(f"B1 raw flow {raw_sum} != expected {EXPECTED_B1_RAW_FLOW}")
        if abs(daily_sum - EXPECTED_B1_DAILY_FLOW) > FLOW_TOL:
            raise RuntimeError(f"B1 daily flow {daily_sum} != expected {EXPECTED_B1_DAILY_FLOW}")

        metadata = {
            "columns": columns,
            "origin_code_field": origin_code,
            "origin_name_field": origin_name,
            "destination_name_field": dest_name,
            "destination_x_field": dest_x,
            "destination_y_field": dest_y,
            "flow_field": flow_col,
            "destination_code_raw_field": dest_code_raw,
            "destination_code_join_field": dest_code_join,
            "fid_field": fid_col,
            "row_count": row_count,
            "raw_flow_sum": raw_sum,
            "daily_factor": B1_DAILY_FACTOR,
            "daily_flow_sum": daily_sum,
            "unique_destinations": len(destination_identity),
        }
        return normalized, metadata
    finally:
        con.close()


# ======================================================================================
# GraphHopper existing-graph server
# ======================================================================================

def find_java(runtime_root: Path) -> Path:
    candidates = sorted(
        p for p in runtime_root.rglob("java.exe") if p.parent.name.lower() == "bin"
    )
    for java in candidates:
        proc = subprocess.run(
            [str(java), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        text = proc.stdout or ""
        match = re.search(r'version\s+"?(\d+)', text)
        if match and int(match.group(1)) >= 17:
            return java
    raise RuntimeError(f"No Java >=17 found under {runtime_root}")


def replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if line.lstrip().startswith(key + ":")]
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one '{key}:' line; found {len(hits)}")
    i = hits[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    escaped = value.replace("'", "''")
    lines[i] = f"{indent}{key}: '{escaped}'"
    return "\n".join(lines) + "\n"


def make_server_config(import_config: Path, graph_dir: Path, run_dir: Path) -> str:
    text = import_config.read_text(encoding="utf-8")
    sentinel = run_dir / "__NO_IMPORT__" / "missing.osm.pbf"
    text = replace_yaml_scalar(text, "datareader.file", sentinel.resolve().as_posix())
    text = replace_yaml_scalar(text, "graph.location", graph_dir.resolve().as_posix())
    if re.search(r"(?m)^server:\s*$", text):
        raise RuntimeError("Candidate import config unexpectedly already contains server block")
    return text + "\n".join([
        "",
        "server:",
        "  application_connectors:",
        "  - type: http",
        f"    port: {APP_PORT}",
        "    bind_host: localhost",
        "    max_request_header_size: 50k",
        "  request_log:",
        "      appenders: []",
        "  admin_connectors:",
        "  - type: http",
        f"    port: {ADMIN_PORT}",
        "    bind_host: localhost",
        "",
    ])


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for_server(proc: subprocess.Popen) -> None:
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"GraphHopper server exited early with code {proc.returncode}")
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


def route_request(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict[str, object]:
    params = [
        ("point", f"{start_lat:.8f},{start_lon:.8f}"),
        ("point", f"{end_lat:.8f},{end_lon:.8f}"),
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "false"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
    ]
    url = f"http://127.0.0.1:{APP_PORT}/route?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Tesi-B1-EXT-GH08/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=ROUTE_TIMEOUT_S) as response:
            body = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        low = body.lower()
        if exc.code in (400, 404) and (
            "not found" in low or "connection" in low or "cannot find" in low or "no path" in low
        ):
            return {"status": "UNREACHABLE", "http_status": int(exc.code), "error": body[:1000]}
        return {"status": "ERROR", "http_status": int(exc.code), "error": body[:1000]}
    except Exception as exc:
        return {"status": "ERROR", "http_status": None, "error": repr(exc)}

    if status != 200:
        return {"status": "ERROR", "http_status": status, "error": f"Unexpected HTTP status {status}"}
    try:
        data = json.loads(body)
        paths = data.get("paths", [])
        if not paths:
            return {"status": "UNREACHABLE", "http_status": 200, "error": "No route path"}
        path = paths[0]
        snapped = path.get("snapped_waypoints", {})
        coordinates = snapped.get("coordinates", [])
        if len(coordinates) != 2:
            return {
                "status": "ERROR",
                "http_status": 200,
                "error": f"Expected 2 snapped waypoints, got {coordinates}",
            }
        snap_start_lon, snap_start_lat = map(float, coordinates[0][:2])
        snap_end_lon, snap_end_lat = map(float, coordinates[1][:2])
        distance_m = float(path["distance"])
        time_s = int(path["time"]) / 1000.0
        weight = float(path["weight"])
        if not (
            math.isfinite(distance_m) and math.isfinite(time_s) and math.isfinite(weight)
            and distance_m > 0 and time_s > 0
        ):
            return {"status": "ERROR", "http_status": 200, "error": "Non-finite/non-positive route metric"}
        return {
            "status": "RAW_PASS",
            "http_status": 200,
            "distance_m": distance_m,
            "time_s": time_s,
            "weight": weight,
            "snap_start_m": haversine_m(start_lon, start_lat, snap_start_lon, snap_start_lat),
            "snap_end_m": haversine_m(end_lon, end_lat, snap_end_lon, snap_end_lat),
            "error": "",
        }
    except Exception as exc:
        return {"status": "ERROR", "http_status": 200, "error": repr(exc)}


# ======================================================================================
# Materialization helpers
# ======================================================================================

def build_internal_costs(
    gamma: dict[str, object],
    crossings: list[dict[str, object]],
    state_node_id: np.ndarray,
    indptr: np.ndarray,
    indices: np.ndarray,
    weights: np.ndarray,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    gamma_rows = list(gamma["rows"])
    by_com = gamma["by_com"]
    assert isinstance(by_com, dict)

    gamma_base_states = [int(x["base_state_id"]) for x in gamma_rows]
    gamma_nodes = sorted({int(x["physical_node_id"]) for x in gamma_rows})
    gamma_node_label = {node: i for i, node in enumerate(gamma_nodes)}

    label_by_state = np.full(len(state_node_id), -1, dtype=np.int32)
    for state_id, raw_node in enumerate(state_node_id):
        label = gamma_node_label.get(int(raw_node))
        if label is not None:
            label_by_state[state_id] = label

    crossing_nodes = {int(x["physical_node_id"]) for x in crossings}
    crossing_states = states_for_nodes(state_node_id, crossing_nodes)
    for node, states in crossing_states.items():
        if not states:
            raise RuntimeError(f"Crossing physical node {node} has no B5 destination states")

    print("  building reverse CSR for exact IE destination semantics...")
    rev_indptr, rev_indices, rev_weights = reverse_csr(indptr, indices, weights)

    access_rows: list[dict[str, object]] = []
    commune_rows: list[dict[str, object]] = []
    total_settled_ie = 0
    total_settled_ei = 0
    internal_unreachable = 0

    for k, crossing in enumerate(crossings, start=1):
        geo = str(crossing["geo_id"])
        gateway = str(crossing["gateway_id"])
        node = int(crossing["physical_node_id"])
        crossing_base = int(crossing["b5_base_state_id"])

        # IE exact: reverse multi-source from all states representing the physical crossing,
        # read distance at each Gamma base-state source.
        ie_result, settled_ie = dijkstra_multi_source_to_state_targets(
            rev_indptr,
            rev_indices,
            rev_weights,
            crossing_states[node],
            gamma_base_states,
        )
        total_settled_ie += settled_ie

        # EI exact: forward from crossing base-state; the first settled state for each Gamma
        # physical node is the canonical min over destination states sharing that node.
        ei_by_label, settled_ei = dijkstra_to_physical_labels(
            indptr,
            indices,
            weights,
            crossing_base,
            label_by_state,
            len(gamma_nodes),
        )
        total_settled_ei += settled_ei

        by_com_dir: dict[tuple[int, str], float] = defaultdict(float)
        by_com_bad: set[tuple[int, str]] = set()

        for access in gamma_rows:
            pro_com = int(access["PRO_COM"])
            access_order = int(access["access_order"])
            base_state = int(access["base_state_id"])
            access_node = int(access["physical_node_id"])
            lam = float(access["lambda_L"])

            ie_time = float(ie_result.get(base_state, math.inf))
            ei_time = float(ei_by_label[gamma_node_label[access_node]])
            for direction, t in (("IE", ie_time), ("EI", ei_time)):
                if not math.isfinite(t):
                    internal_unreachable += 1
                    by_com_bad.add((pro_com, direction))
                else:
                    by_com_dir[(pro_com, direction)] += lam * t

            access_rows.append({
                "gateway_id": gateway,
                "geo_id": geo,
                "crossing_physical_node_id": node,
                "PRO_COM": pro_com,
                "COMUNE": access["COMUNE"],
                "access_order": access_order,
                "access_physical_node_id": access_node,
                "lambda_L": lam,
                "IE_b5_time_s": ie_time,
                "EI_b5_time_s": ei_time,
            })

        for pro_com in sorted(by_com):
            for direction in ("IE", "EI"):
                key = (int(pro_com), direction)
                t = math.inf if key in by_com_bad else float(by_com_dir[key])
                commune_rows.append({
                    "gateway_id": gateway,
                    "geo_id": geo,
                    "crossing_physical_node_id": node,
                    "PRO_COM": int(pro_com),
                    "direction": direction,
                    "internal_lambda_weighted_time_s": t,
                    "aggregation": "ONE_SIDED_LAMBDA_WEIGHTED_EXP_REL_300",
                })

        print(
            f"  crossing {k:02d}/{len(crossings)} {geo:<10} {gateway:<6} "
            f"settled IE={settled_ie:,} EI={settled_ei:,}"
        )

    diagnostics = {
        "internal_access_rows": len(access_rows),
        "internal_commune_rows": len(commune_rows),
        "internal_unreachable_access_direction": internal_unreachable,
        "total_settled_ie": total_settled_ie,
        "total_settled_ei": total_settled_ei,
        "unique_gamma_physical_nodes": len(gamma_nodes),
    }
    return access_rows, commune_rows, diagnostics


def unique_destinations(b1_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[str, dict[str, object]] = {}
    for row in b1_rows:
        key = str(row["destination_key"])
        candidate = {
            "destination_key": key,
            "dest_code_raw": row["dest_code_raw"],
            "dest_code_join": row["dest_code_join"],
            "dest_COMUNE": row["dest_COMUNE"],
            "dest_x_epsg32632": row["dest_x_epsg32632"],
            "dest_y_epsg32632": row["dest_y_epsg32632"],
            "dest_lon": row["dest_lon"],
            "dest_lat": row["dest_lat"],
        }
        previous = by_key.get(key)
        if previous is not None and previous != candidate:
            raise RuntimeError(f"Inconsistent destination key {key}")
        by_key[key] = candidate
    return sorted(by_key.values(), key=lambda x: (str(x["dest_COMUNE"]), str(x["destination_key"])))


def evaluate_external_task(
    destination: dict[str, object],
    crossing: dict[str, object],
    direction: str,
) -> dict[str, object]:
    if direction == "IE":
        start_lat, start_lon = float(crossing["lat"]), float(crossing["lon"])
        end_lat, end_lon = float(destination["dest_lat"]), float(destination["dest_lon"])
    elif direction == "EI":
        start_lat, start_lon = float(destination["dest_lat"]), float(destination["dest_lon"])
        end_lat, end_lon = float(crossing["lat"]), float(crossing["lon"])
    else:
        raise ValueError(direction)

    raw = route_request(start_lat, start_lon, end_lat, end_lon)
    status = str(raw.get("status"))
    crossing_snap_m: float | None = None
    destination_snap_m: float | None = None

    if status == "RAW_PASS":
        if direction == "IE":
            crossing_snap_m = float(raw["snap_start_m"])
            destination_snap_m = float(raw["snap_end_m"])
        else:
            destination_snap_m = float(raw["snap_start_m"])
            crossing_snap_m = float(raw["snap_end_m"])
        if crossing_snap_m <= MAX_CROSSING_SNAP_M and destination_snap_m <= MAX_DESTINATION_SNAP_M:
            status = "PASS"
        else:
            status = "SNAP_FLAG"

    return {
        "destination_key": destination["destination_key"],
        "dest_code_raw": destination["dest_code_raw"],
        "dest_code_join": destination["dest_code_join"],
        "dest_COMUNE": destination["dest_COMUNE"],
        "dest_lon": destination["dest_lon"],
        "dest_lat": destination["dest_lat"],
        "gateway_id": crossing["gateway_id"],
        "geo_id": crossing["geo_id"],
        "crossing_lon": crossing["lon"],
        "crossing_lat": crossing["lat"],
        "direction": direction,
        "external_time_s": raw.get("time_s"),
        "external_distance_m": raw.get("distance_m"),
        "external_weight": raw.get("weight"),
        "crossing_snap_m": crossing_snap_m,
        "destination_snap_m": destination_snap_m,
        "http_status": raw.get("http_status"),
        "status": status,
        "error": raw.get("error", ""),
    }


def build_external_routes(
    destinations: list[dict[str, object]],
    crossings: list[dict[str, object]],
    workers: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    tasks = [
        (dest, crossing, direction)
        for dest in destinations
        for crossing in crossings
        for direction in ("IE", "EI")
    ]
    print(f"  unique destinations      = {len(destinations):,}")
    print(f"  physical crossings       = {len(crossings):,}")
    print(f"  GraphHopper route calls  = {len(tasks):,}")
    print(f"  HTTP workers             = {workers}")

    out: list[dict[str, object]] = []
    started = time.time()
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(evaluate_external_task, dest, crossing, direction): (
                str(dest["destination_key"]), str(crossing["geo_id"]), direction
            )
            for dest, crossing, direction in tasks
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:
                destination_key, geo_id, direction = key
                row = {
                    "destination_key": destination_key,
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
            out.append(row)
            completed += 1
            if completed % 250 == 0 or completed == len(tasks):
                elapsed = max(time.time() - started, 1e-9)
                rate = completed / elapsed
                remain = (len(tasks) - completed) / max(rate, 1e-9)
                with PRINT_LOCK:
                    print(
                        f"  GH progress {completed:,}/{len(tasks):,} "
                        f"({100.0*completed/len(tasks):5.1f}%) "
                        f"rate={rate:6.1f}/s ETA={remain/60:6.1f} min"
                    )

    out.sort(key=lambda r: (str(r["destination_key"]), str(r["geo_id"]), str(r["direction"])))
    counts: dict[str, int] = defaultdict(int)
    max_crossing_snap = 0.0
    max_dest_snap = 0.0
    for row in out:
        counts[str(row["status"])] += 1
        if row["crossing_snap_m"] is not None:
            max_crossing_snap = max(max_crossing_snap, float(row["crossing_snap_m"]))
        if row["destination_snap_m"] is not None:
            max_dest_snap = max(max_dest_snap, float(row["destination_snap_m"]))

    diagnostics = {
        "tasks": len(tasks),
        "status_counts": dict(sorted(counts.items())),
        "max_crossing_snap_m": max_crossing_snap,
        "max_destination_snap_m": max_dest_snap,
        "elapsed_s": time.time() - started,
    }
    return out, diagnostics


def select_routes(
    b1_rows: list[dict[str, object]],
    crossings: list[dict[str, object]],
    internal_commune_rows: list[dict[str, object]],
    external_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    internal_lookup: dict[tuple[int, str, str], float] = {}
    for row in internal_commune_rows:
        internal_lookup[(int(row["PRO_COM"]), str(row["geo_id"]), str(row["direction"]))] = float(
            row["internal_lambda_weighted_time_s"]
        )
    external_lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in external_rows:
        key = (str(row["destination_key"]), str(row["geo_id"]), str(row["direction"]))
        if key in external_lookup:
            raise RuntimeError(f"Duplicate external route cache key: {key}")
        external_lookup[key] = row

    crossing_by_geo = {str(x["geo_id"]): x for x in crossings}
    ie_rows: list[dict[str, object]] = []
    ei_rows: list[dict[str, object]] = []
    unreachable = {"IE": 0, "EI": 0}
    tie_rows = {"IE": 0, "EI": 0}
    cross_gateway_ties = {"IE": 0, "EI": 0}
    min_valid_candidates = {"IE": len(crossings), "EI": len(crossings)}

    for relation in b1_rows:
        pro_com = int(relation["origin_PRO_COM"])
        dest_key = str(relation["destination_key"])
        for direction in ("IE", "EI"):
            candidates: list[dict[str, object]] = []
            for crossing in crossings:
                geo = str(crossing["geo_id"])
                internal_t = internal_lookup.get((pro_com, geo, direction), math.inf)
                external = external_lookup.get((dest_key, geo, direction))
                if external is None or str(external["status"]) != "PASS" or not math.isfinite(internal_t):
                    continue
                external_t = float(external["external_time_s"])
                combined = internal_t + external_t
                candidates.append({
                    "geo_id": geo,
                    "gateway_id": str(crossing["gateway_id"]),
                    "internal_time_s": internal_t,
                    "external_time_s": external_t,
                    "combined_time_s": combined,
                    "external_distance_m": float(external["external_distance_m"]),
                    "crossing_snap_m": float(external["crossing_snap_m"]),
                    "destination_snap_m": float(external["destination_snap_m"]),
                })

            min_valid_candidates[direction] = min(min_valid_candidates[direction], len(candidates))
            if not candidates:
                unreachable[direction] += 1
                selected = {
                    **relation,
                    "direction": direction,
                    "selected_geo_id": "",
                    "selected_gateway_id": "",
                    "internal_lambda_weighted_time_s": None,
                    "external_time_s": None,
                    "combined_time_s": None,
                    "external_distance_m": None,
                    "crossing_snap_m": None,
                    "destination_snap_m": None,
                    "valid_crossing_candidates": 0,
                    "tie_count": 0,
                    "tie_gateway_count": 0,
                    "second_best_combined_time_s": None,
                    "gap_to_second_s": None,
                    "route_status": "UNREACHABLE",
                }
            else:
                candidates.sort(key=lambda x: (float(x["combined_time_s"]), str(x["geo_id"])))
                best = candidates[0]
                best_t = float(best["combined_time_s"])
                tied = [x for x in candidates if abs(float(x["combined_time_s"]) - best_t) <= NUMERIC_TIE_TOL_S]
                tied_gateways = {str(x["gateway_id"]) for x in tied}
                if len(tied) > 1:
                    tie_rows[direction] += 1
                if len(tied_gateways) > 1:
                    cross_gateway_ties[direction] += 1
                second = candidates[1] if len(candidates) > 1 else None
                selected = {
                    **relation,
                    "direction": direction,
                    "selected_geo_id": best["geo_id"],
                    "selected_gateway_id": best["gateway_id"],
                    "internal_lambda_weighted_time_s": best["internal_time_s"],
                    "external_time_s": best["external_time_s"],
                    "combined_time_s": best["combined_time_s"],
                    "external_distance_m": best["external_distance_m"],
                    "crossing_snap_m": best["crossing_snap_m"],
                    "destination_snap_m": best["destination_snap_m"],
                    "valid_crossing_candidates": len(candidates),
                    "tie_count": len(tied),
                    "tie_gateway_count": len(tied_gateways),
                    "second_best_combined_time_s": (
                        float(second["combined_time_s"]) if second is not None else None
                    ),
                    "gap_to_second_s": (
                        float(second["combined_time_s"]) - best_t if second is not None else None
                    ),
                    "route_status": "PASS",
                }
            (ie_rows if direction == "IE" else ei_rows).append(selected)

    diagnostics = {
        "IE_unreachable": unreachable["IE"],
        "EI_unreachable": unreachable["EI"],
        "IE_numeric_tie_rows": tie_rows["IE"],
        "EI_numeric_tie_rows": tie_rows["EI"],
        "IE_cross_gateway_numeric_ties": cross_gateway_ties["IE"],
        "EI_cross_gateway_numeric_ties": cross_gateway_ties["EI"],
        "IE_min_valid_crossing_candidates": min_valid_candidates["IE"],
        "EI_min_valid_crossing_candidates": min_valid_candidates["EI"],
    }
    return ie_rows, ei_rows, diagnostics


def aggregate_flow_attribution(
    ie_rows: list[dict[str, object]],
    ei_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    crossing_acc: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"rows": 0.0, "raw": 0.0, "daily": 0.0}
    )
    gateway_acc: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"rows": 0.0, "raw": 0.0, "daily": 0.0}
    )
    for row in ie_rows + ei_rows:
        if row["route_status"] != "PASS":
            continue
        direction = str(row["direction"])
        geo = str(row["selected_geo_id"])
        gateway = str(row["selected_gateway_id"])
        raw = float(row["Pendolari_raw"])
        daily = float(row["flow_daily"])
        c = crossing_acc[(direction, gateway, geo)]
        c["rows"] += 1
        c["raw"] += raw
        c["daily"] += daily
        g = gateway_acc[(direction, gateway)]
        g["rows"] += 1
        g["raw"] += raw
        g["daily"] += daily

    crossing_rows = [
        {
            "direction": direction,
            "gateway_id": gateway,
            "geo_id": geo,
            "b1_rows": int(v["rows"]),
            "Pendolari_raw_sum": v["raw"],
            "flow_daily_sum": v["daily"],
        }
        for (direction, gateway, geo), v in sorted(crossing_acc.items())
    ]
    gateway_rows = [
        {
            "direction": direction,
            "gateway_id": gateway,
            "b1_rows": int(v["rows"]),
            "Pendolari_raw_sum": v["raw"],
            "flow_daily_sum": v["daily"],
        }
        for (direction, gateway), v in sorted(gateway_acc.items())
    ]
    return crossing_rows, gateway_rows


def endpoint_snap_rows(external_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in external_rows:
        out.append({
            "destination_key": row["destination_key"],
            "dest_COMUNE": row["dest_COMUNE"],
            "gateway_id": row["gateway_id"],
            "geo_id": row["geo_id"],
            "direction": row["direction"],
            "crossing_snap_m": row["crossing_snap_m"],
            "destination_snap_m": row["destination_snap_m"],
            "crossing_snap_threshold_m": MAX_CROSSING_SNAP_M,
            "destination_snap_threshold_m": MAX_DESTINATION_SNAP_M,
            "route_status": row["status"],
        })
    return out


# ======================================================================================
# Self-tests (no project files, no server)
# ======================================================================================

def helper_self_tests() -> None:
    # Graph: 0->1 (2), 0->2 (10), 1->2 (3), 2->3 (4)
    indptr = np.array([0, 2, 3, 4, 4], dtype=np.int32)
    indices = np.array([1, 2, 2, 3], dtype=np.int32)
    weights = np.array([2.0, 10.0, 3.0, 4.0], dtype=np.float64)
    r_indptr, r_indices, r_weights = reverse_csr(indptr, indices, weights)

    # Exact forward 0 -> target states {2,3}: target 2 must be 5, target 3 = 9.
    result, _ = dijkstra_multi_source_to_state_targets(
        indptr, indices, weights, [0], [2, 3]
    )
    if abs(result[2] - 5.0) > 1e-12 or abs(result[3] - 9.0) > 1e-12:
        raise AssertionError("state-target Dijkstra self-test failed")

    # Reverse multisource from physical-destination states {2,3}; source 0 sees min=5.
    rev_result, _ = dijkstra_multi_source_to_state_targets(
        r_indptr, r_indices, r_weights, [2, 3], [0, 1]
    )
    if abs(rev_result[0] - 5.0) > 1e-12 or abs(rev_result[1] - 3.0) > 1e-12:
        raise AssertionError("reverse multisource self-test failed")

    labels = np.array([-1, -1, 0, 1], dtype=np.int32)
    physical, _ = dijkstra_to_physical_labels(indptr, indices, weights, 0, labels, 2)
    if abs(float(physical[0]) - 5.0) > 1e-12 or abs(float(physical[1]) - 9.0) > 1e-12:
        raise AssertionError("physical-label Dijkstra self-test failed")


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--http-workers", type=int, default=DEFAULT_HTTP_WORKERS)
    parser.add_argument(
        "--self-test-only", action="store_true",
        help="Run helper tests only; do not read project files or start GraphHopper.",
    )
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_08_HELPER_SELF_TESTS = PASS")
        return 0
    if args.http_workers < 1 or args.http_workers > 16:
        raise ValueError("--http-workers must be between 1 and 16")

    root = Path(args.root)
    b5_dir = root / Path(B5_DIR_REL)
    gh07_dir = root / Path(GH07_DIR_REL)

    paths = {
        "b5_time": b5_dir / B5_TIME_NAME,
        "b5_base_nodes": b5_dir / B5_BASE_NODES_NAME,
        "b5_state_node": b5_dir / B5_STATE_NODE_NAME,
        "gamma_csv": root / Path(GAMMA_REL),
        "gh07_mapping": gh07_dir / GH07_MAPPING_NAME,
        "gh07_summary": gh07_dir / GH07_SUMMARY_NAME,
        "gh07_manifest": gh07_dir / GH07_MANIFEST_NAME,
        "gh06_manifest": root / Path(GH06_MANIFEST_REL),
        "gh_jar": root / Path(GH_JAR_REL),
        "profile_config": root / Path(PROFILE_CONFIG_REL),
        "profile_model": root / Path(PROFILE_MODEL_REL),
        "base_gpkg": root / Path(BASE_GPKG_REL),
    }
    expected_hashes = {
        "b5_time": B5_TIME_SHA256,
        "b5_base_nodes": B5_BASE_NODES_SHA256,
        "b5_state_node": B5_STATE_NODE_SHA256,
        "gamma_csv": GAMMA_SHA256,
        "gh07_mapping": GH07_MAPPING_SHA256,
        "gh07_summary": GH07_SUMMARY_SHA256,
        "gh07_manifest": GH07_MANIFEST_SHA256,
        "gh06_manifest": GH06_MANIFEST_SHA256,
        "gh_jar": GH_JAR_SHA256,
        "profile_config": PROFILE_CONFIG_SHA256,
        "profile_model": PROFILE_MODEL_SHA256,
    }

    final_graph = root / Path(FINAL_GRAPH_REL)
    runtime_root = root / Path(RUNTIME_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 08 — HYBRID ROUTING MATERIALIZATION")
    print("=" * 124)
    print("B5 FROZEN + EXISTING GH ITALY / 49 PHYSICAL CROSSINGS / 2,895 B1 / IE+EI SEPARATE")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(f"Unexpected staging exists: {staging}")

    proc: subprocess.Popen | None = None
    server_log_handle = None
    base_gpkg_before_hash = ""
    graph_before: list[dict[str, object]] = []
    graph_manifest_path: Path | None = None
    stop_status = "NOT_STARTED"

    try:
        # ------------------------------------------------------------------
        # A. Strict preflight / identities
        # ------------------------------------------------------------------
        print("A. STRICT INPUT / EVIDENCE IDENTITY")
        for name, expected in expected_hashes.items():
            strict_hash_check(name, paths[name], expected)
        if not paths["base_gpkg"].is_file():
            raise FileNotFoundError(paths["base_gpkg"])
        if not final_graph.is_dir():
            raise FileNotFoundError(final_graph)

        base_gpkg_before_hash = sha256(paths["base_gpkg"])
        graph_manifest_path, graph_manifest = find_graph_manifest(root)
        graph_before = graph_inventory(final_graph)
        if normalized_inventory(graph_before) != normalized_inventory(graph_manifest.get("files", [])):
            raise RuntimeError("Imported Italy graph differs from frozen graph manifest")
        print(f"base_gpkg SHA256           INFO  {base_gpkg_before_hash}")
        print(f"graph manifest             PASS  {sha256(graph_manifest_path)}")
        print(f"graph files                = {len(graph_before)}")
        print(f"graph size GiB             = {sum(int(x['size_bytes']) for x in graph_before)/(1024**3):.3f}")
        print("helper self-tests           PASS")

        # Evidence semantic checks.
        gh07_summary = json.loads(paths["gh07_summary"].read_text(encoding="utf-8"))
        if gh07_summary.get("verdict") != "PASS":
            raise RuntimeError("GH07 summary verdict is not PASS")
        if gh07_summary.get("next_gate") != "B1_HYBRID_ROUTING_MATERIALIZATION":
            raise RuntimeError(f"Unexpected GH07 next_gate: {gh07_summary.get('next_gate')}")
        print("GH07 semantic chain         PASS")

        staging.mkdir(parents=True, exist_ok=False)

        # ------------------------------------------------------------------
        # B. Load canonical B5/Gamma/GH07 + B1
        # ------------------------------------------------------------------
        print()
        print("B. CANONICAL INPUT MATERIALIZATION")
        indptr, indices, weights, _ = load_csr_npz(paths["b5_time"])
        base_nodes = np.load(paths["b5_base_nodes"], mmap_mode="r", allow_pickle=False)
        state_node_id = np.load(paths["b5_state_node"], mmap_mode="r", allow_pickle=False)
        if base_nodes.shape != (EXPECTED_B5_BASE_STATES,):
            raise RuntimeError(f"base_nodes shape {base_nodes.shape}")
        if state_node_id.shape != (EXPECTED_B5_TOTAL_STATES,):
            raise RuntimeError(f"state_node_id shape {state_node_id.shape}")
        if not np.array_equal(base_nodes, state_node_id[:EXPECTED_B5_BASE_STATES]):
            raise RuntimeError("B5 base-state node invariant failed")

        gamma = load_gamma(paths["gamma_csv"], base_nodes, state_node_id)
        crossings = load_crossings(paths["gh07_mapping"])
        b1_rows, b1_meta = load_b1_relations(paths["base_gpkg"])
        gamma_by_com = gamma["by_com"]
        assert isinstance(gamma_by_com, dict)
        missing_origins = sorted({int(r["origin_PRO_COM"]) for r in b1_rows} - set(gamma_by_com))
        if missing_origins:
            raise RuntimeError(f"B1 origins absent from Gamma: {missing_origins}")

        print(f"B5 states                  = {len(state_node_id):,}")
        print(f"B5 transitions             = {len(indices):,}")
        print(f"Gamma rows                 = {len(gamma['rows']):,}")
        print(f"Gamma communes             = {len(gamma_by_com):,}")
        print(f"physical crossings         = {len(crossings):,}")
        print(f"modelling gateways         = {len({x['gateway_id'] for x in crossings}):,}")
        print(f"B1 relations               = {len(b1_rows):,}")
        print(f"B1 raw flow                = {b1_meta['raw_flow_sum']:.5f}")
        print(f"B1 daily factor            = {B1_DAILY_FACTOR:.5f}")
        print(f"B1 daily IE/EI each        = {b1_meta['daily_flow_sum']:.5f}")
        print(f"unique external dest       = {b1_meta['unique_destinations']:,}")

        b1_normalized_path = staging / B1_NORMALIZED_CSV
        write_csv(b1_normalized_path, b1_rows)

        # ------------------------------------------------------------------
        # C. Exact internal B5 cost materialization
        # ------------------------------------------------------------------
        print()
        print("C. EXACT INTERNAL B5 CROSSING COSTS")
        print("  IE = Gamma base-state source -> min B5 state at crossing")
        print("  EI = crossing base-state -> min B5 state at Gamma physical node")
        print("  commune aggregation = one-sided lambda weighted EXP_REL_300")
        internal_access_rows, internal_commune_rows, internal_diag = build_internal_costs(
            gamma, crossings, state_node_id, indptr, indices, weights
        )
        internal_access_path = staging / INTERNAL_ACCESS_CSV
        internal_commune_path = staging / INTERNAL_COMMUNE_CSV
        write_csv(internal_access_path, internal_access_rows)
        write_csv(internal_commune_path, internal_commune_rows)
        print(f"internal access rows        = {len(internal_access_rows):,}")
        print(f"internal commune rows       = {len(internal_commune_rows):,}")
        print(f"internal unreachable        = {internal_diag['internal_unreachable_access_direction']:,}")

        # ------------------------------------------------------------------
        # D. Start existing GraphHopper graph safely
        # ------------------------------------------------------------------
        print()
        print("D. SAFE EXISTING-GRAPH SERVER START")
        if not port_is_free(APP_PORT):
            raise RuntimeError(f"Application port {APP_PORT} already in use")
        if not port_is_free(ADMIN_PORT):
            raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")
        java_exe = find_java(runtime_root)
        server_config_path = staging / SERVER_CONFIG
        server_config_path.write_text(
            make_server_config(paths["profile_config"], final_graph, staging), encoding="utf-8"
        )
        server_log_path = staging / SERVER_LOG
        server_log_handle = server_log_path.open("w", encoding="utf-8", errors="replace")
        cmd = [
            str(java_exe),
            f"-Xms{SERVER_XMS_MIB}m",
            f"-Xmx{SERVER_XMX_GIB}g",
            "-XX:+UseParallelGC",
            "-jar",
            str(paths["gh_jar"]),
            "server",
            str(server_config_path),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=staging,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_server(proc)
        print(f"Java                       = {java_exe}")
        print(f"application port           = {APP_PORT}")
        print("bind host                  = localhost")
        print("national PBF passed        = NO")
        print("SERVER_LOAD                = PASS")

        # ------------------------------------------------------------------
        # E. Full external crossing cost cache
        # ------------------------------------------------------------------
        print()
        print("E. FULL EXTERNAL CROSSING ROUTE CACHE")
        destinations = unique_destinations(b1_rows)
        external_rows, external_diag = build_external_routes(
            destinations, crossings, args.http_workers
        )
        external_path = staging / EXTERNAL_ROUTE_CSV
        endpoint_path = staging / ENDPOINT_SNAP_CSV
        write_csv(external_path, external_rows)
        write_csv(endpoint_path, endpoint_snap_rows(external_rows))
        print(f"route status counts         = {external_diag['status_counts']}")
        print(f"max crossing snap m         = {external_diag['max_crossing_snap_m']:.3f}")
        print(f"max destination snap m      = {external_diag['max_destination_snap_m']:.3f}")

        # A technical ERROR or SNAP_FLAG means at least one physical-crossing candidate was
        # not evaluated reliably, so the minimum-over-49 contract is not fully trustworthy.
        external_technical_failures = sum(
            1 for r in external_rows if str(r["status"]) in {"ERROR", "SNAP_FLAG"}
        )

        # ------------------------------------------------------------------
        # F. Physical-crossing minimum + gateway aggregation
        # ------------------------------------------------------------------
        print()
        print("F. B1 PHYSICAL-CROSSING MINIMIZATION / GATEWAY ATTRIBUTION")
        ie_rows, ei_rows, selection_diag = select_routes(
            b1_rows, crossings, internal_commune_rows, external_rows
        )
        ie_path = staging / IE_ROUTING_CSV
        ei_path = staging / EI_ROUTING_CSV
        write_csv(ie_path, ie_rows)
        write_csv(ei_path, ei_rows)

        crossing_flow_rows, gateway_flow_rows = aggregate_flow_attribution(ie_rows, ei_rows)
        crossing_flow_path = staging / CROSSING_FLOW_CSV
        gateway_flow_path = staging / GATEWAY_FLOW_CSV
        write_csv(
            crossing_flow_path,
            crossing_flow_rows,
            fieldnames=[
                "direction", "gateway_id", "geo_id", "b1_rows",
                "Pendolari_raw_sum", "flow_daily_sum",
            ],
        )
        write_csv(
            gateway_flow_path,
            gateway_flow_rows,
            fieldnames=[
                "direction", "gateway_id", "b1_rows",
                "Pendolari_raw_sum", "flow_daily_sum",
            ],
        )

        ie_pass = sum(r["route_status"] == "PASS" for r in ie_rows)
        ei_pass = sum(r["route_status"] == "PASS" for r in ei_rows)
        print(f"IE routed                  = {ie_pass:,}/{EXPECTED_B1_ROWS:,}")
        print(f"EI routed                  = {ei_pass:,}/{EXPECTED_B1_ROWS:,}")
        print(f"IE unreachable             = {selection_diag['IE_unreachable']:,}")
        print(f"EI unreachable             = {selection_diag['EI_unreachable']:,}")
        print(f"IE min valid candidates    = {selection_diag['IE_min_valid_crossing_candidates']}")
        print(f"EI min valid candidates    = {selection_diag['EI_min_valid_crossing_candidates']}")
        print(f"IE cross-gateway ties      = {selection_diag['IE_cross_gateway_numeric_ties']}")
        print(f"EI cross-gateway ties      = {selection_diag['EI_cross_gateway_numeric_ties']}")

        # Flow conservation on routed output.
        ie_daily = sum(float(r["flow_daily"]) for r in ie_rows if r["route_status"] == "PASS")
        ei_daily = sum(float(r["flow_daily"]) for r in ei_rows if r["route_status"] == "PASS")
        print(f"IE routed daily flow       = {ie_daily:.5f}")
        print(f"EI routed daily flow       = {ei_daily:.5f}")

        # ------------------------------------------------------------------
        # G. Server shutdown + byte-integrity
        # ------------------------------------------------------------------
        print()
        print("G. SHUTDOWN / BYTE-INTEGRITY")
        stop_status = stop_server(proc)
        proc = None
        if server_log_handle is not None:
            server_log_handle.close()
            server_log_handle = None
        graph_after = graph_inventory(final_graph)
        graph_unchanged = normalized_inventory(graph_before) == normalized_inventory(graph_after)
        base_gpkg_after_hash = sha256(paths["base_gpkg"])
        base_gpkg_unchanged = base_gpkg_after_hash == base_gpkg_before_hash
        if not graph_unchanged:
            raise RuntimeError("Italy graph files changed during GH08")
        if not base_gpkg_unchanged:
            raise RuntimeError("base_territoriale_fvg.gpkg changed during GH08")
        for name in ("b5_time", "b5_base_nodes", "b5_state_node", "gamma_csv", "gh07_mapping"):
            if sha256(paths[name]) != expected_hashes[name]:
                raise RuntimeError(f"Frozen input changed during GH08: {name}")
        print(f"server shutdown            = {stop_status}")
        print("Italy graph unchanged      = PASS")
        print("base GPKG unchanged        = PASS")
        print("frozen FVG inputs          = PASS")

        # ------------------------------------------------------------------
        # H. Gate verdict / summary / manifest
        # ------------------------------------------------------------------
        blocking_reasons: list[str] = []
        if int(internal_diag["internal_unreachable_access_direction"]) != 0:
            blocking_reasons.append("INTERNAL_B5_UNREACHABLE")
        if external_technical_failures != 0:
            blocking_reasons.append("EXTERNAL_TECHNICAL_OR_SNAP_FAILURE")
        if selection_diag["IE_unreachable"] != 0:
            blocking_reasons.append("IE_RELATION_UNREACHABLE")
        if selection_diag["EI_unreachable"] != 0:
            blocking_reasons.append("EI_RELATION_UNREACHABLE")
        if abs(ie_daily - EXPECTED_B1_DAILY_FLOW) > FLOW_TOL:
            blocking_reasons.append("IE_FLOW_NOT_CONSERVED")
        if abs(ei_daily - EXPECTED_B1_DAILY_FLOW) > FLOW_TOL:
            blocking_reasons.append("EI_FLOW_NOT_CONSERVED")

        verdict = "PASS" if not blocking_reasons else "NOT_READY"
        next_gate = (
            "B1_SELECTED_ROUTE_DIAGNOSTICS_FINAL_GATE"
            if verdict == "PASS"
            else "REVIEW_GH08_BLOCKING_DIAGNOSTICS"
        )

        summary = {
            "schema": "B1_EXT_GH_08_HYBRID_ROUTING_MATERIALIZATION_SUMMARY_V01",
            "verdict": verdict,
            "blocking_reasons": blocking_reasons,
            "contract": {
                "internal_router": "B5_FROZEN",
                "external_router": "GRAPHHOPPER_11_EXISTING_GRAPH",
                "composition": "PHYSICAL_CROSSING_MIN_COMBINED_TIME",
                "fvg_access_aggregation": "ONE_SIDED_LAMBDA_WEIGHTED_EXP_REL_300",
                "IE_EI_separate": True,
                "gateway_after_crossing_minimization": True,
                "nearest_crossing_heuristic": False,
                "end_to_end_graphhopper": False,
            },
            "b1": {
                **b1_meta,
                "expected_rows": EXPECTED_B1_ROWS,
                "expected_raw_flow": EXPECTED_B1_RAW_FLOW,
                "expected_daily_flow_each_direction": EXPECTED_B1_DAILY_FLOW,
            },
            "crossings": {
                "physical_crossings": len(crossings),
                "modelling_gateways": len({x["gateway_id"] for x in crossings}),
            },
            "internal": internal_diag,
            "external": {
                **external_diag,
                "technical_or_snap_failures": external_technical_failures,
                "unreachable_candidate_routes": sum(
                    1 for r in external_rows if str(r["status"]) == "UNREACHABLE"
                ),
            },
            "selection": {
                **selection_diag,
                "IE_routed": ie_pass,
                "EI_routed": ei_pass,
                "IE_routed_daily_flow": ie_daily,
                "EI_routed_daily_flow": ei_daily,
                "crossing_flow_rows": len(crossing_flow_rows),
                "gateway_flow_rows": len(gateway_flow_rows),
            },
            "integrity": {
                "italy_graph_byte_identical_after_run": True,
                "base_gpkg_byte_identical_after_run": True,
                "frozen_fvg_inputs_unchanged": True,
            },
            "scope_guardrail": {
                "pbf_import": "NOT_STARTED",
                "frozen_fvg_artifacts_modified": False,
                "gravity_reopened": False,
                "selected_route_external_subgraph_diagnostics": "NOT_STARTED",
                "ignored_restriction_intersection_audit": "NOT_STARTED",
            },
            "next_gate": next_gate,
        }
        summary_path = staging / SUMMARY_JSON
        write_json(summary_path, summary)

        outputs = [
            b1_normalized_path,
            internal_access_path,
            internal_commune_path,
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
            "schema": "B1_EXT_GH_08_HYBRID_ROUTING_MATERIALIZATION_MANIFEST_V01",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "inputs": {
                name: {
                    "path": str(path),
                    "sha256": sha256(path),
                    "expected_sha256": expected_hashes.get(name),
                }
                for name, path in paths.items()
            },
            "graph_manifest": {
                "path": str(graph_manifest_path),
                "sha256": EXPECTED_GRAPH_MANIFEST_SHA256,
            },
            "outputs": [
                {"filename": p.name, "size_bytes": p.stat().st_size, "sha256": sha256(p)}
                for p in outputs
            ],
            "blocking_reasons": blocking_reasons,
            "next_gate": next_gate,
        }
        manifest_path = staging / MANIFEST_JSON
        write_json(manifest_path, manifest)

        staging.rename(final_dir)

        print()
        print("=" * 124)
        print(f"B1_EXT_GH_08_HYBRID_ROUTING_MATERIALIZATION = {verdict}")
        print(f"B1_RELATIONS = {EXPECTED_B1_ROWS}")
        print(f"UNIQUE_EXTERNAL_DESTINATIONS = {b1_meta['unique_destinations']}")
        print(f"PHYSICAL_CROSSINGS = {len(crossings)}")
        print(f"MODELLING_GATEWAYS = {len({x['gateway_id'] for x in crossings})}")
        print(f"IE_ROUTED = {ie_pass}/{EXPECTED_B1_ROWS}")
        print(f"EI_ROUTED = {ei_pass}/{EXPECTED_B1_ROWS}")
        print(f"IE_UNREACHABLE = {selection_diag['IE_unreachable']}")
        print(f"EI_UNREACHABLE = {selection_diag['EI_unreachable']}")
        print(f"EXTERNAL_TECHNICAL_OR_SNAP_FAILURES = {external_technical_failures}")
        print(f"EXTERNAL_UNREACHABLE_CANDIDATES = {sum(1 for r in external_rows if str(r['status']) == 'UNREACHABLE')}")
        print(f"IE_DAILY_FLOW = {ie_daily:.5f}")
        print(f"EI_DAILY_FLOW = {ei_daily:.5f}")
        print(f"EXPECTED_DAILY_FLOW_EACH = {EXPECTED_B1_DAILY_FLOW:.5f}")
        print(f"CROSS_GATEWAY_NUMERIC_TIES_IE = {selection_diag['IE_cross_gateway_numeric_ties']}")
        print(f"CROSS_GATEWAY_NUMERIC_TIES_EI = {selection_diag['EI_cross_gateway_numeric_ties']}")
        print("ITALY_GRAPH_BYTE_IDENTICAL_AFTER_RUN = YES")
        print("BASE_GPKG_BYTE_IDENTICAL_AFTER_RUN = YES")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print("PBF_IMPORT = NOT_STARTED")
        print("GRAVITY_REOPENED = NO")
        print("SELECTED_ROUTE_EXTERNAL_SUBGRAPH_DIAGNOSTICS = NOT_STARTED")
        print("IGNORED_RESTRICTION_INTERSECTION_AUDIT = NOT_STARTED")
        print(f"NEXT_GATE = {next_gate}")
        print(f"{IE_ROUTING_CSV} SHA256 = {sha256(final_dir / IE_ROUTING_CSV)}")
        print(f"{EI_ROUTING_CSV} SHA256 = {sha256(final_dir / EI_ROUTING_CSV)}")
        print(f"{GATEWAY_FLOW_CSV} SHA256 = {sha256(final_dir / GATEWAY_FLOW_CSV)}")
        print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
        print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
        print("=== RUN COMPLETATA ===")
        return 0 if verdict == "PASS" else 2

    except Exception as exc:
        stop_status = stop_server(proc)
        proc = None
        if server_log_handle is not None:
            server_log_handle.close()
            server_log_handle = None
        print()
        print("=" * 124)
        print("B1_EXT_GH_08_HYBRID_ROUTING_MATERIALIZATION = FAIL")
        print(f"ERROR = {exc}")
        print(f"SERVER_SHUTDOWN = {stop_status}")
        print(f"DIAGNOSTIC_STAGING = {staging if staging.exists() else 'NONE'}")
        print("PBF_IMPORT = NOT_STARTED")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print("GRAVITY_REOPENED = NO")
        print("NEXT_GATE = REVIEW_GH08_FAILURE")
        print("=== RUN COMPLETATA ===")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
