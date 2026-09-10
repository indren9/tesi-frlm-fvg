"""
FINAL LIMITED ASSIGNMENT SANITY CHECK
Gravity LIGHT v0 — FVG-only

PURPOSE
-------
Eseguire l'ultimo controllo limitato sulla rappresentazione
dell'assegnazione per:

    920022 — RA13
    920040 — SS54

Si analizzano SOLO le top-5 OD contributrici di ciascuna sezione
già identificate da E4-B.

Per ogni OD vengono controllati i 9 frozen access-pair paths:

- path_idx;
- pair_weight;
- TIME_B5 path time;
- path distance;
- presenza della sezione ANAS;
- quota PRODUCT-LAMBDA assegnata alla sezione.

IMPORTANTE
----------
Questo script NON:

- ricalcola shortest paths;
- cerca percorsi alternativi;
- modifica il grafo;
- modifica il frozen OD path system;
- calibra Gravity;
- usa ANAS 2025.

Legge esclusivamente i frozen path già materializzati.

Il confronto con eventuali corridoi alternativi plausibili
sarà poi un controllo visuale/manuale limitato.

INPUTS
------
- E4B_section_OD_contributions_candidate_v01.csv
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz
- ANAS_5_8D_calibration_mapping_v01.csv

OUTPUTS
-------
C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\
final_assignment_sanity\\

- final_assignment_OD_summary_v01.csv
- final_assignment_path_detail_v01.csv

FROZEN ARTIFACTS USED
---------------------
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA

FILES WRITTEN
-------------
Temporary diagnostic CSV only.

FILES NEVER MODIFIED
--------------------
Anything under:
C:\\Tesi\\Tesi_QGIS\\02_package
"""

from pathlib import Path
import csv

import numpy as np
import pandas as pd
from scipy.sparse import load_npz


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
    / "final_assignment_sanity"
)

E4B_DETAIL = (
    TEMP
    / "E4B_residual_attribution"
    / "E4B_section_OD_contributions_candidate_v01.csv"
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

ACCESS_PATHS = (
    OD_ROOT
    / "OSM_OD_access_paths_v01.csv"
)

OFFSETS_FILE = (
    OD_ROOT
    / "OSM_OD_path_offsets_v01.npy"
)

TRANSITIONS_FILE = (
    OD_ROOT
    / "OSM_OD_transition_slots_v01.npy"
)

B5_EDGEID_FILE = (
    GRAPH_ROOT
    / "osm_turn_state_edgeid_v01.npz"
)

ANAS_MAPPING = (
    ANAS_ROOT
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

SUMMARY_OUT = (
    OUT_ROOT
    / "final_assignment_OD_summary_v01.csv"
)

DETAIL_OUT = (
    OUT_ROOT
    / "final_assignment_path_detail_v01.csv"
)

TARGET_SECTIONS = [
    "920022",
    "920040",
]

TOP_N = 5


# =============================================================================
# HELPERS
# =============================================================================

def require_file(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"FILE NOT FOUND: {path}"
        )


def require_absent(path):
    if path.exists():
        raise FileExistsError(
            f"OUTPUT ALREADY EXISTS — overwrite forbidden: {path}"
        )


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def parse_edges(value):
    return [
        int(x)
        for x in clean(value).split("|")
        if x.strip()
    ]


# =============================================================================
# MAIN
# =============================================================================

def main():

    print("=" * 130)
    print("FINAL LIMITED ASSIGNMENT SANITY CHECK")
    print("=" * 130)

    # -------------------------------------------------------------------------
    # A. Contract
    # -------------------------------------------------------------------------

    print()
    print("A. CONTRACT")
    print("-" * 130)

    print(
        "TARGET_SECTIONS = "
        + "|".join(TARGET_SECTIONS)
    )

    print(
        f"TOP_OD_PER_SECTION = {TOP_N}"
    )

    print(
        "SHORTEST_PATH_RECALCULATION = NO"
    )

    print(
        "GRAVITY_RECALIBRATION = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    # -------------------------------------------------------------------------
    # B. Preflight
    # -------------------------------------------------------------------------

    print()
    print("B. PREFLIGHT")
    print("-" * 130)

    inputs = [
        E4B_DETAIL,
        ACCESS_PATHS,
        OFFSETS_FILE,
        TRANSITIONS_FILE,
        B5_EDGEID_FILE,
        ANAS_MAPPING,
    ]

    for path in inputs:
        require_file(path)
        print(f"PASS = {path}")

    OUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    require_absent(SUMMARY_OUT)
    require_absent(DETAIL_OUT)

    # -------------------------------------------------------------------------
    # C. Section edge IDs
    # -------------------------------------------------------------------------

    mapping = {}

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

            if section_id not in TARGET_SECTIONS:
                continue

            mapping[section_id] = {
                "ROAD":
                    clean(row["ROAD"]),

                "EDGE_IDS":
                    parse_edges(
                        row[
                            "RELEVANT_DIRECTED_EDGE_IDS"
                        ]
                    ),
            }

    if set(mapping) != set(TARGET_SECTIONS):
        raise RuntimeError(
            "Target section mapping incomplete."
        )

    print()
    print("C. TARGET SECTIONS")
    print("-" * 130)

    for section_id in TARGET_SECTIONS:

        print(
            f"{section_id} | "
            f"ROAD={mapping[section_id]['ROAD']} | "
            f"EDGE_IDS={mapping[section_id]['EDGE_IDS']}"
        )

    # -------------------------------------------------------------------------
    # D. Top OD from E4-B
    # -------------------------------------------------------------------------

    detail = pd.read_csv(
        E4B_DETAIL
    )

    detail[
        "SECTION_ID"
    ] = detail[
        "SECTION_ID"
    ].astype(str)

    selected_rows = []

    print()
    print("D. SELECTED TOP OD")
    print("=" * 150)

    for section_id in TARGET_SECTIONS:

        sub = (
            detail[
                detail["SECTION_ID"]
                == section_id
            ]
            .sort_values("rank")
            .head(TOP_N)
            .copy()
        )

        if len(sub) != TOP_N:
            raise RuntimeError(
                f"{section_id}: expected {TOP_N} top OD."
            )

        for _, row in sub.iterrows():

            selected_rows.append(
                {
                    "SECTION_ID":
                        section_id,

                    "rank":
                        int(row["rank"]),

                    "origin_PRO_COM":
                        int(row["origin_PRO_COM"]),

                    "origin_COMUNE":
                        row["origin_COMUNE"],

                    "destination_PRO_COM":
                        int(row["destination_PRO_COM"]),

                    "destination_COMUNE":
                        row["destination_COMUNE"],

                    "p_ij_a_E4B":
                        float(row["p_ij_a"]),

                    "TOTAL_contribution":
                        float(
                            row[
                                "TOTAL_contribution"
                            ]
                        ),

                    "share_of_section_modelled":
                        float(
                            row[
                                "share_of_section_modelled"
                            ]
                        ),
                }
            )

            print(
                f"{section_id} | "
                f"RANK={int(row['rank'])} | "
                f"{row['origin_COMUNE']} -> "
                f"{row['destination_COMUNE']} | "
                f"p={float(row['p_ij_a']):.6f} | "
                f"CONTRIBUTION="
                f"{float(row['TOTAL_contribution']):.3f}"
            )

    selected = pd.DataFrame(
        selected_rows
    )

    # -------------------------------------------------------------------------
    # E. Access paths
    # -------------------------------------------------------------------------

    paths = pd.read_csv(
        ACCESS_PATHS
    )

    required = {
        "path_idx",
        "origin_PRO_COM",
        "destination_PRO_COM",
        "origin_access_order",
        "destination_access_order",
        "pair_weight",
        "time_s",
        "distance_m",
    }

    missing = (
        required
        - set(paths.columns)
    )

    if missing:
        raise RuntimeError(
            f"ACCESS_PATHS missing columns: {sorted(missing)}"
        )

    for col in [
        "path_idx",
        "origin_PRO_COM",
        "destination_PRO_COM",
        "origin_access_order",
        "destination_access_order",
    ]:
        paths[col] = pd.to_numeric(
            paths[col],
            errors="raise",
        ).astype(np.int64)

    for col in [
        "pair_weight",
        "time_s",
        "distance_m",
    ]:
        paths[col] = pd.to_numeric(
            paths[col],
            errors="raise",
        ).astype(np.float64)

    # -------------------------------------------------------------------------
    # F. Frozen sequence arrays
    # -------------------------------------------------------------------------

    offsets = np.load(
        OFFSETS_FILE,
        mmap_mode="r",
    )

    transitions = np.load(
        TRANSITIONS_FILE,
        mmap_mode="r",
    )

    edgeid = load_npz(
        B5_EDGEID_FILE
    ).tocsr()

    if len(offsets) != 414091:
        raise RuntimeError(
            "Unexpected path offsets length."
        )

    # -------------------------------------------------------------------------
    # G. Inspect ONLY selected 90 paths
    # -------------------------------------------------------------------------

    summary_rows = []
    path_rows = []

    print()
    print("E. FROZEN PATH CHECK")
    print("=" * 170)

    for _, od in selected.iterrows():

        section_id = od[
            "SECTION_ID"
        ]

        target_edges = set(
            mapping[
                section_id
            ]["EDGE_IDS"]
        )

        od_paths = paths[
            (
                paths["origin_PRO_COM"]
                == od["origin_PRO_COM"]
            )
            &
            (
                paths["destination_PRO_COM"]
                == od["destination_PRO_COM"]
            )
        ].copy()

        if len(od_paths) != 9:
            raise RuntimeError(
                f"{section_id} | "
                f"{od['origin_COMUNE']} -> "
                f"{od['destination_COMUNE']}: "
                f"expected 9 paths, found {len(od_paths)}"
            )

        od_paths = od_paths.sort_values(
            [
                "origin_access_order",
                "destination_access_order",
            ]
        )

        n_hit = 0
        hit_weight = 0.0

        weighted_time = 0.0
        weighted_distance = 0.0

        hit_times = []
        nonhit_times = []

        for _, path in od_paths.iterrows():

            path_idx = int(
                path[
                    "path_idx"
                ]
            )

            lo = int(
                offsets[
                    path_idx
                ]
            )

            hi = int(
                offsets[
                    path_idx + 1
                ]
            )

            transition_slot_ids = transitions[
                lo:hi
            ]

            path_edge_ids = edgeid.data[
                transition_slot_ids
            ]

            hit_edge_ids = sorted(
                target_edges
                &
                set(
                    map(
                        int,
                        path_edge_ids,
                    )
                )
            )

            hits_section = (
                len(hit_edge_ids) > 0
            )

            pair_weight = float(
                path[
                    "pair_weight"
                ]
            )

            time_s = float(
                path[
                    "time_s"
                ]
            )

            distance_m = float(
                path[
                    "distance_m"
                ]
            )

            weighted_time += (
                pair_weight
                * time_s
            )

            weighted_distance += (
                pair_weight
                * distance_m
            )

            if hits_section:

                n_hit += 1

                hit_weight += (
                    pair_weight
                )

                hit_times.append(
                    time_s
                )

            else:

                nonhit_times.append(
                    time_s
                )

            path_rows.append(
                {
                    "SECTION_ID":
                        section_id,

                    "rank":
                        int(
                            od[
                                "rank"
                            ]
                        ),

                    "origin_PRO_COM":
                        int(
                            od[
                                "origin_PRO_COM"
                            ]
                        ),

                    "origin_COMUNE":
                        od[
                            "origin_COMUNE"
                        ],

                    "destination_PRO_COM":
                        int(
                            od[
                                "destination_PRO_COM"
                            ]
                        ),

                    "destination_COMUNE":
                        od[
                            "destination_COMUNE"
                        ],

                    "path_idx":
                        path_idx,

                    "origin_access_order":
                        int(
                            path[
                                "origin_access_order"
                            ]
                        ),

                    "destination_access_order":
                        int(
                            path[
                                "destination_access_order"
                            ]
                        ),

                    "pair_weight":
                        pair_weight,

                    "time_min":
                        time_s
                        / 60.0,

                    "distance_km":
                        distance_m
                        / 1000.0,

                    "hits_section":
                        "YES"
                        if hits_section
                        else "NO",

                    "hit_edge_ids":
                        "|".join(
                            map(
                                str,
                                hit_edge_ids,
                            )
                        ),
                }
            )

        pair_weight_sum = float(
            od_paths[
                "pair_weight"
            ].sum()
        )

        if abs(
            pair_weight_sum
            - 1.0
        ) > 1e-10:
            raise RuntimeError(
                "PRODUCT-LAMBDA weight sum != 1."
            )

        # Regression against E4-B aggregate p_ij^a.
        p_expected = float(
            od[
                "p_ij_a_E4B"
            ]
        )

        p_delta = abs(
            hit_weight
            - p_expected
        )

        if p_delta > 1e-10:
            raise RuntimeError(
                f"E4-B p regression failed: "
                f"{section_id}, "
                f"{od['origin_COMUNE']} -> "
                f"{od['destination_COMUNE']}, "
                f"delta={p_delta}"
            )

        min_time = float(
            od_paths[
                "time_s"
            ].min()
        )

        max_time = float(
            od_paths[
                "time_s"
            ].max()
        )

        min_distance = float(
            od_paths[
                "distance_m"
            ].min()
        )

        max_distance = float(
            od_paths[
                "distance_m"
            ].max()
        )

        summary_rows.append(
            {
                "SECTION_ID":
                    section_id,

                "ROAD":
                    mapping[
                        section_id
                    ]["ROAD"],

                "rank":
                    int(
                        od[
                            "rank"
                        ]
                    ),

                "origin_PRO_COM":
                    int(
                        od[
                            "origin_PRO_COM"
                        ]
                    ),

                "origin_COMUNE":
                    od[
                        "origin_COMUNE"
                    ],

                "destination_PRO_COM":
                    int(
                        od[
                            "destination_PRO_COM"
                        ]
                    ),

                "destination_COMUNE":
                    od[
                        "destination_COMUNE"
                    ],

                "section_model_contribution":
                    float(
                        od[
                            "TOTAL_contribution"
                        ]
                    ),

                "section_contribution_share":
                    float(
                        od[
                            "share_of_section_modelled"
                        ]
                    ),

                "path_count":
                    9,

                "paths_hitting_section":
                    n_hit,

                "PRODUCT_LAMBDA_hit_weight":
                    hit_weight,

                "all_9_paths_hit":
                    "YES"
                    if n_hit == 9
                    else "NO",

                "min_time_min":
                    min_time
                    / 60.0,

                "max_time_min":
                    max_time
                    / 60.0,

                "time_spread_min":
                    (
                        max_time
                        - min_time
                    )
                    / 60.0,

                "PRODUCT_LAMBDA_time_min":
                    weighted_time
                    / 60.0,

                "min_distance_km":
                    min_distance
                    / 1000.0,

                "max_distance_km":
                    max_distance
                    / 1000.0,

                "PRODUCT_LAMBDA_distance_km":
                    weighted_distance
                    / 1000.0,
            }
        )

        print(
            f"{section_id} | "
            f"RANK={int(od['rank'])} | "
            f"{od['origin_COMUNE']} -> "
            f"{od['destination_COMUNE']} | "
            f"HIT_PATHS={n_hit}/9 | "
            f"HIT_WEIGHT={hit_weight:.12f} | "
            f"TIME="
            f"{min_time/60:.2f}-"
            f"{max_time/60:.2f} min | "
            f"WEIGHTED_TIME="
            f"{weighted_time/60:.2f} min"
        )

    # -------------------------------------------------------------------------
    # H. Save
    # -------------------------------------------------------------------------

    summary = pd.DataFrame(
        summary_rows
    )

    path_detail = pd.DataFrame(
        path_rows
    )

    summary.to_csv(
        SUMMARY_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    path_detail.to_csv(
        DETAIL_OUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # I. Compact manual-review shortlist
    # -------------------------------------------------------------------------

    print()
    print("F. MANUAL ROUTE REVIEW SHORTLIST")
    print("=" * 150)

    for section_id in TARGET_SECTIONS:

        print()
        print(
            f"SECTION {section_id} — "
            f"{mapping[section_id]['ROAD']}"
        )

        sub = summary[
            summary[
                "SECTION_ID"
            ]
            == section_id
        ].sort_values(
            "rank"
        )

        for _, row in sub.iterrows():

            print(
                f"RANK {int(row['rank'])}: "
                f"{row['origin_COMUNE']} -> "
                f"{row['destination_COMUNE']} | "
                f"FROZEN_HIT_WEIGHT="
                f"{row['PRODUCT_LAMBDA_hit_weight']:.6f} | "
                f"{int(row['paths_hitting_section'])}/9 paths"
            )

    # -------------------------------------------------------------------------
    # J. State
    # -------------------------------------------------------------------------

    print()
    print("G. OUTPUTS")
    print("-" * 130)

    print(
        f"SUMMARY = {SUMMARY_OUT}"
    )

    print(
        f"DETAIL = {DETAIL_OUT}"
    )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / LIMITED SANITY CHECK"
    )

    print()
    print("H. GATE STATE")
    print("=" * 130)

    print(
        "FROZEN_PATH_INSPECTION = COMPLETE"
    )

    print(
        "ROUTE_ALTERNATIVE_VISUAL_CHECK = "
        "PENDING_ANDREA"
    )

    print(
        "ASSIGNMENT_SANITY = "
        "PENDING_FINAL_VISUAL_REVIEW"
    )

    print(
        "NO_MODEL_RECALIBRATION = CONFIRMED"
    )

    print(
        "NO_FROZEN_ARTIFACT_MODIFICATION = CONFIRMED"
    )

    print(
        "ANAS_2025_USED = NO"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

