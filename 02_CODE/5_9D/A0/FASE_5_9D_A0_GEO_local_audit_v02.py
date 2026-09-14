from __future__ import annotations

"""
FASE 5.9D-A0-GEO — discovery-only physical cordon audit.

Purpose
-------
Scan the frozen OSM PBF used by the thesis and identify every potentially
motor-vehicle-relevant OSM road geometry intersecting the administrative
boundary of Friuli Venezia Giulia. The script is deliberately non-destructive:
it reads frozen inputs and writes only into a new audit directory.

Required local environment
--------------------------
The thesis environment that executed Fase 5.6 already used `osmium` (pyosmium).
Also required: geopandas, shapely, pyproj, pandas, numpy.

Default frozen PBF
------------------
C:\\Tesi\\Tesi_QGIS\\00_originali\\rete_stradale\\osm\\nord-est_2026-08-03.osm.pbf
SHA256 = e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813

Boundary
--------
By default the script searches C:\\Tesi for `Com01012026_WGS84.shp`, filters
COD_REG=6 and dissolves the 215 FVG municipalities. A different authoritative
boundary shapefile may be supplied with --boundary-shp.

Hard-stop compliance
--------------------
No frozen network/path/model artifact is modified. No v03/master gateway file
is written. No OD flow, EI/IE/EE, connector, phi_EE or Gravity calculation is
performed.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import osmium
from pyproj import Transformer
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point
from shapely.prepared import prep

EXPECTED_PBF_SHA256 = "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"
DEFAULT_ROOT = Path(r"C:\Tesi\Tesi_QGIS")
DEFAULT_PBF = DEFAULT_ROOT / "00_originali" / "rete_stradale" / "osm" / "nord-est_2026-08-03.osm.pbf"
DEFAULT_OUTDIR = DEFAULT_ROOT / "03_output_temporanei" / "fase_5_9D_A0_geo_v02"

# Initial census: intentionally broad. Explicitly non-motor highway values are
# still retained because they can document NON_MOTOR_VEHICLE false positives.
HIGHWAY_VALUES_TO_EXAMINE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "track", "road",
    # other values useful to prove exclusion rather than silently discard
    "pedestrian", "path", "footway", "cycleway", "bridleway", "steps",
    "construction", "proposed", "raceway", "corridor",
}

NON_MOTOR_HIGHWAYS = {"pedestrian", "path", "footway", "cycleway", "bridleway", "steps", "corridor"}
HIGH_HIERARCHY = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link",
}
OPEN_ORDINARY_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link",
}
OPEN_LOCAL_HIGHWAYS = {"unclassified", "residential", "living_street", "service"}

TAG_KEYS = [
    "highway", "ref", "name", "access", "vehicle", "motor_vehicle", "motorcar",
    "hgv", "bus", "bicycle", "foot", "service", "tracktype", "barrier",
    "smoothness", "surface", "seasonal", "opening_hours", "construction",
    "proposed", "disused", "abandoned", "private", "destination", "maxweight",
    "maxheight", "maxlength", "toll",
]

DENY = {"no", "private"}
RESTRICTIVE = {
    "destination", "customers", "delivery", "agricultural", "forestry", "permit",
    "residents", "official", "emergency", "psv", "bus", "discouraged",
}
ALLOW = {"yes", "permissive", "designated"}


def sha256(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"", "none", "nan", "null"}:
        return ""
    return s


def tags_to_dict(tags: Any) -> dict[str, str]:
    return {str(t.k): str(t.v) for t in tags}


def flatten_intersection_points(g) -> list[Point]:
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Point":
        return [g]
    if g.geom_type == "MultiPoint":
        return list(g.geoms)
    if g.geom_type == "GeometryCollection":
        out: list[Point] = []
        for x in g.geoms:
            out.extend(flatten_intersection_points(x))
        return out
    # A road lying briefly on the administrative boundary is represented by
    # endpoints of the overlap and later flagged for review.
    if g.geom_type == "LineString":
        return [Point(g.coords[0]), Point(g.coords[-1])]
    if g.geom_type == "MultiLineString":
        out = []
        for x in g.geoms:
            out.extend([Point(x.coords[0]), Point(x.coords[-1])])
        return out
    return []


def find_boundary_shp(search_root: Path) -> Path:
    hits = sorted(search_root.rglob("Com01012026_WGS84.shp"))
    if len(hits) != 1:
        raise RuntimeError(
            f"Expected exactly one Com01012026_WGS84.shp under {search_root}; found {len(hits)}: {hits}"
        )
    return hits[0]


def load_fvg_boundary(shp: Path):
    g = gpd.read_file(shp)
    if "COD_REG" not in g.columns:
        raise RuntimeError("Boundary source lacks COD_REG; pass a municipal ISTAT shapefile or adapt explicitly.")
    reg = pd.to_numeric(g["COD_REG"], errors="coerce")
    fvg = g.loc[reg == 6].copy()
    if len(fvg) != 215:
        raise RuntimeError(f"Expected 215 FVG municipalities, found {len(fvg)}")
    if fvg.crs is None:
        raise RuntimeError("Boundary source CRS is missing")
    poly_native = fvg.geometry.union_all()
    if not poly_native.is_valid:
        poly_native = poly_native.buffer(0)
    if not poly_native.is_valid:
        raise RuntimeError("Dissolved FVG boundary remains invalid")
    one = gpd.GeoSeries([poly_native], crs=fvg.crs).to_crs(4326)
    poly_wgs = one.iloc[0]
    if not poly_wgs.is_valid:
        raise RuntimeError("FVG boundary invalid after CRS transform")
    return poly_wgs, {
        "source": str(shp),
        "source_crs": str(fvg.crs),
        "municipalities": int(len(fvg)),
        "geometry_type": poly_wgs.geom_type,
        "valid": bool(poly_wgs.is_valid),
        "bounds_wgs84": list(map(float, poly_wgs.bounds)),
    }


def should_examine(tags: dict[str, str]) -> bool:
    hw = norm(tags.get("highway")).lower()
    if not hw:
        return False
    if hw in HIGHWAY_VALUES_TO_EXAMINE:
        return True
    # Any other highway explicitly permitting motor traffic remains relevant.
    explicit = [norm(tags.get(k)).lower() for k in ("motor_vehicle", "motorcar", "vehicle", "access")]
    return any(v in ALLOW for v in explicit)


def classify_access(tags: dict[str, str], node_tags: list[dict[str, str]]) -> tuple[str, str]:
    hw = norm(tags.get("highway")).lower()
    access = norm(tags.get("access")).lower()
    vehicle = norm(tags.get("vehicle")).lower()
    mv = norm(tags.get("motor_vehicle")).lower()
    mc = norm(tags.get("motorcar")).lower()
    seasonal = norm(tags.get("seasonal")).lower()
    opening = norm(tags.get("opening_hours"))
    tracktype = norm(tags.get("tracktype"))

    barriers = sorted({norm(t.get("barrier")) for t in node_tags if norm(t.get("barrier"))})
    node_access = [
        norm(t.get(k)).lower()
        for t in node_tags
        for k in ("access", "vehicle", "motor_vehicle", "motorcar")
        if norm(t.get(k))
    ]

    evidence = []
    for k in TAG_KEYS:
        v = norm(tags.get(k))
        if v:
            evidence.append(f"{k}={v}")
    if barriers:
        evidence.append("node_barrier=" + "|".join(barriers))
    if node_access:
        evidence.append("node_access=" + "|".join(sorted(set(node_access))))

    if hw in {"construction", "proposed"} or norm(tags.get("construction")):
        return "CLOSED", "; ".join(evidence)
    if hw in NON_MOTOR_HIGHWAYS and not (mv in ALLOW or mc in ALLOW):
        return "NON_MOTOR_VEHICLE", "; ".join(evidence)
    if access == "private" or mv == "private" or mc == "private" or vehicle == "private":
        return "PRIVATE", "; ".join(evidence)
    if any(x in {"bollard", "block"} for x in barriers) and not (mv in ALLOW or mc in ALLOW):
        return "RESTRICTED", "; ".join(evidence)
    if mv == "no" or mc == "no" or vehicle == "no":
        return "RESTRICTED", "; ".join(evidence)
    if access == "no" and not (mv in ALLOW or mc in ALLOW):
        return "RESTRICTED", "; ".join(evidence)
    if seasonal in {"yes", "winter", "summer"}:
        return "SEASONAL", "; ".join(evidence)
    if opening and opening.strip().lower() not in {"24/7", "24x7"}:
        # opening_hours is a temporal access restriction, not evidence of seasonality.
        # The A0 contract has no separate TIME_RESTRICTED class, so keep it
        # conservatively under RESTRICTED for later manual review.
        return "RESTRICTED", "; ".join(evidence)
    if hw == "track":
        if access in {"agricultural", "forestry"} or vehicle in {"agricultural", "forestry"} or mv in {"agricultural", "forestry"}:
            return "AGRICULTURAL_TRACK", "; ".join(evidence)
        if mv in ALLOW or mc in ALLOW or access in ALLOW:
            return "OPEN_LOCAL", "; ".join(evidence)
        return "AGRICULTURAL_TRACK", "; ".join(evidence)
    if access in RESTRICTIVE or vehicle in RESTRICTIVE or mv in RESTRICTIVE or mc in RESTRICTIVE:
        return "RESTRICTED", "; ".join(evidence)
    if hw in OPEN_ORDINARY_HIGHWAYS:
        return "OPEN_ORDINARY", "; ".join(evidence)
    if hw in OPEN_LOCAL_HIGHWAYS:
        return "OPEN_LOCAL", "; ".join(evidence)
    if hw == "road":
        return "UNKNOWN", "; ".join(evidence)
    if mv in ALLOW or mc in ALLOW:
        return "OPEN_LOCAL", "; ".join(evidence)
    return "UNKNOWN", "; ".join(evidence)


def hierarchy(hw: str) -> str:
    hw = norm(hw).lower().replace("_link", "")
    return {
        "motorway": "VERY_HIGH", "trunk": "VERY_HIGH", "primary": "HIGH",
        "secondary": "MEDIUM", "tertiary": "MEDIUM", "unclassified": "LOW",
        "residential": "LOW", "living_street": "VERY_LOW", "service": "VERY_LOW",
        "track": "VERY_LOW", "road": "UNKNOWN",
    }.get(hw, "VERY_LOW")


def materiality(access_class: str, hw: str, ref: str, name: str) -> str:
    if access_class in {"RESTRICTED", "PRIVATE", "AGRICULTURAL_TRACK", "SEASONAL", "CLOSED", "NON_MOTOR_VEHICLE"}:
        return "RESTRICTED_NOT_MODELLABLE"
    if access_class == "UNKNOWN":
        return "UNKNOWN_REQUIRES_REVIEW"
    base = norm(hw).lower().replace("_link", "")
    if base in {"motorway", "trunk", "primary"}:
        return "CORE_CANDIDATE"
    if base in {"secondary", "tertiary"} or norm(ref):
        return "SECONDARY_BUT_POSSIBLY_MATERIAL"
    return "MINOR_LIKELY_EXCLUDABLE"


@dataclass
class RawEvent:
    raw_id: int
    way_id: int
    lon: float
    lat: float
    x: float
    y: float
    tags: dict[str, str]
    overlap_boundary: bool
    near_node_ids: list[int]


class CordonHandler(osmium.SimpleHandler):
    def __init__(self, poly_wgs):
        super().__init__()
        self.poly = poly_wgs
        self.boundary = poly_wgs.boundary
        # A ~300 m band is only a cheap prefilter; exact intersection follows.
        self.band = prep(self.boundary.buffer(0.003))
        self.minx, self.miny, self.maxx, self.maxy = poly_wgs.bounds
        self.to_utm = Transformer.from_crs(4326, 32632, always_xy=True)
        self.events: list[RawEvent] = []
        self.near_nodes: dict[int, tuple[float, float]] = {}
        self.highway_seen = defaultdict(int)
        self.ways_examined = 0

    def way(self, w):
        tags = tags_to_dict(w.tags)
        if not should_examine(tags):
            return
        self.ways_examined += 1
        hw = norm(tags.get("highway")).lower()
        self.highway_seen[hw] += 1
        coords = []
        node_ids = []
        try:
            for n in w.nodes:
                if not n.location.valid():
                    return
                lon = float(n.lon)
                lat = float(n.lat)
                coords.append((lon, lat))
                node_ids.append(int(n.ref))
        except Exception:
            return
        if len(coords) < 2:
            return
        # Way bbox prefilter.
        lons = [p[0] for p in coords]
        lats = [p[1] for p in coords]
        if max(lons) < self.minx - 0.01 or min(lons) > self.maxx + 0.01 or max(lats) < self.miny - 0.01 or min(lats) > self.maxy + 0.01:
            return
        line = LineString(coords)
        if not self.band.intersects(line):
            return
        inter = line.intersection(self.boundary)
        pts = flatten_intersection_points(inter)
        if not pts:
            return
        overlap = inter.geom_type in {"LineString", "MultiLineString"}
        for pt in pts:
            x, y = self.to_utm.transform(pt.x, pt.y)
            # node ids within roughly 150 m of the intersection, to audit barriers
            near = []
            for nid, (lon, lat) in zip(node_ids, coords):
                nx, ny = self.to_utm.transform(lon, lat)
                if (nx - x) ** 2 + (ny - y) ** 2 <= 150.0 ** 2:
                    near.append(nid)
                    self.near_nodes[nid] = (lon, lat)
            self.events.append(RawEvent(
                raw_id=len(self.events) + 1,
                way_id=int(w.id), lon=float(pt.x), lat=float(pt.y), x=float(x), y=float(y),
                tags={k: norm(tags.get(k)) for k in TAG_KEYS if norm(tags.get(k))},
                overlap_boundary=overlap, near_node_ids=near,
            ))


class SelectedNodeHandler(osmium.SimpleHandler):
    def __init__(self, wanted: set[int]):
        super().__init__()
        self.wanted = wanted
        self.tags: dict[int, dict[str, str]] = {}

    def node(self, n):
        nid = int(n.id)
        if nid not in self.wanted:
            return
        t = tags_to_dict(n.tags)
        useful = {k: norm(t.get(k)) for k in TAG_KEYS if norm(t.get(k))}
        if useful:
            self.tags[nid] = useful


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1


def deduplicate(events: list[RawEvent]) -> list[list[int]]:
    """Deterministic physical-crossing grouping with conservative semantics."""
    n = len(events)
    uf = UnionFind(n)
    # Grid index avoids O(n^2) for the usually small border-event set.
    cell = 100.0
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        grid[(math.floor(e.x / cell), math.floor(e.y / cell))].append(i)

    def comparable(a: RawEvent, b: RawEvent, d: float) -> bool:
        ta, tb = a.tags, b.tags
        ha, hb = norm(ta.get("highway")).lower(), norm(tb.get("highway")).lower()
        ra, rb = norm(ta.get("ref")).lower(), norm(tb.get("ref")).lower()
        na, nb = norm(ta.get("name")).lower(), norm(tb.get("name")).lower()
        if d <= 12.0:
            return True
        if a.way_id == b.way_id and d <= 150.0:
            return True
        if d <= 70.0 and ((ra and rb and ra == rb) or (na and nb and na == nb)):
            return True
        # Merge separated carriageways / ramps only when the hierarchy itself
        # strongly indicates one physical corridor.
        linkish = ha.endswith("_link") or hb.endswith("_link")
        mainish = ha in HIGH_HIERARCHY or hb in HIGH_HIERARCHY
        if d <= 250.0 and linkish and mainish and (
            (ra and rb and ra == rb) or
            (not ra and not rb and ha.replace("_link", "") == hb.replace("_link", ""))
        ):
            return True
        return False

    for (gx, gy), ids in list(grid.items()):
        neigh = []
        for dx in (-3, -2, -1, 0, 1, 2, 3):
            for dy in (-3, -2, -1, 0, 1, 2, 3):
                neigh.extend(grid.get((gx + dx, gy + dy), []))
        for i in ids:
            a = events[i]
            for j in neigh:
                if j <= i:
                    continue
                b = events[j]
                d = math.hypot(a.x - b.x, a.y - b.y)
                if d <= 300.0 and comparable(a, b, d):
                    uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    return sorted(groups.values(), key=lambda idxs: (min(events[i].x for i in idxs), min(events[i].y for i in idxs)))


def summarize_group(group_id: int, idxs: list[int], events: list[RawEvent], node_tags: dict[int, dict[str, str]]) -> dict[str, Any]:
    evs = [events[i] for i in idxs]
    x = float(np.mean([e.x for e in evs]))
    y = float(np.mean([e.y for e in evs]))
    lon = float(np.mean([e.lon for e in evs]))
    lat = float(np.mean([e.lat for e in evs]))
    way_ids = sorted({e.way_id for e in evs})
    hws = sorted({norm(e.tags.get("highway")) for e in evs if norm(e.tags.get("highway"))})
    refs = sorted({norm(e.tags.get("ref")) for e in evs if norm(e.tags.get("ref"))})
    names = sorted({norm(e.tags.get("name")) for e in evs if norm(e.tags.get("name"))})

    # Physical-crossing classification must reflect whether the crossing has
    # at least one motorable member. Adjacent footways/cycleways or a restricted
    # parallel service way must NOT turn an otherwise motorable road crossing into
    # NON_MOTOR_VEHICLE / RESTRICTED after geometric deduplication.
    member_classes = []
    evidence = []
    for e in evs:
        nts = [node_tags[nid] for nid in e.near_node_ids if nid in node_tags]
        cls_i, ev = classify_access(e.tags, nts)
        member_classes.append(cls_i)
        if ev:
            evidence.append(ev)

    physical_precedence = [
        "OPEN_ORDINARY", "OPEN_LOCAL", "SEASONAL", "UNKNOWN", "RESTRICTED",
        "PRIVATE", "AGRICULTURAL_TRACK", "CLOSED", "NON_MOTOR_VEHICLE",
    ]
    cls = next((c for c in physical_precedence if c in member_classes), "UNKNOWN")
    member_class_set = sorted(set(member_classes))
    has_motorable = any(c in {"OPEN_ORDINARY", "OPEN_LOCAL", "SEASONAL"} for c in member_classes)
    has_nonmotor_or_restricted = any(
        c in {"NON_MOTOR_VEHICLE", "RESTRICTED", "PRIVATE", "AGRICULTURAL_TRACK", "CLOSED"}
        for c in member_classes
    )

    # Main representative highway: highest hierarchy ranking.
    hrank = {
        "motorway": 9, "motorway_link": 8, "trunk": 8, "trunk_link": 7,
        "primary": 7, "primary_link": 6, "secondary": 6, "secondary_link": 5,
        "tertiary": 5, "tertiary_link": 4, "unclassified": 3, "residential": 2,
        "living_street": 1, "service": 1, "road": 0, "track": -1,
    }
    rep_hw = max(hws, key=lambda h: hrank.get(h, -2)) if hws else ""
    rep_ref = refs[0] if len(refs) == 1 else "|".join(refs)
    rep_name = names[0] if len(names) == 1 else "|".join(names)

    # Diameter diagnostic; a large value means the semantic merge deserves QA.
    diam = 0.0
    for i in range(len(evs)):
        for j in range(i + 1, len(evs)):
            diam = max(diam, math.hypot(evs[i].x - evs[j].x, evs[i].y - evs[j].y))

    return {
        "crossing_candidate_id": f"GEO_{group_id:04d}",
        "lat": lat, "lon": lon, "utm_x": x, "utm_y": y,
        "raw_event_count": len(evs), "osm_way_count": len(way_ids),
        "osm_way_ids": "|".join(map(str, way_ids)),
        "osm_highway": "|".join(hws), "osm_ref": rep_ref, "osm_name": rep_name,
        "motor_vehicle_access_class": cls,
        "member_access_classes": "|".join(member_class_set),
        "restriction_evidence": " || ".join(sorted(set(evidence))),
        "road_hierarchy": hierarchy(rep_hw),
        "corridor_continuity": "TO_BE_RECONCILED",
        "materiality_screen": materiality(cls, rep_hw, rep_ref, rep_name),
        "documentary_inventory_match": "TO_BE_RECONCILED",
        "current_gateway_match": "TO_BE_RECONCILED",
        "known_gateway_id": "",
        "overlap_boundary_geometry": any(e.overlap_boundary for e in evs),
        "dedup_cluster_diameter_m": round(diam, 3),
        "dedup_mixed_motorability": bool(has_motorable and has_nonmotor_or_restricted),
        "dedup_review_flag": bool(
            diam > 350.0
            or (has_motorable and has_nonmotor_or_restricted)
            or len(refs) > 1
            or len(names) > 2
        ),
        "notes": "",
    }


def write_json(path: Path, obj: Any):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbf", type=Path, default=DEFAULT_PBF)
    ap.add_argument("--boundary-shp", type=Path, default=None)
    ap.add_argument("--boundary-search-root", type=Path, default=Path(r"C:\Tesi"))
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = ap.parse_args()

    print("=" * 90)
    print("FASE 5.9D-A0-GEO — FINAL EXHAUSTIVE CORDON GEOMETRY QA / LOCAL RAW-PBF SCAN")
    print("=" * 90)
    print("DISCOVERY ONLY / NO FROZEN ARTIFACT WRITE")

    pbf = args.pbf.resolve()
    outdir = args.outdir.resolve()
    if not pbf.is_file():
        raise FileNotFoundError(f"Frozen PBF not found: {pbf}")
    if outdir.exists():
        raise FileExistsError(f"NO OVERWRITE: output directory already exists: {outdir}")

    boundary_shp = args.boundary_shp.resolve() if args.boundary_shp else find_boundary_shp(args.boundary_search_root)
    if not boundary_shp.is_file():
        raise FileNotFoundError(boundary_shp)

    print(f"Frozen PBF : {pbf}")
    print(f"Boundary   : {boundary_shp}")
    print(f"Output     : {outdir}")

    print("\nPREFLIGHT — SHA256")
    pbf_hash = sha256(pbf)
    print(f"PBF SHA256 : {pbf_hash}")
    if pbf_hash.lower() != EXPECTED_PBF_SHA256.lower():
        raise RuntimeError("Frozen PBF SHA256 mismatch; refusing to run on a different snapshot.")

    poly_wgs, boundary_meta = load_fvg_boundary(boundary_shp)
    print(f"Boundary valid: {boundary_meta['valid']} | municipalities={boundary_meta['municipalities']}")

    outdir.mkdir(parents=True, exist_ok=False)

    handler = CordonHandler(poly_wgs)
    t0 = time.perf_counter()
    # Same pyosmium mechanism already used in Fase 5.6 project scripts. `flex_mem`
    # is explicit for reproducibility; change only if the local machine cannot
    # allocate the node-location index, and document that change.
    handler.apply_file(str(pbf), locations=True, idx="flex_mem")
    scan_seconds = time.perf_counter() - t0
    print(f"PBF scan seconds: {scan_seconds:.2f}")
    print(f"Raw border intersection events: {len(handler.events)}")

    wanted_nodes = set(handler.near_nodes)
    nh = SelectedNodeHandler(wanted_nodes)
    if wanted_nodes:
        nh.apply_file(str(pbf), locations=False)

    groups = deduplicate(handler.events)
    physical = [summarize_group(i + 1, grp, handler.events, nh.tags) for i, grp in enumerate(groups)]

    raw_rows = []
    for e in handler.events:
        nts = [nh.tags[nid] for nid in e.near_node_ids if nid in nh.tags]
        cls, evidence = classify_access(e.tags, nts)
        raw_rows.append({
            "raw_intersection_id": f"RAW_{e.raw_id:05d}",
            "osm_way_id": e.way_id,
            "lat": e.lat, "lon": e.lon, "utm_x": e.x, "utm_y": e.y,
            **{f"osm_{k}": norm(e.tags.get(k)) for k in TAG_KEYS},
            "near_tagged_node_ids": "|".join(map(str, sorted(n for n in e.near_node_ids if n in nh.tags))),
            "motor_vehicle_access_class": cls,
            "restriction_evidence": evidence,
            "overlap_boundary_geometry": e.overlap_boundary,
        })

    raw_df = pd.DataFrame(raw_rows)
    physical_df = pd.DataFrame(physical)
    raw_csv = outdir / "raw_osm_border_intersections_v02.csv"
    physical_csv = outdir / "deduplicated_physical_crossings_v02.csv"
    raw_df.to_csv(raw_csv, index=False, encoding="utf-8")
    physical_df.to_csv(physical_csv, index=False, encoding="utf-8")

    if len(physical_df):
        pg = gpd.GeoDataFrame(
            physical_df.copy(),
            geometry=gpd.points_from_xy(physical_df.lon, physical_df.lat),
            crs="EPSG:4326",
        )
        gpkg = outdir / "A0_GEO_physical_crossings_v02.gpkg"
        pg.to_file(gpkg, layer="physical_crossings", driver="GPKG")
    else:
        gpkg = None

    counts = physical_df["motor_vehicle_access_class"].value_counts().to_dict() if len(physical_df) else {}
    mat_counts = physical_df["materiality_screen"].value_counts().to_dict() if len(physical_df) else {}
    summary = {
        "status": "RAW_GEOMETRY_AUDIT_COMPLETE__RECONCILIATION_REQUIRED",
        "input_pbf": str(pbf),
        "input_pbf_sha256": pbf_hash,
        "boundary": boundary_meta,
        "pbf_scan_seconds": round(scan_seconds, 3),
        "ways_examined": int(handler.ways_examined),
        "highway_values_seen": dict(sorted(handler.highway_seen.items())),
        "raw_osm_border_intersections": int(len(raw_df)),
        "deduplicated_physical_crossings": int(len(physical_df)),
        "access_counts": {k: int(counts.get(k, 0)) for k in [
            "OPEN_ORDINARY", "OPEN_LOCAL", "RESTRICTED", "PRIVATE", "AGRICULTURAL_TRACK",
            "SEASONAL", "CLOSED", "NON_MOTOR_VEHICLE", "UNKNOWN",
        ]},
        "materiality_screen_counts": {k: int(v) for k, v in mat_counts.items()},
        "dedup_review_flags": int(physical_df["dedup_review_flag"].sum()) if len(physical_df) else 0,
        "hard_stop": {
            "frozen_artifacts_modified": False,
            "external_gateway_master_modified": False,
            "external_zones_or_connectors_built": False,
            "OD_flows_or_EI_IE_EE_built": False,
            "phi_EE_or_Gravity_computed": False,
        },
    }
    summary_path = outdir / "A0_GEO_summary_v02.json"
    write_json(summary_path, summary)

    # Manifest after all primary artifacts are present.
    files = [raw_csv, physical_csv, summary_path]
    if gpkg:
        files.append(gpkg)
    script_path = Path(__file__).resolve()
    script_hash = sha256(script_path)
    manifest = {
        "run_contract": "FASE_5_9D_A0_GEO_v02",
        "created_by": script_path.name,
        "created_by_sha256": script_hash,
        "input_pbf": {"path": str(pbf), "sha256": pbf_hash},
        "boundary": boundary_meta,
        "outputs": [
            {"name": f.name, "size_bytes": f.stat().st_size, "sha256": sha256(f)}
            for f in files
        ],
        "summary": summary,
    }
    manifest_path = outdir / "A0_GEO_manifest_v02.json"
    write_json(manifest_path, manifest)
    manifest_sha = sha256(manifest_path)
    (outdir / "A0_GEO_manifest_v02.sha256").write_text(
        f"{manifest_sha}  {manifest_path.name}\n", encoding="ascii"
    )

    print("\nFINAL QA")
    print(f"RAW_OSM_BORDER_INTERSECTIONS      = {len(raw_df)}")
    print(f"DEDUPLICATED_PHYSICAL_CROSSINGS  = {len(physical_df)}")
    for k in ["OPEN_ORDINARY", "OPEN_LOCAL", "RESTRICTED", "PRIVATE", "AGRICULTURAL_TRACK", "SEASONAL", "CLOSED", "NON_MOTOR_VEHICLE", "UNKNOWN"]:
        print(f"{k:<32} = {int(counts.get(k, 0))}")
    print(f"DEDUP_REVIEW_FLAGS                = {summary['dedup_review_flags']}")
    print(f"MANIFEST_SHA256                   = {manifest_sha}")
    print("\nSTOP: reconciliation with documentary inventory/current 18 belongs to A0-GEO review; no model artifact changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
