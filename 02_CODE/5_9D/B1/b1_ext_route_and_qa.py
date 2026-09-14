from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmium
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import transform as shp_transform


DAILY_FACTOR = 0.42855
EXPECTED_OD_ROWS = 2895
EXPECTED_DEDUP_SHA256 = "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe"
EXPECTED_GOSM_SHA256 = "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3"

# Frozen A1 modelling-cordon mapping. Sensitivity-only / excluded physical
# crossings are intentionally absent: if a routed path uses one, it is flagged
# rather than silently reassigned.
GATEWAY_TO_PHYSICAL = {
    "AT01": ["GEO_0842"],
    "AT02": ["GEO_0832"],
    "AT03": ["GEO_0575"],
    "AT04": ["GEO_0411"],

    "VE01": ["GEO_0468", "GEO_0475", "GEO_0484"],
    "VE02": ["GEO_0353", "GEO_0354", "GEO_0345", "GEO_0350", "GEO_0352", "GEO_0357", "GEO_0360", "GEO_0369"],
    "VE03": ["GEO_0196", "GEO_0195", "GEO_0197", "GEO_0199", "GEO_0201"],
    "VE04": ["GEO_0154", "GEO_0098", "GEO_0099", "GEO_0203", "GEO_0205"],
    "VE05": ["GEO_0486"],
    "VE06": ["GEO_0004"],
    "A1V01": ["GEO_0198"],
    "A1V02": ["GEO_0263"],
    "A1V03": ["GEO_0228", "GEO_0213", "GEO_0215", "GEO_0227", "GEO_0229", "GEO_0231", "GEO_0255", "GEO_0256", "GEO_0269"],
    "A1V04": ["GEO_0293", "GEO_0304", "GEO_0273", "GEO_0287", "GEO_0307", "GEO_0315", "GEO_0323"],
    "A1V05": ["GEO_0391", "GEO_0402", "GEO_0373", "GEO_0375", "GEO_0385", "GEO_0399", "GEO_0405"],
    "A1V06": ["GEO_0500"],

    "SI01": ["GEO_0910", "GEO_0887"],
    "SI02": ["GEO_1130", "GEO_1129"],
    "SI03": ["GEO_1109"],
    "SI04": ["GEO_1191", "GEO_1141", "GEO_1157"],
    "SI05": ["GEO_0694"],
    "SI06": ["GEO_1011"],
    "SI07": ["GEO_0766"],
    "SI08": ["GEO_0954", "GEO_0902", "GEO_0937", "GEO_0948", "GEO_0951", "GEO_0966"],
    "A1S01": ["GEO_0692", "GEO_0716", "GEO_0768", "GEO_0802", "GEO_0814"],
    "A1S02": ["GEO_0836", "GEO_0879"],
    "A1S03": ["GEO_1045", "GEO_1051", "GEO_1066"],
    "A1S04": ["GEO_1170"],
}
PHYSICAL_TO_GATEWAY = {
    physical: gateway
    for gateway, physicals in GATEWAY_TO_PHYSICAL.items()
    for physical in physicals
}


def sha256(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm_code(v) -> int:
    if pd.isna(v):
        raise ValueError("null PRO_COM")
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(float(s))


def pick_col(df: pd.DataFrame, candidates: list[str], role: str) -> str:
    direct = {str(c).lower(): str(c) for c in df.columns}
    for c in candidates:
        if c.lower() in direct:
            return direct[c.lower()]
    # relaxed alnum normalization
    def n(x: str) -> str:
        return "".join(ch for ch in x.lower() if ch.isalnum())
    nd = {n(str(c)): str(c) for c in df.columns}
    for c in candidates:
        if n(c) in nd:
            return nd[n(c)]
    raise KeyError(f"Cannot detect {role}. columns={list(df.columns)}")


def http_json(url: str, timeout: int = 120, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"HTTP failed after {retries} attempts: {url}: {last}")


def osrm_nearest(server: str, lon: float, lat: float) -> dict:
    url = f"{server.rstrip('/')}/nearest/v1/driving/{lon:.8f},{lat:.8f}?number=1"
    obj = http_json(url)
    if obj.get("code") != "Ok" or not obj.get("waypoints"):
        raise RuntimeError(f"nearest failed: {obj}")
    w = obj["waypoints"][0]
    return {
        "snap_lon": float(w["location"][0]),
        "snap_lat": float(w["location"][1]),
        "snap_distance_m": float(w.get("distance", math.nan)),
        "snap_name": w.get("name", ""),
    }


def osrm_route(server: str, a: tuple[float, float], b: tuple[float, float]) -> dict:
    lon1, lat1 = a
    lon2, lat2 = b
    query = urllib.parse.urlencode({
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "annotations": "nodes,duration,distance",
    })
    url = (
        f"{server.rstrip('/')}/route/v1/driving/"
        f"{lon1:.8f},{lat1:.8f};{lon2:.8f},{lat2:.8f}?{query}"
    )
    obj = http_json(url, timeout=180, retries=3)
    if obj.get("code") != "Ok" or not obj.get("routes"):
        return {"routing_status": "UNREACHABLE", "raw": obj}
    r = obj["routes"][0]
    leg = r["legs"][0]
    ann = leg.get("annotation") or {}
    nodes = [int(x) for x in ann.get("nodes", [])]
    distances = [float(x) for x in ann.get("distance", [])]
    durations = [float(x) for x in ann.get("duration", [])]
    coords = [(float(x), float(y)) for x, y in r["geometry"]["coordinates"]]
    return {
        "routing_status": "ROUTED",
        "distance_m": float(r["distance"]),
        "duration_s": float(r["duration"]),
        "nodes": nodes,
        "edge_distances": distances,
        "edge_durations": durations,
        "coords": coords,
    }


def point_events_from_intersection(g):
    if g.is_empty:
        return []
    typ = g.geom_type
    if typ == "Point":
        return [g]
    if typ == "MultiPoint":
        return list(g.geoms)
    if typ in ("LineString", "LinearRing"):
        coords = list(g.coords)
        return [Point(coords[0]), Point(coords[-1])] if coords else []
    if typ == "MultiLineString":
        out = []
        for p in g.geoms:
            out.extend(point_events_from_intersection(p))
        return out
    if typ == "GeometryCollection":
        out = []
        for p in g.geoms:
            out.extend(point_events_from_intersection(p))
        return out
    return []


def crossing_for_route(coords_wgs84, boundary_32632, direction: str, to_32632):
    if len(coords_wgs84) < 2:
        return None, "NO_GEOMETRY", 0
    line_wgs = LineString(coords_wgs84)
    line = shp_transform(to_32632.transform, line_wgs)
    inter = line.intersection(boundary_32632.boundary)
    pts = point_events_from_intersection(inter)
    if not pts:
        return None, "NO_BOUNDARY_INTERSECTION", 0
    pts = sorted(pts, key=line.project)
    events = []
    total = line.length
    for p in pts:
        d = line.project(p)
        eps = min(8.0, max(2.0, total * 1e-5))
        before = line.interpolate(max(0.0, d - eps))
        after = line.interpolate(min(total, d + eps))
        b_in = boundary_32632.covers(before)
        a_in = boundary_32632.covers(after)
        events.append((d, p, b_in, a_in))
    chosen = None
    if direction == "IE":
        for ev in events:
            if ev[2] and not ev[3]:
                chosen = ev
                break
    else:
        for ev in reversed(events):
            if not ev[2] and ev[3]:
                chosen = ev
                break
    status = "TRANSITION_CONFIRMED"
    if chosen is None:
        chosen = events[0] if direction == "IE" else events[-1]
        status = "TRANSITION_UNCERTAIN"
    return chosen[1], status, len(events)


def find_lat_lon_cols(df: pd.DataFrame):
    lower = {c.lower(): c for c in df.columns}
    lat_candidates = [
        "representative_lat", "centroid_lat", "lat", "latitude",
        "crossing_lat", "mean_lat", "rep_lat",
    ]
    lon_candidates = [
        "representative_lon", "centroid_lon", "lon", "longitude",
        "crossing_lon", "mean_lon", "rep_lon",
    ]
    lat = next((lower[x] for x in lat_candidates if x in lower), None)
    lon = next((lower[x] for x in lon_candidates if x in lower), None)
    if lat is None:
        lat = next((c for c in df.columns if "lat" in c.lower()), None)
    if lon is None:
        lon = next((c for c in df.columns if "lon" in c.lower()), None)
    if lat is None or lon is None:
        raise KeyError(f"Could not detect lat/lon columns in dedup CSV: {list(df.columns)}")
    return lat, lon


def find_crossing_id_col(df: pd.DataFrame):
    for c in ["physical_crossing_id", "crossing_id", "geo_id", "group_id"]:
        if c in df.columns:
            return c
    for c in df.columns:
        vals = df[c].dropna().astype(str).head(100)
        if len(vals) and vals.str.match(r"^GEO_\d{4}$").mean() > 0.7:
            return c
    raise KeyError(f"Could not detect GEO crossing id column: {list(df.columns)}")


def make_gateway_map_csv(out: Path):
    rows = []
    for gateway, ids in GATEWAY_TO_PHYSICAL.items():
        for pid in ids:
            rows.append({
                "physical_crossing_id": pid,
                "assigned_modelling_gateway_id": gateway,
                "mapping_source": "FASE_5_9D_A1_FROZEN",
            })
    pd.DataFrame(rows).sort_values(
        ["assigned_modelling_gateway_id", "physical_crossing_id"]
    ).to_csv(out, index=False)


class SelectedNodeHandler(osmium.SimpleHandler):
    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.coords = {}

    def node(self, n):
        nid = int(n.id)
        if nid in self.wanted and n.location.valid():
            self.coords[nid] = (float(n.location.lon), float(n.location.lat))


class TopWayHandler(osmium.SimpleHandler):
    def __init__(self, wanted_pairs):
        super().__init__()
        self.wanted = wanted_pairs
        self.matches = defaultdict(list)

    def way(self, w):
        if "highway" not in w.tags:
            return
        refs = [int(n.ref) for n in w.nodes]
        if len(refs) < 2:
            return
        tags = {
            "way_id": int(w.id),
            "highway": w.tags.get("highway", ""),
            "ref": w.tags.get("ref", ""),
            "name": w.tags.get("name", ""),
            "oneway": w.tags.get("oneway", ""),
            "junction": w.tags.get("junction", ""),
            "access": w.tags.get("access", ""),
            "motor_vehicle": w.tags.get("motor_vehicle", ""),
        }
        for a, b in zip(refs[:-1], refs[1:]):
            if (a, b) in self.wanted:
                self.matches[(a, b)].append((tags, "WAY_FORWARD"))
            if (b, a) in self.wanted:
                self.matches[(b, a)].append((tags, "WAY_REVERSE"))


def direction_compatible(tags: dict, orientation: str) -> bool:
    oneway = str(tags.get("oneway", "")).strip().lower()
    hwy = str(tags.get("highway", "")).strip().lower()
    junction = str(tags.get("junction", "")).strip().lower()
    if oneway in {"yes", "1", "true"}:
        return orientation == "WAY_FORWARD"
    if oneway == "-1":
        return orientation == "WAY_REVERSE"
    if oneway in {"no", "0", "false"}:
        return True
    if junction in {"roundabout", "circular"} or hwy in {"motorway", "motorway_link"}:
        return orientation == "WAY_FORWARD"
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-gpkg", type=Path, required=True)
    ap.add_argument("--dedup-csv", type=Path, required=True)
    ap.add_argument("--gosm-gpkg", type=Path, required=True)
    ap.add_argument("--pbf", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--server", default="http://127.0.0.1:5005")
    args = ap.parse_args()

    t0 = time.time()
    out = args.outdir
    out.mkdir(parents=True, exist_ok=False)

    if sha256(args.dedup_csv) != EXPECTED_DEDUP_SHA256:
        raise RuntimeError("A0 dedup SHA256 mismatch")
    if sha256(args.gosm_gpkg) != EXPECTED_GOSM_SHA256:
        raise RuntimeError("Frozen G_OSM GPKG SHA256 mismatch")

    # Basic server health.
    health = http_json(
        f"{args.server.rstrip('/')}/nearest/v1/driving/13.2380,46.0679?number=1",
        timeout=30,
        retries=2,
    )
    if health.get("code") != "Ok":
        raise RuntimeError(f"OSRM server not healthy: {health}")

    # Read project OD and centroids without changing their semantics.
    od = pyogrio.read_dataframe(
        args.base_gpkg,
        layer="pendolari_extra_regione_fvg_2021_od_xy",
        read_geometry=False,
    )
    if len(od) != EXPECTED_OD_ROWS:
        raise RuntimeError(f"OD_ROWS={len(od)} expected={EXPECTED_OD_ROWS}")

    fvg_key = pick_col(
        od,
        ["Procom_FVG", "Procom_res", "origin_PRO_COM", "PRO_COM_FVG", "procom_fvg"],
        "OD FVG PRO_COM",
    )
    ext_key = pick_col(
        od,
        ["Procom_esterno", "Procom_lav", "destination_PRO_COM", "PRO_COM_EST", "procom_esterno"],
        "OD external PRO_COM",
    )
    commuters_col = pick_col(
        od,
        ["Pendolari", "Pendolari_uscita", "commuters"],
        "commuters",
    )

    fvg_cent = pyogrio.read_dataframe(
        args.base_gpkg, layer="centroidi_popolazione_comuni_fvg_final"
    )
    ita_cent = pyogrio.read_dataframe(
        args.base_gpkg, layer="centroidi_geometrici_italia_2026_xy"
    )
    if fvg_cent.crs is None or ita_cent.crs is None:
        raise RuntimeError("Centroid CRS missing")

    fvg_cent = fvg_cent.to_crs(4326)
    ita_cent = ita_cent.to_crs(4326)
    fvg_cent_key = pick_col(fvg_cent, ["PRO_COM", "Procom", "pro_com"], "FVG centroid PRO_COM")
    ita_cent_key = pick_col(ita_cent, ["PRO_COM", "Procom", "pro_com"], "Italy centroid PRO_COM")

    fvg_map = {
        norm_code(r[fvg_cent_key]): (float(r.geometry.x), float(r.geometry.y))
        for _, r in fvg_cent.iterrows()
    }
    ita_map = {
        norm_code(r[ita_cent_key]): (float(r.geometry.x), float(r.geometry.y))
        for _, r in ita_cent.iterrows()
    }

    od = od.copy()
    od["_fvg"] = od[fvg_key].map(norm_code)
    od["_ext"] = od[ext_key].map(norm_code)
    od["_commuters"] = pd.to_numeric(od[commuters_col], errors="raise").astype(float)
    od["_flow_daily"] = od["_commuters"] * DAILY_FACTOR

    missing_o = od.loc[~od["_fvg"].isin(fvg_map), "_fvg"].unique().tolist()
    missing_d = od.loc[~od["_ext"].isin(ita_map), "_ext"].unique().tolist()
    if missing_o or missing_d:
        raise RuntimeError(f"Centroid join missing origin={missing_o[:10]} dest={missing_d[:10]}")

    # Boundary.
    boundary = pyogrio.read_dataframe(args.base_gpkg, layer="confine_fvg_dissolto")
    if len(boundary) != 1 or boundary.crs is None:
        raise RuntimeError("Invalid confine_fvg_dissolto")
    boundary_32632 = boundary.to_crs(32632).geometry.iloc[0]
    to_32632 = Transformer.from_crs(4326, 32632, always_xy=True)
    to_4326 = Transformer.from_crs(32632, 4326, always_xy=True)

    # Physical crossings.
    cross = pd.read_csv(args.dedup_csv)
    cid_col = find_crossing_id_col(cross)
    lat_col, lon_col = find_lat_lon_cols(cross)
    cross["_cid"] = cross[cid_col].astype(str)
    cross["_lat"] = pd.to_numeric(cross[lat_col], errors="coerce")
    cross["_lon"] = pd.to_numeric(cross[lon_col], errors="coerce")
    access_col = next(
        (c for c in cross.columns if c.lower() in {"access_class", "access_status"}),
        None,
    )
    open_cross = cross.dropna(subset=["_lat", "_lon"]).copy()
    if access_col:
        open_cross = open_cross[
            open_cross[access_col].astype(str).isin(["OPEN_ORDINARY", "OPEN_LOCAL"])
        ].copy()
    xs, ys = to_32632.transform(
        open_cross["_lon"].to_numpy(), open_cross["_lat"].to_numpy()
    )
    open_cross["_x"] = xs
    open_cross["_y"] = ys
    cross_xy = open_cross[["_x", "_y"]].to_numpy()
    cross_ids = open_cross["_cid"].to_numpy(dtype=object)

    def nearest_open_crossing(p32632: Point):
        dx = cross_xy[:, 0] - p32632.x
        dy = cross_xy[:, 1] - p32632.y
        d2 = dx * dx + dy * dy
        i = int(np.argmin(d2))
        return str(cross_ids[i]), float(math.sqrt(float(d2[i])))

    # Freeze mapping artifact.
    make_gateway_map_csv(out / "gateway_mapping_frozen_A1_v01.csv")

    # Deterministic endpoint snapping.
    endpoint_rows = []
    snap = {}
    unique_fvg = sorted(set(od["_fvg"]))
    unique_ext = sorted(set(od["_ext"]))
    for kind, codes, cmap in [
        ("FVG", unique_fvg, fvg_map),
        ("EXTERNAL_ITALY", unique_ext, ita_map),
    ]:
        for code in codes:
            lon, lat = cmap[code]
            try:
                n = osrm_nearest(args.server, lon, lat)
                status = "SNAPPED"
            except Exception as e:
                n = {
                    "snap_lon": math.nan,
                    "snap_lat": math.nan,
                    "snap_distance_m": math.nan,
                    "snap_name": "",
                }
                status = f"SNAP_FAILED:{e}"
            rec = {
                "endpoint_type": kind,
                "PRO_COM": code,
                "input_lon": lon,
                "input_lat": lat,
                **n,
                "snap_status": status,
                "snap_flag": (
                    "GROSS_GT10KM" if n["snap_distance_m"] > 10000
                    else "WARNING_GT5KM" if n["snap_distance_m"] > 5000
                    else "OK"
                ) if math.isfinite(n["snap_distance_m"]) else "FAILED",
            }
            endpoint_rows.append(rec)
            if status == "SNAPPED":
                snap[(kind, code)] = (n["snap_lon"], n["snap_lat"])

    endpoint_df = pd.DataFrame(endpoint_rows)
    endpoint_df.to_csv(out / "endpoint_snap_table.csv", index=False)

    ext_covered_codes = {
        int(r.PRO_COM) for r in endpoint_df.itertuples()
        if r.endpoint_type == "EXTERNAL_ITALY" and r.snap_status == "SNAPPED"
    }
    endpoint_coverage_rows = int(od["_ext"].isin(ext_covered_codes).sum())

    # Routing and edge-use accumulation.
    routes = []
    crossing_rows = []
    flagged_geoms = []
    edge_stats = {}
    used_node_ids = set()

    def edge_acc(pair, dist, dur, direction, raw_mass, daily_mass):
        s = edge_stats.get(pair)
        if s is None:
            s = {
                "u": int(pair[0]), "v": int(pair[1]),
                "path_count": 0, "IE_path_count": 0, "EI_path_count": 0,
                "raw_commuter_mass": 0.0, "daily_commuting_mass": 0.0,
                "distance_m_first": float(dist),
                "distance_m_min": float(dist), "distance_m_max": float(dist),
                "duration_s_first": float(dur),
                "duration_s_min": float(dur), "duration_s_max": float(dur),
            }
            edge_stats[pair] = s
        s["path_count"] += 1
        s[f"{direction}_path_count"] += 1
        s["raw_commuter_mass"] += float(raw_mass)
        s["daily_commuting_mass"] += float(daily_mass)
        s["distance_m_min"] = min(s["distance_m_min"], float(dist))
        s["distance_m_max"] = max(s["distance_m_max"], float(dist))
        s["duration_s_min"] = min(s["duration_s_min"], float(dur))
        s["duration_s_max"] = max(s["duration_s_max"], float(dur))

    for od_idx, r in od.reset_index(drop=True).iterrows():
        fvg = int(r["_fvg"])
        ext = int(r["_ext"])
        raw_mass = float(r["_commuters"])
        daily_mass = float(r["_flow_daily"])
        for direction in ("IE", "EI"):
            if ("FVG", fvg) not in snap or ("EXTERNAL_ITALY", ext) not in snap:
                routes.append({
                    "od_index": od_idx, "direction": direction,
                    "origin_PRO_COM": fvg if direction == "IE" else ext,
                    "destination_PRO_COM": ext if direction == "IE" else fvg,
                    "Pendolari": raw_mass, "flow_daily": daily_mass,
                    "routing_status": "OUT_OF_ROUTING_COVERAGE",
                    "gateway_status": "AMBIGUOUS_GATEWAY_MAPPING",
                })
                continue
            a = snap[("FVG", fvg)] if direction == "IE" else snap[("EXTERNAL_ITALY", ext)]
            b = snap[("EXTERNAL_ITALY", ext)] if direction == "IE" else snap[("FVG", fvg)]
            rr = osrm_route(args.server, a, b)
            base = {
                "od_index": od_idx,
                "direction": direction,
                "origin_PRO_COM": fvg if direction == "IE" else ext,
                "destination_PRO_COM": ext if direction == "IE" else fvg,
                "Pendolari": raw_mass,
                "flow_daily": daily_mass,
                "origin_lon": a[0], "origin_lat": a[1],
                "destination_lon": b[0], "destination_lat": b[1],
            }
            if rr["routing_status"] != "ROUTED":
                routes.append({
                    **base,
                    "routing_status": "UNREACHABLE",
                    "gateway_status": "AMBIGUOUS_GATEWAY_MAPPING",
                })
                continue

            nodes = rr["nodes"]
            ed = rr["edge_distances"]
            et = rr["edge_durations"]
            if len(nodes) >= 2 and len(ed) == len(nodes)-1 and len(et) == len(nodes)-1:
                used_node_ids.update(nodes)
                for u, v, dd, tt in zip(nodes[:-1], nodes[1:], ed, et):
                    edge_acc((int(u), int(v)), dd, tt, direction, raw_mass, daily_mass)

            cp, cstatus, n_events = crossing_for_route(
                rr["coords"], boundary_32632, direction, to_32632
            )
            physical = ""
            physical_dist = math.nan
            gateway = ""
            gateway_status = "AMBIGUOUS_GATEWAY_MAPPING"
            cross_lon = math.nan
            cross_lat = math.nan
            if cp is not None:
                physical, physical_dist = nearest_open_crossing(cp)
                cross_lon, cross_lat = to_4326.transform(cp.x, cp.y)
                if physical_dist <= 250.0 and physical in PHYSICAL_TO_GATEWAY:
                    gateway = PHYSICAL_TO_GATEWAY[physical]
                    gateway_status = "ASSIGNED"

            straight = LineString([Point(*a), Point(*b)])
            # rough great-circle lower bound not used as a cost; only diagnostic.
            geod_m = max(
                1.0,
                math.hypot(
                    (a[0]-b[0]) * 111320.0 * math.cos(math.radians((a[1]+b[1])/2)),
                    (a[1]-b[1]) * 110540.0,
                ),
            )
            detour = rr["distance_m"] / geod_m

            rec = {
                **base,
                "shortest_path_cost_s": rr["duration_s"],
                "shortest_path_distance_m": rr["distance_m"],
                "straight_line_proxy_m": geod_m,
                "detour_ratio": detour,
                "physical_crossing_id": physical,
                "crossing_match_distance_m": physical_dist,
                "assigned_gateway_id": gateway,
                "routing_status": "ROUTED",
                "gateway_status": gateway_status,
                "boundary_transition_status": cstatus,
                "boundary_event_count": n_events,
                "crossing_lon": cross_lon,
                "crossing_lat": cross_lat,
            }
            routes.append(rec)
            crossing_rows.append({
                "od_index": od_idx,
                "direction": direction,
                "physical_crossing_id": physical,
                "assigned_gateway_id": gateway,
                "gateway_status": gateway_status,
                "crossing_match_distance_m": physical_dist,
                "boundary_transition_status": cstatus,
                "boundary_event_count": n_events,
                "crossing_lon": cross_lon,
                "crossing_lat": cross_lat,
                "Pendolari": raw_mass,
                "flow_daily": daily_mass,
            })

            gross = (detour > 3.0 and rr["distance_m"] - geod_m > 50000.0)
            if gateway_status != "ASSIGNED" or cstatus != "TRANSITION_CONFIRMED" or gross:
                flagged_geoms.append({
                    "od_index": od_idx, "direction": direction,
                    "gateway_status": gateway_status,
                    "boundary_transition_status": cstatus,
                    "physical_crossing_id": physical,
                    "assigned_gateway_id": gateway,
                    "detour_ratio": detour,
                    "Pendolari": raw_mass,
                    "flow_daily": daily_mass,
                    "geometry": LineString(rr["coords"]),
                })

        if (od_idx + 1) % 100 == 0:
            print(f"ROUTING_PROGRESS={od_idx+1}/{EXPECTED_OD_ROWS}", flush=True)

    routing_df = pd.DataFrame(routes)
    routing_df.to_csv(out / "B1_IE_EI_routing_table.csv", index=False)
    pd.DataFrame(crossing_rows).to_csv(
        out / "B1_crossing_gateway_attribution.csv", index=False
    )

    if flagged_geoms:
        gpd.GeoDataFrame(flagged_geoms, geometry="geometry", crs=4326).to_file(
            out / "B1_QGIS_flagged_paths.gpkg", layer="flagged_paths", driver="GPKG"
        )

    # Coordinates for used OSRM OSM nodes: targeted PBF pass.
    nh = SelectedNodeHandler(used_node_ids)
    nh.apply_file(str(args.pbf), locations=False)

    # Relevant subgraph = unique directed OSRM-annotation node pairs outside FVG.
    sub_rows = []
    near_boundary_pairs = set()
    missing_node_coords = 0
    for pair, s in edge_stats.items():
        u, v = pair
        cu = nh.coords.get(u)
        cv = nh.coords.get(v)
        if cu is None or cv is None:
            missing_node_coords += 1
            continue
        ux, uy = to_32632.transform(*cu)
        vx, vy = to_32632.transform(*cv)
        mid = Point((ux + vx) / 2.0, (uy + vy) / 2.0)
        outside = not boundary_32632.covers(mid)
        dist_boundary = float(mid.distance(boundary_32632.boundary))
        if dist_boundary <= 2000.0:
            near_boundary_pairs.add(pair)
        row = {
            **s,
            "u_lon": cu[0], "u_lat": cu[1],
            "v_lon": cv[0], "v_lat": cv[1],
            "midpoint_distance_to_FVG_boundary_m": dist_boundary,
            "external_edge": bool(outside),
            "near_FVG_boundary_2km": bool(dist_boundary <= 2000.0),
        }
        sub_rows.append(row)

    sub = pd.DataFrame(sub_rows)
    ext_sub = sub[sub["external_edge"]].copy() if len(sub) else sub.copy()

    # QA ranking: all boundary-near pairs + top mass/frequency pairs.
    qa_pairs = set(near_boundary_pairs)
    if len(ext_sub):
        for _, rr in ext_sub.nlargest(min(2000, len(ext_sub)), "daily_commuting_mass").iterrows():
            qa_pairs.add((int(rr["u"]), int(rr["v"])))
        for _, rr in ext_sub.nlargest(min(2000, len(ext_sub)), "path_count").iterrows():
            qa_pairs.add((int(rr["u"]), int(rr["v"])))

    wh = TopWayHandler(qa_pairs)
    wh.apply_file(str(args.pbf), locations=False)

    tag_rows = []
    direction_violations = []
    for pair in sorted(qa_pairs):
        matches = wh.matches.get(pair, [])
        compatible = any(direction_compatible(tags, orient) for tags, orient in matches)
        if matches:
            tags, orient = matches[0]
            tag_rows.append({
                "u": pair[0], "v": pair[1],
                **tags,
                "matched_orientation": orient,
                "direction_plausible_any_match": compatible,
                "n_way_matches": len(matches),
            })
        else:
            tag_rows.append({
                "u": pair[0], "v": pair[1],
                "way_id": np.nan, "highway": "", "ref": "", "name": "",
                "oneway": "", "junction": "", "access": "", "motor_vehicle": "",
                "matched_orientation": "NO_MATCH",
                "direction_plausible_any_match": False,
                "n_way_matches": 0,
            })
        if not compatible:
            direction_violations.append(pair)
    tags_df = pd.DataFrame(tag_rows)
    tags_df.to_csv(out / "B1_targeted_edge_semantic_QA.csv", index=False)

    if len(ext_sub):
        ext_sub = ext_sub.merge(
            tags_df[[
                "u", "v", "way_id", "highway", "ref", "name", "oneway",
                "junction", "direction_plausible_any_match", "n_way_matches"
            ]],
            on=["u", "v"], how="left",
        )
    with gzip.open(out / "B1_RELEVANT_ROUTING_SUBGRAPH.csv.gz", "wt", newline="", encoding="utf-8") as gz:
        ext_sub.to_csv(gz, index=False)

    # Targeted boundary interface against frozen G_OSM spatial representation.
    gosm_layer = "G_OSM_operativo_segments_v01"
    bi_rows = []
    used_cross = (
        pd.DataFrame(crossing_rows)
        .dropna(subset=["crossing_lon", "crossing_lat"])
        .drop_duplicates(subset=["physical_crossing_id", "assigned_gateway_id"])
    )
    for rr in used_cross.itertuples():
        x, y = to_32632.transform(float(rr.crossing_lon), float(rr.crossing_lat))
        p = Point(x, y)
        bbox = (x - 120.0, y - 120.0, x + 120.0, y + 120.0)
        try:
            cand = pyogrio.read_dataframe(args.gosm_gpkg, layer=gosm_layer, bbox=bbox)
        except Exception:
            cand = gpd.GeoDataFrame()
        if len(cand):
            dists = cand.geometry.distance(p)
            min_dist = float(dists.min())
            nearest_idx = dists.idxmin()
            nearest = cand.loc[nearest_idx]
            way_field = next(
                (c for c in cand.columns if c.lower() in {"way_id","osm_way_id","osm_id"}),
                None
            )
            hwy_field = next(
                (c for c in cand.columns if c.lower() == "highway"), None
            )
            nearest_way = nearest.get(way_field, "") if way_field else ""
            nearest_hwy = nearest.get(hwy_field, "") if hwy_field else ""
        else:
            min_dist = math.inf
            nearest_way = ""
            nearest_hwy = ""
        bi_rows.append({
            "physical_crossing_id": rr.physical_crossing_id,
            "assigned_gateway_id": rr.assigned_gateway_id,
            "crossing_lon": rr.crossing_lon,
            "crossing_lat": rr.crossing_lat,
            "nearest_frozen_GOSM_segment_distance_m": min_dist,
            "nearest_frozen_way_id": nearest_way,
            "nearest_frozen_highway": nearest_hwy,
            "boundary_interface_status": "PASS" if min_dist <= 30.0 else "WARNING",
        })
    bi = pd.DataFrame(bi_rows)
    bi.to_csv(out / "B1_boundary_interface_QA.csv", index=False)

    # Diagnostic flags.
    flags = []
    for rr in endpoint_df.itertuples():
        if rr.snap_flag != "OK":
            flags.append({
                "flag_type": "ENDPOINT_SNAP",
                "severity": "HIGH" if rr.snap_flag == "GROSS_GT10KM" else "REVIEW",
                "key": f"{rr.endpoint_type}:{rr.PRO_COM}",
                "detail": f"{rr.snap_flag}; distance={rr.snap_distance_m}",
            })
    for rr in routing_df.itertuples():
        if getattr(rr, "routing_status", "") != "ROUTED":
            flags.append({
                "flag_type": "ROUTING",
                "severity": "HIGH",
                "key": f"{rr.od_index}:{rr.direction}",
                "detail": getattr(rr, "routing_status", ""),
            })
            continue
        if getattr(rr, "gateway_status", "") != "ASSIGNED":
            flags.append({
                "flag_type": "GATEWAY_MAPPING",
                "severity": "HIGH",
                "key": f"{rr.od_index}:{rr.direction}",
                "detail": (
                    f"physical={getattr(rr,'physical_crossing_id','')}; "
                    f"dist={getattr(rr,'crossing_match_distance_m',math.nan)}"
                ),
            })
        if getattr(rr, "boundary_transition_status", "") != "TRANSITION_CONFIRMED":
            flags.append({
                "flag_type": "BOUNDARY_TRANSITION",
                "severity": "HIGH",
                "key": f"{rr.od_index}:{rr.direction}",
                "detail": getattr(rr, "boundary_transition_status", ""),
            })
        dr = getattr(rr, "detour_ratio", math.nan)
        if math.isfinite(dr) and dr > 3.0:
            flags.append({
                "flag_type": "GROSS_DETOUR",
                "severity": "REVIEW",
                "key": f"{rr.od_index}:{rr.direction}",
                "detail": f"detour_ratio={dr:.3f}; commuters={rr.Pendolari}",
            })
    for u, v in direction_violations:
        flags.append({
            "flag_type": "DIRECTIONALITY",
            "severity": "HIGH",
            "key": f"{u}->{v}",
            "detail": "No compatible OSM way-direction match in targeted QA pair.",
        })
    if len(bi):
        for rr in bi.itertuples():
            if rr.boundary_interface_status != "PASS":
                flags.append({
                    "flag_type": "FROZEN_BOUNDARY_INTERFACE",
                    "severity": "HIGH",
                    "key": f"{rr.physical_crossing_id}:{rr.assigned_gateway_id}",
                    "detail": (
                        "nearest frozen segment distance="
                        f"{rr.nearest_frozen_GOSM_segment_distance_m:.2f} m"
                    ),
                })

    flags_df = pd.DataFrame(flags)
    flags_df.to_csv(out / "B1_targeted_QA_flags.csv", index=False)

    # Summary.
    ie = routing_df[routing_df["direction"] == "IE"]
    ei = routing_df[routing_df["direction"] == "EI"]
    ie_routed = int((ie["routing_status"] == "ROUTED").sum())
    ei_routed = int((ei["routing_status"] == "ROUTED").sum())
    unreachable = int((routing_df["routing_status"] == "UNREACHABLE").sum())
    outcov = int((routing_df["routing_status"] == "OUT_OF_ROUTING_COVERAGE").sum())
    ambiguous = int((routing_df["gateway_status"] != "ASSIGNED").sum())

    external_edges = int(len(ext_sub))
    external_nodes = (
        int(len(set(ext_sub["u"].astype(int)).union(set(ext_sub["v"].astype(int)))))
        if len(ext_sub) else 0
    )
    used_len_km = float(ext_sub["distance_m_first"].sum() / 1000.0) if len(ext_sub) else 0.0

    high_flags = (
        int((flags_df["severity"] == "HIGH").sum()) if len(flags_df) else 0
    )
    review_flags = (
        int((flags_df["severity"] == "REVIEW").sum()) if len(flags_df) else 0
    )
    boundary_pass = bool(
        len(bi) > 0 and (bi["boundary_interface_status"] == "PASS").all()
    )
    routing_complete = (
        endpoint_coverage_rows == EXPECTED_OD_ROWS
        and ie_routed == EXPECTED_OD_ROWS
        and ei_routed == EXPECTED_OD_ROWS
        and unreachable == 0
        and outcov == 0
    )
    if routing_complete and ambiguous == 0 and high_flags == 0 and boundary_pass:
        qa_verdict = "PASS" if review_flags == 0 else "ONE_SMALL_TEST_REQUIRED"
    else:
        qa_verdict = "FAIL"

    summary = {
        "artifact": "G_EXT_ITALY_B1_v01",
        "od_rows": EXPECTED_OD_ROWS,
        "distinct_external_municipalities": len(unique_ext),
        "endpoint_coverage_rows": endpoint_coverage_rows,
        "ie_routed": ie_routed,
        "ei_routed": ei_routed,
        "unreachable_directional_paths": unreachable,
        "out_of_routing_coverage_directional_paths": outcov,
        "ambiguous_gateway_mapping_directional_paths": ambiguous,
        "used_external_edges": external_edges,
        "used_external_nodes": external_nodes,
        "used_network_length_km": used_len_km,
        "used_node_coordinate_missing_pairs": missing_node_coords,
        "targeted_directionality_qa_pairs": len(qa_pairs),
        "targeted_directionality_violations": len(direction_violations),
        "boundary_interface": "PASS" if boundary_pass else "NOT_READY",
        "targeted_qa": qa_verdict,
        "daily_factor": DAILY_FACTOR,
        "total_ie_commuting_daily": float(od["_flow_daily"].sum()),
        "total_ei_commuting_daily": float(od["_flow_daily"].sum()),
        "elapsed_seconds": time.time() - t0,
        "hard_stop": {
            "gravity_used": False,
            "ee_built": False,
            "phi_ee_estimated": False,
            "anas_2025_used": False,
            "frozen_artifacts_modified": False,
        },
    }
    with (out / "B1_EXT_summary_v01.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 110)
    for k, v in summary.items():
        if k != "hard_stop":
            print(f"{k} = {v}")
    print("=== RUN COMPLETATA ===")


if __name__ == "__main__":
    main()
