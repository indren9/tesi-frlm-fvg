"""
5.8E-R2 — COMBINED DETERRENCE DIAGNOSTIC TEST
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Testare, sul modello GLOBAL-NORMALIZED pre-R1, la deterrenza combinata:

    f(c) = c^n * exp(-beta*c)

con:

    n >= 0
    beta >= 0

Il modello è:

    W_ij = P_i * A_j * c_ij^n * exp(-beta*c_ij)

    S_ij = W_ij / SUM_rs W_rs

    N_ij = Q * S_ij

Il caso:

    n = 0

deve riprodurre ESATTAMENTE, entro precisione numerica,
il precedente modello esponenziale:

    f(c) = exp(-beta*c)

Questo nested-model invariant è QA obbligatoria.

CALIBRATION
-----------
PRIMARY:

    920032
    920039
    920035

OBJECTIVE:

    UNWEIGHTED SSE / NLLS

Per ogni coppia fissata:

    (n, beta)

Q rimane lineare e viene profilato analiticamente:

    Q*(n,beta) =
        max(
            0,
            SUM_a G_a(n,beta)*(Y_a-C_a)
            /
            SUM_a G_a(n,beta)^2
        )

La ricerca numerica è quindi 2D:

    n
    beta

e NON 3D.

PURPOSE OF R2
-------------
Determinare se la forma della deterrenza è responsabile,
almeno in parte, del spatial-generalization failure osservato
con il modello esponenziale.

Il PRIMARY fit NON è sufficiente per dichiarare successo.

La valutazione decisiva riguarda le sensitivity esposte:

    920022
    920028
    920024
    920026
    920042
    920040

IDENTIFIABILITY WARNING
-----------------------
3 PRIMARY observations
3 effective parameters:

    Q
    n
    beta

Un PRIMARY SSE quasi nullo può essere semplice saturazione.

Pertanto R2 valuta anche:

- uniqueness of minimum;
- local/ridge structure;
- n-beta correlation;
- Jacobian rank;
- singular values;
- column-normalized conditioning;
- relative-parameter conditioning;
- local profiled Hessian where feasible;
- parameter ranges near J_min.

INPUTS
------
Temporary, previously validated operators:

- E3A_final_primary_operator_candidate_v01.npz
- E3A_numerical_minimum_candidate_v01.csv
- E4_primary_residuals_candidate_v01.csv
- E4_sensitivity_sections_candidate_v01.csv
- E4B_residual_attribution_operator_candidate_v01.npz
- R1_missing_sensitivity_operator_candidate_v01.npz

No path is recomputed.
No frozen network artifact is modified.

OUTPUTS
-------
Only under:

C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\
R2_combined_deterrence

CSV:
- R2_nested_model_QA_candidate_v01.csv
- R2_global_surface_candidate_v01.csv
- R2_local_surface_candidate_v01.csv
- R2_numerical_minimum_candidate_v01.csv
- R2_identifiability_candidate_v01.csv
- R2_local_stability_candidate_v01.csv
- R2_primary_fit_candidate_v01.csv
- R2_old_vs_combined_candidate_v01.csv

Plots:
- R2_01_J_surface_global.png
- R2_02_J_surface_zoom.png
- R2_03_Q_surface_global.png
- R2_04_c_peak_contours.png
- R2_05_deterrence_shape_comparison.png
- R2_06_sensitivity_observed_old_combined.png
- R2_07_primary_observed_old_combined.png

FILES NEVER MODIFIED
--------------------
Anything under:

C:\\Tesi\\Tesi_QGIS\\02_package

ANAS 2025 is NEVER used.

No parameter is frozen by this script.
"""

from pathlib import Path
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import minimize


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

TEMP = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
)

OUT_ROOT = (
    TEMP
    / "R2_combined_deterrence"
)


E3A_ROOT = (
    TEMP
    / "E3A_beta_profile"
)

E4_ROOT = (
    TEMP
    / "E4_diagnostics"
)

E4B_ROOT = (
    TEMP
    / "E4B_residual_attribution"
)

R1_ROOT = (
    TEMP
    / "R1_origin_constrained"
)


E3A_OPERATOR = (
    E3A_ROOT
    / "E3A_final_primary_operator_candidate_v01.npz"
)

E3A_MINIMUM = (
    E3A_ROOT
    / "E3A_numerical_minimum_candidate_v01.csv"
)

E4_PRIMARY = (
    E4_ROOT
    / "E4_primary_residuals_candidate_v01.csv"
)

E4_SENSITIVITY = (
    E4_ROOT
    / "E4_sensitivity_sections_candidate_v01.csv"
)

E4B_OPERATOR = (
    E4B_ROOT
    / "E4B_residual_attribution_operator_candidate_v01.npz"
)

R1_MISSING_OPERATOR = (
    R1_ROOT
    / "R1_missing_sensitivity_operator_candidate_v01.npz"
)


QA_OUT = (
    OUT_ROOT
    / "R2_nested_model_QA_candidate_v01.csv"
)

GLOBAL_SURFACE_OUT = (
    OUT_ROOT
    / "R2_global_surface_candidate_v01.csv"
)

LOCAL_SURFACE_OUT = (
    OUT_ROOT
    / "R2_local_surface_candidate_v01.csv"
)

MINIMUM_OUT = (
    OUT_ROOT
    / "R2_numerical_minimum_candidate_v01.csv"
)

IDENTIFIABILITY_OUT = (
    OUT_ROOT
    / "R2_identifiability_candidate_v01.csv"
)

STABILITY_OUT = (
    OUT_ROOT
    / "R2_local_stability_candidate_v01.csv"
)

PRIMARY_OUT = (
    OUT_ROOT
    / "R2_primary_fit_candidate_v01.csv"
)

COMPARISON_OUT = (
    OUT_ROOT
    / "R2_old_vs_combined_candidate_v01.csv"
)


PLOT_GLOBAL_J = (
    OUT_ROOT
    / "R2_01_J_surface_global.png"
)

PLOT_LOCAL_J = (
    OUT_ROOT
    / "R2_02_J_surface_zoom.png"
)

PLOT_GLOBAL_Q = (
    OUT_ROOT
    / "R2_03_Q_surface_global.png"
)

PLOT_C_PEAK = (
    OUT_ROOT
    / "R2_04_c_peak_contours.png"
)

PLOT_DETERRENCE = (
    OUT_ROOT
    / "R2_05_deterrence_shape_comparison.png"
)

PLOT_SENSITIVITY = (
    OUT_ROOT
    / "R2_06_sensitivity_observed_old_combined.png"
)

PLOT_PRIMARY = (
    OUT_ROOT
    / "R2_07_primary_observed_old_combined.png"
)


PRIMARY_IDS = [
    "920032",
    "920039",
    "920035",
]

SENSITIVITY_IDS = [
    "920022",
    "920028",
    "920024",
    "920026",
    "920042",
    "920040",
]

COMPARISON_IDS = (
    PRIMARY_IDS
    + SENSITIVITY_IDS
)


# -----------------------------------------------------------------------------
# Exploratory bounds.
#
# NOT frozen methodological bounds.
# -----------------------------------------------------------------------------

N_MIN = 0.0
N_MAX = 6.0

BETA_MIN = 0.0
BETA_MAX = 0.20


# Global deterministic grid:
#
# n step    = 0.06
# beta step = 0.0008
#
# 101 * 251 = 25,351 profiled model evaluations.
GLOBAL_N_POINTS = 101
GLOBAL_BETA_POINTS = 251


# Local dense surface around continuous candidate.
LOCAL_N_POINTS = 121
LOCAL_BETA_POINTS = 121

LOCAL_N_HALF_WIDTH = 0.40
LOCAL_BETA_HALF_WIDTH = 0.010


# Number of separated global-grid seeds used for continuous 2D refinement.
N_OPTIMIZER_SEEDS = 5


# =============================================================================
# HELPERS
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


def c_peak(n_value, beta):
    if n_value <= 0:
        return 0.0

    if beta <= 0:
        return math.inf

    return n_value / beta


def pct_change(new, old):
    if old == 0:
        return math.nan

    return 100.0 * (
        new / old - 1.0
    )


# =============================================================================
# LOAD MODEL DATA
# =============================================================================

def load_data():
    z = np.load(
        E3A_OPERATOR,
        allow_pickle=False,
    )

    required = {
        "primary_ids",
        "origin_PRO_COM",
        "destination_PRO_COM",
        "c_min",
        "gravity_base",
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

    c_min = z[
        "c_min"
    ].astype(
        np.float64
    )

    gravity_base = z[
        "gravity_base"
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
        c_min
    ) != 46010:
        raise RuntimeError(
            f"Expected 46010 OD, found {len(c_min)}"
        )

    if np.any(
        c_min <= 0
    ):
        raise RuntimeError(
            "Combined deterrence requires strictly positive c_ij."
        )

    if np.any(
        gravity_base < 0
    ):
        raise RuntimeError(
            "Negative global gravity base."
        )

    if not np.any(
        gravity_base > 0
    ):
        raise RuntimeError(
            "All gravity-base weights are zero."
        )

    return {
        "c_min":
            c_min,

        "log_c":
            np.log(
                c_min
            ),

        "gravity_base":
            gravity_base,

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
# LOAD ALL EXISTING SECTION OPERATORS
# =============================================================================

def load_section_operators(data):
    e4b = np.load(
        E4B_OPERATOR,
        allow_pickle=False,
    )

    r1 = np.load(
        R1_MISSING_OPERATOR,
        allow_pickle=False,
    )

    p = {
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

        "920028":
            r1[
                "p_920028"
            ].astype(
                np.float64
            ),

        "920024":
            r1[
                "p_920024"
            ].astype(
                np.float64
            ),

        "920026":
            r1[
                "p_920026"
            ].astype(
                np.float64
            ),

        "920042":
            r1[
                "p_920042"
            ].astype(
                np.float64
            ),
    }

    for section_id, vector in p.items():
        if vector.shape != (
            46010,
        ):
            raise RuntimeError(
                f"{section_id}: unexpected p shape {vector.shape}"
            )

        if np.any(
            vector < -1e-12
        ) or np.any(
            vector > 1.0 + 1e-10
        ):
            raise RuntimeError(
                f"{section_id}: invalid p_ij^a."
            )

    return p


# =============================================================================
# PROFILE Q FOR ONE (n,beta)
# =============================================================================

def evaluate_parameters(
    n_value,
    beta,
    data,
):
    if n_value < 0:
        raise ValueError(
            "n must be >= 0."
        )

    if beta < 0:
        raise ValueError(
            "beta must be >= 0."
        )

    if n_value == 0.0:
        power_term = np.ones(
            len(
                data[
                    "c_min"
                ]
            ),
            dtype=np.float64,
        )
    else:
        power_term = np.exp(
            n_value
            * data[
                "log_c"
            ]
        )

    weights = (
        data[
            "gravity_base"
        ]
        * power_term
        * np.exp(
            -beta
            * data[
                "c_min"
            ]
        )
    )

    denominator = float(
        np.sum(
            weights
        )
    )

    if (
        denominator <= 0
        or not math.isfinite(
            denominator
        )
    ):
        raise RuntimeError(
            f"Invalid denominator at n={n_value}, beta={beta}"
        )

    s_ij = (
        weights
        / denominator
    )

    if (
        not np.all(
            np.isfinite(
                s_ij
            )
        )
        or np.any(
            s_ij < 0
        )
    ):
        raise RuntimeError(
            "Invalid S_ij."
        )

    g = (
        data[
            "primary_p"
        ]
        @ s_ij
    )

    target = (
        data[
            "observed_primary"
        ]
        - data[
            "commuting_primary"
        ]
    )

    q_numerator = float(
        np.dot(
            g,
            target,
        )
    )

    q_denominator = float(
        np.dot(
            g,
            g,
        )
    )

    if q_denominator <= 0:
        raise RuntimeError(
            "Profile Q denominator <= 0."
        )

    q_star = max(
        0.0,
        q_numerator
        / q_denominator,
    )

    modelled = (
        data[
            "commuting_primary"
        ]
        +
        q_star
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
        "n":
            float(
                n_value
            ),

        "beta":
            float(
                beta
            ),

        "c_peak":
            c_peak(
                n_value,
                beta,
            ),

        "Q":
            float(
                q_star
            ),

        "J":
            j,

        "relative_SSE":
            relative_sse,

        "S":
            s_ij,

        "G":
            g,

        "modelled":
            modelled,

        "residual":
            residual,
    }


# =============================================================================
# NESTED MODEL QA
# =============================================================================

def nested_model_qa(
    data,
):
    old_min = pd.read_csv(
        E3A_MINIMUM
    )

    if len(
        old_min
    ) != 1:
        raise RuntimeError(
            "E3-A numerical minimum must contain one row."
        )

    old_beta = float(
        old_min.iloc[
            0
        ][
            "beta"
        ]
    )

    old_q = float(
        old_min.iloc[
            0
        ][
            "Q_star"
        ]
    )

    old_j = float(
        old_min.iloc[
            0
        ][
            "J_profile"
        ]
    )

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

    old_lookup = old_primary.set_index(
        "SECTION_ID"
    )

    nested = evaluate_parameters(
        0.0,
        old_beta,
        data,
    )

    q_delta = abs(
        nested[
            "Q"
        ]
        - old_q
    )

    j_delta = abs(
        nested[
            "J"
        ]
        - old_j
    )

    model_deltas = []

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        old_modelled = float(
            old_lookup.loc[
                section_id,
                "MODELLED",
            ]
        )

        model_deltas.append(
            abs(
                nested[
                    "modelled"
                ][
                    idx
                ]
                - old_modelled
            )
        )

    max_model_delta = max(
        model_deltas
    )

    qa_rows = []

    print()
    print("D. NESTED MODEL QA — n=0")
    print("=" * 130)

    print(
        f"OLD_BETA = {old_beta:.12f}"
    )

    print(
        f"OLD_Q = {old_q:.6f}"
    )

    print(
        f"NESTED_Q = {nested['Q']:.6f}"
    )

    print(
        f"ABS_Q_DELTA = {q_delta:.12e}"
    )

    print(
        f"OLD_J = {old_j:.6f}"
    )

    print(
        f"NESTED_J = {nested['J']:.6f}"
    )

    print(
        f"ABS_J_DELTA = {j_delta:.12e}"
    )

    print(
        f"MAX_PRIMARY_MODELLED_DELTA = "
        f"{max_model_delta:.12e}"
    )

    # Additional exact-shape tests.
    qa_betas = [
        0.0,
        0.02,
        old_beta,
        0.10,
        0.20,
    ]

    for beta in qa_betas:
        old_weights = (
            data[
                "gravity_base"
            ]
            * np.exp(
                -beta
                * data[
                    "c_min"
                ]
            )
        )

        old_s = (
            old_weights
            / np.sum(
                old_weights
            )
        )

        combined = evaluate_parameters(
            0.0,
            beta,
            data,
        )

        max_s_delta = float(
            np.max(
                np.abs(
                    combined[
                        "S"
                    ]
                    - old_s
                )
            )
        )

        print(
            f"BETA={beta:.12f} | "
            f"MAX_S_DELTA_N0_VS_EXP={max_s_delta:.3e}"
        )

        qa_rows.append(
            {
                "beta":
                    beta,

                "max_S_delta_n0_vs_exponential":
                    max_s_delta,
            }
        )

    # Tolerances refer only to numerical reproduction.
    if q_delta > 0.1:
        raise RuntimeError(
            "Nested-model Q invariant FAILED."
        )

    if j_delta > 0.1:
        raise RuntimeError(
            "Nested-model J invariant FAILED."
        )

    if max_model_delta > 0.01:
        raise RuntimeError(
            "Nested-model PRIMARY prediction invariant FAILED."
        )

    if max(
        row[
            "max_S_delta_n0_vs_exponential"
        ]
        for row in qa_rows
    ) > 1e-14:
        raise RuntimeError(
            "n=0 does not reproduce exponential S_ij."
        )

    print(
        "NESTED_MODEL_INVARIANT = PASS"
    )

    qa_df = pd.DataFrame(
        qa_rows
    )

    qa_df[
        "old_beta_candidate"
    ] = old_beta

    qa_df[
        "old_Q_candidate"
    ] = old_q

    qa_df[
        "old_J_candidate"
    ] = old_j

    qa_df[
        "nested_Q_delta_at_old_candidate"
    ] = q_delta

    qa_df[
        "nested_J_delta_at_old_candidate"
    ] = j_delta

    qa_df[
        "max_primary_modelled_delta"
    ] = max_model_delta

    return (
        qa_df,
        old_beta,
        old_q,
        old_j,
    )


# =============================================================================
# DENSE 2D PROFILE SURFACE
# =============================================================================

def calculate_surface(
    n_values,
    beta_values,
    data,
    label,
):
    n_values = np.asarray(
        n_values,
        dtype=np.float64,
    )

    beta_values = np.asarray(
        beta_values,
        dtype=np.float64,
    )

    n_n = len(
        n_values
    )

    n_b = len(
        beta_values
    )

    j_surface = np.empty(
        (
            n_n,
            n_b,
        ),
        dtype=np.float64,
    )

    q_surface = np.empty(
        (
            n_n,
            n_b,
        ),
        dtype=np.float64,
    )

    rel_surface = np.empty(
        (
            n_n,
            n_b,
        ),
        dtype=np.float64,
    )

    # exp(-beta*c) depends only on beta and can therefore
    # be materialized once and reused across all n.
    exp_beta = np.exp(
        -beta_values[
            :,
            None
        ]
        * data[
            "c_min"
        ][
            None,
            :
        ]
    )

    target = (
        data[
            "observed_primary"
        ]
        - data[
            "commuting_primary"
        ]
    )

    print()
    print(
        f"{label} — 2D PROFILE SURFACE"
    )
    print("-" * 130)

    print(
        f"N_RANGE = [{n_values[0]:.6f}, {n_values[-1]:.6f}]"
    )

    print(
        f"BETA_RANGE = "
        f"[{beta_values[0]:.6f}, {beta_values[-1]:.6f}]"
    )

    print(
        f"GRID = {n_n} x {n_b} = {n_n * n_b:,} points"
    )

    next_progress = 10

    for n_idx, n_value in enumerate(
        n_values
    ):
        if n_value == 0.0:
            c_power = np.ones(
                len(
                    data[
                        "c_min"
                    ]
                ),
                dtype=np.float64,
            )
        else:
            c_power = np.exp(
                n_value
                * data[
                    "log_c"
                ]
            )

        base_n = (
            data[
                "gravity_base"
            ]
            * c_power
        )

        # One matrix multiplication calculates denominator and
        # section numerators for every beta simultaneously.
        packed = np.column_stack(
            [
                base_n,
                base_n
                * data[
                    "primary_p"
                ][
                    0
                ],
                base_n
                * data[
                    "primary_p"
                ][
                    1
                ],
                base_n
                * data[
                    "primary_p"
                ][
                    2
                ],
            ]
        )

        moment = (
            exp_beta
            @ packed
        )

        denominator = moment[
            :,
            0
        ]

        if (
            np.any(
                denominator <= 0
            )
            or not np.all(
                np.isfinite(
                    denominator
                )
            )
        ):
            raise RuntimeError(
                f"Invalid gravity denominator for n={n_value}"
            )

        g = (
            moment[
                :,
                1:
            ]
            /
            denominator[
                :,
                None
            ]
        )

        q_num = (
            g
            @ target
        )

        q_den = np.sum(
            g
            * g,
            axis=1,
        )

        if np.any(
            q_den <= 0
        ):
            raise RuntimeError(
                "Invalid profile-Q denominator."
            )

        q = np.maximum(
            0.0,
            q_num
            / q_den,
        )

        modelled = (
            data[
                "commuting_primary"
            ][
                None,
                :
            ]
            +
            q[
                :,
                None
            ]
            * g
        )

        residual = (
            data[
                "observed_primary"
            ][
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

        rel = (
            residual
            /
            data[
                "observed_primary"
            ][
                None,
                :
            ]
        )

        rel_sse = np.sum(
            rel
            * rel,
            axis=1,
        )

        j_surface[
            n_idx,
            :
        ] = j

        q_surface[
            n_idx,
            :
        ] = q

        rel_surface[
            n_idx,
            :
        ] = rel_sse

        progress = int(
            100
            * (
                n_idx
                + 1
            )
            / n_n
        )

        if (
            progress >= next_progress
            or n_idx == n_n - 1
        ):
            print(
                f"SURFACE_PROGRESS = {progress:3d}%"
            )

            while next_progress <= progress:
                next_progress += 10

    return {
        "n_values":
            n_values,

        "beta_values":
            beta_values,

        "J":
            j_surface,

        "Q":
            q_surface,

        "relative_SSE":
            rel_surface,
    }


# =============================================================================
# SURFACE -> DATAFRAME
# =============================================================================

def surface_to_dataframe(
    surface,
    scope,
):
    n_grid, beta_grid = np.meshgrid(
        surface[
            "n_values"
        ],
        surface[
            "beta_values"
        ],
        indexing="ij",
    )

    c_peak_grid = np.full(
        n_grid.shape,
        np.nan,
        dtype=np.float64,
    )

    positive_beta = (
        beta_grid > 0
    )

    positive_n = (
        n_grid > 0
    )

    both = (
        positive_beta
        & positive_n
    )

    c_peak_grid[
        both
    ] = (
        n_grid[
            both
        ]
        /
        beta_grid[
            both
        ]
    )

    # n=0 is the monotonic exponential case.
    c_peak_grid[
        n_grid == 0
    ] = 0.0

    return pd.DataFrame(
        {
            "scope":
                scope,

            "n":
                n_grid.ravel(),

            "beta":
                beta_grid.ravel(),

            "c_peak_min":
                c_peak_grid.ravel(),

            "Q_star":
                surface[
                    "Q"
                ].ravel(),

            "J_profile":
                surface[
                    "J"
                ].ravel(),

            "relative_SSE_diagnostic":
                surface[
                    "relative_SSE"
                ].ravel(),
        }
    )


# =============================================================================
# GLOBAL GRID PROMISING SEEDS
# =============================================================================

def choose_promising_seeds(
    surface,
):
    j = surface[
        "J"
    ]

    order = np.argsort(
        j,
        axis=None,
    )

    n_values = surface[
        "n_values"
    ]

    beta_values = surface[
        "beta_values"
    ]

    n_step = (
        n_values[
            1
        ]
        - n_values[
            0
        ]
    )

    beta_step = (
        beta_values[
            1
        ]
        - beta_values[
            0
        ]
    )

    seeds = []

    for flat_idx in order:
        i, k = np.unravel_index(
            flat_idx,
            j.shape,
        )

        candidate = (
            float(
                n_values[
                    i
                ]
            ),
            float(
                beta_values[
                    k
                ]
            ),
        )

        sufficiently_separated = True

        for old_n, old_beta in seeds:
            if (
                abs(
                    candidate[
                        0
                    ]
                    - old_n
                )
                <= 2.0
                * n_step
                and
                abs(
                    candidate[
                        1
                    ]
                    - old_beta
                )
                <= 2.0
                * beta_step
            ):
                sufficiently_separated = False
                break

        if sufficiently_separated:
            seeds.append(
                candidate
            )

        if len(
            seeds
        ) >= N_OPTIMIZER_SEEDS:
            break

    return seeds


# =============================================================================
# CONTINUOUS PROFILED 2D OPTIMIZATION
# =============================================================================

def continuous_refinement(
    seeds,
    data,
):
    results = []

    print()
    print("G. CONTINUOUS 2D REFINEMENT")
    print("=" * 130)

    def scaled_objective(
        x,
    ):
        n_value = (
            float(
                x[
                    0
                ]
            )
            * N_MAX
        )

        beta = (
            float(
                x[
                    1
                ]
            )
            * BETA_MAX
        )

        return evaluate_parameters(
            n_value,
            beta,
            data,
        )[
            "J"
        ]

    for idx, (
        n_seed,
        beta_seed,
    ) in enumerate(
        seeds,
        start=1,
    ):
        x0 = np.array(
            [
                n_seed
                / N_MAX,

                beta_seed
                / BETA_MAX,
            ],
            dtype=np.float64,
        )

        opt = minimize(
            scaled_objective,
            x0=x0,
            method="L-BFGS-B",
            bounds=[
                (
                    0.0,
                    1.0,
                ),
                (
                    0.0,
                    1.0,
                ),
            ],
            options={
                "ftol":
                    1e-14,

                "gtol":
                    1e-10,

                "maxiter":
                    1000,
            },
        )

        n_opt = (
            float(
                opt.x[
                    0
                ]
            )
            * N_MAX
        )

        beta_opt = (
            float(
                opt.x[
                    1
                ]
            )
            * BETA_MAX
        )

        result = evaluate_parameters(
            n_opt,
            beta_opt,
            data,
        )

        result[
            "optimizer_success"
        ] = bool(
            opt.success
        )

        result[
            "optimizer_message"
        ] = str(
            opt.message
        )

        results.append(
            result
        )

        print(
            f"SEED_{idx} | "
            f"START=({n_seed:.6f},{beta_seed:.6f}) | "
            f"N={n_opt:.12f} | "
            f"BETA={beta_opt:.12f} | "
            f"Q={result['Q']:.3f} | "
            f"J={result['J']:.6f} | "
            f"SUCCESS={opt.success}"
        )

    best = min(
        results,
        key=lambda x:
            x[
                "J"
            ],
    )

    return best


# =============================================================================
# GLOBAL LOCAL-MINIMUM COUNT
# =============================================================================

def count_strict_local_minima(
    j,
):
    if (
        j.shape[
            0
        ] < 3
        or j.shape[
            1
        ] < 3
    ):
        return 0

    center = j[
        1:-1,
        1:-1,
    ]

    is_min = np.ones(
        center.shape,
        dtype=bool,
    )

    for di in [
        -1,
        0,
        1,
    ]:
        for dj in [
            -1,
            0,
            1,
        ]:
            if (
                di == 0
                and dj == 0
            ):
                continue

            neighbour = j[
                1 + di:
                j.shape[
                    0
                ] - 1 + di,
                1 + dj:
                j.shape[
                    1
                ] - 1 + dj,
            ]

            is_min &= (
                center
                < neighbour
            )

    return int(
        np.sum(
            is_min
        )
    )


# =============================================================================
# LOCAL STABILITY
# =============================================================================

def local_stability(
    local_surface,
    best,
):
    rows = []

    j_min = float(
        best[
            "J"
        ]
    )

    n_grid, beta_grid = np.meshgrid(
        local_surface[
            "n_values"
        ],
        local_surface[
            "beta_values"
        ],
        indexing="ij",
    )

    print()
    print("I. LOCAL PARAMETER STABILITY")
    print("=" * 150)

    for pct in [
        0.01,
        0.05,
        0.10,
    ]:
        threshold = (
            j_min
            * (
                1.0
                + pct
            )
        )

        mask = (
            local_surface[
                "J"
            ]
            <= threshold
        )

        if not np.any(
            mask
        ):
            # If numerical saturation makes the relative region
            # narrower than the local grid, retain the exact candidate
            # as a one-point diagnostic.
            n_values = np.array(
                [
                    best[
                        "n"
                    ]
                ]
            )

            beta_values = np.array(
                [
                    best[
                        "beta"
                    ]
                ]
            )

            q_values = np.array(
                [
                    best[
                        "Q"
                    ]
                ]
            )

        else:
            n_values = n_grid[
                mask
            ]

            beta_values = beta_grid[
                mask
            ]

            q_values = local_surface[
                "Q"
            ][
                mask
            ]

        if len(
            n_values
        ) >= 3:
            corr = float(
                np.corrcoef(
                    n_values,
                    beta_values,
                )[
                    0,
                    1
                ]
            )
        else:
            corr = math.nan

        row = {
            "threshold_pct":
                100.0
                * pct,

            "point_count":
                len(
                    n_values
                ),

            "n_min":
                float(
                    np.min(
                        n_values
                    )
                ),

            "n_max":
                float(
                    np.max(
                        n_values
                    )
                ),

            "beta_min":
                float(
                    np.min(
                        beta_values
                    )
                ),

            "beta_max":
                float(
                    np.max(
                        beta_values
                    )
                ),

            "Q_min":
                float(
                    np.min(
                        q_values
                    )
                ),

            "Q_max":
                float(
                    np.max(
                        q_values
                    )
                ),

            "n_beta_correlation":
                corr,
        }

        rows.append(
            row
        )

        print(
            f"WITHIN_+{int(pct * 100)}PCT | "
            f"POINTS={row['point_count']} | "
            f"N=[{row['n_min']:.9f},{row['n_max']:.9f}] | "
            f"BETA=[{row['beta_min']:.9f},{row['beta_max']:.9f}] | "
            f"Q=[{row['Q_min']:.3f},{row['Q_max']:.3f}] | "
            f"CORR_N_BETA={corr}"
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# JACOBIAN / IDENTIFIABILITY
# =============================================================================

def identifiability_analysis(
    best,
    data,
):
    s = best[
        "S"
    ]

    q = best[
        "Q"
    ]

    n_value = best[
        "n"
    ]

    beta = best[
        "beta"
    ]

    mean_log_c = float(
        np.dot(
            s,
            data[
                "log_c"
            ],
        )
    )

    mean_c = float(
        np.dot(
            s,
            data[
                "c_min"
            ],
        )
    )

    # For globally-normalized S:
    #
    # dS/dn =
    # S * (log(c) - E_S[log(c)])
    #
    # dS/dbeta =
    # S * (E_S[c] - c)

    ds_dn = (
        s
        * (
            data[
                "log_c"
            ]
            - mean_log_c
        )
    )

    ds_dbeta = (
        s
        * (
            mean_c
            - data[
                "c_min"
            ]
        )
    )

    g = (
        data[
            "primary_p"
        ]
        @ s
    )

    dg_dn = (
        data[
            "primary_p"
        ]
        @ ds_dn
    )

    dg_dbeta = (
        data[
            "primary_p"
        ]
        @ ds_dbeta
    )

    jacobian = np.column_stack(
        [
            g,
            q
            * dg_dn,
            q
            * dg_dbeta,
        ]
    )

    rank = int(
        np.linalg.matrix_rank(
            jacobian
        )
    )

    singular = np.linalg.svd(
        jacobian,
        compute_uv=False,
    )

    raw_condition = (
        float(
            singular[
                0
            ]
            /
            singular[
                -1
            ]
        )
        if singular[
            -1
        ] > 0
        else math.inf
    )

    column_norms = np.linalg.norm(
        jacobian,
        axis=0,
    )

    if np.any(
        column_norms <= 0
    ):
        normalized_condition = math.inf
        normalized_singular = np.array(
            [
                math.nan,
                math.nan,
                math.nan,
            ]
        )

        cosine_matrix = np.full(
            (
                3,
                3,
            ),
            np.nan,
        )

    else:
        normalized = (
            jacobian
            /
            column_norms[
                None,
                :
            ]
        )

        normalized_singular = np.linalg.svd(
            normalized,
            compute_uv=False,
        )

        normalized_condition = float(
            normalized_singular[
                0
            ]
            /
            normalized_singular[
                -1
            ]
        )

        cosine_matrix = (
            normalized.T
            @ normalized
        )

    if (
        q > 0
        and n_value > 1e-12
        and beta > 1e-12
    ):
        relative_jacobian = (
            jacobian
            * np.array(
                [
                    q,
                    n_value,
                    beta,
                ]
            )[
                None,
                :
            ]
        )

        relative_singular = np.linalg.svd(
            relative_jacobian,
            compute_uv=False,
        )

        relative_condition = float(
            relative_singular[
                0
            ]
            /
            relative_singular[
                -1
            ]
        )

    else:
        relative_singular = np.array(
            [
                math.nan,
                math.nan,
                math.nan,
            ]
        )

        relative_condition = math.nan

    print()
    print("J. LOCAL IDENTIFIABILITY")
    print("=" * 150)

    print(
        "JACOBIAN_COLUMNS = dY/dQ | dY/dn | dY/dbeta"
    )

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        print(
            f"{section_id} | "
            f"dY_dQ={jacobian[idx,0]:.12e} | "
            f"dY_dn={jacobian[idx,1]:.12e} | "
            f"dY_dbeta={jacobian[idx,2]:.12e}"
        )

    print(
        f"JACOBIAN_RANK = {rank}"
    )

    print(
        "RAW_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in singular
        )
    )

    print(
        f"RAW_CONDITION_NUMBER = {raw_condition:.12e}"
    )

    print(
        "COLUMN_NORMALIZED_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in normalized_singular
        )
    )

    print(
        f"COLUMN_NORMALIZED_CONDITION_NUMBER = "
        f"{normalized_condition:.12f}"
    )

    print(
        "COLUMN_COSINE_MATRIX ="
    )

    print(
        cosine_matrix
    )

    print(
        "RELATIVE_PARAMETER_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in relative_singular
        )
    )

    print(
        f"RELATIVE_PARAMETER_CONDITION_NUMBER = "
        f"{relative_condition}"
    )

    saturation_ratio = (
        best[
            "J"
        ]
        /
        float(
            np.sum(
                data[
                    "observed_primary"
                ]
                ** 2
            )
        )
    )

    print(
        f"PRIMARY_SSE_TO_OBSERVED_SQUARE_SCALE = "
        f"{saturation_ratio:.12e}"
    )

    print(
        "IDENTIFIABILITY_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    rows = []

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        rows.append(
            {
                "record_type":
                    "JACOBIAN_ROW",

                "SECTION_ID":
                    section_id,

                "dY_dQ":
                    jacobian[
                        idx,
                        0
                    ],

                "dY_dn":
                    jacobian[
                        idx,
                        1
                    ],

                "dY_dbeta":
                    jacobian[
                        idx,
                        2
                    ],

                "rank":
                    rank,

                "raw_condition_number":
                    raw_condition,

                "column_normalized_condition_number":
                    normalized_condition,

                "relative_parameter_condition_number":
                    relative_condition,

                "primary_SSE_scale_ratio":
                    saturation_ratio,
            }
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# OPTIONAL PROFILED HESSIAN IN SCALED (n,beta) COORDINATES
# =============================================================================

def profile_hessian_scaled(
    best,
    data,
):
    x = np.array(
        [
            best[
                "n"
            ]
            / N_MAX,

            best[
                "beta"
            ]
            / BETA_MAX,
        ],
        dtype=np.float64,
    )

    h = 1e-3

    if np.any(
        x <= h
    ) or np.any(
        x >= 1.0 - h
    ):
        print(
            "PROFILE_HESSIAN = SKIPPED_NEAR_EXPLORATORY_BOUNDARY"
        )

        return

    def f(
        u,
        v,
    ):
        return evaluate_parameters(
            u
            * N_MAX,
            v
            * BETA_MAX,
            data,
        )[
            "J"
        ]

    u = x[
        0
    ]

    v = x[
        1
    ]

    f00 = f(
        u,
        v,
    )

    fpp_u = f(
        u + h,
        v,
    )

    fmm_u = f(
        u - h,
        v,
    )

    fpp_v = f(
        u,
        v + h,
    )

    fmm_v = f(
        u,
        v - h,
    )

    f_uv_pp = f(
        u + h,
        v + h,
    )

    f_uv_pm = f(
        u + h,
        v - h,
    )

    f_uv_mp = f(
        u - h,
        v + h,
    )

    f_uv_mm = f(
        u - h,
        v - h,
    )

    d2u = (
        fpp_u
        - 2.0
        * f00
        + fmm_u
    ) / (
        h
        * h
    )

    d2v = (
        fpp_v
        - 2.0
        * f00
        + fmm_v
    ) / (
        h
        * h
    )

    duv = (
        f_uv_pp
        - f_uv_pm
        - f_uv_mp
        + f_uv_mm
    ) / (
        4.0
        * h
        * h
    )

    hessian = np.array(
        [
            [
                d2u,
                duv,
            ],
            [
                duv,
                d2v,
            ],
        ],
        dtype=np.float64,
    )

    eigenvalues = np.linalg.eigvalsh(
        hessian
    )

    if (
        eigenvalues[
            0
        ] > 0
    ):
        condition = float(
            eigenvalues[
                -1
            ]
            /
            eigenvalues[
                0
            ]
        )
    else:
        condition = math.inf

    print(
        "PROFILE_HESSIAN_SCALED ="
    )

    print(
        hessian
    )

    print(
        "PROFILE_HESSIAN_EIGENVALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in eigenvalues
        )
    )

    print(
        f"PROFILE_HESSIAN_CONDITION = {condition}"
    )


# =============================================================================
# OLD VS COMBINED
# =============================================================================

def old_vs_combined(
    best,
    data,
    p_by_section,
    old_j,
):
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

    primary_lookup = old_primary.set_index(
        "SECTION_ID"
    )

    sensitivity_lookup = old_sensitivity.set_index(
        "SECTION_ID"
    )

    rows = []

    print()
    print("K. OLD EXPONENTIAL vs COMBINED")
    print("=" * 175)

    for section_id in COMPARISON_IDS:
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

        g = float(
            np.dot(
                p,
                best[
                    "S"
                ],
            )
        )

        new_modelled = (
            commuting_assigned
            +
            best[
                "Q"
            ]
            * g
        )

        if section_id in PRIMARY_IDS:
            old_row = primary_lookup.loc[
                section_id
            ]

            role = "PRIMARY"

        else:
            old_row = sensitivity_lookup.loc[
                section_id
            ]

            role = "SENSITIVITY"

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

        old_rel = float(
            old_row[
                "REL_ERROR"
            ]
        )

        new_residual = (
            observed
            - new_modelled
        )

        new_rel = (
            new_residual
            / observed
        )

        old_abs = abs(
            old_rel
        )

        new_abs = abs(
            new_rel
        )

        improved = (
            new_abs
            < old_abs
        )

        print(
            f"{section_id} | "
            f"ROLE={role} | "
            f"OBS={observed:.3f} | "
            f"OLD={old_modelled:.3f} | "
            f"COMBINED={new_modelled:.3f} | "
            f"OLD_REL={old_rel:+.6f} | "
            f"COMBINED_REL={new_rel:+.6f} | "
            f"ABS_REL_CHANGE={new_abs-old_abs:+.6f} | "
            f"{'IMPROVED' if improved else 'WORSENED'}"
        )

        rows.append(
            {
                "SECTION_ID":
                    section_id,

                "ROLE":
                    role,

                "OBSERVED":
                    observed,

                "OLD_EXPONENTIAL_MODELLED":
                    old_modelled,

                "COMBINED_MODELLED":
                    new_modelled,

                "OLD_REL_ERROR":
                    old_rel,

                "COMBINED_REL_ERROR":
                    new_rel,

                "OLD_ABS_REL_ERROR":
                    old_abs,

                "COMBINED_ABS_REL_ERROR":
                    new_abs,

                "DELTA_ABS_REL_ERROR_COMBINED_MINUS_OLD":
                    new_abs
                    - old_abs,

                "IMPROVED":
                    "YES"
                    if improved
                    else "NO",

                "COMBINED_ASSIGNED_COMMUTING":
                    commuting_assigned,

                "COMBINED_ASSIGNED_NONPENDULAR":
                    best[
                        "Q"
                    ]
                    * g,
            }
        )

    df = pd.DataFrame(
        rows
    )

    sensitivity = df[
        df[
            "ROLE"
        ]
        == "SENSITIVITY"
    ].copy()

    improved_count = int(
        (
            sensitivity[
                "IMPROVED"
            ]
            == "YES"
        ).sum()
    )

    worsened_count = (
        len(
            sensitivity
        )
        - improved_count
    )

    old_mae_rel = float(
        sensitivity[
            "OLD_ABS_REL_ERROR"
        ].mean()
    )

    new_mae_rel = float(
        sensitivity[
            "COMBINED_ABS_REL_ERROR"
        ].mean()
    )

    old_median_rel = float(
        sensitivity[
            "OLD_ABS_REL_ERROR"
        ].median()
    )

    new_median_rel = float(
        sensitivity[
            "COMBINED_ABS_REL_ERROR"
        ].median()
    )

    over = sensitivity[
        sensitivity[
            "COMBINED_REL_ERROR"
        ]
        < 0
    ]

    under = sensitivity[
        sensitivity[
            "COMBINED_REL_ERROR"
        ]
        > 0
    ]

    if len(
        over
    ):
        largest_over = over.loc[
            over[
                "COMBINED_REL_ERROR"
            ].idxmin()
        ]

        largest_over_text = (
            f"{largest_over['SECTION_ID']} | "
            f"REL_ERROR={largest_over['COMBINED_REL_ERROR']:+.6f}"
        )
    else:
        largest_over_text = "NONE"

    if len(
        under
    ):
        largest_under = under.loc[
            under[
                "COMBINED_REL_ERROR"
            ].idxmax()
        ]

        largest_under_text = (
            f"{largest_under['SECTION_ID']} | "
            f"REL_ERROR={largest_under['COMBINED_REL_ERROR']:+.6f}"
        )
    else:
        largest_under_text = "NONE"

    print()
    print("SENSITIVITY GENERALIZATION SUMMARY")
    print("-" * 130)

    print(
        f"EXPOSED_SENSITIVITY_COUNT = {len(sensitivity)}"
    )

    print(
        f"SENSITIVITY_IMPROVED = {improved_count}"
    )

    print(
        f"SENSITIVITY_WORSENED = {worsened_count}"
    )

    print(
        f"OLD_MEAN_ABS_REL_ERROR = {old_mae_rel:.6f}"
    )

    print(
        f"COMBINED_MEAN_ABS_REL_ERROR = {new_mae_rel:.6f}"
    )

    print(
        f"OLD_MEDIAN_ABS_REL_ERROR = {old_median_rel:.6f}"
    )

    print(
        f"COMBINED_MEDIAN_ABS_REL_ERROR = {new_median_rel:.6f}"
    )

    print(
        f"LARGEST_COMBINED_OVERPREDICTION = {largest_over_text}"
    )

    print(
        f"LARGEST_COMBINED_UNDERPREDICTION = {largest_under_text}"
    )

    print()
    print(
        f"OLD_PRIMARY_SSE = {old_j:.6f}"
    )

    print(
        f"COMBINED_PRIMARY_SSE = {best['J']:.6f}"
    )

    print(
        f"PRIMARY_SSE_RATIO_COMBINED_OVER_OLD = "
        f"{best['J']/old_j:.12f}"
    )

    return df


# =============================================================================
# PLOTS
# =============================================================================

def make_surface_plots(
    global_surface,
    local_surface,
    best,
):
    # -------------------------------------------------------------------------
    # Global J surface
    # -------------------------------------------------------------------------

    eps = max(
        best[
            "J"
        ]
        * 1e-9,
        1e-12,
    )

    beta_mesh, n_mesh = np.meshgrid(
        global_surface[
            "beta_values"
        ],
        global_surface[
            "n_values"
        ],
    )

    z = np.log10(
        global_surface[
            "J"
        ]
        + eps
    )

    fig = plt.figure(
        figsize=(
            11,
            7,
        )
    )

    mesh = plt.pcolormesh(
        beta_mesh,
        n_mesh,
        z,
        shading="auto",
    )

    plt.colorbar(
        mesh,
        label="log10(J_profile + eps)",
    )

    plt.scatter(
        [
            best[
                "beta"
            ]
        ],
        [
            best[
                "n"
            ]
        ],
        marker="x",
        s=90,
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "n [-]"
    )

    plt.title(
        "Combined deterrence — global profiled SSE surface"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_GLOBAL_J,
        dpi=170,
    )

    plt.close(
        fig
    )


    # -------------------------------------------------------------------------
    # Local J surface
    # -------------------------------------------------------------------------

    beta_mesh, n_mesh = np.meshgrid(
        local_surface[
            "beta_values"
        ],
        local_surface[
            "n_values"
        ],
    )

    z = np.log10(
        local_surface[
            "J"
        ]
        + eps
    )

    fig = plt.figure(
        figsize=(
            11,
            7,
        )
    )

    mesh = plt.pcolormesh(
        beta_mesh,
        n_mesh,
        z,
        shading="auto",
    )

    plt.colorbar(
        mesh,
        label="log10(J_profile + eps)",
    )

    plt.scatter(
        [
            best[
                "beta"
            ]
        ],
        [
            best[
                "n"
            ]
        ],
        marker="x",
        s=90,
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "n [-]"
    )

    plt.title(
        "Combined deterrence — local profiled SSE surface"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_LOCAL_J,
        dpi=170,
    )

    plt.close(
        fig
    )


    # -------------------------------------------------------------------------
    # Global Q surface
    # -------------------------------------------------------------------------

    beta_mesh, n_mesh = np.meshgrid(
        global_surface[
            "beta_values"
        ],
        global_surface[
            "n_values"
        ],
    )

    fig = plt.figure(
        figsize=(
            11,
            7,
        )
    )

    contour = plt.contourf(
        beta_mesh,
        n_mesh,
        global_surface[
            "Q"
        ]
        / 1_000_000.0,
        levels=20,
    )

    plt.colorbar(
        contour,
        label="Q*(n,beta) [million veh/day]",
    )

    plt.scatter(
        [
            best[
                "beta"
            ]
        ],
        [
            best[
                "n"
            ]
        ],
        marker="x",
        s=90,
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "n [-]"
    )

    plt.title(
        "Combined deterrence — profiled Q surface"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_GLOBAL_Q,
        dpi=170,
    )

    plt.close(
        fig
    )


    # -------------------------------------------------------------------------
    # c_peak contours
    # -------------------------------------------------------------------------

    beta_mesh, n_mesh = np.meshgrid(
        global_surface[
            "beta_values"
        ],
        global_surface[
            "n_values"
        ],
    )

    peak = np.full(
        beta_mesh.shape,
        np.nan,
        dtype=np.float64,
    )

    valid = (
        beta_mesh > 0
    ) & (
        n_mesh > 0
    )

    peak[
        valid
    ] = (
        n_mesh[
            valid
        ]
        /
        beta_mesh[
            valid
        ]
    )

    fig = plt.figure(
        figsize=(
            11,
            7,
        )
    )

    levels = [
        5,
        10,
        15,
        20,
        30,
        45,
        60,
        90,
        120,
        150,
    ]

    contour = plt.contour(
        beta_mesh,
        n_mesh,
        peak,
        levels=levels,
    )

    plt.clabel(
        contour,
        inline=True,
        fontsize=8,
        fmt="%g min",
    )

    plt.scatter(
        [
            best[
                "beta"
            ]
        ],
        [
            best[
                "n"
            ]
        ],
        marker="x",
        s=90,
    )

    plt.xlabel(
        "beta [1/min]"
    )

    plt.ylabel(
        "n [-]"
    )

    plt.title(
        "Combined deterrence — c_peak = n / beta"
    )

    plt.tight_layout()

    fig.savefig(
        PLOT_C_PEAK,
        dpi=170,
    )

    plt.close(
        fig
    )


def make_deterrence_plot(
    data,
    old_beta,
    best,
):
    c_values = np.linspace(
        float(
            np.min(
                data[
                    "c_min"
                ]
            )
        ),
        float(
            np.max(
                data[
                    "c_min"
                ]
            )
        ),
        700,
    )

    old_curve = np.exp(
        -old_beta
        * c_values
    )

    combined_curve = (
        np.power(
            c_values,
            best[
                "n"
            ],
        )
        *
        np.exp(
            -best[
                "beta"
            ]
            * c_values
        )
    )

    old_curve /= np.max(
        old_curve
    )

    combined_curve /= np.max(
        combined_curve
    )

    fig = plt.figure(
        figsize=(
            11,
            7,
        )
    )

    plt.plot(
        c_values,
        old_curve,
        label=(
            f"Old exponential "
            f"(beta={old_beta:.4f})"
        ),
    )

    plt.plot(
        c_values,
        combined_curve,
        label=(
            f"Combined "
            f"(n={best['n']:.3f}, "
            f"beta={best['beta']:.4f})"
        ),
    )

    if (
        best[
            "n"
        ] > 0
        and best[
            "beta"
        ] > 0
    ):
        peak = (
            best[
                "n"
            ]
            /
            best[
                "beta"
            ]
        )

        if (
            peak
            >= c_values[
                0
            ]
            and peak
            <= c_values[
                -1
            ]
        ):
            plt.axvline(
                peak,
                linestyle="--",
                label=(
                    f"Combined c_peak={peak:.1f} min"
                ),
            )

    plt.xlabel(
        "Travel time c [min]"
    )

    plt.ylabel(
        "Normalized deterrence weight"
    )

    plt.title(
        "Deterrence shape comparison"
    )

    plt.legend()

    plt.tight_layout()

    fig.savefig(
        PLOT_DETERRENCE,
        dpi=170,
    )

    plt.close(
        fig
    )


def make_comparison_plots(
    comparison,
):
    # Sensitivity
    df = comparison[
        comparison[
            "ROLE"
        ]
        == "SENSITIVITY"
    ].copy()

    x = np.arange(
        len(
            df
        )
    )

    width = 0.26

    fig = plt.figure(
        figsize=(
            12,
            7,
        )
    )

    plt.bar(
        x - width,
        df[
            "OBSERVED"
        ],
        width,
        label="Observed",
    )

    plt.bar(
        x,
        df[
            "OLD_EXPONENTIAL_MODELLED"
        ],
        width,
        label="Old exponential",
    )

    plt.bar(
        x + width,
        df[
            "COMBINED_MODELLED"
        ],
        width,
        label="Combined",
    )

    plt.xticks(
        x,
        df[
            "SECTION_ID"
        ],
    )

    plt.ylabel(
        "LIGHT vehicles/day"
    )

    plt.title(
        "Exposed sensitivity sections — observed vs modelled"
    )

    plt.legend()

    plt.tight_layout()

    fig.savefig(
        PLOT_SENSITIVITY,
        dpi=170,
    )

    plt.close(
        fig
    )


    # Primary
    df = comparison[
        comparison[
            "ROLE"
        ]
        == "PRIMARY"
    ].copy()

    x = np.arange(
        len(
            df
        )
    )

    fig = plt.figure(
        figsize=(
            10,
            7,
        )
    )

    plt.bar(
        x - width,
        df[
            "OBSERVED"
        ],
        width,
        label="Observed",
    )

    plt.bar(
        x,
        df[
            "OLD_EXPONENTIAL_MODELLED"
        ],
        width,
        label="Old exponential",
    )

    plt.bar(
        x + width,
        df[
            "COMBINED_MODELLED"
        ],
        width,
        label="Combined",
    )

    plt.xticks(
        x,
        df[
            "SECTION_ID"
        ],
    )

    plt.ylabel(
        "LIGHT vehicles/day"
    )

    plt.title(
        "PRIMARY sections — observed vs modelled"
    )

    plt.legend()

    plt.tight_layout()

    fig.savefig(
        PLOT_PRIMARY,
        dpi=170,
    )

    plt.close(
        fig
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 140)
    print(
        "5.8E-R2 — COMBINED DETERRENCE DIAGNOSTIC TEST"
    )
    print("=" * 140)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. CONTRACT")
    print("-" * 140)

    print(
        "REFERENCE_MODEL = PRE_R1_GLOBAL_NORMALIZED_GRAVITY"
    )

    print(
        "DETERRENCE = c^n * exp(-beta*c)"
    )

    print(
        "NESTED_EXPONENTIAL_CASE = n=0"
    )

    print(
        "PARAMETERS = Q|n|beta"
    )

    print(
        "NUMERICAL_SEARCH_DIMENSION = 2"
    )

    print(
        "Q_PROFILED_ANALYTICALLY = YES"
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
        "ANAS_2025_USED = NO"
    )

    print(
        "PARAMETER_FREEZE = NO"
    )

    # -------------------------------------------------------------------------
    # B. Exploratory bounds
    # -------------------------------------------------------------------------

    print()
    print("B. EXPLORATORY SEARCH DOMAIN — NOT FROZEN")
    print("-" * 140)

    print(
        f"N_MIN = {N_MIN:.6f}"
    )

    print(
        f"N_MAX = {N_MAX:.6f}"
    )

    print(
        f"BETA_MIN = {BETA_MIN:.6f} 1/min"
    )

    print(
        f"BETA_MAX = {BETA_MAX:.6f} 1/min"
    )

    print(
        f"GLOBAL_GRID = "
        f"{GLOBAL_N_POINTS} x {GLOBAL_BETA_POINTS} "
        f"= {GLOBAL_N_POINTS*GLOBAL_BETA_POINTS:,}"
    )

    print(
        f"LOCAL_GRID = "
        f"{LOCAL_N_POINTS} x {LOCAL_BETA_POINTS} "
        f"= {LOCAL_N_POINTS*LOCAL_BETA_POINTS:,}"
    )

    print(
        "BOUND_STATUS = EXPLORATORY_ONLY"
    )

    # -------------------------------------------------------------------------
    # C. Preflight
    # -------------------------------------------------------------------------

    print()
    print("C. FILE PREFLIGHT")
    print("-" * 140)

    inputs = [
        E3A_OPERATOR,
        E3A_MINIMUM,
        E4_PRIMARY,
        E4_SENSITIVITY,
        E4B_OPERATOR,
        R1_MISSING_OPERATOR,
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
        GLOBAL_SURFACE_OUT,
        LOCAL_SURFACE_OUT,
        MINIMUM_OUT,
        IDENTIFIABILITY_OUT,
        STABILITY_OUT,
        PRIMARY_OUT,
        COMPARISON_OUT,
        PLOT_GLOBAL_J,
        PLOT_LOCAL_J,
        PLOT_GLOBAL_Q,
        PLOT_C_PEAK,
        PLOT_DETERRENCE,
        PLOT_SENSITIVITY,
        PLOT_PRIMARY,
    ]

    for path in outputs:
        require_output_absent(
            path
        )

    data = load_data()

    p_by_section = load_section_operators(
        data
    )

    print()
    print(
        f"C_MIN = {np.min(data['c_min']):.6f} min"
    )

    print(
        f"C_MAX = {np.max(data['c_min']):.6f} min"
    )

    # -------------------------------------------------------------------------
    # D. Nested exponential invariant
    # -------------------------------------------------------------------------

    (
        qa_df,
        old_beta,
        old_q,
        old_j,
    ) = nested_model_qa(
        data
    )

    qa_df.to_csv(
        QA_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # E. Global surface
    # -------------------------------------------------------------------------

    n_global = np.linspace(
        N_MIN,
        N_MAX,
        GLOBAL_N_POINTS,
        dtype=np.float64,
    )

    beta_global = np.linspace(
        BETA_MIN,
        BETA_MAX,
        GLOBAL_BETA_POINTS,
        dtype=np.float64,
    )

    global_surface = calculate_surface(
        n_global,
        beta_global,
        data,
        "E. GLOBAL",
    )

    global_df = surface_to_dataframe(
        global_surface,
        "GLOBAL",
    )

    global_df.to_csv(
        GLOBAL_SURFACE_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    flat_best = int(
        np.argmin(
            global_surface[
                "J"
            ]
        )
    )

    g_i, g_k = np.unravel_index(
        flat_best,
        global_surface[
            "J"
        ].shape,
    )

    global_best_n = float(
        n_global[
            g_i
        ]
    )

    global_best_beta = float(
        beta_global[
            g_k
        ]
    )

    global_best_j = float(
        global_surface[
            "J"
        ][
            g_i,
            g_k
        ]
    )

    global_best_q = float(
        global_surface[
            "Q"
        ][
            g_i,
            g_k
        ]
    )

    print()
    print("F. GLOBAL SURFACE BEST")
    print("=" * 140)

    print(
        f"GLOBAL_GRID_BEST_N = {global_best_n:.12f}"
    )

    print(
        f"GLOBAL_GRID_BEST_BETA = {global_best_beta:.12f}"
    )

    print(
        f"GLOBAL_GRID_BEST_C_PEAK = "
        f"{c_peak(global_best_n, global_best_beta)}"
    )

    print(
        f"GLOBAL_GRID_BEST_Q = {global_best_q:.6f}"
    )

    print(
        f"GLOBAL_GRID_BEST_J = {global_best_j:.6f}"
    )

    global_local_minima = count_strict_local_minima(
        global_surface[
            "J"
        ]
    )

    print(
        f"GLOBAL_STRICT_LOCAL_MINIMA_COUNT = {global_local_minima}"
    )

    # -------------------------------------------------------------------------
    # G. Continuous multistart refinement
    # -------------------------------------------------------------------------

    seeds = choose_promising_seeds(
        global_surface
    )

    print()
    print(
        "PROMISING_GLOBAL_SEEDS = "
        + " | ".join(
            f"({n:.6f},{b:.6f})"
            for n, b in seeds
        )
    )

    best = continuous_refinement(
        seeds,
        data,
    )

    # -------------------------------------------------------------------------
    # H. Local dense surface around continuous best
    # -------------------------------------------------------------------------

    local_n_lo = max(
        N_MIN,
        best[
            "n"
        ]
        - LOCAL_N_HALF_WIDTH,
    )

    local_n_hi = min(
        N_MAX,
        best[
            "n"
        ]
        + LOCAL_N_HALF_WIDTH,
    )

    local_beta_lo = max(
        BETA_MIN,
        best[
            "beta"
        ]
        - LOCAL_BETA_HALF_WIDTH,
    )

    local_beta_hi = min(
        BETA_MAX,
        best[
            "beta"
        ]
        + LOCAL_BETA_HALF_WIDTH,
    )

    n_local = np.linspace(
        local_n_lo,
        local_n_hi,
        LOCAL_N_POINTS,
        dtype=np.float64,
    )

    beta_local = np.linspace(
        local_beta_lo,
        local_beta_hi,
        LOCAL_BETA_POINTS,
        dtype=np.float64,
    )

    local_surface = calculate_surface(
        n_local,
        beta_local,
        data,
        "H. LOCAL",
    )

    local_df = surface_to_dataframe(
        local_surface,
        "LOCAL",
    )

    local_df.to_csv(
        LOCAL_SURFACE_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    local_flat_best = int(
        np.argmin(
            local_surface[
                "J"
            ]
        )
    )

    l_i, l_k = np.unravel_index(
        local_flat_best,
        local_surface[
            "J"
        ].shape,
    )

    local_seed_n = float(
        n_local[
            l_i
        ]
    )

    local_seed_beta = float(
        beta_local[
            l_k
        ]
    )

    # One final continuous refinement starting from the local dense-grid best.
    def final_scaled_objective(
        x,
    ):
        return evaluate_parameters(
            float(
                x[
                    0
                ]
            )
            * N_MAX,
            float(
                x[
                    1
                ]
            )
            * BETA_MAX,
            data,
        )[
            "J"
        ]

    final_opt = minimize(
        final_scaled_objective,
        x0=np.array(
            [
                local_seed_n
                / N_MAX,

                local_seed_beta
                / BETA_MAX,
            ],
            dtype=np.float64,
        ),
        method="L-BFGS-B",
        bounds=[
            (
                0.0,
                1.0,
            ),
            (
                0.0,
                1.0,
            ),
        ],
        options={
            "ftol":
                1e-15,

            "gtol":
                1e-11,

            "maxiter":
                1000,
        },
    )

    final_result = evaluate_parameters(
        float(
            final_opt.x[
                0
            ]
        )
        * N_MAX,

        float(
            final_opt.x[
                1
            ]
        )
        * BETA_MAX,

        data,
    )

    if final_result[
        "J"
    ] < best[
        "J"
    ]:
        best = final_result

    # -------------------------------------------------------------------------
    # I. Candidate
    # -------------------------------------------------------------------------

    boundary_n = (
        abs(
            best[
                "n"
            ]
            - N_MIN
        )
        < 1e-7
        or
        abs(
            best[
                "n"
            ]
            - N_MAX
        )
        < 1e-7
    )

    boundary_beta = (
        abs(
            best[
                "beta"
            ]
            - BETA_MIN
        )
        < 1e-7
        or
        abs(
            best[
                "beta"
            ]
            - BETA_MAX
        )
        < 1e-7
    )

    print()
    print("I. COMBINED NUMERICAL CANDIDATE")
    print("=" * 140)

    print(
        f"N_NUMERICAL_MIN = {best['n']:.12f}"
    )

    print(
        f"BETA_NUMERICAL_MIN = {best['beta']:.12f} 1/min"
    )

    print(
        f"C_PEAK_NUMERICAL_MIN = "
        f"{c_peak(best['n'], best['beta'])}"
    )

    print(
        f"Q_NUMERICAL_MIN = {best['Q']:.6f}"
    )

    print(
        f"J_NUMERICAL_MIN = {best['J']:.12f}"
    )

    print(
        f"RELATIVE_SSE_DIAGNOSTIC = "
        f"{best['relative_SSE']:.12f}"
    )

    print(
        f"N_BOUNDARY_MINIMUM = {'YES' if boundary_n else 'NO'}"
    )

    print(
        f"BETA_BOUNDARY_MINIMUM = "
        f"{'YES' if boundary_beta else 'NO'}"
    )

    print(
        f"OLD_EXPONENTIAL_BETA = {old_beta:.12f}"
    )

    print(
        f"OLD_EXPONENTIAL_Q = {old_q:.6f}"
    )

    print(
        f"OLD_EXPONENTIAL_J = {old_j:.6f}"
    )

    print(
        f"COMBINED_PRIMARY_J_OVER_OLD = "
        f"{best['J']/old_j:.12f}"
    )

    # -------------------------------------------------------------------------
    # J. Local stability / identifiability
    # -------------------------------------------------------------------------

    stability_df = local_stability(
        local_surface,
        best,
    )

    stability_df.to_csv(
        STABILITY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    identifiability_df = identifiability_analysis(
        best,
        data,
    )

    identifiability_df.to_csv(
        IDENTIFIABILITY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    profile_hessian_scaled(
        best,
        data,
    )

    # -------------------------------------------------------------------------
    # K. PRIMARY fit
    # -------------------------------------------------------------------------

    primary_rows = []

    print()
    print("K. COMBINED PRIMARY FIT")
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
            f"OBS={observed:.3f} | "
            f"COMBINED={modelled:.3f} | "
            f"RES={residual:+.3f} | "
            f"REL={relative_error:+.6f}"
        )

        primary_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "OBSERVED":
                    observed,

                "COMBINED_MODELLED":
                    modelled,

                "RESIDUAL":
                    residual,

                "REL_ERROR":
                    relative_error,
            }
        )

    pd.DataFrame(
        primary_rows
    ).to_csv(
        PRIMARY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # L. Out-of-calibration comparison
    # -------------------------------------------------------------------------

    comparison_df = old_vs_combined(
        best,
        data,
        p_by_section,
        old_j,
    )

    comparison_df.to_csv(
        COMPARISON_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # M. Numerical minimum output
    # -------------------------------------------------------------------------

    pd.DataFrame(
        [
            {
                "model":
                    "GLOBAL_NORMALIZED_COMBINED_DETERRENCE",

                "n":
                    best[
                        "n"
                    ],

                "beta":
                    best[
                        "beta"
                    ],

                "c_peak_min":
                    c_peak(
                        best[
                            "n"
                        ],
                        best[
                            "beta"
                        ],
                    ),

                "Q_star":
                    best[
                        "Q"
                    ],

                "J_profile":
                    best[
                        "J"
                    ],

                "relative_SSE_diagnostic":
                    best[
                        "relative_SSE"
                    ],

                "n_boundary":
                    boundary_n,

                "beta_boundary":
                    boundary_beta,

                "parameters_frozen":
                    "NO",

                "ANAS_2025_used":
                    "NO",
            }
        ]
    ).to_csv(
        MINIMUM_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # N. Plots
    # -------------------------------------------------------------------------

    make_surface_plots(
        global_surface,
        local_surface,
        best,
    )

    make_deterrence_plot(
        data,
        old_beta,
        best,
    )

    make_comparison_plots(
        comparison_df
    )

    # -------------------------------------------------------------------------
    # O. Outputs
    # -------------------------------------------------------------------------

    print()
    print("L. OUTPUTS")
    print("-" * 140)

    for path in outputs:
        print(
            "OUTPUT =",
            path,
        )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / DIAGNOSTIC / NOT FROZEN"
    )

    # -------------------------------------------------------------------------
    # P. Gate
    # -------------------------------------------------------------------------

    print()
    print("M. R2 GATE STATE")
    print("=" * 140)

    print(
        "NESTED_MODEL_INVARIANT = PASS"
    )

    print(
        f"N_CANDIDATE = {best['n']:.12f}"
    )

    print(
        f"BETA_CANDIDATE = {best['beta']:.12f}"
    )

    print(
        f"Q_CANDIDATE = {best['Q']:.6f}"
    )

    print(
        f"C_PEAK_CANDIDATE = "
        f"{c_peak(best['n'], best['beta'])}"
    )

    print(
        f"PRIMARY_SSE = {best['J']:.12f}"
    )

    print(
        "IDENTIFIABILITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "SPATIAL_GENERALIZATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "R2_FINAL_VERDICT = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "N_FROZEN = NO"
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
        "FRLM_STARTED = NO"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

