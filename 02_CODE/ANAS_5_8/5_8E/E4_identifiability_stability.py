
"""
E4 — IDENTIFIABILITY + STABILITY + PLAUSIBILITY GATE
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Verificare se il numerical candidate prodotto da E3-A:

    beta = 0.045953794473 1/min
    Q    = 1552629.518131 veh/day

è sufficientemente:

- identificabile;
- stabile;
- plausibile;
- robusto;

per essere proposto alla Chat Madre come candidate freeze.

E4 NON migliora il fit.
E4 NON modifica Q o beta.
E4 NON cambia la frozen objective.
E4 NON usa ANAS 2025.
E4 NON usa le SENSITIVITY per retuning.

ANALYSES
--------
A. Mathematical identifiability
   - Jacobian wrt Q and beta
   - rank
   - singular values
   - raw condition number
   - scaled / column-normalized conditioning
   - column cosine / quasi-collinearity

B. Profile stability
   - beta range within +1%, +5%, +10% of J_min
   - corresponding Q*(beta) range
   - local J probes around beta*

C. Leave-one-out PRIMARY diagnostics
   - 920032 + 920039
   - 920032 + 920035
   - 920039 + 920035

D. Diagnostic loss sensitivity
   - relative squared error
   - baseline SSE remains frozen and unchanged

E. PRIMARY residual decomposition
   - residual
   - absolute error
   - relative error
   - squared-error contribution
   - share of total SSE

F. Q plausibility
   - sum C_ij^ISTAT
   - Q / sum C
   - total modelled LIGHT demand
   - non-pendular share

G. 13 SENSITIVITY diagnostics
   - baseline Q,beta only
   - NO retuning
   - MODEL_EXPOSURE=NO classified separately

INPUTS
------
Temporary E3-A artifacts:
- E3A_final_primary_operator_candidate_v01.npz
- E3A_beta_profile_candidate_v01.csv
- E3A_numerical_minimum_candidate_v01.csv

Frozen inputs:
- ANAS_5_8D_calibration_mapping_v01.csv
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz

Temporary E1-C regression evidence:
- E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv

OUTPUTS
-------
Only under:
C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\E4_diagnostics

- E4_jacobian_candidate_v01.csv
- E4_profile_stability_candidate_v01.csv
- E4_LOO_candidate_v01.csv
- E4_loss_sensitivity_candidate_v01.csv
- E4_primary_residuals_candidate_v01.csv
- E4_Q_plausibility_candidate_v01.csv
- E4_sensitivity_sections_candidate_v01.csv

ASSUMPTIONS
-----------
- Final Gravity v0 PRIMARY set:
    920032
    920039
    920035

- Baseline objective:
    unweighted absolute SSE / NLLS

- Deterrence:
    exponential exp(-beta*c)

- Q >= 0.

- beta units:
    1/minute

- Baseline candidate is NOT frozen yet.

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA
- ISTAT commuting LIGHT v0
- ANAS 5.8D canonical mapping

FILES WRITTEN
-------------
Only temporary diagnostic outputs under E4_diagnostics.

FILES NEVER MODIFIED
--------------------
Anything under:
C:\\Tesi\\Tesi_QGIS\\02_package

The original ANAS 5.8D canonical mapping is NEVER modified.
"""

from pathlib import Path
import csv
import math

import numpy as np
import pandas as pd

from scipy.optimize import minimize_scalar
from scipy.sparse import load_npz


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

E3A_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E3A_beta_profile"
)

E1C_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E1C_sensitivity_screen"
)

OUT_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E4_diagnostics"
)

OD_ROOT = (
    ROOT
    / "02_package"
    / "od_paths_osm_light"
)

GRAPH_ROOT = (
    ROOT
    / "02_package"
    / "grafo_operativo_osm"
)

ANAS_ROOT = (
    ROOT
    / "02_package"
    / "anas_calibration_v0"
)


E3A_OPERATOR = (
    E3A_ROOT
    / "E3A_final_primary_operator_candidate_v01.npz"
)

E3A_PROFILE = (
    E3A_ROOT
    / "E3A_beta_profile_candidate_v01.csv"
)

E3A_MINIMUM = (
    E3A_ROOT
    / "E3A_numerical_minimum_candidate_v01.csv"
)

E1C_SCREEN = (
    E1C_ROOT
    / "E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv"
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


JACOBIAN_OUT = (
    OUT_ROOT
    / "E4_jacobian_candidate_v01.csv"
)

PROFILE_STABILITY_OUT = (
    OUT_ROOT
    / "E4_profile_stability_candidate_v01.csv"
)

LOO_OUT = (
    OUT_ROOT
    / "E4_LOO_candidate_v01.csv"
)

LOSS_OUT = (
    OUT_ROOT
    / "E4_loss_sensitivity_candidate_v01.csv"
)

PRIMARY_RESIDUALS_OUT = (
    OUT_ROOT
    / "E4_primary_residuals_candidate_v01.csv"
)

Q_PLAUSIBILITY_OUT = (
    OUT_ROOT
    / "E4_Q_plausibility_candidate_v01.csv"
)

SENSITIVITY_OUT = (
    OUT_ROOT
    / "E4_sensitivity_sections_candidate_v01.csv"
)


PRIMARY_IDS = [
    "920032",
    "920039",
    "920035",
]

EXPECTED_SENSITIVITY_COUNT = 13


# Mother-ratified E3-A candidate.
BASELINE_BETA = 0.045953794473
BASELINE_Q = 1552629.518131


# Same exploratory E3-A beta domain.
# This is diagnostic, NOT a new frozen methodological bound.
BETA_MIN = 0.0
BETA_MAX = 0.20
DIAGNOSTIC_GRID_POINTS = 5001
BETA_BLOCK_SIZE = 64

PATH_SCAN_CHUNK = 10_000_000


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


def pct_delta(value, baseline):
    if baseline == 0:
        return math.nan

    return 100.0 * (
        value / baseline - 1.0
    )


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
        "gravity_base",
        "C_ij_ISTAT",
        "p_matrix",
        "observed_2024",
        "commuting_assigned",
    }

    missing = (
        required
        - set(z.files)
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
            "Unexpected E3-A PRIMARY order: "
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

    p_matrix = z[
        "p_matrix"
    ].astype(
        np.float64
    )

    observed = z[
        "observed_2024"
    ].astype(
        np.float64
    )

    commuting_assigned = z[
        "commuting_assigned"
    ].astype(
        np.float64
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

    n_od = len(
        c_min
    )

    if n_od != 46010:
        raise RuntimeError(
            f"Expected 46010 OD, found {n_od}"
        )

    if gravity_base.shape != (
        n_od,
    ):
        raise RuntimeError(
            "gravity_base shape mismatch."
        )

    if commuting.shape != (
        n_od,
    ):
        raise RuntimeError(
            "commuting shape mismatch."
        )

    if p_matrix.shape != (
        3,
        n_od,
    ):
        raise RuntimeError(
            f"p_matrix shape unexpected: {p_matrix.shape}"
        )

    return {
        "origin":
            origin,

        "destination":
            destination,

        "c_min":
            c_min,

        "gravity_base":
            gravity_base,

        "commuting":
            commuting,

        "p_matrix":
            p_matrix,

        "observed":
            observed,

        "commuting_assigned":
            commuting_assigned,
    }


# =============================================================================
# GRAVITY / PROFILE CORE
# =============================================================================

def gravity_s_and_derivative(
    beta,
    gravity_base,
    c_min,
):
    weights = (
        gravity_base
        *
        np.exp(
            -beta
            * c_min
        )
    )

    denominator = float(
        np.sum(
            weights
        )
    )

    if denominator <= 0:
        raise RuntimeError(
            "Gravity normalization denominator <= 0."
        )

    s = (
        weights
        / denominator
    )

    # E_S[c]
    mean_c = float(
        np.dot(
            s,
            c_min,
        )
    )

    # dS/dbeta =
    # S * (E_S[c] - c)
    ds_dbeta = (
        s
        *
        (
            mean_c
            - c_min
        )
    )

    return (
        s,
        ds_dbeta,
        mean_c,
    )


def calculate_g(
    beta,
    gravity_base,
    c_min,
    p_matrix,
):
    (
        s,
        ds_dbeta,
        mean_c,
    ) = gravity_s_and_derivative(
        beta,
        gravity_base,
        c_min,
    )

    g = (
        p_matrix
        @ s
    )

    dg_dbeta = (
        p_matrix
        @ ds_dbeta
    )

    return (
        g,
        dg_dbeta,
        s,
        mean_c,
    )


def profile_q(
    g,
    observed,
    commuting_assigned,
    relative=False,
):
    target = (
        observed
        - commuting_assigned
    )

    if relative:
        weights = (
            1.0
            / (
                observed
                * observed
            )
        )
    else:
        weights = np.ones(
            len(observed),
            dtype=np.float64,
        )

    numerator = float(
        np.sum(
            weights
            * g
            * target
        )
    )

    denominator = float(
        np.sum(
            weights
            * g
            * g
        )
    )

    if denominator <= 0:
        raise RuntimeError(
            "Profile-Q denominator <= 0."
        )

    q = max(
        0.0,
        numerator
        / denominator,
    )

    modelled = (
        commuting_assigned
        +
        q
        * g
    )

    residual = (
        observed
        - modelled
    )

    absolute_sse = float(
        np.sum(
            residual
            * residual
        )
    )

    relative_error = (
        residual
        / observed
    )

    relative_sse = float(
        np.sum(
            relative_error
            * relative_error
        )
    )

    objective = (
        relative_sse
        if relative
        else absolute_sse
    )

    return {
        "Q":
            q,

        "modelled":
            modelled,

        "residual":
            residual,

        "relative_error":
            relative_error,

        "absolute_sse":
            absolute_sse,

        "relative_sse":
            relative_sse,

        "objective":
            objective,
    }


def evaluate_single_profile(
    beta,
    data,
    section_indices,
    relative=False,
):
    (
        g_all,
        _,
        _,
        _,
    ) = calculate_g(
        beta,
        data[
            "gravity_base"
        ],
        data[
            "c_min"
        ],
        data[
            "p_matrix"
        ],
    )

    idx = np.asarray(
        section_indices,
        dtype=np.int64,
    )

    result = profile_q(
        g_all[
            idx
        ],
        data[
            "observed"
        ][
            idx
        ],
        data[
            "commuting_assigned"
        ][
            idx
        ],
        relative=relative,
    )

    result[
        "G"
    ] = g_all[
        idx
    ]

    return result


# =============================================================================
# ONE GLOBAL G(beta) GRID
# =============================================================================

def calculate_g_grid(
    betas,
    data,
):
    betas = np.asarray(
        betas,
        dtype=np.float64,
    )

    g_grid = np.empty(
        (
            len(betas),
            3,
        ),
        dtype=np.float64,
    )

    base = data[
        "gravity_base"
    ]

    c_min = data[
        "c_min"
    ]

    p_matrix = data[
        "p_matrix"
    ]

    print()
    print("F. DIAGNOSTIC G(beta) GRID")
    print("-" * 110)

    print(
        f"BETA_GRID_MIN = {betas[0]:.6f}"
    )

    print(
        f"BETA_GRID_MAX = {betas[-1]:.6f}"
    )

    print(
        f"BETA_GRID_POINTS = {len(betas)}"
    )

    for lo in range(
        0,
        len(betas),
        BETA_BLOCK_SIZE,
    ):
        hi = min(
            lo
            + BETA_BLOCK_SIZE,
            len(betas),
        )

        b = betas[
            lo:hi
        ]

        weights = np.exp(
            -b[
                :,
                None
            ]
            * c_min[
                None,
                :
            ]
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
                "Grid gravity denominator <= 0."
            )

        g = (
            weights
            @ p_matrix.T
        )

        g /= denom[
            :,
            None
        ]

        g_grid[
            lo:hi,
            :
        ] = g

    return g_grid


# =============================================================================
# PROFILE FROM PRECOMPUTED G GRID
# =============================================================================

def profile_from_g_grid(
    betas,
    g_grid,
    observed,
    commuting_assigned,
    section_indices,
    relative=False,
):
    idx = np.asarray(
        section_indices,
        dtype=np.int64,
    )

    g = g_grid[
        :,
        idx
    ]

    y = observed[
        idx
    ]

    c = commuting_assigned[
        idx
    ]

    target = (
        y
        - c
    )

    if relative:
        weights = (
            1.0
            / (
                y
                * y
            )
        )
    else:
        weights = np.ones(
            len(idx),
            dtype=np.float64,
        )

    numerator = np.sum(
        g
        * (
            weights
            * target
        )[
            None,
            :
        ],
        axis=1,
    )

    denominator = np.sum(
        g
        * g
        * weights[
            None,
            :
        ],
        axis=1,
    )

    if np.any(
        denominator <= 0
    ):
        raise RuntimeError(
            "Grid profile-Q denominator <= 0."
        )

    q = np.maximum(
        0.0,
        numerator
        / denominator,
    )

    modelled = (
        c[
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
        y[
            None,
            :
        ]
        - modelled
    )

    abs_sse = np.sum(
        residual
        * residual,
        axis=1,
    )

    rel_error = (
        residual
        / y[
            None,
            :
        ]
    )

    rel_sse = np.sum(
        rel_error
        * rel_error,
        axis=1,
    )

    objective = (
        rel_sse
        if relative
        else abs_sse
    )

    return pd.DataFrame(
        {
            "beta":
                betas,

            "Q_star":
                q,

            "objective":
                objective,

            "absolute_SSE":
                abs_sse,

            "relative_SSE":
                rel_sse,
        }
    )


# =============================================================================
# CONTINUOUS REFINEMENT OF A DIAGNOSTIC PROFILE
# =============================================================================

def refine_profile(
    grid_df,
    data,
    section_indices,
    relative=False,
):
    best_idx = int(
        grid_df[
            "objective"
        ].idxmin()
    )

    beta_grid_best = float(
        grid_df.loc[
            best_idx,
            "beta",
        ]
    )

    # Diagnostic local interval around the grid minimum.
    half_width = 0.005

    lo = max(
        BETA_MIN,
        beta_grid_best
        - half_width,
    )

    hi = min(
        BETA_MAX,
        beta_grid_best
        + half_width,
    )

    def objective(beta):
        result = evaluate_single_profile(
            beta,
            data,
            section_indices,
            relative=relative,
        )

        return float(
            result[
                "objective"
            ]
        )

    opt = minimize_scalar(
        objective,
        bounds=(
            lo,
            hi,
        ),
        method="bounded",
        options={
            "xatol": 1e-11,
            "maxiter": 500,
        },
    )

    candidates = [
        lo,
        float(
            opt.x
        ),
        hi,
    ]

    candidate_results = []

    for beta in candidates:
        result = evaluate_single_profile(
            beta,
            data,
            section_indices,
            relative=relative,
        )

        candidate_results.append(
            (
                beta,
                result,
            )
        )

    beta_best, result_best = min(
        candidate_results,
        key=lambda item:
            item[
                1
            ][
                "objective"
            ],
    )

    boundary = (
        abs(
            beta_best
            - BETA_MIN
        )
        < 1e-8
        or
        abs(
            beta_best
            - BETA_MAX
        )
        < 1e-8
    )

    return {
        "beta":
            float(
                beta_best
            ),

        "Q":
            float(
                result_best[
                    "Q"
                ]
            ),

        "objective":
            float(
                result_best[
                    "objective"
                ]
            ),

        "absolute_SSE":
            float(
                result_best[
                    "absolute_sse"
                ]
            ),

        "relative_SSE":
            float(
                result_best[
                    "relative_sse"
                ]
            ),

        "modelled":
            result_best[
                "modelled"
            ],

        "residual":
            result_best[
                "residual"
            ],

        "optimizer_success":
            bool(
                opt.success
            ),

        "boundary_minimum":
            boundary,
    }


# =============================================================================
# ANAS SENSITIVITY MAPPING
# =============================================================================

def load_sensitivity_mapping():
    rows = []

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
            if (
                clean(
                    row[
                        "ROLE"
                    ]
                ).upper()
                != "SENSITIVITY"
            ):
                continue

            section_id = clean(
                row[
                    "SECTION_ID"
                ]
            )

            edges = parse_pipe_ints(
                row[
                    "RELEVANT_DIRECTED_EDGE_IDS"
                ]
            )

            if not edges:
                raise RuntimeError(
                    f"{section_id}: no canonical edge IDs."
                )

            rows.append(
                {
                    "SECTION_ID":
                        section_id,

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

                    "QGIS_REVIEW_STATUS":
                        clean(
                            row[
                                "QGIS_REVIEW_STATUS"
                            ]
                        ),

                    "EDGE_IDS":
                        edges,
                }
            )

    if (
        len(rows)
        != EXPECTED_SENSITIVITY_COUNT
    ):
        raise RuntimeError(
            "Expected 13 sensitivity sections, "
            f"found {len(rows)}"
        )

    return rows


# =============================================================================
# LOAD ACCESS-PATH -> OD MAPPING
# =============================================================================

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

    if len(df) != 414090:
        raise RuntimeError(
            f"Expected 414090 access paths, found {len(df)}"
        )

    df[
        "path_idx"
    ] = pd.to_numeric(
        df[
            "path_idx"
        ],
        errors="raise",
    ).astype(
        np.int64
    )

    df[
        "origin_PRO_COM"
    ] = pd.to_numeric(
        df[
            "origin_PRO_COM"
        ],
        errors="raise",
    ).astype(
        np.int64
    )

    df[
        "destination_PRO_COM"
    ] = pd.to_numeric(
        df[
            "destination_PRO_COM"
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

    od_df = pd.DataFrame(
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
        od_df,
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
            "Access-path -> OD join incomplete."
        )

    df = df.sort_values(
        "path_idx"
    ).reset_index(
        drop=True
    )

    expected = np.arange(
        len(df),
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
            "path_idx not canonical 0..414089."
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


# =============================================================================
# SCAN 13 SENSITIVITY SECTIONS
# =============================================================================

def scan_sensitivity_paths(
    sensitivity_rows,
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

    if len(
        offsets
    ) != 414091:
        raise RuntimeError(
            "Unexpected offsets length."
        )

    if len(
        transitions
    ) != 598707601:
        raise RuntimeError(
            "Unexpected transition slot count."
        )

    # 13 bits fit uint16.
    section_bit = {
        row[
            "SECTION_ID"
        ]:
        np.uint16(
            1
            << idx
        )

        for idx, row
        in enumerate(
            sensitivity_rows
        )
    }

    slot_mask = np.zeros(
        b5_edgeid.nnz,
        dtype=np.uint16,
    )

    print()
    print("P. SENSITIVITY CANONICAL EDGE QA")
    print("-" * 110)

    for row in sensitivity_rows:
        section_id = row[
            "SECTION_ID"
        ]

        bit = section_bit[
            section_id
        ]

        for edge_id in row[
            "EDGE_IDS"
        ]:
            matches = np.flatnonzero(
                b5_edgeid.data
                == edge_id
            )

            print(
                f"{section_id} | "
                f"EDGE_ID={edge_id} | "
                f"B5_SLOT_OCCURRENCES={len(matches)}"
            )

            if len(
                matches
            ) == 0:
                raise RuntimeError(
                    f"{section_id}: edge {edge_id} absent from B5."
                )

            slot_mask[
                matches
            ] |= bit

    path_hits = {
        row[
            "SECTION_ID"
        ]:
        set()

        for row
        in sensitivity_rows
    }

    n_slots = len(
        transitions
    )

    print()
    print("Q. FROZEN SENSITIVITY PATH SCAN")
    print("-" * 110)

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

        local_positions = np.flatnonzero(
            masks
        )

        if local_positions.size > 0:
            global_positions = (
                local_positions
                + lo
            )

            path_indices = (
                np.searchsorted(
                    offsets,
                    global_positions,
                    side="right",
                )
                - 1
            )

            matched_masks = masks[
                local_positions
            ]

            for (
                section_id,
                bit,
            ) in section_bit.items():

                relevant = (
                    matched_masks
                    & bit
                ) != 0

                if not np.any(
                    relevant
                ):
                    continue

                unique_paths = np.unique(
                    path_indices[
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
            100
            * hi
            / n_slots
        )

        if (
            progress
            >= next_progress
            or hi
            == n_slots
        ):
            print(
                f"SCAN_PROGRESS = {progress:3d}%"
            )

            while (
                next_progress
                <= progress
            ):
                next_progress += 10

    return path_hits


# =============================================================================
# BUILD SENSITIVITY p_ij^a
# =============================================================================

def build_sensitivity_operator(
    sensitivity_rows,
    path_hits,
    path_to_od,
    pair_weight,
    n_od,
):
    p_matrix = np.zeros(
        (
            len(
                sensitivity_rows
            ),
            n_od,
        ),
        dtype=np.float64,
    )

    path_counts = {}
    od_counts = {}

    for idx, row in enumerate(
        sensitivity_rows
    ):
        section_id = row[
            "SECTION_ID"
        ]

        paths = np.asarray(
            sorted(
                path_hits[
                    section_id
                ]
            ),
            dtype=np.int64,
        )

        if len(
            paths
        ) == 0:
            p = np.zeros(
                n_od,
                dtype=np.float64,
            )

        else:
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
                f"{section_id}: p_ij^a > 1."
            )

        p = np.minimum(
            p,
            1.0,
        )

        p_matrix[
            idx,
            :
        ] = p

        path_counts[
            section_id
        ] = int(
            len(
                paths
            )
        )

        od_counts[
            section_id
        ] = int(
            np.count_nonzero(
                p > 0
            )
        )

    return (
        p_matrix,
        path_counts,
        od_counts,
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 120)
    print(
        "E4 — IDENTIFIABILITY + STABILITY + PLAUSIBILITY GATE"
    )
    print("=" * 120)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. CONTRACT")
    print("-" * 120)

    print(
        "BASELINE_OBJECTIVE = "
        "UNWEIGHTED SSE / NLLS"
    )

    print(
        "PRIMARY = "
        + "|".join(
            PRIMARY_IDS
        )
    )

    print(
        f"BASELINE_BETA = {BASELINE_BETA:.12f} 1/min"
    )

    print(
        f"BASELINE_Q = {BASELINE_Q:.6f} veh/day"
    )

    print(
        "FIT_IMPROVEMENT_ALLOWED = NO"
    )

    print(
        "SENSITIVITY_RETUNING = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    # -------------------------------------------------------------------------
    # B. File preflight
    # -------------------------------------------------------------------------

    print()
    print("B. FILE PREFLIGHT")
    print("-" * 120)

    input_files = [
        E3A_OPERATOR,
        E3A_PROFILE,
        E3A_MINIMUM,
        E1C_SCREEN,
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
        JACOBIAN_OUT,
        PROFILE_STABILITY_OUT,
        LOO_OUT,
        LOSS_OUT,
        PRIMARY_RESIDUALS_OUT,
        Q_PLAUSIBILITY_OUT,
        SENSITIVITY_OUT,
    ]

    for path in output_files:
        require_output_absent(
            path
        )

    # -------------------------------------------------------------------------
    # C. Load E3-A operator + regression candidate
    # -------------------------------------------------------------------------

    data = load_e3a_operator()

    minimum_df = pd.read_csv(
        E3A_MINIMUM
    )

    if len(
        minimum_df
    ) != 1:
        raise RuntimeError(
            "E3-A numerical minimum file must contain exactly 1 row."
        )

    beta_file = float(
        minimum_df.iloc[
            0
        ][
            "beta"
        ]
    )

    q_file = float(
        minimum_df.iloc[
            0
        ][
            "Q_star"
        ]
    )

    if abs(
        beta_file
        - BASELINE_BETA
    ) > 1e-9:
        raise RuntimeError(
            "Baseline beta does not match E3-A artifact."
        )

    if abs(
        q_file
        - BASELINE_Q
    ) > 0.1:
        raise RuntimeError(
            "Baseline Q does not match E3-A artifact."
        )

    print()
    print("C. E3-A CANDIDATE REGRESSION")
    print("-" * 120)

    print(
        f"E3A_FILE_BETA = {beta_file:.12f}"
    )

    print(
        f"E3A_FILE_Q = {q_file:.6f}"
    )

    print(
        "CANDIDATE_REGRESSION = PASS"
    )

    # -------------------------------------------------------------------------
    # D. Baseline gravity quantities
    # -------------------------------------------------------------------------

    (
        g_base,
        dg_dbeta,
        s_base,
        gravity_mean_c,
    ) = calculate_g(
        BASELINE_BETA,
        data[
            "gravity_base"
        ],
        data[
            "c_min"
        ],
        data[
            "p_matrix"
        ],
    )

    modelled_base = (
        data[
            "commuting_assigned"
        ]
        +
        BASELINE_Q
        * g_base
    )

    residual_base = (
        data[
            "observed"
        ]
        - modelled_base
    )

    j_base = float(
        np.sum(
            residual_base
            * residual_base
        )
    )

    print()
    print("D. BASELINE RECONSTRUCTION")
    print("-" * 120)

    print(
        f"GRAVITY_MEAN_C_AT_BETA = {gravity_mean_c:.6f} min"
    )

    print(
        f"RECONSTRUCTED_J = {j_base:.6f}"
    )

    # -------------------------------------------------------------------------
    # E. Mathematical identifiability
    # -------------------------------------------------------------------------

    # Jacobian of Yhat wrt [Q, beta]
    #
    # dY/dQ    = G_a(beta)
    # dY/dbeta = Q * dG_a/dbeta

    jacobian = np.column_stack(
        [
            g_base,
            BASELINE_Q
            * dg_dbeta,
        ]
    )

    rank = int(
        np.linalg.matrix_rank(
            jacobian
        )
    )

    singular_values = np.linalg.svd(
        jacobian,
        compute_uv=False,
    )

    raw_condition = float(
        singular_values[
            0
        ]
        /
        singular_values[
            -1
        ]
    )

    col_norms = np.linalg.norm(
        jacobian,
        axis=0,
    )

    if np.any(
        col_norms
        <= 0
    ):
        raise RuntimeError(
            "Jacobian contains zero column."
        )

    normalized_jacobian = (
        jacobian
        / col_norms[
            None,
            :
        ]
    )

    normalized_singular_values = (
        np.linalg.svd(
            normalized_jacobian,
            compute_uv=False,
        )
    )

    normalized_condition = float(
        normalized_singular_values[
            0
        ]
        /
        normalized_singular_values[
            -1
        ]
    )

    column_cosine = float(
        np.dot(
            jacobian[
                :,
                0
            ],
            jacobian[
                :,
                1
            ],
        )
        /
        (
            col_norms[
                0
            ]
            *
            col_norms[
                1
            ]
        )
    )

    # Scale parameters to relative/log-like perturbations.
    # This is much less sensitive to the radically different units of Q and beta.
    scaled_jacobian = np.column_stack(
        [
            BASELINE_Q
            * jacobian[
                :,
                0
            ],

            BASELINE_BETA
            * jacobian[
                :,
                1
            ],
        ]
    )

    scaled_singular_values = np.linalg.svd(
        scaled_jacobian,
        compute_uv=False,
    )

    scaled_condition = float(
        scaled_singular_values[
            0
        ]
        /
        scaled_singular_values[
            -1
        ]
    )

    print()
    print("E. MATHEMATICAL IDENTIFIABILITY")
    print("=" * 120)

    print("JACOBIAN_ROWS = PRIMARY")
    print("JACOBIAN_COLUMNS = dY/dQ | dY/dbeta")
    print()

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        print(
            f"{section_id} | "
            f"dY_dQ={jacobian[idx, 0]:.12e} | "
            f"dY_dbeta={jacobian[idx, 1]:.12e}"
        )

    print()
    print(
        f"JACOBIAN_RANK = {rank}"
    )

    print(
        "RAW_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in singular_values
        )
    )

    print(
        f"RAW_CONDITION_NUMBER = {raw_condition:.12e}"
    )

    print(
        "RAW_CONDITION_NOTE = "
        "UNIT_DEPENDENT_BECAUSE_Q_AND_BETA_HAVE_DIFFERENT_SCALES"
    )

    print(
        "COLUMN_NORMALIZED_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in normalized_singular_values
        )
    )

    print(
        f"COLUMN_NORMALIZED_CONDITION_NUMBER = "
        f"{normalized_condition:.12f}"
    )

    print(
        f"JACOBIAN_COLUMN_COSINE = {column_cosine:.12f}"
    )

    print(
        "SCALED_SINGULAR_VALUES = "
        + "|".join(
            f"{x:.12e}"
            for x in scaled_singular_values
        )
    )

    print(
        f"SCALED_CONDITION_NUMBER = {scaled_condition:.12f}"
    )

    print(
        "IDENTIFIABILITY_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    jacobian_df = pd.DataFrame(
        {
            "SECTION_ID":
                PRIMARY_IDS,

            "dYhat_dQ":
                jacobian[
                    :,
                    0
                ],

            "dYhat_dbeta":
                jacobian[
                    :,
                    1
                ],

            "scaled_dYhat_dlogQ":
                scaled_jacobian[
                    :,
                    0
                ],

            "scaled_dYhat_dlogbeta":
                scaled_jacobian[
                    :,
                    1
                ],
        }
    )

    jacobian_df.to_csv(
        JACOBIAN_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # F. One diagnostic G(beta) grid for LOO and loss sensitivity
    # -------------------------------------------------------------------------

    beta_grid = np.linspace(
        BETA_MIN,
        BETA_MAX,
        DIAGNOSTIC_GRID_POINTS,
        dtype=np.float64,
    )

    g_grid = calculate_g_grid(
        beta_grid,
        data,
    )

    # -------------------------------------------------------------------------
    # G. Existing E3-A profile stability
    # -------------------------------------------------------------------------

    profile = pd.read_csv(
        E3A_PROFILE
    )

    required_profile_cols = {
        "scan_scope",
        "beta",
        "Q_star",
        "J_profile",
    }

    missing = (
        required_profile_cols
        - set(
            profile.columns
        )
    )

    if missing:
        raise RuntimeError(
            f"E3-A profile missing columns: {sorted(missing)}"
        )

    profile = profile[
        [
            "scan_scope",
            "beta",
            "Q_star",
            "J_profile",
        ]
    ].copy()

    profile = profile.sort_values(
        [
            "beta",
            "J_profile",
        ]
    ).drop_duplicates(
        subset=[
            "beta"
        ],
        keep="first",
    )

    threshold_rows = []

    print()
    print("G. PROFILE STABILITY")
    print("=" * 120)

    print(
        f"BASELINE_BETA = {BASELINE_BETA:.12f}"
    )

    print(
        f"J_MIN = {j_base:.6f}"
    )

    for pct in [
        0.01,
        0.05,
        0.10,
    ]:
        threshold = (
            j_base
            * (
                1.0
                + pct
            )
        )

        inside = profile[
            profile[
                "J_profile"
            ]
            <= threshold
        ]

        if len(
            inside
        ) == 0:
            raise RuntimeError(
                f"No profile points within +{pct:.0%}"
            )

        beta_lo = float(
            inside[
                "beta"
            ].min()
        )

        beta_hi = float(
            inside[
                "beta"
            ].max()
        )

        q_lo = float(
            inside[
                "Q_star"
            ].min()
        )

        q_hi = float(
            inside[
                "Q_star"
            ].max()
        )

        width = (
            beta_hi
            - beta_lo
        )

        threshold_rows.append(
            {
                "record_type":
                    "J_THRESHOLD_RANGE",

                "threshold_pct":
                    100.0
                    * pct,

                "beta":
                    math.nan,

                "J":
                    threshold,

                "delta_J_pct":
                    100.0
                    * pct,

                "beta_lo":
                    beta_lo,

                "beta_hi":
                    beta_hi,

                "beta_width":
                    width,

                "Q_lo":
                    q_lo,

                "Q_hi":
                    q_hi,
            }
        )

        print(
            f"WITHIN_+{int(pct * 100)}PCT | "
            f"BETA=[{beta_lo:.12f}, {beta_hi:.12f}] | "
            f"WIDTH={width:.12f} | "
            f"Q=[{q_lo:.3f}, {q_hi:.3f}]"
        )

    # Direct local probes around candidate beta.
    print()
    print("LOCAL_J_PROBES")

    local_probe_rows = []

    for rel_shift in [
        -0.10,
        -0.05,
        -0.02,
        -0.01,
        0.00,
        0.01,
        0.02,
        0.05,
        0.10,
    ]:
        beta_probe = (
            BASELINE_BETA
            * (
                1.0
                + rel_shift
            )
        )

        result = evaluate_single_profile(
            beta_probe,
            data,
            [
                0,
                1,
                2,
            ],
            relative=False,
        )

        j_probe = float(
            result[
                "absolute_sse"
            ]
        )

        delta_j_pct = (
            100.0
            * (
                j_probe
                / j_base
                - 1.0
            )
        )

        print(
            f"BETA_SHIFT={rel_shift * 100:+.1f}% | "
            f"BETA={beta_probe:.12f} | "
            f"Q*={result['Q']:.3f} | "
            f"J={j_probe:.3f} | "
            f"DELTA_J={delta_j_pct:+.3f}%"
        )

        local_probe_rows.append(
            {
                "record_type":
                    "LOCAL_BETA_PROBE",

                "threshold_pct":
                    math.nan,

                "beta":
                    beta_probe,

                "J":
                    j_probe,

                "delta_J_pct":
                    delta_j_pct,

                "beta_lo":
                    math.nan,

                "beta_hi":
                    math.nan,

                "beta_width":
                    math.nan,

                "Q_lo":
                    float(
                        result[
                            "Q"
                        ]
                    ),

                "Q_hi":
                    float(
                        result[
                            "Q"
                        ]
                    ),
            }
        )

    pd.DataFrame(
        threshold_rows
        + local_probe_rows
    ).to_csv(
        PROFILE_STABILITY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # H. Leave-one-out PRIMARY
    # -------------------------------------------------------------------------

    loo_specs = [
        {
            "name":
                "920032+920039",

            "indices":
                [
                    0,
                    1,
                ],

            "held_out_index":
                2,
        },
        {
            "name":
                "920032+920035",

            "indices":
                [
                    0,
                    2,
                ],

            "held_out_index":
                1,
        },
        {
            "name":
                "920039+920035",

            "indices":
                [
                    1,
                    2,
                ],

            "held_out_index":
                0,
        },
    ]

    loo_rows = []

    print()
    print("H. LEAVE-ONE-OUT PRIMARY")
    print("=" * 140)

    for spec in loo_specs:
        grid_df = profile_from_g_grid(
            beta_grid,
            g_grid,
            data[
                "observed"
            ],
            data[
                "commuting_assigned"
            ],
            spec[
                "indices"
            ],
            relative=False,
        )

        result = refine_profile(
            grid_df,
            data,
            spec[
                "indices"
            ],
            relative=False,
        )

        beta_loo = result[
            "beta"
        ]

        q_loo = result[
            "Q"
        ]

        held_idx = spec[
            "held_out_index"
        ]

        # Evaluate held-out PRIMARY without retuning further.
        (
            g_loo_all,
            _,
            _,
            _,
        ) = calculate_g(
            beta_loo,
            data[
                "gravity_base"
            ],
            data[
                "c_min"
            ],
            data[
                "p_matrix"
            ],
        )

        held_modelled = float(
            data[
                "commuting_assigned"
            ][
                held_idx
            ]
            +
            q_loo
            * g_loo_all[
                held_idx
            ]
        )

        held_observed = float(
            data[
                "observed"
            ][
                held_idx
            ]
        )

        held_residual = (
            held_observed
            - held_modelled
        )

        held_rel_error = (
            held_residual
            / held_observed
        )

        beta_diff_pct = pct_delta(
            beta_loo,
            BASELINE_BETA,
        )

        q_diff_pct = pct_delta(
            q_loo,
            BASELINE_Q,
        )

        print(
            f"{spec['name']} | "
            f"BETA={beta_loo:.12f} | "
            f"Q={q_loo:.3f} | "
            f"J={result['absolute_SSE']:.6f} | "
            f"C_HALF={c_half(beta_loo):.6f} | "
            f"DELTA_BETA={beta_diff_pct:+.3f}% | "
            f"DELTA_Q={q_diff_pct:+.3f}% | "
            f"BOUNDARY={'YES' if result['boundary_minimum'] else 'NO'}"
        )

        print(
            f"    HELD_OUT={PRIMARY_IDS[held_idx]} | "
            f"OBS={held_observed:.3f} | "
            f"MODEL={held_modelled:.3f} | "
            f"REL_ERROR={held_rel_error:+.6f}"
        )

        loo_rows.append(
            {
                "fit_sections":
                    spec[
                        "name"
                    ],

                "held_out_section":
                    PRIMARY_IDS[
                        held_idx
                    ],

                "beta_LOO":
                    beta_loo,

                "Q_LOO":
                    q_loo,

                "J_LOO":
                    result[
                        "absolute_SSE"
                    ],

                "c_half_LOO":
                    c_half(
                        beta_loo
                    ),

                "beta_pct_diff_vs_baseline":
                    beta_diff_pct,

                "Q_pct_diff_vs_baseline":
                    q_diff_pct,

                "boundary_minimum":
                    result[
                        "boundary_minimum"
                    ],

                "held_out_observed":
                    held_observed,

                "held_out_modelled":
                    held_modelled,

                "held_out_residual":
                    held_residual,

                "held_out_relative_error":
                    held_rel_error,
            }
        )

    pd.DataFrame(
        loo_rows
    ).to_csv(
        LOO_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "LOO_STABILITY_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    # -------------------------------------------------------------------------
    # I. Loss sensitivity — RSE diagnostic only
    # -------------------------------------------------------------------------

    rse_grid = profile_from_g_grid(
        beta_grid,
        g_grid,
        data[
            "observed"
        ],
        data[
            "commuting_assigned"
        ],
        [
            0,
            1,
            2,
        ],
        relative=True,
    )

    rse_result = refine_profile(
        rse_grid,
        data,
        [
            0,
            1,
            2,
        ],
        relative=True,
    )

    beta_rse = rse_result[
        "beta"
    ]

    q_rse = rse_result[
        "Q"
    ]

    print()
    print("I. LOSS SENSITIVITY — DIAGNOSTIC ONLY")
    print("=" * 120)

    print(
        "BASELINE_LOSS = UNWEIGHTED_ABSOLUTE_SSE"
    )

    print(
        "DIAGNOSTIC_LOSS = RELATIVE_SQUARED_ERROR"
    )

    print(
        f"BETA_RSE = {beta_rse:.12f}"
    )

    print(
        f"Q_RSE = {q_rse:.6f}"
    )

    print(
        f"BETA_RSE_DIFF = "
        f"{pct_delta(beta_rse, BASELINE_BETA):+.3f}%"
    )

    print(
        f"Q_RSE_DIFF = "
        f"{pct_delta(q_rse, BASELINE_Q):+.3f}%"
    )

    print(
        f"RSE_OBJECTIVE_AT_RSE_MIN = "
        f"{rse_result['relative_SSE']:.12f}"
    )

    print(
        f"ABSOLUTE_SSE_AT_RSE_MIN = "
        f"{rse_result['absolute_SSE']:.6f}"
    )

    print(
        "BASELINE_LOSS_CHANGED = NO"
    )

    pd.DataFrame(
        [
            {
                "diagnostic_loss":
                    "RELATIVE_SQUARED_ERROR",

                "beta":
                    beta_rse,

                "Q":
                    q_rse,

                "beta_pct_diff_vs_baseline":
                    pct_delta(
                        beta_rse,
                        BASELINE_BETA,
                    ),

                "Q_pct_diff_vs_baseline":
                    pct_delta(
                        q_rse,
                        BASELINE_Q,
                    ),

                "relative_SSE":
                    rse_result[
                        "relative_SSE"
                    ],

                "absolute_SSE":
                    rse_result[
                        "absolute_SSE"
                    ],

                "boundary_minimum":
                    rse_result[
                        "boundary_minimum"
                    ],
            }
        ]
    ).to_csv(
        LOSS_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # J. PRIMARY residual decomposition
    # -------------------------------------------------------------------------

    squared_error = (
        residual_base
        * residual_base
    )

    sse_share = (
        squared_error
        / j_base
    )

    primary_rows = []

    print()
    print("J. PRIMARY RESIDUAL STRUCTURE")
    print("=" * 130)

    for idx, section_id in enumerate(
        PRIMARY_IDS
    ):
        observed = float(
            data[
                "observed"
            ][
                idx
            ]
        )

        modelled = float(
            modelled_base[
                idx
            ]
        )

        residual = float(
            residual_base[
                idx
            ]
        )

        abs_error = abs(
            residual
        )

        rel_error = (
            residual
            / observed
        )

        sq = float(
            squared_error[
                idx
            ]
        )

        share = float(
            sse_share[
                idx
            ]
        )

        print(
            f"{section_id} | "
            f"OBS={observed:.3f} | "
            f"MODEL={modelled:.3f} | "
            f"RES={residual:+.3f} | "
            f"ABS={abs_error:.3f} | "
            f"REL={rel_error:+.6f} | "
            f"SQ={sq:.3f} | "
            f"SSE_SHARE={share:.6f}"
        )

        primary_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "OBSERVED":
                    observed,

                "MODELLED":
                    modelled,

                "RESIDUAL_VEH_DAY":
                    residual,

                "ABS_ERROR":
                    abs_error,

                "REL_ERROR":
                    rel_error,

                "SQUARED_ERROR_CONTRIBUTION":
                    sq,

                "SHARE_OF_TOTAL_SSE":
                    share,
            }
        )

    dominant_idx = int(
        np.argmax(
            sse_share
        )
    )

    print()
    print(
        "DOMINANT_SSE_SECTION =",
        PRIMARY_IDS[
            dominant_idx
        ],
    )

    print(
        "DOMINANT_SSE_SHARE = "
        f"{float(sse_share[dominant_idx]):.6f}"
    )

    pd.DataFrame(
        primary_rows
    ).to_csv(
        PRIMARY_RESIDUALS_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # K. Q plausibility
    # -------------------------------------------------------------------------

    sum_c = float(
        np.sum(
            data[
                "commuting"
            ]
        )
    )

    total_light = (
        sum_c
        + BASELINE_Q
    )

    q_over_c = (
        BASELINE_Q
        / sum_c
    )

    nonpend_share = (
        BASELINE_Q
        / total_light
    )

    commuting_share = (
        sum_c
        / total_light
    )

    print()
    print("K. Q PLAUSIBILITY")
    print("=" * 120)

    print(
        f"SUM_C_INTERMUNICIPAL = {sum_c:.6f} veh/day"
    )

    print(
        f"Q_NONPENDULAR = {BASELINE_Q:.6f} veh/day"
    )

    print(
        f"TOTAL_LIGHT_MODEL_DEMAND = {total_light:.6f} veh/day"
    )

    print(
        f"Q_OVER_SUM_C = {q_over_c:.6f}"
    )

    print(
        f"NONPENDULAR_SHARE = {nonpend_share:.6f}"
    )

    print(
        f"COMMUTING_SHARE = {commuting_share:.6f}"
    )

    print(
        "Q_PLAUSIBILITY_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    pd.DataFrame(
        [
            {
                "SUM_C_INTERMUNICIPAL":
                    sum_c,

                "Q_NONPENDULAR":
                    BASELINE_Q,

                "TOTAL_LIGHT_MODEL_DEMAND":
                    total_light,

                "Q_OVER_SUM_C":
                    q_over_c,

                "NONPENDULAR_SHARE":
                    nonpend_share,

                "COMMUTING_SHARE":
                    commuting_share,
            }
        ]
    ).to_csv(
        Q_PLAUSIBILITY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # L. Prepare sensitivity section operator
    # -------------------------------------------------------------------------

    sensitivity_rows = (
        load_sensitivity_mapping()
    )

    path_to_od, pair_weight = (
        load_access_path_metadata(
            data
        )
    )

    path_hits = scan_sensitivity_paths(
        sensitivity_rows
    )

    (
        sensitivity_p,
        sensitivity_path_counts,
        sensitivity_od_counts,
    ) = build_sensitivity_operator(
        sensitivity_rows,
        path_hits,
        path_to_od,
        pair_weight,
        len(
            data[
                "c_min"
            ]
        ),
    )

    # -------------------------------------------------------------------------
    # M. E1-C regression
    # -------------------------------------------------------------------------

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
    print("R. E1-C SENSITIVITY REGRESSION")
    print("=" * 120)

    for idx, row in enumerate(
        sensitivity_rows
    ):
        section_id = row[
            "SECTION_ID"
        ]

        if section_id not in e1c_lookup.index:
            raise RuntimeError(
                f"{section_id}: missing from E1-C screen."
            )

        expected_path = int(
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

        actual_path = (
            sensitivity_path_counts[
                section_id
            ]
        )

        actual_od = (
            sensitivity_od_counts[
                section_id
            ]
        )

        ok = (
            expected_path
            == actual_path
            and
            expected_od
            == actual_od
        )

        print(
            f"{section_id} = "
            f"{'PASS' if ok else 'FAIL'} | "
            f"PATH={actual_path} | "
            f"OD={actual_od}"
        )

        if not ok:
            raise RuntimeError(
                f"{section_id}: E1-C regression mismatch."
            )

    # -------------------------------------------------------------------------
    # N. 13 sensitivity diagnostics — baseline candidate only
    # -------------------------------------------------------------------------

    sensitivity_c = (
        sensitivity_p
        @ data[
            "commuting"
        ]
    )

    sensitivity_g = (
        sensitivity_p
        @ s_base
    )

    sensitivity_modelled = (
        sensitivity_c
        +
        BASELINE_Q
        * sensitivity_g
    )

    sensitivity_output_rows = []

    print()
    print("S. 13 SENSITIVITY DIAGNOSTICS — NO RETUNING")
    print("=" * 170)

    for idx, row in enumerate(
        sensitivity_rows
    ):
        section_id = row[
            "SECTION_ID"
        ]

        observed = row[
            "OBSERVED"
        ]

        path_count = (
            sensitivity_path_counts[
                section_id
            ]
        )

        od_count = (
            sensitivity_od_counts[
                section_id
            ]
        )

        exposure = (
            "YES"
            if od_count > 0
            else "NO"
        )

        if exposure == "NO":
            classification = (
                "NOT_REPRESENTED_BY_CURRENT_DOMAIN"
            )

            modelled = math.nan
            residual = math.nan
            rel_error = math.nan

            interpretation = (
                "CURRENT_DOMAIN_NOT_REPRESENTATIVE"
            )

        else:
            modelled = float(
                sensitivity_modelled[
                    idx
                ]
            )

            residual = (
                observed
                - modelled
            )

            rel_error = (
                residual
                / observed
            )

            classification = (
                "MODEL_EXPOSURE_YES"
            )

            # Do not infer causality from the residual alone.
            interpretation = (
                "NO_CAUSAL_CLASS_ASSIGNED"
            )

        print(
            f"{section_id} | "
            f"ROAD={row['ROAD']} | "
            f"QUALITY={row['QUALITY_CLASS']} | "
            f"EXTERNAL={row['EXTERNAL_EXPOSURE']} | "
            f"MODEL_EXPOSURE={exposure} | "
            f"PATH_HITS={path_count} | "
            f"OD={od_count} | "
            f"OBS={observed:.3f} | "
            f"MODEL="
            f"{'NA' if math.isnan(modelled) else f'{modelled:.3f}'} | "
            f"RES="
            f"{'NA' if math.isnan(residual) else f'{residual:+.3f}'} | "
            f"REL="
            f"{'NA' if math.isnan(rel_error) else f'{rel_error:+.6f}'} | "
            f"CLASS={classification}"
        )

        sensitivity_output_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "ROAD":
                    row[
                        "ROAD"
                    ],

                "QUALITY_CLASS":
                    row[
                        "QUALITY_CLASS"
                    ],

                "EXTERNAL_EXPOSURE":
                    row[
                        "EXTERNAL_EXPOSURE"
                    ],

                "MODEL_EXPOSURE":
                    exposure,

                "PATH_HITS":
                    path_count,

                "OD_P_GT_0":
                    od_count,

                "OBSERVED":
                    observed,

                "MODELLED":
                    modelled,

                "RESIDUAL_VEH_DAY":
                    residual,

                "REL_ERROR":
                    rel_error,

                "DOMAIN_CLASSIFICATION":
                    classification,

                "ERROR_INTERPRETATION":
                    interpretation,
            }
        )

    pd.DataFrame(
        sensitivity_output_rows
    ).to_csv(
        SENSITIVITY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # O. Outputs
    # -------------------------------------------------------------------------

    print()
    print("T. OUTPUTS")
    print("-" * 120)

    for path in output_files:
        print(
            "OUTPUT =",
            path,
        )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / DIAGNOSTIC / NOT FROZEN"
    )

    # -------------------------------------------------------------------------
    # P. Gate state
    # -------------------------------------------------------------------------

    print()
    print("U. E4 GATE STATE")
    print("=" * 120)

    print(
        "IDENTIFIABILITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "PROFILE_STABILITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "LOO_STABILITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "LOSS_SENSITIVITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "Q_PLAUSIBILITY = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "E4_FINAL_VERDICT = "
        "PENDING_CHAT_INTERPRETATION"
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


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

