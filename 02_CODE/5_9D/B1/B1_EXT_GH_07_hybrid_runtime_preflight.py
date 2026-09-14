#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import heapq
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

# ======================================================================================
# B1-EXT-GH 07 — HYBRID ROUTING RUNTIME / INTERFACE PREFLIGHT
#
# READ-ONLY on all frozen/canonical inputs.
# NO GraphHopper server start.
# NO PBF import.
# NO full 2,895 B1 routing.
# NO gateway assignment.
# NO frozen artifact modification.
#
# Purpose:
#   1) verify the exact frozen B5/Gamma interface used by hybrid routing;
#   2) materialize the 49 Veneto physical-crossing -> B5 runtime mapping;
#   3) run a minimal canonical B5 smoke route in both directions;
#   4) fail closed before the expensive hybrid materialization if any interface is unclear.
# ======================================================================================

ROOT_DEFAULT = r"C:\Tesi"

# ----- Frozen B5 package ---------------------------------------------------------------
B5_DIR_REL = r"Tesi_QGIS\02_package\grafo_operativo_osm"

B5_TIME_NAME = "osm_turn_state_time_v01.npz"
B5_TIME_SHA256 = "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"

B5_LENGTH_NAME = "osm_turn_state_length_v01.npz"
B5_LENGTH_SHA256 = "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2"

B5_EDGEID_NAME = "osm_turn_state_edgeid_v01.npz"
B5_EDGEID_SHA256 = "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185"

B5_INDEX_NAME = "osm_turn_state_index_v01.sqlite"
B5_INDEX_SHA256 = "c8af04daa3a588001faa5fdf24d942361845d4081693a19ccfccf94605771bff"

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
EXPECTED_ACCESSES_PER_COMMUNE = 3
LAMBDA_SUM_TOL = 1e-12

# ----- Frozen shared-boundary GEO audit ------------------------------------------------
GEO_AUDIT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_geo_audit_v01.csv"
)
GEO_AUDIT_SHA256 = "281d116da9b86374e1e4add02d72255a9db11fa70cc70a06265c5e7f1326a2bd"
EXPECTED_VENETO_GEOS = 49
EXPECTED_VENETO_GATEWAYS = 12
GEO_STATUS_OK = "SHARED_EXACT_B2_CORE_ANCHOR"

# ----- GH06 evidence chain --------------------------------------------------------------
GH06_MANIFEST_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\graph_load_targeted_routing_qa_v01"
    r"\B1_EXT_GH_graph_load_targeted_routing_qa_manifest_v01.json"
)
GH06_MANIFEST_SHA256 = "a7590ed3b5dd61670ee509843b6707d14d66fc609ded37056a81aa8214f0353d"

# ----- Output --------------------------------------------------------------------------
OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01"
)

MAPPING_CSV = "B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_07_hybrid_runtime_preflight_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_07_hybrid_runtime_preflight_manifest_v01.json"


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


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    if not columns:
        raise RuntimeError(f"CSV has no header: {path}")
    return rows, columns


def strict_hash_check(name: str, path: Path, expected: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    ok = actual == expected.lower()
    print(f"{name:<26} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {name}")
    return actual


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


def float_required(row: dict[str, str], key: str) -> float:
    try:
        x = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid/missing float field {key!r}: {row.get(key)!r}") from exc
    if not math.isfinite(x):
        raise RuntimeError(f"Non-finite float field {key!r}: {row.get(key)!r}")
    return x


def assert_sqlite_integrity(path: Path) -> None:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite integrity_check failed for {path}: {result}")
    finally:
        con.close()


# ======================================================================================
# CSR/B5 helpers
# ======================================================================================

def load_csr_npz(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as z:
        required = {"indices", "indptr", "format", "shape", "data"}
        missing = required - set(z.files)
        if missing:
            raise RuntimeError(f"{path.name}: missing CSR keys {sorted(missing)}")

        fmt_raw = z["format"].item()
        if isinstance(fmt_raw, bytes):
            fmt = fmt_raw.decode("ascii", errors="strict")
        else:
            fmt = str(fmt_raw)
        if fmt.lower() != "csr":
            raise RuntimeError(f"{path.name}: expected CSR, found {fmt!r}")

        shape_arr = np.asarray(z["shape"], dtype=np.int64)
        if shape_arr.shape != (2,):
            raise RuntimeError(f"{path.name}: invalid shape vector {shape_arr.shape}")

        return {
            "indices": np.asarray(z["indices"]),
            "indptr": np.asarray(z["indptr"]),
            "shape": (int(shape_arr[0]), int(shape_arr[1])),
            "data": np.asarray(z["data"]),
            "format": fmt.lower(),
        }


def validate_csr_contract(
    time_csr: dict[str, object],
    length_csr: dict[str, object],
    edgeid_csr: dict[str, object],
) -> None:
    expected_shape = (EXPECTED_B5_TOTAL_STATES, EXPECTED_B5_TOTAL_STATES)
    for label, csr in (
        ("time", time_csr),
        ("length", length_csr),
        ("edgeid", edgeid_csr),
    ):
        if csr["shape"] != expected_shape:
            raise RuntimeError(f"{label} CSR shape {csr['shape']} != {expected_shape}")
        indices = csr["indices"]
        indptr = csr["indptr"]
        data = csr["data"]
        assert isinstance(indices, np.ndarray)
        assert isinstance(indptr, np.ndarray)
        assert isinstance(data, np.ndarray)
        if len(indices) != EXPECTED_B5_TRANSITIONS:
            raise RuntimeError(f"{label}: transitions {len(indices)} != {EXPECTED_B5_TRANSITIONS}")
        if len(data) != EXPECTED_B5_TRANSITIONS:
            raise RuntimeError(f"{label}: data length mismatch")
        if len(indptr) != EXPECTED_B5_TOTAL_STATES + 1:
            raise RuntimeError(f"{label}: indptr length mismatch")
        if int(indptr[0]) != 0 or int(indptr[-1]) != EXPECTED_B5_TRANSITIONS:
            raise RuntimeError(f"{label}: invalid indptr endpoints")

    for other_label, other in (("length", length_csr), ("edgeid", edgeid_csr)):
        if not np.array_equal(time_csr["indices"], other["indices"]):
            raise RuntimeError(f"CSR structural mismatch: time vs {other_label} indices")
        if not np.array_equal(time_csr["indptr"], other["indptr"]):
            raise RuntimeError(f"CSR structural mismatch: time vs {other_label} indptr")

    time_data = time_csr["data"]
    assert isinstance(time_data, np.ndarray)
    if not np.all(np.isfinite(time_data)):
        raise RuntimeError("B5 time CSR contains non-finite transition costs")
    if np.any(time_data < 0):
        raise RuntimeError("B5 time CSR contains negative transition costs")


def dijkstra_to_target_states(
    indptr: np.ndarray,
    indices: np.ndarray,
    weights: np.ndarray,
    source_state: int,
    target_states: Iterable[int],
) -> tuple[float, int, int]:
    n = len(indptr) - 1
    if not (0 <= source_state < n):
        raise ValueError(f"source_state out of range: {source_state}")

    targets = {int(x) for x in target_states}
    if not targets:
        raise ValueError("target_states is empty")
    if any(x < 0 or x >= n for x in targets):
        raise ValueError("target state out of range")

    if source_state in targets:
        return 0.0, source_state, 1

    dist = np.full(n, np.inf, dtype=np.float64)
    dist[source_state] = 0.0
    heap: list[tuple[float, int]] = [(0.0, source_state)]
    settled = 0

    while heap:
        d_u, u = heapq.heappop(heap)
        if d_u != float(dist[u]):
            continue
        settled += 1
        if u in targets:
            return d_u, u, settled

        start = int(indptr[u])
        end = int(indptr[u + 1])
        for pos in range(start, end):
            v = int(indices[pos])
            alt = d_u + float(weights[pos])
            if alt < float(dist[v]):
                dist[v] = alt
                heapq.heappush(heap, (alt, v))

    return math.inf, -1, settled


def target_state_map(state_node_id: np.ndarray, target_nodes: set[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {node: [] for node in target_nodes}
    for state_id, node_raw in enumerate(state_node_id):
        node = int(node_raw)
        if node in result:
            result[node].append(state_id)
    return result


def base_state_map(base_nodes: np.ndarray, target_nodes: set[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {node: [] for node in target_nodes}
    for state_id, node_raw in enumerate(base_nodes):
        node = int(node_raw)
        if node in result:
            result[node].append(state_id)
    return result


# ======================================================================================
# Gamma + GEO helpers
# ======================================================================================

def validate_gamma(
    rows: list[dict[str, str]],
    columns: list[str],
    base_nodes: np.ndarray,
    state_node_id: np.ndarray,
) -> dict[str, object]:
    required = {
        "PRO_COM",
        "COMUNE",
        "access_order",
        "structural_node_id",
        "base_state_id",
        "lambda_L",
        "weight_rule",
        "tau_m",
    }
    missing = required - set(columns)
    if missing:
        raise RuntimeError(f"Gamma missing columns: {sorted(missing)}")
    if len(rows) != EXPECTED_GAMMA_ROWS:
        raise RuntimeError(f"Gamma rows {len(rows)} != {EXPECTED_GAMMA_ROWS}")

    by_com: dict[int, list[dict[str, object]]] = defaultdict(list)
    max_node_mismatch = 0

    normalized: list[dict[str, object]] = []
    for row in rows:
        pro_com = parse_intlike(row["PRO_COM"])
        access_order = parse_intlike(row["access_order"])
        physical_node = parse_intlike(row["structural_node_id"])
        base_state = parse_intlike(row["base_state_id"])
        if None in (pro_com, access_order, physical_node, base_state):
            raise RuntimeError(f"Gamma integer parse failure: {row}")
        assert pro_com is not None
        assert access_order is not None
        assert physical_node is not None
        assert base_state is not None

        lam = float_required(row, "lambda_L")
        tau = float_required(row, "tau_m")
        if not (lam > 0):
            raise RuntimeError(f"Non-positive lambda for PRO_COM={pro_com}, access={access_order}")
        if row["weight_rule"] != "EXP_REL_300":
            raise RuntimeError(f"Unexpected Gamma weight_rule: {row['weight_rule']!r}")
        if abs(tau - 300.0) > 1e-9:
            raise RuntimeError(f"Unexpected tau_m={tau}")
        if not (0 <= base_state < len(base_nodes)):
            raise RuntimeError(f"Gamma base_state out of range: {base_state}")

        bnode = int(base_nodes[base_state])
        snode = int(state_node_id[base_state])
        if bnode != physical_node or snode != physical_node:
            max_node_mismatch += 1
            raise RuntimeError(
                "Gamma base-state/physical-node mismatch: "
                f"PRO_COM={pro_com} access={access_order} physical={physical_node} "
                f"base_nodes[{base_state}]={bnode} state_node_id[{base_state}]={snode}"
            )

        item = {
            "PRO_COM": pro_com,
            "COMUNE": row["COMUNE"],
            "access_order": access_order,
            "physical_node_id": physical_node,
            "base_state_id": base_state,
            "lambda_L": lam,
        }
        normalized.append(item)
        by_com[pro_com].append(item)

    if len(by_com) != EXPECTED_GAMMA_COMMUNES:
        raise RuntimeError(f"Gamma communes {len(by_com)} != {EXPECTED_GAMMA_COMMUNES}")

    max_lambda_sum_error = 0.0
    for pro_com, items in by_com.items():
        if len(items) != EXPECTED_ACCESSES_PER_COMMUNE:
            raise RuntimeError(f"PRO_COM={pro_com}: access count {len(items)} != 3")
        orders = {int(x["access_order"]) for x in items}
        if orders != {1, 2, 3}:
            raise RuntimeError(f"PRO_COM={pro_com}: access orders {sorted(orders)}")
        lam_sum = sum(float(x["lambda_L"]) for x in items)
        err = abs(lam_sum - 1.0)
        max_lambda_sum_error = max(max_lambda_sum_error, err)
        if err > LAMBDA_SUM_TOL:
            raise RuntimeError(f"PRO_COM={pro_com}: lambda sum={lam_sum:.17g}")

    return {
        "rows": normalized,
        "by_commune": by_com,
        "communes": len(by_com),
        "max_lambda_sum_error": max_lambda_sum_error,
        "base_state_node_mismatches": max_node_mismatch,
    }


def representative_geo_rows(
    rows: list[dict[str, str]],
    columns: list[str],
) -> list[dict[str, str]]:
    required = {
        "gateway_id",
        "geo_id",
        "best_anchor_lon",
        "best_anchor_lat",
        "best_anchor_distance_m",
        "status",
    }
    missing = required - set(columns)
    if missing:
        raise RuntimeError(f"GEO audit missing columns: {sorted(missing)}")

    eligible = [r for r in rows if r.get("status") == GEO_STATUS_OK]
    if not eligible:
        raise RuntimeError(f"No GEO rows with status={GEO_STATUS_OK}")

    gateway_by_geo: dict[str, set[str]] = defaultdict(set)
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in eligible:
        gateway = str(row["gateway_id"]).strip()
        geo = str(row["geo_id"]).strip()
        if not gateway or not geo:
            raise RuntimeError("Blank gateway_id/geo_id in eligible GEO audit")
        gateway_by_geo[geo].add(gateway)
        groups[(gateway, geo)].append(row)

    ambiguous = {geo: sorted(gws) for geo, gws in gateway_by_geo.items() if len(gws) != 1}
    if ambiguous:
        raise RuntimeError(f"Ambiguous GEO->gateway mapping: {ambiguous}")

    reps: list[dict[str, str]] = []
    for key in sorted(groups):
        candidates = sorted(
            groups[key],
            key=lambda r: (float_required(r, "best_anchor_distance_m"), json.dumps(r, sort_keys=True)),
        )
        reps.append(candidates[0])

    unique_geos = {r["geo_id"] for r in reps}
    gateways = {r["gateway_id"] for r in reps}
    if len(unique_geos) != EXPECTED_VENETO_GEOS:
        raise RuntimeError(f"Eligible unique GEO count {len(unique_geos)} != {EXPECTED_VENETO_GEOS}")
    if len(gateways) != EXPECTED_VENETO_GATEWAYS:
        raise RuntimeError(f"Eligible gateway count {len(gateways)} != {EXPECTED_VENETO_GATEWAYS}")
    return reps


def infer_physical_node_column(
    rows: list[dict[str, str]],
    columns: list[str],
    valid_base_nodes: set[int],
) -> tuple[str, dict[str, object]]:
    """Infer the physical/B5 anchor-node column without guessing a fixed header.

    A candidate must be integer-like for every representative GEO row and all values must be
    present among B5 physical base nodes. Name affinity only ranks valid candidates; it never
    rescues an invalid candidate. If more than one non-identical candidate remains at the best
    rank, fail closed.
    """
    excluded = {
        "gateway_id",
        "geo_id",
        "status",
        "best_anchor_lon",
        "best_anchor_lat",
        "best_anchor_distance_m",
    }

    valid: list[dict[str, object]] = []
    for col in columns:
        if col in excluded:
            continue
        vals = [parse_intlike(row.get(col)) for row in rows]
        if any(v is None for v in vals):
            continue
        int_vals = [int(v) for v in vals if v is not None]
        membership = sum(v in valid_base_nodes for v in int_vals)
        if membership != len(rows):
            continue

        lname = col.lower()
        score = 0
        if "anchor" in lname:
            score += 8
        if "node" in lname:
            score += 8
        if "physical" in lname:
            score += 4
        if lname.endswith("_id"):
            score += 2
        if "way" in lname or "edge" in lname or "relation" in lname:
            score -= 4
        valid.append({"column": col, "score": score, "values": int_vals})

    if not valid:
        raise RuntimeError(
            "Could not infer a GEO physical anchor node column. "
            f"Actual GEO columns: {columns}"
        )

    best_score = max(int(x["score"]) for x in valid)
    best = [x for x in valid if int(x["score"]) == best_score]

    # Multiple best columns are acceptable only if they are exactly the same vector.
    vectors = {tuple(int(v) for v in x["values"]) for x in best}
    if len(vectors) != 1:
        detail = [(x["column"], x["score"]) for x in best]
        raise RuntimeError(f"Ambiguous GEO physical-node columns: {detail}")

    chosen = sorted(str(x["column"]) for x in best)[0]
    diagnostics = {
        "valid_candidates": [
            {"column": str(x["column"]), "score": int(x["score"])}
            for x in sorted(valid, key=lambda z: (-int(z["score"]), str(z["column"])))
        ],
        "chosen": chosen,
        "best_score": best_score,
    }
    return chosen, diagnostics


# ======================================================================================
# Self-tests (no project files)
# ======================================================================================

def helper_self_tests() -> None:
    # 0 -> 1 (2), 0 -> 2 (10), 1 -> 2 (3). Shortest 0->2 = 5.
    indptr = np.array([0, 2, 3, 3], dtype=np.int32)
    indices = np.array([1, 2, 2], dtype=np.int32)
    weights = np.array([2.0, 10.0, 3.0], dtype=np.float64)
    d, target, settled = dijkstra_to_target_states(indptr, indices, weights, 0, [2])
    if abs(d - 5.0) > 1e-12 or target != 2 or settled < 2:
        raise AssertionError("Dijkstra helper self-test failed")

    d0, target0, _ = dijkstra_to_target_states(indptr, indices, weights, 2, [2])
    if d0 != 0.0 or target0 != 2:
        raise AssertionError("Dijkstra zero-distance self-test failed")

    fake_rows = [
        {"gateway_id": "VE01", "geo_id": "0001", "status": GEO_STATUS_OK,
         "best_anchor_lon": "13.0", "best_anchor_lat": "45.0", "best_anchor_distance_m": "0.1",
         "best_anchor_node_id": "101", "way_id": "999"},
        {"gateway_id": "VE01", "geo_id": "0002", "status": GEO_STATUS_OK,
         "best_anchor_lon": "13.1", "best_anchor_lat": "45.1", "best_anchor_distance_m": "0.2",
         "best_anchor_node_id": "102", "way_id": "998"},
    ]
    col, _ = infer_physical_node_column(
        fake_rows,
        list(fake_rows[0].keys()),
        {101, 102},
    )
    if col != "best_anchor_node_id":
        raise AssertionError("GEO node-column inference self-test failed")


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument(
        "--self-test-only",
        action="store_true",
        help="Run helper tests only; do not touch project files.",
    )
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_07_HELPER_SELF_TESTS = PASS")
        return 0

    root = Path(args.root)
    b5_dir = root / Path(B5_DIR_REL)

    paths = {
        "b5_time": b5_dir / B5_TIME_NAME,
        "b5_length": b5_dir / B5_LENGTH_NAME,
        "b5_edgeid": b5_dir / B5_EDGEID_NAME,
        "b5_index": b5_dir / B5_INDEX_NAME,
        "b5_base_nodes": b5_dir / B5_BASE_NODES_NAME,
        "b5_state_node": b5_dir / B5_STATE_NODE_NAME,
        "gamma_csv": root / Path(GAMMA_REL),
        "geo_audit": root / Path(GEO_AUDIT_REL),
        "gh06_manifest": root / Path(GH06_MANIFEST_REL),
    }
    expected_hashes = {
        "b5_time": B5_TIME_SHA256,
        "b5_length": B5_LENGTH_SHA256,
        "b5_edgeid": B5_EDGEID_SHA256,
        "b5_index": B5_INDEX_SHA256,
        "b5_base_nodes": B5_BASE_NODES_SHA256,
        "b5_state_node": B5_STATE_NODE_SHA256,
        "gamma_csv": GAMMA_SHA256,
        "geo_audit": GEO_AUDIT_SHA256,
        "gh06_manifest": GH06_MANIFEST_SHA256,
    }

    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 07 — HYBRID ROUTING RUNTIME / INTERFACE PREFLIGHT")
    print("=" * 124)
    print("READ-ONLY FROZEN INPUTS / NO GH SERVER / NO FULL B1 ROUTING")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(f"Unexpected staging exists: {staging}")

    staging.mkdir(parents=True, exist_ok=False)

    try:
        # ------------------------------------------------------------------
        # A. Strict input identity
        # ------------------------------------------------------------------
        print("A. STRICT INPUT IDENTITY")
        before_hashes: dict[str, str] = {}
        for name in paths:
            before_hashes[name] = strict_hash_check(name, paths[name], expected_hashes[name])
        assert_sqlite_integrity(paths["b5_index"])
        print("b5_index integrity        PASS")
        print("helper self-tests         PASS")

        with paths["gh06_manifest"].open("r", encoding="utf-8-sig") as f:
            gh06_manifest = json.load(f)
        if gh06_manifest.get("verdict") != "PASS":
            raise RuntimeError("GH06 manifest verdict is not PASS")
        print("GH06 evidence chain       PASS")

        # ------------------------------------------------------------------
        # B. B5 runtime contract
        # ------------------------------------------------------------------
        print()
        print("B. B5 RUNTIME CONTRACT")
        time_csr = load_csr_npz(paths["b5_time"])
        length_csr = load_csr_npz(paths["b5_length"])
        edgeid_csr = load_csr_npz(paths["b5_edgeid"])
        validate_csr_contract(time_csr, length_csr, edgeid_csr)

        base_nodes = np.load(paths["b5_base_nodes"], allow_pickle=False)
        state_node_id = np.load(paths["b5_state_node"], allow_pickle=False)
        if base_nodes.ndim != 1 or len(base_nodes) != EXPECTED_B5_BASE_STATES:
            raise RuntimeError(f"base_nodes shape mismatch: {base_nodes.shape}")
        if state_node_id.ndim != 1 or len(state_node_id) != EXPECTED_B5_TOTAL_STATES:
            raise RuntimeError(f"state_node_id shape mismatch: {state_node_id.shape}")
        if not np.array_equal(state_node_id[:EXPECTED_B5_BASE_STATES], base_nodes):
            raise RuntimeError("B5 invariant failed: state_node_id[:base_states] != base_nodes")

        print(f"base states               = {len(base_nodes):,}")
        print(f"total states              = {len(state_node_id):,}")
        print(f"transitions               = {len(time_csr['indices']):,}")
        print("CSR structural identity   = PASS")
        print("base-state node invariant = PASS")

        # ------------------------------------------------------------------
        # C. Gamma runtime contract
        # ------------------------------------------------------------------
        print()
        print("C. GAMMA RUNTIME CONTRACT")
        gamma_rows_raw, gamma_columns = read_csv(paths["gamma_csv"])
        gamma = validate_gamma(gamma_rows_raw, gamma_columns, base_nodes, state_node_id)
        print(f"Gamma rows                = {len(gamma_rows_raw)}")
        print(f"Gamma communes            = {gamma['communes']}")
        print(f"accesses per commune      = {EXPECTED_ACCESSES_PER_COMMUNE}")
        print(f"max lambda sum error      = {gamma['max_lambda_sum_error']:.3e}")
        print("Gamma base-state mapping  = PASS")

        # ------------------------------------------------------------------
        # D. 49 physical crossing -> B5 mapping
        # ------------------------------------------------------------------
        print()
        print("D. VENETO PHYSICAL CROSSING -> B5 MAPPING")
        geo_rows_raw, geo_columns = read_csv(paths["geo_audit"])
        geo_rows = representative_geo_rows(geo_rows_raw, geo_columns)

        valid_base_node_set = {int(x) for x in base_nodes}
        node_column, node_inference = infer_physical_node_column(
            geo_rows,
            geo_columns,
            valid_base_node_set,
        )
        print(f"physical node column      = {node_column}")
        print(f"eligible GEO concepts     = {len(geo_rows)}")
        print(f"modelling gateways        = {len({r['gateway_id'] for r in geo_rows})}")

        crossing_nodes: set[int] = set()
        for row in geo_rows:
            node = parse_intlike(row.get(node_column))
            if node is None:
                raise RuntimeError(f"Invalid inferred node value: {row.get(node_column)!r}")
            crossing_nodes.add(node)
        # Do not assume that 49 semantic GEO concepts imply 49 distinct B5 node IDs.
        # A duplicate anchor node would be a diagnostic property, not an automatic topology failure.
        crossing_base = base_state_map(base_nodes, crossing_nodes)
        crossing_targets = target_state_map(state_node_id, crossing_nodes)

        mapping_rows: list[dict[str, object]] = []
        for row in sorted(geo_rows, key=lambda r: (r["gateway_id"], r["geo_id"])):
            node = int(parse_intlike(row[node_column]))
            base_states = crossing_base[node]
            dest_states = crossing_targets[node]
            if len(base_states) != 1:
                raise RuntimeError(
                    f"Crossing node {node}: expected exactly one B5 base state, got {base_states}"
                )
            if not dest_states:
                raise RuntimeError(f"Crossing node {node}: no B5 destination states")

            mapping_rows.append({
                "gateway_id": row["gateway_id"],
                "geo_id": row["geo_id"],
                "physical_node_column": node_column,
                "physical_node_id": node,
                "b5_base_state_id": int(base_states[0]),
                "b5_destination_state_count": len(dest_states),
                "b5_destination_state_min": min(dest_states),
                "b5_destination_state_max": max(dest_states),
                "best_anchor_lon": float_required(row, "best_anchor_lon"),
                "best_anchor_lat": float_required(row, "best_anchor_lat"),
                "best_anchor_distance_m": float_required(row, "best_anchor_distance_m"),
                "status": row["status"],
            })

        print(f"crossings with base state = {len(mapping_rows)}/{EXPECTED_VENETO_GEOS}")
        print(f"crossings with dest state = {len(mapping_rows)}/{EXPECTED_VENETO_GEOS}")
        print("GEO->gateway ambiguity    = 0")

        mapping_path = staging / MAPPING_CSV
        with mapping_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(mapping_rows[0].keys()))
            writer.writeheader()
            writer.writerows(mapping_rows)

        # ------------------------------------------------------------------
        # E. Canonical B5 two-direction smoke
        # ------------------------------------------------------------------
        print()
        print("E. CANONICAL B5 TWO-DIRECTION SMOKE")
        gamma_rows = gamma["rows"]
        assert isinstance(gamma_rows, list)
        smoke_access = next(
            x for x in gamma_rows
            if int(x["physical_node_id"]) != int(mapping_rows[0]["physical_node_id"])
        )
        smoke_crossing = mapping_rows[0]

        indptr = time_csr["indptr"]
        indices = time_csr["indices"]
        weights = time_csr["data"]
        assert isinstance(indptr, np.ndarray)
        assert isinstance(indices, np.ndarray)
        assert isinstance(weights, np.ndarray)

        access_source_state = int(smoke_access["base_state_id"])
        access_node = int(smoke_access["physical_node_id"])
        crossing_source_state = int(smoke_crossing["b5_base_state_id"])
        crossing_node = int(smoke_crossing["physical_node_id"])

        ie_targets = crossing_targets[crossing_node]
        ei_targets = np.flatnonzero(state_node_id == access_node).tolist()
        if not ei_targets:
            raise RuntimeError("Smoke Gamma target has no B5 destination state")

        ie_time_s, ie_target_state, ie_settled = dijkstra_to_target_states(
            indptr, indices, weights, access_source_state, ie_targets
        )
        ei_time_s, ei_target_state, ei_settled = dijkstra_to_target_states(
            indptr, indices, weights, crossing_source_state, ei_targets
        )

        if not math.isfinite(ie_time_s) or ie_time_s <= 0:
            raise RuntimeError(f"B5 IE smoke failed: time={ie_time_s}")
        if not math.isfinite(ei_time_s) or ei_time_s <= 0:
            raise RuntimeError(f"B5 EI smoke failed: time={ei_time_s}")

        print(
            f"IE smoke: PRO_COM={smoke_access['PRO_COM']} access={smoke_access['access_order']} "
            f"-> {smoke_crossing['geo_id']} time_s={ie_time_s:.6f} settled={ie_settled:,} PASS"
        )
        print(
            f"EI smoke: {smoke_crossing['geo_id']} -> PRO_COM={smoke_access['PRO_COM']} "
            f"access={smoke_access['access_order']} time_s={ei_time_s:.6f} settled={ei_settled:,} PASS"
        )

        # ------------------------------------------------------------------
        # F. Frozen-input byte integrity after runtime reads
        # ------------------------------------------------------------------
        print()
        print("F. FROZEN INPUT BYTE-INTEGRITY")
        after_hashes = {name: sha256(path) for name, path in paths.items()}
        changed = [name for name in paths if after_hashes[name] != before_hashes[name]]
        if changed:
            raise RuntimeError(f"Frozen input(s) changed during preflight: {changed}")
        print("frozen inputs unchanged   = PASS")

        # ------------------------------------------------------------------
        # G. Summary / manifest / promotion
        # ------------------------------------------------------------------
        summary = {
            "schema": "B1_EXT_GH_07_HYBRID_RUNTIME_PREFLIGHT_SUMMARY_V01",
            "verdict": "PASS",
            "contract": {
                "internal_router": "B5_FROZEN",
                "external_router": "GRAPHHOPPER_11",
                "composition": "PHYSICAL_CROSSING_MIN_COMBINED_TIME",
                "ie_ei_separate": True,
                "gateway_selection_after_physical_crossing_minimization": True,
                "fvg_access_weight_model": "EXP_REL_300",
                "fvg_access_aggregation_for_external_leg": "ONE_SIDED_LAMBDA_WEIGHTED",
            },
            "b5": {
                "base_states": len(base_nodes),
                "total_states": len(state_node_id),
                "transitions": len(indices),
                "source_semantics": "PHYSICAL_NODE_BASE_STATE",
                "destination_semantics": "MIN_OVER_B5_STATES_SHARING_PHYSICAL_NODE",
                "csr_structural_identity_time_length_edgeid": True,
            },
            "gamma": {
                "rows": len(gamma_rows_raw),
                "communes": gamma["communes"],
                "accesses_per_commune": EXPECTED_ACCESSES_PER_COMMUNE,
                "lambda_rule": "EXP_REL_300",
                "max_lambda_sum_error": gamma["max_lambda_sum_error"],
            },
            "crossings": {
                "geo_concepts": len(mapping_rows),
                "gateways": len({r["gateway_id"] for r in mapping_rows}),
                "physical_node_column": node_column,
                "node_column_inference": node_inference,
                "unique_physical_node_ids": len(crossing_nodes),
                "with_exactly_one_base_state": len(mapping_rows),
                "with_destination_states": len(mapping_rows),
                "ambiguous_gateway_mapping": 0,
            },
            "b5_smoke": {
                "gamma": smoke_access,
                "crossing": {
                    "gateway_id": smoke_crossing["gateway_id"],
                    "geo_id": smoke_crossing["geo_id"],
                    "physical_node_id": crossing_node,
                    "base_state_id": crossing_source_state,
                },
                "IE": {
                    "time_s": ie_time_s,
                    "target_state": ie_target_state,
                    "settled_states": ie_settled,
                    "status": "PASS",
                },
                "EI": {
                    "time_s": ei_time_s,
                    "target_state": ei_target_state,
                    "settled_states": ei_settled,
                    "status": "PASS",
                },
            },
            "scope_guardrail": {
                "graphhopper_server": "NOT_STARTED",
                "full_b1_routing": "NOT_STARTED",
                "gateway_assignment": "NOT_STARTED",
                "pbf_import": "NOT_STARTED",
                "frozen_fvg_artifacts_modified": False,
            },
            "frozen_inputs_byte_identical": True,
            "next_gate": "B1_HYBRID_ROUTING_MATERIALIZATION",
        }

        summary_path = staging / SUMMARY_JSON
        write_json(summary_path, summary)

        manifest = {
            "schema": "B1_EXT_GH_07_HYBRID_RUNTIME_PREFLIGHT_MANIFEST_V01",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                name: {
                    "path": str(paths[name]),
                    "sha256": before_hashes[name],
                }
                for name in paths
            },
            "outputs": [
                {
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "sha256": sha256(p),
                }
                for p in (mapping_path, summary_path)
            ],
            "verdict": "PASS",
            "next_gate": "B1_HYBRID_ROUTING_MATERIALIZATION",
        }
        manifest_path = staging / MANIFEST_JSON
        write_json(manifest_path, manifest)

        staging.rename(final_dir)

        print()
        print("=" * 124)
        print("B1_EXT_GH_07_HYBRID_RUNTIME_PREFLIGHT = PASS")
        print(f"GAMMA_ROWS = {len(gamma_rows_raw)}")
        print(f"GAMMA_COMMUNES = {gamma['communes']}")
        print(f"PHYSICAL_CROSSINGS = {len(mapping_rows)}")
        print(f"PHYSICAL_NODE_COLUMN = {node_column}")
        print(f"CROSSINGS_WITH_B5_BASE_STATE = {len(mapping_rows)}/{EXPECTED_VENETO_GEOS}")
        print(f"CROSSINGS_WITH_B5_DEST_STATES = {len(mapping_rows)}/{EXPECTED_VENETO_GEOS}")
        print("B5_IE_SMOKE = PASS")
        print("B5_EI_SMOKE = PASS")
        print("FROZEN_INPUTS_BYTE_IDENTICAL = YES")
        print("GRAPHHOPPER_SERVER = NOT_STARTED")
        print("FULL_B1_ROUTING = NOT_STARTED")
        print("GATEWAY_ASSIGNMENT = NOT_STARTED")
        print("PBF_IMPORT = NOT_STARTED")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print("NEXT_GATE = B1_HYBRID_ROUTING_MATERIALIZATION")
        print(f"{MAPPING_CSV} SHA256 = {sha256(final_dir / MAPPING_CSV)}")
        print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
        print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
        print("=== RUN COMPLETATA ===")
        return 0

    except Exception as exc:
        # Staging is deliberately preserved for diagnostics; frozen inputs are never written.
        print()
        print("=" * 124)
        print("B1_EXT_GH_07_HYBRID_RUNTIME_PREFLIGHT = FAIL")
        print(f"ERROR = {exc}")
        print(f"DIAGNOSTIC_STAGING = {staging if staging.exists() else 'NONE'}")
        print("GRAPHHOPPER_SERVER = NOT_STARTED")
        print("FULL_B1_ROUTING = NOT_STARTED")
        print("GATEWAY_ASSIGNMENT = NOT_STARTED")
        print("PBF_IMPORT = NOT_STARTED")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print("NEXT_GATE = REVIEW_HYBRID_RUNTIME_INTERFACE_FAILURE")
        print("=== RUN COMPLETATA ===")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
