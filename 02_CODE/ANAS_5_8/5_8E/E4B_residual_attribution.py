"""
E4-B — RESIDUAL ATTRIBUTION SMALL TEST
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Attribuire il traffico modellato alle singole OD comunali per:

    920032 — SS54
    920022 — RA13
    920040 — SS54

usando ESCLUSIVAMENTE il candidate E3-A:

    beta = 0.045953794473 1/min
    Q    = 1552629.518131 veh/day

Lo scopo NON è migliorare il fit.

Lo scopo è distinguere tra:

A. mismatch concentrato in poche OD/path
   -> possibile ASSIGNMENT_REPRESENTATION;

B. mismatch diffuso su molte OD
   -> maggiore evidenza di DEMAND_MODEL_MISMATCH
      e/o MODEL_SCALE_MISMATCH.

Per ogni OD:

    N_ij = Q * S_ij(beta)

    contribution_C_ij^a =
        p_ij^a * C_ij

    contribution_N_ij^a =
        p_ij^a * N_ij

    contribution_TOTAL_ij^a =
        contribution_C_ij^a
        +
        contribution_N_ij^a

Il test calcola inoltre:

- assigned commuting contribution;
- assigned non-pendular contribution;
- total modelled;
- residual;
- cumulative shares top 1/5/10/25/50 OD;
- HHI;
- effective number of contributing OD;
- numero OD necessario per raggiungere 50%, 80%, 90% del flow.

NO RETUNING.
NO LOSS CHANGE.
NO ANAS 2025.
NO frozen-artifact modification.

INPUTS
------
Temporary E3-A:
- E3A_final_primary_operator_candidate_v01.npz

Temporary E4:
- E4_primary_residuals_candidate_v01.csv
- E4_sensitivity_sections_candidate_v01.csv

Frozen:
- ANAS_5_8D_calibration_mapping_v01.csv
- OSM_OD_municipal_summary_v01.csv
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz

OUTPUTS
-------
Only under:

C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\E4B_residual_attribution

- E4B_section_summary_candidate_v01.csv
- E4B_section_OD_contributions_candidate_v01.csv
- E4B_residual_attribution_operator_candidate_v01.npz

ASSUMPTIONS
-----------
- beta and Q are candidate values only, not frozen parameters.
- PRODUCT-LAMBDA assignment remains frozen.
- Measurement operator remains BIDIRECTIONAL_SUM.
- A path counts once for a section even if it intersects more than one
  canonical directed edge belonging to that section.

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA
- ANAS 5.8D canonical mapping

FILES WRITTEN
-------------
Temporary outputs only under E4B_residual_attribution.

FILES NEVER MODIFIED
--------------------
Anything under:

C:\\Tesi\\Tesi_QGIS\\02_package
"""

from pathlib import Path
import csv
import math

import numpy as np
import pandas as pd
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

E4_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E4_diagnostics"
)

OUT_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E4B_residual_attribution"
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

E4_PRIMARY_RESIDUALS = (
    E4_ROOT
    / "E4_primary_residuals_candidate_v01.csv"
)

E4_SENSITIVITY = (
    E4_ROOT
    / "E4_sensitivity_sections_candidate_v01.csv"
)

ANAS_MAPPING = (
    ANAS_ROOT
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

MUNICIPAL_SUMMARY = (
    OD_ROOT
    / "OSM_OD_municipal_summary_v01.csv"
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


SUMMARY_OUT = (
    OUT_ROOT
    / "E4B_section_summary_candidate_v01.csv"
)

DETAIL_OUT = (
    OUT_ROOT
    / "E4B_section_OD_contributions_candidate_v01.csv"
)

OPERATOR_OUT = (
    OUT_ROOT
    / "E4B_residual_attribution_operator_candidate_v01.npz"
)


SECTIONS = [
    "920032",
    "920022",
    "920040",
]

SECTIONS_TO_SCAN = [
    "920022",
    "920040",
]


BASELINE_BETA = 0.045953794473
BASELINE_Q = 1552629.518131

PATH_SCAN_CHUNK = 10_000_000

TOP_N_PRINT = 10


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


def safe_share(
    numerator,
    denominator,
):
    if denominator <= 0:
        return math.nan

    return float(
        numerator
        / denominator
    )


def cumulative_count_for_share(
    contributions,
    target_share,
):
    contributions = np.asarray(
        contributions,
        dtype=np.float64,
    )

    total = float(
        np.sum(
            contributions
        )
    )

    if total <= 0:
        return 0

    cumulative = np.cumsum(
        contributions
    )

    target = (
        target_share
        * total
    )

    idx = int(
        np.searchsorted(
            cumulative,
            target,
            side="left",
        )
    )

    return idx + 1


# =============================================================================
# E3-A OPERATOR
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
        - set(
            z.files
        )
    )

    if missing:
        raise RuntimeError(
            "E3-A operator missing arrays: "
            f"{sorted(missing)}"
        )

    primary_ids = [
        str(x)
        for x in z[
            "primary_ids"
        ].tolist()
    ]

    if "920032" not in primary_ids:
        raise RuntimeError(
            "920032 missing from E3-A PRIMARY operator."
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

    if len(
        origin
    ) != 46010:
        raise RuntimeError(
            f"Expected 46010 OD, found {len(origin)}"
        )

    idx_920032 = primary_ids.index(
        "920032"
    )

    p_920032 = primary_p[
        idx_920032,
        :
    ].copy()

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

        "p_920032":
            p_920032,

        "primary_ids":
            primary_ids,
    }


# =============================================================================
# MUNICIPAL OD NAMES
# =============================================================================

def load_od_names(
    data,
):
    df = pd.read_csv(
        MUNICIPAL_SUMMARY,
        usecols=[
            "origin_PRO_COM",
            "origin_COMUNE",
            "destination_PRO_COM",
            "destination_COMUNE",
        ],
    )

    if len(
        df
    ) != 46010:
        raise RuntimeError(
            "Municipal summary must contain 46010 OD."
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

    if df[
        [
            "origin_PRO_COM",
            "destination_PRO_COM",
        ]
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate OD in municipal summary."
        )

    canonical = pd.DataFrame(
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

    merged = canonical.merge(
        df,
        on=[
            "origin_PRO_COM",
            "destination_PRO_COM",
        ],
        how="left",
        validate="one_to_one",
        sort=False,
    )

    if (
        merged[
            "origin_COMUNE"
        ].isna().any()
        or merged[
            "destination_COMUNE"
        ].isna().any()
    ):
        raise RuntimeError(
            "Municipal names join incomplete."
        )

    merged = merged.sort_values(
        "od_idx"
    ).reset_index(
        drop=True
    )

    return merged


# =============================================================================
# TARGET ANAS MAPPING
# =============================================================================

def load_target_mapping():
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

            if section_id not in SECTIONS:
                continue

            result[
                section_id
            ] = {
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

                "EDGE_IDS":
                    parse_pipe_ints(
                        row[
                            "RELEVANT_DIRECTED_EDGE_IDS"
                        ]
                    ),
            }

    missing = (
        set(
            SECTIONS
        )
        - set(
            result
        )
    )

    if missing:
        raise RuntimeError(
            "Missing target sections in canonical ANAS mapping: "
            f"{sorted(missing)}"
        )

    return result


# =============================================================================
# ACCESS PATH -> OD
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

    if len(
        df
    ) != 414090:
        raise RuntimeError(
            f"Expected 414090 paths, found {len(df)}"
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
            "Access path -> OD join incomplete."
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
            "path_idx ordering is not canonical."
        )

    path_to_od = df[
        "od_idx"
    ].to_numpy(
        dtype=np.int64
    )

    pair_weight = df[
        "pair_weight"
    ].to_numpy(
        dtype=np.float64
    )

    return (
        path_to_od,
        pair_weight,
    )


# =============================================================================
# SCAN ONLY 920022 + 920040
# =============================================================================

def scan_sensitivity_targets(
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
            "Unexpected transition-slot length."
        )

    bit_by_section = {
        "920022":
            np.uint8(
                1
            ),

        "920040":
            np.uint8(
                2
            ),
    }

    slot_mask = np.zeros(
        b5_edgeid.nnz,
        dtype=np.uint8,
    )

    print()
    print("F. TARGET EDGE QA")
    print("-" * 110)

    for section_id in SECTIONS_TO_SCAN:
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
        section_id:
            set()

        for section_id
        in SECTIONS_TO_SCAN
    }

    n_slots = len(
        transitions
    )

    print()
    print("G. FROZEN PATH SCAN")
    print("-" * 110)

    print(
        "TRANSITION_SLOTS =",
        f"{n_slots:,}",
    )

    print(
        "TARGET_SECTIONS =",
        "|".join(
            SECTIONS_TO_SCAN
        ),
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

            for section_id in SECTIONS_TO_SCAN:
                bit = bit_by_section[
                    section_id
                ]

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
            progress >= next_progress
            or hi == n_slots
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
# BUILD p_ij^a
# =============================================================================

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
        return (
            np.zeros(
                n_od,
                dtype=np.float64,
            ),
            0,
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

    p = np.minimum(
        p,
        1.0,
    )

    return (
        p,
        len(
            paths
        ),
    )


# =============================================================================
# E4 REGRESSION
# =============================================================================

def load_e4_expected():
    primary = pd.read_csv(
        E4_PRIMARY_RESIDUALS
    )

    sensitivity = pd.read_csv(
        E4_SENSITIVITY
    )

    primary[
        "SECTION_ID"
    ] = primary[
        "SECTION_ID"
    ].astype(
        str
    )

    sensitivity[
        "SECTION_ID"
    ] = sensitivity[
        "SECTION_ID"
    ].astype(
        str
    )

    result = {}

    row = primary[
        primary[
            "SECTION_ID"
        ]
        == "920032"
    ]

    if len(
        row
    ) != 1:
        raise RuntimeError(
            "920032 missing/duplicated in E4 primary residuals."
        )

    result[
        "920032"
    ] = {
        "MODELLED":
            float(
                row.iloc[
                    0
                ][
                    "MODELLED"
                ]
            ),

        "OBSERVED":
            float(
                row.iloc[
                    0
                ][
                    "OBSERVED"
                ]
            ),
    }

    for section_id in [
        "920022",
        "920040",
    ]:
        row = sensitivity[
            sensitivity[
                "SECTION_ID"
            ]
            == section_id
        ]

        if len(
            row
        ) != 1:
            raise RuntimeError(
                f"{section_id} missing/duplicated in E4 sensitivity."
            )

        result[
            section_id
        ] = {
            "MODELLED":
                float(
                    row.iloc[
                        0
                    ][
                        "MODELLED"
                    ]
                ),

            "OBSERVED":
                float(
                    row.iloc[
                        0
                    ][
                        "OBSERVED"
                    ]
                ),
        }

    return result


# =============================================================================
# SECTION ATTRIBUTION
# =============================================================================

def analyse_section(
    section_id,
    metadata,
    p,
    commuting,
    nonpendular,
    od_names,
):
    exposed = (
        p > 0
    )

    c_contribution = (
        p
        * commuting
    )

    n_contribution = (
        p
        * nonpendular
    )

    total_contribution = (
        c_contribution
        + n_contribution
    )

    c_assigned = float(
        np.sum(
            c_contribution
        )
    )

    n_assigned = float(
        np.sum(
            n_contribution
        )
    )

    modelled = (
        c_assigned
        + n_assigned
    )

    observed = float(
        metadata[
            "OBSERVED"
        ]
    )

    residual = (
        observed
        - modelled
    )

    relative_error = (
        residual
        / observed
    )

    rows = od_names.loc[
        exposed,
        [
            "od_idx",
            "origin_PRO_COM",
            "origin_COMUNE",
            "destination_PRO_COM",
            "destination_COMUNE",
        ],
    ].copy()

    rows[
        "SECTION_ID"
    ] = section_id

    rows[
        "ROAD"
    ] = metadata[
        "ROAD"
    ]

    rows[
        "p_ij_a"
    ] = p[
        exposed
    ]

    rows[
        "C_ij"
    ] = commuting[
        exposed
    ]

    rows[
        "N_ij"
    ] = nonpendular[
        exposed
    ]

    rows[
        "C_ij_contribution"
    ] = c_contribution[
        exposed
    ]

    rows[
        "N_ij_contribution"
    ] = n_contribution[
        exposed
    ]

    rows[
        "TOTAL_contribution"
    ] = total_contribution[
        exposed
    ]

    rows = rows.sort_values(
        "TOTAL_contribution",
        ascending=False,
    ).reset_index(
        drop=True
    )

    rows[
        "rank"
    ] = np.arange(
        1,
        len(
            rows
        )
        + 1,
        dtype=np.int64,
    )

    if modelled > 0:
        rows[
            "share_of_section_modelled"
        ] = (
            rows[
                "TOTAL_contribution"
            ]
            / modelled
        )
    else:
        rows[
            "share_of_section_modelled"
        ] = math.nan

    rows[
        "cumulative_share"
    ] = rows[
        "share_of_section_modelled"
    ].cumsum()

    contributions = rows[
        "TOTAL_contribution"
    ].to_numpy(
        dtype=np.float64
    )

    shares = rows[
        "share_of_section_modelled"
    ].to_numpy(
        dtype=np.float64
    )

    hhi = float(
        np.sum(
            shares
            * shares
        )
    )

    effective_n = (
        1.0
        / hhi
        if hhi > 0
        else math.nan
    )

    def top_share(n):
        n_eff = min(
            n,
            len(
                contributions
            ),
        )

        return safe_share(
            np.sum(
                contributions[
                    :n_eff
                ]
            ),
            modelled,
        )

    summary = {
        "SECTION_ID":
            section_id,

        "ROAD":
            metadata[
                "ROAD"
            ],

        "QUALITY_CLASS":
            metadata[
                "QUALITY_CLASS"
            ],

        "EXTERNAL_EXPOSURE":
            metadata[
                "EXTERNAL_EXPOSURE"
            ],

        "OBSERVED":
            observed,

        "ASSIGNED_COMMUTING":
            c_assigned,

        "ASSIGNED_NONPENDULAR":
            n_assigned,

        "MODELLED_TOTAL":
            modelled,

        "RESIDUAL_VEH_DAY":
            residual,

        "REL_ERROR":
            relative_error,

        "NONPENDULAR_SHARE_OF_MODELLED":
            safe_share(
                n_assigned,
                modelled,
            ),

        "EXPOSED_OD":
            int(
                np.count_nonzero(
                    exposed
                )
            ),

        "TOP1_SHARE":
            top_share(
                1
            ),

        "TOP5_SHARE":
            top_share(
                5
            ),

        "TOP10_SHARE":
            top_share(
                10
            ),

        "TOP25_SHARE":
            top_share(
                25
            ),

        "TOP50_SHARE":
            top_share(
                50
            ),

        "HHI_OD_CONTRIBUTION":
            hhi,

        "EFFECTIVE_OD_COUNT":
            effective_n,

        "OD_FOR_50PCT":
            cumulative_count_for_share(
                contributions,
                0.50,
            ),

        "OD_FOR_80PCT":
            cumulative_count_for_share(
                contributions,
                0.80,
            ),

        "OD_FOR_90PCT":
            cumulative_count_for_share(
                contributions,
                0.90,
            ),
    }

    return (
        summary,
        rows,
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 120)
    print(
        "E4-B — RESIDUAL ATTRIBUTION SMALL TEST"
    )
    print("=" * 120)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. CONTRACT")
    print("-" * 120)

    print(
        f"BETA_CANDIDATE = {BASELINE_BETA:.12f} 1/min"
    )

    print(
        f"Q_CANDIDATE = {BASELINE_Q:.6f} veh/day"
    )

    print(
        "TARGET_SECTIONS = "
        + "|".join(
            SECTIONS
        )
    )

    print(
        "RETUNING = NO"
    )

    print(
        "LOSS_CHANGE = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    # -------------------------------------------------------------------------
    # B. Preflight
    # -------------------------------------------------------------------------

    print()
    print("B. FILE PREFLIGHT")
    print("-" * 120)

    input_files = [
        E3A_OPERATOR,
        E4_PRIMARY_RESIDUALS,
        E4_SENSITIVITY,
        ANAS_MAPPING,
        MUNICIPAL_SUMMARY,
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

    for path in [
        SUMMARY_OUT,
        DETAIL_OUT,
        OPERATOR_OUT,
    ]:
        require_output_absent(
            path
        )

    # -------------------------------------------------------------------------
    # C. Load baseline operator
    # -------------------------------------------------------------------------

    data = load_e3a_operator()

    print()
    print("C. E3-A OPERATOR")
    print("-" * 120)

    print(
        f"OD_ROWS = {len(data['origin'])}"
    )

    print(
        "E3A_PRIMARY_IDS = "
        + "|".join(
            data[
                "primary_ids"
            ]
        )
    )

    print(
        "920032_OPERATOR_REUSED = YES"
    )

    # -------------------------------------------------------------------------
    # D. Gravity baseline
    # -------------------------------------------------------------------------

    weights = (
        data[
            "gravity_base"
        ]
        *
        np.exp(
            -BASELINE_BETA
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

    if denominator <= 0:
        raise RuntimeError(
            "Gravity denominator <= 0."
        )

    s_ij = (
        weights
        / denominator
    )

    if abs(
        float(
            np.sum(
                s_ij
            )
        )
        - 1.0
    ) > 1e-12:
        raise RuntimeError(
            "S_ij normalization failure."
        )

    n_ij = (
        BASELINE_Q
        * s_ij
    )

    print()
    print("D. BASELINE GRAVITY DEMAND")
    print("-" * 120)

    print(
        f"SUM_S_IJ = {float(np.sum(s_ij)):.15f}"
    )

    print(
        f"SUM_N_IJ = {float(np.sum(n_ij)):.6f}"
    )

    print(
        f"EXPECTED_Q = {BASELINE_Q:.6f}"
    )

    # -------------------------------------------------------------------------
    # E. Mapping and names
    # -------------------------------------------------------------------------

    mapping = load_target_mapping()

    od_names = load_od_names(
        data
    )

    path_to_od, pair_weight = (
        load_access_path_metadata(
            data
        )
    )

    print()
    print("E. TARGET SECTIONS")
    print("-" * 120)

    for section_id in SECTIONS:
        x = mapping[
            section_id
        ]

        print(
            f"{section_id} | "
            f"ROAD={x['ROAD']} | "
            f"OBSERVED={x['OBSERVED']:.3f} | "
            f"QUALITY={x['QUALITY_CLASS']} | "
            f"EXTERNAL={x['EXTERNAL_EXPOSURE']} | "
            f"EDGES={x['EDGE_IDS']}"
        )

    # -------------------------------------------------------------------------
    # F/G. Scan only sensitivity targets
    # -------------------------------------------------------------------------

    path_hits = scan_sensitivity_targets(
        mapping
    )

    p_920022, path_count_920022 = (
        build_p_from_paths(
            path_hits[
                "920022"
            ],
            path_to_od,
            pair_weight,
            len(
                data[
                    "origin"
                ]
            ),
        )
    )

    p_920040, path_count_920040 = (
        build_p_from_paths(
            path_hits[
                "920040"
            ],
            path_to_od,
            pair_weight,
            len(
                data[
                    "origin"
                ]
            ),
        )
    )

    p_by_section = {
        "920032":
            data[
                "p_920032"
            ],

        "920022":
            p_920022,

        "920040":
            p_920040,
    }

    print()
    print("H. EXPOSURE QA")
    print("=" * 120)

    print(
        "920032 | "
        f"OD_P_GT_0={np.count_nonzero(p_by_section['920032'] > 0)}"
    )

    print(
        "920022 | "
        f"PATH_HITS={path_count_920022} | "
        f"OD_P_GT_0={np.count_nonzero(p_920022 > 0)}"
    )

    print(
        "920040 | "
        f"PATH_HITS={path_count_920040} | "
        f"OD_P_GT_0={np.count_nonzero(p_920040 > 0)}"
    )

    # -------------------------------------------------------------------------
    # I. Analyse sections
    # -------------------------------------------------------------------------

    expected = load_e4_expected()

    summaries = []
    details = []

    for section_id in SECTIONS:
        summary, detail = analyse_section(
            section_id,
            mapping[
                section_id
            ],
            p_by_section[
                section_id
            ],
            data[
                "commuting"
            ],
            n_ij,
            od_names,
        )

        # Regression against the completed E4 result.
        expected_modelled = expected[
            section_id
        ][
            "MODELLED"
        ]

        delta = abs(
            summary[
                "MODELLED_TOTAL"
            ]
            - expected_modelled
        )

        if delta > 0.01:
            raise RuntimeError(
                f"{section_id}: E4 modelled-flow "
                f"regression mismatch: delta={delta:.6f}"
            )

        summaries.append(
            summary
        )

        details.append(
            detail
        )

    summary_df = pd.DataFrame(
        summaries
    )

    detail_df = pd.concat(
        details,
        ignore_index=True,
    )

    # -------------------------------------------------------------------------
    # J. Section-level summary
    # -------------------------------------------------------------------------

    print()
    print("I. SECTION ATTRIBUTION SUMMARY")
    print("=" * 170)

    for _, row in summary_df.iterrows():
        print(
            f"{row['SECTION_ID']} | "
            f"OBS={row['OBSERVED']:.3f} | "
            f"C={row['ASSIGNED_COMMUTING']:.3f} | "
            f"N={row['ASSIGNED_NONPENDULAR']:.3f} | "
            f"MODEL={row['MODELLED_TOTAL']:.3f} | "
            f"RES={row['RESIDUAL_VEH_DAY']:+.3f} | "
            f"REL={row['REL_ERROR']:+.6f} | "
            f"NP_SHARE={row['NONPENDULAR_SHARE_OF_MODELLED']:.6f}"
        )

    # -------------------------------------------------------------------------
    # K. Concentration
    # -------------------------------------------------------------------------

    print()
    print("J. OD CONCENTRATION")
    print("=" * 170)

    for _, row in summary_df.iterrows():
        print(
            f"{row['SECTION_ID']} | "
            f"EXPOSED_OD={int(row['EXPOSED_OD'])} | "
            f"TOP1={row['TOP1_SHARE']:.6f} | "
            f"TOP5={row['TOP5_SHARE']:.6f} | "
            f"TOP10={row['TOP10_SHARE']:.6f} | "
            f"TOP25={row['TOP25_SHARE']:.6f} | "
            f"TOP50={row['TOP50_SHARE']:.6f} | "
            f"HHI={row['HHI_OD_CONTRIBUTION']:.8f} | "
            f"EFFECTIVE_N={row['EFFECTIVE_OD_COUNT']:.2f}"
        )

        print(
            f"    OD_FOR_50PCT={int(row['OD_FOR_50PCT'])} | "
            f"OD_FOR_80PCT={int(row['OD_FOR_80PCT'])} | "
            f"OD_FOR_90PCT={int(row['OD_FOR_90PCT'])}"
        )

    # -------------------------------------------------------------------------
    # L. Top contributors
    # -------------------------------------------------------------------------

    print()
    print("K. TOP OD CONTRIBUTORS")
    print("=" * 180)

    for section_id in SECTIONS:
        print()
        print(
            "#" * 180
        )

        print(
            f"SECTION = {section_id}"
        )

        print(
            "#" * 180
        )

        section_detail = detail_df[
            detail_df[
                "SECTION_ID"
            ]
            == section_id
        ].head(
            TOP_N_PRINT
        )

        for _, row in section_detail.iterrows():
            print(
                f"RANK={int(row['rank']):>2} | "
                f"{row['origin_COMUNE']} "
                f"({int(row['origin_PRO_COM'])})"
                f" -> "
                f"{row['destination_COMUNE']} "
                f"({int(row['destination_PRO_COM'])}) | "
                f"p={row['p_ij_a']:.6f} | "
                f"C={row['C_ij_contribution']:.3f} | "
                f"N={row['N_ij_contribution']:.3f} | "
                f"TOTAL={row['TOTAL_contribution']:.3f} | "
                f"SHARE={row['share_of_section_modelled']:.6f} | "
                f"CUM={row['cumulative_share']:.6f}"
            )

    # -------------------------------------------------------------------------
    # M. Save
    # -------------------------------------------------------------------------

    summary_df.to_csv(
        SUMMARY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # Reorder detail columns for readability.
    detail_columns = [
        "SECTION_ID",
        "ROAD",
        "rank",
        "origin_PRO_COM",
        "origin_COMUNE",
        "destination_PRO_COM",
        "destination_COMUNE",
        "p_ij_a",
        "C_ij",
        "N_ij",
        "C_ij_contribution",
        "N_ij_contribution",
        "TOTAL_contribution",
        "share_of_section_modelled",
        "cumulative_share",
        "od_idx",
    ]

    detail_df[
        detail_columns
    ].to_csv(
        DETAIL_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    np.savez_compressed(
        OPERATOR_OUT,

        section_ids=np.array(
            SECTIONS
        ),

        origin_PRO_COM=data[
            "origin"
        ],

        destination_PRO_COM=data[
            "destination"
        ],

        C_ij=data[
            "commuting"
        ],

        N_ij=n_ij,

        p_920032=p_by_section[
            "920032"
        ],

        p_920022=p_by_section[
            "920022"
        ],

        p_920040=p_by_section[
            "920040"
        ],
    )

    # -------------------------------------------------------------------------
    # N. Output state
    # -------------------------------------------------------------------------

    print()
    print("L. OUTPUTS")
    print("-" * 120)

    print(
        "SUMMARY_FILE =",
        SUMMARY_OUT,
    )

    print(
        "OD_DETAIL_FILE =",
        DETAIL_OUT,
    )

    print(
        "OPERATOR_FILE =",
        OPERATOR_OUT,
    )

    print(
        f"OD_DETAIL_ROWS = {len(detail_df)}"
    )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / DIAGNOSTIC / NOT FROZEN"
    )

    # -------------------------------------------------------------------------
    # O. Gate
    # -------------------------------------------------------------------------

    print()
    print("M. E4-B GATE STATE")
    print("=" * 120)

    print(
        "RESIDUAL_ATTRIBUTION_COMPLETE = YES"
    )

    print(
        "ATTRIBUTION_CLASSIFICATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "E4B_FINAL_RECOMMENDATION = "
        "PENDING_CHAT_INTERPRETATION"
    )

    print(
        "Q_RETUNED = NO"
    )

    print(
        "BETA_RETUNED = NO"
    )

    print(
        "LOSS_CHANGED = NO"
    )

    print(
        "Q_FROZEN = NO"
    )

    print(
        "BETA_FROZEN = NO"
    )

    print(
        "E5_STARTED = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")


