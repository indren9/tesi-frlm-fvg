# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import sys
import time
import traceback
import unicodedata

import numpy as np
import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

BACKBONE = ROOT / "02_package" / "grafo_operativo_osm"
GAMMA_DIR = ROOT / "02_package" / "accessi_comunali_osm_light"

B1_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "B1_full_materialization"
)

B1_SHARDS = B1_ROOT / "shards"

OUT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "B2_canonical_candidate"
)

LOG = OUT / "FASE_5_7_B2_canonical_candidate.txt"

ACCESS_PATHS = OUT / "OSM_OD_access_paths_v01.csv"
MUNICIPAL = OUT / "OSM_OD_municipal_summary_v01.csv"
OFFSETS_OUT = OUT / "OSM_OD_path_offsets_v01.npy"
SLOTS_OUT = OUT / "OSM_OD_transition_slots_v01.npy"

SEQ_CONTRACT = OUT / "OSM_OD_sequence_contract_v01.json"
F1_REGRESSION = OUT / "OSM_OD_F1_regression_v01.csv"
MANIFEST = OUT / "OSM_OD_PATHS_candidate_manifest_v01.json"


GAMMA_CSV = GAMMA_DIR / "Gamma_OSM_L_comuni_fvg_v01.csv"

TIME_NPZ = BACKBONE / "osm_turn_state_time_v01.npz"

B1_GATE = B1_ROOT / "B1_FULL_MATERIALIZATION_GATE_v01.json"

A1_LOG = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "A1_cost_contract"
    / "FASE_5_7_A1_cost_contract_regression.txt"
)


F1_MOVEMENTS = (
    BACKBONE
    / "G_OSM_F1_shadow_regression_movements_v01.csv"
)

F1_SUMMARY = (
    BACKBONE
    / "G_OSM_F1_shadow_regression_summary_v01.csv"
)

F1_MANIFEST = (
    BACKBONE
    / "G_OSM_F1_shadow_regression_manifest_v01.json"
)


EXPECTED_F1_HASHES = {
    F1_MOVEMENTS:
        "86a36f128148c830cbb9c73761f5e3f56afa811e0b84a43d1975af4fb44532c6",

    F1_SUMMARY:
        "56764e5ef8dcf53c967783fd4d90eb518eb9519b61187005e1261572b42b003b",

    F1_MANIFEST:
        "43ba21ec5782a518a97f8a1c2227e397bddb6a3c0ff5b6ee5ed7ff12dc9632b5",
}


EXPECTED_GAMMA_SHA = (
    "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
)

EXPECTED_TIME_SHA = (
    "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"
)


N_STATES = 904_607
N_TRANSITIONS = 1_699_994

N_MUNICIPALITIES = 215
N_PATHS_PER_ORIGIN = 1_926

N_OD = 46_010
N_PATHS = 414_090

PAIR_TOL = 1e-12


lines = []


# =============================================================================
# HELPERS
# =============================================================================

def emit(msg=""):
    msg = str(msg)
    print(msg, flush=True)
    lines.append(msg)


def hard(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256_file(path, chunk_size=16 * 1024 * 1024):

    h = hashlib.sha256()

    with Path(path).open("rb") as f:

        while True:

            b = f.read(chunk_size)

            if not b:
                break

            h.update(b)

    return h.hexdigest()


def normalize_name(value):

    s = str(value).strip().lower()

    s = "".join(
        c
        for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )

    return " ".join(s.split())


def shard_paths(origin_code):

    prefix = f"O{int(origin_code):05d}"

    return {
        "csv":
            B1_SHARDS / f"{prefix}_paths_v01.csv",

        "offsets":
            B1_SHARDS / f"{prefix}_offsets_v01.npy",

        "slots":
            B1_SHARDS / f"{prefix}_transition_slots_v01.npy",

        "manifest":
            B1_SHARDS / f"{prefix}_manifest_v01.json",
    }


def qstats(x):

    x = np.asarray(
        x,
        dtype=np.float64,
    )

    return {
        "min": float(np.min(x)),
        "p05": float(np.quantile(x, 0.05)),
        "p50": float(np.quantile(x, 0.50)),
        "mean": float(np.mean(x)),
        "p95": float(np.quantile(x, 0.95)),
        "max": float(np.max(x)),
    }


# =============================================================================
# MAIN
# =============================================================================

try:

    start = time.perf_counter()

    emit("=" * 124)

    emit(
        "FASE 5.7 — B2 — "
        "CANONICAL CONSOLIDATION + FINAL QA CANDIDATE"
    )

    emit("=" * 124)

    emit(f"Python : {sys.executable}")
    emit(f"B1     : {B1_ROOT}")
    emit(f"Output : {OUT}")

    # Temporary B2 output may be rebuilt.
    # Frozen/canonical packages are NEVER touched here.
    if OUT.exists():
        shutil.rmtree(OUT)

    OUT.mkdir(
        parents=True,
        exist_ok=False,
    )


    # =========================================================================
    # A. A1 / B1 GATE INHERITANCE
    # =========================================================================

    emit()
    emit("A. A1 / B1 GATE INHERITANCE")
    emit("-" * 124)

    hard(
        A1_LOG.is_file(),
        "A1 log missing.",
    )

    a1_text = A1_LOG.read_text(
        encoding="utf-8",
        errors="replace",
    )

    hard(
        "A1 COST CONTRACT RESULT = PASS"
        in a1_text,
        "A1 PASS marker missing.",
    )

    hard(
        "CANONICAL_ROUTE_IMPEDANCE = TIME_B5"
        in a1_text,
        "A1 cost-contract marker missing.",
    )

    hard(
        "DISTANCE = PATH_ATTRIBUTE"
        in a1_text,
        "A1 distance-contract marker missing.",
    )

    hard(
        B1_GATE.is_file(),
        "B1 gate JSON missing.",
    )

    b1_gate = json.loads(
        B1_GATE.read_text(
            encoding="utf-8"
        )
    )

    hard(
        b1_gate.get("verdict") == "PASS",
        "B1 verdict != PASS.",
    )

    counts = b1_gate["counts"]

    hard(
        int(counts["N_origin_shards"])
        == 215,
        "B1 origin shard count mismatch.",
    )

    hard(
        int(counts["N_municipal_OD"])
        == N_OD,
        "B1 municipal OD mismatch.",
    )

    hard(
        int(counts["N_access_pair_paths"])
        == N_PATHS,
        "B1 path count mismatch.",
    )

    hard(
        int(counts["N_finite"])
        == N_PATHS,
        "B1 finite count mismatch.",
    )

    hard(
        int(counts["N_unreachable"])
        == 0,
        "B1 unreachable != 0.",
    )

    hard(
        int(counts["path_reconstruction_failures"])
        == 0,
        "B1 reconstruction failures != 0.",
    )

    total_slots_expected = int(
        counts["N_stored_transition_slots"]
    )

    emit("A1 cost contract       = PASS")
    emit("B1 materialization     = PASS")

    emit(
        f"B1 transition slots    = "
        f"{total_slots_expected:,}"
    )


    # =========================================================================
    # B. FROZEN B5 / GAMMA / F1 IDENTITY
    # =========================================================================

    emit()
    emit("B. FROZEN IDENTITY")
    emit("-" * 124)

    gamma_sha = sha256_file(
        GAMMA_CSV
    )

    time_sha = sha256_file(
        TIME_NPZ
    )

    emit(
        f"{GAMMA_CSV.name:<50} "
        f"{gamma_sha}"
    )

    emit(
        f"{TIME_NPZ.name:<50} "
        f"{time_sha}"
    )

    hard(
        gamma_sha == EXPECTED_GAMMA_SHA,
        "Gamma SHA mismatch.",
    )

    hard(
        time_sha == EXPECTED_TIME_SHA,
        "B5 TIME SHA mismatch.",
    )


    f1_hashes = {}

    for path, expected in EXPECTED_F1_HASHES.items():

        hard(
            path.is_file(),
            f"Missing F1 artifact: {path.name}",
        )

        actual = sha256_file(
            path
        )

        f1_hashes[
            path.name
        ] = actual

        emit(
            f"{path.name:<50} "
            f"{actual}"
        )

        hard(
            actual == expected,
            f"F1 SHA mismatch: {path.name}",
        )

    emit(
        "Frozen B5 / Gamma / F1 identity = PASS"
    )


    # =========================================================================
    # C. CANONICAL ORIGIN ORDER
    # =========================================================================

    emit()
    emit("C. CANONICAL DOMAIN ORDER")
    emit("-" * 124)

    gamma = pd.read_csv(
        GAMMA_CSV
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
        len(origin_codes)
        == N_MUNICIPALITIES,
        "Origin municipality count != 215.",
    )

    emit(
        f"Origin municipalities = "
        f"{len(origin_codes):,}"
    )


    # =========================================================================
    # D. LOAD B5 CSR STATE STRUCTURE
    # =========================================================================

    emit()
    emit("D. B5 CSR STATE STRUCTURE")
    emit("-" * 124)

    with np.load(
        TIME_NPZ,
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

        shape = tuple(
            int(x)
            for x in np.asarray(
                z["shape"]
            ).tolist()
        )

    hard(
        shape
        == (
            N_STATES,
            N_STATES,
        ),
        "B5 shape mismatch.",
    )

    hard(
        len(indices)
        == N_TRANSITIONS,
        "B5 transition count mismatch.",
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
        len(slot_from_state)
        == N_TRANSITIONS,
        "slot_from_state length mismatch.",
    )

    emit(
        f"B5 states      = {N_STATES:,}"
    )

    emit(
        f"B5 transitions = {N_TRANSITIONS:,}"
    )


    # =========================================================================
    # E. PREFLIGHT ALL B1 SHARDS
    # =========================================================================

    emit()
    emit("E. B1 SHARD PREFLIGHT")
    emit("-" * 124)

    shard_manifests = []

    for pos, origin_code in enumerate(
        origin_codes,
        start=1,
    ):

        p = shard_paths(
            origin_code
        )

        for key in [
            "csv",
            "offsets",
            "slots",
            "manifest",
        ]:

            hard(
                p[key].is_file(),
                f"Missing B1 shard file: {p[key]}",
            )

        manifest = json.loads(
            p["manifest"].read_text(
                encoding="utf-8"
            )
        )

        hard(
            manifest.get("status")
            == "PASS",
            f"Shard {origin_code} != PASS.",
        )

        hard(
            int(
                manifest[
                    "metrics"
                ][
                    "N_paths"
                ]
            )
            == N_PATHS_PER_ORIGIN,
            f"Shard {origin_code} path count mismatch.",
        )

        for key in [
            "csv",
            "offsets",
            "slots",
        ]:

            expected = (
                manifest[
                    "files_sha256"
                ][
                    p[key].name
                ]
            )

            actual = sha256_file(
                p[key]
            )

            hard(
                actual == expected,
                f"Shard SHA mismatch: "
                f"{p[key].name}",
            )

        shard_manifests.append(
            manifest
        )

        if (
            pos == 1
            or pos % 25 == 0
            or pos == 215
        ):

            emit(
                f"Verified shards: "
                f"{pos:03d}/215"
            )

    total_slots_manifest = sum(

        int(
            m[
                "metrics"
            ][
                "N_transition_slots"
            ]
        )

        for m in shard_manifests
    )

    hard(
        total_slots_manifest
        == total_slots_expected,
        "Total shard slot count differs "
        "from B1 global gate.",
    )

    emit(
        f"Valid shards        = 215 / 215"
    )

    emit(
        f"Total B5 slots      = "
        f"{total_slots_manifest:,}"
    )


    # =========================================================================
    # F. CREATE GLOBAL MEMMAPS
    # =========================================================================

    emit()
    emit("F. CREATE CANONICAL CSR-LIKE STORE")
    emit("-" * 124)

    offsets_mm = np.lib.format.open_memmap(
        OFFSETS_OUT,
        mode="w+",
        dtype=np.int64,
        shape=(
            N_PATHS + 1,
        ),
    )

    slots_mm = np.lib.format.open_memmap(
        SLOTS_OUT,
        mode="w+",
        dtype=np.int32,
        shape=(
            total_slots_expected,
        ),
    )

    offsets_mm[0] = 0


    # =========================================================================
    # G. CONSOLIDATE + FULL SEQUENCE QA
    # =========================================================================

    emit()
    emit("G. CONSOLIDATE PATHS + FULL SEQUENCE QA")
    emit("-" * 124)

    global_path = 0
    global_slot = 0

    first_csv = True

    municipal_rows = []

    path_ids_seen = set()

    sequence_discontinuities = 0
    source_mismatch = 0
    destination_mismatch = 0
    forbidden_slot_violations = 0

    transition_count_mismatch = 0

    nonpositive_time = 0
    nonpositive_distance = 0
    nonpositive_weight = 0

    max_pair_sum_error = 0.0

    f1_pair_counts = {}

    for origin_pos, origin_code in enumerate(
        origin_codes,
        start=1,
    ):

        p = shard_paths(
            origin_code
        )

        df = pd.read_csv(
            p["csv"]
        )

        offsets = np.load(
            p["offsets"],
            mmap_mode="r",
        )

        slots = np.load(
            p["slots"],
            mmap_mode="r",
        )

        n_paths = len(df)
        n_slots = len(slots)

        hard(
            n_paths
            == N_PATHS_PER_ORIGIN,
            "Unexpected shard path count.",
        )

        hard(
            len(offsets)
            == n_paths + 1,
            "Shard offset length mismatch.",
        )

        hard(
            int(offsets[0])
            == 0,
            "Shard offsets do not start at zero.",
        )

        hard(
            int(offsets[-1])
            == n_slots,
            "Shard offsets do not end at slot count.",
        )

        path_lengths = np.diff(
            offsets
        )

        hard(
            (
                path_lengths > 0
            ).all(),
            "Zero-length path found.",
        )


        # -------------------------------------------------------------
        # Slot domain
        # -------------------------------------------------------------

        bad_slot = int(
            np.count_nonzero(
                (slots < 0)
                |
                (slots >= N_TRANSITIONS)
            )
        )

        forbidden_slot_violations += bad_slot

        hard(
            bad_slot == 0,
            "Transition slot outside frozen B5 domain.",
        )


        # -------------------------------------------------------------
        # Source / destination state integrity
        # -------------------------------------------------------------

        first_slots = np.asarray(
            slots[
                offsets[:-1]
            ],
            dtype=np.int64,
        )

        last_slots = np.asarray(
            slots[
                offsets[1:] - 1
            ],
            dtype=np.int64,
        )

        first_from = slot_from_state[
            first_slots
        ]

        last_to = indices[
            last_slots
        ]

        source_bad = int(
            np.count_nonzero(
                first_from
                !=
                df[
                    "source_state"
                ].to_numpy(
                    dtype=np.int64
                )
            )
        )

        dest_bad = int(
            np.count_nonzero(
                last_to
                !=
                df[
                    "destination_state"
                ].to_numpy(
                    dtype=np.int64
                )
            )
        )

        source_mismatch += source_bad
        destination_mismatch += dest_bad

        hard(
            source_bad == 0,
            f"Source mismatch in O{origin_code}.",
        )

        hard(
            dest_bad == 0,
            f"Destination mismatch in O{origin_code}.",
        )


        # -------------------------------------------------------------
        # Full state-sequence continuity
        # -------------------------------------------------------------

        from_states = slot_from_state[
            slots
        ]

        to_states = indices[
            slots
        ]

        if n_slots > 1:

            continuity = (
                to_states[:-1]
                ==
                from_states[1:]
            )

            boundary_idx = (
                np.asarray(
                    offsets[1:-1],
                    dtype=np.int64,
                )
                - 1
            )

            continuity[
                boundary_idx
            ] = True

            local_disc = int(
                np.count_nonzero(
                    ~continuity
                )
            )

        else:

            local_disc = 0

        sequence_discontinuities += local_disc

        hard(
            local_disc == 0,
            f"Sequence discontinuity "
            f"in O{origin_code}.",
        )

        del from_states
        del to_states


        # -------------------------------------------------------------
        # Metadata-vs-offset sequence lengths
        # -------------------------------------------------------------

        local_count_bad = int(
            np.count_nonzero(
                path_lengths
                !=
                df[
                    "n_B5_transitions"
                ].to_numpy(
                    dtype=np.int64
                )
            )
        )

        transition_count_mismatch += (
            local_count_bad
        )

        hard(
            local_count_bad == 0,
            "Transition count metadata mismatch.",
        )


        # -------------------------------------------------------------
        # Basic numerical QA
        # -------------------------------------------------------------

        local_bad_time = int(
            np.count_nonzero(
                df[
                    "time_s"
                ].to_numpy(
                    dtype=np.float64
                )
                <= 0
            )
        )

        local_bad_distance = int(
            np.count_nonzero(
                df[
                    "distance_m"
                ].to_numpy(
                    dtype=np.float64
                )
                <= 0
            )
        )

        local_bad_weight = int(
            np.count_nonzero(
                df[
                    "pair_weight"
                ].to_numpy(
                    dtype=np.float64
                )
                <= 0
            )
        )

        nonpositive_time += local_bad_time
        nonpositive_distance += local_bad_distance
        nonpositive_weight += local_bad_weight

        hard(
            local_bad_time == 0,
            "Non-positive time.",
        )

        hard(
            local_bad_distance == 0,
            "Non-positive distance.",
        )

        hard(
            local_bad_weight == 0,
            "Non-positive pair weight.",
        )


        # -------------------------------------------------------------
        # PRODUCT-LAMBDA per municipal OD
        # -------------------------------------------------------------

        grouped = df.groupby(
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ],
            sort=False,
        )

        hard(
            grouped.ngroups == 214,
            "Municipal OD groups per origin != 214.",
        )


        for (
            origin_pro_com,
            destination_pro_com
        ), g in grouped:

            hard(
                len(g) == 9,
                "Municipal OD does not contain 9 access pairs.",
            )

            w = g[
                "pair_weight"
            ].to_numpy(
                dtype=np.float64
            )

            t = g[
                "time_s"
            ].to_numpy(
                dtype=np.float64
            )

            d = g[
                "distance_m"
            ].to_numpy(
                dtype=np.float64
            )

            sum_w = float(
                np.sum(
                    w,
                    dtype=np.float64,
                )
            )

            err = abs(
                sum_w - 1.0
            )

            max_pair_sum_error = max(
                max_pair_sum_error,
                err,
            )

            hard(
                err <= PAIR_TOL,
                "PRODUCT-LAMBDA OD sum error.",
            )


            # Deterministic reporting tie-break only.
            best_time = g.sort_values(
                [
                    "time_s",
                    "origin_access_order",
                    "destination_access_order",
                    "path_id",
                ],
                kind="mergesort",
            ).iloc[0]

            best_distance = g.sort_values(
                [
                    "distance_m",
                    "origin_access_order",
                    "destination_access_order",
                    "path_id",
                ],
                kind="mergesort",
            ).iloc[0]


            municipal_rows.append(
                {
                    "origin_PRO_COM":
                        int(origin_pro_com),

                    "origin_COMUNE":
                        str(
                            g.iloc[0][
                                "origin_COMUNE"
                            ]
                        ),

                    "destination_PRO_COM":
                        int(
                            destination_pro_com
                        ),

                    "destination_COMUNE":
                        str(
                            g.iloc[0][
                                "destination_COMUNE"
                            ]
                        ),

                    "N_access_pairs":
                        9,

                    "sum_pair_weight":
                        sum_w,

                    "time_s_PRODUCT_LAMBDA":
                        float(
                            np.dot(
                                w,
                                t,
                            )
                        ),

                    "distance_m_PRODUCT_LAMBDA":
                        float(
                            np.dot(
                                w,
                                d,
                            )
                        ),

                    "time_min_s":
                        float(
                            np.min(t)
                        ),

                    "time_max_s":
                        float(
                            np.max(t)
                        ),

                    "time_spread_s":
                        float(
                            np.max(t)
                            -
                            np.min(t)
                        ),

                    "distance_min_m":
                        float(
                            np.min(d)
                        ),

                    "distance_max_m":
                        float(
                            np.max(d)
                        ),

                    "distance_spread_m":
                        float(
                            np.max(d)
                            -
                            np.min(d)
                        ),

                    "best_time_path_id":
                        str(
                            best_time[
                                "path_id"
                            ]
                        ),

                    "best_time_origin_access_order":
                        int(
                            best_time[
                                "origin_access_order"
                            ]
                        ),

                    "best_time_destination_access_order":
                        int(
                            best_time[
                                "destination_access_order"
                            ]
                        ),

                    "best_distance_path_id":
                        str(
                            best_distance[
                                "path_id"
                            ]
                        ),

                    "best_distance_origin_access_order":
                        int(
                            best_distance[
                                "origin_access_order"
                            ]
                        ),

                    "best_distance_destination_access_order":
                        int(
                            best_distance[
                                "destination_access_order"
                            ]
                        ),
                }
            )


        # -------------------------------------------------------------
        # F1 municipal-domain presence counters
        # -------------------------------------------------------------

        for row in df.itertuples(
            index=False
        ):

            o = normalize_name(
                row.origin_COMUNE
            )

            dname = normalize_name(
                row.destination_COMUNE
            )

            key = (
                o,
                dname,
            )

            f1_pair_counts[
                key
            ] = (
                f1_pair_counts.get(
                    key,
                    0,
                )
                + 1
            )


        # -------------------------------------------------------------
        # Global deterministic path ID uniqueness
        # -------------------------------------------------------------

        for pid in df[
            "path_id"
        ].astype(str):

            hard(
                pid not in path_ids_seen,
                f"Duplicate path_id: {pid}",
            )

            path_ids_seen.add(
                pid
            )


        # -------------------------------------------------------------
        # Copy shard sequences into canonical global store
        # -------------------------------------------------------------

        slots_mm[
            global_slot:
            global_slot + n_slots
        ] = slots[:]


        offsets_mm[
            global_path + 1:
            global_path + n_paths + 1
        ] = (
            global_slot
            +
            offsets[1:]
        )


        # -------------------------------------------------------------
        # Canonical path table
        # -------------------------------------------------------------

        out_df = df.copy()

        out_df.insert(
            0,
            "path_idx",
            np.arange(
                global_path,
                global_path + n_paths,
                dtype=np.int64,
            ),
        )

        out_df[
            "sequence_start"
        ] = (
            global_slot
            +
            offsets[:-1]
        )

        out_df[
            "sequence_end"
        ] = (
            global_slot
            +
            offsets[1:]
        )

        out_df[
            "canonical_route_impedance"
        ] = "TIME_B5"

        out_df[
            "distance_semantics"
        ] = "PATH_ATTRIBUTE"


        # Remove local-only positions from canonical output.
        for col in [
            "sequence_start_local",
            "sequence_end_local",
        ]:

            if col in out_df.columns:
                out_df.drop(
                    columns=[col],
                    inplace=True,
                )


        out_df.to_csv(
            ACCESS_PATHS,
            mode=(
                "w"
                if first_csv
                else "a"
            ),
            header=first_csv,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.17g",
        )

        first_csv = False


        global_path += n_paths
        global_slot += n_slots


        if (
            origin_pos == 1
            or origin_pos % 20 == 0
            or origin_pos == 215
        ):

            emit(
                f"[{origin_pos:03d}/215] "
                f"paths={global_path:,} | "
                f"slots={global_slot:,} | "
                f"sequence_disc="
                f"{sequence_discontinuities:,}"
            )


    offsets_mm.flush()
    slots_mm.flush()

    del offsets_mm
    del slots_mm


    # =========================================================================
    # H. GLOBAL CONSOLIDATION CHECK
    # =========================================================================

    emit()
    emit("H. GLOBAL CONSOLIDATION CHECK")
    emit("-" * 124)

    hard(
        global_path == N_PATHS,
        "Global path count != 414090.",
    )

    hard(
        global_slot
        == total_slots_expected,
        "Global slot count mismatch.",
    )

    hard(
        len(path_ids_seen)
        == N_PATHS,
        "Global unique path_id count mismatch.",
    )

    canonical_offsets = np.load(
        OFFSETS_OUT,
        mmap_mode="r",
    )

    canonical_slots = np.load(
        SLOTS_OUT,
        mmap_mode="r",
    )

    hard(
        len(canonical_offsets)
        == N_PATHS + 1,
        "Canonical offsets length mismatch.",
    )

    hard(
        int(canonical_offsets[0])
        == 0,
        "Canonical offsets do not start at zero.",
    )

    hard(
        int(canonical_offsets[-1])
        == total_slots_expected,
        "Canonical offsets final value mismatch.",
    )

    hard(
        (
            np.diff(
                canonical_offsets
            )
            > 0
        ).all(),
        "Canonical zero-length path.",
    )

    hard(
        len(canonical_slots)
        == total_slots_expected,
        "Canonical slots length mismatch.",
    )

    emit(
        f"Canonical paths      = "
        f"{global_path:,}"
    )

    emit(
        f"Canonical slots      = "
        f"{global_slot:,}"
    )

    emit(
        f"Sequence discontinuities = "
        f"{sequence_discontinuities:,}"
    )

    emit(
        f"Source mismatch          = "
        f"{source_mismatch:,}"
    )

    emit(
        f"Destination mismatch     = "
        f"{destination_mismatch:,}"
    )

    emit(
        f"Forbidden slot violation = "
        f"{forbidden_slot_violations:,}"
    )

    emit(
        f"Transition-count mismatch= "
        f"{transition_count_mismatch:,}"
    )


    # =========================================================================
    # I. MUNICIPAL SUMMARY
    # =========================================================================

    emit()
    emit("I. MUNICIPAL PRODUCT-LAMBDA SUMMARY")
    emit("-" * 124)

    municipal = pd.DataFrame(
        municipal_rows
    )

    hard(
        len(municipal)
        == N_OD,
        "Municipal summary rows != 46010.",
    )

    hard(
        municipal[
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ]
        ]
        .drop_duplicates()
        .shape[0]
        == N_OD,
        "Duplicate municipal OD.",
    )

    hard(
        (
            municipal[
                "origin_PRO_COM"
            ]
            !=
            municipal[
                "destination_PRO_COM"
            ]
        ).all(),
        "Self municipal OD found.",
    )

    hard(
        (
            municipal[
                "N_access_pairs"
            ]
            == 9
        ).all(),
        "N_access_pairs != 9.",
    )

    hard(
        float(
            (
                municipal[
                    "sum_pair_weight"
                ]
                - 1.0
            )
            .abs()
            .max()
        )
        <= PAIR_TOL,
        "Municipal weight sum failure.",
    )

    municipal.to_csv(
        MUNICIPAL,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )


    time_stats = qstats(
        municipal[
            "time_s_PRODUCT_LAMBDA"
        ]
    )

    distance_stats = qstats(
        municipal[
            "distance_m_PRODUCT_LAMBDA"
        ]
        / 1000.0
    )

    time_spread_stats = qstats(
        municipal[
            "time_spread_s"
        ]
    )

    distance_spread_stats = qstats(
        municipal[
            "distance_spread_m"
        ]
        / 1000.0
    )


    emit(
        f"Municipal ordered OD = "
        f"{len(municipal):,}"
    )

    emit(
        "Time PRODUCT-LAMBDA [s]: "
        f"median={time_stats['p50']:.3f}, "
        f"p95={time_stats['p95']:.3f}, "
        f"max={time_stats['max']:.3f}"
    )

    emit(
        "Distance PRODUCT-LAMBDA [km]: "
        f"median={distance_stats['p50']:.3f}, "
        f"p95={distance_stats['p95']:.3f}, "
        f"max={distance_stats['max']:.3f}"
    )

    emit(
        "9-path time spread [s]: "
        f"median={time_spread_stats['p50']:.3f}, "
        f"p95={time_spread_stats['p95']:.3f}"
    )

    emit(
        "9-path distance spread [km]: "
        f"median={distance_spread_stats['p50']:.3f}, "
        f"p95={distance_spread_stats['p95']:.3f}"
    )


    # =========================================================================
    # J. F1 SHADOW TECHNICAL REGRESSION
    # =========================================================================

    emit()
    emit("J. F1 SHADOW TECHNICAL REGRESSION")
    emit("-" * 124)

    f1_rows = []


    def count_pair(origin, destination):

        return int(
            f1_pair_counts.get(
                (
                    normalize_name(
                        origin
                    ),
                    normalize_name(
                        destination
                    ),
                ),
                0,
            )
        )


    # SHADOW-01
    c = count_pair(
        "Cavazzo Carnico",
        "Amaro",
    )

    hard(
        c == 9,
        "SHADOW-01 canonical OD "
        "does not contain 9 access paths.",
    )

    f1_rows.append(
        {
            "site":
                "SHADOW-01",

            "movement":
                "Cavazzo Carnico -> Amaro",

            "new_materialization_check":
                "9_ACCESS_PATHS_PRESENT",

            "new_materialization_count":
                c,

            "frozen_F1_evidence":
                "PASS",

            "regression_mode":
                "OD_DOMAIN_PRESENCE + FROZEN_B5_IDENTITY",

            "result":
                "PASS",
        }
    )


    # SHADOW-02
    c1 = count_pair(
        "Cercivento",
        "Paluzza",
    )

    c2 = count_pair(
        "Paluzza",
        "Cercivento",
    )

    hard(
        c1 == 9
        and c2 == 9,
        "SHADOW-02 bidirectional "
        "canonical OD paths missing.",
    )

    f1_rows.append(
        {
            "site":
                "SHADOW-02",

            "movement":
                "Cercivento <-> Paluzza",

            "new_materialization_check":
                "18_BIDIRECTIONAL_ACCESS_PATHS_PRESENT",

            "new_materialization_count":
                c1 + c2,

            "frozen_F1_evidence":
                "PASS",

            "regression_mode":
                "OD_DOMAIN_PRESENCE + FROZEN_B5_IDENTITY",

            "result":
                "PASS",
        }
    )


    # SHADOW-03
    c1 = count_pair(
        "Ovaro",
        "Raveo",
    )

    c2 = count_pair(
        "Raveo",
        "Ovaro",
    )

    hard(
        c1 == 9
        and c2 == 9,
        "SHADOW-03 bidirectional "
        "canonical OD paths missing.",
    )

    f1_rows.append(
        {
            "site":
                "SHADOW-03",

            "movement":
                "Ovaro <-> Raveo",

            "new_materialization_check":
                "18_BIDIRECTIONAL_ACCESS_PATHS_PRESENT",

            "new_materialization_count":
                c1 + c2,

            "frozen_F1_evidence":
                "PASS",

            "regression_mode":
                "OD_DOMAIN_PRESENCE + FROZEN_B5_IDENTITY",

            "result":
                "PASS",
        }
    )


    # SHADOW-04B:
    # local negative-control movement, not a municipal OD.
    # It is inherited only through the unchanged frozen B5 + exact F1 evidence.
    f1_rows.append(
        {
            "site":
                "SHADOW-04B",

            "movement":
                "Via Andervolti negative control",

            "new_materialization_check":
                "OUTSIDE_MUNICIPAL_OD_DOMAIN",

            "new_materialization_count":
                0,

            "frozen_F1_evidence":
                "PASS",

            "regression_mode":
                "FROZEN_B5_IDENTITY_ONLY",

            "result":
                "PASS",
        }
    )


    f1_df = pd.DataFrame(
        f1_rows
    )

    hard(
        len(f1_df) == 4,
        "F1 technical regression count != 4.",
    )

    hard(
        (
            f1_df[
                "result"
            ]
            == "PASS"
        ).all(),
        "F1 regression failure.",
    )

    f1_df.to_csv(
        F1_REGRESSION,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


    for row in f1_df.itertuples(
        index=False
    ):

        emit(
            f"{row.site:<10} "
            f"{row.result:<4} | "
            f"{row.new_materialization_check}"
        )

    emit(
        "F1 sites = 4"
    )

    emit(
        "Technical failures = 0"
    )

    emit(
        "Real B5 regressions = 0"
    )

    emit(
        "F1 technical inheritance/regression = PASS"
    )


    # =========================================================================
    # K. SEQUENCE CONTRACT
    # =========================================================================

    emit()
    emit("K. CANONICAL SEQUENCE CONTRACT")
    emit("-" * 124)

    sequence_contract = {
        "version":
            "v01",

        "path_order":
            (
                "path_idx 0..414089 in canonical "
                "Gamma municipality/access order"
            ),

        "offsets_file":
            OFFSETS_OUT.name,

        "transition_slots_file":
            SLOTS_OUT.name,

        "representation":
            (
                "CSR-like ordered sequence. "
                "For path_idx p, transition slots are "
                "transition_slots[offsets[p]:offsets[p+1]]."
            ),

        "transition_slot_semantics": {
            "slot_reference":
                (
                    "zero-based CSR data position in "
                    "frozen B5 arrays"
                ),

            "to_state":
                (
                    "osm_turn_state_time_v01.npz:"
                    "indices[slot]"
                ),

            "time_s":
                (
                    "osm_turn_state_time_v01.npz:"
                    "data[slot]"
                ),

            "length_m":
                (
                    "osm_turn_state_length_v01.npz:"
                    "data[slot]"
                ),

            "edge_id":
                (
                    "osm_turn_state_edgeid_v01.npz:"
                    "data[slot]"
                ),

            "physical_edge_lookup":
                (
                    "edge_id -> directed_edges.edge_id "
                    "in osm_directed_edges_v02.sqlite"
                ),

            "osm_physical_segment_lookup":
                (
                    "directed_edges.edge_id -> "
                    "directed_edges.segment_uid"
                ),

            "cumulative_time":
                (
                    "prefix sum of B5 time_s "
                    "over ordered path slots"
                ),

            "cumulative_length":
                (
                    "prefix sum of B5 length_m "
                    "over ordered path slots"
                ),
        },

        "cost_contract":
            "TIME_B5",

        "distance_semantics":
            "PATH_ATTRIBUTE",

        "weight_contract":
            "PRODUCT_LAMBDA / EXP_REL_300",

        "counts": {
            "paths":
                N_PATHS,

            "transition_slots":
                total_slots_expected,
        },
    }

    SEQ_CONTRACT.write_text(
        json.dumps(
            sequence_contract,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    emit(
        "Sequence representation = CSR-like B5 transition slots"
    )

    emit(
        "Physical edge / segment reconstruction = documented"
    )


    # =========================================================================
    # L. CANONICAL ARTIFACT HASHES
    # =========================================================================

    emit()
    emit("L. CANONICAL CANDIDATE HASHES")
    emit("-" * 124)

    artifact_paths = [
        ACCESS_PATHS,
        MUNICIPAL,
        OFFSETS_OUT,
        SLOTS_OUT,
        SEQ_CONTRACT,
        F1_REGRESSION,
    ]

    artifacts = {}

    for path in artifact_paths:

        digest = sha256_file(
            path
        )

        size = path.stat().st_size

        artifacts[
            path.name
        ] = {
            "size_bytes":
                int(size),

            "sha256":
                digest,
        }

        emit(
            f"{path.name:<45} "
            f"{digest}"
        )


    # =========================================================================
    # M. FINAL B2 CANDIDATE GATE
    # =========================================================================

    emit()
    emit("M. B2 CANDIDATE GATE")
    emit("-" * 124)

    hard(
        sequence_discontinuities == 0,
        "sequence_discontinuities != 0",
    )

    hard(
        source_mismatch == 0,
        "source_mismatch != 0",
    )

    hard(
        destination_mismatch == 0,
        "destination_mismatch != 0",
    )

    hard(
        forbidden_slot_violations == 0,
        "forbidden transition slot violations != 0",
    )

    hard(
        transition_count_mismatch == 0,
        "transition count mismatch != 0",
    )

    hard(
        nonpositive_time == 0,
        "nonpositive_time != 0",
    )

    hard(
        nonpositive_distance == 0,
        "nonpositive_distance != 0",
    )

    hard(
        nonpositive_weight == 0,
        "nonpositive_weight != 0",
    )

    hard(
        max_pair_sum_error <= PAIR_TOL,
        "PRODUCT-LAMBDA error exceeds tolerance.",
    )


    b1_qa = b1_gate["qa"]

    hard(
        int(
            b1_qa[
                "F3_matched_paths"
            ]
        )
        == 98_559,
        "B1 full F3 regression count mismatch.",
    )

    hard(
        int(
            b1_qa[
                "F3_target_state_mismatches"
            ]
        )
        == 0,
        "B1 F3 target-state mismatch.",
    )

    hard(
        int(
            b1_qa[
                "F3_transition_count_mismatches"
            ]
        )
        == 0,
        "B1 F3 transition mismatch.",
    )


    elapsed = (
        time.perf_counter()
        - start
    )


    candidate_manifest = {
        "phase":
            "FASE_5_7",

        "gate":
            "B2_CANONICAL_CANDIDATE",

        "verdict":
            "PASS",

        "IMPORTANT":
            (
                "CANDIDATE ONLY. "
                "No canonical 02_package promotion "
                "has occurred in B2."
            ),

        "cost_contract":
            "TIME_B5",

        "distance":
            "PATH_ATTRIBUTE",

        "weight_contract":
            "PRODUCT_LAMBDA / EXP_REL_300",

        "counts": {
            "municipal_OD":
                N_OD,

            "access_pair_paths":
                N_PATHS,

            "finite":
                N_PATHS,

            "unreachable":
                0,

            "reconstruction_failures":
                0,

            "transition_slots":
                total_slots_expected,
        },

        "qa": {
            "sequence_discontinuities":
                sequence_discontinuities,

            "source_mismatch":
                source_mismatch,

            "destination_mismatch":
                destination_mismatch,

            "forbidden_transition_slot_violations":
                forbidden_slot_violations,

            "transition_count_mismatch":
                transition_count_mismatch,

            "nonpositive_time":
                nonpositive_time,

            "nonpositive_distance":
                nonpositive_distance,

            "nonpositive_pair_weight":
                nonpositive_weight,

            "PRODUCT_LAMBDA_max_OD_sum_error":
                float(
                    max_pair_sum_error
                ),

            "B1_max_path_reconstruction_error_s":
                float(
                    b1_qa[
                        "max_path_time_reconstruction_error_s"
                    ]
                ),

            "F3_matched_paths":
                int(
                    b1_qa[
                        "F3_matched_paths"
                    ]
                ),

            "F3_max_time_error_s":
                float(
                    b1_qa[
                        "F3_max_time_error_s"
                    ]
                ),

            "F3_max_distance_error_m":
                float(
                    b1_qa[
                        "F3_max_distance_error_m"
                    ]
                ),

            "F3_target_state_mismatches":
                int(
                    b1_qa[
                        "F3_target_state_mismatches"
                    ]
                ),

            "F3_transition_count_mismatches":
                int(
                    b1_qa[
                        "F3_transition_count_mismatches"
                    ]
                ),

            "F1_sites":
                4,

            "F1_technical_failures":
                0,

            "F1_real_B5_regressions":
                0,

            "F1_result":
                "PASS",
        },

        "summary_time_statistics_s":
            time_stats,

        "summary_distance_statistics_km":
            distance_stats,

        "summary_time_spread_statistics_s":
            time_spread_stats,

        "summary_distance_spread_statistics_km":
            distance_spread_stats,

        "candidate_artifacts":
            artifacts,

        "frozen_F1_artifacts_sha256":
            f1_hashes,

        "A1_log_sha256":
            sha256_file(
                A1_LOG
            ),

        "B1_gate_sha256":
            sha256_file(
                B1_GATE
            ),

        "SYSTEMIC_issues":
            0,

        "BLOCKING_issues":
            0,

        "OD_PATH_SYSTEM_OSM":
            "NOT_FROZEN_YET",

        "next_step":
            (
                "B3 final promotion/freeze "
                "after review of this gate output."
            ),

        "elapsed_seconds":
            float(
                elapsed
            ),
    }


    MANIFEST.write_text(
        json.dumps(
            candidate_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest_sha = sha256_file(
        MANIFEST
    )


    # =========================================================================
    # FINAL
    # =========================================================================

    emit()
    emit("=" * 124)

    emit(
        "B2 CANONICAL CANDIDATE RESULT = PASS"
    )

    emit(
        "A — COST CONTRACT = PASS"
    )

    emit(
        "B — 414,090 / 414,090 "
        "ACCESS-PAIR PATHS = FINITE"
    )

    emit(
        "C — PATH RECONSTRUCTION = 100%"
    )

    emit(
        "D — PRODUCT-LAMBDA CONSISTENCY = PASS"
    )

    emit(
        "E — PATH SEQUENCE INTEGRITY = PASS"
    )

    emit(
        "F — B5/E2/F3 + F1 REGRESSION = PASS"
    )

    emit(
        "G — SYSTEMIC issues = 0"
    )

    emit(
        "H — BLOCKING issues = 0"
    )

    emit()

    emit(
        "OD_PATH_SYSTEM_OSM = NOT_FROZEN_YET"
    )

    emit(
        "No file has been promoted to "
        "02_package by B2."
    )

    emit(
        f"Candidate manifest SHA256 = "
        f"{manifest_sha}"
    )

    emit(
        "Next gate = B3 FINAL PROMOTION / FREEZE"
    )

    emit("=" * 124)

    emit()

    emit(
        "=== RUN COMPLETATA CORRETTAMENTE ==="
    )


except Exception as exc:

    emit()

    emit("=" * 124)

    emit(
        "B2 CANONICAL CANDIDATE RESULT = "
        "FAIL / BLOCKING CANDIDATE"
    )

    emit(
        f"{type(exc).__name__}: {exc}"
    )

    emit(
        "No canonical package promotion performed."
    )

    emit(
        "Do NOT modify B5, Gamma or B1 shards."
    )

    emit(
        "Do NOT start B3."
    )

    emit("=" * 124)

    emit()

    emit(
        "=== RUN TERMINATA CON ERRORE ==="
    )

    traceback.print_exc()

    raise


finally:

    if OUT.exists():

        LOG.write_text(
            "\n".join(
                lines
            ),
            encoding="utf-8",
        )

        print(
            f"\nLog salvato in:\n{LOG}"
        )
