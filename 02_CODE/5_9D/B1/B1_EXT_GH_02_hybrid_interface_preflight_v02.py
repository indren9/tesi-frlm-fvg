#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ======================================================================================
# B1-EXT-GH 02 v02 — HYBRID B5 <-> GRAPHHOPPER INTERFACE PREFLIGHT
#
# READ-ONLY.
# No graph import, no routing, no downloads, no project writes.
#
# Purpose:
#   - verify the materialized external support package;
#   - verify the frozen B5 artifacts needed for a strict hybrid composition;
#   - verify the A1 Veneto modelling-gateway -> A0 physical-crossing mapping is
#     resolvable on the frozen A0 inventory;
#   - verify the B5 state/node representation exposes a usable physical-node
#     interface for the next targeted cross-snapshot topology test.
# ======================================================================================

EXPECTED = {
    "frozen_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf",
        "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813",
    ),
    "b2": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite",
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",
    ),
    "b5_index": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_index_v01.sqlite",
        "c8af04daa3a588001faa5fdf24d942361845d4081693a19ccfccf94605771bff",
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
    "b5_base_nodes": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_base_nodes_v01.npy",
        "de02faa32628af6099118e08bd3e13847fbb0330d1aa7d824df47220b2f947d7",
    ),
    "b5_state_nodes": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_node_id_v01.npy",
        "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935",
    ),
    "gamma": (
        r"Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv",
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",
    ),
    "a0": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_A0_geo_v02\deduplicated_physical_crossings_v02.csv",
        "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe",
    ),
    "italy": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1\italy-260801.osm.pbf",
        "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538",
    ),
    "gh_jar": (
        r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar",
        "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def",
    ),
    "jre_zip": (
        r"tools\graphhopper\b1_ext_v01\downloads\OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip",
        "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae",
    ),
}

MATERIALIZATION_MANIFEST = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\B1_EXT_GH_materialization_manifest_v01.json"
)

# Frozen A1 Veneto modelling-cordon mapping.
# The 12 gateways are the only gateway family relevant to B1 external-Italy commuting.
A1_VENETO = {
    "VE01":  ["GEO_0468", "GEO_0475", "GEO_0484"],
    "VE02":  ["GEO_0353", "GEO_0354", "GEO_0345", "GEO_0350",
              "GEO_0352", "GEO_0357", "GEO_0360", "GEO_0369"],
    "VE03":  ["GEO_0196", "GEO_0195", "GEO_0197", "GEO_0199", "GEO_0201"],
    "VE04":  ["GEO_0154", "GEO_0098", "GEO_0099", "GEO_0203", "GEO_0205"],
    "VE05":  ["GEO_0486"],
    "VE06":  ["GEO_0004"],
    "A1V01": ["GEO_0198"],
    "A1V02": ["GEO_0263"],
    "A1V03": ["GEO_0228", "GEO_0213", "GEO_0215", "GEO_0227",
              "GEO_0229", "GEO_0231", "GEO_0255", "GEO_0256", "GEO_0269"],
    "A1V04": ["GEO_0293", "GEO_0304", "GEO_0273", "GEO_0287",
              "GEO_0307", "GEO_0315", "GEO_0323"],
    "A1V05": ["GEO_0391", "GEO_0402", "GEO_0373", "GEO_0375",
              "GEO_0385", "GEO_0399", "GEO_0405"],
    "A1V06": ["GEO_0500"],
}

EXPECTED_B2_COLUMNS = [
    "edge_id", "edge_uid", "segment_uid", "way_id", "seq", "u", "v",
    "way_direction", "length_m", "speed_kmh", "time_s", "highway",
    "direction_status", "routing_status", "routing_code", "closure_cause",
    "access_class", "speed_source", "edge_role", "core_eligible",
    "access_conditional_flag", "direction_conditional_flag",
    "speed_conditional_flag",
]

EXPECTED_B5_STATES = 904_607
EXPECTED_B5_BASE_STATES = 897_857
EXPECTED_B5_TRANSITIONS = 1_699_994


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def pbf_header(path: Path) -> dict[str, str]:
    import osmium

    reader = osmium.io.Reader(str(path))
    try:
        h = reader.header()
        return {
            "generator": h.get("generator", ""),
            "base_url": h.get("osmosis_replication_base_url", ""),
            "sequence": h.get("osmosis_replication_sequence_number", ""),
            "timestamp": h.get("osmosis_replication_timestamp", "") or h.get("timestamp", ""),
        }
    finally:
        reader.close()


def parse_iso_z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalize_geo_id(value: object) -> str:
    s = str(value).strip().upper().replace("-", "_")
    m = re.search(r"GEO_?(\d{1,4})", s)
    if not m:
        return ""
    return f"GEO_{int(m.group(1)):04d}"


def extract_way_ids(value: object) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, float) and np.isnan(value):
        return set()
    return {int(x) for x in re.findall(r"(?<!\d)\d{3,}(?!\d)", str(value))}


def load_csr_npz(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        keys = set(z.files)
        required = {"indptr", "indices", "data"}
        if not required.issubset(keys):
            raise RuntimeError(
                f"{path.name}: NPZ keys={sorted(keys)}; required={sorted(required)}"
            )
        # Copy into ordinary ndarrays before the NPZ handle is closed.
        return z["indptr"].copy(), z["indices"].copy(), z["data"].copy()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\Tesi")
    args = ap.parse_args()

    root = Path(args.root)

    print("=" * 118)
    print("B1-EXT-GH 02 v02 — HYBRID B5 <-> GRAPHHOPPER INTERFACE PREFLIGHT")
    print("=" * 118)
    print("READ-ONLY / NO GRAPH IMPORT / NO ROUTING / NO DOWNLOADS / NO PROJECT WRITES")
    print()

    failures: list[str] = []
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # A. Byte identities
    # ------------------------------------------------------------------
    print("A. BYTE IDENTITY")
    paths: dict[str, Path] = {}

    for key, (rel, expected_hash) in EXPECTED.items():
        path = root / Path(rel)
        paths[key] = path
        if not path.is_file():
            print(f"{key:<20} FAIL  MISSING: {path}")
            failures.append(f"missing:{key}")
            continue
        actual = sha256(path)
        ok = actual == expected_hash
        print(f"{key:<20} {'PASS' if ok else 'FAIL':<5} {actual}")
        if not ok:
            failures.append(f"sha256:{key}")

    if failures:
        print()
        print("B1_EXT_GH_02 = FAIL")
        print("Reason: byte-identity preflight failed.")
        print("GRAPH_IMPORT = NOT_STARTED")
        print("ROUTING = NOT_STARTED")
        print("=== RUN COMPLETATA ===")
        return 2

    # ------------------------------------------------------------------
    # B. Materialization package and temporal relation
    # ------------------------------------------------------------------
    print()
    print("B. MATERIALIZED EXTERNAL SUPPORT")

    manifest_path = root / Path(MATERIALIZATION_MANIFEST)
    if not manifest_path.is_file():
        failures.append("materialization_manifest_missing")
        print("manifest = FAIL MISSING")
    else:
        with manifest_path.open("r", encoding="utf-8-sig") as f:
            manifest = json.load(f)
        hard = manifest.get("hard_stop", {})
        manifest_ok = (
            manifest.get("role") == "EXTERNAL_ITALY_ROUTING_SUPPORT_ONLY"
            and hard.get("graph_import") == "NOT_STARTED"
            and hard.get("routing") == "NOT_STARTED"
            and hard.get("frozen_artifacts_modified") is False
        )
        print(f"manifest role         = {manifest.get('role')}")
        print(f"manifest source policy= {manifest.get('source_policy')}")
        print(f"manifest graph import = {hard.get('graph_import')}")
        print(f"manifest routing      = {hard.get('routing')}")
        print(f"manifest guardrail    = {'PASS' if manifest_ok else 'FAIL'}")
        if not manifest_ok:
            failures.append("materialization_manifest_guardrail")

    frozen_h = pbf_header(paths["frozen_pbf"])
    italy_h = pbf_header(paths["italy"])

    print(f"frozen timestamp = {frozen_h['timestamp']}")
    print(f"italy timestamp  = {italy_h['timestamp']}")

    try:
        offset_h = (
            parse_iso_z(frozen_h["timestamp"]) - parse_iso_z(italy_h["timestamp"])
        ).total_seconds() / 3600.0
        print(f"frozen-minus-italy temporal offset = {offset_h:.6f} h")
        if offset_h < 0:
            failures.append("national_snapshot_newer_than_frozen")
        elif offset_h > 72:
            warnings.append("temporal_offset_gt_72h")
    except Exception as e:
        failures.append("timestamp_parse")
        print(f"temporal offset = FAIL ({e!r})")

    # ------------------------------------------------------------------
    # C. A1 Veneto -> A0 physical inventory
    # ------------------------------------------------------------------
    print()
    print("C. A1 VENETO -> A0 PHYSICAL CROSSING RESOLUTION")

    a0 = pd.read_csv(paths["a0"], low_memory=False)
    print(f"A0 rows    = {len(a0)}")
    print(f"A0 columns = {list(a0.columns)}")

    if "crossing_candidate_id" not in a0.columns:
        failures.append("a0_missing_crossing_candidate_id")
        geo_series = pd.Series([""] * len(a0), index=a0.index)
    else:
        geo_series = a0["crossing_candidate_id"].map(normalize_geo_id)

    index_by_geo: dict[str, list[int]] = {}
    for idx, geo in geo_series.items():
        if geo:
            index_by_geo.setdefault(geo, []).append(int(idx))

    all_requested = [g for values in A1_VENETO.values() for g in values]
    unique_requested = sorted(set(all_requested))
    missing_geo = [g for g in unique_requested if g not in index_by_geo]
    duplicate_geo = {
        g: index_by_geo[g]
        for g in unique_requested
        if len(index_by_geo.get(g, [])) != 1
    }

    print(f"A1 Veneto gateways              = {len(A1_VENETO)}")
    print(f"A1 referenced raw GEO groups    = {len(all_requested)}")
    print(f"A1 unique referenced GEO groups = {len(unique_requested)}")
    print(f"A0 missing referenced GEO       = {len(missing_geo)}")
    print(f"A0 duplicate referenced GEO     = {len(duplicate_geo)}")

    if missing_geo:
        print("missing GEO:", ", ".join(missing_geo))
        failures.append("a1_geo_missing")
    if duplicate_geo:
        print("duplicate GEO:", duplicate_geo)
        failures.append("a1_geo_duplicate")

    # Extract way IDs only from columns that semantically carry way IDs.
    way_columns = [
        c for c in a0.columns
        if "way" in c.lower() and ("id" in c.lower() or "ids" in c.lower())
    ]
    print(f"A0 way-id columns = {way_columns}")

    gateway_way_ids: dict[str, set[int]] = {}
    empty_way_geos: list[str] = []

    for gateway, geos in A1_VENETO.items():
        ids: set[int] = set()
        for geo in geos:
            rows = index_by_geo.get(geo, [])
            if len(rows) != 1:
                continue
            row = a0.loc[rows[0]]
            geo_ids: set[int] = set()
            for c in way_columns:
                geo_ids |= extract_way_ids(row[c])
            if not geo_ids:
                empty_way_geos.append(geo)
            ids |= geo_ids
        gateway_way_ids[gateway] = ids
        print(
            f"{gateway:<6} GEO={len(geos):>2} "
            f"unique_way_ids={len(ids):>3}"
        )

    if empty_way_geos:
        print("GEO groups without parsed way IDs:", ", ".join(sorted(set(empty_way_geos))))
        failures.append("a0_way_id_resolution")

    all_target_way_ids = sorted(set().union(*gateway_way_ids.values()))
    print(f"TOTAL UNIQUE TARGET WAY IDS = {len(all_target_way_ids)}")

    # ------------------------------------------------------------------
    # D. B2 interface schema and way coverage
    # ------------------------------------------------------------------
    print()
    print("D. B2 PHYSICAL/DIRECTED INTERFACE")

    # Use a proper file URI so Windows drive letters/backslashes cannot be
    # misinterpreted by sqlite URI parsing.
    b2_uri = paths["b2"].resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(b2_uri, uri=True)
    try:
        table_names = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required_tables = {"directed_edges", "nodes"}
        missing_tables = sorted(required_tables - table_names)
        print(f"B2 tables = {sorted(table_names)}")
        if missing_tables:
            failures.append("b2_missing_tables")
            print(f"B2 missing tables = {missing_tables}")

        cols = [row[1] for row in con.execute("PRAGMA table_info(directed_edges)")]
        print(f"B2 directed_edges columns = {cols}")
        if cols != EXPECTED_B2_COLUMNS:
            failures.append("b2_schema_mismatch")

        qmarks = ",".join("?" for _ in all_target_way_ids)
        if all_target_way_ids:
            sql = (
                "SELECT COUNT(*), "
                "COUNT(DISTINCT way_id), "
                "SUM(CASE WHEN routing_code=1 THEN 1 ELSE 0 END) "
                "FROM directed_edges WHERE way_id IN (" + qmarks + ")"
            )
            n_edges, n_ways, n_core = con.execute(sql, all_target_way_ids).fetchone()
        else:
            n_edges = n_ways = n_core = 0

        print(f"B2 target directed edges = {n_edges}")
        print(f"B2 target ways present    = {n_ways}/{len(all_target_way_ids)}")
        print(f"B2 target CORE edges      = {n_core}")

        if n_ways != len(all_target_way_ids):
            warnings.append("some_A0_way_ids_not_in_B2")
        if not n_core:
            failures.append("no_target_core_edges")
    finally:
        con.close()

    # ------------------------------------------------------------------
    # E. B5 array/state contract
    # ------------------------------------------------------------------
    print()
    print("E. B5 PHYSICAL-NODE / STATE INTERFACE")

    base_nodes = np.load(paths["b5_base_nodes"], allow_pickle=False)
    state_nodes = np.load(paths["b5_state_nodes"], allow_pickle=False)

    print(f"base_nodes shape = {base_nodes.shape} dtype={base_nodes.dtype}")
    print(f"state_nodes shape= {state_nodes.shape} dtype={state_nodes.dtype}")

    base_shape_ok = base_nodes.ndim == 1 and len(base_nodes) == EXPECTED_B5_BASE_STATES
    state_shape_ok = state_nodes.ndim == 1 and len(state_nodes) == EXPECTED_B5_STATES
    base_prefix_ok = (
        base_shape_ok
        and state_shape_ok
        and np.array_equal(state_nodes[:len(base_nodes)], base_nodes)
    )
    unique_base_ok = base_shape_ok and len(np.unique(base_nodes)) == len(base_nodes)

    print(f"B5 base-state count            = {'PASS' if base_shape_ok else 'FAIL'}")
    print(f"B5 total-state count           = {'PASS' if state_shape_ok else 'FAIL'}")
    print(f"state_nodes[:base_count]=base  = {'PASS' if base_prefix_ok else 'FAIL'}")
    print(f"base physical nodes unique     = {'PASS' if unique_base_ok else 'FAIL'}")

    if not all([base_shape_ok, state_shape_ok, base_prefix_ok, unique_base_ok]):
        failures.append("b5_state_node_contract")

    t_indptr, t_indices, t_data = load_csr_npz(paths["b5_time"])
    l_indptr, l_indices, l_data = load_csr_npz(paths["b5_length"])
    e_indptr, e_indices, e_data = load_csr_npz(paths["b5_edgeid"])

    csr_contract_ok = (
        len(t_indptr) == EXPECTED_B5_STATES + 1
        and len(t_indices) == EXPECTED_B5_TRANSITIONS
        and len(t_data) == EXPECTED_B5_TRANSITIONS
        and np.array_equal(t_indptr, l_indptr)
        and np.array_equal(t_indptr, e_indptr)
        and np.array_equal(t_indices, l_indices)
        and np.array_equal(t_indices, e_indices)
        and len(l_data) == EXPECTED_B5_TRANSITIONS
        and len(e_data) == EXPECTED_B5_TRANSITIONS
        and int(t_indptr[-1]) == EXPECTED_B5_TRANSITIONS
    )

    index_range_ok = (
        t_indices.size == 0
        or (
            int(t_indices.min()) >= 0
            and int(t_indices.max()) < EXPECTED_B5_STATES
        )
    )

    finite_time_ok = bool(np.isfinite(t_data).all() and (t_data >= 0).all())
    finite_length_ok = bool(np.isfinite(l_data).all() and (l_data >= 0).all())

    print(f"B5 CSR structure              = {'PASS' if csr_contract_ok else 'FAIL'}")
    print(f"B5 destination state range    = {'PASS' if index_range_ok else 'FAIL'}")
    print(f"B5 time finite/nonnegative    = {'PASS' if finite_time_ok else 'FAIL'}")
    print(f"B5 length finite/nonnegative  = {'PASS' if finite_length_ok else 'FAIL'}")

    if not all([csr_contract_ok, index_range_ok, finite_time_ok, finite_length_ok]):
        failures.append("b5_csr_contract")

    # ------------------------------------------------------------------
    # F. Gamma source-state sanity
    # ------------------------------------------------------------------
    print()
    print("F. GAMMA SOURCE-STATE SANITY")

    gamma = pd.read_csv(paths["gamma"])
    required_gamma = {"structural_node_id", "base_state_id"}
    gamma_cols_ok = required_gamma.issubset(gamma.columns)
    print(f"Gamma rows = {len(gamma)}")
    print(f"Gamma required columns = {'PASS' if gamma_cols_ok else 'FAIL'}")

    gamma_state_ok = False
    if gamma_cols_ok:
        bs = pd.to_numeric(gamma["base_state_id"], errors="coerce").to_numpy()
        pn = pd.to_numeric(gamma["structural_node_id"], errors="coerce").to_numpy()

        finite = np.isfinite(bs) & np.isfinite(pn)
        if finite.all():
            bs_i = bs.astype(np.int64)
            pn_i = pn.astype(np.int64)
            in_range = (bs_i >= 0) & (bs_i < len(base_nodes))
            gamma_state_ok = bool(
                in_range.all()
                and np.array_equal(base_nodes[bs_i], pn_i)
            )

    print(f"Gamma base_state -> physical node = {'PASS' if gamma_state_ok else 'FAIL'}")
    if not gamma_cols_ok or not gamma_state_ok:
        failures.append("gamma_b5_state_mapping")

    # ------------------------------------------------------------------
    # G. Final decision
    # ------------------------------------------------------------------
    print()
    print("=" * 118)

    if failures:
        verdict = "NOT_READY"
    else:
        verdict = "PASS_TO_TARGETED_TOPOLOGY_TEST"

    print(f"B1_EXT_GH_02_HYBRID_INTERFACE_PREFLIGHT = {verdict}")
    print(f"FAILURES = {len(failures)}")
    print(f"WARNINGS = {len(warnings)}")

    if failures:
        print("FAILURE_CODES:")
        for x in failures:
            print(f"  - {x}")

    if warnings:
        print("WARNING_CODES:")
        for x in warnings:
            print(f"  - {x}")

    print("INTERNAL_ROUTER = B5_FROZEN")
    print("EXTERNAL_ROUTER = GRAPHHOPPER_11_CANDIDATE")
    print("NATIONAL_PBF = italy-260801.osm.pbf")
    print("VENETO_MODELLING_GATEWAYS = 12")
    print(f"A1_REFERENCED_RAW_GEO_GROUPS = {len(unique_requested)}")
    print(f"TARGET_OSM_WAYS = {len(all_target_way_ids)}")
    print("GRAPH_IMPORT = NOT_STARTED")
    print("ROUTING = NOT_STARTED")
    print("PROJECT_WRITES = NONE")
    print(
        "NEXT_GATE = "
        + (
            "TARGETED_SHARED_BOUNDARY_TOPOLOGY_SCAN"
            if verdict == "PASS_TO_TARGETED_TOPOLOGY_TEST"
            else "STOP_AND_REVIEW"
        )
    )
    print("=== RUN COMPLETATA ===")

    return 0 if verdict == "PASS_TO_TARGETED_TOPOLOGY_TEST" else 2


if __name__ == "__main__":
    raise SystemExit(main())
