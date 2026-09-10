from pathlib import Path
from collections import defaultdict
from itertools import combinations
from datetime import datetime
import math
import sqlite3

import numpy as np
import pandas as pd

from scipy.sparse import load_npz
from scipy.sparse.csgraph import breadth_first_order


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

CANDIDATES = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"gamma_sensitivity\Gamma_OSM_topological_top50_E0_v03.csv"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "gamma_sensitivity"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

OUT = (
    OUTDIR
    / "Gamma_OSM_cardinality_final_audit_E0_v04.csv"
)

LOG = (
    OUTDIR
    / f"gamma_osm_cardinality_final_audit_v04_{STAMP}.txt"
)

K_VALUES = [1, 2, 3, 5]


lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def percentile(a, q):
    a = np.asarray(a, dtype=float)
    return float(np.percentile(a, q))


out("=" * 118)
out("FASE 5.6 — E0_v04 — Gamma_OSM FINAL CARDINALITY AUDIT")
out("=" * 118)

for p in [
    B2,
    B3,
    TIME_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
    CANDIDATES,
]:
    if not p.exists():
        raise FileNotFoundError(p)

if OUT.exists():
    raise RuntimeError(
        f"Output già esistente: {OUT}"
    )


# =============================================================================
# A. CANDIDATI V03
# =============================================================================

out()
out("A. CANDIDATI CORRETTI E0_v03")
out("-" * 118)

cand = pd.read_csv(
    CANDIDATES
)

required = [
    "PRO_COM",
    "COMUNE",
    "source_rank",
    "node_id",
    "x",
    "y",
    "distance_m",
]

missing = [
    c for c in required
    if c not in cand.columns
]

if missing:
    raise RuntimeError(
        f"Campi mancanti: {missing}"
    )

out(f"Candidate rows : {len(cand):,}")
out(f"Comuni         : {cand['PRO_COM'].nunique():,}")

candidate_nodes = set(
    cand["node_id"]
    .astype(np.int64)
    .tolist()
)


# =============================================================================
# B. RICOSTRUZIONE STRUCTURAL SET CORRETTO
# =============================================================================

out()
out("B. STRUCTURAL SET CORRETTO")
out("-" * 118)

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
    [int(r[0]) for r in rows],
    dtype=np.int64,
)

degrees = np.asarray(
    [int(r[1]) for r in rows],
    dtype=np.int32,
)

out(f"B3 giant SCC : {len(giant_nodes):,}")


# =============================================================================
# C. B5 MUTUAL DOMAIN
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
    or int(base_nodes[anchor_state]) != anchor_node
):
    raise RuntimeError(
        "Anchor non presente nei base states."
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

dest_ok = fp < len(forward_phys)

safe_fp = np.minimum(
    fp,
    len(forward_phys) - 1,
)

dest_ok &= (
    forward_phys[safe_fp]
    == giant_nodes
)

bp = np.searchsorted(
    base_nodes,
    giant_nodes,
)

base_ok = bp < len(base_nodes)

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

valid = np.flatnonzero(
    base_ok
)

origin_ok[valid] = (
    reverse_mask[
        bp[valid]
    ]
)

mutual = (
    dest_ok
    &
    origin_ok
)

out(
    f"B5 mutual : "
    f"{int(mutual.sum()):,}"
)

giant_nodes = giant_nodes[mutual]
degrees = degrees[mutual]

del TIME
del reverse_mask


# =============================================================================
# D. INCIDENT WAY COUNT E STRUCTURAL NODES
# =============================================================================

out()
out("D. STRUCTURAL NODE RULE")
out("-" * 118)

way_count = {}

for nid, nways in b2.execute(
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
        for nid in giant_nodes
    ],
    dtype=np.int16,
)

structural_mask = (
    (degrees != 2)
    |
    (incident_way_count >= 2)
)

structural_nodes = giant_nodes[
    structural_mask
]

structural_set = set(
    int(x)
    for x in structural_nodes
)

out(
    f"Structural nodes : "
    f"{len(structural_set):,}"
)

missing_candidate_structural = (
    candidate_nodes
    -
    structural_set
)

out(
    f"Candidate non structural : "
    f"{len(missing_candidate_structural):,}"
)

if missing_candidate_structural:
    raise RuntimeError(
        "Candidate v03 non appartenenti "
        "allo structural set ricostruito."
    )


# =============================================================================
# E. TOPOLOGICAL SEGMENTS CORRETTI
# =============================================================================

out()
out("E. TOPOLOGICAL SEGMENT INCIDENCE — CORRECTED")
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
    nid
    for nid in candidate_nodes
    if not topo_sets[nid]
]

out(
    f"Topological segments : "
    f"{topo_segment_count:,}"
)

out(
    f"Candidate senza topo incidence : "
    f"{len(missing_topo):,}"
)

if missing_topo:
    raise RuntimeError(
        "Candidate senza topological incidence."
    )


# =============================================================================
# F. NEAREST-K FINAL AUDIT
# =============================================================================

out()
out("F. NEAREST-K FINAL CARDINALITY AUDIT")
out("-" * 118)

summary_rows = []


for K in K_VALUES:

    feasible = 0

    shared_topo = 0
    sep_lt_50 = 0
    sep_lt_100 = 0

    extras = []
    farthest = []
    min_seps = []

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
            .head(K)
            .to_dict("records")
        )

        if len(records) < K:
            continue

        feasible += 1

        distances = [
            float(r["distance_m"])
            for r in records
        ]

        extras.append(
            max(distances)
            - distances[0]
        )

        farthest.append(
            max(distances)
        )

        if K > 1:

            pair_distances = []

            municipality_shared = False

            for a, b in combinations(
                records,
                2,
            ):

                d = math.hypot(
                    float(a["x"])
                    - float(b["x"]),

                    float(a["y"])
                    - float(b["y"]),
                )

                pair_distances.append(d)

                if (
                    topo_sets[
                        int(a["node_id"])
                    ]
                    &
                    topo_sets[
                        int(b["node_id"])
                    ]
                ):
                    municipality_shared = True

            min_sep = min(
                pair_distances
            )

            min_seps.append(
                min_sep
            )

            if min_sep < 50:
                sep_lt_50 += 1

            if min_sep < 100:
                sep_lt_100 += 1

            if municipality_shared:
                shared_topo += 1


    row = {
        "K":
            K,

        "municipalities_feasible":
            feasible,

        "municipalities_shared_toposeg":
            shared_topo,

        "municipalities_minsep_lt50":
            sep_lt_50,

        "municipalities_minsep_lt100":
            sep_lt_100,

        "median_extra_m":
            float(
                np.median(extras)
            ),

        "p95_extra_m":
            percentile(
                extras,
                95,
            ),

        "median_farthest_m":
            float(
                np.median(farthest)
            ),

        "p95_farthest_m":
            percentile(
                farthest,
                95,
            ),

        "median_minsep_m":
            (
                float(
                    np.median(min_seps)
                )
                if min_seps
                else np.nan
            ),

        "min_minsep_m":
            (
                float(
                    min(min_seps)
                )
                if min_seps
                else np.nan
            ),
    }

    summary_rows.append(
        row
    )

    out(
        f"K={K} | "
        f"feasible={feasible:3}/215 | "
        f"shared-toposeg="
        f"{shared_topo:3} | "
        f"minsep<50="
        f"{sep_lt_50:3} | "
        f"minsep<100="
        f"{sep_lt_100:3} | "
        f"extra-med="
        f"{row['median_extra_m']:7.1f} m | "
        f"extra-p95="
        f"{row['p95_extra_m']:7.1f} m"
    )


summary = pd.DataFrame(
    summary_rows
)

summary.to_csv(
    OUT,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# G. CROSS-CHECK K3@100 DA V03
# =============================================================================

out()
out("G. CROSS-CHECK E0_v03")
out("-" * 118)

required_rank_csv = (
    OUTDIR
    / "Gamma_OSM_K3_100m_required_rank_E0_v03.csv"
)

if not required_rank_csv.exists():
    raise FileNotFoundError(
        required_rank_csv
    )

rank_df = pd.read_csv(
    required_rank_csv
)

feasible = int(
    rank_df[
        "feasible_within_50"
    ].sum()
)

max_required_rank = int(
    rank_df[
        "minimum_required_depth"
    ].max()
)

p95_required_rank = float(
    np.percentile(
        rank_df[
            "minimum_required_depth"
        ],
        95,
    )
)

out(
    f"K3@100 feasible : "
    f"{feasible}/215"
)

out(
    f"Required rank p95: "
    f"{p95_required_rank:.1f}"
)

out(
    f"Required rank max: "
    f"{max_required_rank}"
)


# =============================================================================
# H. FINAL
# =============================================================================

out()
out("=" * 118)

if (
    feasible == 215
    and max_required_rank <= 30
):

    out(
        "ESITO E0_v04: CARDINALITY_AUDIT_READY"
    )

else:

    out(
        "ESITO E0_v04: CHECK_REQUIRED"
    )

out("=" * 118)

out(f"Output : {OUT}")
out(f"LOG    : {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

b2.close()
b3.close()
