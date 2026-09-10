from pathlib import Path
from datetime import datetime
import hashlib
import json
import math
import sqlite3
import time

import numpy as np
import pandas as pd

from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

B5DIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b5"
)

TIME_NPZ = (
    B5DIR
    / "osm_turn_state_time_v01.npz"
)

BASE_NODES_NPY = (
    B5DIR
    / "osm_turn_state_base_nodes_v01.npy"
)

STATE_NODE_NPY = (
    B5DIR
    / "osm_turn_state_node_id_v01.npy"
)

E1_CSV = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"gamma_osm\Gamma_OSM_L_comuni_fvg_v01_CANDIDATE.csv"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"gamma_osm\e2"
)

OUTDIR.mkdir(
    parents=True,
    exist_ok=True,
)

WORKDIR = (
    OUTDIR
    / "_work_E2_v01"
)

WORKDIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUT_MATRIX = (
    OUTDIR
    / "Gamma_OSM_E2_time_matrix_645x645_v01.npy"
)

OUT_ACCESS_INDEX = (
    OUTDIR
    / "Gamma_OSM_E2_access_index_v01.csv"
)

OUT_INTER = (
    OUTDIR
    / "Gamma_OSM_E2_intermunicipal_pairs_v01.csv"
)

OUT_INTRA = (
    OUTDIR
    / "Gamma_OSM_E2_intramunicipal_pairs_v01.csv"
)

OUT_ACCESS_SUMMARY = (
    OUTDIR
    / "Gamma_OSM_E2_access_summary_v01.csv"
)

OUT_TRIPLET_SUMMARY = (
    OUTDIR
    / "Gamma_OSM_E2_triplet_summary_v01.csv"
)

OUT_UNREACHABLE = (
    OUTDIR
    / "Gamma_OSM_E2_unreachable_pairs_v01.csv"
)

OUT_ASYMMETRY = (
    OUTDIR
    / "Gamma_OSM_E2_top_asymmetry_v01.csv"
)

OUT_DETOUR = (
    OUTDIR
    / "Gamma_OSM_E2_top_detour_proxy_v01.csv"
)

OUT_MANIFEST = (
    OUTDIR
    / "Gamma_OSM_E2_manifest_v01.json"
)

WORK_MATRIX = (
    WORKDIR
    / "time_matrix_WORK.npy"
)

WORK_DONE = (
    WORKDIR
    / "sources_done.npy"
)

WORK_META = (
    WORKDIR
    / "checkpoint_metadata.json"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

LOG = (
    OUTDIR
    / f"full_645_source_dijkstra_turnaware_v01_{STAMP}.txt"
)

EXPECTED_COMUNI = 215
K = 3
EXPECTED_ACCESS = 645

EXPECTED_INTER = (
    EXPECTED_COMUNI
    * (EXPECTED_COMUNI - 1)
    * K
    * K
)

EXPECTED_INTRA = (
    EXPECTED_COMUNI
    * K
    * (K - 1)
)

EXPECTED_OFFDIAG = (
    EXPECTED_ACCESS
    * (EXPECTED_ACCESS - 1)
)

EXPECTED_FULL = (
    EXPECTED_ACCESS
    * EXPECTED_ACCESS
)

# 4 sorgenti per chiamata:
# memoria molto contenuta anche su macchina non enorme.
DIJKSTRA_BATCH_SIZE = 4

# Tolleranza sul bound fisico velocità,
# per assorbire piccole differenze metriche/proiezione.
SPEED_BOUND_TOLERANCE = 1.01

TOP_DIAGNOSTIC_ROWS = 100


# =============================================================================
# LOG
# =============================================================================

lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def sha256(path):

    h = hashlib.sha256()

    with open(path, "rb") as f:

        while True:

            chunk = f.read(
                1024 * 1024
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 124)
out("FASE 5.6 — E2 — FULL 645-SOURCE DIJKSTRA TURN-AWARE")
out("=" * 124)

for p in [
    B2,
    TIME_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
    E1_CSV,
]:

    if not p.exists():
        raise FileNotFoundError(p)


final_outputs = [
    OUT_MATRIX,
    OUT_ACCESS_INDEX,
    OUT_INTER,
    OUT_INTRA,
    OUT_ACCESS_SUMMARY,
    OUT_TRIPLET_SUMMARY,
    OUT_UNREACHABLE,
    OUT_ASYMMETRY,
    OUT_DETOUR,
    OUT_MANIFEST,
]

existing_final = [
    p
    for p in final_outputs
    if p.exists()
]

if existing_final:

    raise RuntimeError(
        "Output finali E2 già esistenti:\n"
        + "\n".join(
            str(x)
            for x in existing_final
        )
    )


out(f"B2          : {B2}")
out(f"B5 TIME     : {TIME_NPZ}")
out(f"E1 Gamma    : {E1_CSV}")
out(f"Batch size  : {DIJKSTRA_BATCH_SIZE}")

out()
out("Conteggi teorici")
out("-" * 124)

out(f"Full matrix              : {EXPECTED_FULL:,}")
out(f"Self                     : {EXPECTED_ACCESS:,}")
out(f"Intra-comunali ordinati  : {EXPECTED_INTRA:,}")
out(f"Inter-comunali ordinati  : {EXPECTED_INTER:,}")
out(f"Off-diagonal totali      : {EXPECTED_OFFDIAG:,}")


# =============================================================================
# A. LOAD E1
# =============================================================================

out()
out("A. LOAD Gamma_OSM E1")
out("-" * 124)

gamma = pd.read_csv(
    E1_CSV
)

required = [
    "PRO_COM",
    "COMUNE",
    "access_order",
    "structural_node_id",
    "base_state_id",
    "candidate_rank",
    "x",
    "y",
    "lambda_L",
]

missing = [
    c
    for c in required
    if c not in gamma.columns
]

if missing:

    raise RuntimeError(
        f"Campi E1 mancanti: {missing}"
    )


gamma = (
    gamma
    .sort_values(
        [
            "PRO_COM",
            "access_order",
        ]
    )
    .reset_index(drop=True)
)


gamma["access_index"] = np.arange(
    len(gamma),
    dtype=np.int32,
)


if len(gamma) != EXPECTED_ACCESS:

    raise RuntimeError(
        f"Accessi E1={len(gamma)}, "
        f"attesi {EXPECTED_ACCESS}"
    )


if (
    gamma["PRO_COM"].nunique()
    != EXPECTED_COMUNI
):

    raise RuntimeError(
        "E1 non contiene 215 comuni."
    )


counts = (
    gamma.groupby("PRO_COM")
    .size()
)

if not (counts == 3).all():

    raise RuntimeError(
        "E1 non ha esattamente 3 accessi/comune."
    )


out(f"Accessi       : {len(gamma):,}")
out(f"Comuni        : {gamma['PRO_COM'].nunique():,}")


# =============================================================================
# B. LOAD STATE GRAPH
# =============================================================================

out()
out("B. LOAD B5 STATE GRAPH")
out("-" * 124)

TIME = load_npz(
    TIME_NPZ
).tocsr()

base_nodes = np.load(
    BASE_NODES_NPY
)

state_node = np.load(
    STATE_NODE_NPY
)


if TIME.shape[0] != TIME.shape[1]:

    raise RuntimeError(
        "TIME matrix non quadrata."
    )

if TIME.shape[0] != len(state_node):

    raise RuntimeError(
        "Mismatch TIME/state_node."
    )

if len(base_nodes) > len(state_node):

    raise RuntimeError(
        "base_nodes > state_node."
    )


out(f"B5 states      : {TIME.shape[0]:,}")
out(f"B5 transitions : {TIME.nnz:,}")
out(f"Base states    : {len(base_nodes):,}")


# =============================================================================
# C. SOURCE STATE VALIDATION
# =============================================================================

out()
out("C. SOURCE-STATE VALIDATION")
out("-" * 124)

access_nodes = (
    gamma[
        "structural_node_id"
    ]
    .to_numpy(
        dtype=np.int64
    )
)

source_states = (
    gamma[
        "base_state_id"
    ]
    .to_numpy(
        dtype=np.int64
    )
)


bad_source_state = []

for i, (
    nid,
    sid,
) in enumerate(
    zip(
        access_nodes,
        source_states,
    )
):

    if (
        sid < 0
        or sid >= len(base_nodes)
        or int(
            base_nodes[sid]
        ) != int(nid)
    ):

        bad_source_state.append(
            (
                i,
                int(nid),
                int(sid),
            )
        )


out(
    f"Source-state mismatch : "
    f"{len(bad_source_state):,}"
)

if bad_source_state:

    out(
        "Esempi: "
        + str(
            bad_source_state[:20]
        )
    )

    raise RuntimeError(
        "E1 base_state_id non coerente con B5."
    )


source_outdegree = (
    np.diff(
        TIME.indptr
    )[
        source_states
    ]
)

zero_outdegree_sources = np.flatnonzero(
    source_outdegree == 0
)

out(
    f"Source base-state outdegree=0 : "
    f"{len(zero_outdegree_sources):,}"
)


# =============================================================================
# D. GLOBAL DUPLICATE NODE QA
# =============================================================================

out()
out("D. GLOBAL STRUCTURAL-NODE UNIQUENESS")
out("-" * 124)

duplicate_global_mask = (
    gamma[
        "structural_node_id"
    ]
    .duplicated(
        keep=False
    )
)

duplicate_global = gamma[
    duplicate_global_mask
].copy()

duplicate_global_count = int(
    duplicate_global_mask.sum()
)

out(
    f"Access rows su node_id globale duplicato : "
    f"{duplicate_global_count:,}"
)

if duplicate_global_count:

    for r in (
        duplicate_global
        .head(20)
        .itertuples()
    ):

        out(
            f"  node={int(r.structural_node_id)} "
            f"PRO_COM={int(r.PRO_COM)} "
            f"access={int(r.access_order)}"
        )


# =============================================================================
# E. DESTINATION STATE GROUPS
# =============================================================================

out()
out("E. DESTINATION STATE GROUPS")
out("-" * 124)

# Ordiniamo una sola volta state_node.
# Poi ogni structural_node recupera tutti gli state
# che rappresentano lo stesso nodo fisico.

state_sort = np.argsort(
    state_node,
    kind="stable",
)

sorted_state_nodes = (
    state_node[
        state_sort
    ]
)


destination_states = []

for nid in access_nodes:

    left = int(
        np.searchsorted(
            sorted_state_nodes,
            int(nid),
            side="left",
        )
    )

    right = int(
        np.searchsorted(
            sorted_state_nodes,
            int(nid),
            side="right",
        )
    )

    states = state_sort[
        left:right
    ].astype(
        np.int64,
        copy=False,
    )

    if len(states) == 0:

        raise RuntimeError(
            f"Nessuno state B5 per access node {nid}"
        )

    destination_states.append(
        states
    )


destination_state_counts = np.asarray(
    [
        len(x)
        for x in destination_states
    ],
    dtype=np.int32,
)


out(
    f"Destination-state count min/med/max : "
    f"{destination_state_counts.min()} / "
    f"{np.median(destination_state_counts):.1f} / "
    f"{destination_state_counts.max()}"
)


# =============================================================================
# F. CHECKPOINT INITIALIZATION / RESUME
# =============================================================================

out()
out("F. CHECKPOINT")
out("-" * 124)

fingerprint = {
    "version":
        "E2_v01",

    "E1_csv_sha256":
        sha256(E1_CSV),

    "B5_time_sha256":
        sha256(TIME_NPZ),

    "access_count":
        EXPECTED_ACCESS,

    "state_count":
        int(TIME.shape[0]),

    "transition_count":
        int(TIME.nnz),

    "batch_size":
        DIJKSTRA_BATCH_SIZE,
}


if WORK_META.exists():

    old_meta = json.loads(
        WORK_META.read_text(
            encoding="utf-8"
        )
    )

    if old_meta != fingerprint:

        raise RuntimeError(
            "Checkpoint E2 esistente ma fingerprint diversa.\n"
            "Non riutilizzo risultati di un input differente."
        )

    if (
        not WORK_MATRIX.exists()
        or
        not WORK_DONE.exists()
    ):

        raise RuntimeError(
            "Checkpoint metadata presente ma file work mancanti."
        )

    work_matrix = np.load(
        WORK_MATRIX,
        mmap_mode="r+",
    )

    done = np.load(
        WORK_DONE
    ).astype(bool)

    if (
        work_matrix.shape
        != (
            EXPECTED_ACCESS,
            EXPECTED_ACCESS,
        )
    ):

        raise RuntimeError(
            "Shape checkpoint matrix errata."
        )

    if len(done) != EXPECTED_ACCESS:

        raise RuntimeError(
            "Shape checkpoint done errata."
        )

    out(
        f"RESUME checkpoint: "
        f"{int(done.sum())}/{EXPECTED_ACCESS} sorgenti già completate"
    )


else:

    if (
        WORK_MATRIX.exists()
        or WORK_DONE.exists()
    ):

        raise RuntimeError(
            "Work file E2 presenti senza metadata."
        )

    work_matrix = np.lib.format.open_memmap(
        WORK_MATRIX,
        mode="w+",
        dtype=np.float64,
        shape=(
            EXPECTED_ACCESS,
            EXPECTED_ACCESS,
        ),
    )

    work_matrix[:] = np.nan
    work_matrix.flush()

    done = np.zeros(
        EXPECTED_ACCESS,
        dtype=bool,
    )

    np.save(
        WORK_DONE,
        done,
    )

    WORK_META.write_text(
        json.dumps(
            fingerprint,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out(
        "Nuovo checkpoint inizializzato."
    )


# =============================================================================
# G. FULL 645-SOURCE DIJKSTRA
# =============================================================================

out()
out("G. FULL 645-SOURCE DIJKSTRA")
out("-" * 124)

todo = np.flatnonzero(
    ~done
)

out(
    f"Sorgenti da calcolare : "
    f"{len(todo):,}"
)

t0 = time.perf_counter()

completed_this_run = 0


for batch_start in range(
    0,
    len(todo),
    DIJKSTRA_BATCH_SIZE,
):

    batch_indices = todo[
        batch_start:
        batch_start
        + DIJKSTRA_BATCH_SIZE
    ]

    batch_source_states = (
        source_states[
            batch_indices
        ]
    )


    # Ogni indice rappresenta un Dijkstra indipendente.
    dist = dijkstra(
        TIME,
        directed=True,
        indices=batch_source_states,
        return_predecessors=False,
    )


    if dist.ndim == 1:

        dist = dist[
            np.newaxis,
            :
        ]


    batch_result = np.empty(
        (
            len(batch_indices),
            EXPECTED_ACCESS,
        ),
        dtype=np.float64,
    )


    # Destinazione fisica:
    # minimo fra tutti gli state B5 associati
    # allo structural node.
    for dest_idx, states in enumerate(
        destination_states
    ):

        batch_result[
            :,
            dest_idx
        ] = np.min(
            dist[
                :,
                states
            ],
            axis=1,
        )


    work_matrix[
        batch_indices,
        :
    ] = batch_result

    work_matrix.flush()


    done[
        batch_indices
    ] = True

    np.save(
        WORK_DONE,
        done,
    )


    completed_this_run += len(
        batch_indices
    )

    elapsed = (
        time.perf_counter()
        - t0
    )

    total_done = int(
        done.sum()
    )

    rate = (
        completed_this_run
        / elapsed
        if elapsed > 0
        else float("nan")
    )

    remaining = (
        EXPECTED_ACCESS
        - total_done
    )

    eta_s = (
        remaining / rate
        if rate > 0
        else float("nan")
    )


    out(
        f"  done="
        f"{total_done:>3}/{EXPECTED_ACCESS} | "
        f"batch={len(batch_indices)} | "
        f"elapsed={elapsed/60:8.1f} min | "
        f"ETA={eta_s/60:8.1f} min"
    )


if not done.all():

    raise RuntimeError(
        "Non tutte le sorgenti E2 risultano completate."
    )


out(
    "Tutti i 645 Dijkstra completati."
)


# =============================================================================
# H. FINAL MATRIX
# =============================================================================

out()
out("H. FINAL MATRIX")
out("-" * 124)

M = np.asarray(
    work_matrix,
    dtype=np.float64,
)

np.save(
    OUT_MATRIX,
    M,
)

gamma.to_csv(
    OUT_ACCESS_INDEX,
    index=False,
    encoding="utf-8-sig",
)

out(
    f"Matrix shape : "
    f"{M.shape}"
)

out(
    f"Finite cells : "
    f"{np.isfinite(M).sum():,}"
)


# =============================================================================
# I. HARD REACHABILITY QA
# =============================================================================

out()
out("I. HARD REACHABILITY QA")
out("-" * 124)

finite = np.isfinite(
    M
)

diag_values = np.diag(
    M
)

diagonal_bad = int(
    (
        np.abs(
            diag_values
        )
        > 1e-9
    ).sum()
)


source_reachable = finite.sum(
    axis=1
)

destination_reachable = finite.sum(
    axis=0
)

bad_source_reach = int(
    (
        source_reachable
        != EXPECTED_ACCESS
    ).sum()
)

bad_destination_reach = int(
    (
        destination_reachable
        != EXPECTED_ACCESS
    ).sum()
)


pro = (
    gamma[
        "PRO_COM"
    ]
    .to_numpy(
        dtype=np.int64
    )
)

orders = (
    gamma[
        "access_order"
    ]
    .to_numpy(
        dtype=np.int8
    )
)


ii = np.repeat(
    np.arange(
        EXPECTED_ACCESS,
        dtype=np.int32
    ),
    EXPECTED_ACCESS,
)

jj = np.tile(
    np.arange(
        EXPECTED_ACCESS,
        dtype=np.int32
    ),
    EXPECTED_ACCESS,
)


offdiag_mask = (
    ii != jj
)

inter_mask = (
    pro[ii]
    !=
    pro[jj]
)

intra_mask = (
    (pro[ii] == pro[jj])
    &
    offdiag_mask
)


flat_time = M[
    ii,
    jj
]


unreachable_offdiag = (
    offdiag_mask
    &
    ~np.isfinite(
        flat_time
    )
)

unreachable_inter = (
    inter_mask
    &
    ~np.isfinite(
        flat_time
    )
)

unreachable_intra = (
    intra_mask
    &
    ~np.isfinite(
        flat_time
    )
)


zero_offdiag = (
    offdiag_mask
    &
    np.isfinite(
        flat_time
    )
    &
    (
        flat_time
        <= 1e-12
    )
)


negative_time = (
    np.isfinite(
        flat_time
    )
    &
    (
        flat_time
        < -1e-12
    )
)


out(
    f"Diagonal non-zero              : "
    f"{diagonal_bad:,}"
)

out(
    f"Source con reach !=645         : "
    f"{bad_source_reach:,}"
)

out(
    f"Destination con reach !=645    : "
    f"{bad_destination_reach:,}"
)

out(
    f"Unreachable off-diagonal       : "
    f"{int(unreachable_offdiag.sum()):,}"
)

out(
    f"Unreachable intermunicipal     : "
    f"{int(unreachable_inter.sum()):,}"
)

out(
    f"Unreachable intramunicipal     : "
    f"{int(unreachable_intra.sum()):,}"
)

out(
    f"Zero-time off-diagonal         : "
    f"{int(zero_offdiag.sum()):,}"
)

out(
    f"Negative-time cells            : "
    f"{int(negative_time.sum()):,}"
)


# =============================================================================
# J. PAIR DATAFRAMES
# =============================================================================

out()
out("J. PAIR TABLES")
out("-" * 124)

node = (
    gamma[
        "structural_node_id"
    ]
    .to_numpy(
        dtype=np.int64
    )
)

x = (
    gamma[
        "x"
    ]
    .to_numpy(
        dtype=float
    )
)

y = (
    gamma[
        "y"
    ]
    .to_numpy(
        dtype=float
    )
)


def build_pair_df(mask):

    src = ii[
        mask
    ]

    dst = jj[
        mask
    ]

    t = M[
        src,
        dst
    ]

    reverse_t = M[
        dst,
        src
    ]

    euclid = np.hypot(
        x[src] - x[dst],
        y[src] - y[dst],
    )

    min_t = np.minimum(
        t,
        reverse_t,
    )

    max_t = np.maximum(
        t,
        reverse_t,
    )

    asym_ratio = np.full(
        len(t),
        np.nan,
        dtype=float,
    )

    valid_ratio = (
        np.isfinite(
            min_t
        )
        &
        np.isfinite(
            max_t
        )
        &
        (
            min_t > 0
        )
    )

    asym_ratio[
        valid_ratio
    ] = (
        max_t[
            valid_ratio
        ]
        /
        min_t[
            valid_ratio
        ]
    )


    return pd.DataFrame({
        "source_index":
            src,

        "destination_index":
            dst,

        "source_PRO_COM":
            pro[src],

        "destination_PRO_COM":
            pro[dst],

        "source_access_order":
            orders[src],

        "destination_access_order":
            orders[dst],

        "source_node_id":
            node[src],

        "destination_node_id":
            node[dst],

        "time_s":
            t,

        "reverse_time_s":
            reverse_t,

        "asymmetry_ratio":
            asym_ratio,

        "asymmetry_abs_s":
            np.abs(
                t
                - reverse_t
            ),

        "euclidean_m":
            euclid,

        "reachable":
            np.isfinite(t).astype(
                np.int8
            ),
    })


inter_df = build_pair_df(
    inter_mask
)

intra_df = build_pair_df(
    intra_mask
)


if len(inter_df) != EXPECTED_INTER:

    raise RuntimeError(
        f"Inter pairs={len(inter_df)}, "
        f"attesi {EXPECTED_INTER}"
    )

if len(intra_df) != EXPECTED_INTRA:

    raise RuntimeError(
        f"Intra pairs={len(intra_df)}, "
        f"attesi {EXPECTED_INTRA}"
    )


inter_df.to_csv(
    OUT_INTER,
    index=False,
    encoding="utf-8-sig",
)

intra_df.to_csv(
    OUT_INTRA,
    index=False,
    encoding="utf-8-sig",
)


out(
    f"Inter rows : "
    f"{len(inter_df):,}"
)

out(
    f"Intra rows : "
    f"{len(intra_df):,}"
)


# =============================================================================
# K. UNREACHABLE TABLE
# =============================================================================

out()
out("K. UNREACHABLE DIAGNOSTIC")
out("-" * 124)

unreach_mask = (
    offdiag_mask
    &
    ~np.isfinite(
        flat_time
    )
)

unreach_src = ii[
    unreach_mask
]

unreach_dst = jj[
    unreach_mask
]

unreachable_df = pd.DataFrame({
    "source_index":
        unreach_src,

    "destination_index":
        unreach_dst,

    "source_PRO_COM":
        pro[
            unreach_src
        ],

    "destination_PRO_COM":
        pro[
            unreach_dst
        ],

    "source_access_order":
        orders[
            unreach_src
        ],

    "destination_access_order":
        orders[
            unreach_dst
        ],

    "source_node_id":
        node[
            unreach_src
        ],

    "destination_node_id":
        node[
            unreach_dst
        ],
})

unreachable_df.to_csv(
    OUT_UNREACHABLE,
    index=False,
    encoding="utf-8-sig",
)

out(
    f"Unreachable rows written : "
    f"{len(unreachable_df):,}"
)


# =============================================================================
# L. PHYSICAL TIME LOWER-BOUND QA
# =============================================================================

out()
out("L. PHYSICAL TIME LOWER-BOUND QA")
out("-" * 124)

b2 = sqlite3.connect(
    B2
)

max_speed_kmh = float(
    b2.execute(
        """
        SELECT MAX(speed_kmh)
        FROM directed_edges
        WHERE core_eligible = 1
        """
    ).fetchone()[0]
)

b2.close()


out(
    f"Max CORE speed model : "
    f"{max_speed_kmh:.3f} km/h"
)


# Controllo solo coppie intermunicipali.
inter_min_physical_time = (
    inter_df[
        "euclidean_m"
    ].to_numpy(
        dtype=float
    )
    * 3.6
    / (
        max_speed_kmh
        * SPEED_BOUND_TOLERANCE
    )
)

inter_times = (
    inter_df[
        "time_s"
    ].to_numpy(
        dtype=float
    )
)

impossible_time = (
    np.isfinite(
        inter_times
    )
    &
    (
        inter_times
        + 1e-6
        <
        inter_min_physical_time
    )
)

impossible_time_count = int(
    impossible_time.sum()
)

out(
    f"Physical lower-bound violations : "
    f"{impossible_time_count:,}"
)


# Detour proxy:
# rapporto fra tempo reale e tempo teorico alla
# velocità massima in linea retta.
base_lower_bound = (
    inter_df[
        "euclidean_m"
    ].to_numpy(
        dtype=float
    )
    * 3.6
    / max_speed_kmh
)

detour_proxy = np.full(
    len(inter_df),
    np.nan,
    dtype=float,
)

valid_detour = (
    np.isfinite(
        inter_times
    )
    &
    (
        base_lower_bound > 1e-9
    )
)

detour_proxy[
    valid_detour
] = (
    inter_times[
        valid_detour
    ]
    /
    base_lower_bound[
        valid_detour
    ]
)

detour_df = (
    inter_df.copy()
)

detour_df[
    "time_vs_maxspeed_euclid_factor"
] = detour_proxy

detour_df = (
    detour_df
    .sort_values(
        "time_vs_maxspeed_euclid_factor",
        ascending=False,
    )
    .head(
        TOP_DIAGNOSTIC_ROWS
    )
)

detour_df.to_csv(
    OUT_DETOUR,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# M. ASYMMETRY QA
# =============================================================================

out()
out("M. ASYMMETRY QA")
out("-" * 124)

# Una coppia ordinata e il suo reverse compaiono entrambe.
# Per le statistiche teniamo una sola metà.
upper_inter = (
    (
        inter_df[
            "source_index"
        ]
        <
        inter_df[
            "destination_index"
        ]
    )
)

asym = (
    inter_df[
        upper_inter
    ]
    .copy()
)

valid_asym = asym[
    np.isfinite(
        asym[
            "asymmetry_ratio"
        ]
    )
]


if len(valid_asym):

    ratios = (
        valid_asym[
            "asymmetry_ratio"
        ].to_numpy(
            dtype=float
        )
    )

    out(
        f"Asymmetry ratio median : "
        f"{np.median(ratios):.4f}"
    )

    out(
        f"Asymmetry ratio p95    : "
        f"{np.percentile(ratios,95):.4f}"
    )

    out(
        f"Asymmetry ratio p99    : "
        f"{np.percentile(ratios,99):.4f}"
    )

    out(
        f"Asymmetry ratio max    : "
        f"{np.max(ratios):.4f}"
    )


top_asym = (
    valid_asym
    .sort_values(
        [
            "asymmetry_ratio",
            "asymmetry_abs_s",
        ],
        ascending=[
            False,
            False,
        ],
    )
    .head(
        TOP_DIAGNOSTIC_ROWS
    )
)

top_asym.to_csv(
    OUT_ASYMMETRY,
    index=False,
    encoding="utf-8-sig",
)


out()
out("Top 10 asymmetry intermunicipal")
out("-" * 124)

for r in (
    top_asym
    .head(10)
    .itertuples()
):

    out(
        f"{int(r.source_PRO_COM)}:"
        f"{int(r.source_access_order)} "
        f"<-> "
        f"{int(r.destination_PRO_COM)}:"
        f"{int(r.destination_access_order)} | "
        f"{r.time_s:9.1f}s / "
        f"{r.reverse_time_s:9.1f}s | "
        f"ratio={r.asymmetry_ratio:7.3f}"
    )


# =============================================================================
# N. ACCESS-LEVEL QA
# =============================================================================

out()
out("N. ACCESS-LEVEL QA")
out("-" * 124)

access_summary_rows = []


for i in range(
    EXPECTED_ACCESS
):

    external = (
        pro
        != pro[i]
    )

    internal_other = (
        (pro == pro[i])
        &
        (
            np.arange(
                EXPECTED_ACCESS
            )
            != i
        )
    )


    out_ext = M[
        i,
        external
    ]

    in_ext = M[
        external,
        i
    ]

    out_intra = M[
        i,
        internal_other
    ]

    in_intra = M[
        internal_other,
        i
    ]


    access_summary_rows.append({
        "access_index":
            i,

        "PRO_COM":
            int(
                pro[i]
            ),

        "COMUNE":
            str(
                gamma.iloc[i][
                    "COMUNE"
                ]
            ),

        "access_order":
            int(
                orders[i]
            ),

        "structural_node_id":
            int(
                node[i]
            ),

        "candidate_rank":
            int(
                gamma.iloc[i][
                    "candidate_rank"
                ]
            ),

        "base_state_id":
            int(
                source_states[i]
            ),

        "base_state_outdegree":
            int(
                source_outdegree[i]
            ),

        "reachable_all_accesses":
            int(
                source_reachable[i]
            ),

        "reachable_external":
            int(
                np.isfinite(
                    out_ext
                ).sum()
            ),

        "reachable_internal_other":
            int(
                np.isfinite(
                    out_intra
                ).sum()
            ),

        "external_out_median_s":
            float(
                np.median(
                    out_ext
                )
            )
            if np.isfinite(
                out_ext
            ).all()
            else np.nan,

        "external_in_median_s":
            float(
                np.median(
                    in_ext
                )
            )
            if np.isfinite(
                in_ext
            ).all()
            else np.nan,

        "external_out_p95_s":
            float(
                np.percentile(
                    out_ext,
                    95,
                )
            )
            if np.isfinite(
                out_ext
            ).all()
            else np.nan,

        "external_in_p95_s":
            float(
                np.percentile(
                    in_ext,
                    95,
                )
            )
            if np.isfinite(
                in_ext
            ).all()
            else np.nan,

        "internal_out_max_s":
            float(
                np.max(
                    out_intra
                )
            )
            if np.isfinite(
                out_intra
            ).all()
            else np.nan,

        "internal_in_max_s":
            float(
                np.max(
                    in_intra
                )
            )
            if np.isfinite(
                in_intra
            ).all()
            else np.nan,
    })


access_summary = pd.DataFrame(
    access_summary_rows
)

access_summary.to_csv(
    OUT_ACCESS_SUMMARY,
    index=False,
    encoding="utf-8-sig",
)


# =============================================================================
# O. TRIPLET QA
# =============================================================================

out()
out("O. TRIPLET QA")
out("-" * 124)

triplet_rows = []


for pro_com, group in (
    access_summary
    .groupby(
        "PRO_COM",
        sort=True,
    )
):

    idxs = (
        group[
            "access_index"
        ]
        .to_numpy(
            dtype=np.int32
        )
    )


    internal_times = []

    for a in idxs:

        for b in idxs:

            if a == b:
                continue

            internal_times.append(
                M[
                    a,
                    b
                ]
            )


    internal_times = np.asarray(
        internal_times,
        dtype=float,
    )


    out_medians = (
        group[
            "external_out_median_s"
        ]
        .to_numpy(
            dtype=float
        )
    )

    in_medians = (
        group[
            "external_in_median_s"
        ]
        .to_numpy(
            dtype=float
        )
    )


    out_ratio = (
        float(
            np.max(out_medians)
            /
            np.min(out_medians)
        )
        if (
            np.isfinite(
                out_medians
            ).all()
            and np.min(
                out_medians
            ) > 0
        )
        else np.nan
    )

    in_ratio = (
        float(
            np.max(in_medians)
            /
            np.min(in_medians)
        )
        if (
            np.isfinite(
                in_medians
            ).all()
            and np.min(
                in_medians
            ) > 0
        )
        else np.nan
    )


    gamma_group = gamma[
        gamma[
            "PRO_COM"
        ] == pro_com
    ]


    triplet_rows.append({
        "PRO_COM":
            int(
                pro_com
            ),

        "COMUNE":
            str(
                gamma_group.iloc[0][
                    "COMUNE"
                ]
            ),

        "all_6_internal_reachable":
            int(
                np.isfinite(
                    internal_times
                ).all()
            ),

        "internal_time_min_s":
            float(
                np.min(
                    internal_times
                )
            )
            if np.isfinite(
                internal_times
            ).all()
            else np.nan,

        "internal_time_median_s":
            float(
                np.median(
                    internal_times
                )
            )
            if np.isfinite(
                internal_times
            ).all()
            else np.nan,

        "internal_time_max_s":
            float(
                np.max(
                    internal_times
                )
            )
            if np.isfinite(
                internal_times
            ).all()
            else np.nan,

        "external_out_median_ratio":
            out_ratio,

        "external_in_median_ratio":
            in_ratio,

        "max_candidate_rank":
            int(
                gamma_group[
                    "candidate_rank"
                ].max()
            ),

        "required_depth":
            int(
                gamma_group[
                    "required_depth"
                ].max()
            ),

        "min_pair_separation_m":
            float(
                gamma_group[
                    "min_pair_separation_m"
                ].iloc[0]
            ),
    })


triplet_summary = pd.DataFrame(
    triplet_rows
)

triplet_summary.to_csv(
    OUT_TRIPLET_SUMMARY,
    index=False,
    encoding="utf-8-sig",
)


bad_triplet_reach = int(
    (
        triplet_summary[
            "all_6_internal_reachable"
        ]
        != 1
    ).sum()
)


out(
    f"Triplette con 6/6 reach FAIL : "
    f"{bad_triplet_reach:,}"
)


out()
out(
    "Triplet external-median ratios"
)

out("-" * 124)

for col in [
    "external_out_median_ratio",
    "external_in_median_ratio",
]:

    values = (
        triplet_summary[
            col
        ]
        .dropna()
        .to_numpy(
            dtype=float
        )
    )

    out(
        f"{col:<34} "
        f"med={np.median(values):7.4f} | "
        f"p95={np.percentile(values,95):7.4f} | "
        f"max={np.max(values):7.4f}"
    )


# =============================================================================
# P. WEIGHT RECHECK
# =============================================================================

out()
out("P. EXP_REL_300 RECHECK")
out("-" * 124)

lambda_values = (
    gamma[
        "lambda_L"
    ]
    .to_numpy(
        dtype=float
    )
)

lambda_sums = (
    gamma.groupby(
        "PRO_COM"
    )[
        "lambda_L"
    ].sum()
)

nonpositive_lambda = int(
    (
        lambda_values
        <= 0
    ).sum()
)

max_lambda_error = float(
    np.max(
        np.abs(
            lambda_sums.to_numpy()
            - 1.0
        )
    )
)


out(
    f"Nonpositive lambda      : "
    f"{nonpositive_lambda:,}"
)

out(
    f"Max lambda sum error    : "
    f"{max_lambda_error:.3e}"
)


# =============================================================================
# Q. HARD GATE
# =============================================================================

out()
out("Q. E2 HARD GATE")
out("-" * 124)

issues = []


if zero_outdegree_sources.size:
    issues.append(
        (
            "GAMMA_OR_ROUTING_LOCAL",
            "SOURCE_BASE_STATE_OUTDEGREE_ZERO",
            int(
                zero_outdegree_sources.size
            ),
        )
    )


if duplicate_global_count:
    issues.append(
        (
            "GAMMA_LOCAL",
            "GLOBAL_DUPLICATE_STRUCTURAL_NODE",
            duplicate_global_count,
        )
    )


if diagonal_bad:
    issues.append(
        (
            "ROUTING_LOCAL_OR_SYSTEMIC",
            "NONZERO_DIAGONAL",
            diagonal_bad,
        )
    )


if bad_source_reach:
    issues.append(
        (
            "GAMMA_OR_ROUTING_LOCAL",
            "SOURCE_REACHABILITY",
            bad_source_reach,
        )
    )


if bad_destination_reach:
    issues.append(
        (
            "GAMMA_OR_ROUTING_LOCAL",
            "DESTINATION_REACHABILITY",
            bad_destination_reach,
        )
    )


if unreachable_inter.sum():
    issues.append(
        (
            "GAMMA_OR_ROUTING_LOCAL",
            "UNREACHABLE_INTERMUNICIPAL",
            int(
                unreachable_inter.sum()
            ),
        )
    )


if unreachable_intra.sum():
    issues.append(
        (
            "GAMMA_OR_ROUTING_LOCAL",
            "UNREACHABLE_INTRAMUNICIPAL",
            int(
                unreachable_intra.sum()
            ),
        )
    )


if zero_offdiag.sum():
    issues.append(
        (
            "GAMMA_LOCAL_OR_ROUTING",
            "ZERO_TIME_OFFDIAGONAL",
            int(
                zero_offdiag.sum()
            ),
        )
    )


if negative_time.sum():
    issues.append(
        (
            "BLOCKING",
            "NEGATIVE_TIME",
            int(
                negative_time.sum()
            ),
        )
    )


if impossible_time_count:
    issues.append(
        (
            "ROUTING_LOCAL_OR_SYSTEMIC",
            "PHYSICAL_TIME_BOUND",
            impossible_time_count,
        )
    )


if bad_triplet_reach:
    issues.append(
        (
            "GAMMA_LOCAL",
            "TRIPLET_REACHABILITY",
            bad_triplet_reach,
        )
    )


if nonpositive_lambda:
    issues.append(
        (
            "GAMMA_LOCAL",
            "NONPOSITIVE_WEIGHT",
            nonpositive_lambda,
        )
    )


if max_lambda_error > 1e-12:
    issues.append(
        (
            "GAMMA_LOCAL",
            "WEIGHT_NORMALIZATION",
            max_lambda_error,
        )
    )


for classification, name, value in issues:

    out(
        f"{classification:<28} | "
        f"{name:<40} | "
        f"{value}"
    )


# =============================================================================
# R. MANIFEST
# =============================================================================

out()
out("R. MANIFEST")
out("-" * 124)

matrix_sha = sha256(
    OUT_MATRIX
)

inter_sha = sha256(
    OUT_INTER
)


manifest = {
    "phase":
        "FASE_5_6_E2",

    "version":
        "v01",

    "created_at":
        STAMP,

    "routing":
        "B5 turn-aware TIME",

    "source_semantics":
        "base state of each Gamma access",

    "destination_semantics":
        "minimum distance across all B5 states associated with destination physical node",

    "counts": {
        "sources":
            EXPECTED_ACCESS,

        "destinations":
            EXPECTED_ACCESS,

        "full_matrix_cells":
            EXPECTED_FULL,

        "self":
            EXPECTED_ACCESS,

        "ordered_intramunicipal":
            EXPECTED_INTRA,

        "ordered_intermunicipal":
            EXPECTED_INTER,

        "ordered_offdiagonal":
            EXPECTED_OFFDIAG,
    },

    "reachability": {
        "unreachable_intermunicipal":
            int(
                unreachable_inter.sum()
            ),

        "unreachable_intramunicipal":
            int(
                unreachable_intra.sum()
            ),

        "bad_source_count":
            bad_source_reach,

        "bad_destination_count":
            bad_destination_reach,

        "bad_triplet_count":
            bad_triplet_reach,
    },

    "routing_qa": {
        "zero_outdegree_sources":
            int(
                zero_outdegree_sources.size
            ),

        "zero_time_offdiagonal":
            int(
                zero_offdiag.sum()
            ),

        "negative_time_cells":
            int(
                negative_time.sum()
            ),

        "max_core_speed_kmh":
            max_speed_kmh,

        "physical_lower_bound_violations":
            impossible_time_count,
    },

    "gamma_qa": {
        "global_duplicate_structural_node_rows":
            duplicate_global_count,

        "nonpositive_lambda":
            nonpositive_lambda,

        "max_lambda_sum_error":
            max_lambda_error,
    },

    "issues": [
        {
            "classification":
                classification,

            "issue":
                name,

            "value":
                (
                    float(value)
                    if isinstance(
                        value,
                        (np.floating, float)
                    )
                    else int(value)
                ),
        }

        for classification, name, value
        in issues
    ],

    "sha256": {
        "time_matrix":
            matrix_sha,

        "intermunicipal_pairs_csv":
            inter_sha,

        "E1_csv":
            fingerprint[
                "E1_csv_sha256"
            ],

        "B5_TIME":
            fingerprint[
                "B5_time_sha256"
            ],
    },
}


if not issues:

    manifest[
        "gate_status"
    ] = "PASS"

else:

    manifest[
        "gate_status"
    ] = "CHECK_REQUIRED"


OUT_MANIFEST.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# =============================================================================
# S. FINAL
# =============================================================================

out()
out("=" * 124)

if not issues:

    out(
        "ESITO E2: PASS"
    )

    out(
        "Gamma_OSM E1+E2 eligible for FREEZE."
    )

else:

    out(
        "ESITO E2: CHECK_REQUIRED"
    )

    out(
        "NON congelare Gamma prima della classificazione degli issue."
    )

out("=" * 124)

out(
    f"Matrix SHA256 : "
    f"{matrix_sha}"
)

out(
    f"Inter SHA256  : "
    f"{inter_sha}"
)

out(f"Matrix      : {OUT_MATRIX}")
out(f"Inter pairs : {OUT_INTER}")
out(f"Intra pairs : {OUT_INTRA}")
out(f"Access QA   : {OUT_ACCESS_SUMMARY}")
out(f"Triplet QA  : {OUT_TRIPLET_SUMMARY}")
out(f"Asymmetry   : {OUT_ASYMMETRY}")
out(f"Detour      : {OUT_DETOUR}")
out(f"Manifest    : {OUT_MANIFEST}")
out(f"LOG         : {LOG}")

out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
