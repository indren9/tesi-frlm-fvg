from pathlib import Path
from datetime import datetime
from collections import Counter
from importlib.metadata import version
import hashlib
import json
import math
import re
import sqlite3
import sys

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

RAWDB = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b1\osm_topology_raw_v01.sqlite"
)

SOURCE_GPKG = (
    ROOT
    / r"02_package\rete_stradale_osm_fvg.gpkg"
)

SOURCE_LAYER = "osm_rete_light_20km_tempi_base_v3"

BASE_GPKG = (
    ROOT
    / r"02_package\base_territoriale_fvg.gpkg"
)

MASK_LAYER = "area_estrazione_rete_fvg_20km_wgs84"

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b2"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUTDB = OUTDIR / "osm_directed_edges_v01.sqlite"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"build_osm_directed_edges_v01_{STAMP}.txt"

BATCH_SIZE = 100_000

# Segmenti praticamente nulli non entrano nel routing.
MIN_LENGTH_M = 0.01


# =============================================================================
# LOG
# =============================================================================

lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def norm_text(x):
    if x is None:
        return None
    return str(x)


def norm_float(x):
    if x is None:
        return None

    try:
        f = float(x)
    except Exception:
        return None

    if not math.isfinite(f):
        return None

    return round(f, 9)


def positive_time(x):
    f = norm_float(x)
    return f is not None and f > 0


def parse_osm_id(value):

    if value is None:
        return None

    if isinstance(value, int):
        return value

    s = str(value).strip()

    if not s:
        return None

    if re.fullmatch(r"\d+", s):
        return int(s)

    m = re.search(r"(\d+)$", s)

    if m:
        return int(m.group(1))

    return None


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 100)
out("FASE 5.6 — BUILD B2 — OSM NATIVE SEGMENTS + DIRECTED EDGES")
out("=" * 100)

out(f"RAW topology   : {RAWDB}")
out(f"Semantic layer : {SOURCE_GPKG} | {SOURCE_LAYER}")
out(f"Spatial mask   : {BASE_GPKG} | {MASK_LAYER}")
out(f"Output         : {OUTDB}")

for p in [RAWDB, SOURCE_GPKG, BASE_GPKG]:
    if not p.exists():
        raise FileNotFoundError(p)

if OUTDB.exists():
    raise RuntimeError(
        f"Output già esistente:\n{OUTDB}\n"
        "Non sovrascrivo output versionati."
    )


# =============================================================================
# A. LETTURA E VALIDAZIONE SEMANTICA v3
# =============================================================================

out()
out("A. CONSOLIDAMENTO SEMANTICA ROUTING v3")
out("-" * 100)

src = sqlite3.connect(SOURCE_GPKG)
src_cur = src.cursor()

columns = [
    r[1]
    for r in src_cur.execute(
        f'PRAGMA table_info("{SOURCE_LAYER}")'
    ).fetchall()
]

required = [
    "osm_id",
    "highway",
    "name",
    "tag_ref",

    "access_fwd_class",
    "access_bwd_class",
    "access_conditional_flag",

    "direction_status",
    "direction_code",
    "direction_conditional_flag",

    "routing_fwd_status",
    "routing_bwd_status",
    "routing_fwd_code",
    "routing_bwd_code",

    "routing_fwd_closure_cause",
    "routing_bwd_closure_cause",

    "speed_fwd_model_kmh",
    "speed_bwd_model_kmh",
    "speed_fwd_model_source",
    "speed_bwd_model_source",
    "speed_conditional_flag",

    "time_fwd_base_s",
    "time_bwd_base_s",

    "length_m",
]

missing_cols = [c for c in required if c not in columns]

if missing_cols:
    raise RuntimeError(
        "Campi mancanti nel layer v3: "
        + ", ".join(missing_cols)
    )

source_stats = src_cur.execute(
    f'''
    SELECT
        COUNT(*),
        COUNT(DISTINCT osm_id),
        SUM(length_m)
    FROM "{SOURCE_LAYER}"
    '''
).fetchone()

source_feature_count = int(source_stats[0])
source_unique_way_count = int(source_stats[1])
source_length_m = float(source_stats[2])

out(f"Feature sorgente       : {source_feature_count:,}")
out(f"Way OSM distinte       : {source_unique_way_count:,}")
out(f"Lunghezza v3           : {source_length_m / 1000:,.3f} km")

sql = f'''
SELECT
    {", ".join('"' + c + '"' for c in required)}
FROM "{SOURCE_LAYER}"
ORDER BY osm_id
'''

semantics = {}
signatures = {}
duplicate_count = 0
conflicts = []
invalid_open_speed = []

for row in src_cur.execute(sql):

    d = dict(zip(required, row))

    wid = parse_osm_id(d["osm_id"])

    if wid is None:
        raise RuntimeError(
            f"osm_id non interpretabile: {d['osm_id']}"
        )

    fwd_open = positive_time(d["time_fwd_base_s"])
    bwd_open = positive_time(d["time_bwd_base_s"])

    sf = norm_float(d["speed_fwd_model_kmh"])
    sb = norm_float(d["speed_bwd_model_kmh"])

    if fwd_open and (sf is None or sf <= 0):
        invalid_open_speed.append((wid, "FWD", sf))

    if bwd_open and (sb is None or sb <= 0):
        invalid_open_speed.append((wid, "BWD", sb))

    signature = (
        norm_text(d["highway"]),

        norm_text(d["access_fwd_class"]),
        norm_text(d["access_bwd_class"]),
        norm_text(d["access_conditional_flag"]),

        norm_text(d["direction_status"]),
        norm_text(d["direction_code"]),
        norm_text(d["direction_conditional_flag"]),

        norm_text(d["routing_fwd_status"]),
        norm_text(d["routing_bwd_status"]),
        norm_text(d["routing_fwd_code"]),
        norm_text(d["routing_bwd_code"]),

        norm_text(d["routing_fwd_closure_cause"]),
        norm_text(d["routing_bwd_closure_cause"]),

        sf,
        sb,

        norm_text(d["speed_fwd_model_source"]),
        norm_text(d["speed_bwd_model_source"]),
        norm_text(d["speed_conditional_flag"]),

        fwd_open,
        bwd_open,
    )

    if wid in signatures:

        duplicate_count += 1

        if signatures[wid] != signature:
            if len(conflicts) < 50:
                conflicts.append(wid)

        continue

    signatures[wid] = signature

    semantics[wid] = {
        "way_id": wid,

        "highway": norm_text(d["highway"]),
        "name": norm_text(d["name"]),
        "ref": norm_text(d["tag_ref"]),

        "access_fwd_class":
            norm_text(d["access_fwd_class"]),
        "access_bwd_class":
            norm_text(d["access_bwd_class"]),
        "access_conditional_flag":
            norm_text(d["access_conditional_flag"]),

        "direction_status":
            norm_text(d["direction_status"]),
        "direction_code":
            norm_text(d["direction_code"]),
        "direction_conditional_flag":
            norm_text(d["direction_conditional_flag"]),

        "routing_fwd_status":
            norm_text(d["routing_fwd_status"]),
        "routing_bwd_status":
            norm_text(d["routing_bwd_status"]),

        "routing_fwd_code":
            norm_text(d["routing_fwd_code"]),
        "routing_bwd_code":
            norm_text(d["routing_bwd_code"]),

        "routing_fwd_closure_cause":
            norm_text(d["routing_fwd_closure_cause"]),
        "routing_bwd_closure_cause":
            norm_text(d["routing_bwd_closure_cause"]),

        "speed_fwd_model_kmh": sf,
        "speed_bwd_model_kmh": sb,

        "speed_fwd_model_source":
            norm_text(d["speed_fwd_model_source"]),
        "speed_bwd_model_source":
            norm_text(d["speed_bwd_model_source"]),

        "speed_conditional_flag":
            norm_text(d["speed_conditional_flag"]),

        "fwd_open": fwd_open,
        "bwd_open": bwd_open,
    }

src.close()

out(f"Way consolidate       : {len(semantics):,}")
out(f"Righe duplicate way   : {duplicate_count:,}")
out(f"Conflitti semantici   : {len(conflicts):,}")
out(f"Open senza speed      : {len(invalid_open_speed):,}")

if conflicts:
    out(f"Esempi conflitti: {conflicts[:20]}")
    raise RuntimeError(
        "La stessa OSM way presenta semantica routing "
        "incoerente tra feature v3."
    )

if invalid_open_speed:
    out(f"Esempi: {invalid_open_speed[:20]}")
    raise RuntimeError(
        "Direzioni operative senza velocità valida."
    )


# =============================================================================
# B. TAG NATIVI DAL PBF/B1
# =============================================================================

out()
out("B. RECUPERO TAG NATIVI WAY")
out("-" * 100)

raw = sqlite3.connect(RAWDB)
raw_cur = raw.cursor()

raw_way_count = raw_cur.execute(
    "SELECT COUNT(*) FROM ways"
).fetchone()[0]

raw_tags = {}

for wid, tags_json in raw_cur.execute(
    "SELECT way_id, tags_json FROM ways"
):

    tags = json.loads(tags_json)

    raw_tags[int(wid)] = {
        "oneway": tags.get("oneway"),
        "junction": tags.get("junction"),
        "bridge": tags.get("bridge"),
        "tunnel": tags.get("tunnel"),
        "layer": tags.get("layer"),

        "access": tags.get("access"),
        "vehicle": tags.get("vehicle"),
        "motor_vehicle": tags.get("motor_vehicle"),
        "motorcar": tags.get("motorcar"),
    }

out(f"Way B1              : {raw_way_count:,}")
out(f"Tag way caricati    : {len(raw_tags):,}")

missing_semantics = set(raw_tags) - set(semantics)
missing_raw_tags = set(semantics) - set(raw_tags)

out(f"B1 senza semantica  : {len(missing_semantics):,}")
out(f"v3 senza B1         : {len(missing_raw_tags):,}")

if missing_semantics or missing_raw_tags:
    raise RuntimeError(
        "Mismatch tra B1 e layer semantico v3."
    )


# =============================================================================
# C. MASCHERA FVG + 20 km
# =============================================================================

out()
out("C. CARICAMENTO MASCHERA FVG + 20 km")
out("-" * 100)

mask_gdf = gpd.read_file(
    BASE_GPKG,
    layer=MASK_LAYER,
)

if len(mask_gdf) == 0:
    raise RuntimeError("Maschera spaziale vuota.")

if mask_gdf.crs is None:
    raise RuntimeError("Maschera senza CRS.")

if mask_gdf.crs.to_epsg() != 4326:
    mask_gdf = mask_gdf.to_crs(4326)

mask_geom = mask_gdf.geometry.union_all()

if mask_geom.is_empty:
    raise RuntimeError("Geometria maschera vuota.")

if not mask_geom.is_valid:
    mask_geom = shapely.make_valid(mask_geom)

minx, miny, maxx, maxy = mask_geom.bounds

out(f"CRS maschera : EPSG:4326")
out(
    f"BBOX         : "
    f"{minx:.6f}, {miny:.6f}, "
    f"{maxx:.6f}, {maxy:.6f}"
)


# =============================================================================
# D. OUTPUT DATABASE
# =============================================================================

out()
out("D. INIZIALIZZAZIONE OUTPUT")
out("-" * 100)

db = sqlite3.connect(OUTDB)
cur = db.cursor()

cur.executescript(
    """
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE nodes (
        node_id INTEGER PRIMARY KEY,
        lon REAL NOT NULL,
        lat REAL NOT NULL,
        x REAL NOT NULL,
        y REAL NOT NULL
    );

    CREATE TABLE segments (
        segment_uid TEXT PRIMARY KEY,

        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,

        osm_u INTEGER NOT NULL,
        osm_v INTEGER NOT NULL,

        length_m REAL NOT NULL,

        highway TEXT,
        name TEXT,
        ref TEXT,

        oneway_raw TEXT,
        junction_raw TEXT,
        bridge_raw TEXT,
        tunnel_raw TEXT,
        layer_raw TEXT,

        access_raw TEXT,
        vehicle_raw TEXT,
        motor_vehicle_raw TEXT,
        motorcar_raw TEXT,

        direction_status TEXT,
        direction_code TEXT,

        access_conditional_flag TEXT,
        direction_conditional_flag TEXT,
        speed_conditional_flag TEXT
    );

    CREATE INDEX idx_segments_way
        ON segments(way_id);

    CREATE INDEX idx_segments_u
        ON segments(osm_u);

    CREATE INDEX idx_segments_v
        ON segments(osm_v);

    CREATE TABLE directed_edges (
        edge_id INTEGER PRIMARY KEY,
        edge_uid TEXT NOT NULL UNIQUE,

        segment_uid TEXT NOT NULL,

        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,

        u INTEGER NOT NULL,
        v INTEGER NOT NULL,

        way_direction TEXT NOT NULL,

        length_m REAL NOT NULL,
        speed_kmh REAL NOT NULL,
        time_s REAL NOT NULL,

        highway TEXT,

        direction_status TEXT,

        routing_status TEXT,
        routing_code TEXT,
        closure_cause TEXT,

        access_class TEXT,

        speed_source TEXT,

        access_conditional_flag TEXT,
        direction_conditional_flag TEXT,
        speed_conditional_flag TEXT
    );

    CREATE INDEX idx_edges_u
        ON directed_edges(u);

    CREATE INDEX idx_edges_v
        ON directed_edges(v);

    CREATE INDEX idx_edges_way
        ON directed_edges(way_id);

    CREATE TABLE segment_rejections (
        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        osm_u INTEGER,
        osm_v INTEGER,
        length_m REAL,
        reason TEXT NOT NULL
    );
    """
)

metadata = {
    "phase": "FASE_5_6_BUILD_B2",
    "version": "v01",
    "created_at": STAMP,

    "python": sys.version.replace("\n", " "),
    "numpy": version("numpy"),
    "shapely": version("shapely"),
    "geopandas": version("geopandas"),
    "pyproj": version("pyproj"),

    "raw_topology_db": str(RAWDB),

    "semantic_gpkg": str(SOURCE_GPKG),
    "semantic_layer": SOURCE_LAYER,

    "mask_gpkg": str(BASE_GPKG),
    "mask_layer": MASK_LAYER,

    "target_crs": "EPSG:32632",

    "edge_uid_rule":
        "{way_id}:{segment_seq}:{F|B}",

    "topology_rule":
        "OSM consecutive nodes only; no geometric intersection noding",
}

cur.executemany(
    "INSERT INTO metadata(key, value) VALUES (?, ?)",
    [(k, str(v)) for k, v in metadata.items()],
)

db.commit()


# =============================================================================
# E. STREAM DEI SEGMENTI NATIVI
# =============================================================================

out()
out("E. RICOSTRUZIONE SEGMENTI OSM NATIVI")
out("-" * 100)

segment_sql = """
WITH ordered AS (
    SELECT
        wn.way_id AS way_id,
        wn.seq AS seq,

        wn.node_id AS osm_u,
        n.lon AS lon_u,
        n.lat AS lat_u,

        LEAD(wn.node_id)
            OVER (
                PARTITION BY wn.way_id
                ORDER BY wn.seq
            ) AS osm_v,

        LEAD(n.lon)
            OVER (
                PARTITION BY wn.way_id
                ORDER BY wn.seq
            ) AS lon_v,

        LEAD(n.lat)
            OVER (
                PARTITION BY wn.way_id
                ORDER BY wn.seq
            ) AS lat_v

    FROM way_nodes AS wn

    JOIN nodes AS n
        ON n.node_id = wn.node_id
)

SELECT
    way_id,
    seq,
    osm_u,
    lon_u,
    lat_u,
    osm_v,
    lon_v,
    lat_v

FROM ordered

WHERE osm_v IS NOT NULL

ORDER BY way_id, seq
"""

seg_cur = raw.cursor()
seg_cur.execute(segment_sql)

transformer = Transformer.from_crs(
    4326,
    32632,
    always_xy=True,
)

total_raw_segments = 0
bbox_candidates = 0
inside_segments = 0
outside_segments = 0
zero_length_segments = 0

edge_id = 0

represented_ways = set()

direction_counts = Counter()
direction_source_counts = Counter()
highway_segment_counts = Counter()

while True:

    rows = seg_cur.fetchmany(BATCH_SIZE)

    if not rows:
        break

    n = len(rows)

    total_raw_segments += n

    way_ids = np.fromiter(
        (int(r[0]) for r in rows),
        dtype=np.int64,
        count=n,
    )

    seqs = np.fromiter(
        (int(r[1]) for r in rows),
        dtype=np.int64,
        count=n,
    )

    us = np.fromiter(
        (int(r[2]) for r in rows),
        dtype=np.int64,
        count=n,
    )

    lon_u = np.fromiter(
        (float(r[3]) for r in rows),
        dtype=np.float64,
        count=n,
    )

    lat_u = np.fromiter(
        (float(r[4]) for r in rows),
        dtype=np.float64,
        count=n,
    )

    vs = np.fromiter(
        (int(r[5]) for r in rows),
        dtype=np.int64,
        count=n,
    )

    lon_v = np.fromiter(
        (float(r[6]) for r in rows),
        dtype=np.float64,
        count=n,
    )

    lat_v = np.fromiter(
        (float(r[7]) for r in rows),
        dtype=np.float64,
        count=n,
    )

    seg_minx = np.minimum(lon_u, lon_v)
    seg_maxx = np.maximum(lon_u, lon_v)
    seg_miny = np.minimum(lat_u, lat_v)
    seg_maxy = np.maximum(lat_u, lat_v)

    bbox_mask = (
        (seg_maxx >= minx)
        & (seg_minx <= maxx)
        & (seg_maxy >= miny)
        & (seg_miny <= maxy)
    )

    candidate_idx = np.flatnonzero(bbox_mask)

    bbox_candidates += len(candidate_idx)

    keep_idx = np.array([], dtype=np.int64)

    if len(candidate_idx):

        coords = np.empty(
            (len(candidate_idx), 2, 2),
            dtype=np.float64,
        )

        coords[:, 0, 0] = lon_u[candidate_idx]
        coords[:, 0, 1] = lat_u[candidate_idx]

        coords[:, 1, 0] = lon_v[candidate_idx]
        coords[:, 1, 1] = lat_v[candidate_idx]

        geom_batch = shapely.linestrings(coords)

        exact = np.asarray(
            shapely.intersects(
                geom_batch,
                mask_geom,
            ),
            dtype=bool,
        )

        keep_idx = candidate_idx[exact]

    inside_segments += len(keep_idx)
    outside_segments += n - len(keep_idx)

    if len(keep_idx) == 0:
        continue

    ku = lon_u[keep_idx]
    kva = lat_u[keep_idx]

    kv = lon_v[keep_idx]
    kvb = lat_v[keep_idx]

    x_u, y_u = transformer.transform(
        ku,
        kva,
    )

    x_v, y_v = transformer.transform(
        kv,
        kvb,
    )

    lengths = np.hypot(
        np.asarray(x_v) - np.asarray(x_u),
        np.asarray(y_v) - np.asarray(y_u),
    )

    node_batch = {}

    segment_batch = []
    edge_batch = []
    reject_batch = []

    for pos, idx in enumerate(keep_idx):

        wid = int(way_ids[idx])
        seq = int(seqs[idx])

        u = int(us[idx])
        v = int(vs[idx])

        length_m = float(lengths[pos])

        node_batch[u] = (
            u,
            float(lon_u[idx]),
            float(lat_u[idx]),
            float(x_u[pos]),
            float(y_u[pos]),
        )

        node_batch[v] = (
            v,
            float(lon_v[idx]),
            float(lat_v[idx]),
            float(x_v[pos]),
            float(y_v[pos]),
        )

        if length_m <= MIN_LENGTH_M:

            zero_length_segments += 1

            reject_batch.append(
                (
                    wid,
                    seq,
                    u,
                    v,
                    length_m,
                    "ZERO_OR_NEAR_ZERO_LENGTH",
                )
            )

            continue

        represented_ways.add(wid)

        sem = semantics[wid]
        tags = raw_tags[wid]

        segment_uid = f"{wid}:{seq}"

        segment_batch.append(
            (
                segment_uid,

                wid,
                seq,

                u,
                v,

                length_m,

                sem["highway"],
                sem["name"],
                sem["ref"],

                tags["oneway"],
                tags["junction"],
                tags["bridge"],
                tags["tunnel"],
                tags["layer"],

                tags["access"],
                tags["vehicle"],
                tags["motor_vehicle"],
                tags["motorcar"],

                sem["direction_status"],
                sem["direction_code"],

                sem["access_conditional_flag"],
                sem["direction_conditional_flag"],
                sem["speed_conditional_flag"],
            )
        )

        highway_segment_counts[
            sem["highway"]
        ] += 1

        direction_source_counts[
            sem["direction_status"]
        ] += 1

        # -------------------------------------------------------------
        # FWD = stesso ordine della OSM way
        # -------------------------------------------------------------

        if sem["fwd_open"]:

            speed = float(
                sem["speed_fwd_model_kmh"]
            )

            time_s = length_m * 3.6 / speed

            edge_id += 1

            edge_batch.append(
                (
                    edge_id,
                    f"{wid}:{seq}:F",

                    segment_uid,

                    wid,
                    seq,

                    u,
                    v,

                    "FWD",

                    length_m,
                    speed,
                    time_s,

                    sem["highway"],

                    sem["direction_status"],

                    sem["routing_fwd_status"],
                    sem["routing_fwd_code"],
                    sem[
                        "routing_fwd_closure_cause"
                    ],

                    sem["access_fwd_class"],

                    sem[
                        "speed_fwd_model_source"
                    ],

                    sem[
                        "access_conditional_flag"
                    ],
                    sem[
                        "direction_conditional_flag"
                    ],
                    sem[
                        "speed_conditional_flag"
                    ],
                )
            )

            direction_counts["FWD"] += 1

        # -------------------------------------------------------------
        # BWD = opposto all'ordine della OSM way
        # -------------------------------------------------------------

        if sem["bwd_open"]:

            speed = float(
                sem["speed_bwd_model_kmh"]
            )

            time_s = length_m * 3.6 / speed

            edge_id += 1

            edge_batch.append(
                (
                    edge_id,
                    f"{wid}:{seq}:B",

                    segment_uid,

                    wid,
                    seq,

                    v,
                    u,

                    "BWD",

                    length_m,
                    speed,
                    time_s,

                    sem["highway"],

                    sem["direction_status"],

                    sem["routing_bwd_status"],
                    sem["routing_bwd_code"],
                    sem[
                        "routing_bwd_closure_cause"
                    ],

                    sem["access_bwd_class"],

                    sem[
                        "speed_bwd_model_source"
                    ],

                    sem[
                        "access_conditional_flag"
                    ],
                    sem[
                        "direction_conditional_flag"
                    ],
                    sem[
                        "speed_conditional_flag"
                    ],
                )
            )

            direction_counts["BWD"] += 1

    if node_batch:
        cur.executemany(
            """
            INSERT OR IGNORE INTO nodes(
                node_id,
                lon,
                lat,
                x,
                y
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            list(node_batch.values()),
        )

    if segment_batch:
        cur.executemany(
            """
            INSERT INTO segments(
                segment_uid,

                way_id,
                seq,

                osm_u,
                osm_v,

                length_m,

                highway,
                name,
                ref,

                oneway_raw,
                junction_raw,
                bridge_raw,
                tunnel_raw,
                layer_raw,

                access_raw,
                vehicle_raw,
                motor_vehicle_raw,
                motorcar_raw,

                direction_status,
                direction_code,

                access_conditional_flag,
                direction_conditional_flag,
                speed_conditional_flag
            )
            VALUES (
                ?, ?, ?,
                ?, ?,
                ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?
            )
            """,
            segment_batch,
        )

    if edge_batch:
        cur.executemany(
            """
            INSERT INTO directed_edges(
                edge_id,
                edge_uid,

                segment_uid,

                way_id,
                seq,

                u,
                v,

                way_direction,

                length_m,
                speed_kmh,
                time_s,

                highway,

                direction_status,

                routing_status,
                routing_code,
                closure_cause,

                access_class,

                speed_source,

                access_conditional_flag,
                direction_conditional_flag,
                speed_conditional_flag
            )
            VALUES (
                ?, ?,
                ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?, ?,
                ?,
                ?,
                ?, ?, ?,
                ?,
                ?,
                ?, ?, ?
            )
            """,
            edge_batch,
        )

    if reject_batch:
        cur.executemany(
            """
            INSERT INTO segment_rejections(
                way_id,
                seq,
                osm_u,
                osm_v,
                length_m,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            reject_batch,
        )

    db.commit()

    out(
        f"  raw={total_raw_segments:>9,} | "
        f"intersect={inside_segments:>8,} | "
        f"edges={edge_id:>9,}"
    )


# =============================================================================
# F. QA BUILD B2
# =============================================================================

out()
out("F. QA BUILD B2")
out("-" * 100)

final_node_count = cur.execute(
    "SELECT COUNT(*) FROM nodes"
).fetchone()[0]

final_segment_count = cur.execute(
    "SELECT COUNT(*) FROM segments"
).fetchone()[0]

final_edge_count = cur.execute(
    "SELECT COUNT(*) FROM directed_edges"
).fetchone()[0]

native_length_m = cur.execute(
    "SELECT SUM(length_m) FROM segments"
).fetchone()[0]

native_length_m = float(native_length_m or 0)

represented_way_count = cur.execute(
    "SELECT COUNT(DISTINCT way_id) FROM segments"
).fetchone()[0]

missing_after_clip = (
    source_unique_way_count
    - represented_way_count
)

length_delta_m = (
    native_length_m
    - source_length_m
)

length_delta_pct = (
    100.0
    * length_delta_m
    / source_length_m
)

self_loops = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE u = v
    """
).fetchone()[0]

out(f"Raw segmenti B1          : {total_raw_segments:,}")
out(f"Candidate bbox           : {bbox_candidates:,}")
out(f"Segmenti intersect mask  : {inside_segments:,}")
out(f"Segmenti fuori mask      : {outside_segments:,}")
out(f"Segmenti zero-length     : {zero_length_segments:,}")

out()
out(f"Way rappresentate        : {represented_way_count:,}")
out(f"Way sorgente v3          : {source_unique_way_count:,}")
out(f"Way perse dopo clip      : {missing_after_clip:,}")

out()
out(f"Nodi finali              : {final_node_count:,}")
out(f"Segmenti finali          : {final_segment_count:,}")
out(f"Edge diretti             : {final_edge_count:,}")
out(f"Self-loop diretti        : {self_loops:,}")

out()
out(f"Lunghezza v3             : {source_length_m / 1000:,.3f} km")
out(f"Lunghezza nativa B2      : {native_length_m / 1000:,.3f} km")
out(f"Delta                    : {length_delta_m / 1000:,.3f} km")
out(f"Delta %                  : {length_delta_pct:+.4f}%")

out()
out("Edge per verso")
out("-" * 100)

for direction, n in cur.execute(
    """
    SELECT way_direction, COUNT(*)
    FROM directed_edges
    GROUP BY way_direction
    ORDER BY way_direction
    """
):
    out(f"{direction:<20} {n:>12,}")

out()
out("Segmenti per direction_status")
out("-" * 100)

for status, n in cur.execute(
    """
    SELECT direction_status, COUNT(*)
    FROM segments
    GROUP BY direction_status
    ORDER BY COUNT(*) DESC
    """
):
    out(f"{str(status):<40} {n:>12,}")

out()
out("Top highway per segmenti")
out("-" * 100)

for highway, n, km in cur.execute(
    """
    SELECT
        highway,
        COUNT(*),
        SUM(length_m) / 1000.0
    FROM segments
    GROUP BY highway
    ORDER BY COUNT(*) DESC
    """
):
    out(
        f"{str(highway):<25} "
        f"{n:>12,} "
        f"{float(km):>12,.3f} km"
    )


# =============================================================================
# G. METADATA FINALI
# =============================================================================

final_metadata = {
    "source_feature_count":
        source_feature_count,

    "source_unique_way_count":
        source_unique_way_count,

    "source_length_m":
        source_length_m,

    "raw_segment_count":
        total_raw_segments,

    "spatial_intersect_segment_count":
        inside_segments,

    "spatial_outside_segment_count":
        outside_segments,

    "zero_length_segment_count":
        zero_length_segments,

    "represented_way_count":
        represented_way_count,

    "missing_way_after_clip_count":
        missing_after_clip,

    "final_node_count":
        final_node_count,

    "final_segment_count":
        final_segment_count,

    "final_directed_edge_count":
        final_edge_count,

    "self_loop_directed_edge_count":
        self_loops,

    "native_length_m":
        native_length_m,

    "length_delta_vs_v3_m":
        length_delta_m,

    "length_delta_vs_v3_pct":
        length_delta_pct,
}

cur.executemany(
    """
    INSERT OR REPLACE INTO metadata(
        key,
        value
    )
    VALUES (?, ?)
    """,
    [
        (k, str(v))
        for k, v in final_metadata.items()
    ],
)

db.commit()


# =============================================================================
# H. FINALIZZAZIONE
# =============================================================================

out()
out("G. FINALIZZAZIONE")
out("-" * 100)

cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
db.commit()

db.close()
raw.close()

out(f"SQLite prodotto : {OUTDB}")
out(f"Dimensione      : {OUTDB.stat().st_size:,} bytes")

out()
out("=" * 100)

blocking = False

if missing_after_clip != 0:
    blocking = True
    out(
        "ATTENZIONE: alcune way del network v3 "
        "non sono rappresentate dopo il clipping."
    )

if abs(length_delta_pct) > 1.0:
    blocking = True
    out(
        "ATTENZIONE: delta metrico > 1% rispetto "
        "alla rete v3."
    )

if blocking:
    out("ESITO BUILD B2: CHECK REQUIRED")
else:
    out("ESITO BUILD B2: PASS")

out("=" * 100)
out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
