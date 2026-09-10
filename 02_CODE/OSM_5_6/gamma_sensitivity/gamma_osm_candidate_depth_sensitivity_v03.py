from pathlib import Path
from datetime import datetime
from collections import defaultdict
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

BASE_GPKG = (
    ROOT
    / r"02_package\base_territoriale_fvg.gpkg"
)

COMUNI_LAYER = "comuni_fvg_2026"
CENTROIDI_LAYER = "centroidi_popolazione_comuni_fvg_final"

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "gamma_sensitivity"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

LOG = (
    OUTDIR
    / f"gamma_osm_candidate_depth_sensitivity_v03_{STAMP}.txt"
)

OUT_CANDIDATES = (
    OUTDIR
    / "Gamma_OSM_topological_top50_E0_v03.csv"
)

OUT_DETAIL = (
    OUTDIR
    / "Gamma_OSM_candidate_depth_detail_E0_v03.csv"
)

OUT_SUMMARY = (
    OUTDIR
    / "Gamma_OSM_candidate_depth_summary_E0_v03.csv"
)

OUT_REQUIRED_RANK = (
    OUTDIR
    / "Gamma_OSM_K3_100m_required_rank_E0_v03.csv"
)

OUT_MANIFEST = (
    OUTDIR
    / "Gamma_OSM_candidate_depth_manifest_E0_v03.json"
)

POOL_DEPTHS = [20, 25, 30, 40, 50]
SEP_VALUES = [50.0, 100.0, 150.0, 200.0]

MAX_POOL = 50
K = 3

EXPECTED_COMUNI = 215


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

    for candidate in candidates:
        if candidate.lower() in lut:
            return lut[candidate.lower()]

    raise RuntimeError(
        f"Campo non trovato. Disponibili: {list(columns)}"
    )


def pct(values, q):

    a = np.asarray(values, dtype=float)

    if len(a) == 0:
        return np.nan

    return float(
        np.percentile(a, q)
    )


def best_anchored(
    records,
    min_sep_m,
    topo_sets,
):
    """
    K=3 fisso.

    Primary = nearest.
    Fra le coppie secondarie ammissibili:
      1 min max distance
      2 min sum distance
      3 max min pair separation
      4 deterministic node-id tie-break
    """

    if len(records) < 3:
        return None

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

            independent[i, j] = not bool(
                topo_sets[
                    int(records[i]["node_id"])
                ]
                &
                topo_sets[
                    int(records[j]["node_id"])
                ]
            )

            independent[j, i] = independent[i, j]

    best = None
    best_obj = None

    # primary = indice 0
    for i, j in combinations(
        range(1, n),
        2,
    ):

        idxs = (0, i, j)

        feasible = True
        min_pair = float("inf")

        for a, b in combinations(
            idxs,
            2,
        ):

            if not independent[a, b]:
                feasible = False
                break

            if sep[a, b] < min_sep_m:
                feasible = False
                break

            min_pair = min(
                min_pair,
                sep[a, b],
            )

        if not feasible:
            continue

        chosen = [
            records[x]
            for x in idxs
        ]

        dists = [
            float(x["distance_m"])
            for x in chosen
        ]

        obj = (
            max(dists),
            sum(dists),
            -min_pair,
            tuple(
                int(x["node_id"])
                for x in chosen
            ),
        )

        if (
            best_obj is None
            or obj < best_obj
        ):
            best_obj = obj
            best = chosen

    return best


def selected_metrics(chosen):

    d = [
        float(x["distance_m"])
        for x in chosen
    ]

    min_sep = min(
        math.hypot(
            a["x"] - b["x"],
            a["y"] - b["y"],
        )
        for a, b in combinations(
            chosen,
            2,
        )
    )

    return {
        "primary_distance_m":
            d[0],

        "max_distance_m":
            max(d),

        "extra_max_distance_m":
            max(d) - d[0],

        "sum_distance_m":
            sum(d),

        "min_pair_sep_m":
            min_sep,

        "max_source_rank":
            max(
                int(x["source_rank"])
                for x in chosen
            ),

        "selected_node_ids":
            json.dumps(
                [
                    int(x["node_id"])
                    for x in chosen
                ],
                separators=(",", ":"),
            ),

        "selected_source_ranks":
            json.dumps(
                [
                    int(x["source_rank"])
                    for x in chosen
                ],
                separators=(",", ":"),
            ),
    }


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 118)
out("FASE 5.6 — E0_v03 — Gamma_OSM CANDIDATE-DEPTH SENSITIVITY")
out("=" * 118)

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
    OUT_DETAIL,
    OUT_SUMMARY,
    OUT_REQUIRED_RANK,
    OUT_MANIFEST,
]:
    if p.exists():
        raise RuntimeError(
            f"Output già esistente: {p}"
        )

out(f"K              : {K}")
out(f"Pool depths    : {POOL_DEPTHS}")
out(f"Separations    : {SEP_VALUES}")


# =============================================================================
# A. TERRITORIO
# =============================================================================

out()
out("A. TERRITORIO")
out("-" * 118)

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
    [
        "PRO_COM",
        "PROCOM",
        "PRO_COM_T",
        "COD_PROCOM",
    ],
)

pf = detect_field(
    centroidi.columns,
    [
        "PRO_COM",
        "PROCOM",
        "PRO_COM_T",
        "COD_PROCOM",
    ],
)

name_field = None

for candidate in [
    "COMUNE",
    "DEN_COM",
    "COMUNE_NOME",
    "NAME",
    "DENOMINAZIONE",
]:

    try:
        name_field = detect_field(
            comuni.columns,
            [candidate],
        )
        break
    except Exception:
        pass


comuni = comuni.copy()
centroidi = centroidi.copy()

comuni["PRO_COM_X"] = comuni[
    cf
].map(
    lambda x: int(float(x))
)

centroidi["PRO_COM_X"] = centroidi[
    pf
].map(
    lambda x: int(float(x))
)

if (
    len(comuni) != EXPECTED_COMUNI
    or len(centroidi) != EXPECTED_COMUNI
):
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
# B. B3 GIANT SCC
# =============================================================================

out()
out("B. B3 GIANT SCC")
out("-" * 118)

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
)

ys = np.asarray(
    [float(r[2]) for r in rows],
)

lons = np.asarray(
    [float(r[3]) for r in rows],
)

lats = np.asarray(
    [float(r[4]) for r in rows],
)

degrees = np.asarray(
    [int(r[5]) for r in rows],
    dtype=np.int32,
)

out(f"Giant SCC nodes : {len(node_ids):,}")


# =============================================================================
# C. B5 MUTUAL
# =============================================================================

out()
out("C. B5 MUTUAL DOMAIN")
out("-" * 118)

TIME = load_npz(
    TIME_NPZ
).tocsr()

base_nodes = np.load(
    BASE_NODES_NPY
)

state_node = np.load(
    STATE_NODE_NPY
)

anchor_node = int(
    node_ids[0]
)

anchor_state = int(
    np.searchsorted(
        base_nodes,
        anchor_node,
    )
)

if (
    anchor_state >= len(base_nodes)
    or int(base_nodes[anchor_state])
    != anchor_node
):
    raise RuntimeError(
        "Anchor non trovato."
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

safe_fp = np.minimum(
    fp,
    len(forward_phys) - 1,
)

destination_ok &= (
    forward_phys[safe_fp]
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
    f"B5 mutual nodes : "
    f"{int(mutual.sum()):,}"
)

out(
    f"Excluded        : "
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
# D. STRUCTURAL NODES
# =============================================================================

out()
out("D. STRUCTURAL NODE DETECTION")
out("-" * 118)

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

structural_mask = (
    (degrees != 2)
    |
    (incident_way_count >= 2)
)

raw_count = len(node_ids)

node_ids = node_ids[structural_mask]
xs = xs[structural_mask]
ys = ys[structural_mask]
lons = lons[structural_mask]
lats = lats[structural_mask]
degrees = degrees[structural_mask]
incident_way_count = (
    incident_way_count[
        structural_mask
    ]
)

structural_set = set(
    int(x)
    for x in node_ids
)

out(f"Mutual raw nodes  : {raw_count:,}")
out(f"Structural nodes  : {len(node_ids):,}")


# =============================================================================
# E. TOPOLOGICAL SEGMENTS
# =============================================================================

out()
out("E. TOPOLOGICAL SEGMENT SKELETON")
out("-" * 118)

topo_sets = defaultdict(set)

topo_segment_count = 0

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
        or start_seq > end_seq
    ):
        return

    topo_segment_count += 1

    uid = (
        f"{int(way_id)}:"
        f"{int(start_seq)}-{int(end_seq)}"
    )

    if int(start_node) in structural_set:
        topo_sets[
            int(start_node)
        ].add(uid)

    if int(end_node) in structural_set:
        topo_sets[
            int(end_node)
        ].add(uid)


for wid, seq, u, v in con.execute(
    """
    SELECT
        way_id,
        seq,
        osm_u,
        osm_v

    FROM segments

    ORDER BY way_id, seq
    """
):

    wid = int(wid)
    seq = int(seq)
    u = int(u)
    v = int(v)

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


if (
    current_way is not None
    and piece_start_seq is not None
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
    f"Topological segments : "
    f"{topo_segment_count:,}"
)

out(
    f"Structural no incidence : "
    f"{len(missing_topo):,}"
)

if missing_topo:
    raise RuntimeError(
        "Structural nodes senza topo segment."
    )


# =============================================================================
# F. TOP-50 CANDIDATES
# =============================================================================

out()
out("F. TOP-50 STRUCTURAL CANDIDATES")
out("-" * 118)

points = shapely.points(
    xs,
    ys,
)

tree = STRtree(
    points
)

candidate_rows = []
pool_sizes = []

for _, municipality in comuni.sort_values(
    "PRO_COM_X"
).iterrows():

    pro_com = int(
        municipality["PRO_COM_X"]
    )

    comune_name = (
        str(
            municipality[
                name_field
            ]
        )
        if name_field is not None
        else str(pro_com)
    )

    geom = municipality.geometry

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

    centroid = centroid_map[
        pro_com
    ]

    distances = np.hypot(
        xs[idx] - float(centroid.x),
        ys[idx] - float(centroid.y),
    )

    order = np.lexsort(
        (
            node_ids[idx],
            distances,
        )
    )

    idx = idx[
        order[:MAX_POOL]
    ]

    distances = distances[
        order[:MAX_POOL]
    ]

    for rank, (
        p,
        d,
    ) in enumerate(
        zip(idx, distances),
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
                float(d),

            "undirected_degree":
                int(degrees[p]),

            "incident_topo_count":
                len(
                    topo_sets[nid]
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
    f"Candidate rows       : "
    f"{len(cand):,}"
)

out(
    f"Pool min/med/max     : "
    f"{min(pool_sizes):,} / "
    f"{np.median(pool_sizes):.1f} / "
    f"{max(pool_sizes):,}"
)

out(
    f"Comuni con >=50      : "
    f"{int((counts >= 50).sum())}/215"
)


# =============================================================================
# G. DEPTH × SEPARATION
# =============================================================================

out()
out("G. DEPTH × SEPARATION SENSITIVITY — K=3")
out("-" * 118)

detail_rows = []
summary_rows = []


for depth in POOL_DEPTHS:

    for sep_rule in SEP_VALUES:

        feasible_count = 0

        extras = []
        max_distances = []
        min_separations = []
        ranks = []

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
                .head(depth)
                .to_dict("records")
            )

            chosen = best_anchored(
                records,
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

                    "pool_depth":
                        depth,

                    "K":
                        K,

                    "sep_rule_m":
                        sep_rule,

                    "feasible":
                        0,
                })

                continue

            feasible_count += 1

            metrics = selected_metrics(
                chosen
            )

            extras.append(
                metrics[
                    "extra_max_distance_m"
                ]
            )

            max_distances.append(
                metrics[
                    "max_distance_m"
                ]
            )

            min_separations.append(
                metrics[
                    "min_pair_sep_m"
                ]
            )

            ranks.append(
                metrics[
                    "max_source_rank"
                ]
            )

            detail_rows.append({
                "PRO_COM":
                    int(pro_com),

                "COMUNE":
                    chosen[0]["COMUNE"],

                "pool_depth":
                    depth,

                "K":
                    K,

                "sep_rule_m":
                    sep_rule,

                "feasible":
                    1,

                **metrics,
            })


        summary = {
            "pool_depth":
                depth,

            "K":
                K,

            "sep_rule_m":
                sep_rule,

            "feasible_municipalities":
                feasible_count,

            "median_extra_max_m":
                (
                    float(
                        np.median(extras)
                    )
                    if extras
                    else np.nan
                ),

            "p95_extra_max_m":
                pct(
                    extras,
                    95,
                ),

            "max_extra_max_m":
                (
                    float(max(extras))
                    if extras
                    else np.nan
                ),

            "median_max_distance_m":
                (
                    float(
                        np.median(
                            max_distances
                        )
                    )
                    if max_distances
                    else np.nan
                ),

            "p95_max_distance_m":
                pct(
                    max_distances,
                    95,
                ),

            "median_min_sep_m":
                (
                    float(
                        np.median(
                            min_separations
                        )
                    )
                    if min_separations
                    else np.nan
                ),

            "min_observed_sep_m":
                (
                    float(
                        min(
                            min_separations
                        )
                    )
                    if min_separations
                    else np.nan
                ),

            "max_source_rank":
                (
                    int(max(ranks))
                    if ranks
                    else np.nan
                ),
        }

        summary_rows.append(
            summary
        )

        out(
            f"depth={depth:>2} | "
            f"sep={sep_rule:>3.0f} m | "
            f"feasible="
            f"{feasible_count:>3}/215 | "
            f"extra-med="
            f"{summary['median_extra_max_m']:7.1f} m | "
            f"extra-p95="
            f"{summary['p95_extra_max_m']:7.1f} m | "
            f"rank-max="
            f"{summary['max_source_rank']}"
        )


detail_df = pd.DataFrame(
    detail_rows
)

summary_df = pd.DataFrame(
    summary_rows
)

detail_df.to_csv(
    OUT_DETAIL,
    index=False,
    encoding="utf-8-sig",
)

summary_df.to_csv(
    OUT_SUMMARY,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# H. MINIMUM REQUIRED DEPTH FOR K=3, 100 m
# =============================================================================

out()
out("H. MINIMUM REQUIRED DEPTH — K=3, 100 m")
out("-" * 118)

required_rows = []

for pro_com, group in cand.groupby(
    "PRO_COM",
    sort=True,
):

    full_records = (
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

    minimum_depth = None
    chosen_final = None

    # Cerchiamo il primo rank che rende
    # disponibile almeno una tripletta valida.
    for depth in range(
        3,
        min(
            MAX_POOL,
            len(full_records)
        ) + 1,
    ):

        chosen = best_anchored(
            full_records[:depth],
            100.0,
            topo_sets,
        )

        if chosen is not None:
            minimum_depth = depth
            chosen_final = chosen
            break


    comune_name = (
        full_records[0]["COMUNE"]
        if full_records
        else None
    )

    if chosen_final is None:

        required_rows.append({
            "PRO_COM":
                int(pro_com),

            "COMUNE":
                comune_name,

            "feasible_within_50":
                0,

            "minimum_required_depth":
                np.nan,
        })

        out(
            f"FAIL within top50: "
            f"{pro_com} {comune_name}"
        )

    else:

        metrics = selected_metrics(
            chosen_final
        )

        required_rows.append({
            "PRO_COM":
                int(pro_com),

            "COMUNE":
                comune_name,

            "feasible_within_50":
                1,

            "minimum_required_depth":
                int(
                    minimum_depth
                ),

            **metrics,
        })


required_df = pd.DataFrame(
    required_rows
)

required_df.to_csv(
    OUT_REQUIRED_RANK,
    index=False,
    encoding="utf-8-sig",
)


feasible_50 = int(
    required_df[
        "feasible_within_50"
    ].sum()
)

out(
    f"Feasible K3@100 within top50 : "
    f"{feasible_50}/215"
)

if feasible_50 == 215:

    required_depths = (
        required_df[
            "minimum_required_depth"
        ].to_numpy(dtype=float)
    )

    out(
        f"Required depth median         : "
        f"{np.median(required_depths):.1f}"
    )

    out(
        f"Required depth p95            : "
        f"{pct(required_depths, 95):.1f}"
    )

    out(
        f"Required depth max            : "
        f"{int(np.max(required_depths))}"
    )

    out()
    out("Comuni che richiedono rank >20")
    out("-" * 118)

    exceptional = (
        required_df[
            required_df[
                "minimum_required_depth"
            ] > 20
        ]
        .sort_values(
            "minimum_required_depth"
        )
    )

    for r in exceptional.itertuples():

        out(
            f"{int(r.PRO_COM):>6} | "
            f"{r.COMUNE:<35} | "
            f"required_depth="
            f"{int(r.minimum_required_depth):>2} | "
            f"extra="
            f"{r.extra_max_distance_m:7.1f} m | "
            f"min_sep="
            f"{r.min_pair_sep_m:7.1f} m"
        )


# =============================================================================
# I. GATE INTERPRETATIVO
# =============================================================================

out()
out("I. GATE E0_v03")
out("-" * 118)

row_20_100 = summary_df[
    (summary_df["pool_depth"] == 20)
    &
    (summary_df["sep_rule_m"] == 100.0)
].iloc[0]

best_all_feasible_depth = None

for depth in POOL_DEPTHS:

    row = summary_df[
        (summary_df["pool_depth"] == depth)
        &
        (summary_df["sep_rule_m"] == 100.0)
    ].iloc[0]

    if int(
        row[
            "feasible_municipalities"
        ]
    ) == 215:

        best_all_feasible_depth = depth
        break


out(
    f"Top20 K3@100 : "
    f"{int(row_20_100['feasible_municipalities'])}/215"
)

out(
    f"Prima profondità testata con 215/215 : "
    f"{best_all_feasible_depth}"
)


if feasible_50 == 215:

    out(
        "INTERPRETAZIONE: "
        "100 m strutturalmente fattibile per 215/215; "
        "le eccezioni top20 sono candidate-pool truncation."
    )

    out(
        "ESITO E0_v03: K3_100_TRANSFER_FEASIBLE"
    )

else:

    out(
        "INTERPRETAZIONE: "
        "100 m non completamente fattibile neppure entro top50."
    )

    out(
        "ESITO E0_v03: CHECK_REQUIRED"
    )


# =============================================================================
# J. MANIFEST
# =============================================================================

manifest = {
    "phase":
        "FASE_5_6_E0_v03",

    "purpose":
        "test whether top20 truncation explains K=3, 100m OSM exceptions",

    "K":
        K,

    "pool_depths":
        POOL_DEPTHS,

    "separation_values_m":
        SEP_VALUES,

    "maximum_examined_pool":
        MAX_POOL,

    "feasible_K3_100_within_top50":
        feasible_50,

    "first_tested_depth_215_215":
        best_all_feasible_depth,

    "structural_nodes":
        int(len(node_ids)),

    "topological_segments":
        int(topo_segment_count),
}

OUT_MANIFEST.write_text(
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
out("=" * 118)
out("E0_v03 COMPLETATO")
out("=" * 118)

out(f"Summary       : {OUT_SUMMARY}")
out(f"Required rank : {OUT_REQUIRED_RANK}")
out(f"Manifest      : {OUT_MANIFEST}")
out(f"LOG           : {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

con.close()
