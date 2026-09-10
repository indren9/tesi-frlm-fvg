# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import traceback

import numpy as np
import pandas as pd

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


# =============================================================================
# 0. CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

BACKBONE = (
    ROOT
    / "02_package"
    / "grafo_operativo_osm"
)

GAMMA_DIR = (
    ROOT
    / "02_package"
    / "accessi_comunali_osm_light"
)

WORK = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "B1_full_materialization"
)

SHARDS = WORK / "shards"

WORK.mkdir(
    parents=True,
    exist_ok=True,
)

SHARDS.mkdir(
    parents=True,
    exist_ok=True,
)


B2 = BACKBONE / "osm_directed_edges_v02.sqlite"

TIME_NPZ = (
    BACKBONE
    / "osm_turn_state_time_v01.npz"
)

LENGTH_NPZ = (
    BACKBONE
    / "osm_turn_state_length_v01.npz"
)

EDGEID_NPZ = (
    BACKBONE
    / "osm_turn_state_edgeid_v01.npz"
)

STATE_NODE_NPY = (
    BACKBONE
    / "osm_turn_state_node_id_v01.npy"
)

GAMMA_CSV = (
    GAMMA_DIR
    / "Gamma_OSM_L_comuni_fvg_v01.csv"
)

E2_NPY = (
    GAMMA_DIR
    / "Gamma_OSM_E2_time_matrix_645x645_v01.npy"
)

F3_CSV = (
    BACKBONE
    / "G_OSM_F3_access_pair_timeoptimal_v01.csv"
)


LOG = (
    WORK
    / "FASE_5_7_B1_full_materialization.txt"
)

PROGRESS_JSON = (
    WORK
    / "B1_progress_v01.json"
)

FINAL_JSON = (
    WORK
    / "B1_FULL_MATERIALIZATION_GATE_v01.json"
)


EXPECTED_HASHES = {

    B2:
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",

    TIME_NPZ:
        "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72",

    LENGTH_NPZ:
        "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2",

    EDGEID_NPZ:
        "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185",

    STATE_NODE_NPY:
        "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935",

    GAMMA_CSV:
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",

    E2_NPY:
        "b787665e7c4064cf6ec68e1905d8db5654a69aad1538919f1d0a92adafa006db",

    F3_CSV:
        "edbcc784aad11c2a1860bee8667bfabf8987fad5f6ba8665490d8557fbf90ffd",
}


SCRIPT_VERSION = "FASE_5_7_B1_v01"

N_STATES = 904_607
N_TRANSITIONS = 1_699_994

N_MUNICIPALITIES = 215
N_ACCESSES = 645

EXPECTED_PATHS_PER_ORIGIN = 1_926
EXPECTED_TOTAL_PATHS = 414_090
EXPECTED_F3_ROWS = 98_559

E2_TOL_S = 1e-9
PATH_TIME_TOL_S = 1e-7
PATH_LENGTH_TOL_M = 1e-6
PAIR_WEIGHT_TOL = 1e-12
F3_TIME_TOL_S = 1e-9
F3_LENGTH_TOL_M = 1e-6
F3_WEIGHT_TOL = 1e-12

TARGET_TIE_TOL_S = 1e-12

MIN_FREE_GB = 3.0


_lines = []


# =============================================================================
# 1. UTILITIES
# =============================================================================

def emit(msg=""):
    msg = str(msg)
    print(msg, flush=True)
    _lines.append(msg)


def hard(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256_file(
    path: Path,
    chunk_size: int = 16 * 1024 * 1024,
):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def atomic_json(
    path: Path,
    obj,
):
    tmp = Path(
        str(path) + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            obj,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def atomic_npy(
    path: Path,
    array,
):
    tmp = Path(
        str(path) + ".tmp"
    )

    with tmp.open("wb") as f:
        np.save(
            f,
            array,
            allow_pickle=False,
        )

    os.replace(
        tmp,
        path,
    )


def atomic_csv(
    path: Path,
    df: pd.DataFrame,
):
    tmp = Path(
        str(path) + ".tmp"
    )

    df.to_csv(
        tmp,
        index=False,
        encoding="utf-8-sig",
    )

    os.replace(
        tmp,
        path,
    )


def load_sparse_npz(
    path: Path,
):

    with np.load(
        path,
        allow_pickle=False,
    ) as z:

        indices = np.array(
            z["indices"],
            copy=True,
        )

        indptr = np.array(
            z["indptr"],
            copy=True,
        )

        data = np.array(
            z["data"],
            copy=True,
        )

        shape = tuple(
            int(x)
            for x in np.asarray(
                z["shape"]
            ).tolist()
        )

    return (
        indices,
        indptr,
        data,
        shape,
    )


def human_duration(seconds):

    seconds = max(
        0.0,
        float(seconds),
    )

    h = int(
        seconds // 3600
    )

    m = int(
        (seconds % 3600) // 60
    )

    s = int(
        seconds % 60
    )

    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"

    return f"{m:02d}:{s:02d}"


def shard_paths(
    origin_code,
):

    prefix = (
        f"O{int(origin_code):05d}"
    )

    return {
        "csv":
            SHARDS
            / f"{prefix}_paths_v01.csv",

        "offsets":
            SHARDS
            / f"{prefix}_offsets_v01.npy",

        "slots":
            SHARDS
            / f"{prefix}_transition_slots_v01.npy",

        "manifest":
            SHARDS
            / f"{prefix}_manifest_v01.json",
    }


def remove_shard_files(
    paths,
):

    for key in [
        "csv",
        "offsets",
        "slots",
        "manifest",
    ]:

        path = paths[key]

        if path.exists():
            path.unlink()


def validate_existing_shard(
    origin_code,
):

    paths = shard_paths(
        origin_code
    )

    manifest_path = (
        paths["manifest"]
    )

    if not manifest_path.is_file():
        return None

    try:

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        hard(
            manifest.get(
                "script_version"
            )
            == SCRIPT_VERSION,
            "script version mismatch",
        )

        hard(
            int(
                manifest[
                    "origin_PRO_COM"
                ]
            )
            == int(origin_code),
            "origin mismatch",
        )

        hard(
            manifest.get(
                "status"
            )
            == "PASS",
            "shard not PASS",
        )

        hard(
            int(
                manifest[
                    "metrics"
                ][
                    "N_paths"
                ]
            )
            == EXPECTED_PATHS_PER_ORIGIN,
            "unexpected path count",
        )

        for key in [
            "csv",
            "offsets",
            "slots",
        ]:

            p = paths[key]

            hard(
                p.is_file(),
                f"missing {p.name}",
            )

            expected = (
                manifest[
                    "files_sha256"
                ][
                    p.name
                ]
            )

            actual = sha256_file(
                p
            )

            hard(
                actual
                == expected,
                f"SHA mismatch {p.name}",
            )

        return manifest

    except Exception as exc:

        emit(
            f"  Existing shard "
            f"O{int(origin_code):05d} "
            f"is stale/invalid: {exc}"
        )

        emit(
            "  -> temporary shard "
            "will be rebuilt."
        )

        remove_shard_files(
            paths
        )

        return None


def load_b2_uv(
    sqlite_path: Path,
):

    con = sqlite3.connect(
        f"file:{sqlite_path}?mode=ro",
        uri=True,
    )

    max_edge = int(
        con.execute(
            """
            SELECT MAX(edge_id)
            FROM directed_edges
            """
        ).fetchone()[0]
    )

    n_edges = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM directed_edges
            """
        ).fetchone()[0]
    )

    u = np.full(
        max_edge + 1,
        -1,
        dtype=np.int64,
    )

    v = np.full(
        max_edge + 1,
        -1,
        dtype=np.int64,
    )

    query = """
        SELECT
            edge_id,
            u,
            v
        FROM directed_edges
        ORDER BY edge_id
    """

    for chunk in pd.read_sql_query(
        query,
        con,
        chunksize=250_000,
    ):

        ids = chunk[
            "edge_id"
        ].to_numpy(
            dtype=np.int64
        )

        u[ids] = chunk[
            "u"
        ].to_numpy(
            dtype=np.int64
        )

        v[ids] = chunk[
            "v"
        ].to_numpy(
            dtype=np.int64
        )

    con.close()

    return (
        n_edges,
        max_edge,
        u,
        v,
    )


def create_predecessor_slot_map(
    predecessors,
    csr_indices,
    slot_from_state,
    pred_slot,
):

    pred_slot.fill(
        -1
    )

    mask = (
        predecessors[
            csr_indices
        ]
        ==
        slot_from_state
    )

    selected_slots = np.flatnonzero(
        mask
    ).astype(
        np.int32,
        copy=False,
    )

    selected_children = (
        csr_indices[
            mask
        ]
    )

    pred_slot[
        selected_children
    ] = selected_slots


def reconstruct_slots(
    predecessors,
    pred_slot,
    source_state,
    target_state,
):

    current = int(
        target_state
    )

    rev_slots = []

    guard = 0

    while current != source_state:

        parent = int(
            predecessors[
                current
            ]
        )

        slot = int(
            pred_slot[
                current
            ]
        )

        if parent < 0:
            raise RuntimeError(
                "Missing predecessor: "
                f"source={source_state}, "
                f"target={target_state}, "
                f"current={current}, "
                f"pred={parent}"
            )

        if slot < 0:
            raise RuntimeError(
                "Missing predecessor transition slot: "
                f"source={source_state}, "
                f"target={target_state}, "
                f"current={current}, "
                f"parent={parent}"
            )

        rev_slots.append(
            slot
        )

        current = parent

        guard += 1

        if guard > N_STATES:
            raise RuntimeError(
                "Predecessor cycle/overflow."
            )

    hard(
        len(
            rev_slots
        )
        > 0,
        "Empty intermunicipal path.",
    )

    return np.asarray(
        rev_slots[::-1],
        dtype=np.int32,
    )


# =============================================================================
# 2. MAIN
# =============================================================================

try:

    emit(
        "=" * 124
    )

    emit(
        "FASE 5.7 — B1 — "
        "FULL SHARDED PATH MATERIALIZATION"
    )

    emit(
        "=" * 124
    )

    emit(
        f"Python  : {sys.executable}"
    )

    emit(
        f"Work    : {WORK}"
    )

    emit(
        f"Shards  : {SHARDS}"
    )


    # =========================================================================
    # A. DISK PREFLIGHT
    # =========================================================================

    emit()

    emit(
        "A. DISK PREFLIGHT"
    )

    emit(
        "-" * 124
    )

    disk = shutil.disk_usage(
        WORK
    )

    free_gb = (
        disk.free
        / 1024**3
    )

    emit(
        f"Free space = "
        f"{free_gb:.2f} GB"
    )

    hard(
        free_gb
        >= MIN_FREE_GB,
        "Less than "
        f"{MIN_FREE_GB:.1f} GB "
        "free on working volume.",
    )


    # =========================================================================
    # B. FROZEN INPUT IDENTITY
    # =========================================================================

    emit()

    emit(
        "B. FROZEN INPUT IDENTITY"
    )

    emit(
        "-" * 124
    )

    actual_hashes = {}

    for path, expected in EXPECTED_HASHES.items():

        hard(
            path.is_file(),
            f"Missing frozen input: {path}",
        )

        actual = sha256_file(
            path
        )

        actual_hashes[
            path.name
        ] = actual

        emit(
            f"{path.name:<50} "
            f"{actual}"
        )

        hard(
            actual.lower()
            == expected.lower(),
            "Frozen input SHA mismatch: "
            f"{path.name}",
        )

    emit(
        "Frozen identity = PASS"
    )


    # =========================================================================
    # C. LOAD B5
    # =========================================================================

    emit()

    emit(
        "C. LOAD B5 TIME/LENGTH/EDGEID"
    )

    emit(
        "-" * 124
    )


    (
        indices,
        indptr,
        time_data,
        shape,
    ) = load_sparse_npz(
        TIME_NPZ
    )


    (
        length_indices,
        length_indptr,
        length_data,
        length_shape,
    ) = load_sparse_npz(
        LENGTH_NPZ
    )


    (
        edge_indices,
        edge_indptr,
        edge_data,
        edge_shape,
    ) = load_sparse_npz(
        EDGEID_NPZ
    )


    hard(
        shape
        == (
            N_STATES,
            N_STATES,
        ),
        f"Unexpected B5 shape: {shape}",
    )

    hard(
        length_shape == shape,
        "LENGTH shape mismatch.",
    )

    hard(
        edge_shape == shape,
        "EDGEID shape mismatch.",
    )

    hard(
        len(
            time_data
        )
        == N_TRANSITIONS,
        "Unexpected transition count.",
    )

    hard(
        np.array_equal(
            indices,
            length_indices,
        ),
        "TIME/LENGTH indices mismatch.",
    )

    hard(
        np.array_equal(
            indices,
            edge_indices,
        ),
        "TIME/EDGEID indices mismatch.",
    )

    hard(
        np.array_equal(
            indptr,
            length_indptr,
        ),
        "TIME/LENGTH indptr mismatch.",
    )

    hard(
        np.array_equal(
            indptr,
            edge_indptr,
        ),
        "TIME/EDGEID indptr mismatch.",
    )


    edge_ids = edge_data.astype(
        np.int64,
        copy=False,
    )


    B5_TIME = csr_matrix(
        (
            time_data,
            indices,
            indptr,
        ),
        shape=shape,
        copy=False,
    )


    # We need one unique transition slot
    # for each B5 state -> state relation.
    duplicate_check = B5_TIME.copy()

    nnz_before = int(
        duplicate_check.nnz
    )

    duplicate_check.sum_duplicates()

    nnz_after = int(
        duplicate_check.nnz
    )

    del duplicate_check


    hard(
        nnz_before
        == nnz_after,
        "Duplicate B5 state-to-state "
        "transitions detected. "
        "Cannot use deterministic "
        "predecessor-slot mapping.",
    )


    slot_from_state = np.repeat(

        np.arange(
            N_STATES,
            dtype=np.int32,
        ),

        np.diff(
            indptr
        ).astype(
            np.int64,
            copy=False,
        ),

    )


    hard(
        len(
            slot_from_state
        )
        == N_TRANSITIONS,
        "slot_from_state size mismatch.",
    )


    emit(
        f"B5 states      = "
        f"{N_STATES:,}"
    )

    emit(
        f"B5 transitions = "
        f"{N_TRANSITIONS:,}"
    )

    emit(
        "Duplicate B5 state-pairs = 0"
    )


    # =========================================================================
    # D. GLOBAL B5 PHYSICAL CONTINUITY
    # =========================================================================

    emit()

    emit(
        "D. GLOBAL B5 -> B2 PHYSICAL "
        "TRANSITION CONTINUITY"
    )

    emit(
        "-" * 124
    )


    state_nodes = np.load(
        STATE_NODE_NPY,
        mmap_mode="r",
    )


    hard(
        state_nodes.shape
        == (
            N_STATES,
        ),
        "state_nodes shape mismatch.",
    )


    (
        n_b2_edges,
        max_b2_edge,
        b2_u,
        b2_v,
    ) = load_b2_uv(
        B2
    )


    hard(
        (
            edge_ids > 0
        ).all(),
        "B5 edge_id <= 0.",
    )

    hard(
        (
            edge_ids
            <= max_b2_edge
        ).all(),
        "B5 edge_id outside B2 domain.",
    )


    source_transition_mismatch = int(
        np.count_nonzero(

            b2_u[
                edge_ids
            ]

            !=

            np.asarray(
                state_nodes[
                    slot_from_state
                ]
            )

        )
    )


    destination_transition_mismatch = int(
        np.count_nonzero(

            b2_v[
                edge_ids
            ]

            !=

            np.asarray(
                state_nodes[
                    indices
                ]
            )

        )
    )


    emit(
        f"B2 directed edges         = "
        f"{n_b2_edges:,}"
    )

    emit(
        "Transition source mismatch "
        f"= {source_transition_mismatch:,}"
    )

    emit(
        "Transition destination mismatch "
        f"= {destination_transition_mismatch:,}"
    )


    hard(
        source_transition_mismatch
        == 0,
        "Global B5/B2 transition "
        "source mismatch.",
    )

    hard(
        destination_transition_mismatch
        == 0,
        "Global B5/B2 transition "
        "destination mismatch.",
    )


    emit(
        "Global physical transition "
        "continuity = PASS"
    )


    # =========================================================================
    # E. LOAD GAMMA / E2
    # =========================================================================

    emit()

    emit(
        "E. GAMMA / E2 DOMAIN"
    )

    emit(
        "-" * 124
    )


    gamma = pd.read_csv(
        GAMMA_CSV
    ).reset_index(
        drop=True
    )


    gamma[
        "access_index"
    ] = np.arange(
        len(gamma),
        dtype=np.int64,
    )


    hard(
        len(
            gamma
        )
        == N_ACCESSES,
        f"Gamma rows != {N_ACCESSES}",
    )

    hard(
        gamma[
            "PRO_COM"
        ].nunique()
        == N_MUNICIPALITIES,
        "Gamma municipalities != 215.",
    )


    for pro_com, group in gamma.groupby(
        "PRO_COM",
        sort=False,
    ):

        hard(
            len(group)
            == 3,
            f"Municipality {pro_com} "
            "does not have 3 accesses.",
        )

        hard(
            sorted(
                group[
                    "access_order"
                ].astype(int).tolist()
            )
            == [
                1,
                2,
                3,
            ],
            f"Municipality {pro_com} "
            "access_order != 1,2,3.",
        )


    hard(
        (
            gamma[
                "lambda_L"
            ]
            > 0
        ).all(),
        "Nonpositive Gamma lambda.",
    )


    lambda_max_error = float(

        (
            gamma
            .groupby(
                "PRO_COM"
            )[
                "lambda_L"
            ]
            .sum()
            - 1.0
        )
        .abs()
        .max()

    )


    hard(
        lambda_max_error
        <= PAIR_WEIGHT_TOL,
        "Gamma lambda sums "
        "do not equal 1.",
    )


    e2 = np.load(
        E2_NPY,
        mmap_mode="r",
    )


    hard(
        e2.shape
        == (
            N_ACCESSES,
            N_ACCESSES,
        ),
        "Unexpected E2 shape.",
    )

    hard(
        np.isfinite(
            e2
        ).all(),
        "E2 contains non-finite values.",
    )


    origin_codes = (
        gamma[
            "PRO_COM"
        ]
        .drop_duplicates()
        .astype(int)
        .tolist()
    )


    hard(
        len(
            origin_codes
        )
        == N_MUNICIPALITIES,
        "Unexpected origin municipality count.",
    )


    # Destination state groups.
    target_physical_nodes = set(
        int(x)
        for x in gamma[
            "structural_node_id"
        ].tolist()
    )


    destination_states = {
        node: []
        for node
        in target_physical_nodes
    }


    for state_id, physical_node in enumerate(
        np.asarray(
            state_nodes
        )
    ):

        physical_node = int(
            physical_node
        )

        if physical_node in destination_states:

            destination_states[
                physical_node
            ].append(
                state_id
            )


    for node, states in destination_states.items():

        hard(
            len(states) > 0,
            "No B5 destination state "
            f"for physical node {node}",
        )


    destination_state_counts = np.array(
        [
            len(
                destination_states[
                    int(node)
                ]
            )
            for node
            in gamma[
                "structural_node_id"
            ]
        ],
        dtype=np.int64,
    )


    emit(
        f"Municipalities             = "
        f"{len(origin_codes):,}"
    )

    emit(
        f"Accesses                   = "
        f"{len(gamma):,}"
    )

    emit(
        "Destination states min/med/max "
        f"= {destination_state_counts.min()} / "
        f"{np.median(destination_state_counts):.1f} / "
        f"{destination_state_counts.max()}"
    )

    emit(
        "Gamma lambda max sum error "
        f"= {lambda_max_error:.3e}"
    )


    # =========================================================================
    # F. LOAD FULL F3 REFERENCE
    # =========================================================================

    emit()

    emit(
        "F. FULL F3 REFERENCE"
    )

    emit(
        "-" * 124
    )


    # F3 reader: same robust semantics already validated in A1.
    # First try the standard CSV parser; if the file is interpreted
    # as one column, reload it as a semicolon-separated file.
    # F3 reader: same robust semantics already validated in A1.
    # First try the standard CSV parser; if the file is interpreted
    # as one column, reload it as a semicolon-separated file.
    f3 = pd.read_csv(
        F3_CSV,
        low_memory=False,
    )

    if len(f3.columns) == 1:

        f3 = pd.read_csv(
            F3_CSV,
            sep=";",
            low_memory=False,
        )

    # Defensive normalization of header names.
    f3.columns = [
        str(col)
        .replace("\ufeff", "")
        .strip()
        for col in f3.columns
    ]

    emit(
        f"F3 detected columns = "
        f"{list(f3.columns)}"
    )

    if len(f3.columns) == 1:

        f3 = pd.read_csv(
            F3_CSV,
            sep=";",
            low_memory=False,
        )

    # Defensive normalization of header names.
    f3.columns = [
        str(col)
        .replace("\ufeff", "")
        .strip()
        for col in f3.columns
    ]

    emit(
        f"F3 detected columns = "
        f"{list(f3.columns)}"
    )


    hard(
        len(
            f3
        )
        == EXPECTED_F3_ROWS,
        "Unexpected F3 row count: "
        f"{len(f3)}",
    )


    required_f3 = [
        "origin_PRO_COM",
        "destination_PRO_COM",
        "origin_access_order",
        "destination_access_order",
        "pair_weight",
        "time_s",
        "distance_m",
        "target_state",
        "path_state_edges",
    ]


    for col in required_f3:

        hard(
            col in f3.columns,
            f"F3 missing column {col}",
        )


    f3_reference = {}


    for row in f3.itertuples(
        index=False
    ):

        key = (
            int(
                row.origin_PRO_COM
            ),
            int(
                row.destination_PRO_COM
            ),
            int(
                row.origin_access_order
            ),
            int(
                row.destination_access_order
            ),
        )

        hard(
            key not in f3_reference,
            f"Duplicate F3 key {key}",
        )

        f3_reference[
            key
        ] = {
            "pair_weight":
                float(
                    row.pair_weight
                ),

            "time_s":
                float(
                    row.time_s
                ),

            "distance_m":
                float(
                    row.distance_m
                ),

            "target_state":
                int(
                    row.target_state
                ),

            "path_state_edges":
                int(
                    row.path_state_edges
                ),
        }


    hard(
        len(
            f3_reference
        )
        == EXPECTED_F3_ROWS,
        "F3 key cardinality mismatch.",
    )


    emit(
        f"F3 reference paths = "
        f"{len(f3_reference):,}"
    )


    # =========================================================================
    # G. FULL MATERIALIZATION
    # =========================================================================

    emit()

    emit(
        "G. FULL MATERIALIZATION — "
        "215 RESUMABLE ORIGIN SHARDS"
    )

    emit(
        "-" * 124
    )


    start_all = time.perf_counter()

    pred_slot = np.full(
        N_STATES,
        -1,
        dtype=np.int32,
    )


    shard_manifests = []


    for origin_pos, origin_code in enumerate(
        origin_codes,
        start=1,
    ):

        origin_start = time.perf_counter()

        origin_code = int(
            origin_code
        )


        existing = validate_existing_shard(
            origin_code
        )


        if existing is not None:

            shard_manifests.append(
                existing
            )

            emit(
                f"[{origin_pos:03d}/"
                f"{N_MUNICIPALITIES}] "
                f"O{origin_code:05d} "
                "VALID SHARD -> SKIP"
            )

            continue


        paths = shard_paths(
            origin_code
        )


        source_rows = (

            gamma[
                gamma[
                    "PRO_COM"
                ]
                == origin_code
            ]

            .sort_values(
                "access_order"
            )

        )


        hard(
            len(
                source_rows
            )
            == 3,
            "Origin access count != 3.",
        )


        destination_rows = gamma[
            gamma[
                "PRO_COM"
            ]
            != origin_code
        ]


        hard(
            len(
                destination_rows
            )
            == 642,
            "Destination access count != 642.",
        )


        records = []

        offsets = [
            0
        ]

        sequence_parts = []

        local_slot_count = 0

        n_finite = 0
        n_unreachable = 0
        n_reconstruction_failures = 0

        max_e2_error = 0.0
        max_time_reconstruction_error = 0.0

        tie_paths = 0
        extra_tie_states = 0

        f3_matched = 0

        f3_max_time_error = 0.0
        f3_max_distance_error = 0.0
        f3_max_weight_error = 0.0

        f3_target_state_mismatch = 0
        f3_transition_count_mismatch = 0


        for source_row in source_rows.itertuples(
            index=False
        ):

            source_access_index = int(
                source_row.access_index
            )

            source_state = int(
                source_row.base_state_id
            )

            origin_node = int(
                source_row.structural_node_id
            )

            origin_access_order = int(
                source_row.access_order
            )

            lambda_origin = float(
                source_row.lambda_L
            )


            hard(
                int(
                    state_nodes[
                        source_state
                    ]
                )
                == origin_node,
                "Source state physical-node mismatch.",
            )


            (
                distances,
                predecessors,
            ) = dijkstra(
                B5_TIME,
                directed=True,
                indices=source_state,
                return_predecessors=True,
            )


            create_predecessor_slot_map(
                predecessors,
                indices,
                slot_from_state,
                pred_slot,
            )


            for dest_row in destination_rows.itertuples(
                index=False
            ):

                destination_access_index = int(
                    dest_row.access_index
                )

                destination_code = int(
                    dest_row.PRO_COM
                )

                destination_access_order = int(
                    dest_row.access_order
                )

                destination_node = int(
                    dest_row.structural_node_id
                )

                lambda_destination = float(
                    dest_row.lambda_L
                )


                candidate_states = np.asarray(
                    destination_states[
                        destination_node
                    ],
                    dtype=np.int64,
                )


                candidate_costs = np.asarray(
                    distances[
                        candidate_states
                    ],
                    dtype=np.float64,
                )


                best_time = float(
                    np.min(
                        candidate_costs
                    )
                )


                if not np.isfinite(
                    best_time
                ):

                    n_unreachable += 1

                    raise RuntimeError(
                        "Unreachable intermunicipal "
                        "access pair: "
                        f"{origin_code}/"
                        f"{origin_access_order} -> "
                        f"{destination_code}/"
                        f"{destination_access_order}"
                    )


                n_finite += 1


                equal_states = candidate_states[

                    np.abs(
                        candidate_costs
                        - best_time
                    )
                    <= TARGET_TIE_TOL_S

                ]


                hard(
                    len(
                        equal_states
                    )
                    >= 1,
                    "No destination state selected.",
                )


                destination_state = int(
                    np.min(
                        equal_states
                    )
                )


                if len(
                    equal_states
                ) > 1:

                    tie_paths += 1

                    extra_tie_states += (
                        len(
                            equal_states
                        )
                        - 1
                    )


                e2_reference = float(
                    e2[
                        source_access_index,
                        destination_access_index,
                    ]
                )


                e2_error = abs(
                    best_time
                    - e2_reference
                )


                max_e2_error = max(
                    max_e2_error,
                    e2_error,
                )


                hard(
                    e2_error
                    <= E2_TOL_S,
                    "B5/E2 mismatch: "
                    f"{origin_code}/"
                    f"{origin_access_order} -> "
                    f"{destination_code}/"
                    f"{destination_access_order}, "
                    f"error={e2_error}",
                )


                try:

                    slots = reconstruct_slots(
                        predecessors,
                        pred_slot,
                        source_state,
                        destination_state,
                    )

                except Exception:

                    n_reconstruction_failures += 1
                    raise


                reconstructed_time = float(
                    np.sum(
                        time_data[
                            slots
                        ],
                        dtype=np.float64,
                    )
                )


                distance_m = float(
                    np.sum(
                        length_data[
                            slots
                        ],
                        dtype=np.float64,
                    )
                )


                time_reconstruction_error = abs(
                    reconstructed_time
                    - best_time
                )


                max_time_reconstruction_error = max(
                    max_time_reconstruction_error,
                    time_reconstruction_error,
                )


                hard(
                    time_reconstruction_error
                    <= PATH_TIME_TOL_S,
                    "Path time reconstruction mismatch: "
                    f"{time_reconstruction_error}",
                )


                hard(
                    best_time > 0,
                    "Non-positive intermunicipal time.",
                )

                hard(
                    distance_m > 0,
                    "Non-positive intermunicipal distance.",
                )


                hard(
                    int(
                        state_nodes[
                            destination_state
                        ]
                    )
                    == destination_node,
                    "Destination physical-node mismatch.",
                )


                pair_weight = (
                    lambda_origin
                    *
                    lambda_destination
                )


                hard(
                    pair_weight > 0,
                    "Non-positive pair_weight.",
                )


                key = (
                    origin_code,
                    destination_code,
                    origin_access_order,
                    destination_access_order,
                )


                f3_ref = f3_reference.get(
                    key
                )


                if f3_ref is not None:

                    f3_matched += 1

                    f3_time_error = abs(
                        best_time
                        - f3_ref[
                            "time_s"
                        ]
                    )

                    f3_distance_error = abs(
                        distance_m
                        - f3_ref[
                            "distance_m"
                        ]
                    )

                    f3_weight_error = abs(
                        pair_weight
                        - f3_ref[
                            "pair_weight"
                        ]
                    )


                    f3_max_time_error = max(
                        f3_max_time_error,
                        f3_time_error,
                    )

                    f3_max_distance_error = max(
                        f3_max_distance_error,
                        f3_distance_error,
                    )

                    f3_max_weight_error = max(
                        f3_max_weight_error,
                        f3_weight_error,
                    )


                    if (
                        destination_state
                        != f3_ref[
                            "target_state"
                        ]
                    ):

                        f3_target_state_mismatch += 1


                    if (
                        len(
                            slots
                        )
                        != f3_ref[
                            "path_state_edges"
                        ]
                    ):

                        f3_transition_count_mismatch += 1


                    hard(
                        f3_time_error
                        <= F3_TIME_TOL_S,
                        "F3 time regression mismatch.",
                    )

                    hard(
                        f3_distance_error
                        <= F3_LENGTH_TOL_M,
                        "F3 distance regression mismatch.",
                    )

                    hard(
                        f3_weight_error
                        <= F3_WEIGHT_TOL,
                        "F3 pair-weight mismatch.",
                    )


                path_id = (

                    f"GOSM_v01|GAMMA_v01|"
                    f"O{origin_code:05d}:A"
                    f"{origin_access_order}|"
                    f"D{destination_code:05d}:A"
                    f"{destination_access_order}"

                )


                start_local = int(
                    local_slot_count
                )

                local_slot_count += int(
                    len(
                        slots
                    )
                )

                end_local = int(
                    local_slot_count
                )


                sequence_parts.append(
                    slots
                )

                offsets.append(
                    end_local
                )


                records.append(
                    {
                        "path_id":
                            path_id,

                        "origin_PRO_COM":
                            origin_code,

                        "origin_COMUNE":
                            str(
                                source_row.COMUNE
                            ),

                        "destination_PRO_COM":
                            destination_code,

                        "destination_COMUNE":
                            str(
                                dest_row.COMUNE
                            ),

                        "origin_access_index":
                            source_access_index,

                        "destination_access_index":
                            destination_access_index,

                        "origin_access_order":
                            origin_access_order,

                        "destination_access_order":
                            destination_access_order,

                        "origin_structural_node_id":
                            origin_node,

                        "destination_structural_node_id":
                            destination_node,

                        "source_state":
                            source_state,

                        "destination_state":
                            destination_state,

                        "destination_state_tie_count":
                            int(
                                len(
                                    equal_states
                                )
                            ),

                        "lambda_origin":
                            lambda_origin,

                        "lambda_destination":
                            lambda_destination,

                        "pair_weight":
                            pair_weight,

                        "time_s":
                            best_time,

                        "distance_m":
                            distance_m,

                        "n_physical_edges":
                            int(
                                len(
                                    slots
                                )
                            ),

                        "n_B5_transitions":
                            int(
                                len(
                                    slots
                                )
                            ),

                        "sequence_start_local":
                            start_local,

                        "sequence_end_local":
                            end_local,

                        "E2_time_reference_s":
                            e2_reference,

                        "E2_time_abs_error_s":
                            e2_error,

                        "status":
                            "FINITE_RECONSTRUCTED",
                    }
                )


        # =====================================================================
        # SHARD QA
        # =====================================================================

        df = pd.DataFrame(
            records
        )


        hard(
            len(
                df
            )
            == EXPECTED_PATHS_PER_ORIGIN,
            "Shard path count != 1926.",
        )


        hard(
            df[
                "path_id"
            ].nunique()
            == EXPECTED_PATHS_PER_ORIGIN,
            "Duplicate path_id in shard.",
        )


        hard(
            n_finite
            == EXPECTED_PATHS_PER_ORIGIN,
            "Finite paths != 1926.",
        )

        hard(
            n_unreachable == 0,
            "Unreachable paths > 0.",
        )

        hard(
            n_reconstruction_failures == 0,
            "Reconstruction failures > 0.",
        )


        pair_weight_sums = (

            df.groupby(
                [
                    "origin_PRO_COM",
                    "destination_PRO_COM",
                ],
                sort=False,
            )[
                "pair_weight"
            ]
            .sum()

        )


        hard(
            len(
                pair_weight_sums
            )
            == 214,
            "Municipal OD count "
            "inside shard != 214.",
        )


        pair_weight_max_error = float(

            (
                pair_weight_sums
                - 1.0
            )
            .abs()
            .max()

        )


        hard(
            pair_weight_max_error
            <= PAIR_WEIGHT_TOL,
            "PRODUCT-LAMBDA sum "
            "error exceeds tolerance.",
        )


        offsets_arr = np.asarray(
            offsets,
            dtype=np.int64,
        )


        hard(
            len(
                offsets_arr
            )
            == (
                EXPECTED_PATHS_PER_ORIGIN
                + 1
            ),
            "Local offsets size mismatch.",
        )


        hard(
            (
                np.diff(
                    offsets_arr
                )
                > 0
            ).all(),
            "Non-positive path sequence length.",
        )


        if sequence_parts:

            slots_arr = np.concatenate(
                sequence_parts
            ).astype(
                np.int32,
                copy=False,
            )

        else:

            slots_arr = np.empty(
                0,
                dtype=np.int32,
            )


        hard(
            int(
                offsets_arr[
                    -1
                ]
            )
            == len(
                slots_arr
            ),
            "Offsets / sequence-array mismatch.",
        )


        hard(
            (
                slots_arr >= 0
            ).all(),
            "Negative transition slot.",
        )

        hard(
            (
                slots_arr
                < N_TRANSITIONS
            ).all(),
            "Transition slot outside B5 domain.",
        )


        # =====================================================================
        # WRITE SHARD ATOMICALLY
        # =====================================================================

        atomic_csv(
            paths[
                "csv"
            ],
            df,
        )

        atomic_npy(
            paths[
                "offsets"
            ],
            offsets_arr,
        )

        atomic_npy(
            paths[
                "slots"
            ],
            slots_arr,
        )


        files_sha = {

            paths[
                "csv"
            ].name:
                sha256_file(
                    paths[
                        "csv"
                    ]
                ),

            paths[
                "offsets"
            ].name:
                sha256_file(
                    paths[
                        "offsets"
                    ]
                ),

            paths[
                "slots"
            ].name:
                sha256_file(
                    paths[
                        "slots"
                    ]
                ),
        }


        shard_manifest = {
            "script_version":
                SCRIPT_VERSION,

            "phase":
                "FASE_5_7_B1",

            "status":
                "PASS",

            "origin_PRO_COM":
                origin_code,

            "origin_COMUNE":
                str(
                    source_rows.iloc[
                        0
                    ][
                        "COMUNE"
                    ]
                ),

            "cost_contract":
                "TIME_B5",

            "distance_semantics":
                "PATH_ATTRIBUTE_SUM_B5_LENGTH",

            "sequence_representation":
                (
                    "ordered B5 CSR transition_slot "
                    "indices; local path slicing "
                    "defined by offsets"
                ),

            "metrics": {
                "N_paths":
                    int(
                        len(
                            df
                        )
                    ),

                "N_municipal_OD":
                    214,

                "N_finite":
                    int(
                        n_finite
                    ),

                "N_unreachable":
                    int(
                        n_unreachable
                    ),

                "path_reconstruction_failures":
                    int(
                        n_reconstruction_failures
                    ),

                "N_transition_slots":
                    int(
                        len(
                            slots_arr
                        )
                    ),

                "max_E2_time_abs_error_s":
                    float(
                        max_e2_error
                    ),

                "max_path_time_reconstruction_error_s":
                    float(
                        max_time_reconstruction_error
                    ),

                "pair_weight_max_sum_error":
                    float(
                        pair_weight_max_error
                    ),

                "destination_state_tie_paths":
                    int(
                        tie_paths
                    ),

                "destination_state_extra_ties":
                    int(
                        extra_tie_states
                    ),

                "F3_matched_paths":
                    int(
                        f3_matched
                    ),

                "F3_max_time_abs_error_s":
                    float(
                        f3_max_time_error
                    ),

                "F3_max_distance_abs_error_m":
                    float(
                        f3_max_distance_error
                    ),

                "F3_max_pair_weight_abs_error":
                    float(
                        f3_max_weight_error
                    ),

                "F3_target_state_mismatches":
                    int(
                        f3_target_state_mismatch
                    ),

                "F3_transition_count_mismatches":
                    int(
                        f3_transition_count_mismatch
                    ),
            },

            "files_sha256":
                files_sha,

            "frozen_inputs_sha256":
                actual_hashes,
        }


        atomic_json(
            paths[
                "manifest"
            ],
            shard_manifest,
        )


        shard_manifests.append(
            shard_manifest
        )


        elapsed_origin = (
            time.perf_counter()
            - origin_start
        )

        elapsed_all = (
            time.perf_counter()
            - start_all
        )


        completed = int(
            origin_pos
        )


        avg_per_origin = (
            elapsed_all
            / max(
                1,
                completed
            )
        )


        eta = (
            avg_per_origin
            * (
                N_MUNICIPALITIES
                - completed
            )
        )


        emit(
            f"[{origin_pos:03d}/"
            f"{N_MUNICIPALITIES}] "
            f"O{origin_code:05d} PASS | "
            f"paths={len(df):,} | "
            f"slots={len(slots_arr):,} | "
            f"ties={tie_paths:,} | "
            f"F3={f3_matched:,} | "
            f"run={human_duration(elapsed_origin)} | "
            f"ETA~{human_duration(eta)}"
        )


        atomic_json(
            PROGRESS_JSON,
            {
                "script_version":
                    SCRIPT_VERSION,

                "status":
                    "RUNNING",

                "completed_origin_position":
                    int(
                        origin_pos
                    ),

                "completed_origin_PRO_COM":
                    origin_code,

                "completed_shards_in_this_run":
                    int(
                        len(
                            shard_manifests
                        )
                    ),

                "elapsed_seconds":
                    float(
                        elapsed_all
                    ),

                "estimated_remaining_seconds":
                    float(
                        eta
                    ),
            },
        )


    # =========================================================================
    # H. RELOAD / VALIDATE ALL 215 SHARDS
    # =========================================================================

    emit()

    emit(
        "H. GLOBAL SHARD VALIDATION"
    )

    emit(
        "-" * 124
    )


    all_manifests = []


    for origin_code in origin_codes:

        manifest = validate_existing_shard(
            origin_code
        )

        hard(
            manifest is not None,
            "Missing final valid shard "
            f"for O{int(origin_code):05d}",
        )

        all_manifests.append(
            manifest
        )


    total_paths = sum(
        int(
            m[
                "metrics"
            ][
                "N_paths"
            ]
        )
        for m
        in all_manifests
    )


    total_municipal_od = sum(
        int(
            m[
                "metrics"
            ][
                "N_municipal_OD"
            ]
        )
        for m
        in all_manifests
    )


    total_finite = sum(
        int(
            m[
                "metrics"
            ][
                "N_finite"
            ]
        )
        for m
        in all_manifests
    )


    total_unreachable = sum(
        int(
            m[
                "metrics"
            ][
                "N_unreachable"
            ]
        )
        for m
        in all_manifests
    )


    total_reconstruction_failures = sum(
        int(
            m[
                "metrics"
            ][
                "path_reconstruction_failures"
            ]
        )
        for m
        in all_manifests
    )


    total_slots = sum(
        int(
            m[
                "metrics"
            ][
                "N_transition_slots"
            ]
        )
        for m
        in all_manifests
    )


    max_e2_error_global = max(
        float(
            m[
                "metrics"
            ][
                "max_E2_time_abs_error_s"
            ]
        )
        for m
        in all_manifests
    )


    max_reconstruction_error_global = max(
        float(
            m[
                "metrics"
            ][
                "max_path_time_reconstruction_error_s"
            ]
        )
        for m
        in all_manifests
    )


    max_pair_weight_error_global = max(
        float(
            m[
                "metrics"
            ][
                "pair_weight_max_sum_error"
            ]
        )
        for m
        in all_manifests
    )


    total_tie_paths = sum(
        int(
            m[
                "metrics"
            ][
                "destination_state_tie_paths"
            ]
        )
        for m
        in all_manifests
    )


    total_extra_ties = sum(
        int(
            m[
                "metrics"
            ][
                "destination_state_extra_ties"
            ]
        )
        for m
        in all_manifests
    )


    total_f3_matched = sum(
        int(
            m[
                "metrics"
            ][
                "F3_matched_paths"
            ]
        )
        for m
        in all_manifests
    )


    global_f3_time_error = max(
        float(
            m[
                "metrics"
            ][
                "F3_max_time_abs_error_s"
            ]
        )
        for m
        in all_manifests
    )


    global_f3_distance_error = max(
        float(
            m[
                "metrics"
            ][
                "F3_max_distance_abs_error_m"
            ]
        )
        for m
        in all_manifests
    )


    global_f3_weight_error = max(
        float(
            m[
                "metrics"
            ][
                "F3_max_pair_weight_abs_error"
            ]
        )
        for m
        in all_manifests
    )


    total_f3_target_mismatch = sum(
        int(
            m[
                "metrics"
            ][
                "F3_target_state_mismatches"
            ]
        )
        for m
        in all_manifests
    )


    total_f3_transition_mismatch = sum(
        int(
            m[
                "metrics"
            ][
                "F3_transition_count_mismatches"
            ]
        )
        for m
        in all_manifests
    )


    hard(
        len(
            all_manifests
        )
        == N_MUNICIPALITIES,
        "Valid shard count != 215.",
    )

    hard(
        total_paths
        == EXPECTED_TOTAL_PATHS,
        "Global path count != 414090.",
    )

    hard(
        total_municipal_od
        == 46_010,
        "Global municipal OD count != 46010.",
    )

    hard(
        total_finite
        == EXPECTED_TOTAL_PATHS,
        "Global finite count != 414090.",
    )

    hard(
        total_unreachable == 0,
        "Global unreachable > 0.",
    )

    hard(
        total_reconstruction_failures
        == 0,
        "Global reconstruction failures > 0.",
    )

    hard(
        max_e2_error_global
        <= E2_TOL_S,
        "Global B5/E2 error exceeds tolerance.",
    )

    hard(
        max_pair_weight_error_global
        <= PAIR_WEIGHT_TOL,
        "Global PRODUCT-LAMBDA error "
        "exceeds tolerance.",
    )

    hard(
        total_f3_matched
        == EXPECTED_F3_ROWS,
        "Not all F3 paths were matched: "
        f"{total_f3_matched} / "
        f"{EXPECTED_F3_ROWS}",
    )

    hard(
        global_f3_time_error
        <= F3_TIME_TOL_S,
        "Full F3 time regression failed.",
    )

    hard(
        global_f3_distance_error
        <= F3_LENGTH_TOL_M,
        "Full F3 distance regression failed.",
    )

    hard(
        global_f3_weight_error
        <= F3_WEIGHT_TOL,
        "Full F3 pair-weight regression failed.",
    )

    hard(
        total_f3_target_mismatch
        == 0,
        "F3 target-state mismatches > 0.",
    )

    hard(
        total_f3_transition_mismatch
        == 0,
        "F3 path transition-count "
        "mismatches > 0.",
    )


    total_elapsed = (
        time.perf_counter()
        - start_all
    )


    emit(
        f"Valid origin shards             = "
        f"{len(all_manifests):,}"
    )

    emit(
        f"Municipal OD                    = "
        f"{total_municipal_od:,}"
    )

    emit(
        f"Access-pair paths               = "
        f"{total_paths:,}"
    )

    emit(
        f"Finite                          = "
        f"{total_finite:,}"
    )

    emit(
        f"Unreachable                     = "
        f"{total_unreachable:,}"
    )

    emit(
        f"Reconstruction failures         = "
        f"{total_reconstruction_failures:,}"
    )

    emit(
        f"Total stored B5 transition slots= "
        f"{total_slots:,}"
    )

    emit(
        f"Max B5 -> E2 error              = "
        f"{max_e2_error_global:.3e} s"
    )

    emit(
        f"Max path reconstruction error   = "
        f"{max_reconstruction_error_global:.3e} s"
    )

    emit(
        f"PRODUCT-LAMBDA max OD sum error = "
        f"{max_pair_weight_error_global:.3e}"
    )

    emit(
        f"Destination-state tie paths     = "
        f"{total_tie_paths:,}"
    )

    emit(
        f"Extra equal-cost target states  = "
        f"{total_extra_ties:,}"
    )

    emit(
        f"Full F3 matched paths           = "
        f"{total_f3_matched:,} / "
        f"{EXPECTED_F3_ROWS:,}"
    )

    emit(
        f"Full F3 max time error          = "
        f"{global_f3_time_error:.3e} s"
    )

    emit(
        f"Full F3 max distance error      = "
        f"{global_f3_distance_error:.3e} m"
    )

    emit(
        f"Full F3 max pair-weight error   = "
        f"{global_f3_weight_error:.3e}"
    )

    emit(
        f"Full F3 target-state mismatch   = "
        f"{total_f3_target_mismatch:,}"
    )

    emit(
        f"Full F3 transition mismatch     = "
        f"{total_f3_transition_mismatch:,}"
    )

    emit(
        f"Elapsed                         = "
        f"{human_duration(total_elapsed)}"
    )


    # =========================================================================
    # I. TEMPORARY B1 GATE MANIFEST
    # =========================================================================

    final_gate = {
        "phase":
            "FASE_5_7_B1",

        "script_version":
            SCRIPT_VERSION,

        "verdict":
            "PASS",

        "cost_contract":
            "TIME_B5",

        "distance":
            "PATH_ATTRIBUTE",

        "storage_architecture":
            (
                "215 resumable origin-municipality "
                "shards; each shard stores path CSV, "
                "local CSR-style offsets and ordered "
                "B5 transition_slot array"
            ),

        "counts": {
            "N_origin_shards":
                int(
                    len(
                        all_manifests
                    )
                ),

            "N_municipal_OD":
                int(
                    total_municipal_od
                ),

            "N_access_pair_paths":
                int(
                    total_paths
                ),

            "N_finite":
                int(
                    total_finite
                ),

            "N_unreachable":
                int(
                    total_unreachable
                ),

            "path_reconstruction_failures":
                int(
                    total_reconstruction_failures
                ),

            "N_stored_transition_slots":
                int(
                    total_slots
                ),
        },

        "qa": {
            "B5_B2_global_transition_source_mismatch":
                int(
                    source_transition_mismatch
                ),

            "B5_B2_global_transition_destination_mismatch":
                int(
                    destination_transition_mismatch
                ),

            "max_B5_E2_error_s":
                float(
                    max_e2_error_global
                ),

            "max_path_time_reconstruction_error_s":
                float(
                    max_reconstruction_error_global
                ),

            "PRODUCT_LAMBDA_max_OD_sum_error":
                float(
                    max_pair_weight_error_global
                ),

            "destination_state_tie_paths":
                int(
                    total_tie_paths
                ),

            "destination_state_extra_ties":
                int(
                    total_extra_ties
                ),

            "F3_matched_paths":
                int(
                    total_f3_matched
                ),

            "F3_max_time_error_s":
                float(
                    global_f3_time_error
                ),

            "F3_max_distance_error_m":
                float(
                    global_f3_distance_error
                ),

            "F3_max_pair_weight_error":
                float(
                    global_f3_weight_error
                ),

            "F3_target_state_mismatches":
                int(
                    total_f3_target_mismatch
                ),

            "F3_transition_count_mismatches":
                int(
                    total_f3_transition_mismatch
                ),
        },

        "frozen_inputs_sha256":
            actual_hashes,

        "SYSTEMIC_issues":
            0,

        "BLOCKING_issues":
            0,

        "note":
            (
                "B1 is not the final Fase 5.7 freeze. "
                "Canonical consolidation, municipal "
                "summary, explicit F1 SHADOW regression "
                "and final package manifest remain."
            ),
    }


    atomic_json(
        FINAL_JSON,
        final_gate,
    )


    atomic_json(
        PROGRESS_JSON,
        {
            "script_version":
                SCRIPT_VERSION,

            "status":
                "PASS_COMPLETE",

            "completed_origin_shards":
                N_MUNICIPALITIES,

            "N_access_pair_paths":
                total_paths,

            "N_transition_slots":
                total_slots,

            "elapsed_seconds":
                float(
                    total_elapsed
                ),
        },
    )


    # =========================================================================
    # FINAL
    # =========================================================================

    emit()

    emit(
        "=" * 124
    )

    emit(
        "B1 FULL MATERIALIZATION RESULT = PASS"
    )

    emit(
        "414,090 / 414,090 ACCESS-PAIR PATHS = FINITE"
    )

    emit(
        "PATH RECONSTRUCTION = 100%"
    )

    emit(
        "PRODUCT-LAMBDA CONSISTENCY = PASS"
    )

    emit(
        "B5 TRANSITION INTEGRITY = PASS"
    )

    emit(
        "FULL F3 REGRESSION = PASS"
    )

    emit(
        "SYSTEMIC issues = 0"
    )

    emit(
        "BLOCKING issues = 0"
    )

    emit(
        "NOTE: OD_PATH_SYSTEM_OSM is NOT frozen yet."
    )

    emit(
        "Next gate: canonical consolidation + "
        "municipal summary + F1 SHADOW regression."
    )

    emit(
        "=" * 124
    )

    emit()

    emit(
        "=== RUN COMPLETATA CORRETTAMENTE ==="
    )


except Exception as exc:

    emit()

    emit(
        "=" * 124
    )

    emit(
        "B1 FULL MATERIALIZATION RESULT = "
        "FAIL / BLOCKING CANDIDATE"
    )

    emit(
        f"{type(exc).__name__}: {exc}"
    )

    emit(
        "Completed valid municipality shards "
        "remain resumable."
    )

    emit(
        "Do NOT modify B5, Gamma or E2."
    )

    emit(
        "Do NOT start B2."
    )

    emit(
        "=" * 124
    )

    emit()

    emit(
        "=== RUN TERMINATA CON ERRORE ==="
    )

    traceback.print_exc()

    raise


finally:

    LOG.write_text(
        "\n".join(
            _lines
        ),
        encoding="utf-8",
    )

    print(
        f"\nLog salvato in:\n{LOG}"
    )



