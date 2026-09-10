# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3
import sys
import traceback

import numpy as np
import pandas as pd

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


# =============================================================================
# 0. CONFIGURAZIONE
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

OUT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "A1_cost_contract"
)

OUT.mkdir(
    parents=True,
    exist_ok=True,
)


B2 = (
    BACKBONE
    / "osm_directed_edges_v02.sqlite"
)

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

BASE_NODES_NPY = (
    BACKBONE
    / "osm_turn_state_base_nodes_v01.npy"
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
    OUT
    / "FASE_5_7_A1_cost_contract_regression.txt"
)

SAMPLE_CSV = (
    OUT
    / "A1_F3_path_regression_sample_v01.csv"
)


EXPECTED = {

    B2:
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",

    TIME_NPZ:
        "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72",

    LENGTH_NPZ:
        "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2",

    EDGEID_NPZ:
        "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185",

    BASE_NODES_NPY:
        "de02faa32628af6099118e08bd3e13847fbb0330d1aa7d824df47220b2f947d7",

    STATE_NODE_NPY:
        "0468f8f3ba1352a1a7b4998059bf2cf18cf0f52b3489aacec42cb9661fde4935",

    GAMMA_CSV:
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",

    E2_NPY:
        "b787665e7c4064cf6ec68e1905d8db5654a69aad1538919f1d0a92adafa006db",

    F3_CSV:
        "edbcc784aad11c2a1860bee8667bfabf8987fad5f6ba8665490d8557fbf90ffd",
}


N_BASE = 897_857
N_STATES = 904_607
N_TRANSITIONS = 1_699_994

N_GAMMA = 645
N_MUNICIPALITIES = 215

N_F3_ACCESS_PAIRS = 98_559

FLOAT_TOL = 1e-9


_lines = []


# =============================================================================
# 1. UTILITÀ
# =============================================================================

def emit(msg=""):
    msg = str(msg)
    print(msg)
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


def load_sparse_npz(path: Path):

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


def read_csv_auto(path: Path):

    df = pd.read_csv(
        path,
        low_memory=False,
    )

    if len(df.columns) == 1:

        df = pd.read_csv(
            path,
            sep=";",
            low_memory=False,
        )

    return df


def find_transition_slot(
    indptr,
    indices,
    u,
    v,
):

    lo = int(
        indptr[u]
    )

    hi = int(
        indptr[u + 1]
    )

    rel = np.flatnonzero(
        indices[lo:hi] == v
    )

    if len(rel) != 1:
        raise RuntimeError(
            "Transition slot ambiguity/missing: "
            f"{u} -> {v}, "
            f"matches={len(rel)}"
        )

    return (
        lo
        + int(rel[0])
    )


def reconstruct_state_path(
    predecessors,
    source,
    target,
):

    reversed_states = [
        int(target)
    ]

    current = int(target)

    guard = 0

    while current != source:

        parent = int(
            predecessors[current]
        )

        if parent < 0:
            raise RuntimeError(
                "Predecessor missing: "
                f"source={source}, "
                f"target={target}, "
                f"current={current}, "
                f"pred={parent}"
            )

        reversed_states.append(
            parent
        )

        current = parent

        guard += 1

        if guard > len(predecessors):
            raise RuntimeError(
                "Predecessor cycle / overflow"
            )

    reversed_states.reverse()

    return reversed_states


def detect_f3_time_column(
    f3,
    gamma_index,
    e2,
):

    required = [
        "origin_PRO_COM",
        "destination_PRO_COM",
        "origin_access_order",
        "destination_access_order",
    ]

    for col in required:
        hard(
            col in f3.columns,
            "F3 missing key column: "
            f"{col}. "
            f"Columns={list(f3.columns)}"
        )

    ordered = (
        f3
        .sort_values(required)
        .reset_index(drop=True)
    )

    probe_idx = np.linspace(
        0,
        len(ordered) - 1,
        min(
            40,
            len(ordered),
        ),
        dtype=int,
    )

    probe = ordered.iloc[
        probe_idx
    ]

    valid_rows = []
    e2_values = []

    for idx, row in probe.iterrows():

        origin_key = (
            int(
                row["origin_PRO_COM"]
            ),
            int(
                row["origin_access_order"]
            ),
        )

        destination_key = (
            int(
                row["destination_PRO_COM"]
            ),
            int(
                row["destination_access_order"]
            ),
        )

        if (
            origin_key in gamma_index
            and destination_key in gamma_index
        ):

            oi = gamma_index[
                origin_key
            ]

            di = gamma_index[
                destination_key
            ]

            valid_rows.append(
                idx
            )

            e2_values.append(
                float(
                    e2[
                        oi,
                        di,
                    ]
                )
            )

    hard(
        len(valid_rows) > 0,
        "No F3 rows could be mapped "
        "to Gamma/E2."
    )

    e2_values = np.asarray(
        e2_values,
        dtype=float,
    )

    candidates = []

    for col in ordered.columns:

        col_lower = str(
            col
        ).lower()

        is_time_like = (
            "time" in col_lower
            or col_lower.endswith(
                "_s"
            )
        )

        if not is_time_like:
            continue

        if not pd.api.types.is_numeric_dtype(
            ordered[col]
        ):
            continue

        values = pd.to_numeric(
            ordered.loc[
                valid_rows,
                col,
            ],
            errors="coerce",
        ).to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():
            continue

        error = float(
            np.max(
                np.abs(
                    values
                    - e2_values
                )
            )
        )

        candidates.append(
            (
                error,
                col,
            )
        )

    candidates.sort(
        key=lambda x: (
            x[0],
            str(
                x[1]
            ),
        )
    )

    emit(
        "F3 time-column candidates "
        "vs E2:"
    )

    for error, col in candidates[:12]:

        emit(
            f"  {col:<45} "
            f"max_abs_error="
            f"{error:.3e} s"
        )

    hard(
        len(candidates) > 0,
        "No numeric F3 time-like "
        "column found."
    )

    best_error, best_col = (
        candidates[0]
    )

    hard(
        best_error <= FLOAT_TOL,
        "No F3 time column reproduces "
        "E2 within tolerance. "
        f"Best={best_col}, "
        f"error={best_error}"
    )

    return best_col


# =============================================================================
# 2. MAIN
# =============================================================================

try:

    emit(
        "=" * 118
    )

    emit(
        "FASE 5.7 — A1 — "
        "COST CONTRACT + "
        "B5/E2/F3 REGRESSION"
    )

    emit(
        "=" * 118
    )

    emit(
        f"Python : {sys.executable}"
    )

    emit(
        f"Output : {OUT}"
    )


    # =========================================================================
    # A. FROZEN COMPUTATIONAL ARTIFACTS
    # =========================================================================

    emit()

    emit(
        "A. FROZEN COMPUTATIONAL ARTIFACTS"
    )

    emit(
        "-" * 118
    )

    for path, expected in EXPECTED.items():

        hard(
            path.is_file(),
            f"Missing file: {path}"
        )

        actual = sha256_file(
            path
        )

        emit(
            f"{path.name:<48} "
            f"{actual}"
        )

        hard(
            actual.lower()
            == expected.lower(),
            "SHA mismatch: "
            f"{path.name}"
        )

    emit(
        "Frozen identity = PASS"
    )


    # =========================================================================
    # B. B5 SYNCHRONIZED MATRICES
    # =========================================================================

    emit()

    emit(
        "B. LOAD B5 SYNCHRONIZED MATRICES"
    )

    emit(
        "-" * 118
    )


    (
        time_indices,
        time_indptr,
        time_data,
        time_shape,
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
        time_shape
        == (
            N_STATES,
            N_STATES,
        ),
        f"Unexpected TIME shape: "
        f"{time_shape}"
    )

    hard(
        length_shape
        == time_shape,
        "LENGTH shape differs "
        "from TIME."
    )

    hard(
        edge_shape
        == time_shape,
        "EDGEID shape differs "
        "from TIME."
    )


    hard(
        len(time_data)
        == N_TRANSITIONS,
        "Unexpected TIME transitions: "
        f"{len(time_data)}"
    )


    hard(
        np.array_equal(
            time_indices,
            length_indices,
        ),
        "TIME/LENGTH indices mismatch."
    )

    hard(
        np.array_equal(
            time_indices,
            edge_indices,
        ),
        "TIME/EDGEID indices mismatch."
    )

    hard(
        np.array_equal(
            time_indptr,
            length_indptr,
        ),
        "TIME/LENGTH indptr mismatch."
    )

    hard(
        np.array_equal(
            time_indptr,
            edge_indptr,
        ),
        "TIME/EDGEID indptr mismatch."
    )


    hard(
        np.isfinite(
            time_data
        ).all(),
        "B5 TIME contains "
        "non-finite transitions."
    )

    hard(
        (
            time_data > 0
        ).all(),
        "B5 TIME contains "
        "non-positive transitions."
    )


    hard(
        np.isfinite(
            length_data
        ).all(),
        "B5 LENGTH contains "
        "non-finite transitions."
    )

    hard(
        (
            length_data > 0
        ).all(),
        "B5 LENGTH contains "
        "non-positive transitions."
    )


    b5_edge_ids = (
        edge_data.astype(
            np.int64,
            copy=False,
        )
    )


    hard(
        np.equal(
            edge_data,
            b5_edge_ids,
        ).all(),
        "B5 EDGEID data are "
        "not integral."
    )


    emit(
        f"States      : "
        f"{time_shape[0]:,}"
    )

    emit(
        f"Transitions : "
        f"{len(time_data):,}"
    )

    emit(
        "TIME/LENGTH/EDGEID "
        "sparsity structure = MATCH"
    )


    # =========================================================================
    # C. B5 vs B2 COST PROVENANCE
    # =========================================================================

    emit()

    emit(
        "C. B5 TRANSITION COSTS "
        "vs B2 DIRECTED EDGES"
    )

    emit(
        "-" * 118
    )


    con = sqlite3.connect(
        f"file:{B2}?mode=ro",
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


    b2_u = np.full(
        max_edge + 1,
        -1,
        dtype=np.int64,
    )

    b2_v = np.full(
        max_edge + 1,
        -1,
        dtype=np.int64,
    )

    b2_length = np.full(
        max_edge + 1,
        np.nan,
        dtype=np.float64,
    )

    b2_time = np.full(
        max_edge + 1,
        np.nan,
        dtype=np.float64,
    )

    b2_routing_code = np.full(
        max_edge + 1,
        -1,
        dtype=np.int8,
    )


    query = """
        SELECT
            edge_id,
            u,
            v,
            length_m,
            time_s,
            routing_code
        FROM directed_edges
        ORDER BY edge_id
    """


    for chunk in pd.read_sql_query(
        query,
        con,
        chunksize=250_000,
    ):

        ids = (
            chunk[
                "edge_id"
            ]
            .to_numpy(
                dtype=np.int64
            )
        )

        b2_u[ids] = (
            chunk["u"]
            .to_numpy(
                dtype=np.int64
            )
        )

        b2_v[ids] = (
            chunk["v"]
            .to_numpy(
                dtype=np.int64
            )
        )

        b2_length[ids] = (
            chunk["length_m"]
            .to_numpy(
                dtype=float
            )
        )

        b2_time[ids] = (
            chunk["time_s"]
            .to_numpy(
                dtype=float
            )
        )

        b2_routing_code[ids] = (
            chunk["routing_code"]
            .to_numpy(
                dtype=np.int8
            )
        )


    con.close()


    hard(
        n_edges == 1_698_857,
        "Unexpected B2 directed "
        f"edge count: {n_edges}"
    )


    hard(
        (
            b5_edge_ids > 0
        ).all(),
        "B5 transition edge_id <= 0."
    )

    hard(
        (
            b5_edge_ids
            <= max_edge
        ).all(),
        "B5 transition edge_id "
        "outside B2 domain."
    )


    hard(
        np.isfinite(
            b2_time[
                b5_edge_ids
            ]
        ).all(),
        "At least one B5 edge_id "
        "maps to no B2 edge."
    )


    max_time_delta = float(
        np.max(
            np.abs(
                time_data
                - b2_time[
                    b5_edge_ids
                ]
            )
        )
    )


    max_length_delta = float(
        np.max(
            np.abs(
                length_data
                - b2_length[
                    b5_edge_ids
                ]
            )
        )
    )


    non_core_transitions = int(
        np.count_nonzero(
            b2_routing_code[
                b5_edge_ids
            ]
            != 1
        )
    )


    emit(
        "Max |B5 time - B2 edge time| "
        f"= {max_time_delta:.3e} s"
    )

    emit(
        "Max |B5 length - B2 length| "
        f"= {max_length_delta:.3e} m"
    )

    emit(
        "B5 transitions on non-CORE edge "
        f"= {non_core_transitions:,}"
    )


    hard(
        max_time_delta
        <= FLOAT_TOL,
        "B5/B2 time mismatch: "
        f"{max_time_delta}"
    )

    hard(
        max_length_delta
        <= FLOAT_TOL,
        "B5/B2 length mismatch: "
        f"{max_length_delta}"
    )

    hard(
        non_core_transitions == 0,
        "B5 contains "
        f"{non_core_transitions} "
        "non-CORE transition refs."
    )


    emit(
        "B5 transition cost provenance = PASS"
    )


    # =========================================================================
    # D. STATE SEMANTICS + GAMMA
    # =========================================================================

    emit()

    emit(
        "D. STATE SEMANTICS + "
        "GAMMA + PRODUCT-LAMBDA"
    )

    emit(
        "-" * 118
    )


    base_nodes = np.load(
        BASE_NODES_NPY,
        mmap_mode="r",
    )

    state_nodes = np.load(
        STATE_NODE_NPY,
        mmap_mode="r",
    )


    hard(
        base_nodes.shape
        == (
            N_BASE,
        ),
        "Unexpected base_nodes shape: "
        f"{base_nodes.shape}"
    )

    hard(
        state_nodes.shape
        == (
            N_STATES,
        ),
        "Unexpected state_nodes shape: "
        f"{state_nodes.shape}"
    )


    hard(
        np.array_equal(
            np.asarray(
                state_nodes[
                    :N_BASE
                ]
            ),
            np.asarray(
                base_nodes
            ),
        ),
        "state_node_id[:N_BASE] "
        "does not match base_nodes."
    )


    gamma = pd.read_csv(
        GAMMA_CSV
    )


    hard(
        len(gamma)
        == N_GAMMA,
        "Gamma rows: "
        f"{len(gamma)}"
    )


    required_gamma = [
        "PRO_COM",
        "COMUNE",
        "access_order",
        "structural_node_id",
        "base_state_id",
        "lambda_L",
    ]


    for col in required_gamma:

        hard(
            col in gamma.columns,
            f"Gamma missing {col}"
        )


    hard(
        gamma[
            "PRO_COM"
        ].nunique()
        == N_MUNICIPALITIES,
        "Gamma municipalities "
        "!= 215."
    )


    hard(
        (
            gamma[
                "lambda_L"
            ]
            > 0
        ).all(),
        "Nonpositive lambda_L."
    )


    lambda_sum_error = float(

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
        lambda_sum_error
        <= 1e-12,
        "Lambda sum error: "
        f"{lambda_sum_error}"
    )


    source_states = (
        gamma[
            "base_state_id"
        ]
        .to_numpy(
            dtype=np.int64
        )
    )

    source_nodes = (
        gamma[
            "structural_node_id"
        ]
        .to_numpy(
            dtype=np.int64
        )
    )


    hard(
        (
            source_states >= 0
        ).all(),
        "Negative Gamma base_state_id."
    )

    hard(
        (
            source_states
            < N_BASE
        ).all(),
        "Gamma base_state_id "
        "outside base-state domain."
    )


    source_mismatch = int(
        np.count_nonzero(
            np.asarray(
                state_nodes[
                    source_states
                ]
            )
            != source_nodes
        )
    )


    hard(
        source_mismatch == 0,
        "Gamma source-state mismatch: "
        f"{source_mismatch}"
    )


    gamma_index = {

        (
            int(
                row.PRO_COM
            ),
            int(
                row.access_order
            ),
        ):
        idx

        for idx, row
        in enumerate(
            gamma.itertuples(
                index=False
            )
        )

    }


    hard(
        len(
            gamma_index
        )
        == N_GAMMA,
        "Duplicate Gamma "
        "PRO_COM/access_order key."
    )


    emit(
        "Lambda max sum error "
        f"= {lambda_sum_error:.3e}"
    )

    emit(
        "Gamma source-state mismatch "
        f"= {source_mismatch}"
    )

    emit(
        "Gamma/E2 source semantics = PASS"
    )


    # =========================================================================
    # E. DESTINATION SEMANTICS + E2
    # =========================================================================

    emit()

    emit(
        "E. DESTINATION STATE GROUPS + E2"
    )

    emit(
        "-" * 118
    )


    target_nodes = set(
        int(x)
        for x in gamma[
            "structural_node_id"
        ]
    )


    destination_states = {

        node: []

        for node
        in target_nodes

    }


    for state_id, node_id in enumerate(
        np.asarray(
            state_nodes
        )
    ):

        node_id = int(
            node_id
        )

        if node_id in destination_states:

            destination_states[
                node_id
            ].append(
                state_id
            )


    destination_counts = np.array(
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
        dtype=int,
    )


    hard(
        (
            destination_counts
            > 0
        ).all(),
        "At least one Gamma destination "
        "node has no B5 state."
    )


    e2 = np.load(
        E2_NPY,
        mmap_mode="r",
    )


    hard(
        e2.shape
        == (
            N_GAMMA,
            N_GAMMA,
        ),
        "Unexpected E2 shape: "
        f"{e2.shape}"
    )


    hard(
        np.isfinite(
            e2
        ).all(),
        "E2 contains non-finite cells."
    )


    emit(
        "Destination-state count "
        "min/med/max = "
        f"{destination_counts.min()} / "
        f"{np.median(destination_counts):.1f} / "
        f"{destination_counts.max()}"
    )

    emit(
        "E2 matrix = PASS"
    )


    # =========================================================================
    # F. F3 DIRECT REGRESSION SAMPLE
    # =========================================================================

    emit()

    emit(
        "F. F3 DIRECT REGRESSION SAMPLE"
    )

    emit(
        "-" * 118
    )


    f3 = read_csv_auto(
        F3_CSV
    )


    emit(
        f"F3 rows    : {len(f3):,}"
    )

    emit(
        f"F3 columns : {list(f3.columns)}"
    )


    hard(
        len(f3)
        == N_F3_ACCESS_PAIRS,
        "Unexpected F3 pair rows: "
        f"{len(f3)}"
    )


    f3_keys = [
        "origin_PRO_COM",
        "destination_PRO_COM",
        "origin_access_order",
        "destination_access_order",
    ]


    for col in f3_keys:

        hard(
            col in f3.columns,
            f"F3 missing {col}"
        )


    f3_time_col = detect_f3_time_column(
        f3,
        gamma_index,
        e2,
    )


    emit(
        "F3 direct time column "
        f"= {f3_time_col}"
    )


    ordered_f3 = (

        f3
        .sort_values(
            f3_keys
        )
        .reset_index(
            drop=True
        )

    )


    # Campione deterministico distribuito
    # lungo tutto il dataset F3.
    selected_indices = set(

        np.linspace(
            0,
            len(ordered_f3) - 1,
            24,
            dtype=int,
        ).tolist()

    )


    # Se i nomi comunali sono presenti,
    # includere nel campione anche le OD
    # dei siti shadow che ricadono nel
    # dominio F3.
    #
    # Non è una nuova review del sito:
    # è soltanto regression tecnica.
    origin_name_col = next(
        (
            col
            for col in [
                "origin_COMUNE",
                "origin_comune",
                "Comune_res",
            ]
            if col in ordered_f3.columns
        ),
        None,
    )


    destination_name_col = next(
        (
            col
            for col in [
                "destination_COMUNE",
                "destination_comune",
                "Comune_lav",
            ]
            if col in ordered_f3.columns
        ),
        None,
    )


    shadow_pairs = [
        (
            "Cavazzo Carnico",
            "Amaro",
        ),
        (
            "Cercivento",
            "Paluzza",
        ),
        (
            "Paluzza",
            "Cercivento",
        ),
        (
            "Ovaro",
            "Raveo",
        ),
        (
            "Raveo",
            "Ovaro",
        ),
    ]


    if (
        origin_name_col
        and destination_name_col
    ):

        for origin_name, destination_name in shadow_pairs:

            mask = (

                (
                    ordered_f3[
                        origin_name_col
                    ].astype(str)
                    == origin_name
                )

                &

                (
                    ordered_f3[
                        destination_name_col
                    ].astype(str)
                    == destination_name
                )

            )


            hits = ordered_f3.index[
                mask
            ]


            if len(hits) == 0:
                continue


            first_hit = int(
                hits[0]
            )


            origin_code = int(
                ordered_f3.loc[
                    first_hit,
                    "origin_PRO_COM",
                ]
            )

            destination_code = int(
                ordered_f3.loc[
                    first_hit,
                    "destination_PRO_COM",
                ]
            )


            od_rows = ordered_f3.index[

                (
                    ordered_f3[
                        "origin_PRO_COM"
                    ]
                    == origin_code
                )

                &

                (
                    ordered_f3[
                        "destination_PRO_COM"
                    ]
                    == destination_code
                )

            ]


            selected_indices.update(
                int(x)
                for x in od_rows
            )


    sample = (

        ordered_f3
        .iloc[
            sorted(
                selected_indices
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )

    )


    emit(
        "Regression sample rows "
        f"= {len(sample)}"
    )


    # CSR canonico TIME_B5.
    B5_TIME = csr_matrix(
        (
            time_data,
            time_indices,
            time_indptr,
        ),
        shape=time_shape,
    )


    results = []

    dijkstra_cache = {}


    max_e2_error = 0.0
    max_f3_error = 0.0
    max_time_reconstruction_error = 0.0
    max_length_b2_error = 0.0

    extra_destination_state_ties = 0


    for sample_order, (_, row) in enumerate(
        sample.iterrows(),
        start=1,
    ):

        origin_key = (
            int(
                row[
                    "origin_PRO_COM"
                ]
            ),
            int(
                row[
                    "origin_access_order"
                ]
            ),
        )


        destination_key = (
            int(
                row[
                    "destination_PRO_COM"
                ]
            ),
            int(
                row[
                    "destination_access_order"
                ]
            ),
        )


        hard(
            origin_key
            in gamma_index,
            "F3 origin key not "
            f"in Gamma: {origin_key}"
        )

        hard(
            destination_key
            in gamma_index,
            "F3 destination key not "
            f"in Gamma: {destination_key}"
        )


        origin_index = gamma_index[
            origin_key
        ]

        destination_index = gamma_index[
            destination_key
        ]


        source_state = int(
            gamma.iloc[
                origin_index
            ][
                "base_state_id"
            ]
        )


        origin_physical_node = int(
            gamma.iloc[
                origin_index
            ][
                "structural_node_id"
            ]
        )


        destination_physical_node = int(
            gamma.iloc[
                destination_index
            ][
                "structural_node_id"
            ]
        )


        # Una Dijkstra per source-state
        # distinta nel campione.
        if source_state not in dijkstra_cache:

            (
                distances,
                predecessors,
            ) = dijkstra(
                B5_TIME,
                directed=True,
                indices=source_state,
                return_predecessors=True,
            )

            dijkstra_cache[
                source_state
            ] = (
                distances,
                predecessors,
            )


        (
            distances,
            predecessors,
        ) = dijkstra_cache[
            source_state
        ]


        candidate_destination_states = np.asarray(
            destination_states[
                destination_physical_node
            ],
            dtype=np.int64,
        )


        candidate_costs = np.asarray(
            distances[
                candidate_destination_states
            ],
            dtype=float,
        )


        best_time = float(
            np.min(
                candidate_costs
            )
        )


        hard(
            np.isfinite(
                best_time
            ),
            "Unreachable sample: "
            f"{origin_key} -> "
            f"{destination_key}"
        )


        equal_destination_states = (
            candidate_destination_states[

                np.abs(
                    candidate_costs
                    - best_time
                )
                <= 1e-12

            ]
        )


        # Criterio tecnico usato SOLO
        # per ricostruire la sequenza se
        # più destination-state hanno
        # esattamente lo stesso costo.
        #
        # Non modifica il costo.
        destination_state = int(
            np.min(
                equal_destination_states
            )
        )


        if len(
            equal_destination_states
        ) > 1:

            extra_destination_state_ties += (
                len(
                    equal_destination_states
                )
                - 1
            )


        e2_time = float(
            e2[
                origin_index,
                destination_index,
            ]
        )


        f3_time = float(
            row[
                f3_time_col
            ]
        )


        e2_error = abs(
            best_time
            - e2_time
        )


        f3_error = abs(
            best_time
            - f3_time
        )


        max_e2_error = max(
            max_e2_error,
            e2_error,
        )


        max_f3_error = max(
            max_f3_error,
            f3_error,
        )


        hard(
            e2_error
            <= FLOAT_TOL,
            "E2 regression mismatch "
            f"{origin_key} -> "
            f"{destination_key}: "
            f"{e2_error}"
        )


        hard(
            f3_error
            <= FLOAT_TOL,
            "F3 regression mismatch "
            f"{origin_key} -> "
            f"{destination_key}: "
            f"{f3_error}"
        )


        # ---------------------------------------------------------------------
        # RECONSTRUCT STATE SEQUENCE
        # ---------------------------------------------------------------------

        state_sequence = reconstruct_state_path(
            predecessors,
            source_state,
            destination_state,
        )


        transition_slots = []


        for from_state, to_state in zip(
            state_sequence[:-1],
            state_sequence[1:],
        ):

            transition_slots.append(

                find_transition_slot(
                    time_indptr,
                    time_indices,
                    int(
                        from_state
                    ),
                    int(
                        to_state
                    ),
                )

            )


        transition_slots = np.asarray(
            transition_slots,
            dtype=np.int64,
        )


        hard(
            len(
                transition_slots
            )
            > 0,
            "Empty intermunicipal "
            "path sequence."
        )


        reconstructed_time = float(
            np.sum(
                time_data[
                    transition_slots
                ],
                dtype=np.float64,
            )
        )


        reconstructed_length = float(
            np.sum(
                length_data[
                    transition_slots
                ],
                dtype=np.float64,
            )
        )


        sequence_edge_ids = (
            b5_edge_ids[
                transition_slots
            ]
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
            <= (
                FLOAT_TOL
                * max(
                    1,
                    len(
                        transition_slots
                    ),
                )
            ),
            "Path time reconstruction "
            "mismatch: "
            f"{time_reconstruction_error}"
        )


        # ---------------------------------------------------------------------
        # PHYSICAL CONTINUITY
        # ---------------------------------------------------------------------

        from_states = np.asarray(
            state_sequence[:-1],
            dtype=np.int64,
        )


        to_states = np.asarray(
            state_sequence[1:],
            dtype=np.int64,
        )


        physical_from = np.asarray(
            state_nodes[
                from_states
            ],
            dtype=np.int64,
        )


        physical_to = np.asarray(
            state_nodes[
                to_states
            ],
            dtype=np.int64,
        )


        edge_source_mismatch = int(
            np.count_nonzero(
                b2_u[
                    sequence_edge_ids
                ]
                != physical_from
            )
        )


        edge_destination_mismatch = int(
            np.count_nonzero(
                b2_v[
                    sequence_edge_ids
                ]
                != physical_to
            )
        )


        hard(
            (
                edge_source_mismatch == 0
                and
                edge_destination_mismatch == 0
            ),
            "B5/B2 physical continuity "
            "mismatch: "
            f"u={edge_source_mismatch}, "
            f"v={edge_destination_mismatch}"
        )


        b2_length_sum = float(
            np.sum(
                b2_length[
                    sequence_edge_ids
                ],
                dtype=np.float64,
            )
        )


        length_b2_error = abs(
            reconstructed_length
            - b2_length_sum
        )


        max_length_b2_error = max(
            max_length_b2_error,
            length_b2_error,
        )


        hard(
            length_b2_error
            <= (
                FLOAT_TOL
                * max(
                    1,
                    len(
                        transition_slots
                    ),
                )
            ),
            "B5/B2 path length mismatch: "
            f"{length_b2_error}"
        )


        hard(
            int(
                state_nodes[
                    source_state
                ]
            )
            == origin_physical_node,
            "Path source physical "
            "node mismatch."
        )


        hard(
            int(
                state_nodes[
                    destination_state
                ]
            )
            == destination_physical_node,
            "Path destination physical "
            "node mismatch."
        )


        results.append(
            {
                "origin_PRO_COM":
                    origin_key[0],

                "origin_access_order":
                    origin_key[1],

                "destination_PRO_COM":
                    destination_key[0],

                "destination_access_order":
                    destination_key[1],

                "source_state":
                    source_state,

                "destination_state":
                    destination_state,

                "destination_state_tie_count":
                    len(
                        equal_destination_states
                    ),

                "time_dijkstra_s":
                    best_time,

                "time_E2_s":
                    e2_time,

                "time_F3_s":
                    f3_time,

                "abs_error_E2_s":
                    e2_error,

                "abs_error_F3_s":
                    f3_error,

                "distance_reconstructed_m":
                    reconstructed_length,

                "n_B5_transitions":
                    len(
                        transition_slots
                    ),

                "n_physical_edges":
                    len(
                        sequence_edge_ids
                    ),

                "first_transition_slot":
                    int(
                        transition_slots[0]
                    ),

                "last_transition_slot":
                    int(
                        transition_slots[-1]
                    ),

                "status":
                    "PASS",
            }
        )


        emit(
            f"  {sample_order:02d}/"
            f"{len(sample):02d} "
            f"{origin_key} -> "
            f"{destination_key} | "
            f"time={best_time:.6f}s | "
            f"transitions="
            f"{len(transition_slots)} | "
            f"dest_ties="
            f"{len(equal_destination_states)}"
        )


    pd.DataFrame(
        results
    ).to_csv(
        SAMPLE_CSV,
        index=False,
        encoding="utf-8-sig",
    )


    emit()

    emit(
        "Max B5 -> E2 error              "
        f"= {max_e2_error:.3e} s"
    )

    emit(
        "Max B5 -> F3 error              "
        f"= {max_f3_error:.3e} s"
    )

    emit(
        "Max reconstructed time error    "
        f"= {max_time_reconstruction_error:.3e} s"
    )

    emit(
        "Max B5/B2 path-length error     "
        f"= {max_length_b2_error:.3e} m"
    )

    emit(
        "Extra equal-cost destination-"
        "state ties observed "
        f"= {extra_destination_state_ties}"
    )

    emit(
        f"Sample CSV: {SAMPLE_CSV}"
    )


    # =========================================================================
    # FINAL VERDICT
    # =========================================================================

    emit()

    emit(
        "=" * 118
    )

    emit(
        "A1 COST CONTRACT RESULT = PASS"
    )

    emit(
        "CANONICAL_ROUTE_IMPEDANCE = TIME_B5"
    )

    emit(
        "DISTANCE = PATH_ATTRIBUTE"
    )

    emit(
        "B5 TIME/LENGTH/EDGEID SPARSITY = MATCH"
    )

    emit(
        "B5 TRANSITION COST PROVENANCE = PASS"
    )

    emit(
        "GAMMA SOURCE / DESTINATION SEMANTICS = PASS"
    )

    emit(
        "B5 vs E2/F3 SAMPLE REGRESSION = PASS"
    )


    emit(        "No frozen Phase-5.6 artifact was modified."
    )

    emit(
        "=" * 118
    )

    emit()

    emit(
        "=== RUN COMPLETATA CORRETTAMENTE ==="
    )


except Exception as exc:

    emit()

    emit(
        "=" * 118
    )

    emit(
        "A1 COST CONTRACT RESULT = "
        "FAIL / BLOCKING CANDIDATE"
    )

    emit(
        f"{type(exc).__name__}: {exc}"
    )

    emit(
        "STOP: do not materialize "
        "the 414,090 paths."
    )

    emit(
        "Do not modify B5/Gamma."
    )

    emit(
        "Return this log to Chat 5.7 "
        "/ Chat Madre."
    )

    emit(
        "=" * 118
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
