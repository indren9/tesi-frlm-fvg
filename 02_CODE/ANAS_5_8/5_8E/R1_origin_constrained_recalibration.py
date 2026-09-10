"""
5.8E-R1 — ORIGIN-CONSTRAINED GRAVITY RECALIBRATION
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Implementare e calibrare la nuova baseline:

ORIGIN-CONSTRAINED GRAVITY

Per i != j:

    N_ij =
        Q * P_i *
        [
            A_j * exp(-beta*c_ij)
            /
            SUM_{s != i}
            A_s * exp(-beta*c_is)
        ]

N_ii = 0 / excluded.

P_i è un HARD RELATIVE ORIGIN SHARE.

A_j resta una RELATIVE DESTINATION ATTRACTIVENESS PROXY
e NON costituisce un hard destination margin.

CALIBRATION
-----------
PRIMARY:
    920032
    920039
    920035

OBJECTIVE:
    UNWEIGHTED SSE / NLLS

A beta fissato:

    Yhat_a = C_a + Q * G_a(beta)

quindi Q è profilato analiticamente:

    Q*(beta) =
        max(
            0,
            SUM_a G_a(beta)*(Y_a-C_a)
            /
            SUM_a G_a(beta)^2
        )

Q e beta vengono ricalibrati DA ZERO.

I precedenti parametri del modello global-normalized
NON vengono usati per inizializzare o vincolare il nuovo fit.

MANDATORY QA
------------
1. SUM_i P_i = 1

2. Per beta multipli:
       SUM_j conditional_share_ij = 1
   per ogni origine.

3. Per Q multipli:
       SUM_j N_ij = Q * P_i
   per ogni origine.

4. SUM_ij N_ij = Q

5. No NaN / inf / negative flows.

6. A_j = 0 produce esattamente zero destination-attraction flow.

COMPARISON
----------
Confronto OLD global-normalized vs NEW origin-constrained
senza modificare network/path artifacts.

PRIMARY:
    920032
    920039
    920035

EXPOSED SENSITIVITY:
    920022
    920028
    920035
    920024
    920026
    920042
    920040

920035 appartiene al canonical 5.8D sensitivity set
ma è PRIMARY nel calibration design corrente.
Non costituisce quindi validazione indipendente.

INPUTS
------
Frozen:
- Gravity_v0_territorial_inputs_derived_v01.xlsx
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz
- ANAS_5_8D_calibration_mapping_v01.csv

Temporary / prior diagnostic:
- E3A_final_primary_operator_candidate_v01.npz
- E4_primary_residuals_candidate_v01.csv
- E4_sensitivity_sections_candidate_v01.csv
- E4B_residual_attribution_operator_candidate_v01.npz
- E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv

OUTPUTS
-------
Only under:

C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\
R1_origin_constrained

- R1_QA_invariants_candidate_v01.csv
- R1_beta_profile_candidate_v01.csv
- R1_numerical_minimum_candidate_v01.csv
- R1_primary_fit_candidate_v01.csv
- R1_old_vs_new_section_comparison_candidate_v01.csv
- R1_missing_sensitivity_operator_candidate_v01.npz

Plots:
- R1_01_J_profile_global.png
- R1_02_J_profile_zoom.png
- R1_03_Q_star_global.png
- R1_04_J_normalized_global.png

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- Gamma_OSM
- EXP_REL_300
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA
- territorial P_i
- territorial A_j
- ISTAT commuting
- ANAS mapping

FILES NEVER MODIFIED
--------------------
Anything under:

C:\\Tesi\\Tesi_QGIS\\02_package

ANAS 2025 is NEVER accessed.
"""

from pathlib import Path
import csv
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import minimize_scalar
from scipy.sparse import load_npz


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

PACKAGE = ROOT / "02_package"

TEMP = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
)

OUT_ROOT = (
    TEMP
    / "R1_origin_constrained"
)


TERRITORIAL_FILE = (
    PACKAGE
    / "gravity_v0_inputs"
    / "Gravity_v0_territorial_inputs_derived_v01.xlsx"
)

E3A_OPERATOR = (
    TEMP
    / "E3A_beta_profile"
    / "E3A_final_primary_operator_candidate_v01.npz"
)

E4_PRIMARY = (
    TEMP
    / "E4_diagnostics"
    / "E4_primary_residuals_candidate_v01.csv"
)

E4_SENSITIVITY = (
    TEMP
    / "E4_diagnostics"
    / "E4_sensitivity_sections_candidate_v01.csv"
)

E4B_OPERATOR = (
    TEMP
    / "E4B_residual_attribution"
    / "E4B_residual_attribution_operator_candidate_v01.npz"
)

E1C_SCREEN = (
    TEMP
    / "E1C_sensitivity_screen"
    / "E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv"
)

ANAS_MAPPING = (
    PACKAGE
    / "anas_calibration_v0"
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

OD_ROOT = (
    PACKAGE
    / "od_paths_osm_light"
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
    PACKAGE
    / "grafo_operativo_osm"
    / "osm_turn_state_edgeid_v01.npz"
)


QA_OUT = (
    OUT_ROOT
    / "R1_QA_invariants_candidate_v01.csv"
)

PROFILE_OUT = (
    OUT_ROOT
    / "R1_beta_profile_candidate_v01.csv"
)

MINIMUM_OUT = (
    OUT_ROOT
    / "R1_numerical_minimum_candidate_v01.csv"
)

PRIMARY_OUT = (
    OUT_ROOT
    / "R1_primary_fit_candidate_v01.csv"
)

COMPARISON_OUT = (
    OUT_ROOT
    / "R1_old_vs_new_section_comparison_candidate_v01.csv"
)

MISSING_OPERATOR_OUT = (
    OUT_ROOT
    / "R1_missing_sensitivity_operator_candidate_v01.npz"
)


PLOT_GLOBAL = (
    OUT_ROOT
    / "R1_01_J_profile_global.png"
)

PLOT_ZOOM = (
    OUT_ROOT
    / "R1_02_J_profile_zoom.png"
)

PLOT_Q = (
    OUT_ROOT
    / "R1_03_Q_star_global.png"
)

PLOT_NORMALIZED = (
    OUT_ROOT
    / "R1_04_J_normalized_global.png"
)


PRIMARY_IDS = [
    "920032",
    "920039",
    "920035",
]

EXPOSED_SENSITIVITY_IDS = [
    "920022",
    "920028",
    "920035",
    "920024",
    "920026",
    "920042",
    "920040",
]

# Already available without a new scan:
#
# 920035 = PRIMARY operator
# 920022, 920040 = E4-B operator
#
# Therefore scan only the missing four exposed sensitivity sections.
MISSING_SENSITIVITY_IDS = [
    "920028",
    "920024",
    "920026",
    "920042",
]


BETA_MIN = 0.0
BETA_MAX = 0.20

GLOBAL_POINTS = 5001
LOCAL_POINTS = 5001

LOCAL_HALF_WIDTH = 0.004

BETA_BLOCK_SIZE = 64
PATH_SCAN_CHUNK = 10_000_000


QA_BETAS = [
    0.0,
    0.02,
    0.05,
    0.10,
    0.20,
]

QA_Q_VALUES = [
    100000.0,
    1000000.0,
    2500000.0,
]


# =============================================================================
# GENERAL HELPERS
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
# LOAD TERRITORIAL P_i / A_j
# =============================================================================

def load_territorial():
    df = pd.read_excel(
        TERRITORIAL_FILE,
        sheet_name="TERRITORIAL_INPUTS",
    )

    required = {
        "PRO_COM",
        "COMUNE",
        "P_i",
        "A_j",
    }

    missing = required - set(
        df.columns
    )

    if missing:
        raise RuntimeError(
            "Territorial workbook missing columns: "
            f"{sorted(missing)}"
        )

    df = df[
        [
            "PRO_COM",
            "COMUNE",
            "P_i",
            "A_j",
        ]
    ].copy()

    df[
        "PRO_COM"
    ] = pd.to_numeric(
        df[
            "PRO_COM"
        ],
        errors="raise",
    ).astype(
        np.int64
    )

    df[
        "P_i"
    ] = pd.to_numeric(
        df[
            "P_i"
        ],
        errors="raise",
    ).astype(
        np.float64
    )

    df[
        "A_j"
    ] = pd.to_numeric(
        df[
            "A_j"
        ],
        errors="raise",
    ).astype(
        np.float64
    )

    if len(
        df
    ) != 215:
        raise RuntimeError(
            f"Expected 215 municipalities, found {len(df)}"
        )

    if df[
        "PRO_COM"
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate PRO_COM in territorial workbook."
        )

    if (
        df[
            [
                "P_i",
                "A_j",
            ]
        ].isna().any().any()
    ):
        raise RuntimeError(
            "NaN in P_i or A_j."
        )

    if (
        (
            df[
                "P_i"
            ]
            < 0
        ).any()
        or
        (
            df[
                "A_j"
            ]
            < 0
        ).any()
    ):
        raise RuntimeError(
            "Negative P_i or A_j."
        )

    return df


# =============================================================================
# LOAD E3-A OPERATOR
# =============================================================================

def load_e3a_operator():
    z = np.load(
        E3A_OPERATOR,
        allow_pickle=False,
    )

    required = {
        "primary_ids",
        "origin_PRO_COM",
        "destination_PRO_COM",
        "c_min",
        "C_ij_ISTAT",
        "p_matrix",
        "observed_2024",
        "commuting_assigned",
    }

    missing = required - set(
        z.files
    )

    if missing:
        raise RuntimeError(
            f"E3-A operator missing arrays: {sorted(missing)}"
        )

    primary_ids = [
        str(x)
        for x in z[
            "primary_ids"
        ].tolist()
    ]

    if primary_ids != PRIMARY_IDS:
        raise RuntimeError(
            "Unexpected PRIMARY order: "
            f"{primary_ids}"
        )

    origin = z[
        "origin_PRO_COM"
    ].astype(
        np.int64
    )

    destination = z[
        "destination_PRO_COM"
    ].astype(
        np.int64
    )

    c_min = z[
        "c_min"
    ].astype(
        np.float64
    )

    commuting = z[
        "C_ij_ISTAT"
    ].astype(
        np.float64
    )

    primary_p = z[
        "p_matrix"
    ].astype(
        np.float64
    )

    observed_primary = z[
        "observed_2024"
    ].astype(
        np.float64
    )

    commuting_primary = z[
        "commuting_assigned"
    ].astype(
        np.float64
    )

    if len(
        origin
    ) != 46010:
        raise RuntimeError(
            "Expected 46010 ordered intermunicipal OD."
        )

    if primary_p.shape != (
        3,
        46010,
    ):
        raise RuntimeError(
            f"Unexpected primary p_matrix shape: {primary_p.shape}"
        )

    return {
        "origin":
            origin,

        "destination":
            destination,

        "c_min":
            c_min,

        "commuting":
            commuting,

        "primary_p":
            primary_p,

        "observed_primary":
            observed_primary,

        "commuting_primary":
            commuting_primary,
    }


# =============================================================================
# BUILD ORIGIN-CONSTRAINED STRUCTURE
# =============================================================================

def build_origin_structure(
    territorial,
    data,
):
    codes = territorial[
        "PRO_COM"
    ].to_numpy(
        dtype=np.int64
    )

    code_to_group = {
        int(code):
            idx

        for idx, code
        in enumerate(
            codes
        )
    }

    p_by_code = dict(
        zip(
            territorial[
                "PRO_COM"
            ].astype(
                int
            ),
            territorial[
                "P_i"
            ],
        )
    )

    a_by_code = dict(
        zip(
            territorial[
                "PRO_COM"
            ].astype(
                int
            ),
            territorial[
                "A_j"
            ],
        )
    )

    p_origin = np.array(
        [
            p_by_code[
                int(code)
            ]
            for code in data[
                "origin"
            ]
        ],
        dtype=np.float64,
    )

    a_destination = np.array(
        [
            a_by_code[
                int(code)
            ]
            for code in data[
                "destination"
            ]
        ],
        dtype=np.float64,
    )

    origin_group = np.array(
        [
            code_to_group[
                int(code)
            ]
            for code in data[
                "origin"
            ]
        ],
        dtype=np.int64,
    )

    groups = []

    for group_idx in range(
        len(
            codes
        )
    ):
        indices = np.flatnonzero(
            origin_group
            == group_idx
        )

        if len(
            indices
        ) != 214:
            raise RuntimeError(
                f"Origin group {group_idx}: "
                f"expected 214 destinations, found {len(indices)}"
            )

        groups.append(
            indices
        )

    zero_a = territorial[
        territorial[
            "A_j"
        ]
        == 0
    ].copy()

    return {
        "codes":
            codes,

        "p_origin":
            p_origin,

        "a_destination":
            a_destination,

        "origin_group":
            origin_group,

        "groups":
            groups,

        "P_vector":
            territorial[
                "P_i"
            ].to_numpy(
                dtype=np.float64
            ),

        "A_vector":
            territorial[
                "A_j"
            ].to_numpy(
                dtype=np.float64
            ),

        "zero_A_table":
            zero_a,
    }


# =============================================================================
# ORIGIN-CONSTRAINED FLOW FOR ONE BETA
# =============================================================================

def calculate_unit_flow(
    beta,
    structure,
    c_min,
):
    attraction_weight = (
        structure[
            "a_destination"
        ]
        *
        np.exp(
            -beta
            * c_min
        )
    )

    n_origins = len(
        structure[
            "groups"
        ]
    )

    denominator = np.empty(
        n_origins,
        dtype=np.float64,
    )

    for idx, od_indices in enumerate(
        structure[
            "groups"
        ]
    ):
        denominator[
            idx
        ] = np.sum(
            attraction_weight[
                od_indices
            ]
        )

    if (
        not np.all(
            np.isfinite(
                denominator
            )
        )
        or
        np.any(
            denominator
            <= 0
        )
    ):
        raise RuntimeError(
            f"Invalid origin denominator at beta={beta}"
        )

    conditional_share = (
        attraction_weight
        /
        denominator[
            structure[
                "origin_group"
            ]
        ]
    )

    unit_n = (
        structure[
            "p_origin"
        ]
        *
        conditional_share
    )

    if (
        not np.all(
            np.isfinite(
                conditional_share
            )
        )
        or
        not np.all(
            np.isfinite(
                unit_n
            )
        )
    ):
        raise RuntimeError(
            f"NaN/inf at beta={beta}"
        )

    if (
        np.any(
            conditional_share
            < 0
        )
        or
        np.any(
            unit_n
            < 0
        )
    ):
        raise RuntimeError(
            f"Negative flows at beta={beta}"
        )

    return (
        conditional_share,
        unit_n,
    )


# =============================================================================
# MANDATORY QA
# =============================================================================

def run_mandatory_qa(
    territorial,
    data,
    structure,
):
    qa_rows = []

    sum_p = float(
        territorial[
            "P_i"
        ].sum()
    )

    sum_a = float(
        territorial[
            "A_j"
        ].sum()
    )

    print()
    print("D. MANDATORY ORIGIN-CONSTRAINED QA")
    print("=" * 140)

    print(
        f"SUM_P_i = {sum_p:.15f}"
    )

    print(
        f"SUM_A_j = {sum_a:.15f}"
    )

    if abs(
        sum_p
        - 1.0
    ) > 1e-12:
        raise RuntimeError(
            "SUM P_i != 1"
        )

    zero_a = structure[
        "zero_A_table"
    ]

    print(
        f"ZERO_A_MUNICIPALITIES = {len(zero_a)}"
    )

    for _, row in zero_a.iterrows():
        print(
            f"ZERO_A = "
            f"{int(row['PRO_COM'])} | "
            f"{row['COMUNE']}"
        )

    zero_a_codes = set(
        zero_a[
            "PRO_COM"
        ].astype(
            int
        )
    )

    zero_a_od_mask = np.array(
        [
            int(code)
            in zero_a_codes

            for code in data[
                "destination"
            ]
        ],
        dtype=bool,
    )

    for beta in QA_BETAS:
        (
            conditional_share,
            unit_n,
        ) = calculate_unit_flow(
            beta,
            structure,
            data[
                "c_min"
            ],
        )

        share_sums = np.array(
            [
                np.sum(
                    conditional_share[
                        indices
                    ]
                )

                for indices
                in structure[
                    "groups"
                ]
            ],
            dtype=np.float64,
        )

        unit_sums = np.array(
            [
                np.sum(
                    unit_n[
                        indices
                    ]
                )

                for indices
                in structure[
                    "groups"
                ]
            ],
            dtype=np.float64,
        )

        max_share_error = float(
            np.max(
                np.abs(
                    share_sums
                    - 1.0
                )
            )
        )

        max_unit_origin_error = float(
            np.max(
                np.abs(
                    unit_sums
                    - structure[
                        "P_vector"
                    ]
                )
            )
        )

        total_unit_n = float(
            np.sum(
                unit_n
            )
        )

        zero_a_max = (
            float(
                np.max(
                    np.abs(
                        unit_n[
                            zero_a_od_mask
                        ]
                    )
                )
            )
            if np.any(
                zero_a_od_mask
            )
            else 0.0
        )

        print()
        print(
            f"BETA_QA = {beta:.6f}"
        )

        print(
            f"MAX_ORIGIN_SHARE_SUM_ERROR = "
            f"{max_share_error:.3e}"
        )

        print(
            f"MAX_UNIT_ORIGIN_MASS_ERROR = "
            f"{max_unit_origin_error:.3e}"
        )

        print(
            f"SUM_UNIT_N = {total_unit_n:.15f}"
        )

        print(
            f"MAX_FLOW_TO_ZERO_A_DESTINATION = "
            f"{zero_a_max:.3e}"
        )

        if max_share_error > 1e-12:
            raise RuntimeError(
                "Origin conditional shares do not sum to 1."
            )

        if max_unit_origin_error > 1e-12:
            raise RuntimeError(
                "Unit origin masses do not equal P_i."
            )

        if abs(
            total_unit_n
            - 1.0
        ) > 1e-12:
            raise RuntimeError(
                "Total unit N does not equal 1."
            )

        if zero_a_max != 0.0:
            raise RuntimeError(
                "A_j=0 does not produce exact zero flow."
            )

        for q_test in QA_Q_VALUES:
            n_test = (
                q_test
                * unit_n
            )

            origin_totals = np.array(
                [
                    np.sum(
                        n_test[
                            indices
                        ]
                    )

                    for indices
                    in structure[
                        "groups"
                    ]
                ],
                dtype=np.float64,
            )

            expected_origin = (
                q_test
                * structure[
                    "P_vector"
                ]
            )

            max_q_origin_error = float(
                np.max(
                    np.abs(
                        origin_totals
                        - expected_origin
                    )
                )
            )

            total_q_error = abs(
                float(
                    np.sum(
                        n_test
                    )
                )
                - q_test
            )

            print(
                f"    Q_TEST={q_test:.0f} | "
                f"MAX_ORIGIN_ERROR={max_q_origin_error:.6e} | "
                f"TOTAL_ERROR={total_q_error:.6e}"
            )

            tolerance = max(
                1e-8,
                q_test
                * 1e-12,
            )

            if max_q_origin_error > tolerance:
                raise RuntimeError(
                    "Q origin constraint QA failed."
                )

            if total_q_error > tolerance:
                raise RuntimeError(
                    "SUM_ij N_ij != Q."
                )

            qa_rows.append(
                {
                    "beta":
                        beta,

                    "Q_test":
                        q_test,

                    "max_origin_share_sum_error":
                        max_share_error,

                    "max_unit_origin_mass_error":
                        max_unit_origin_error,

                    "sum_unit_N":
                        total_unit_n,

                    "max_zero_A_flow":
                        zero_a_max,

                    "max_Q_origin_error":
                        max_q_origin_error,

                    "total_Q_error":
                        total_q_error,
                }
            )

    print()
    print(
        "MANDATORY_QA = PASS"
    )

    return pd.DataFrame(
        qa_rows
    )


# =============================================================================
# G(beta) FOR ONE BETA
# =============================================================================

def calculate_g(
    beta,
    structure,
    data,
    p_matrix,
):
    _, unit_n = calculate_unit_flow(
        beta,
        structure,
        data[
            "c_min"
        ],
    )

    g = (
        p_matrix
        @ unit_n
    )

    return (
        g,
        unit_n,
    )


# =============================================================================
# G(beta) GRID
# =============================================================================

def calculate_g_grid(
    betas,
    structure,
    data,
    p_matrix,
    label,
):
    betas = np.asarray(
        betas,
        dtype=np.float64,
    )

    n_beta = len(
        betas
    )

    n_sections = p_matrix.shape[
        0
    ]

    g_grid = np.empty(
        (
            n_beta,
            n_sections,
        ),
        dtype=np.float64,
    )

    c_min = data[
        "c_min"
    ]

    a_dest = structure[
        "a_destination"
    ]

    p_origin = structure[
        "p_origin"
    ]

    origin_group = structure[
        "origin_group"
    ]

    groups = structure[
        "groups"
    ]

    print()
    print(
        f"{label} — G(beta) GRID"
    )
    print("-" * 120)

    print(
        f"BETA_MIN = {betas[0]:.12f}"
    )

    print(
        f"BETA_MAX = {betas[-1]:.12f}"
    )

    print(
        f"POINTS = {len(betas)}"
    )

    next_progress = 10

    for lo in range(
        0,
        n_beta,
        BETA_BLOCK_SIZE,
    ):
        hi = min(
            lo
            + BETA_BLOCK_SIZE,
            n_beta,
        )

        beta_block = betas[
            lo:hi
        ]

        weights = np.exp(
            -beta_block[
                :,
                None
            ]
            * c_min[
                None,
                :
            ]
        )

        weights *= a_dest[
            None,
            :
        ]

        denominator = np.empty(
            (
                len(
                    beta_block
                ),
                len(
                    groups
                ),
            ),
            dtype=np.float64,
        )

        for group_idx, od_indices in enumerate(
            groups
        ):
            denominator[
                :,
                group_idx
            ] = np.sum(
                weights[
                    :,
                    od_indices
                ],
                axis=1,
            )

        if (
            np.any(
                denominator
                <= 0
            )
            or
            not np.all(
                np.isfinite(
                    denominator
                )
            )
        ):
            raise RuntimeError(
                "Invalid origin denominator in beta grid."
            )

        conditional_share = (
            weights
            /
            denominator[
                :,
                origin_group
            ]
        )

        unit_n = (
            conditional_share
            * p_origin[
                None,
                :
            ]
        )

        g_grid[
            lo:hi,
            :
        ] = (
            unit_n
            @ p_matrix.T
        )

        progress = int(
            100
            * hi
            / n_beta
        )

        if (
            progress
            >= next_progress
            or hi
            == n_beta
        ):
            print(
                f"GRID_PROGRESS = {progress:3d}%"
            )

            while (
                next_progress
                <= progress
            ):
                next_progress += 10

    return g_grid


# =============================================================================
# PROFILE Q
# =============================================================================

def profile_from_g(
    betas,
    g_grid,
    observed,
    commuting_assigned,
    scope,
):
    target = (
        observed
        - commuting_assigned
    )

    numerator = np.sum(
        g_grid
        * target[
            None,
            :
        ],
        axis=1,
    )

    denominator = np.sum(
        g_grid
        * g_grid,
        axis=1,
    )

    if np.any(
        denominator
        <= 0
    ):
        raise RuntimeError(
            "Profile-Q denominator <= 0."
        )

    q = np.maximum(
        0.0,
        numerator
        / denominator,
    )

    modelled = (
        commuting_assigned[
            None,
            :
        ]
        +
        q[
            :,
            None
        ]
        * g_grid
    )

    residual = (
        observed[
            None,
            :
        ]
        - modelled
    )

    j = np.sum(
        residual
        * residual,
        axis=1,
    )

    relative_error = (
        residual
        / observed[
            None,
            :
        ]
    )

    relative_sse = np.sum(
        relative_error
        * relative_error,
        axis=1,
    )

    df = pd.DataFrame(
        {
            "scan_scope":
                scope,

            "beta":
                betas,

            "c_half_min":
                [
                    c_half(
                        x
                    )
                    for x in betas
                ],

            "Q_star":
                q,

            "J_profile":
                j,

            "SSE_absolute":
                j,

            "relative_SSE_diagnostic":
                relative_sse,
        }
    )

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        df[
            f"{section_id}_observed"
        ] = observed[
            idx
        ]

        df[
            f"{section_id}_modelled"
        ] = modelled[
            :,
            idx
        ]

        df[
            f"{section_id}_residual_veh_day"
        ] = residual[
            :,
            idx
        ]

        df[
            f"{section_id}_relative_error"
        ] = relative_error[
            :,
            idx
        ]

    return df


# =============================================================================
# SINGLE-BETA PROFILE FOR CONTINUOUS OPTIMIZER
# =============================================================================

def evaluate_profile_beta(
    beta,
    structure,
    data,
):
    g, unit_n = calculate_g(
        beta,
        structure,
        data,
        data[
            "primary_p"
        ],
    )

    target = (
        data[
            "observed_primary"
        ]
        - data[
            "commuting_primary"
        ]
    )

    numerator = float(
        np.dot(
            g,
            target,
        )
    )

    denominator = float(
        np.dot(
            g,
            g,
        )
    )

    if denominator <= 0:
        raise RuntimeError(
            "Single-beta Q denominator <= 0."
        )

    q = max(
        0.0,
        numerator
        / denominator,
    )

    modelled = (
        data[
            "commuting_primary"
        ]
        +
        q
        * g
    )

    residual = (
        data[
            "observed_primary"
        ]
        - modelled
    )

    j = float(
        np.dot(
            residual,
            residual,
        )
    )

    relative_error = (
        residual
        / data[
            "observed_primary"
        ]
    )

    relative_sse = float(
        np.dot(
            relative_error,
            relative_error,
        )
    )

    return {
        "beta":
            beta,

        "Q":
            q,

        "G":
            g,

        "unit_n":
            unit_n,

        "modelled":
            modelled,

        "residual":
            residual,

        "J":
            j,

        "relative_SSE":
            relative_sse,
    }


# =============================================================================
# MISSING SENSITIVITY OPERATOR
# =============================================================================

def load_anas_mapping():
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
                row[
                    "SECTION_ID"
                ]
            )

            if section_id not in set(
                EXPOSED_SENSITIVITY_IDS
            ):
                continue

            result[
                section_id
            ] = {
                "ROAD":
                    clean(
                        row[
                            "ROAD"
                        ]
                    ),

                "OBSERVED":
                    float(
                        row[
                            "TGMA_LIGHT_2024"
                        ]
                    ),

                "QUALITY_CLASS":
                    clean(
                        row[
                            "QUALITY_CLASS"
                        ]
                    ),

                "EXTERNAL_EXPOSURE":
                    clean(
                        row[
                            "EXTERNAL_EXPOSURE"
                        ]
                    ),

                "EDGE_IDS":
                    parse_pipe_ints(
                        row[
                            "RELEVANT_DIRECTED_EDGE_IDS"
                        ]
                    ),
            }

    return result


def load_access_path_metadata(
    data,
):
    df = pd.read_csv(
        ACCESS_PATHS,
        usecols=[
            "path_idx",
            "origin_PRO_COM",
            "destination_PRO_COM",
            "pair_weight",
        ],
    )

    if len(
        df
    ) != 414090:
        raise RuntimeError(
            "Expected 414090 access paths."
        )

    for column in [
        "path_idx",
        "origin_PRO_COM",
        "destination_PRO_COM",
    ]:
        df[
            column
        ] = pd.to_numeric(
            df[
                column
            ],
            errors="raise",
        ).astype(
            np.int64
        )

    df[
        "pair_weight"
    ] = pd.to_numeric(
        df[
            "pair_weight"
        ],
        errors="raise",
    ).astype(
        np.float64
    )

    od_lookup = pd.DataFrame(
        {
            "origin_PRO_COM":
                data[
                    "origin"
                ],

            "destination_PRO_COM":
                data[
                    "destination"
                ],

            "od_idx":
                np.arange(
                    len(
                        data[
                            "origin"
                        ]
                    ),
                    dtype=np.int64,
                ),
        }
    )

    df = df.merge(
        od_lookup,
        on=[
            "origin_PRO_COM",
            "destination_PRO_COM",
        ],
        how="left",
        validate="many_to_one",
        sort=False,
    )

    if df[
        "od_idx"
    ].isna().any():
        raise RuntimeError(
            "Access path -> OD join failed."
        )

    df = df.sort_values(
        "path_idx"
    ).reset_index(
        drop=True
    )

    expected = np.arange(
        len(
            df
        ),
        dtype=np.int64,
    )

    if not np.array_equal(
        df[
            "path_idx"
        ].to_numpy(
            dtype=np.int64
        ),
        expected,
    ):
        raise RuntimeError(
            "Non-canonical path_idx ordering."
        )

    return (
        df[
            "od_idx"
        ].to_numpy(
            dtype=np.int64
        ),
        df[
            "pair_weight"
        ].to_numpy(
            dtype=np.float64
        ),
    )


def scan_missing_sensitivity(
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

    edgeid = load_npz(
        B5_EDGEID
    ).tocsr()

    bits = {
        section_id:
            np.uint8(
                1 << idx
            )

        for idx, section_id
        in enumerate(
            MISSING_SENSITIVITY_IDS
        )
    }

    slot_mask = np.zeros(
        edgeid.nnz,
        dtype=np.uint8,
    )

    print()
    print("G. MISSING SENSITIVITY EDGE QA")
    print("-" * 120)

    for section_id in MISSING_SENSITIVITY_IDS:
        for physical_edge in mapping[
            section_id
        ]["EDGE_IDS"]:

            matches = np.flatnonzero(
                edgeid.data
                == physical_edge
            )

            print(
                f"{section_id} | "
                f"EDGE_ID={physical_edge} | "
                f"B5_SLOT_OCCURRENCES={len(matches)}"
            )

            if len(
                matches
            ) == 0:
                raise RuntimeError(
                    f"{section_id}: edge missing from B5."
                )

            slot_mask[
                matches
            ] |= bits[
                section_id
            ]

    path_hits = {
        section_id:
            set()

        for section_id
        in MISSING_SENSITIVITY_IDS
    }

    n_slots = len(
        transitions
    )

    print()
    print("H. FROZEN PATH SCAN — MISSING SENSITIVITY")
    print("-" * 120)

    print(
        f"TRANSITION_SLOTS = {n_slots:,}"
    )

    next_progress = 10

    for lo in range(
        0,
        n_slots,
        PATH_SCAN_CHUNK,
    ):
        hi = min(
            lo
            + PATH_SCAN_CHUNK,
            n_slots,
        )

        slots = transitions[
            lo:hi
        ]

        masks = slot_mask[
            slots
        ]

        local_pos = np.flatnonzero(
            masks
        )

        if local_pos.size:
            global_pos = (
                local_pos
                + lo
            )

            path_idx = (
                np.searchsorted(
                    offsets,
                    global_pos,
                    side="right",
                )
                - 1
            )

            matched_masks = masks[
                local_pos
            ]

            for section_id in MISSING_SENSITIVITY_IDS:
                relevant = (
                    matched_masks
                    & bits[
                        section_id
                    ]
                ) != 0

                if np.any(
                    relevant
                ):
                    path_hits[
                        section_id
                    ].update(
                        map(
                            int,
                            np.unique(
                                path_idx[
                                    relevant
                                ]
                            ),
                        )
                    )

        progress = int(
            100
            * hi
            / n_slots
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


def build_p_from_paths(
    paths,
    path_to_od,
    pair_weight,
    n_od,
):
    paths = np.asarray(
        sorted(
            paths
        ),
        dtype=np.int64,
    )

    if len(
        paths
    ) == 0:
        return np.zeros(
            n_od,
            dtype=np.float64,
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

    if np.any(
        p
        > 1.0
        + 1e-10
    ):
        raise RuntimeError(
            "p_ij^a exceeds 1."
        )

    return np.minimum(
        p,
        1.0,
    )


# =============================================================================
# PLOTS
# =============================================================================

def make_plots(
    global_profile,
    local_profile,
    beta_best,
    q_best,
    j_best,
):
    fig = plt.figure(
        figsize=(
            10,
            6,
        )
    )

    plt.plot(
        global_profile[
            "beta"
        ],
        global_profile[
            "J_profile"
        ],
    )

    plt.scatter(
        [
            beta_best
        ],
        [
            j_best
        ],
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "J_profile — absolute SSE"
    )

    plt.title(
        "Origin-constrained Gravity — J profile"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_GLOBAL,
        dpi=160,
    )

    plt.close(
        fig
    )


    fig = plt.figure(
        figsize=(
            10,
            6,
        )
    )

    plt.plot(
        local_profile[
            "beta"
        ],
        local_profile[
            "J_profile"
        ],
    )

    plt.scatter(
        [
            beta_best
        ],
        [
            j_best
        ],
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "J_profile — absolute SSE"
    )

    plt.title(
        "Origin-constrained Gravity — local minimum"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_ZOOM,
        dpi=160,
    )

    plt.close(
        fig
    )


    fig = plt.figure(
        figsize=(
            10,
            6,
        )
    )

    plt.plot(
        global_profile[
            "beta"
        ],
        global_profile[
            "Q_star"
        ],
    )

    plt.scatter(
        [
            beta_best
        ],
        [
            q_best
        ],
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "Q*(beta) [veh/day]"
    )

    plt.title(
        "Origin-constrained Gravity — profiled Q"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_Q,
        dpi=160,
    )

    plt.close(
        fig
    )


    fig = plt.figure(
        figsize=(
            10,
            6,
        )
    )

    normalized = (
        global_profile[
            "J_profile"
        ]
        / j_best
    )

    plt.plot(
        global_profile[
            "beta"
        ],
        normalized,
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "J / J_min"
    )

    plt.title(
        "Origin-constrained Gravity — normalized J"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_NORMALIZED,
        dpi=160,
    )

    plt.close(
        fig
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 130)
    print(
        "5.8E-R1 — ORIGIN-CONSTRAINED GRAVITY RECALIBRATION"
    )
    print("=" * 130)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. CONTRACT")
    print("-" * 130)

    print(
        "MODEL = ORIGIN_CONSTRAINED_GRAVITY"
    )

    print(
        "DETERRENCE = EXPONENTIAL"
    )

    print(
        "P_i = HARD_RELATIVE_ORIGIN_SHARE"
    )

    print(
        "A_j = RELATIVE_DESTINATION_ATTRACTIVENESS_PROXY"
    )

    print(
        "OBJECTIVE = UNWEIGHTED_SSE_NLLS"
    )

    print(
        "PRIMARY = "
        + "|".join(
            PRIMARY_IDS
        )
    )

    print(
        "OLD_Q_BETA_REUSED_FOR_CALIBRATION = NO"
    )

    print(
        "COMBINED_TANNER_TESTED = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    # -------------------------------------------------------------------------
    # B. Preflight
    # -------------------------------------------------------------------------

    print()
    print("B. FILE PREFLIGHT")
    print("-" * 130)

    inputs = [
        TERRITORIAL_FILE,
        E3A_OPERATOR,
        E4_PRIMARY,
        E4_SENSITIVITY,
        E4B_OPERATOR,
        E1C_SCREEN,
        ANAS_MAPPING,
        ACCESS_PATHS,
        PATH_OFFSETS,
        TRANSITION_SLOTS,
        B5_EDGEID,
    ]

    for path in inputs:
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

    outputs = [
        QA_OUT,
        PROFILE_OUT,
        MINIMUM_OUT,
        PRIMARY_OUT,
        COMPARISON_OUT,
        MISSING_OPERATOR_OUT,
        PLOT_GLOBAL,
        PLOT_ZOOM,
        PLOT_Q,
        PLOT_NORMALIZED,
    ]

    for path in outputs:
        require_output_absent(
            path
        )

    # -------------------------------------------------------------------------
    # C. Data
    # -------------------------------------------------------------------------

    territorial = load_territorial()

    data = load_e3a_operator()

    structure = build_origin_structure(
        territorial,
        data,
    )

    print()
    print("C. INPUT STRUCTURE")
    print("-" * 130)

    print(
        f"MUNICIPALITIES = {len(territorial)}"
    )

    print(
        f"ORDERED_INTERMUNICIPAL_OD = {len(data['origin'])}"
    )

    print(
        f"SUM_P_i = {territorial['P_i'].sum():.15f}"
    )

    print(
        f"SUM_A_j = {territorial['A_j'].sum():.15f}"
    )

    # -------------------------------------------------------------------------
    # D. QA
    # -------------------------------------------------------------------------

    qa_df = run_mandatory_qa(
        territorial,
        data,
        structure,
    )

    qa_df.to_csv(
        QA_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # E. Profile — global
    # -------------------------------------------------------------------------

    global_betas = np.linspace(
        BETA_MIN,
        BETA_MAX,
        GLOBAL_POINTS,
        dtype=np.float64,
    )

    global_g = calculate_g_grid(
        global_betas,
        structure,
        data,
        data[
            "primary_p"
        ],
        "E. GLOBAL",
    )

    global_profile = profile_from_g(
        global_betas,
        global_g,
        data[
            "observed_primary"
        ],
        data[
            "commuting_primary"
        ],
        "GLOBAL",
    )

    global_best_idx = int(
        global_profile[
            "J_profile"
        ].idxmin()
    )

    global_best_beta = float(
        global_profile.loc[
            global_best_idx,
            "beta",
        ]
    )

    print()
    print("F. GLOBAL PROFILE RESULT")
    print("=" * 130)

    print(
        f"GLOBAL_GRID_BEST_BETA = {global_best_beta:.12f}"
    )

    print(
        f"GLOBAL_GRID_BEST_Q = "
        f"{global_profile.loc[global_best_idx, 'Q_star']:.6f}"
    )

    print(
        f"GLOBAL_GRID_BEST_J = "
        f"{global_profile.loc[global_best_idx, 'J_profile']:.6f}"
    )

    # -------------------------------------------------------------------------
    # F. Local dense refinement
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

    local_g = calculate_g_grid(
        local_betas,
        structure,
        data,
        data[
            "primary_p"
        ],
        "G. LOCAL",
    )

    local_profile = profile_from_g(
        local_betas,
        local_g,
        data[
            "observed_primary"
        ],
        data[
            "commuting_primary"
        ],
        "LOCAL",
    )

    local_best_idx = int(
        local_profile[
            "J_profile"
        ].idxmin()
    )

    local_best_beta = float(
        local_profile.loc[
            local_best_idx,
            "beta",
        ]
    )

    print()
    print("H. LOCAL PROFILE RESULT")
    print("=" * 130)

    print(
        f"LOCAL_BETA_MIN = {local_lo:.12f}"
    )

    print(
        f"LOCAL_BETA_MAX = {local_hi:.12f}"
    )

    print(
        f"LOCAL_GRID_BEST_BETA = {local_best_beta:.12f}"
    )

    print(
        f"LOCAL_GRID_BEST_Q = "
        f"{local_profile.loc[local_best_idx, 'Q_star']:.6f}"
    )

    print(
        f"LOCAL_GRID_BEST_J = "
        f"{local_profile.loc[local_best_idx, 'J_profile']:.6f}"
    )

    # -------------------------------------------------------------------------
    # G. Continuous refinement
    # -------------------------------------------------------------------------

    def scalar_objective(beta):
        return evaluate_profile_beta(
            beta,
            structure,
            data,
        )[
            "J"
        ]

    opt = minimize_scalar(
        scalar_objective,
        bounds=(
            local_lo,
            local_hi,
        ),
        method="bounded",
        options={
            "xatol":
                1e-12,

            "maxiter":
                500,
        },
    )

    candidates = [
        local_lo,
        float(
            opt.x
        ),
        local_hi,
    ]

    candidate_results = [
        evaluate_profile_beta(
            beta,
            structure,
            data,
        )

        for beta
        in candidates
    ]

    best = min(
        candidate_results,
        key=lambda x:
            x[
                "J"
            ],
    )

    beta_best = float(
        best[
            "beta"
        ]
    )

    q_best = float(
        best[
            "Q"
        ]
    )

    j_best = float(
        best[
            "J"
        ]
    )

    print()
    print("I. CONTINUOUS NUMERICAL MINIMUM")
    print("=" * 130)

    print(
        f"OPTIMIZER_SUCCESS = {opt.success}"
    )

    print(
        f"BETA_NUMERICAL_MIN = {beta_best:.12f}"
    )

    print(
        f"C_HALF_AT_NUMERICAL_MIN = {c_half(beta_best):.6f} min"
    )

    print(
        f"Q_AT_NUMERICAL_MIN = {q_best:.6f}"
    )

    print(
        f"J_NUMERICAL_MIN = {j_best:.6f}"
    )

    print(
        f"RELATIVE_SSE_DIAGNOSTIC = {best['relative_SSE']:.12f}"
    )

    # -------------------------------------------------------------------------
    # H. Profile shape
    # -------------------------------------------------------------------------

    global_j = global_profile[
        "J_profile"
    ].to_numpy(
        dtype=np.float64
    )

    local_minima_count = int(
        np.sum(
            (
                global_j[
                    1:-1
                ]
                <
                global_j[
                    :-2
                ]
            )
            &
            (
                global_j[
                    1:-1
                ]
                <
                global_j[
                    2:
                ]
            )
        )
    )

    within_1 = global_profile[
        global_profile[
            "J_profile"
        ]
        <= 1.01
        * j_best
    ]

    width_1 = (
        float(
            within_1[
                "beta"
            ].max()
            -
            within_1[
                "beta"
            ].min()
        )
        if len(
            within_1
        )
        else math.nan
    )

    print()
    print("J. PROFILE SHAPE")
    print("=" * 130)

    print(
        f"GLOBAL_GRID_LOCAL_MINIMA_COUNT = {local_minima_count}"
    )

    print(
        f"BETA_WIDTH_WITHIN_1PCT_OF_J_MIN = {width_1:.12f}"
    )

    print(
        f"J_AT_BETA_MIN = "
        f"{global_profile.iloc[0]['J_profile']:.6f}"
    )

    print(
        f"J_AT_BETA_MAX = "
        f"{global_profile.iloc[-1]['J_profile']:.6f}"
    )

    print(
        "PROFILE_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    # -------------------------------------------------------------------------
    # I. Save profile
    # -------------------------------------------------------------------------

    profile_combined = pd.concat(
        [
            global_profile,
            local_profile,
        ],
        ignore_index=True,
    )

    profile_combined.to_csv(
        PROFILE_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # J. Primary fit
    # -------------------------------------------------------------------------

    primary_rows = []

    print()
    print("K. NEW PRIMARY FIT")
    print("=" * 140)

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        observed = float(
            data[
                "observed_primary"
            ][
                idx
            ]
        )

        modelled = float(
            best[
                "modelled"
            ][
                idx
            ]
        )

        residual = float(
            best[
                "residual"
            ][
                idx
            ]
        )

        relative_error = (
            residual
            / observed
        )

        print(
            f"{section_id} | "
            f"OBSERVED={observed:.3f} | "
            f"MODELLED={modelled:.3f} | "
            f"RESIDUAL={residual:+.3f} | "
            f"REL_ERROR={relative_error:+.6f}"
        )

        primary_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "OBSERVED":
                    observed,

                "NEW_MODELLED":
                    modelled,

                "NEW_RESIDUAL":
                    residual,

                "NEW_REL_ERROR":
                    relative_error,
            }
        )

    primary_df = pd.DataFrame(
        primary_rows
    )

    primary_df.to_csv(
        PRIMARY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # K. Load sensitivity operators already available
    # -------------------------------------------------------------------------

    e4b = np.load(
        E4B_OPERATOR,
        allow_pickle=False,
    )

    p_by_section = {
        "920032":
            data[
                "primary_p"
            ][
                0
            ],

        "920039":
            data[
                "primary_p"
            ][
                1
            ],

        "920035":
            data[
                "primary_p"
            ][
                2
            ],

        "920022":
            e4b[
                "p_920022"
            ].astype(
                np.float64
            ),

        "920040":
            e4b[
                "p_920040"
            ].astype(
                np.float64
            ),
    }

    mapping = load_anas_mapping()

    # -------------------------------------------------------------------------
    # L. Scan only missing four sensitivity sections
    # -------------------------------------------------------------------------

    path_to_od, pair_weight = (
        load_access_path_metadata(
            data
        )
    )

    path_hits = scan_missing_sensitivity(
        mapping
    )

    e1c = pd.read_csv(
        E1C_SCREEN
    )

    e1c[
        "SECTION_ID"
    ] = e1c[
        "SECTION_ID"
    ].astype(
        str
    )

    e1c_lookup = e1c.set_index(
        "SECTION_ID"
    )

    print()
    print("I. MISSING SENSITIVITY EXPOSURE REGRESSION")
    print("=" * 130)

    for section_id in MISSING_SENSITIVITY_IDS:
        p = build_p_from_paths(
            path_hits[
                section_id
            ],
            path_to_od,
            pair_weight,
            len(
                data[
                    "origin"
                ]
            ),
        )

        actual_path_hits = len(
            path_hits[
                section_id
            ]
        )

        actual_od = int(
            np.count_nonzero(
                p > 0
            )
        )

        expected_path_hits = int(
            e1c_lookup.loc[
                section_id,
                "PATH_HITS",
            ]
        )

        expected_od = int(
            e1c_lookup.loc[
                section_id,
                "OD_P_GT_0",
            ]
        )

        passed = (
            actual_path_hits
            == expected_path_hits
            and
            actual_od
            == expected_od
        )

        print(
            f"{section_id} | "
            f"PATH={actual_path_hits} | "
            f"OD={actual_od} | "
            f"REGRESSION={'PASS' if passed else 'FAIL'}"
        )

        if not passed:
            raise RuntimeError(
                f"{section_id}: E1-C regression mismatch."
            )

        p_by_section[
            section_id
        ] = p

    np.savez_compressed(
        MISSING_OPERATOR_OUT,

        section_ids=np.array(
            MISSING_SENSITIVITY_IDS
        ),

        p_920028=p_by_section[
            "920028"
        ],

        p_920024=p_by_section[
            "920024"
        ],

        p_920026=p_by_section[
            "920026"
        ],

        p_920042=p_by_section[
            "920042"
        ],
    )

    # -------------------------------------------------------------------------
    # M. OLD vs NEW comparison
    # -------------------------------------------------------------------------

    old_primary = pd.read_csv(
        E4_PRIMARY
    )

    old_primary[
        "SECTION_ID"
    ] = old_primary[
        "SECTION_ID"
    ].astype(
        str
    )

    old_sensitivity = pd.read_csv(
        E4_SENSITIVITY
    )

    old_sensitivity[
        "SECTION_ID"
    ] = old_sensitivity[
        "SECTION_ID"
    ].astype(
        str
    )

    old_primary_lookup = old_primary.set_index(
        "SECTION_ID"
    )

    old_sensitivity_lookup = old_sensitivity.set_index(
        "SECTION_ID"
    )

    comparison_ids = [
        "920032",
        "920039",
        "920035",
        "920022",
        "920028",
        "920024",
        "920026",
        "920042",
        "920040",
    ]

    comparison_rows = []

    print()
    print("M. OLD vs ORIGIN-CONSTRAINED")
    print("=" * 170)

    for section_id in comparison_ids:
        p = p_by_section[
            section_id
        ]

        commuting_assigned = float(
            np.dot(
                p,
                data[
                    "commuting"
                ],
            )
        )

        new_g = float(
            np.dot(
                p,
                best[
                    "unit_n"
                ],
            )
        )

        new_modelled = (
            commuting_assigned
            +
            q_best
            * new_g
        )

        if section_id in PRIMARY_IDS:
            old_row = old_primary_lookup.loc[
                section_id
            ]

            observed = float(
                old_row[
                    "OBSERVED"
                ]
            )

            old_modelled = float(
                old_row[
                    "MODELLED"
                ]
            )

            old_rel_error = float(
                old_row[
                    "REL_ERROR"
                ]
            )

            role = "PRIMARY"

        else:
            old_row = old_sensitivity_lookup.loc[
                section_id
            ]

            observed = float(
                old_row[
                    "OBSERVED"
                ]
            )

            old_modelled = float(
                old_row[
                    "MODELLED"
                ]
            )

            old_rel_error = float(
                old_row[
                    "REL_ERROR"
                ]
            )

            role = "SENSITIVITY"

        new_residual = (
            observed
            - new_modelled
        )

        new_rel_error = (
            new_residual
            / observed
        )

        old_abs = abs(
            old_rel_error
        )

        new_abs = abs(
            new_rel_error
        )

        abs_rel_error_change = (
            new_abs
            - old_abs
        )

        print(
            f"{section_id} | "
            f"ROLE={role} | "
            f"OBS={observed:.3f} | "
            f"OLD={old_modelled:.3f} | "
            f"NEW={new_modelled:.3f} | "
            f"OLD_REL={old_rel_error:+.6f} | "
            f"NEW_REL={new_rel_error:+.6f} | "
            f"DELTA_ABS_REL={abs_rel_error_change:+.6f}"
        )

        comparison_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "ROLE":
                    role,

                "OBSERVED":
                    observed,

                "OLD_MODELLED":
                    old_modelled,

                "NEW_MODELLED":
                    new_modelled,

                "OLD_REL_ERROR":
                    old_rel_error,

                "NEW_REL_ERROR":
                    new_rel_error,

                "OLD_ABS_REL_ERROR":
                    old_abs,

                "NEW_ABS_REL_ERROR":
                    new_abs,

                "DELTA_ABS_REL_ERROR_NEW_MINUS_OLD":
                    abs_rel_error_change,

                "NEW_ASSIGNED_COMMUTING":
                    commuting_assigned,

                "NEW_ASSIGNED_NONPENDULAR":
                    q_best
                    * new_g,
            }
        )

    comparison_df = pd.DataFrame(
        comparison_rows
    )

    comparison_df.to_csv(
        COMPARISON_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # N. Numerical minimum file
    # -------------------------------------------------------------------------

    minimum_df = pd.DataFrame(
        [
            {
                "beta":
                    beta_best,

                "c_half_min":
                    c_half(
                        beta_best
                    ),

                "Q_star":
                    q_best,

                "J_profile":
                    j_best,

                "relative_SSE_diagnostic":
                    best[
                        "relative_SSE"
                    ],

                "optimizer_success":
                    bool(
                        opt.success
                    ),

                "model":
                    "ORIGIN_CONSTRAINED_GRAVITY",

                "parameters_frozen":
                    "NO",

                "ANAS_2025_used":
                    "NO",
            }
        ]
    )

    minimum_df.to_csv(
        MINIMUM_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # O. Plots
    # -------------------------------------------------------------------------

    make_plots(
        global_profile,
        local_profile,
        beta_best,
        q_best,
        j_best,
    )

    # -------------------------------------------------------------------------
    # P. Outputs
    # -------------------------------------------------------------------------

    print()
    print("N. OUTPUTS")
    print("-" * 130)

    for path in outputs:
        print(
            "OUTPUT =",
            path,
        )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / CANDIDATE / NOT FROZEN"
    )

    # -------------------------------------------------------------------------
    # Q. Gate state
    # -------------------------------------------------------------------------

    print()
    print("O. R1 GATE STATE")
    print("=" * 130)

    print(
        "MODEL = ORIGIN_CONSTRAINED_GRAVITY"
    )

    print(
        "MANDATORY_QA = PASS"
    )

    print(
        f"BETA_NEW_CANDIDATE = {beta_best:.12f}"
    )

    print(
        f"Q_NEW_CANDIDATE = {q_best:.6f}"
    )

    print(
        f"J_NEW_CANDIDATE = {j_best:.6f}"
    )

    print(
        "OLD_VS_NEW_VERDICT = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "FINAL_R1_VERDICT = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "Q_FROZEN = NO"
    )

    print(
        "BETA_FROZEN = NO"
    )

    print(
        "COMBINED_TANNER_TESTED = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    print(
        "FRLM_STARTED = NO"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

