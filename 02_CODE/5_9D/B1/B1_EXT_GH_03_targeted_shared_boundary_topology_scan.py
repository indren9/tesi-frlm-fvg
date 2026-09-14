#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import osmium

# ======================================================================================
# B1-EXT-GH 03 — TARGETED SHARED-BOUNDARY TOPOLOGY SCAN
#
# PURPOSE
#   Validate, before any GraphHopper import, that the frozen FVG/B5-side topology
#   and the near-contemporaneous Italy support PBF expose exact shared OSM topology
#   at the 12 A1 Veneto modelling gateways.
#
# SCOPE
#   - 49 A1-referenced raw A0 GEO groups;
#   - only OSM way IDs explicitly listed in A0.osm_way_ids;
#   - only B2 CORE edges for hybrid anchor viability;
#   - one targeted way scan of frozen Nord-Est PBF;
#   - one targeted way scan of Italy PBF.
#
# WRITES
#   Only a new, versioned diagnostic directory under 03_output_temporanei.
#   Staging is removed on runtime failure. Existing output is never overwritten.
#
# HARD STOP
#   NO GraphHopper graph import.
#   NO routing.
#   NO change to G_OSM, B2/B4/B5, Gamma, OD_PATH_SYSTEM, A0 or A1.
# ======================================================================================

EXPECTED_SHA256 = {
    "frozen_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf",
        "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813",
    ),
    "italy_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1\italy-260801.osm.pbf",
        "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538",
    ),
    "b2": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite",
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",
    ),
    "a0": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_A0_geo_v02\deduplicated_physical_crossings_v02.csv",
        "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe",
    ),
    "b5_state_nodes": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_node_id_v01.npy",
        "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935",
    ),
    "b5_base_nodes": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_base_nodes_v01.npy",
        "de02faa32628af6099118e08bd3e13847fbb0330d1aa7d824df47220b2f947d7",
    ),
}

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

OUTPUT_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_topology_scan_v01"
)

WAY_AUDIT = "B1_EXT_shared_boundary_way_audit_v01.csv"
GEO_AUDIT = "B1_EXT_shared_boundary_geo_audit_v01.csv"
GATEWAY_AUDIT = "B1_EXT_shared_boundary_gateway_audit_v01.csv"
SUMMARY_JSON = "B1_EXT_shared_boundary_topology_summary_v01.json"
MANIFEST_JSON = "B1_EXT_shared_boundary_topology_manifest_v01.json"

# A large nearest-anchor distance is diagnostic, not an automatic failure.
ANCHOR_DISTANCE_WARNING_M = 1_000.0


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def normalize_geo_id(value: object) -> str:
    s = str(value).strip().upper().replace("-", "_")
    m = re.search(r"GEO_?(\d{1,4})", s)
    return f"GEO_{int(m.group(1)):04d}" if m else ""


def extract_way_ids(value: object) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, float) and np.isnan(value):
        return set()
    return {int(x) for x in re.findall(r"(?<!\d)\d{3,}(?!\d)", str(value))}


def chunks(values: list[int], size: int = 700) -> Iterable[list[int]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2.0) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    )
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


class TargetWayHandler(osmium.SimpleHandler):
    """Capture only selected OSM ways. No node-location index is created."""

    TAGS = (
        "highway", "ref", "name", "oneway", "junction",
        "access", "vehicle", "motor_vehicle", "motorcar", "maxspeed",
    )

    def __init__(self, wanted: set[int]):
        super().__init__()
        self.wanted = wanted
        self.ways: dict[int, dict] = {}

    def way(self, w):
        wid = int(w.id)
        if wid not in self.wanted:
            return
        self.ways[wid] = {
            "way_id": wid,
            "version": int(w.version),
            "node_ids": tuple(int(n.ref) for n in w.nodes),
            "tags": {k: (w.tags.get(k) or "") for k in self.TAGS},
        }


def scan_target_ways(pbf: Path, wanted: set[int]) -> dict[int, dict]:
    handler = TargetWayHandler(wanted)
    handler.apply_file(str(pbf), locations=False)
    return handler.ways


def query_b2(
    db_path: Path,
    target_way_ids: list[int],
) -> tuple[pd.DataFrame, dict[int, tuple[float, float]]]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        frames = []
        for batch in chunks(target_way_ids):
            q = ",".join("?" for _ in batch)
            sql = (
                "SELECT edge_id, way_id, u, v, routing_code, core_eligible, "
                "length_m, time_s, highway, direction_status, routing_status "
                f"FROM directed_edges WHERE way_id IN ({q})"
            )
            frames.append(pd.read_sql_query(sql, con, params=batch))

        edges = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(
                columns=[
                    "edge_id", "way_id", "u", "v", "routing_code",
                    "core_eligible", "length_m", "time_s", "highway",
                    "direction_status", "routing_status",
                ]
            )
        )

        node_ids = sorted(
            set(pd.to_numeric(edges.get("u", pd.Series(dtype=float)), errors="coerce")
                .dropna().astype("int64").tolist())
            | set(pd.to_numeric(edges.get("v", pd.Series(dtype=float)), errors="coerce")
                  .dropna().astype("int64").tolist())
        )

        coords: dict[int, tuple[float, float]] = {}
        for batch in chunks(node_ids):
            q = ",".join("?" for _ in batch)
            sql = f"SELECT node_id, lon, lat FROM nodes WHERE node_id IN ({q})"
            for nid, lon, lat in con.execute(sql, batch):
                coords[int(nid)] = (float(lon), float(lat))

        return edges, coords
    finally:
        con.close()


def write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\Tesi")
    args = ap.parse_args()

    root = Path(args.root)
    final_dir = root / Path(OUTPUT_DIR_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 122)
    print("B1-EXT-GH 03 — TARGETED SHARED-BOUNDARY TOPOLOGY SCAN")
    print("=" * 122)
    print("NO GRAPH IMPORT / NO ROUTING / TARGETED QA ONLY")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(f"Unexpected existing staging: {staging}")

    paths: dict[str, Path] = {}

    try:
        # ------------------------------------------------------------------
        # A. Strict preflight before any output directory is created.
        # ------------------------------------------------------------------
        print("A. STRICT PREFLIGHT")
        for key, (rel, expected) in EXPECTED_SHA256.items():
            p = root / Path(rel)
            paths[key] = p
            if not p.is_file():
                raise FileNotFoundError(p)
            actual = sha256(p)
            ok = actual == expected
            print(f"{key:<18} {'PASS' if ok else 'FAIL':<5} {actual}")
            if not ok:
                raise RuntimeError(f"SHA256 mismatch: {key}")

        # ------------------------------------------------------------------
        # B. Resolve exact A0 way IDs. Only osm_way_ids is authoritative here.
        # ------------------------------------------------------------------
        print()
        print("B. A1 VENETO / A0 TARGET RESOLUTION")
        a0 = pd.read_csv(paths["a0"], low_memory=False)

        required_a0 = {
            "crossing_candidate_id", "lat", "lon", "osm_way_ids",
            "osm_highway", "motor_vehicle_access_class", "materiality_screen",
        }
        missing = required_a0 - set(a0.columns)
        if missing:
            raise RuntimeError(f"A0 missing required columns: {sorted(missing)}")

        a0 = a0.copy()
        a0["_geo"] = a0["crossing_candidate_id"].map(normalize_geo_id)
        if (a0["_geo"] == "").any():
            raise RuntimeError("A0 contains unparseable crossing_candidate_id")

        dup = a0["_geo"].duplicated(keep=False)
        if dup.any():
            raise RuntimeError(
                "A0 duplicate GEO identifiers: "
                + ",".join(sorted(a0.loc[dup, "_geo"].unique()))
            )

        a0_by_geo = a0.set_index("_geo", drop=False)
        requested_geos = [g for gs in A1_VENETO.values() for g in gs]
        if len(requested_geos) != 49 or len(set(requested_geos)) != 49:
            raise RuntimeError("Embedded A1 Veneto mapping must contain 49 unique GEO groups")

        missing_geos = sorted(set(requested_geos) - set(a0_by_geo.index))
        if missing_geos:
            raise RuntimeError("A1 GEO groups missing from A0: " + ",".join(missing_geos))

        gateway_by_geo = {
            geo: gateway
            for gateway, geos in A1_VENETO.items()
            for geo in geos
        }

        geo_way_ids: dict[str, set[int]] = {}
        for geo in requested_geos:
            ids = extract_way_ids(a0_by_geo.loc[geo, "osm_way_ids"])
            if not ids:
                raise RuntimeError(f"No osm_way_ids parsed for {geo}")
            geo_way_ids[geo] = ids

        target_way_ids = sorted(set().union(*geo_way_ids.values()))
        print(f"Veneto gateways       = {len(A1_VENETO)}")
        print(f"Raw GEO groups        = {len(requested_geos)}")
        print(f"Unique target way IDs = {len(target_way_ids)}")
        print("A0 way source         = osm_way_ids ONLY")

        # ------------------------------------------------------------------
        # C. B2 targeted interface.
        # ------------------------------------------------------------------
        print()
        print("C. B2 TARGETED INTERFACE")
        b2_edges, b2_coords = query_b2(paths["b2"], target_way_ids)
        b2_edges["way_id"] = pd.to_numeric(b2_edges["way_id"], errors="raise").astype("int64")
        core_edges = b2_edges.loc[
            (pd.to_numeric(b2_edges["routing_code"], errors="coerce") == 1)
            & (pd.to_numeric(b2_edges["core_eligible"], errors="coerce") == 1)
        ].copy()

        b2_all_ways = set(b2_edges["way_id"].astype(int).tolist())
        b2_core_ways = set(core_edges["way_id"].astype(int).tolist())

        print(f"B2 target ways present = {len(b2_all_ways)}/{len(target_way_ids)}")
        print(f"B2 CORE ways           = {len(b2_core_ways)}/{len(target_way_ids)}")
        print(f"B2 CORE directed edges = {len(core_edges)}")
        print(f"B2 endpoint coords     = {len(b2_coords)}")

        # Build B2 CORE node sets per way.
        b2_core_nodes_by_way: dict[int, set[int]] = defaultdict(set)
        for row in core_edges.itertuples(index=False):
            b2_core_nodes_by_way[int(row.way_id)].add(int(row.u))
            b2_core_nodes_by_way[int(row.way_id)].add(int(row.v))

        # ------------------------------------------------------------------
        # D. Targeted PBF scans.
        # ------------------------------------------------------------------
        print()
        print("D. TARGETED PBF WAY SCANS")
        target_set = set(target_way_ids)

        print("Scanning frozen Nord-Est PBF...")
        frozen_ways = scan_target_ways(paths["frozen_pbf"], target_set)
        print(f"Frozen target ways found = {len(frozen_ways)}/{len(target_way_ids)}")

        print("Scanning Italy support PBF...")
        italy_ways = scan_target_ways(paths["italy_pbf"], target_set)
        print(f"Italy target ways found  = {len(italy_ways)}/{len(target_way_ids)}")

        # ------------------------------------------------------------------
        # E. Cross-snapshot way-level audit.
        # ------------------------------------------------------------------
        print()
        print("E. CROSS-SNAPSHOT WAY AUDIT")

        way_to_geos: dict[int, list[str]] = defaultdict(list)
        for geo, ids in geo_way_ids.items():
            for wid in ids:
                way_to_geos[wid].append(geo)

        way_rows = []
        core_way_absent_italy = []
        core_way_no_shared_b2_node = []

        for wid in target_way_ids:
            fw = frozen_ways.get(wid)
            iw = italy_ways.get(wid)
            frozen_nodes = set(fw["node_ids"]) if fw else set()
            italy_nodes = set(iw["node_ids"]) if iw else set()
            b2_nodes = b2_core_nodes_by_way.get(wid, set())

            shared_nodes = frozen_nodes & italy_nodes
            shared_b2_nodes = b2_nodes & italy_nodes & frozen_nodes

            if wid in b2_core_ways and iw is None:
                core_way_absent_italy.append(wid)
            if wid in b2_core_ways and not shared_b2_nodes:
                core_way_no_shared_b2_node.append(wid)

            same_sequence = bool(
                fw is not None
                and iw is not None
                and fw["node_ids"] == iw["node_ids"]
            )
            same_tags = bool(
                fw is not None
                and iw is not None
                and fw["tags"] == iw["tags"]
            )

            way_rows.append({
                "way_id": wid,
                "gateways": "|".join(sorted({gateway_by_geo[g] for g in way_to_geos[wid]})),
                "geo_groups": "|".join(sorted(way_to_geos[wid])),
                "b2_present": wid in b2_all_ways,
                "b2_core": wid in b2_core_ways,
                "b2_core_node_count": len(b2_nodes),
                "frozen_present": fw is not None,
                "italy_present": iw is not None,
                "frozen_version": fw["version"] if fw else np.nan,
                "italy_version": iw["version"] if iw else np.nan,
                "frozen_node_count": len(fw["node_ids"]) if fw else 0,
                "italy_node_count": len(iw["node_ids"]) if iw else 0,
                "same_node_sequence": same_sequence,
                "same_selected_tags": same_tags,
                "shared_node_count": len(shared_nodes),
                "shared_b2_core_node_count": len(shared_b2_nodes),
                "frozen_highway": fw["tags"]["highway"] if fw else "",
                "italy_highway": iw["tags"]["highway"] if iw else "",
                "frozen_ref": fw["tags"]["ref"] if fw else "",
                "italy_ref": iw["tags"]["ref"] if iw else "",
                "frozen_name": fw["tags"]["name"] if fw else "",
                "italy_name": iw["tags"]["name"] if iw else "",
            })

        way_df = pd.DataFrame(way_rows)
        print(f"B2 CORE ways absent in Italy       = {len(core_way_absent_italy)}")
        print(f"B2 CORE ways with no shared B2 node= {len(core_way_no_shared_b2_node)}")
        print(
            "B2 CORE exact node-sequence equal  = "
            f"{int(way_df.loc[way_df.b2_core, 'same_node_sequence'].sum())}/"
            f"{int(way_df.b2_core.sum())}"
        )

        # ------------------------------------------------------------------
        # F. GEO-level anchor audit.
        # ------------------------------------------------------------------
        print()
        print("F. GEO-LEVEL EXACT SHARED ANCHOR AUDIT")

        geo_rows = []
        anchor_distance_warnings = []

        for geo in requested_geos:
            row = a0_by_geo.loc[geo]
            gateway = gateway_by_geo[geo]
            ids = geo_way_ids[geo]

            core_ids = sorted(ids & b2_core_ways)
            candidate_nodes: set[int] = set()

            for wid in core_ids:
                fw = frozen_ways.get(wid)
                iw = italy_ways.get(wid)
                if fw is None or iw is None:
                    continue
                candidate_nodes |= (
                    b2_core_nodes_by_way.get(wid, set())
                    & set(fw["node_ids"])
                    & set(iw["node_ids"])
                )

            ranked = []
            a0_lon = float(row["lon"])
            a0_lat = float(row["lat"])
            for nid in sorted(candidate_nodes):
                coord = b2_coords.get(nid)
                if coord is None:
                    continue
                lon, lat = coord
                ranked.append((haversine_m(a0_lon, a0_lat, lon, lat), nid, lon, lat))

            ranked.sort()
            if ranked:
                best_dist, best_node, best_lon, best_lat = ranked[0]
                status = "SHARED_EXACT_B2_CORE_ANCHOR"
                if best_dist > ANCHOR_DISTANCE_WARNING_M:
                    anchor_distance_warnings.append((geo, best_dist))
            elif not core_ids:
                best_dist = np.nan
                best_node = np.nan
                best_lon = np.nan
                best_lat = np.nan
                status = "NO_B2_CORE_COMPONENT"
            else:
                best_dist = np.nan
                best_node = np.nan
                best_lon = np.nan
                best_lat = np.nan
                status = "B2_CORE_BUT_NO_SHARED_ANCHOR"

            geo_rows.append({
                "gateway_id": gateway,
                "geo_id": geo,
                "a0_lon": a0_lon,
                "a0_lat": a0_lat,
                "a0_highway": row.get("osm_highway", ""),
                "a0_access_class": row.get("motor_vehicle_access_class", ""),
                "a0_materiality": row.get("materiality_screen", ""),
                "a0_way_count_targeted": len(ids),
                "b2_core_way_count": len(core_ids),
                "shared_anchor_candidate_count": len(ranked),
                "best_anchor_node_id": best_node,
                "best_anchor_lon": best_lon,
                "best_anchor_lat": best_lat,
                "best_anchor_distance_m": best_dist,
                "status": status,
            })

        geo_df = pd.DataFrame(geo_rows)
        print(geo_df["status"].value_counts(dropna=False).to_string())
        print(f"Anchor distance warnings > {ANCHOR_DISTANCE_WARNING_M:.0f} m = {len(anchor_distance_warnings)}")

        # ------------------------------------------------------------------
        # G. Gateway-level viability.
        # ------------------------------------------------------------------
        print()
        print("G. GATEWAY-LEVEL HYBRID ANCHOR VIABILITY")

        gateway_rows = []
        gateway_failures = []

        for gateway, geos in A1_VENETO.items():
            sub = geo_df.loc[geo_df["geo_id"].isin(geos)].copy()
            routable = sub.loc[sub["b2_core_way_count"] > 0]
            anchored = sub.loc[sub["status"] == "SHARED_EXACT_B2_CORE_ANCHOR"]
            routable_unanchored = routable.loc[
                routable["status"] != "SHARED_EXACT_B2_CORE_ANCHOR"
            ]

            viable = len(anchored) > 0 and len(routable_unanchored) == 0
            status = "PASS" if viable else "NOT_READY"
            if not viable:
                gateway_failures.append(gateway)

            distances = pd.to_numeric(
                anchored["best_anchor_distance_m"], errors="coerce"
            ).dropna()

            gateway_rows.append({
                "gateway_id": gateway,
                "geo_groups": len(geos),
                "geo_with_b2_core": len(routable),
                "geo_with_shared_anchor": len(anchored),
                "routable_geo_without_anchor": len(routable_unanchored),
                "min_anchor_distance_m": float(distances.min()) if len(distances) else np.nan,
                "max_anchor_distance_m": float(distances.max()) if len(distances) else np.nan,
                "status": status,
            })

        gateway_df = pd.DataFrame(gateway_rows)
        print(gateway_df.to_string(index=False))

        # ------------------------------------------------------------------
        # H. Gate decision.
        # ------------------------------------------------------------------
        print()
        print("H. GATE DECISION")

        failure_codes = []
        warning_codes = []

        if core_way_absent_italy:
            failure_codes.append("B2_CORE_TARGET_WAY_ABSENT_IN_ITALY")
        if core_way_no_shared_b2_node:
            failure_codes.append("B2_CORE_TARGET_WAY_NO_EXACT_SHARED_NODE")
        if gateway_failures:
            failure_codes.append("VENETO_GATEWAY_WITHOUT_COMPLETE_ROUTABLE_GEO_ANCHOR")

        non_b2_target_ways = sorted(set(target_way_ids) - b2_core_ways)
        if non_b2_target_ways:
            warning_codes.append("A0_TARGET_WAYS_OUTSIDE_B2_CORE")
        if anchor_distance_warnings:
            warning_codes.append("ANCHOR_DISTANCE_GT_1000M")
        changed_core_sequences = way_df.loc[
            way_df["b2_core"] & ~way_df["same_node_sequence"], "way_id"
        ].astype(int).tolist()
        if changed_core_sequences:
            warning_codes.append("B2_CORE_WAY_NODE_SEQUENCE_CHANGED_BETWEEN_SNAPSHOTS")
        changed_core_tags = way_df.loc[
            way_df["b2_core"] & ~way_df["same_selected_tags"], "way_id"
        ].astype(int).tolist()
        if changed_core_tags:
            warning_codes.append("B2_CORE_WAY_SELECTED_TAGS_CHANGED_BETWEEN_SNAPSHOTS")

        verdict = "PASS" if not failure_codes else "NOT_READY"

        print(f"TARGETED_SHARED_BOUNDARY_TOPOLOGY = {verdict}")
        print(f"failure codes = {len(failure_codes)}")
        print(f"warning codes = {len(warning_codes)}")

        # ------------------------------------------------------------------
        # I. Materialize diagnostic evidence only.
        # ------------------------------------------------------------------
        print()
        print("I. MATERIALIZE DIAGNOSTIC EVIDENCE")

        staging.mkdir(parents=True, exist_ok=False)

        way_path = staging / WAY_AUDIT
        geo_path = staging / GEO_AUDIT
        gateway_path = staging / GATEWAY_AUDIT
        summary_path = staging / SUMMARY_JSON
        manifest_path = staging / MANIFEST_JSON

        way_df.to_csv(way_path, index=False, encoding="utf-8")
        geo_df.to_csv(geo_path, index=False, encoding="utf-8")
        gateway_df.to_csv(gateway_path, index=False, encoding="utf-8")

        summary = {
            "schema": "B1_EXT_SHARED_BOUNDARY_TOPOLOGY_SUMMARY_V01",
            "verdict": verdict,
            "architecture": {
                "internal_router": "B5_FROZEN",
                "external_router": "GRAPHHOPPER_11_CANDIDATE",
                "composition_target": "PHYSICAL_CROSSING_MIN_COMBINED_TIME",
                "graphhopper_import": "NOT_STARTED",
                "routing": "NOT_STARTED",
            },
            "scope": {
                "veneto_modelling_gateways": len(A1_VENETO),
                "a1_raw_geo_groups": len(requested_geos),
                "a0_unique_target_way_ids": len(target_way_ids),
                "b2_target_ways_present": len(b2_all_ways),
                "b2_core_target_ways": len(b2_core_ways),
            },
            "cross_snapshot": {
                "frozen_target_ways_found": len(frozen_ways),
                "italy_target_ways_found": len(italy_ways),
                "b2_core_way_absent_in_italy": core_way_absent_italy,
                "b2_core_way_no_exact_shared_node": core_way_no_shared_b2_node,
                "b2_core_way_node_sequence_changed": changed_core_sequences,
                "b2_core_way_selected_tags_changed": changed_core_tags,
            },
            "geo_anchor_status_counts": {
                str(k): int(v)
                for k, v in geo_df["status"].value_counts().to_dict().items()
            },
            "gateway_status_counts": {
                str(k): int(v)
                for k, v in gateway_df["status"].value_counts().to_dict().items()
            },
            "gateway_failures": gateway_failures,
            "non_b2_core_target_way_ids": non_b2_target_ways,
            "anchor_distance_warning_threshold_m": ANCHOR_DISTANCE_WARNING_M,
            "anchor_distance_warnings": [
                {"geo_id": g, "distance_m": d}
                for g, d in anchor_distance_warnings
            ],
            "failure_codes": failure_codes,
            "warning_codes": warning_codes,
            "hard_stop": {
                "graph_import": "NOT_STARTED",
                "routing": "NOT_STARTED",
                "frozen_artifacts_modified": False,
            },
        }
        write_json(summary_path, summary)

        outputs = []
        for p in [way_path, geo_path, gateway_path, summary_path]:
            outputs.append({
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            })

        manifest = {
            "schema": "B1_EXT_SHARED_BOUNDARY_TOPOLOGY_MANIFEST_V01",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                key: {
                    "path": str(paths[key]),
                    "sha256": EXPECTED_SHA256[key][1],
                }
                for key in EXPECTED_SHA256
            },
            "a1_veneto_mapping": A1_VENETO,
            "target_way_source": "A0.osm_way_ids_ONLY",
            "outputs": outputs,
            "verdict": verdict,
            "failure_codes": failure_codes,
            "warning_codes": warning_codes,
            "hard_stop": {
                "graph_import": "NOT_STARTED",
                "routing": "NOT_STARTED",
                "frozen_artifacts_modified": False,
            },
        }
        write_json(manifest_path, manifest)

        print(f"Staging = {staging}")
        print(f"Final   = {final_dir}")

        staging.rename(final_dir)

        print(f"{WAY_AUDIT} SHA256 = {sha256(final_dir / WAY_AUDIT)}")
        print(f"{GEO_AUDIT} SHA256 = {sha256(final_dir / GEO_AUDIT)}")
        print(f"{GATEWAY_AUDIT} SHA256 = {sha256(final_dir / GATEWAY_AUDIT)}")
        print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
        print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")

        # ------------------------------------------------------------------
        # J. Final report / hard stop.
        # ------------------------------------------------------------------
        print()
        print("=" * 122)
        print(f"B1_EXT_GH_03_TARGETED_TOPOLOGY = {verdict}")
        print(f"VENETO_GATEWAYS = {len(A1_VENETO)}")
        print(f"A1_RAW_GEO_GROUPS = {len(requested_geos)}")
        print(f"TARGET_WAYS_A0_OSM_WAY_IDS_ONLY = {len(target_way_ids)}")
        print(f"B2_CORE_TARGET_WAYS = {len(b2_core_ways)}")
        print(f"B2_CORE_WAYS_ABSENT_IN_ITALY = {len(core_way_absent_italy)}")
        print(f"B2_CORE_WAYS_NO_EXACT_SHARED_NODE = {len(core_way_no_shared_b2_node)}")
        print(f"GATEWAY_FAILURES = {len(gateway_failures)}")
        print(f"WARNINGS = {len(warning_codes)}")
        if failure_codes:
            print("FAILURE_CODES = " + "|".join(failure_codes))
        if warning_codes:
            print("WARNING_CODES = " + "|".join(warning_codes))
        print("GRAPH_IMPORT = NOT_STARTED")
        print("ROUTING = NOT_STARTED")
        print("FROZEN_ARTIFACTS_MODIFIED = NO")
        print(
            "NEXT_GATE = "
            + (
                "GRAPHHOPPER_PROFILE_AND_IMPORT_PREFLIGHT"
                if verdict == "PASS"
                else "REVIEW_TARGETED_TOPOLOGY_FLAGS"
            )
        )
        print("=== RUN COMPLETATA ===")

        return 0 if verdict == "PASS" else 2

    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
