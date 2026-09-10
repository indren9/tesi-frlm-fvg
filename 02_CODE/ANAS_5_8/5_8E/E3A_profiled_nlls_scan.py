"""
E3-A — PROFILED NLLS DENSE BETA SCAN
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Eseguire lo studio esplorativo del profile objective J(beta) dopo il
freeze E2:

    OBJECTIVE = UNWEIGHTED NONLINEAR LEAST SQUARES

    J(Q,beta) = sum_a [Y_a - Yhat_a(Q,beta)]^2

con PRIMARY finali:

    920032 — SS54
    920039 — SS52BIS
    920035 — SS202

Per ogni beta:

1. costruire
       W_ij(beta) = P_i A_j exp(-beta c_ij)

2. normalizzare
       S_ij(beta) = W_ij / sum_rs W_rs

3. calcolare, per ciascuna sezione a:
       G_a(beta) = sum_ij p_ij^a S_ij(beta)

4. usare:
       Yhat_a = C_a + Q G_a(beta)

5. profilare analiticamente Q:
       Q*(beta) =
       max(0,
           sum_a G_a(beta) [Y_a - C_a]
           /
           sum_a G_a(beta)^2
       )

6. calcolare:
       J_profile(beta)

Lo script esegue:
- GLOBAL DENSE BETA SCAN;
- LOCAL DENSE REFINEMENT;
- continuous bounded numerical minimization nella zona del miglior
  minimo osservato.

Il risultato di E3-A è DIAGNOSTICO.
Q e beta NON vengono congelati.

INPUTS
------
- Gravity_v0_territorial_inputs_derived_v01.xlsx
- OSM_OD_municipal_summary_v01.csv
- ISTAT_commuting_LIGHT_v0.xlsx
- ANAS_5_8D_calibration_mapping_v01.csv
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz

OUTPUTS
-------
Solo sotto:
C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\E3A_beta_profile

- E3A_final_primary_operator_candidate_v01.npz
- E3A_final_primary_OD_exposure_candidate_v01.csv
- E3A_beta_profile_candidate_v01.csv
- E3A_numerical_minimum_candidate_v01.csv
- E3A_01_J_profile_global.png
- E3A_02_J_profile_zoom.png
- E3A_03_Q_star_global.png
- E3A_04_J_normalized_global.png

ASSUMPTIONS
-----------
- Gravity v0 FVG-only.
- Exponential deterrence frozen.
- beta expressed in 1/minute.
- c_ij = TIME_B5 PRODUCT-LAMBDA municipal impedance, converted to minutes.
- PRODUCT-LAMBDA access-pair assignment frozen.
- Measurement operator = BIDIRECTIONAL_SUM.
- Q constrained to Q >= 0.
- ANAS 2024 only.
- ANAS 2025 explicitly excluded.

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA
- territorial Gravity v0 inputs
- ISTAT commuting LIGHT v0
- ANAS 5.8D canonical mapping

FILES NEVER MODIFIED
--------------------
Qualsiasi file sotto:
C:\\Tesi\\Tesi_QGIS\\02_package

Il canonical mapping ANAS 5.8D non viene modificato.
"""

from pathlib import Path
import csv
import math
import re

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

from scipy.sparse import load_npz
from scipy.optimize import minimize_scalar


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

GRAVITY_ROOT = ROOT / "02_package" / "gravity_v0_inputs"
OD_ROOT = ROOT / "02_package" / "od_paths_osm_light"
GRAPH_ROOT = ROOT / "02_package" / "grafo_operativo_osm"
ANAS_ROOT = ROOT / "02_package" / "anas_calibration_v0"

OUT_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E3A_beta_profile"
)

TERRITORIAL_XLSX = (
    GRAVITY_ROOT
    / "Gravity_v0_territorial_inputs_derived_v01.xlsx"
)

MUNICIPAL_SUMMARY = (
    OD_ROOT
    / "OSM_OD_municipal_summary_v01.csv"
)

COMMUTING_XLSX = (
    GRAVITY_ROOT
    / "ISTAT_commuting_LIGHT_v0.xlsx"
)

ANAS_MAPPING = (
    ANAS_ROOT
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

ACCESS_PATHS = (
    OD_ROOT
    / "OSM_OD_access_paths_v01.csv"
)

PATH_OFFSETS = (
    OD_ROOT
    / "OSM_OD_path_offsets_v01.npy"
)

TRANSITION_SLOTS = (
    OD_ROOT
    / "OSM_OD_transition_slots_v01.npy"
)

B5_EDGEID = (
    GRAPH_ROOT
    / "osm_turn_state_edgeid_v01.npz"
)

OPERATOR_OUT = (
    OUT_ROOT
    / "E3A_final_primary_operator_candidate_v01.npz"
)

OD_EXPOSURE_OUT = (
    OUT_ROOT
    / "E3A_final_primary_OD_exposure_candidate_v01.csv"
)

PROFILE_OUT = (
    OUT_ROOT
    / "E3A_beta_profile_candidate_v01.csv"
)

MINIMUM_OUT = (
    OUT_ROOT
    / "E3A_numerical_minimum_candidate_v01.csv"
)

PLOT_GLOBAL = (
    OUT_ROOT
    / "E3A_01_J_profile_global.png"
)

PLOT_ZOOM = (
    OUT_ROOT
    / "E3A_02_J_profile_zoom.png"
)

PLOT_Q = (
    OUT_ROOT
    / "E3A_03_Q_star_global.png"
)

PLOT_NORMALIZED = (
    OUT_ROOT
    / "E3A_04_J_normalized_global.png"
)


PRIMARY_IDS = [
    "920032",
    "920039",
    "920035",
]


# -----------------------------------------------------------------------------
# Exploratory beta domain.
# NOT a frozen methodological bound.
# -----------------------------------------------------------------------------

BETA_MIN = 0.0
BETA_MAX = 0.20

GLOBAL_POINTS = 5001

LOCAL_POINTS = 5001
LOCAL_HALF_WIDTH = 0.004

BETA_BLOCK_SIZE = 64

PATH_SCAN_CHUNK = 10_000_000


# -----------------------------------------------------------------------------
# Regression evidence already established in E1 / E1-C.
# Used only as QA.
# -----------------------------------------------------------------------------

EXPECTED_EXPOSURE = {
    "920032": {
        "PATH_HITS": 25935,
        "OD_P_GT_0": 2884,
        "C_A_APPROX": 1241.819,
    },
    "920039": {
        "PATH_HITS": 21265,
        "OD_P_GT_0": 2364,
        "C_A_APPROX": 1294.221,
    },
    "920035": {
        "PATH_HITS": 4470,
        "OD_P_GT_0": 639,
        "C_A_APPROX": 2275.155,
    },
}


# =============================================================================
# GENERIC HELPERS
# =============================================================================

def require_file(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"FILE NOT FOUND: {path}"
        )


def require_output_absent(path):
    if path.exists():
        raise FileExistsError(
            "OUTPUT ALREADY EXISTS — overwrite forbidden: "
            f"{path}"
        )


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_col(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower(),
    )


def parse_pipe_ints(value):
    text = clean(value)

    if not text:
        return []

    return [
        int(x.strip())
        for x in text.split("|")
        if x.strip()
    ]


def c_half(beta):
    if beta <= 0:
        return math.inf

    return math.log(2.0) / beta


# =============================================================================
# TERRITORIAL P_i / A_j
# =============================================================================

def find_alias_column(columns, aliases):
    normalized = {
        normalize_col(c): c
        for c in columns
    }

    for alias in aliases:
        key = normalize_col(alias)

        if key in normalized:
            return normalized[key]

    return None


def load_territorial():
    workbook = pd.ExcelFile(
        TERRITORIAL_XLSX
    )

    candidates = []

    pro_aliases = [
        "PRO_COM",
        "PROCOM",
    ]

    p_aliases = [
        "P_i",
        "P_i_v0",
        "P_ORIGIN_PROPENSITY",
        "ORIGIN_PROPENSITY",
        "PRODUCTION_PROPENSITY",
    ]

    a_aliases = [
        "A_j",
        "A_j_v0",
        "A_DESTINATION_PROPENSITY",
        "DESTINATION_ATTRACTION",
        "ATTRACTION_PROPENSITY",
    ]

    for sheet in workbook.sheet_names:
        df = pd.read_excel(
            TERRITORIAL_XLSX,
            sheet_name=sheet,
        )

        pro_col = find_alias_column(
            df.columns,
            pro_aliases,
        )

        p_col = find_alias_column(
            df.columns,
            p_aliases,
        )

        a_col = find_alias_column(
            df.columns,
            a_aliases,
        )

        if (
            pro_col is not None
            and p_col is not None
            and a_col is not None
        ):
            candidates.append(
                (
                    sheet,
                    df,
                    pro_col,
                    p_col,
                    a_col,
                )
            )

    if len(candidates) != 1:
        print()
        print("TERRITORIAL WORKBOOK SHEETS / COLUMNS:")

        for sheet in workbook.sheet_names:
            probe = pd.read_excel(
                TERRITORIAL_XLSX,
                sheet_name=sheet,
                nrows=2,
            )

            print(
                f"{sheet}: {list(probe.columns)}"
            )

        raise RuntimeError(
            "Could not uniquely resolve territorial "
            "PRO_COM / P_i / A_j schema."
        )

    (
        sheet,
        df,
        pro_col,
        p_col,
        a_col,
    ) = candidates[0]

    out = pd.DataFrame(
        {
            "PRO_COM":
                pd.to_numeric(
                    df[pro_col],
                    errors="raise",
                ).astype(np.int64),

            "P_i":
                pd.to_numeric(
                    df[p_col],
                    errors="raise",
                ).astype(np.float64),

            "A_j":
                pd.to_numeric(
                    df[a_col],
                    errors="raise",
                ).astype(np.float64),
        }
    )

    if len(out) != 215:
        raise RuntimeError(
            f"Expected 215 territorial rows, found {len(out)}"
        )

    if out["PRO_COM"].duplicated().any():
        raise RuntimeError(
            "Duplicate PRO_COM in territorial input."
        )

    if not np.isfinite(
        out[["P_i", "A_j"]].to_numpy()
    ).all():
        raise RuntimeError(
            "Non-finite P_i / A_j."
        )

    if (
        (out["P_i"] < 0).any()
        or (out["A_j"] < 0).any()
    ):
        raise RuntimeError(
            "Negative P_i / A_j."
        )

    return out, {
        "sheet": sheet,
        "pro_col": str(pro_col),
        "p_col": str(p_col),
        "a_col": str(a_col),
    }


# =============================================================================
# MUNICIPAL OD + IMPEDANCE
# =============================================================================

def load_municipal_od():
    df = pd.read_csv(
        MUNICIPAL_SUMMARY
    )

    required = {
        "origin_PRO_COM",
        "origin_COMUNE",
        "destination_PRO_COM",
        "destination_COMUNE",
        "time_s_PRODUCT_LAMBDA",
    }

    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            f"Municipal summary missing: {sorted(missing)}"
        )

    df = df[
        [
            "origin_PRO_COM",
            "origin_COMUNE",
            "destination_PRO_COM",
            "destination_COMUNE",
            "time_s_PRODUCT_LAMBDA",
        ]
    ].copy()

    df["origin_PRO_COM"] = pd.to_numeric(
        df["origin_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    df["destination_PRO_COM"] = pd.to_numeric(
        df["destination_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    df["c_min"] = (
        pd.to_numeric(
            df["time_s_PRODUCT_LAMBDA"],
            errors="raise",
        ).astype(np.float64)
        / 60.0
    )

    if len(df) != 46010:
        raise RuntimeError(
            f"Expected 46010 OD, found {len(df)}"
        )

    if df[
        [
            "origin_PRO_COM",
            "destination_PRO_COM",
        ]
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate municipal OD."
        )

    if not np.isfinite(
        df["c_min"].to_numpy()
    ).all():
        raise RuntimeError(
            "Non-finite c_ij."
        )

    if np.any(
        df["c_min"].to_numpy() <= 0
    ):
        raise RuntimeError(
            "Non-positive c_ij."
        )

    df = df.reset_index(
        drop=True
    )

    df["od_idx"] = np.arange(
        len(df),
        dtype=np.int64,
    )

    return df


# =============================================================================
# COMMUTING C_ij
# =============================================================================

def load_commuting(od):
    df = pd.read_excel(
        COMMUTING_XLSX,
        sheet_name="COMMUTING_OD",
    )

    required = {
        "ORIGIN_PRO_COM",
        "DESTINATION_PRO_COM",
        "C_ij_ISTAT_VEH_DAY",
    }

    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            "COMMUTING_OD missing columns: "
            f"{sorted(missing)}"
        )

    df = df[
        [
            "ORIGIN_PRO_COM",
            "DESTINATION_PRO_COM",
            "C_ij_ISTAT_VEH_DAY",
        ]
    ].copy()

    df.columns = [
        "origin_PRO_COM",
        "destination_PRO_COM",
        "C_ij_ISTAT",
    ]

    df["origin_PRO_COM"] = pd.to_numeric(
        df["origin_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    df["destination_PRO_COM"] = pd.to_numeric(
        df["destination_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    df["C_ij_ISTAT"] = pd.to_numeric(
        df["C_ij_ISTAT"],
        errors="raise",
    ).astype(np.float64)

    if len(df) != 46010:
        raise RuntimeError(
            f"Expected 46010 commuting OD, found {len(df)}"
        )

    merged = od[
        [
            "origin_PRO_COM",
            "destination_PRO_COM",
            "od_idx",
        ]
    ].merge(
        df,
        on=[
            "origin_PRO_COM",
            "destination_PRO_COM",
        ],
        how="left",
        validate="one_to_one",
    )

    if merged["C_ij_ISTAT"].isna().any():
        raise RuntimeError(
            "Commuting join incomplete."
        )

    return merged[
        "C_ij_ISTAT"
    ].to_numpy(
        dtype=np.float64
    )


# =============================================================================
# JOIN P_i / A_j TO OD
# =============================================================================

def build_gravity_base(
    od,
    territorial,
):
    p_lookup = territorial.set_index(
        "PRO_COM"
    )["P_i"]

    a_lookup = territorial.set_index(
        "PRO_COM"
    )["A_j"]

    p_origin = od[
        "origin_PRO_COM"
    ].map(
        p_lookup
    )

    a_destination = od[
        "destination_PRO_COM"
    ].map(
        a_lookup
    )

    if (
        p_origin.isna().any()
        or a_destination.isna().any()
    ):
        raise RuntimeError(
            "Territorial join incomplete."
        )

    base = (
        p_origin.to_numpy(
            dtype=np.float64
        )
        *
        a_destination.to_numpy(
            dtype=np.float64
        )
    )

    if not np.isfinite(
        base
    ).all():
        raise RuntimeError(
            "Non-finite P_i*A_j."
        )

    if np.any(
        base < 0
    ):
        raise RuntimeError(
            "Negative P_i*A_j."
        )

    if float(
        np.sum(base)
    ) <= 0:
        raise RuntimeError(
            "Gravity base has zero total mass."
        )

    return base


# =============================================================================
# FINAL ANAS PRIMARY MAPPING
# =============================================================================

def load_final_primary_mapping():
    result = {}

    with ANAS_MAPPING.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter=";",
        )

        for row in reader:
            section_id = clean(
                row["SECTION_ID"]
            )

            if section_id not in PRIMARY_IDS:
                continue

            result[section_id] = {
                "SECTION_ID":
                    section_id,

                "ROAD":
                    clean(
                        row["ROAD"]
                    ),

                "OBSERVED":
                    float(
                        row["TGMA_LIGHT_2024"]
                    ),

                "QUALITY_CLASS":
                    clean(
                        row["QUALITY_CLASS"]
                    ),

                "EXTERNAL_EXPOSURE":
                    clean(
                        row["EXTERNAL_EXPOSURE"]
                    ),

                "QGIS_REVIEW_STATUS":
                    clean(
                        row["QGIS_REVIEW_STATUS"]
                    ),

                "EDGE_IDS":
                    parse_pipe_ints(
                        row[
                            "RELEVANT_DIRECTED_EDGE_IDS"
                        ]
                    ),
            }

    missing = (
        set(PRIMARY_IDS)
        - set(result)
    )

    if missing:
        raise RuntimeError(
            f"Final primary missing from ANAS mapping: {sorted(missing)}"
        )

    for section_id in PRIMARY_IDS:
        if not result[
            section_id
        ]["EDGE_IDS"]:
            raise RuntimeError(
                f"{section_id}: no canonical edge IDs."
            )

        if (
            result[
                section_id
            ]["QGIS_REVIEW_STATUS"].upper()
            != "CLOSED"
        ):
            raise RuntimeError(
                f"{section_id}: QGIS review not CLOSED."
            )

    return result


# =============================================================================
# ACCESS PATH -> OD INDEX
# =============================================================================

def load_access_path_metadata(od):
    access = pd.read_csv(
        ACCESS_PATHS,
        usecols=[
            "path_idx",
            "origin_PRO_COM",
            "destination_PRO_COM",
            "pair_weight",
        ],
    )

    if len(access) != 414090:
        raise RuntimeError(
            f"Expected 414090 paths, found {len(access)}"
        )

    access["path_idx"] = pd.to_numeric(
        access["path_idx"],
        errors="raise",
    ).astype(np.int64)

    access["origin_PRO_COM"] = pd.to_numeric(
        access["origin_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    access["destination_PRO_COM"] = pd.to_numeric(
        access["destination_PRO_COM"],
        errors="raise",
    ).astype(np.int64)

    access["pair_weight"] = pd.to_numeric(
        access["pair_weight"],
        errors="raise",
    ).astype(np.float64)

    access = access.merge(
        od[
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
                "od_idx",
            ]
        ],
        on=[
            "origin_PRO_COM",
            "destination_PRO_COM",
        ],
        how="left",
        validate="many_to_one",
        sort=False,
    )

    if access["od_idx"].isna().any():
        raise RuntimeError(
            "Access path -> municipal OD join incomplete."
        )

    access = access.sort_values(
        "path_idx"
    ).reset_index(
        drop=True
    )

    expected_path_idx = np.arange(
        len(access),
        dtype=np.int64,
    )

    if not np.array_equal(
        access["path_idx"].to_numpy(),
        expected_path_idx,
    ):
        raise RuntimeError(
            "path_idx not canonical 0..414089."
        )

    od_counts = access.groupby(
        "od_idx"
    ).size()

    if (
        int(od_counts.min()) != 9
        or int(od_counts.max()) != 9
    ):
        raise RuntimeError(
            "Expected exactly 9 access paths per OD."
        )

    weight_sums = access.groupby(
        "od_idx"
    )["pair_weight"].sum()

    max_weight_error = float(
        np.max(
            np.abs(
                weight_sums.to_numpy()
                - 1.0
            )
        )
    )

    if max_weight_error > 1e-10:
        raise RuntimeError(
            "PRODUCT-LAMBDA weight sum failure: "
            f"{max_weight_error:.3e}"
        )

    path_to_od = access[
        "od_idx"
    ].to_numpy(
        dtype=np.int64
    )

    pair_weight = access[
        "pair_weight"
    ].to_numpy(
        dtype=np.float64
    )

    return (
        path_to_od,
        pair_weight,
        max_weight_error,
    )


# =============================================================================
# SCAN FROZEN PATHS FOR FINAL PRIMARY SET
# =============================================================================

def scan_final_primary_paths(
    mapping,
):
    offsets = np.load(
        PATH_OFFSETS,
        mmap_mode="r",
    )

    transitions = np.load(
        TRANSITION_SLOTS,
        mmap_mode="r",
    )

    b5_edgeid = load_npz(
        B5_EDGEID
    ).tocsr()

    if len(offsets) != 414091:
        raise RuntimeError(
            f"Unexpected offsets length: {len(offsets)}"
        )

    if len(transitions) != 598707601:
        raise RuntimeError(
            "Unexpected transition slot count: "
            f"{len(transitions)}"
        )

    bit_by_section = {
        section_id: np.uint8(
            1 << idx
        )
        for idx, section_id
        in enumerate(PRIMARY_IDS)
    }

    slot_mask = np.zeros(
        b5_edgeid.nnz,
        dtype=np.uint8,
    )

    print()
    print("G. FINAL PRIMARY EDGE QA")
    print("-" * 100)

    for section_id in PRIMARY_IDS:
        bit = bit_by_section[
            section_id
        ]

        for edge_id in mapping[
            section_id
        ]["EDGE_IDS"]:

            matches = np.flatnonzero(
                b5_edgeid.data
                == edge_id
            )

            print(
                f"{section_id} | "
                f"EDGE_ID={edge_id} | "
                f"B5_SLOT_OCCURRENCES={len(matches)}"
            )

            if len(matches) != 1:
                raise RuntimeError(
                    f"{section_id}: EDGE_ID {edge_id} "
                    f"expected exactly once in B5."
                )

            slot_mask[
                matches
            ] |= bit

    path_hits = {
        section_id: set()
        for section_id
        in PRIMARY_IDS
    }

    n_slots = len(
        transitions
    )

    print()
    print("H. FROZEN PATH SCAN")
    print("-" * 100)

    print(
        "TRANSITION_SLOTS =",
        f"{n_slots:,}",
    )

    next_progress = 10

    for lo in range(
        0,
        n_slots,
        PATH_SCAN_CHUNK,
    ):
        hi = min(
            lo + PATH_SCAN_CHUNK,
            n_slots,
        )

        slots = transitions[
            lo:hi
        ]

        masks = slot_mask[
            slots
        ]

        local = np.flatnonzero(
            masks
        )

        if local.size > 0:
            global_positions = (
                local + lo
            )

            path_idx = (
                np.searchsorted(
                    offsets,
                    global_positions,
                    side="right",
                )
                - 1
            )

            matched_masks = masks[
                local
            ]

            for section_id in PRIMARY_IDS:
                bit = bit_by_section[
                    section_id
                ]

                relevant = (
                    matched_masks & bit
                ) != 0

                if not np.any(
                    relevant
                ):
                    continue

                unique_paths = np.unique(
                    path_idx[
                        relevant
                    ]
                )

                path_hits[
                    section_id
                ].update(
                    map(
                        int,
                        unique_paths,
                    )
                )

        progress = int(
            100 * hi / n_slots
        )

        if (
            progress >= next_progress
            or hi == n_slots
        ):
            print(
                f"SCAN_PROGRESS = {progress:3d}%"
            )

            while next_progress <= progress:
                next_progress += 10

    return path_hits


# =============================================================================
# BUILD p_ij^a
# =============================================================================

def build_exposure_operator(
    path_hits,
    path_to_od,
    pair_weight,
    n_od,
):
    p_matrix = np.zeros(
        (
            len(PRIMARY_IDS),
            n_od,
        ),
        dtype=np.float64,
    )

    n_paths_by_od = {}

    print()
    print("I. FINAL PRIMARY MODEL EXPOSURE")
    print("=" * 100)

    for a_idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        paths = np.asarray(
            sorted(
                path_hits[
                    section_id
                ]
            ),
            dtype=np.int64,
        )

        if len(paths) == 0:
            raise RuntimeError(
                f"{section_id}: zero path exposure."
            )

        p = np.bincount(
            path_to_od[
                paths
            ],
            weights=pair_weight[
                paths
            ],
            minlength=n_od,
        ).astype(
            np.float64
        )

        counts = np.bincount(
            path_to_od[
                paths
            ],
            minlength=n_od,
        ).astype(
            np.int64
        )

        if np.any(
            p > 1.0 + 1e-10
        ):
            raise RuntimeError(
                f"{section_id}: p_ij^a > 1."
            )

        p = np.minimum(
            p,
            1.0,
        )

        p_matrix[
            a_idx,
            :
        ] = p

        n_paths_by_od[
            section_id
        ] = counts

        path_count = int(
            len(paths)
        )

        od_count = int(
            np.count_nonzero(
                p > 0
            )
        )

        expected = EXPECTED_EXPOSURE[
            section_id
        ]

        if (
            path_count
            != expected["PATH_HITS"]
            or od_count
            != expected["OD_P_GT_0"]
        ):
            raise RuntimeError(
                f"{section_id}: E1 regression mismatch. "
                f"PATH={path_count}, OD={od_count}"
            )

        print(
            f"{section_id} | "
            f"PATH_HITS={path_count} | "
            f"OD_P_GT_0={od_count} | "
            f"P_MAX={float(np.max(p)):.12f}"
        )

    return (
        p_matrix,
        n_paths_by_od,
    )


# =============================================================================
# PROFILE OBJECTIVE
# =============================================================================

def evaluate_beta_grid(
    betas,
    base,
    c_min,
    p_matrix,
    observed,
    commuting_assigned,
    scan_scope,
):
    betas = np.asarray(
        betas,
        dtype=np.float64,
    )

    n = len(
        betas
    )

    q_star = np.empty(
        n,
        dtype=np.float64,
    )

    j_profile = np.empty(
        n,
        dtype=np.float64,
    )

    rel_sse = np.empty(
        n,
        dtype=np.float64,
    )

    modelled = np.empty(
        (
            n,
            len(PRIMARY_IDS),
        ),
        dtype=np.float64,
    )

    residual = np.empty_like(
        modelled
    )

    rel_error = np.empty_like(
        modelled
    )

    g_all = np.empty_like(
        modelled
    )

    target_nonpendular = (
        observed
        - commuting_assigned
    )

    for lo in range(
        0,
        n,
        BETA_BLOCK_SIZE,
    ):
        hi = min(
            lo + BETA_BLOCK_SIZE,
            n,
        )

        beta_block = betas[
            lo:hi
        ]

        weights = np.exp(
            -beta_block[:, None]
            * c_min[None, :]
        )

        weights *= base[
            None,
            :
        ]

        denom = np.sum(
            weights,
            axis=1,
        )

        if np.any(
            denom <= 0
        ):
            raise RuntimeError(
                "Gravity normalization denominator <= 0."
            )

        # Numerator for each ANAS section:
        # sum_ij p_ij^a W_ij(beta)
        g = (
            weights
            @ p_matrix.T
        )

        g /= denom[
            :, None
        ]

        g_all[
            lo:hi,
            :
        ] = g

        q_num = (
            g
            @ target_nonpendular
        )

        q_den = np.sum(
            g * g,
            axis=1,
        )

        if np.any(
            q_den <= 0
        ):
            raise RuntimeError(
                "Profile Q denominator <= 0."
            )

        q_unconstrained = (
            q_num
            / q_den
        )

        q = np.maximum(
            0.0,
            q_unconstrained,
        )

        pred = (
            commuting_assigned[
                None,
                :
            ]
            +
            q[:, None]
            * g
        )

        res = (
            observed[
                None,
                :
            ]
            - pred
        )

        rel = (
            res
            / observed[
                None,
                :
            ]
        )

        q_star[
            lo:hi
        ] = q

        modelled[
            lo:hi,
            :
        ] = pred

        residual[
            lo:hi,
            :
        ] = res

        rel_error[
            lo:hi,
            :
        ] = rel

        j_profile[
            lo:hi
        ] = np.sum(
            res * res,
            axis=1,
        )

        rel_sse[
            lo:hi
        ] = np.sum(
            rel * rel,
            axis=1,
        )

    data = {
        "scan_scope":
            np.repeat(
                scan_scope,
                n,
            ),

        "beta":
            betas,

        "c_half_min":
            np.array(
                [
                    c_half(x)
                    for x in betas
                ],
                dtype=np.float64,
            ),

        "Q_star":
            q_star,

        "J_profile":
            j_profile,

        # Deliberate duplicate semantic field requested by contract.
        "SSE_absolute":
            j_profile.copy(),

        "relative_SSE_diagnostic":
            rel_sse,
    }

    for a_idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        data[
            f"G_{section_id}"
        ] = g_all[
            :,
            a_idx
        ]

        data[
            f"observed_{section_id}"
        ] = np.repeat(
            observed[
                a_idx
            ],
            n,
        )

        data[
            f"modelled_{section_id}"
        ] = modelled[
            :,
            a_idx
        ]

        data[
            f"residual_veh_day_{section_id}"
        ] = residual[
            :,
            a_idx
        ]

        data[
            f"relative_error_{section_id}"
        ] = rel_error[
            :,
            a_idx
        ]

    return pd.DataFrame(
        data
    )


def evaluate_single_beta(
    beta,
    base,
    c_min,
    p_matrix,
    observed,
    commuting_assigned,
):
    df = evaluate_beta_grid(
        np.array(
            [beta],
            dtype=np.float64,
        ),
        base,
        c_min,
        p_matrix,
        observed,
        commuting_assigned,
        "NUMERICAL",
    )

    return df.iloc[
        0
    ]


# =============================================================================
# OD EXPOSURE EXPORT — FINAL PRIMARY ONLY
# =============================================================================

def build_od_exposure_export(
    od,
    p_matrix,
    n_paths_by_od,
):
    frames = []

    for a_idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        p = p_matrix[
            a_idx,
            :
        ]

        mask = (
            p > 0
        )

        part = od.loc[
            mask,
            [
                "origin_PRO_COM",
                "origin_COMUNE",
                "destination_PRO_COM",
                "destination_COMUNE",
            ],
        ].copy()

        part.insert(
            0,
            "SECTION_ID",
            section_id,
        )

        part[
            "n_access_paths_hitting"
        ] = n_paths_by_od[
            section_id
        ][
            mask
        ]

        part[
            "p_ij_a"
        ] = p[
            mask
        ]

        frames.append(
            part
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


# =============================================================================
# PLOTS
# =============================================================================

def save_plots(
    global_df,
    local_df,
    minimum_row,
):
    beta_opt = float(
        minimum_row[
            "beta"
        ]
    )

    q_opt = float(
        minimum_row[
            "Q_star"
        ]
    )

    j_opt = float(
        minimum_row[
            "J_profile"
        ]
    )

    # 1. Raw global J(beta)
    fig, ax = plt.subplots()

    ax.plot(
        global_df["beta"],
        global_df["J_profile"],
    )

    ax.scatter(
        [beta_opt],
        [j_opt],
    )

    ax.set_xlabel(
        "beta [1/min]"
    )

    ax.set_ylabel(
        "J_profile = absolute SSE [(veh/day)^2]"
    )

    ax.set_title(
        "E3-A — Global profile objective"
    )

    ax.text(
        beta_opt,
        j_opt,
        (
            f"beta={beta_opt:.10f}\n"
            f"Q*={q_opt:.3f}\n"
            f"J={j_opt:.3f}"
        ),
    )

    fig.tight_layout()

    fig.savefig(
        PLOT_GLOBAL,
        dpi=180,
    )

    plt.close(
        fig
    )

    # 2. Local zoom
    fig, ax = plt.subplots()

    ax.plot(
        local_df["beta"],
        local_df["J_profile"],
    )

    ax.scatter(
        [beta_opt],
        [j_opt],
    )

    ax.set_xlabel(
        "beta [1/min]"
    )

    ax.set_ylabel(
        "J_profile = absolute SSE [(veh/day)^2]"
    )

    ax.set_title(
        "E3-A — Local minimum zoom"
    )

    ax.text(
        beta_opt,
        j_opt,
        (
            f"beta={beta_opt:.10f}\n"
            f"Q*={q_opt:.3f}"
        ),
    )

    fig.tight_layout()

    fig.savefig(
        PLOT_ZOOM,
        dpi=180,
    )

    plt.close(
        fig
    )

    # 3. Q*(beta)
    fig, ax = plt.subplots()

    ax.plot(
        global_df["beta"],
        global_df["Q_star"],
    )

    ax.scatter(
        [beta_opt],
        [q_opt],
    )

    ax.set_xlabel(
        "beta [1/min]"
    )

    ax.set_ylabel(
        "Q*(beta) [veh/day]"
    )

    ax.set_title(
        "E3-A — Profiled Q*(beta)"
    )

    fig.tight_layout()

    fig.savefig(
        PLOT_Q,
        dpi=180,
    )

    plt.close(
        fig
    )

    # 4. Normalized J/Jmin
    fig, ax = plt.subplots()

    ax.plot(
        global_df["beta"],
        global_df["J_profile"]
        / j_opt,
    )

    ax.scatter(
        [beta_opt],
        [1.0],
    )

    ax.set_xlabel(
        "beta [1/min]"
    )

    ax.set_ylabel(
        "J_profile / J_min"
    )

    ax.set_title(
        "E3-A — Normalized global objective"
    )

    fig.tight_layout()

    fig.savefig(
        PLOT_NORMALIZED,
        dpi=180,
    )

    plt.close(
        fig
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 110)
    print(
        "E3-A — PROFILED NLLS DENSE BETA SCAN"
    )
    print("=" * 110)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. FROZEN E2 CONTRACT")
    print("-" * 110)

    print(
        "OBJECTIVE = UNWEIGHTED NONLINEAR LEAST SQUARES"
    )

    print(
        "PRIMARY = "
        + "|".join(
            PRIMARY_IDS
        )
    )

    print(
        "CUSTOM_WEIGHTS = NO"
    )

    print(
        "ROBUST_LOSS = NO"
    )

    print(
        "RELATIVE_SSE = DIAGNOSTIC_ONLY"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    # -------------------------------------------------------------------------
    # B. Exploratory scan contract — printed BEFORE execution
    # -------------------------------------------------------------------------

    global_step = (
        BETA_MAX
        - BETA_MIN
    ) / (
        GLOBAL_POINTS
        - 1
    )

    print()
    print("B. EXPLORATORY BETA RANGE — NOT FROZEN")
    print("-" * 110)

    print(
        f"BETA_MIN = {BETA_MIN:.6f} 1/min"
    )

    print(
        f"BETA_MAX = {BETA_MAX:.6f} 1/min"
    )

    print(
        "C_HALF_AT_BETA_MIN = INF min "
        "(NO DISTANCE DETERRENCE)"
    )

    print(
        "C_HALF_AT_BETA_MAX = "
        f"{c_half(BETA_MAX):.6f} min"
    )

    print(
        "C_HALF_EXPLORED_RANGE = "
        f"[{c_half(BETA_MAX):.6f} min, INF)"
    )

    print(
        f"GLOBAL_POINTS = {GLOBAL_POINTS}"
    )

    print(
        f"GLOBAL_STEP = {global_step:.10f} 1/min"
    )

    print(
        f"LOCAL_POINTS = {LOCAL_POINTS}"
    )

    print(
        "LOCAL_REFINEMENT = "
        f"+/- {LOCAL_HALF_WIDTH:.6f} 1/min "
        "around best global grid point, clipped to global range"
    )

    # -------------------------------------------------------------------------
    # C. Preflight
    # -------------------------------------------------------------------------

    print()
    print("C. FILE PREFLIGHT")
    print("-" * 110)

    input_files = [
        TERRITORIAL_XLSX,
        MUNICIPAL_SUMMARY,
        COMMUTING_XLSX,
        ANAS_MAPPING,
        ACCESS_PATHS,
        PATH_OFFSETS,
        TRANSITION_SLOTS,
        B5_EDGEID,
    ]

    for path in input_files:
        require_file(
            path
        )

        print(
            "PASS =",
            path,
        )

    OUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_files = [
        OPERATOR_OUT,
        OD_EXPOSURE_OUT,
        PROFILE_OUT,
        MINIMUM_OUT,
        PLOT_GLOBAL,
        PLOT_ZOOM,
        PLOT_Q,
        PLOT_NORMALIZED,
    ]

    for path in output_files:
        require_output_absent(
            path
        )

    # -------------------------------------------------------------------------
    # D. Load Gravity inputs
    # -------------------------------------------------------------------------

    territorial, territorial_schema = (
        load_territorial()
    )

    od = load_municipal_od()

    commuting = load_commuting(
        od
    )

    base = build_gravity_base(
        od,
        territorial,
    )

    c_min = od[
        "c_min"
    ].to_numpy(
        dtype=np.float64
    )

    print()
    print("D. GRAVITY INPUT QA")
    print("-" * 110)

    print(
        "TERRITORIAL_SHEET =",
        territorial_schema[
            "sheet"
        ],
    )

    print(
        "P_COLUMN =",
        territorial_schema[
            "p_col"
        ],
    )

    print(
        "A_COLUMN =",
        territorial_schema[
            "a_col"
        ],
    )

    print(
        f"TERRITORIAL_ROWS = {len(territorial)}"
    )

    print(
        f"SUM_P_i = {territorial['P_i'].sum():.15f}"
    )

    print(
        f"SUM_A_j = {territorial['A_j'].sum():.15f}"
    )

    print(
        f"OD_ROWS = {len(od)}"
    )

    print(
        f"C_MIN_MIN = {float(np.min(c_min)):.6f} min"
    )

    print(
        f"C_MIN_MAX = {float(np.max(c_min)):.6f} min"
    )

    # -------------------------------------------------------------------------
    # E. Final primary mapping
    # -------------------------------------------------------------------------

    mapping = (
        load_final_primary_mapping()
    )

    print()
    print("E. FINAL PRIMARY SET")
    print("-" * 110)

    for section_id in PRIMARY_IDS:
        x = mapping[
            section_id
        ]

        print(
            f"{section_id} | "
            f"ROAD={x['ROAD']} | "
            f"OBSERVED_2024={x['OBSERVED']:.3f} | "
            f"QUALITY={x['QUALITY_CLASS']} | "
            f"EXTERNAL={x['EXTERNAL_EXPOSURE']} | "
            f"EDGES={x['EDGE_IDS']}"
        )

    # -------------------------------------------------------------------------
    # F. Access path metadata
    # -------------------------------------------------------------------------

    (
        path_to_od,
        pair_weight,
        max_weight_error,
    ) = load_access_path_metadata(
        od
    )

    print()
    print("F. PRODUCT-LAMBDA QA")
    print("-" * 110)

    print(
        f"PATH_ROWS = {len(path_to_od)}"
    )

    print(
        "PATHS_PER_OD = 9"
    )

    print(
        "MAX_OD_PAIR_WEIGHT_SUM_ERROR = "
        f"{max_weight_error:.3e}"
    )

    # -------------------------------------------------------------------------
    # G/H. Frozen path scan
    # -------------------------------------------------------------------------

    path_hits = scan_final_primary_paths(
        mapping
    )

    # -------------------------------------------------------------------------
    # I. Build final p_ij^a
    # -------------------------------------------------------------------------

    (
        p_matrix,
        n_paths_by_od,
    ) = build_exposure_operator(
        path_hits,
        path_to_od,
        pair_weight,
        len(od),
    )

    observed = np.array(
        [
            mapping[
                section_id
            ]["OBSERVED"]
            for section_id in PRIMARY_IDS
        ],
        dtype=np.float64,
    )

    commuting_assigned = (
        p_matrix
        @ commuting
    )

    print()
    print("J. ASSIGNED COMMUTING QA")
    print("=" * 110)

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        c_a = float(
            commuting_assigned[
                idx
            ]
        )

        expected = EXPECTED_EXPOSURE[
            section_id
        ]["C_A_APPROX"]

        delta = abs(
            c_a - expected
        )

        print(
            f"{section_id} | "
            f"C_a_ISTAT={c_a:.6f} | "
            f"PREVIOUS_APPROX={expected:.3f} | "
            f"ABS_DELTA={delta:.6f}"
        )

        if delta > 0.01:
            raise RuntimeError(
                f"{section_id}: commuting assignment "
                f"regression mismatch."
            )

    # -------------------------------------------------------------------------
    # Materialize reusable temporary operator.
    # -------------------------------------------------------------------------

    np.savez_compressed(
        OPERATOR_OUT,

        primary_ids=np.array(
            PRIMARY_IDS
        ),

        origin_PRO_COM=od[
            "origin_PRO_COM"
        ].to_numpy(
            dtype=np.int64
        ),

        destination_PRO_COM=od[
            "destination_PRO_COM"
        ].to_numpy(
            dtype=np.int64
        ),

        c_min=c_min,

        gravity_base=base,

        C_ij_ISTAT=commuting,

        p_matrix=p_matrix,

        observed_2024=observed,

        commuting_assigned=commuting_assigned,
    )

    # -------------------------------------------------------------------------
    # Final-primary OD exposure file.
    # -------------------------------------------------------------------------

    exposure_export = (
        build_od_exposure_export(
            od,
            p_matrix,
            n_paths_by_od,
        )
    )

    exposure_export.to_csv(
        OD_EXPOSURE_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # K. Global dense scan
    # -------------------------------------------------------------------------

    print()
    print("K. GLOBAL DENSE BETA SCAN")
    print("=" * 110)

    global_betas = np.linspace(
        BETA_MIN,
        BETA_MAX,
        GLOBAL_POINTS,
        dtype=np.float64,
    )

    global_df = evaluate_beta_grid(
        global_betas,
        base,
        c_min,
        p_matrix,
        observed,
        commuting_assigned,
        "GLOBAL",
    )

    global_best_idx = int(
        global_df[
            "J_profile"
        ].idxmin()
    )

    global_best_beta = float(
        global_df.loc[
            global_best_idx,
            "beta",
        ]
    )

    global_best_q = float(
        global_df.loc[
            global_best_idx,
            "Q_star",
        ]
    )

    global_best_j = float(
        global_df.loc[
            global_best_idx,
            "J_profile",
        ]
    )

    print(
        f"GLOBAL_GRID_BEST_BETA = {global_best_beta:.10f}"
    )

    print(
        f"GLOBAL_GRID_BEST_Q = {global_best_q:.6f}"
    )

    print(
        f"GLOBAL_GRID_BEST_J = {global_best_j:.6f}"
    )

    # -------------------------------------------------------------------------
    # L. Local dense refinement
    # -------------------------------------------------------------------------

    local_lo = max(
        BETA_MIN,
        global_best_beta
        - LOCAL_HALF_WIDTH,
    )

    local_hi = min(
        BETA_MAX,
        global_best_beta
        + LOCAL_HALF_WIDTH,
    )

    local_betas = np.linspace(
        local_lo,
        local_hi,
        LOCAL_POINTS,
        dtype=np.float64,
    )

    local_step = (
        local_hi
        - local_lo
    ) / (
        LOCAL_POINTS
        - 1
    )

    print()
    print("L. LOCAL DENSE REFINEMENT")
    print("=" * 110)

    print(
        f"LOCAL_BETA_MIN = {local_lo:.10f}"
    )

    print(
        f"LOCAL_BETA_MAX = {local_hi:.10f}"
    )

    print(
        f"LOCAL_POINTS = {LOCAL_POINTS}"
    )

    print(
        f"LOCAL_STEP = {local_step:.12f} 1/min"
    )

    local_df = evaluate_beta_grid(
        local_betas,
        base,
        c_min,
        p_matrix,
        observed,
        commuting_assigned,
        "LOCAL",
    )

    local_best_idx = int(
        local_df[
            "J_profile"
        ].idxmin()
    )

    local_best_beta = float(
        local_df.loc[
            local_best_idx,
            "beta",
        ]
    )

    local_best_j = float(
        local_df.loc[
            local_best_idx,
            "J_profile",
        ]
    )

    print(
        f"LOCAL_GRID_BEST_BETA = {local_best_beta:.12f}"
    )

    print(
        f"LOCAL_GRID_BEST_J = {local_best_j:.6f}"
    )

    # -------------------------------------------------------------------------
    # M. Continuous numerical refinement
    # -------------------------------------------------------------------------

    print()
    print("M. CONTINUOUS NUMERICAL REFINEMENT")
    print("=" * 110)

    def scalar_objective(beta):
        row = evaluate_single_beta(
            beta,
            base,
            c_min,
            p_matrix,
            observed,
            commuting_assigned,
        )

        return float(
            row[
                "J_profile"
            ]
        )

    opt = minimize_scalar(
        scalar_objective,
        bounds=(
            local_lo,
            local_hi,
        ),
        method="bounded",
        options={
            "xatol": 1e-11,
            "maxiter": 500,
        },
    )

    # Explicitly compare optimizer result and local interval endpoints.
    numerical_candidates = [
        local_lo,
        float(opt.x),
        local_hi,
    ]

    candidate_rows = [
        evaluate_single_beta(
            beta,
            base,
            c_min,
            p_matrix,
            observed,
            commuting_assigned,
        )
        for beta
        in numerical_candidates
    ]

    minimum_row = min(
        candidate_rows,
        key=lambda row:
            float(
                row[
                    "J_profile"
                ]
            ),
    )

    beta_opt = float(
        minimum_row[
            "beta"
        ]
    )

    q_opt = float(
        minimum_row[
            "Q_star"
        ]
    )

    j_opt = float(
        minimum_row[
            "J_profile"
        ]
    )

    print(
        f"OPTIMIZER_SUCCESS = {opt.success}"
    )

    print(
        f"BETA_NUMERICAL_MIN = {beta_opt:.12f}"
    )

    print(
        f"C_HALF_AT_NUMERICAL_MIN = "
        f"{c_half(beta_opt):.6f} min"
        if beta_opt > 0
        else
        "C_HALF_AT_NUMERICAL_MIN = INF min"
    )

    print(
        f"Q_AT_NUMERICAL_MIN = {q_opt:.6f}"
    )

    print(
        f"J_NUMERICAL_MIN = {j_opt:.6f}"
    )

    # -------------------------------------------------------------------------
    # N. Profile diagnostics — no automatic methodological judgement.
    # -------------------------------------------------------------------------

    j_global = global_df[
        "J_profile"
    ].to_numpy(
        dtype=np.float64
    )

    local_min_indices = (
        np.flatnonzero(
            (
                j_global[
                    1:-1
                ]
                <=
                j_global[
                    :-2
                ]
            )
            &
            (
                j_global[
                    1:-1
                ]
                <=
                j_global[
                    2:
                ]
            )
        )
        + 1
    )

    near_best_1pct = global_df[
        global_df[
            "J_profile"
        ]
        <=
        j_opt * 1.01
    ]

    if len(
        near_best_1pct
    ) > 0:
        width_1pct = float(
            near_best_1pct[
                "beta"
            ].max()
            -
            near_best_1pct[
                "beta"
            ].min()
        )
    else:
        width_1pct = 0.0

    boundary_distance = min(
        beta_opt - BETA_MIN,
        BETA_MAX - beta_opt,
    )

    print()
    print("N. PROFILE SHAPE DIAGNOSTICS")
    print("=" * 110)

    print(
        f"GLOBAL_GRID_LOCAL_MINIMA_COUNT = {len(local_min_indices)}"
    )

    print(
        f"BETA_WIDTH_WITHIN_1PCT_OF_J_MIN = "
        f"{width_1pct:.10f}"
    )

    print(
        f"DISTANCE_FROM_NEAREST_BETA_BOUNDARY = "
        f"{boundary_distance:.10f}"
    )

    print(
        f"J_AT_BETA_MIN = "
        f"{float(global_df.iloc[0]['J_profile']):.6f}"
    )

    print(
        f"J_AT_BETA_MAX = "
        f"{float(global_df.iloc[-1]['J_profile']):.6f}"
    )

    print(
        "PROFILE_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    # -------------------------------------------------------------------------
    # O. Primary values at numerical minimum
    # -------------------------------------------------------------------------

    print()
    print("O. PRIMARY DIAGNOSTICS AT NUMERICAL MINIMUM")
    print("=" * 130)

    for section_id in PRIMARY_IDS:
        observed_value = float(
            minimum_row[
                f"observed_{section_id}"
            ]
        )

        modelled_value = float(
            minimum_row[
                f"modelled_{section_id}"
            ]
        )

        residual_value = float(
            minimum_row[
                f"residual_veh_day_{section_id}"
            ]
        )

        relative_value = float(
            minimum_row[
                f"relative_error_{section_id}"
            ]
        )

        print(
            f"{section_id} | "
            f"OBSERVED={observed_value:.3f} | "
            f"MODELLED={modelled_value:.3f} | "
            f"RESIDUAL={residual_value:.3f} | "
            f"REL_ERROR={relative_value:.6f}"
        )

    print(
        "RELATIVE_SSE_DIAGNOSTIC = "
        f"{float(minimum_row['relative_SSE_diagnostic']):.12f}"
    )

    # -------------------------------------------------------------------------
    # P. Save profile data
    # -------------------------------------------------------------------------

    numerical_df = pd.DataFrame(
        [
            minimum_row.to_dict()
        ]
    )

    profile_all = pd.concat(
        [
            global_df,
            local_df,
            numerical_df,
        ],
        ignore_index=True,
    )

    profile_all.to_csv(
        PROFILE_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    numerical_df.to_csv(
        MINIMUM_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # Q. Plots
    # -------------------------------------------------------------------------

    save_plots(
        global_df,
        local_df,
        minimum_row,
    )

    print()
    print("P. OUTPUTS")
    print("-" * 110)

    print(
        "OPERATOR_FILE =",
        OPERATOR_OUT,
    )

    print(
        "FINAL_PRIMARY_OD_EXPOSURE =",
        OD_EXPOSURE_OUT,
    )

    print(
        "PROFILE_CSV =",
        PROFILE_OUT,
    )

    print(
        "NUMERICAL_MINIMUM_CSV =",
        MINIMUM_OUT,
    )

    print(
        "PLOT_1_GLOBAL_RAW =",
        PLOT_GLOBAL,
    )

    print(
        "PLOT_2_LOCAL_ZOOM =",
        PLOT_ZOOM,
    )

    print(
        "PLOT_3_Q_PROFILE =",
        PLOT_Q,
    )

    print(
        "PLOT_4_NORMALIZED =",
        PLOT_NORMALIZED,
    )

    print()
    print("Q. E3-A GATE STATE")
    print("=" * 110)

    print(
        f"BETA_GRID_POINTS = "
        f"{GLOBAL_POINTS} GLOBAL + {LOCAL_POINTS} LOCAL"
    )

    print(
        f"BETA_GLOBAL_MIN = {beta_opt:.12f}"
    )

    print(
        f"Q_AT_GLOBAL_MIN = {q_opt:.6f}"
    )

    print(
        f"J_MIN = {j_opt:.6f}"
    )

    print(
        "BETA_FROZEN = NO"
    )

    print(
        "Q_FROZEN = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    print(
        "TEMPORAL_VALIDATION_STARTED = NO"
    )

    print(
        "E3A_STATUS = "
        "EXPLORATORY_PROFILE_COMPLETE / "
        "AWAITING_CHAT_INTERPRETATION"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

