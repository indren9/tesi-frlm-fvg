from pathlib import Path
from datetime import datetime
from collections import defaultdict
from itertools import combinations
import hashlib
import json
import math
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

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

E0_CANDIDATES = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"gamma_sensitivity\Gamma_OSM_topological_top50_E0_v03.csv"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "gamma_osm"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUT_GPKG = (
    OUTDIR
    / "Gamma_OSM_L_comuni_fvg_v01_CANDIDATE.gpkg"
)

OUT_CSV = (
    OUTDIR
    / "Gamma_OSM_L_comuni_fvg_v01_CANDIDATE.csv"
)

OUT_DIAG = (
    OUTDIR
    / "Gamma_OSM_L_diagnostics_v01.csv"
)

OUT_MANIFEST = (
    OUTDIR
    / "Gamma_OSM_L_manifest_v01.json"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

LOG = (
    OUTDIR
    / f"materialize_gamma_osm_v01_{STAMP}.txt"
)

K = 3
MIN_SEP_M = 100.0

# Non è un parametro metodologico:
# è solo il bound empirico validato da E0_v03.
VALIDATED_MAX_RANK = 30

TAU_M = 300.0

EXPECTED_COMUNI = 215
EXPECTED_RECORDS = 645
EXPECTED_TOPO_SEGMENTS = 167_033


# =============================================================================
# LOG
# =============================================================================

lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def file_sha256(path):

    h = hashlib.sha256()

    with open(path, "rb") as f:

        while True:

            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


# =============================================================================
# SELECTION HELPERS
# =============================================================================

def evaluate_triple(
    chosen,
    topo_sets,
):
    """
    Valida una tripletta e restituisce:
      separazioni pairwise,
      indipendenza topologica,
      metriche della funzione obiettivo.
    """

    if len(chosen) != 3:
        raise RuntimeError(
            "evaluate_triple richiede esattamente 3 record."
        )

    a1, a2, a3 = chosen

    sep_12 = math.hypot(
        float(a1["x"]) - float(a2["x"]),
        float(a1["y"]) - float(a2["y"]),
    )

    sep_13 = math.hypot(
        float(a1["x"]) - float(a3["x"]),
        float(a1["y"]) - float(a3["y"]),
    )

    sep_23 = math.hypot(
        float(a2["x"]) - float(a3["x"]),
        float(a2["y"]) - float(a3["y"]),
    )

    separations = [
        sep_12,
        sep_13,
        sep_23,
    ]

    shared_12 = bool(
        topo_sets[int(a1["node_id"])]
        &
        topo_sets[int(a2["node_id"])]
    )

    shared_13 = bool(
        topo_sets[int(a1["node_id"])]
        &
        topo_sets[int(a3["node_id"])]
    )

    shared_23 = bool(
        topo_sets[int(a2["node_id"])]
        &
        topo_sets[int(a3["node_id"])]
    )

    shared_count = sum(
        [
            shared_12,
            shared_13,
            shared_23,
        ]
    )

    distances = [
        float(x["distance_m"])
        for x in chosen
    ]

    return {
        "sep_12_m":
            float(sep_12),

        "sep_13_m":
            float(sep_13),

        "sep_23_m":
            float(sep_23),

        "min_pair_separation_m":
            float(min(separations)),

        "shared_toposeg_12":
            int(shared_12),

        "shared_toposeg_13":
            int(shared_13),

        "shared_toposeg_23":
            int(shared_23),

        "shared_toposeg_pairs":
            int(shared_count),

        "objective_max_distance_m":
            float(max(distances)),

        "objective_sum_distance_m":
            float(sum(distances)),

        "objective_min_separation_m":
            float(min(separations)),
    }


def best_triple_at_depth(
    records,
    depth,
    topo_sets,
):
    """
    Primary fisso = rank 1.

    Cerca la migliore coppia di secondari fra i primi `depth`
    candidati secondo l'ordine lessicografico congelato:

      1. min max distanza
      2. min somma distanze
      3. max separazione minima
      4. tie-break node_id
    """

    local = records[:depth]

    if len(local) < 3:
        return None

    primary = local[0]

    best = None
    best_obj = None

    for i, j in combinations(
        range(1, len(local)),
        2,
    ):

        chosen = [
            primary,
            local[i],
            local[j],
        ]

        metrics = evaluate_triple(
            chosen,
            topo_sets,
        )

        if (
            metrics["min_pair_separation_m"]
            < MIN_SEP_M - 1e-9
        ):
            continue

        if (
            metrics["shared_toposeg_pairs"]
            != 0
        ):
            continue

        node_tuple = tuple(
            int(x["node_id"])
            for x in chosen
        )

        objective = (
            metrics[
                "objective_max_distance_m"
            ],
            metrics[
                "objective_sum_distance_m"
            ],
            -metrics[
                "objective_min_separation_m"
            ],
            node_tuple,
        )

        if (
            best_obj is None
            or objective < best_obj
        ):

            best_obj = objective

            best = {
                "chosen":
                    chosen,

                "metrics":
                    metrics,

                "objective":
                    objective,
            }

    return best


def adaptive_select(
    records,
    topo_sets,
):
    """
    Candidate search ADATTIVA.

    Ordina per source_rank e aumenta la profondità finché compare
    la prima soluzione ammissibile. Alla prima profondità feasible
    seleziona la soluzione lessicograficamente ottima.

    VALIDATED_MAX_RANK=30 è solo il limite empiricamente già
    validato da E0_v03, non un parametro del modello.
    """

    records = sorted(
        records,
        key=lambda r: (
            int(r["source_rank"]),
            float(r["distance_m"]),
            int(r["node_id"]),
        ),
    )

    if not records:
        return None

    if int(records[0]["source_rank"]) != 1:
        raise RuntimeError(
            "Il candidate pool non parte dal rank 1."
        )

    upper = min(
        VALIDATED_MAX_RANK,
        len(records),
    )

    for depth in range(
        3,
        upper + 1,
    ):

        result = best_triple_at_depth(
            records,
            depth,
            topo_sets,
        )

        if result is not None:

            result[
                "required_depth"
            ] = depth

            return result

    return None


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 122)
out("FASE 5.6 — E1 — MATERIALIZZAZIONE Gamma_OSM v01")
out("=" * 122)

for path in [
    B2,
    B3,
    TIME_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
    E0_CANDIDATES,
]:

    if not path.exists():
        raise FileNotFoundError(path)

for path in [
    OUT_GPKG,
    OUT_CSV,
    OUT_DIAG,
    OUT_MANIFEST,
]:

    if path.exists():

        raise RuntimeError(
            f"Output già esistente: {path}\n"
            "Non sovrascrivo output versionati."
        )

out(f"B2                 : {B2}")
out(f"B3                 : {B3}")
out(f"B5 TIME            : {TIME_NPZ}")
out(f"E0 candidates      : {E0_CANDIDATES}")
out(f"K                  : {K}")
out(f"Min separation     : {MIN_SEP_M:.0f} m")
out(f"Candidate search   : ADAPTIVE")
out(f"Validated max rank : {VALIDATED_MAX_RANK}")
out(f"Weight candidate   : EXP_REL_{int(TAU_M)}")


# =============================================================================
# A. CANDIDATES
# =============================================================================

out()
out("A. CANDIDATI E0_v03")
out("-" * 122)

cand = pd.read_csv(
    E0_CANDIDATES
)

required_fields = [
    "PRO_COM",
    "COMUNE",
    "source_rank",
    "node_id",
    "x",
    "y",
    "lon",
    "lat",
    "distance_m",
]

missing = [
    field
    for field in required_fields
    if field not in cand.columns
]

if missing:

    raise RuntimeError(
        f"Campi mancanti: {missing}"
    )

cand["PRO_COM"] = (
    cand["PRO_COM"]
    .astype(np.int64)
)

cand["node_id"] = (
    cand["node_id"]
    .astype(np.int64)
)

cand["source_rank"] = (
    cand["source_rank"]
    .astype(int)
)

candidate_counts = (
    cand.groupby("PRO_COM")
    .size()
)

out(f"Candidate rows   : {len(cand):,}")
out(
    f"Comuni           : "
    f"{cand['PRO_COM'].nunique():,}"
)
out(
    f"Candidate/comune : "
    f"min={int(candidate_counts.min())} | "
    f"max={int(candidate_counts.max())}"
)

if (
    cand["PRO_COM"].nunique()
    != EXPECTED_COMUNI
):

    raise RuntimeError(
        "I candidati non coprono 215 comuni."
    )

if (
    candidate_counts.min()
    < VALIDATED_MAX_RANK
):

    raise RuntimeError(
        "Almeno un comune non contiene "
        "il pool validato fino al rank 30."
    )


# Rank 1 esattamente uno per comune.
rank1_counts = (
    cand[
        cand["source_rank"] == 1
    ]
    .groupby("PRO_COM")
    .size()
)

if (
    len(rank1_counts) != EXPECTED_COMUNI
    or
    not (rank1_counts == 1).all()
):

    raise RuntimeError(
        "Rank 1 non univoco per tutti i comuni."
    )


candidate_nodes = set(
    int(x)
    for x in cand["node_id"]
)


# =============================================================================
# B. REBUILD B3 + B5 MUTUAL DOMAIN
# =============================================================================

out()
out("B. REBUILD DOMINIO ROUTING")
out("-" * 122)

b2 = sqlite3.connect(B2)
b3 = sqlite3.connect(B3)

rows = b3.execute(
    """
    SELECT
        node_id,
        undirected_degree

    FROM node_components

    WHERE in_giant_scc = 1

    ORDER BY node_id
    """
).fetchall()

giant_nodes = np.asarray(
    [
        int(r[0])
        for r in rows
    ],
    dtype=np.int64,
)

degrees = np.asarray(
    [
        int(r[1])
        for r in rows
    ],
    dtype=np.int32,
)

out(
    f"B3 giant SCC : "
    f"{len(giant_nodes):,}"
)


TIME = load_npz(
    TIME_NPZ
).tocsr()

base_nodes = np.load(
    BASE_NODES_NPY
)

state_node = np.load(
    STATE_NODE_NPY
)

if TIME.shape[0] != len(state_node):

    raise RuntimeError(
        "Mismatch TIME / state_node."
    )

anchor_node = int(
    giant_nodes[0]
)

anchor_state = int(
    np.searchsorted(
        base_nodes,
        anchor_node,
    )
)

if (
    anchor_state >= len(base_nodes)
    or int(
        base_nodes[anchor_state]
    ) != anchor_node
):

    raise RuntimeError(
        "Anchor B5 non trovato."
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
    giant_nodes,
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
    == giant_nodes
)


bp = np.searchsorted(
    base_nodes,
    giant_nodes,
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
    == giant_nodes
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
    len(giant_nodes),
    dtype=bool,
)

valid_pos = np.flatnonzero(
    base_ok
)

origin_ok[
    valid_pos
] = reverse_mask[
    bp[valid_pos]
]


mutual = (
    destination_ok
    &
    origin_ok
)

out(
    f"B5 mutual    : "
    f"{int(mutual.sum()):,}"
)

out(
    f"B5 excluded  : "
    f"{int((~mutual).sum()):,}"
)


giant_nodes = giant_nodes[
    mutual
]

degrees = degrees[
    mutual
]

del TIME
del reverse_mask


# =============================================================================
# C. STRUCTURAL NODE RULE
# =============================================================================

out()
out("C. STRUCTURAL NODE RULE")
out("-" * 122)

way_count = {}

for nid, nways in b2.execute(
    """
    SELECT
        node_id,
        COUNT(DISTINCT way_id)

    FROM (
        SELECT
            osm_u AS node_id,
            way_id
        FROM segments

        UNION ALL

        SELECT
            osm_v AS node_id,
            way_id
        FROM segments
    )

    GROUP BY node_id
    """
):

    way_count[
        int(nid)
    ] = int(nways)


incident_way_count = np.asarray(
    [
        way_count.get(
            int(nid),
            0,
        )
        for nid in giant_nodes
    ],
    dtype=np.int16,
)


structural_mask = (
    (degrees != 2)
    |
    (incident_way_count >= 2)
)

structural_nodes = (
    giant_nodes[
        structural_mask
    ]
)

structural_set = set(
    int(x)
    for x in structural_nodes
)

out(
    f"Structural nodes : "
    f"{len(structural_set):,}"
)

if len(structural_set) != 131_871:

    raise RuntimeError(
        "Regression structural nodes: "
        f"{len(structural_set):,} != 131,871"
    )


candidate_non_structural = (
    candidate_nodes
    -
    structural_set
)

out(
    f"Candidate non structural : "
    f"{len(candidate_non_structural):,}"
)

if candidate_non_structural:

    raise RuntimeError(
        "Candidate E0 non structural."
    )


# =============================================================================
# D. CORRECT TOPOLOGICAL SEGMENT INCIDENCE
# =============================================================================

out()
out("D. TOPOLOGICAL SEGMENT INCIDENCE")
out("-" * 122)

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

    if int(start_node) in candidate_nodes:

        topo_sets[
            int(start_node)
        ].add(uid)

    if int(end_node) in candidate_nodes:

        topo_sets[
            int(end_node)
        ].add(uid)


for wid, seq, u, v in b2.execute(
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


out(
    f"Topological segments : "
    f"{topo_segment_count:,}"
)

if (
    topo_segment_count
    != EXPECTED_TOPO_SEGMENTS
):

    raise RuntimeError(
        "Regression topological skeleton: "
        f"{topo_segment_count:,} != "
        f"{EXPECTED_TOPO_SEGMENTS:,}"
    )


missing_topo = [
    nid
    for nid in candidate_nodes
    if not topo_sets[nid]
]

out(
    f"Candidate senza topo incidence : "
    f"{len(missing_topo):,}"
)

if missing_topo:

    raise RuntimeError(
        "Candidate senza topological incidence."
    )


# =============================================================================
# E. ADAPTIVE SELECTION
# =============================================================================

out()
out("E. ADAPTIVE ANCHORED SELECTION")
out("-" * 122)

selection_rows = []
diagnostic_rows = []

failures = []
determinism_failures = []


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


    # -------------------------------------------------------------
    # Prima esecuzione
    # -------------------------------------------------------------

    result_1 = adaptive_select(
        records,
        topo_sets,
    )


    # -------------------------------------------------------------
    # Seconda esecuzione indipendente:
    # controllo determinismo.
    # -------------------------------------------------------------

    result_2 = adaptive_select(
        list(records),
        topo_sets,
    )


    if result_1 is None:

        failures.append(
            (
                int(pro_com),
                (
                    str(records[0]["COMUNE"])
                    if records
                    else None
                ),
            )
        )

        continue


    sig_1 = (
        int(
            result_1[
                "required_depth"
            ]
        ),
        tuple(
            int(x["node_id"])
            for x in result_1["chosen"]
        ),
        tuple(
            float(x)
            for x in result_1["objective"][:3]
        ),
    )

    sig_2 = (
        int(
            result_2[
                "required_depth"
            ]
        ),
        tuple(
            int(x["node_id"])
            for x in result_2["chosen"]
        ),
        tuple(
            float(x)
            for x in result_2["objective"][:3]
        ),
    )


    if sig_1 != sig_2:

        determinism_failures.append(
            (
                int(pro_com),
                sig_1,
                sig_2,
            )
        )


    chosen = result_1[
        "chosen"
    ]

    metrics = result_1[
        "metrics"
    ]

    required_depth = int(
        result_1[
            "required_depth"
        ]
    )


    # Ordine accessi:
    # primary = rank1;
    # secondari ordinati deterministicamente per source rank/node id.
    primary = chosen[0]

    secondaries = sorted(
        chosen[1:],
        key=lambda x: (
            int(x["source_rank"]),
            int(x["node_id"]),
        ),
    )

    chosen = [
        primary,
        *secondaries,
    ]


    # Ricalcolo metriche nell'ordine access_order 1/2/3.
    metrics = evaluate_triple(
        chosen,
        topo_sets,
    )


    primary_distance = float(
        chosen[0]["distance_m"]
    )


    # -------------------------------------------------------------
    # EXP_REL_300 candidate weights
    # -------------------------------------------------------------

    raw_weights = np.asarray(
        [
            math.exp(
                -(
                    float(r["distance_m"])
                    - primary_distance
                )
                / TAU_M
            )
            for r in chosen
        ],
        dtype=float,
    )

    lambdas = (
        raw_weights
        /
        raw_weights.sum()
    )


    effective_n = float(
        1.0
        /
        np.sum(
            lambdas ** 2
        )
    )


    # -------------------------------------------------------------
    # Base-state IDs per E2
    # -------------------------------------------------------------

    base_state_ids = []

    for r in chosen:

        nid = int(
            r["node_id"]
        )

        pos = int(
            np.searchsorted(
                base_nodes,
                nid,
            )
        )

        if (
            pos >= len(base_nodes)
            or int(
                base_nodes[pos]
            ) != nid
        ):

            raise RuntimeError(
                f"Accesso {nid} non presente "
                "come base-state B5."
            )

        base_state_ids.append(
            pos
        )


    # -------------------------------------------------------------
    # Diagnostic row
    # -------------------------------------------------------------

    diagnostic_rows.append({
        "PRO_COM":
            int(pro_com),

        "COMUNE":
            str(chosen[0]["COMUNE"]),

        "required_depth":
            required_depth,

        "selected_rank_1":
            int(
                chosen[0]["source_rank"]
            ),

        "selected_rank_2":
            int(
                chosen[1]["source_rank"]
            ),

        "selected_rank_3":
            int(
                chosen[2]["source_rank"]
            ),

        "structural_node_id_1":
            int(
                chosen[0]["node_id"]
            ),

        "structural_node_id_2":
            int(
                chosen[1]["node_id"]
            ),

        "structural_node_id_3":
            int(
                chosen[2]["node_id"]
            ),

        "base_state_id_1":
            int(
                base_state_ids[0]
            ),

        "base_state_id_2":
            int(
                base_state_ids[1]
            ),

        "base_state_id_3":
            int(
                base_state_ids[2]
            ),

        "primary_distance_m":
            primary_distance,

        "farthest_distance_m":
            metrics[
                "objective_max_distance_m"
            ],

        "extra_farthest_m":
            (
                metrics[
                    "objective_max_distance_m"
                ]
                - primary_distance
            ),

        "sep_12_m":
            metrics["sep_12_m"],

        "sep_13_m":
            metrics["sep_13_m"],

        "sep_23_m":
            metrics["sep_23_m"],

        "min_pair_separation_m":
            metrics[
                "min_pair_separation_m"
            ],

        "shared_toposeg_12":
            metrics[
                "shared_toposeg_12"
            ],

        "shared_toposeg_13":
            metrics[
                "shared_toposeg_13"
            ],

        "shared_toposeg_23":
            metrics[
                "shared_toposeg_23"
            ],

        "shared_toposeg_pairs":
            metrics[
                "shared_toposeg_pairs"
            ],

        "lex_obj_1_max_distance_m":
            metrics[
                "objective_max_distance_m"
            ],

        "lex_obj_2_sum_distance_m":
            metrics[
                "objective_sum_distance_m"
            ],

        "lex_obj_3_min_separation_m":
            metrics[
                "objective_min_separation_m"
            ],

        "effective_access_count":
            effective_n,

        "selection_deterministic":
            int(
                sig_1 == sig_2
            ),

        "selection_status":
            "CANDIDATE_PENDING_E2",
    })


    # -------------------------------------------------------------
    # Access rows
    # -------------------------------------------------------------

    for access_order, (
        r,
        lam,
        base_state_id,
    ) in enumerate(
        zip(
            chosen,
            lambdas,
            base_state_ids,
        ),
        start=1,
    ):

        nid = int(
            r["node_id"]
        )

        selection_rows.append({
            "PRO_COM":
                int(pro_com),

            "COMUNE":
                str(r["COMUNE"]),

            "access_order":
                access_order,

            "access_role":
                (
                    "PRIMARY"
                    if access_order == 1
                    else "SECONDARY"
                ),

            "structural_node_id":
                nid,

            "base_state_id":
                int(
                    base_state_id
                ),

            "candidate_rank":
                int(
                    r["source_rank"]
                ),

            "required_depth":
                required_depth,

            "x":
                float(r["x"]),

            "y":
                float(r["y"]),

            "lon":
                float(r["lon"]),

            "lat":
                float(r["lat"]),

            "distance_centroid_m":
                float(
                    r["distance_m"]
                ),

            "delta_distance_primary_m":
                (
                    float(
                        r["distance_m"]
                    )
                    - primary_distance
                ),

            "sep_12_m":
                metrics["sep_12_m"],

            "sep_13_m":
                metrics["sep_13_m"],

            "sep_23_m":
                metrics["sep_23_m"],

            "min_pair_separation_m":
                metrics[
                    "min_pair_separation_m"
                ],

            "lex_obj_1_max_distance_m":
                metrics[
                    "objective_max_distance_m"
                ],

            "lex_obj_2_sum_distance_m":
                metrics[
                    "objective_sum_distance_m"
                ],

            "lex_obj_3_min_separation_m":
                metrics[
                    "objective_min_separation_m"
                ],

            "lambda_L":
                float(lam),

            "weight_rule":
                "EXP_REL_300",

            "tau_m":
                TAU_M,

            "incident_topo_count":
                len(
                    topo_sets[nid]
                ),

            "incident_topo_ids_json":
                json.dumps(
                    sorted(
                        topo_sets[nid]
                    ),
                    separators=(",", ":"),
                ),

            "b3_giant_scc":
                1,

            "b5_turn_aware_mutual":
                1,

            "structural_node":
                1,

            "selection_deterministic":
                int(
                    sig_1 == sig_2
                ),

            "selection_status":
                "CANDIDATE_PENDING_E2",
        })


sel = pd.DataFrame(
    selection_rows
)

diag = pd.DataFrame(
    diagnostic_rows
)


out(
    f"Comuni selezionati : "
    f"{sel['PRO_COM'].nunique():,}"
)

out(
    f"Record selezionati : "
    f"{len(sel):,}"
)

out(
    f"Selection failures : "
    f"{len(failures):,}"
)

out(
    f"Determinism fail   : "
    f"{len(determinism_failures):,}"
)


for failure in failures:
    out(
        f"  SELECTION FAIL: {failure}"
    )

for failure in determinism_failures[:20]:
    out(
        f"  DETERMINISM FAIL: {failure}"
    )


# =============================================================================
# F. HARD QA
# =============================================================================

out()
out("F. HARD QA E1")
out("-" * 122)

counts = (
    sel.groupby(
        "PRO_COM"
    ).size()
)

bad_cardinality = int(
    (counts != 3).sum()
)

duplicate_nodes = int(
    sel.duplicated(
        subset=[
            "PRO_COM",
            "structural_node_id",
        ]
    ).sum()
)

duplicate_access_order = int(
    sel.duplicated(
        subset=[
            "PRO_COM",
            "access_order",
        ]
    ).sum()
)

primary_bad = int(
    (
        sel[
            sel["access_order"] == 1
        ][
            "candidate_rank"
        ]
        != 1
    ).sum()
)

pair_sep_bad = int(
    (
        diag[
            "min_pair_separation_m"
        ]
        < MIN_SEP_M - 1e-9
    ).sum()
)

topo_bad = int(
    (
        diag[
            "shared_toposeg_pairs"
        ]
        != 0
    ).sum()
)

depth_bad = int(
    (
        diag[
            "required_depth"
        ]
        > VALIDATED_MAX_RANK
    ).sum()
)

determinism_bad = int(
    (
        diag[
            "selection_deterministic"
        ]
        != 1
    ).sum()
)

base_state_duplicates = int(
    sel.duplicated(
        subset=[
            "PRO_COM",
            "base_state_id",
        ]
    ).sum()
)

lambda_sums = (
    sel.groupby(
        "PRO_COM"
    )[
        "lambda_L"
    ].sum()
)

max_lambda_error = float(
    np.max(
        np.abs(
            lambda_sums.to_numpy()
            - 1.0
        )
    )
)

nonpositive_lambda = int(
    (
        sel["lambda_L"]
        <= 0
    ).sum()
)


out(
    f"Comuni != 3 accessi            : "
    f"{bad_cardinality:,}"
)

out(
    f"Duplicate structural node      : "
    f"{duplicate_nodes:,}"
)

out(
    f"Duplicate access_order         : "
    f"{duplicate_access_order:,}"
)

out(
    f"Duplicate base-state/comune    : "
    f"{base_state_duplicates:,}"
)

out(
    f"Primary non nearest rank-1     : "
    f"{primary_bad:,}"
)

out(
    f"Pair separation violations     : "
    f"{pair_sep_bad:,}"
)

out(
    f"Topological independence fail  : "
    f"{topo_bad:,}"
)

out(
    f"Required depth >29             : "
    f"{depth_bad:,}"
)

out(
    f"Determinism failures           : "
    f"{determinism_bad:,}"
)

out(
    f"Nonpositive lambda             : "
    f"{nonpositive_lambda:,}"
)

out(
    f"Max lambda sum error           : "
    f"{max_lambda_error:.3e}"
)


# =============================================================================
# G. DISTRIBUTIVE QA
# =============================================================================

out()
out("G. DISTRIBUTIVE QA")
out("-" * 122)


def report_dist(
    label,
    values,
):

    a = np.asarray(
        values,
        dtype=float,
    )

    out(
        f"{label:<34} "
        f"min={np.min(a):9.2f} | "
        f"med={np.median(a):9.2f} | "
        f"p95={np.percentile(a,95):9.2f} | "
        f"max={np.max(a):9.2f}"
    )


primary_dist = (
    sel[
        sel["access_order"] == 1
    ][
        "distance_centroid_m"
    ].to_numpy(dtype=float)
)

extra_farthest = (
    diag[
        "extra_farthest_m"
    ].to_numpy(dtype=float)
)

min_separation = (
    diag[
        "min_pair_separation_m"
    ].to_numpy(dtype=float)
)

required_depth = (
    diag[
        "required_depth"
    ].to_numpy(dtype=float)
)

effective_n = (
    diag[
        "effective_access_count"
    ].to_numpy(dtype=float)
)


report_dist(
    "Primary distance m",
    primary_dist,
)

report_dist(
    "Extra farthest m",
    extra_farthest,
)

report_dist(
    "Minimum separation m",
    min_separation,
)

report_dist(
    "Required depth",
    required_depth,
)

report_dist(
    "Effective access count",
    effective_n,
)


primary_lambda = (
    sel[
        sel["access_order"] == 1
    ][
        "lambda_L"
    ].to_numpy(dtype=float)
)

secondary2_lambda = (
    sel[
        sel["access_order"] == 2
    ][
        "lambda_L"
    ].to_numpy(dtype=float)
)

secondary3_lambda = (
    sel[
        sel["access_order"] == 3
    ][
        "lambda_L"
    ].to_numpy(dtype=float)
)


out()
out(
    f"Lambda primary median    : "
    f"{np.median(primary_lambda):.4f}"
)

out(
    f"Lambda secondary2 median : "
    f"{np.median(secondary2_lambda):.4f}"
)

out(
    f"Lambda secondary3 median : "
    f"{np.median(secondary3_lambda):.4f}"
)


# =============================================================================
# H. WRITE CSV
# =============================================================================

out()
out("H. WRITE CSV")
out("-" * 122)

sel.to_csv(
    OUT_CSV,
    index=False,
    encoding="utf-8-sig",
)

diag.to_csv(
    OUT_DIAG,
    index=False,
    encoding="utf-8-sig",
)

out(f"Selection   : {OUT_CSV}")
out(f"Diagnostics : {OUT_DIAG}")


# =============================================================================
# I. WRITE GPKG
# =============================================================================

out()
out("I. WRITE GPKG")
out("-" * 122)

gdf = gpd.GeoDataFrame(
    sel.copy(),
    geometry=gpd.points_from_xy(
        sel["x"],
        sel["y"],
    ),
    crs="EPSG:32632",
)

pyogrio.write_dataframe(
    gdf,
    OUT_GPKG,
    layer="Gamma_OSM_L_comuni_fvg_v01",
    driver="GPKG",
)


meta = sqlite3.connect(
    OUT_GPKG
)

meta.execute(
    """
    CREATE TABLE Gamma_OSM_L_metadata_v01 (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """
)

metadata = {
    "phase":
        "FASE_5_6_E1",

    "version":
        "v01",

    "status":
        "CANDIDATE_PENDING_E2",

    "created_at":
        STAMP,

    "source_B2":
        str(B2),

    "source_B3":
        str(B3),

    "source_B5_TIME":
        str(TIME_NPZ),

    "source_E0_candidates":
        str(E0_CANDIDATES),

    "structural_node_count":
        len(structural_set),

    "topological_segment_count":
        topo_segment_count,

    "municipality_count":
        sel["PRO_COM"].nunique(),

    "access_count":
        len(sel),

    "cardinality_K":
        K,

    "primary_rule":
        "nearest eligible structural node",

    "secondary_rule":
        "adaptive anchored lexicographic selection",

    "lexicographic_objective":
        "min(max centroid distance); "
        "min(sum centroid distances); "
        "max(min pair separation); "
        "node-id deterministic tie-break",

    "topological_independence":
        "no shared incident OSM topological segment",

    "minimum_pair_separation_m":
        MIN_SEP_M,

    "candidate_search":
        "adaptive; stop at first feasible depth",

    "validated_empirical_rank_bound":
        VALIDATED_MAX_RANK,

    "observed_required_depth_max":
        int(
            diag[
                "required_depth"
            ].max()
        ),

    "weight_rule":
        "EXP_REL_300",

    "weight_status":
        "CANDIDATE_PENDING_E2",

    "tau_m":
        TAU_M,

    "max_lambda_sum_error":
        max_lambda_error,

    "selection_deterministic":
        str(
            determinism_bad == 0
        ),

    "next_gate":
        "E2 full 645-source turn-aware Dijkstra",
}

meta.executemany(
    """
    INSERT INTO Gamma_OSM_L_metadata_v01(
        key,
        value
    )
    VALUES (?, ?)
    """,
    [
        (
            str(k),
            str(v),
        )
        for k, v in metadata.items()
    ],
)

meta.commit()
meta.close()


# =============================================================================
# J. HASH + MANIFEST
# =============================================================================

csv_sha = file_sha256(
    OUT_CSV
)

gpkg_sha = file_sha256(
    OUT_GPKG
)


manifest = {
    "phase":
        "FASE_5_6_E1",

    "version":
        "v01",

    "status":
        "CANDIDATE_PENDING_E2",

    "created_at":
        STAMP,

    "selection": {
        "municipalities":
            int(
                sel[
                    "PRO_COM"
                ].nunique()
            ),

        "records":
            int(
                len(sel)
            ),

        "K":
            K,

        "minimum_pair_separation_m":
            MIN_SEP_M,

        "candidate_search":
            "ADAPTIVE",

        "observed_required_depth_median":
            float(
                np.median(
                    diag[
                        "required_depth"
                    ]
                )
            ),

        "observed_required_depth_p95":
            float(
                np.percentile(
                    diag[
                        "required_depth"
                    ],
                    95,
                )
            ),

        "observed_required_depth_max":
            int(
                diag[
                    "required_depth"
                ].max()
            ),

        "weight_rule":
            "EXP_REL_300",

        "weight_status":
            "CANDIDATE_PENDING_E2",

        "tau_m":
            TAU_M,
    },

    "qa": {
        "bad_cardinality":
            bad_cardinality,

        "duplicate_nodes":
            duplicate_nodes,

        "duplicate_access_order":
            duplicate_access_order,

        "duplicate_base_states":
            base_state_duplicates,

        "primary_bad":
            primary_bad,

        "pair_sep_bad":
            pair_sep_bad,

        "topological_independence_bad":
            topo_bad,

        "depth_bad":
            depth_bad,

        "determinism_bad":
            determinism_bad,

        "nonpositive_lambda":
            nonpositive_lambda,

        "max_lambda_sum_error":
            max_lambda_error,
    },

    "sha256": {
        "csv":
            csv_sha,

        "gpkg":
            gpkg_sha,
    },

    "next_gate":
        "E2_FULL_645_SOURCE_DIJKSTRA",
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
# K. FINAL GATE
# =============================================================================

blocking = []

if (
    sel["PRO_COM"].nunique()
    != EXPECTED_COMUNI
):
    blocking.append(
        "MUNICIPALITY_COUNT"
    )

if len(sel) != EXPECTED_RECORDS:
    blocking.append(
        "ACCESS_COUNT"
    )

if failures:
    blocking.append(
        "SELECTION_FAILURE"
    )

if bad_cardinality:
    blocking.append(
        "CARDINALITY"
    )

if duplicate_nodes:
    blocking.append(
        "DUPLICATE_NODE"
    )

if duplicate_access_order:
    blocking.append(
        "DUPLICATE_ACCESS_ORDER"
    )

if base_state_duplicates:
    blocking.append(
        "DUPLICATE_BASE_STATE"
    )

if primary_bad:
    blocking.append(
        "PRIMARY_NOT_NEAREST"
    )

if pair_sep_bad:
    blocking.append(
        "PAIR_SEPARATION"
    )

if topo_bad:
    blocking.append(
        "TOPOLOGICAL_INDEPENDENCE"
    )

if depth_bad:
    blocking.append(
        "SEARCH_DEPTH_REGRESSION"
    )

if determinism_bad:
    blocking.append(
        "NONDETERMINISTIC_SELECTION"
    )

if nonpositive_lambda:
    blocking.append(
        "NONPOSITIVE_WEIGHT"
    )

if max_lambda_error > 1e-12:
    blocking.append(
        "WEIGHT_NORMALIZATION"
    )


out()
out("=" * 122)

if blocking:

    out(
        "ESITO E1: FAIL"
    )

    for item in blocking:

        out(
            f"  BLOCKING: {item}"
        )

else:

    out(
        "ESITO E1: PASS_CANDIDATE"
    )

out("=" * 122)

out(
    f"GPKG SHA256 : "
    f"{gpkg_sha}"
)

out(
    f"CSV SHA256  : "
    f"{csv_sha}"
)

out(f"GPKG     : {OUT_GPKG}")
out(f"CSV      : {OUT_CSV}")
out(f"Manifest : {OUT_MANIFEST}")
out(f"LOG      : {LOG}")

out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

b2.close()
b3.close()
