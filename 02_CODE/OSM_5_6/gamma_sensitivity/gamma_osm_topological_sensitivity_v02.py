from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from itertools import combinations
import json
import math
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from scipy.sparse import load_npz
from scipy.sparse.csgraph import breadth_first_order


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

B3 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b3\osm_core_connectivity_qa_v01.sqlite"
)

B5DIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b5"
)

TIME_NPZ = B5DIR / "osm_turn_state_time_v01.npz"
BASE_NODES_NPY = B5DIR / "osm_turn_state_base_nodes_v01.npy"
STATE_NODE_NPY = B5DIR / "osm_turn_state_node_id_v01.npy"

BASE_GPKG = ROOT / r"02_package\base_territoriale_fvg.gpkg"

COMUNI_LAYER = "comuni_fvg_2026"
CENTROIDI_LAYER = "centroidi_popolazione_comuni_fvg_final"

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "gamma_sensitivity"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUT_CANDIDATES = OUTDIR / "Gamma_OSM_topological_top20_E0_v02.csv"
OUT_SUMMARY = OUTDIR / "Gamma_OSM_topological_sensitivity_summary_E0_v02.csv"
OUT_DETAIL = OUTDIR / "Gamma_OSM_topological_sensitivity_detail_E0_v02.csv"
OUT_SKELETON = OUTDIR / "Gamma_OSM_topological_skeleton_summary_E0_v02.json"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"gamma_osm_topological_sensitivity_v02_{STAMP}.txt"

K_VALUES = [1, 2, 3, 5]
SEP_VALUES = [0.0, 50.0, 100.0, 150.0, 200.0]

TOP_K = 20
EXPECTED_MUNICIPALITIES = 215


# =============================================================================
# LOG
# =============================================================================

lines = []

def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


# =============================================================================
# HELPERS
# =============================================================================

def detect_field(columns, candidates):

    lut = {
        str(c).lower(): c
        for c in columns
    }

    for c in candidates:
        if c.lower() in lut:
            return lut[c.lower()]

    raise RuntimeError(
        f"Campo non trovato. Disponibili: {list(columns)}"
    )


def norm_code(x):
    return int(float(x))


def pct(values, q):

    a = np.asarray(
        values,
        dtype=float,
    )

    return (
        float(np.percentile(a, q))
        if len(a)
        else np.nan
    )


def pair_metrics(records, topo_sets):

    if len(records) < 2:
        return np.nan, 0

    min_sep = float("inf")
    shared = 0

    for a, b in combinations(records, 2):

        sep = math.hypot(
            a["x"] - b["x"],
            a["y"] - b["y"],
        )

        min_sep = min(
            min_sep,
            sep,
        )

        if (
            topo_sets[int(a["node_id"])]
            &
            topo_sets[int(b["node_id"])]
        ):
            shared += 1

    return float(min_sep), shared


def best_anchored(
    records,
    K,
    min_sep_m,
    topo_sets,
):

    if len(records) < K:
        return None

    primary = records[0]

    if K == 1:
        return [primary]

    n = len(records)

    sep = np.zeros(
        (n, n),
        dtype=float,
    )

    independent = np.ones(
        (n, n),
        dtype=bool,
    )

    for i in range(n):

        for j in range(i + 1, n):

            d = math.hypot(
                records[i]["x"] - records[j]["x"],
                records[i]["y"] - records[j]["y"],
            )

            sep[i, j] = d
            sep[j, i] = d

            ok = not bool(
                topo_sets[int(records[i]["node_id"])]
                &
                topo_sets[int(records[j]["node_id"])]
            )

            independent[i, j] = ok
            independent[j, i] = ok

    best = None
    best_obj = None

    for combo in combinations(
        range(1, n),
        K - 1,
    ):

        idxs = (0,) + combo

        feasible = True
        min_pair = float("inf")

        for i, j in combinations(idxs, 2):

            if not independent[i, j]:
                feasible = False
                break

            if sep[i, j] < min_sep_m:
                feasible = False
                break

            min_pair = min(
                min_pair,
                sep[i, j],
            )

        if not feasible:
            continue

        chosen = [
            records[i]
            for i in idxs
        ]

        distances = [
            float(r["distance_m"])
            for r in chosen
        ]

        obj = (
            max(distances),
            sum(distances),
            -min_pair,
            tuple(
                int(r["node_id"])
                for r in chosen
            ),
        )

        if (
            best_obj is None
            or obj < best_obj
        ):
            best_obj = obj
            best = chosen

    return best


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 116)
out("FASE 5.6 — E0_v02 — Gamma_OSM TOPOLOGICAL TRANSFER SENSITIVITY")
out("=" * 116)

for p in [
    B2,
    B3,
    TIME_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
    BASE_GPKG,
]:
    if not p.exists():
        raise FileNotFoundError(p)

for p in [
    OUT_CANDIDATES,
    OUT_SUMMARY,
    OUT_DETAIL,
    OUT_SKELETON,
]:
    if p.exists():
        raise RuntimeError(
            f"Output già esistente: {p}"
        )


# =============================================================================
# A. TERRITORIO
# =============================================================================

out()
out("A. TERRITORIO")
out("-" * 116)

comuni = gpd.read_file(
    BASE_GPKG,
    layer=COMUNI_LAYER,
).to_crs(32632)

centroidi = gpd.read_file(
    BASE_GPKG,
    layer=CENTROIDI_LAYER,
).to_crs(32632)

cf = detect_field(
    comuni.columns,
    ["PRO_COM", "PROCOM", "PRO_COM_T", "COD_PROCOM"],
)

pf = detect_field(
    centroidi.columns,
    ["PRO_COM", "PROCOM", "PRO_COM_T", "COD_PROCOM"],
)

name_field = None

for c in [
    "COMUNE",
    "DEN_COM",
    "COMUNE_NOME",
    "NAME",
    "DENOMINAZIONE",
]:
    if c.lower() in {
        str(x).lower()
        for x in comuni.columns
    }:
        name_field = detect_field(
            comuni.columns,
            [c],
        )
        break

comuni = comuni.copy()
centroidi = centroidi.copy()

comuni["PRO_COM_X"] = comuni[cf].map(norm_code)
centroidi["PRO_COM_X"] = centroidi[pf].map(norm_code)

if len(comuni) != 215 or len(centroidi) != 215:
    raise RuntimeError(
        "Cardinalità territorio inattesa."
    )

centroid_map = {
    int(r.PRO_COM_X): r.geometry
    for r in centroidi[
        ["PRO_COM_X", "geometry"]
    ].itertuples()
}

out("Comuni / centroidi : 215 / 215")


# =============================================================================
# B. NODI GIANT SCC + DEGREE
# =============================================================================

out()
out("B. B3 GIANT SCC")
out("-" * 116)

con = sqlite3.connect(B2)

con.execute(
    "ATTACH DATABASE ? AS qa",
    (str(B3),),
)

rows = con.execute(
    """
    SELECT
        n.node_id,
        n.x,
        n.y,
        n.lon,
        n.lat,
        q.undirected_degree

    FROM nodes AS n

    JOIN qa.node_components AS q
      ON q.node_id = n.node_id

    WHERE q.in_giant_scc = 1

    ORDER BY n.node_id
    """
).fetchall()

node_ids = np.asarray(
    [int(r[0]) for r in rows],
    dtype=np.int64,
)

xs = np.asarray(
    [float(r[1]) for r in rows],
    dtype=float,
)

ys = np.asarray(
    [float(r[2]) for r in rows],
    dtype=float,
)

lons = np.asarray(
    [float(r[3]) for r in rows],
    dtype=float,
)

lats = np.asarray(
    [float(r[4]) for r in rows],
    dtype=float,
)

degrees = np.asarray(
    [int(r[5]) for r in rows],
    dtype=np.int32,
)

out(f"Giant SCC nodes : {len(node_ids):,}")


# =============================================================================
# C. B5 MUTUAL DOMAIN
# =============================================================================

out()
out("C. B5 MUTUAL DOMAIN")
out("-" * 116)

TIME = load_npz(
    TIME_NPZ
).tocsr()

base_nodes = np.load(
    BASE_NODES_NPY
)

state_node = np.load(
    STATE_NODE_NPY
)

anchor_node = int(node_ids[0])

anchor_state = int(
    np.searchsorted(
        base_nodes,
        anchor_node,
    )
)

forward_states = breadth_first_order(
    TIME,
    i_start=anchor_state,
    directed=True,
    return_predecessors=False,
)

reverse_states = breadth_first_order(
    TIME.transpose().tocsr(),
    i_start=anchor_state,
    directed=True,
    return_predecessors=False,
)

forward_phys = np.unique(
    state_node[
        np.asarray(
            forward_states,
            dtype=np.int64,
        )
    ]
)

forward_phys.sort()

fp = np.searchsorted(
    forward_phys,
    node_ids,
)

destination_ok = (
    fp < len(forward_phys)
)

safe = np.minimum(
    fp,
    len(forward_phys) - 1,
)

destination_ok &= (
    forward_phys[safe]
    == node_ids
)

bp = np.searchsorted(
    base_nodes,
    node_ids,
)

base_ok = (
    bp < len(base_nodes)
)

safe_bp = np.minimum(
    bp,
    len(base_nodes) - 1,
)

base_ok &= (
    base_nodes[safe_bp]
    == node_ids
)

reverse_mask = np.zeros(
    TIME.shape[0],
    dtype=bool,
)

reverse_mask[
    np.asarray(
        reverse_states,
        dtype=np.int64,
    )
] = True

origin_ok = np.zeros(
    len(node_ids),
    dtype=bool,
)

valid = np.flatnonzero(
    base_ok
)

origin_ok[valid] = reverse_mask[
    bp[valid]
]

mutual = (
    destination_ok
    &
    origin_ok
)

out(
    f"Mutual nodes : "
    f"{int(mutual.sum()):,}"
)

out(
    f"Excluded     : "
    f"{int((~mutual).sum()):,}"
)

node_ids = node_ids[mutual]
xs = xs[mutual]
ys = ys[mutual]
lons = lons[mutual]
lats = lats[mutual]
degrees = degrees[mutual]

del TIME
del reverse_mask


# =============================================================================
# D. INCIDENT WAY COUNT
# =============================================================================

out()
out("D. STRUCTURAL NODE DETECTION")
out("-" * 116)

out("Calcolo numero di OSM way incidenti...")

way_count = {}

for nid, nways in con.execute(
    """
    SELECT
        node_id,
        COUNT(DISTINCT way_id)

    FROM (
        SELECT osm_u AS node_id, way_id
        FROM segments

        UNION ALL

        SELECT osm_v AS node_id, way_id
        FROM segments
    )

    GROUP BY node_id
    """
):
    way_count[int(nid)] = int(nways)


incident_way_count = np.asarray(
    [
        way_count.get(
            int(nid),
            0,
        )
        for nid in node_ids
    ],
    dtype=np.int16,
)


# Un semplice shape node interno a una singola OSM way
# ha normalmente degree=2 e una sola way incidente.
structural_mask = (
    (degrees != 2)
    |
    (incident_way_count >= 2)
)

raw_mutual_count = len(node_ids)

node_ids = node_ids[structural_mask]
xs = xs[structural_mask]
ys = ys[structural_mask]
lons = lons[structural_mask]
lats = lats[structural_mask]
degrees = degrees[structural_mask]
incident_way_count = incident_way_count[
    structural_mask
]

structural_set = set(
    int(x)
    for x in node_ids
)

out(f"B5 mutual raw nodes   : {raw_mutual_count:,}")
out(f"Structural nodes      : {len(node_ids):,}")
out(
    f"Shape-like removed    : "
    f"{raw_mutual_count - len(node_ids):,}"
)


# =============================================================================
# E. BUILD TOPOLOGICAL SEGMENTS
# =============================================================================

out()
out("E. TOPOLOGICAL SEGMENT SKELETON")
out("-" * 116)

topo_sets = defaultdict(set)

topo_segment_count = 0
native_segment_count = 0

read = con.execute(
    """
    SELECT
        way_id,
        seq,
        osm_u,
        osm_v

    FROM segments

    ORDER BY
        way_id,
        seq
    """
)


current_way = None
piece_start_node = None
piece_start_seq = None

prev_seq = None
prev_v = None


def finalize_piece(
    way_id,
    start_seq,
    end_seq,
    start_node,
    end_node,
):
    global topo_segment_count

    if (
        way_id is None
        or start_seq is None
        or end_seq is None
        or start_node is None
        or end_node is None
    ):
        return

    topo_segment_count += 1

    uid = (
        f"{int(way_id)}:"
        f"{int(start_seq)}-{int(end_seq)}"
    )

    # Solo gli endpoint strutturali possono
    # diventare candidati Gamma.
    if int(start_node) in structural_set:
        topo_sets[
            int(start_node)
        ].add(uid)

    if int(end_node) in structural_set:
        topo_sets[
            int(end_node)
        ].add(uid)


for wid, seq, u, v in read:

    wid = int(wid)
    seq = int(seq)
    u = int(u)
    v = int(v)

    native_segment_count += 1

    new_run = (
        current_way is None
        or wid != current_way
        or prev_seq is None
        or seq != prev_seq + 1
        or prev_v != u
    )

    if new_run:

        if current_way is not None:
            finalize_piece(
                current_way,
                piece_start_seq,
                prev_seq,
                piece_start_node,
                prev_v,
            )

        current_way = wid
        piece_start_node = u
        piece_start_seq = seq

    # Ogni structural node spezza la way in
    # un nuovo topological segment.
    if (
        v in structural_set
        and piece_start_node is not None
    ):

        finalize_piece(
            wid,
            piece_start_seq,
            seq,
            piece_start_node,
            v,
        )

        piece_start_node = v
        piece_start_seq = seq + 1

    prev_seq = seq
    prev_v = v


if current_way is not None:

    if (
        piece_start_seq is not None
        and piece_start_seq <= prev_seq
    ):

        finalize_piece(
            current_way,
            piece_start_seq,
            prev_seq,
            piece_start_node,
            prev_v,
        )


missing_topo = [
    int(nid)
    for nid in node_ids
    if not topo_sets.get(
        int(nid)
    )
]

out(
    f"Native segments       : "
    f"{native_segment_count:,}"
)

out(
    f"Topological segments  : "
    f"{topo_segment_count:,}"
)

out(
    f"Structural nodes no topo incidence : "
    f"{len(missing_topo):,}"
)

if missing_topo:
    raise RuntimeError(
        "Structural nodes senza topological segment."
    )


# =============================================================================
# F. TOP20 STRUCTURAL CANDIDATES
# =============================================================================

out()
out("F. TOP-20 STRUCTURAL CANDIDATES")
out("-" * 116)

points = shapely.points(
    xs,
    ys,
)

tree = STRtree(
    points
)

candidate_rows = []
pool_sizes = []
top20_spans = []


for _, row in comuni.sort_values(
    "PRO_COM_X"
).iterrows():

    pro_com = int(
        row["PRO_COM_X"]
    )

    comune_name = (
        str(row[name_field])
        if name_field is not None
        else str(pro_com)
    )

    geom = row.geometry

    if not geom.is_valid:
        geom = shapely.make_valid(
            geom
        )

    idx = np.asarray(
        tree.query(
            geom.buffer(2.0),
            predicate="intersects",
        ),
        dtype=np.int64,
    )

    pool_sizes.append(
        len(idx)
    )

    if len(idx) == 0:
        continue

    cp = centroid_map[
        pro_com
    ]

    d = np.hypot(
        xs[idx] - float(cp.x),
        ys[idx] - float(cp.y),
    )

    order = np.lexsort(
        (
            node_ids[idx],
            d,
        )
    )

    idx = idx[
        order[:TOP_K]
    ]

    d = d[
        order[:TOP_K]
    ]

    if len(d):
        top20_spans.append(
            float(
                d[-1] - d[0]
            )
        )

    for rank, (
        p,
        dist,
    ) in enumerate(
        zip(idx, d),
        start=1,
    ):

        nid = int(
            node_ids[p]
        )

        candidate_rows.append({
            "PRO_COM":
                pro_com,

            "COMUNE":
                comune_name,

            "source_rank":
                rank,

            "node_id":
                nid,

            "x":
                float(xs[p]),

            "y":
                float(ys[p]),

            "lon":
                float(lons[p]),

            "lat":
                float(lats[p]),

            "distance_m":
                float(dist),

            "undirected_degree":
                int(degrees[p]),

            "incident_way_count":
                int(
                    incident_way_count[p]
                ),

            "incident_topo_count":
                len(
                    topo_sets[nid]
                ),

            "incident_topo_ids":
                json.dumps(
                    sorted(
                        topo_sets[nid]
                    ),
                    separators=(",", ":"),
                ),
        })


cand = pd.DataFrame(
    candidate_rows
)

cand.to_csv(
    OUT_CANDIDATES,
    index=False,
    encoding="utf-8-sig",
)


counts = cand.groupby(
    "PRO_COM"
).size()

out(
    f"Candidate rows         : "
    f"{len(cand):,}"
)

out(
    f"Structural pool min/med/max : "
    f"{min(pool_sizes):,} / "
    f"{np.median(pool_sizes):.1f} / "
    f"{max(pool_sizes):,}"
)

out(
    f"Comuni con >=20 structural : "
    f"{int((counts >= 20).sum())}/215"
)

out(
    f"Top20 physical span median : "
    f"{np.median(top20_spans):.1f} m"
)

out(
    f"Top20 physical span p95    : "
    f"{pct(top20_spans, 95):.1f} m"
)


# =============================================================================
# G. NEAREST-K DIAGNOSTIC
# =============================================================================

out()
out("G. NEAREST-K STRUCTURAL DIAGNOSTIC")
out("-" * 116)

nearest_summary = []

for K in K_VALUES:

    feasible = 0
    shared_municipalities = 0
    short50 = 0
    short100 = 0

    for _, group in cand.groupby(
        "PRO_COM"
    ):

        records = (
            group
            .sort_values(
                [
                    "source_rank",
                    "node_id",
                ]
            )
            .to_dict("records")
        )

        if len(records) < K:
            continue

        feasible += 1

        chosen = records[:K]

        min_sep, shared = pair_metrics(
            chosen,
            topo_sets,
        )

        if shared > 0:
            shared_municipalities += 1

        if K > 1:

            if min_sep < 50:
                short50 += 1

            if min_sep < 100:
                short100 += 1

    nearest_summary.append(
        (
            K,
            feasible,
            shared_municipalities,
            short50,
            short100,
        )
    )

    out(
        f"K={K} | "
        f"feasible={feasible}/215 | "
        f"shared-toposeg={shared_municipalities} | "
        f"minsep<50={short50} | "
        f"minsep<100={short100}"
    )


# =============================================================================
# H. ANCHORED SENSITIVITY
# =============================================================================

out()
out("H. ANCHORED TOPOLOGICAL SENSITIVITY")
out("-" * 116)

detail_rows = []
summary_rows = []


for K in K_VALUES:

    for sep_rule in SEP_VALUES:

        feasible_count = 0

        extra_max = []
        min_seps = []
        max_ranks = []

        for pro_com, group in cand.groupby(
            "PRO_COM",
            sort=True,
        ):

            records = (
                group
                .sort_values(
                    [
                        "source_rank",
                        "distance_m",
                        "node_id",
                    ]
                )
                .to_dict("records")
            )

            chosen = best_anchored(
                records,
                K,
                sep_rule,
                topo_sets,
            )

            if chosen is None:

                detail_rows.append({
                    "PRO_COM":
                        int(pro_com),

                    "COMUNE":
                        records[0]["COMUNE"]
                        if records
                        else None,

                    "K":
                        K,

                    "sep_rule_m":
                        sep_rule,

                    "feasible":
                        0,
                })

                continue

            feasible_count += 1

            d = [
                float(r["distance_m"])
                for r in chosen
            ]

            ranks = [
                int(r["source_rank"])
                for r in chosen
            ]

            min_sep, shared = pair_metrics(
                chosen,
                topo_sets,
            )

            extra = max(d) - d[0]

            extra_max.append(
                extra
            )

            if K > 1:
                min_seps.append(
                    min_sep
                )

            max_ranks.append(
                max(ranks)
            )

            detail_rows.append({
                "PRO_COM":
                    int(pro_com),

                "COMUNE":
                    chosen[0]["COMUNE"],

                "K":
                    K,

                "sep_rule_m":
                    sep_rule,

                "feasible":
                    1,

                "primary_node_id":
                    int(
                        chosen[0]["node_id"]
                    ),

                "selected_node_ids":
                    json.dumps(
                        [
                            int(r["node_id"])
                            for r in chosen
                        ],
                        separators=(",", ":"),
                    ),

                "selected_source_ranks":
                    json.dumps(
                        ranks,
                        separators=(",", ":"),
                    ),

                "primary_distance_m":
                    d[0],

                "max_distance_m":
                    max(d),

                "extra_max_distance_m":
                    extra,

                "min_pair_sep_m":
                    min_sep,

                "shared_toposeg_pairs":
                    shared,

                "max_source_rank":
                    max(ranks),
            })


        row = {
            "K":
                K,

            "sep_rule_m":
                sep_rule,

            "feasible_municipalities":
                feasible_count,

            "median_extra_max_m":
                (
                    float(np.median(extra_max))
                    if extra_max
                    else np.nan
                ),

            "p95_extra_max_m":
                pct(
                    extra_max,
                    95,
                ),

            "max_extra_max_m":
                (
                    float(max(extra_max))
                    if extra_max
                    else np.nan
                ),

            "median_min_pair_sep_m":
                (
                    float(np.median(min_seps))
                    if min_seps
                    else np.nan
                ),

            "min_pair_sep_m":
                (
                    float(min(min_seps))
                    if min_seps
                    else np.nan
                ),

            "max_source_rank":
                (
                    int(max(max_ranks))
                    if max_ranks
                    else np.nan
                ),
        }

        summary_rows.append(
            row
        )

        out(
            f"K={K} | "
            f"sep={sep_rule:>3.0f} m | "
            f"feasible={feasible_count:>3}/215 | "
            f"extra-med={row['median_extra_max_m']:7.1f} m | "
            f"extra-p95={row['p95_extra_max_m']:7.1f} m | "
            f"rank-max={row['max_source_rank']}"
        )


detail = pd.DataFrame(
    detail_rows
)

summary = pd.DataFrame(
    summary_rows
)

detail.to_csv(
    OUT_DETAIL,
    index=False,
    encoding="utf-8-sig",
)

summary.to_csv(
    OUT_SUMMARY,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# I. SKELETON MANIFEST
# =============================================================================

manifest = {
    "phase":
        "FASE_5_6_E0_v02",

    "purpose":
        "topology-equivalent transfer validation of Gamma from GSFVG to OSM",

    "structural_node_rule":
        "B5 mutual node AND (undirected_degree != 2 OR incident distinct OSM ways >= 2)",

    "topological_segment_rule":
        "consecutive native OSM segments on one way, split at structural nodes",

    "independence_rule":
        "no shared incident topological segment",

    "raw_mutual_nodes":
        int(raw_mutual_count),

    "structural_nodes":
        int(len(node_ids)),

    "topological_segments":
        int(topo_segment_count),

    "top20_physical_span_median":
        float(np.median(top20_spans)),

    "top20_physical_span_p95":
        pct(top20_spans, 95),

    "K_values":
        K_VALUES,

    "separation_values_m":
        SEP_VALUES,
}

OUT_SKELETON.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# =============================================================================
# FINAL
# =============================================================================

out()
out("=" * 116)
out("ESITO E0_v02: TOPOLOGICAL_SENSITIVITY_READY")
out("=" * 116)

out(f"Candidates : {OUT_CANDIDATES}")
out(f"Summary    : {OUT_SUMMARY}")
out(f"Detail     : {OUT_DETAIL}")
out(f"Skeleton   : {OUT_SKELETON}")
out(f"LOG        : {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

con.close()
