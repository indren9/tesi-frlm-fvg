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

OUTDIR.mkdir(parents=True, exist_ok=True)

OUT_CANDIDATES = OUTDIR / "Gamma_OSM_top20_candidates_E0_v01.csv"
OUT_NAIVE = OUTDIR / "Gamma_OSM_nearestK_sensitivity_E0_v01.csv"
OUT_ANCHORED = OUTDIR / "Gamma_OSM_anchored_sensitivity_E0_v01.csv"
OUT_SUMMARY = OUTDIR / "Gamma_OSM_sensitivity_summary_E0_v01.csv"
OUT_MANIFEST = OUTDIR / "Gamma_OSM_sensitivity_manifest_E0_v01.json"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"gamma_osm_structural_sensitivity_v01_{STAMP}.txt"

TOP_K = 20

K_VALUES = [1, 2, 3, 5]
SEPARATIONS_M = [0.0, 50.0, 100.0, 150.0, 200.0]

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

def detect_field(columns, candidates, label):

    lut = {
        str(c).lower(): c
        for c in columns
    }

    for candidate in candidates:

        if candidate.lower() in lut:
            return lut[candidate.lower()]

    raise RuntimeError(
        f"Campo {label} non riconosciuto. "
        f"Disponibili: {list(columns)}"
    )


def normalize_code(x):

    if pd.isna(x):
        return None

    return int(float(x))


def percentile(arr, q):

    arr = np.asarray(arr, dtype=float)

    if len(arr) == 0:
        return np.nan

    return float(
        np.percentile(arr, q)
    )


def pairwise_metrics(records, way_sets):

    if len(records) < 2:
        return {
            "min_sep_m": np.nan,
            "shared_way_pairs": 0,
            "pair_count": 0,
        }

    min_sep = float("inf")
    shared = 0
    pair_count = 0

    for a, b in combinations(records, 2):

        sep = math.hypot(
            a["x"] - b["x"],
            a["y"] - b["y"],
        )

        min_sep = min(
            min_sep,
            sep,
        )

        pair_count += 1

        if (
            way_sets[int(a["node_id"])]
            &
            way_sets[int(b["node_id"])]
        ):
            shared += 1

    return {
        "min_sep_m": float(min_sep),
        "shared_way_pairs": shared,
        "pair_count": pair_count,
    }


def best_anchored_selection(
    records,
    k,
    min_sep_m,
    way_sets,
):
    """
    Primary fissato = record rank 1.

    Tra le combinazioni ammissibili dei secondari:
      1. minimizza max distanza
      2. minimizza somma distanze
      3. massimizza min separazione
      4. tie-break deterministico node_id
    """

    if len(records) < k:
        return None

    primary = records[0]

    if k == 1:
        return [primary]

    # Matrici pairwise sul top20.
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
                records[i]["x"]
                - records[j]["x"],

                records[i]["y"]
                - records[j]["y"],
            )

            sep[i, j] = d
            sep[j, i] = d

            ok = not bool(
                way_sets[
                    int(records[i]["node_id"])
                ]
                &
                way_sets[
                    int(records[j]["node_id"])
                ]
            )

            independent[i, j] = ok
            independent[j, i] = ok

    best = None
    best_objective = None

    secondary_indices = range(
        1,
        n,
    )

    for combo in combinations(
        secondary_indices,
        k - 1,
    ):

        idxs = (0,) + combo

        feasible = True
        min_sep = float("inf")

        for i, j in combinations(
            idxs,
            2,
        ):

            if not independent[i, j]:
                feasible = False
                break

            if sep[i, j] < min_sep_m:
                feasible = False
                break

            min_sep = min(
                min_sep,
                sep[i, j],
            )

        if not feasible:
            continue

        chosen = [
            records[i]
            for i in idxs
        ]

        distances = [
            float(x["distance_m"])
            for x in chosen
        ]

        node_tuple = tuple(
            int(x["node_id"])
            for x in chosen
        )

        objective = (
            max(distances),
            sum(distances),
            -min_sep,
            node_tuple,
        )

        if (
            best_objective is None
            or objective < best_objective
        ):
            best_objective = objective
            best = chosen

    return best


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 112)
out("FASE 5.6 — E0 — Gamma_OSM STRUCTURAL SENSITIVITY")
out("=" * 112)

for path in [
    B2,
    B3,
    TIME_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
    BASE_GPKG,
]:
    if not path.exists():
        raise FileNotFoundError(path)

for path in [
    OUT_CANDIDATES,
    OUT_NAIVE,
    OUT_ANCHORED,
    OUT_SUMMARY,
    OUT_MANIFEST,
]:
    if path.exists():
        raise RuntimeError(
            f"Output già esistente: {path}"
        )

out(f"B2       : {B2}")
out(f"B3       : {B3}")
out(f"B5 TIME  : {TIME_NPZ}")
out(f"Base     : {BASE_GPKG}")

out(f"K test   : {K_VALUES}")
out(f"Sep test : {SEPARATIONS_M}")


# =============================================================================
# A. TERRITORIO
# =============================================================================

out()
out("A. COMUNI E CENTROIDI")
out("-" * 112)

comuni = gpd.read_file(
    BASE_GPKG,
    layer=COMUNI_LAYER,
).to_crs(32632)

centroidi = gpd.read_file(
    BASE_GPKG,
    layer=CENTROIDI_LAYER,
).to_crs(32632)

comune_code = detect_field(
    comuni.columns,
    [
        "PRO_COM",
        "PROCOM",
        "PRO_COM_T",
        "COD_PROCOM",
    ],
    "PRO_COM comuni",
)

centroid_code = detect_field(
    centroidi.columns,
    [
        "PRO_COM",
        "PROCOM",
        "PRO_COM_T",
        "COD_PROCOM",
    ],
    "PRO_COM centroidi",
)

name_field = None

for candidate in [
    "COMUNE",
    "DEN_COM",
    "COMUNE_NOME",
    "NAME",
    "DENOMINAZIONE",
]:
    if candidate.lower() in {
        str(c).lower()
        for c in comuni.columns
    }:
        name_field = detect_field(
            comuni.columns,
            [candidate],
            "nome comune",
        )
        break

comuni = comuni.copy()
centroidi = centroidi.copy()

comuni["PRO_COM_X"] = comuni[
    comune_code
].map(normalize_code)

centroidi["PRO_COM_X"] = centroidi[
    centroid_code
].map(normalize_code)

if len(comuni) != EXPECTED_MUNICIPALITIES:
    raise RuntimeError(
        f"Comuni={len(comuni)}, attesi 215"
    )

if len(centroidi) != EXPECTED_MUNICIPALITIES:
    raise RuntimeError(
        f"Centroidi={len(centroidi)}, attesi 215"
    )

if comuni["PRO_COM_X"].duplicated().any():
    raise RuntimeError(
        "PRO_COM duplicati nei comuni."
    )

if centroidi["PRO_COM_X"].duplicated().any():
    raise RuntimeError(
        "PRO_COM duplicati nei centroidi."
    )

centroid_map = {
    int(r.PRO_COM_X): r.geometry

    for r in centroidi[
        ["PRO_COM_X", "geometry"]
    ].itertuples()
}

out(f"Comuni    : {len(comuni)}")
out(f"Centroidi : {len(centroidi)}")


# =============================================================================
# B. B3 GIANT SCC
# =============================================================================

out()
out("B. DOMINIO B3 GIANT SCC")
out("-" * 112)

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
        n.lat

    FROM nodes AS n

    JOIN qa.node_components AS q
        ON q.node_id = n.node_id

    WHERE q.in_giant_scc = 1

    ORDER BY n.node_id
    """
).fetchall()

node_ids = np.fromiter(
    (int(r[0]) for r in rows),
    dtype=np.int64,
    count=len(rows),
)

xs = np.fromiter(
    (float(r[1]) for r in rows),
    dtype=np.float64,
    count=len(rows),
)

ys = np.fromiter(
    (float(r[2]) for r in rows),
    dtype=np.float64,
    count=len(rows),
)

lons = np.fromiter(
    (float(r[3]) for r in rows),
    dtype=np.float64,
    count=len(rows),
)

lats = np.fromiter(
    (float(r[4]) for r in rows),
    dtype=np.float64,
    count=len(rows),
)

out(
    f"Nodi giant SCC B3 : "
    f"{len(node_ids):,}"
)


# =============================================================================
# C. FILTRO TURN-AWARE B5
# =============================================================================

out()
out("C. DOMINIO MUTUAMENTE RAGGIUNGIBILE B5")
out("-" * 112)

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
    or
    int(base_nodes[anchor_state])
    != anchor_node
):
    raise RuntimeError(
        "Anchor B3 non presente nei base states B5."
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

forward_pos = np.searchsorted(
    forward_phys,
    node_ids,
)

destination_ok = (
    forward_pos
    < len(forward_phys)
)

safe_forward = np.minimum(
    forward_pos,
    len(forward_phys) - 1,
)

destination_ok &= (
    forward_phys[
        safe_forward
    ]
    == node_ids
)

base_pos = np.searchsorted(
    base_nodes,
    node_ids,
)

base_present = (
    base_pos
    < len(base_nodes)
)

safe_base = np.minimum(
    base_pos,
    len(base_nodes) - 1,
)

base_present &= (
    base_nodes[
        safe_base
    ]
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
    base_present
)

origin_ok[valid] = reverse_mask[
    base_pos[valid]
]

turn_ok = (
    destination_ok
    &
    origin_ok
)

out(
    f"B3 giant SCC      : "
    f"{len(node_ids):,}"
)

out(
    f"B5 mutual domain  : "
    f"{int(turn_ok.sum()):,}"
)

out(
    f"Esclusi da B5     : "
    f"{int((~turn_ok).sum()):,}"
)

if turn_ok.sum() < 0.95 * len(node_ids):
    raise RuntimeError(
        "Dominio mutual turn-aware <95% giant SCC."
    )

node_ids = node_ids[turn_ok]
xs = xs[turn_ok]
ys = ys[turn_ok]
lons = lons[turn_ok]
lats = lats[turn_ok]

del TIME
del reverse_mask


# =============================================================================
# D. TOP20 PER COMUNE
# =============================================================================

out()
out("D. TOP-20 CANDIDATI PER COMUNE")
out("-" * 112)

points = shapely.points(
    xs,
    ys,
)

tree = STRtree(
    points
)

candidate_rows = []
pool_sizes = []

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

    # Piccola tolleranza di bordo.
    search_geom = geom.buffer(
        2.0
    )

    idx = np.asarray(
        tree.query(
            search_geom,
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

    cx = float(
        centroid.x
    )

    cy = float(
        centroid.y
    )

    distances = np.hypot(
        xs[idx] - cx,
        ys[idx] - cy,
    )

    order = np.lexsort(
        (
            node_ids[idx],
            distances,
        )
    )

    idx = idx[
        order[:TOP_K]
    ]

    distances = distances[
        order[:TOP_K]
    ]

    for rank, (
        p,
        distance_m,
    ) in enumerate(
        zip(idx, distances),
        start=1,
    ):

        candidate_rows.append({
            "PRO_COM":
                pro_com,

            "COMUNE":
                comune_name,

            "source_rank":
                rank,

            "node_id":
                int(node_ids[p]),

            "x":
                float(xs[p]),

            "y":
                float(ys[p]),

            "lon":
                float(lons[p]),

            "lat":
                float(lats[p]),

            "distance_m":
                float(distance_m),
        })

cand_df = pd.DataFrame(
    candidate_rows
)

out(
    f"Candidate rows : "
    f"{len(cand_df):,}"
)

out(
    f"Pool interno min/med/max : "
    f"{min(pool_sizes):,} / "
    f"{np.median(pool_sizes):.1f} / "
    f"{max(pool_sizes):,}"
)

top20_counts = (
    cand_df.groupby(
        "PRO_COM"
    ).size()
)

out(
    f"Comuni con >=20 candidati : "
    f"{int((top20_counts >= 20).sum())}/215"
)


# =============================================================================
# E. INCIDENT WAY SETS
# =============================================================================

out()
out("E. WAY_ID INCIDENTI")
out("-" * 112)

candidate_nodes = sorted(
    {
        int(x)
        for x in cand_df["node_id"]
    }
)

con.execute(
    """
    CREATE TEMP TABLE gamma_nodes (
        node_id INTEGER PRIMARY KEY
    )
    """
)

con.executemany(
    """
    INSERT INTO gamma_nodes(node_id)
    VALUES (?)
    """,
    [
        (x,)
        for x in candidate_nodes
    ],
)

way_sets = defaultdict(set)

for nid, wid in con.execute(
    """
    SELECT
        g.node_id,
        s.way_id

    FROM gamma_nodes AS g

    JOIN segments AS s
        ON s.osm_u = g.node_id

    UNION

    SELECT
        g.node_id,
        s.way_id

    FROM gamma_nodes AS g

    JOIN segments AS s
        ON s.osm_v = g.node_id
    """
):

    way_sets[
        int(nid)
    ].add(
        int(wid)
    )

missing_wayset = [
    nid
    for nid in candidate_nodes
    if not way_sets[nid]
]

out(
    f"Candidate nodes distinti : "
    f"{len(candidate_nodes):,}"
)

out(
    f"Node senza way incidente : "
    f"{len(missing_wayset):,}"
)

if missing_wayset:
    raise RuntimeError(
        "Candidate senza way_id incidente."
    )

cand_df[
    "incident_way_ids"
] = cand_df[
    "node_id"
].map(
    lambda nid:
        json.dumps(
            sorted(
                way_sets[
                    int(nid)
                ]
            ),
            separators=(",", ":"),
        )
)

cand_df.to_csv(
    OUT_CANDIDATES,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# F. NEAREST-K INGENUO
# =============================================================================

out()
out("F. SENSITIVITY NEAREST-K INGENUO")
out("-" * 112)

naive_rows = []

for pro_com, group in cand_df.groupby(
    "PRO_COM",
    sort=True,
):

    records = (
        group
        .sort_values(
            [
                "source_rank",
                "node_id",
            ]
        )
        .to_dict(
            "records"
        )
    )

    for k in K_VALUES:

        if len(records) < k:

            naive_rows.append({
                "PRO_COM":
                    int(pro_com),

                "COMUNE":
                    records[0]["COMUNE"]
                    if records
                    else None,

                "K":
                    k,

                "feasible":
                    0,
            })

            continue

        chosen = records[:k]

        pair = pairwise_metrics(
            chosen,
            way_sets,
        )

        distances = [
            float(x["distance_m"])
            for x in chosen
        ]

        naive_rows.append({
            "PRO_COM":
                int(pro_com),

            "COMUNE":
                chosen[0]["COMUNE"],

            "K":
                k,

            "feasible":
                1,

            "primary_distance_m":
                distances[0],

            "max_distance_m":
                max(distances),

            "sum_distance_m":
                sum(distances),

            "extra_max_distance_m":
                max(distances)
                - distances[0],

            "min_pair_sep_m":
                pair[
                    "min_sep_m"
                ],

            "shared_way_pairs":
                pair[
                    "shared_way_pairs"
                ],

            "has_shared_way":
                int(
                    pair[
                        "shared_way_pairs"
                    ] > 0
                ),

            "max_source_rank":
                k,
        })

naive_df = pd.DataFrame(
    naive_rows
)

naive_df.to_csv(
    OUT_NAIVE,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# G. ANCHORED / DIVERSE SENSITIVITY
# =============================================================================

out()
out("G. SENSITIVITY ANCHORED + DIVERSITÀ")
out("-" * 112)

anchored_rows = []

total_scenarios = (
    len(K_VALUES)
    * len(SEPARATIONS_M)
)

scenario_counter = 0

for k in K_VALUES:

    for sep_m in SEPARATIONS_M:

        scenario_counter += 1

        out(
            f"Scenario "
            f"{scenario_counter:>2}/{total_scenarios}: "
            f"K={k}, sep={sep_m:.0f} m"
        )

        feasible_count = 0

        for pro_com, group in cand_df.groupby(
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
                .to_dict(
                    "records"
                )
            )

            chosen = best_anchored_selection(
                records,
                k,
                sep_m,
                way_sets,
            )

            if chosen is None:

                anchored_rows.append({
                    "PRO_COM":
                        int(pro_com),

                    "COMUNE":
                        records[0]["COMUNE"]
                        if records
                        else None,

                    "K":
                        k,

                    "min_sep_rule_m":
                        sep_m,

                    "feasible":
                        0,

                    "candidate_count":
                        len(records),
                })

                continue

            feasible_count += 1

            pair = pairwise_metrics(
                chosen,
                way_sets,
            )

            distances = [
                float(x["distance_m"])
                for x in chosen
            ]

            ranks = [
                int(x["source_rank"])
                for x in chosen
            ]

            anchored_rows.append({
                "PRO_COM":
                    int(pro_com),

                "COMUNE":
                    chosen[0]["COMUNE"],

                "K":
                    k,

                "min_sep_rule_m":
                    sep_m,

                "feasible":
                    1,

                "candidate_count":
                    len(records),

                "primary_node_id":
                    int(
                        chosen[0]["node_id"]
                    ),

                "primary_distance_m":
                    distances[0],

                "max_distance_m":
                    max(distances),

                "sum_distance_m":
                    sum(distances),

                "extra_max_distance_m":
                    max(distances)
                    - distances[0],

                "min_pair_sep_m":
                    pair[
                        "min_sep_m"
                    ],

                "shared_way_pairs":
                    pair[
                        "shared_way_pairs"
                    ],

                "max_source_rank":
                    max(ranks),

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
                        ranks,
                        separators=(",", ":"),
                    ),
            })

        out(
            f"  feasible: "
            f"{feasible_count}/215"
        )


anchored_df = pd.DataFrame(
    anchored_rows
)

anchored_df.to_csv(
    OUT_ANCHORED,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# H. SUMMARY
# =============================================================================

out()
out("H. SUMMARY")
out("-" * 112)

summary_rows = []


# ---------------------------------------------------------------------
# NEAREST-K
# ---------------------------------------------------------------------

for k in K_VALUES:

    sub = naive_df[
        naive_df["K"] == k
    ]

    ok = sub[
        sub["feasible"] == 1
    ]

    summary_rows.append({
        "mode":
            "NEAREST_K",

        "K":
            k,

        "min_sep_rule_m":
            np.nan,

        "municipalities_feasible":
            int(
                sub["feasible"].sum()
            ),

        "municipalities_with_shared_way":
            int(
                ok[
                    "has_shared_way"
                ].sum()
            )
            if k > 1
            else 0,

        "median_max_distance_m":
            float(
                ok[
                    "max_distance_m"
                ].median()
            ),

        "p95_max_distance_m":
            percentile(
                ok[
                    "max_distance_m"
                ],
                95,
            ),

        "max_max_distance_m":
            float(
                ok[
                    "max_distance_m"
                ].max()
            ),

        "median_extra_max_distance_m":
            float(
                ok[
                    "extra_max_distance_m"
                ].median()
            ),

        "p95_extra_max_distance_m":
            percentile(
                ok[
                    "extra_max_distance_m"
                ],
                95,
            ),

        "median_min_pair_sep_m":
            (
                float(
                    ok[
                        "min_pair_sep_m"
                    ].median()
                )
                if k > 1
                else np.nan
            ),

        "min_min_pair_sep_m":
            (
                float(
                    ok[
                        "min_pair_sep_m"
                    ].min()
                )
                if k > 1
                else np.nan
            ),

        "median_max_source_rank":
            float(
                ok[
                    "max_source_rank"
                ].median()
            ),

        "max_source_rank":
            int(
                ok[
                    "max_source_rank"
                ].max()
            ),
    })


# ---------------------------------------------------------------------
# ANCHORED
# ---------------------------------------------------------------------

for k in K_VALUES:

    for sep_m in SEPARATIONS_M:

        sub = anchored_df[
            (anchored_df["K"] == k)
            &
            (
                anchored_df[
                    "min_sep_rule_m"
                ]
                == sep_m
            )
        ]

        ok = sub[
            sub["feasible"] == 1
        ]

        summary_rows.append({
            "mode":
                "ANCHORED_DIVERSE",

            "K":
                k,

            "min_sep_rule_m":
                sep_m,

            "municipalities_feasible":
                int(
                    sub[
                        "feasible"
                    ].sum()
                ),

            "municipalities_with_shared_way":
                int(
                    (
                        ok[
                            "shared_way_pairs"
                        ]
                        > 0
                    ).sum()
                )
                if k > 1
                else 0,

            "median_max_distance_m":
                (
                    float(
                        ok[
                            "max_distance_m"
                        ].median()
                    )
                    if len(ok)
                    else np.nan
                ),

            "p95_max_distance_m":
                percentile(
                    ok[
                        "max_distance_m"
                    ],
                    95,
                )
                if len(ok)
                else np.nan,

            "max_max_distance_m":
                (
                    float(
                        ok[
                            "max_distance_m"
                        ].max()
                    )
                    if len(ok)
                    else np.nan
                ),

            "median_extra_max_distance_m":
                (
                    float(
                        ok[
                            "extra_max_distance_m"
                        ].median()
                    )
                    if len(ok)
                    else np.nan
                ),

            "p95_extra_max_distance_m":
                percentile(
                    ok[
                        "extra_max_distance_m"
                    ],
                    95,
                )
                if len(ok)
                else np.nan,

            "median_min_pair_sep_m":
                (
                    float(
                        ok[
                            "min_pair_sep_m"
                        ].median()
                    )
                    if (
                        len(ok)
                        and k > 1
                    )
                    else np.nan
                ),

            "min_min_pair_sep_m":
                (
                    float(
                        ok[
                            "min_pair_sep_m"
                        ].min()
                    )
                    if (
                        len(ok)
                        and k > 1
                    )
                    else np.nan
                ),

            "median_max_source_rank":
                (
                    float(
                        ok[
                            "max_source_rank"
                        ].median()
                    )
                    if len(ok)
                    else np.nan
                ),

            "max_source_rank":
                (
                    int(
                        ok[
                            "max_source_rank"
                        ].max()
                    )
                    if len(ok)
                    else np.nan
                ),
        })


summary_df = pd.DataFrame(
    summary_rows
)

summary_df.to_csv(
    OUT_SUMMARY,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# I. CONSOLE SUMMARY
# =============================================================================

out()
out("I. RISULTATI NEAREST-K")
out("-" * 112)

nearest_summary = summary_df[
    summary_df[
        "mode"
    ] == "NEAREST_K"
]

for r in nearest_summary.itertuples():

    out(
        f"K={r.K} | "
        f"feasible={int(r.municipalities_feasible):3}/215 | "
        f"shared-way comuni="
        f"{int(r.municipalities_with_shared_way):3} | "
        f"extra-med="
        f"{r.median_extra_max_distance_m:7.1f} m | "
        f"extra-p95="
        f"{r.p95_extra_max_distance_m:7.1f} m | "
        f"min-sep="
        f"{r.min_min_pair_sep_m}"
    )


out()
out("J. RISULTATI ANCHORED-DIVERSE")
out("-" * 112)

anchored_summary = summary_df[
    summary_df[
        "mode"
    ] == "ANCHORED_DIVERSE"
]

for r in anchored_summary.itertuples():

    out(
        f"K={r.K} | "
        f"sep={r.min_sep_rule_m:5.0f} m | "
        f"feasible="
        f"{int(r.municipalities_feasible):3}/215 | "
        f"extra-med="
        f"{r.median_extra_max_distance_m:7.1f} m | "
        f"extra-p95="
        f"{r.p95_extra_max_distance_m:7.1f} m | "
        f"rank-max="
        f"{r.max_source_rank}"
    )


# =============================================================================
# K. MANIFEST
# =============================================================================

manifest = {
    "phase":
        "FASE_5_6_E0",

    "version":
        "v01",

    "created_at":
        STAMP,

    "purpose":
        "Transfer validation della cardinalità e diversità di Gamma sul backbone OSM",

    "K_values":
        K_VALUES,

    "separation_values_m":
        SEPARATIONS_M,

    "candidate_top_k":
        TOP_K,

    "primary_rule":
        "nearest eligible node to population centroid",

    "eligibility":
        "own municipality + B3 giant SCC + B5 turn-aware mutual-via-anchor",

    "topological_diversity":
        "no shared incident OSM way_id",

    "anchored_objective": [
        "minimize maximum centroid distance",
        "minimize total centroid distance",
        "maximize minimum pair separation",
        "deterministic node-id tie break",
    ],

    "outputs": {
        "candidates":
            str(OUT_CANDIDATES),

        "nearest_k":
            str(OUT_NAIVE),

        "anchored":
            str(OUT_ANCHORED),

        "summary":
            str(OUT_SUMMARY),
    },
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
# L. FINAL
# =============================================================================

out()
out("=" * 112)
out("ESITO E0: SENSITIVITY_READY")
out("=" * 112)

out(f"Summary  : {OUT_SUMMARY}")
out(f"Manifest : {OUT_MANIFEST}")
out(f"LOG      : {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

con.close()
