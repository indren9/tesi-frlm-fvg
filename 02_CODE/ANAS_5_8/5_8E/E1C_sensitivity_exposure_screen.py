"""
E1-C — ANAS SENSITIVITY MODEL-EXPOSURE SCREEN

PURPOSE
-------
Valutare la model exposure delle 13 sezioni ANAS già classificate
SENSITIVITY nella Fase 5.8D, rispetto al frozen municipal OD path system
della Gravity LIGHT v0.

Per ogni sezione a vengono calcolati:

    PATH_HITS
    OD_P_GT_0
    P_MAX
    assigned C_a^ISTAT

dove:

    p_ij^a =
    somma dei frozen PRODUCT-LAMBDA pair_weight dei 9 access paths
    della OD i->j che attraversano almeno uno dei directed edge canonici
    associati alla sezione ANAS a.

e:

    C_a^ISTAT =
    sum_ij p_ij^a * C_ij^ISTAT

MODEL_EXPOSURE = YES se OD_P_GT_0 > 0, altrimenti NO.

Questo è esclusivamente uno screening strutturale.

NON vengono:
- calibrati Q o beta;
- selezionate loss;
- calcolati residui di fit;
- usati dati ANAS 2025;
- modificati mapping ANAS;
- ricostruiti shortest paths;
- eseguiti nuovi matching GIS;
- selezionate automaticamente nuove PRIMARY.

INPUTS
------
- ANAS_5_8D_calibration_mapping_v01.csv
- OSM_OD_access_paths_v01.csv
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- osm_turn_state_edgeid_v01.npz
- ISTAT_commuting_LIGHT_v0.xlsx

OUTPUTS
-------
- E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv

ASSUMPTIONS
-----------
- Il canonical ANAS mapping 5.8D è frozen.
- ROLE=SENSITIVITY identifica esattamente 13 sezioni.
- Le sequenze path della Fase 5.7 sono frozen.
- pair_weight implementa PRODUCT-LAMBDA.
- Una path viene conteggiata una sola volta per una sezione anche se
  intercetta più edge canonici appartenenti alla stessa sezione.
- Il commuting input contiene esattamente il dominio delle 46,010
  ordered intermunicipal OD della Gravity v0.

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- OD_PATH_SYSTEM_OSM
- TIME_B5
- PRODUCT-LAMBDA
- ANAS 5.8D canonical mapping
- ISTAT commuting LIGHT v0

FILES WRITTEN
-------------
Solo:
C:\\Tesi\\Tesi_QGIS\\03_output_temporanei\\fase_5_8E\\E1C_sensitivity_screen\\

FILES NEVER MODIFIED
--------------------
Qualsiasi artefatto sotto:
C:\\Tesi\\Tesi_QGIS\\02_package\\

E1 ed E1-B outputs esistenti non vengono modificati.
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

GRAVITY_ROOT = (
    ROOT
    / "02_package"
    / "gravity_v0_inputs"
)

ANAS_ROOT = (
    ROOT
    / "02_package"
    / "anas_calibration_v0"
)

OUT_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_8E"
    / "E1C_sensitivity_screen"
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

COMMUTING_XLSX = (
    GRAVITY_ROOT
    / "ISTAT_commuting_LIGHT_v0.xlsx"
)

OUTPUT_CSV = (
    OUT_ROOT
    / "E1C_ANAS_sensitivity_exposure_screen_candidate_v01.csv"
)

SCAN_CHUNK_SIZE = 10_000_000

EXPECTED_SENSITIVITY_COUNT = 13

PRIMARY_CORRIDOR_GROUPS = {
    "SS54_CIVIDALE_INTERNAL",
    "SS52BIS_CARNIA_INTERNAL",
}


# =============================================================================
# HELPERS
# =============================================================================

def clean(value):
    if value is None:
        return ""
    return str(value).strip()


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


def parse_pipe_ints(value):
    text = clean(value)

    if not text:
        return []

    return [
        int(x.strip())
        for x in text.split("|")
        if x.strip()
    ]


def normalize_pro_com(value):
    if pd.isna(value):
        raise ValueError("PRO_COM missing")

    text = str(value).strip()

    try:
        return int(float(text))
    except Exception as exc:
        raise ValueError(
            f"Invalid PRO_COM value: {value!r}"
        ) from exc


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

        required = {
            "SECTION_ID",
            "ROAD",
            "TGMA_LIGHT_2024",
            "QUALITY_CLASS",
            "ROLE",
            "MEASUREMENT_OPERATOR",
            "RELEVANT_DIRECTED_EDGE_IDS",
            "EXTERNAL_EXPOSURE",
            "CORRIDOR_GROUP",
            "INFORMATION_ROLE",
            "QGIS_REVIEW_STATUS",
        }

        missing = (
            required
            - set(reader.fieldnames or [])
        )

        if missing:
            raise RuntimeError(
                "ANAS mapping missing columns: "
                f"{sorted(missing)}"
            )

        for row in reader:
            if clean(row["ROLE"]).upper() != "SENSITIVITY":
                continue

            section_id = clean(
                row["SECTION_ID"]
            )

            edges = parse_pipe_ints(
                row["RELEVANT_DIRECTED_EDGE_IDS"]
            )

            if not edges:
                raise RuntimeError(
                    f"{section_id}: no relevant directed edges"
                )

            rows.append(
                {
                    "SECTION_ID": section_id,
                    "ROAD": clean(
                        row["ROAD"]
                    ),
                    "TGMA_LIGHT_2024": float(
                        row["TGMA_LIGHT_2024"]
                    ),
                    "QUALITY_CLASS": clean(
                        row["QUALITY_CLASS"]
                    ),
                    "MEASUREMENT_OPERATOR": clean(
                        row["MEASUREMENT_OPERATOR"]
                    ),
                    "EDGE_IDS": edges,
                    "EXTERNAL_EXPOSURE": clean(
                        row["EXTERNAL_EXPOSURE"]
                    ),
                    "CORRIDOR_GROUP": clean(
                        row["CORRIDOR_GROUP"]
                    ),
                    "INFORMATION_ROLE": clean(
                        row["INFORMATION_ROLE"]
                    ),
                    "QGIS_REVIEW_STATUS": clean(
                        row["QGIS_REVIEW_STATUS"]
                    ),
                }
            )

    if len(rows) != EXPECTED_SENSITIVITY_COUNT:
        raise RuntimeError(
            "Expected exactly "
            f"{EXPECTED_SENSITIVITY_COUNT} SENSITIVITY rows, "
            f"found {len(rows)}"
        )

    section_ids = [
        row["SECTION_ID"]
        for row in rows
    ]

    if len(set(section_ids)) != len(section_ids):
        raise RuntimeError(
            "Duplicate SECTION_ID among sensitivities."
        )

    return rows


# =============================================================================
# ACCESS PATH METADATA
# =============================================================================

def load_access_paths():
    df = pd.read_csv(
        ACCESS_PATHS,
        dtype={
            "path_idx": np.int64,
            "origin_PRO_COM": np.int64,
            "destination_PRO_COM": np.int64,
        },
    )

    required = {
        "path_idx",
        "origin_PRO_COM",
        "destination_PRO_COM",
        "pair_weight",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise RuntimeError(
            "ACCESS_PATHS missing columns: "
            f"{sorted(missing)}"
        )

    if len(df) != 414090:
        raise RuntimeError(
            "Expected 414090 access paths, "
            f"found {len(df)}"
        )

    expected_idx = np.arange(
        len(df),
        dtype=np.int64,
    )

    if not np.array_equal(
        df["path_idx"].to_numpy(
            dtype=np.int64
        ),
        expected_idx,
    ):
        raise RuntimeError(
            "path_idx is not canonical 0..414089."
        )

    if not np.isfinite(
        df["pair_weight"].to_numpy(
            dtype=np.float64
        )
    ).all():
        raise RuntimeError(
            "Non-finite pair_weight found."
        )

    od_counts = (
        df.groupby(
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ],
            sort=False,
        )
        .size()
    )

    if (
        int(od_counts.min()) != 9
        or int(od_counts.max()) != 9
    ):
        raise RuntimeError(
            "Expected exactly 9 access paths per OD."
        )

    pair_sums = (
        df.groupby(
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ],
            sort=False,
        )["pair_weight"]
        .sum()
    )

    max_error = float(
        np.max(
            np.abs(
                pair_sums.to_numpy()
                - 1.0
            )
        )
    )

    if max_error > 1e-10:
        raise RuntimeError(
            "PRODUCT-LAMBDA OD weight sums invalid. "
            f"max error={max_error:.3e}"
        )

    return df, max_error


# =============================================================================
# COMMUTING INPUT
# =============================================================================

def resolve_column(
    columns,
    accepted_names,
    semantic_name,
):
    exact = {
        str(c).strip(): c
        for c in columns
    }

    casefold = {
        str(c).strip().casefold(): c
        for c in columns
    }

    matches = []

    for name in accepted_names:
        if name in exact:
            matches.append(
                exact[name]
            )
        elif name.casefold() in casefold:
            matches.append(
                casefold[
                    name.casefold()
                ]
            )

    matches = list(
        dict.fromkeys(matches)
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"Could not uniquely resolve {semantic_name}. "
            f"Accepted={accepted_names}; "
            f"available={list(columns)}"
        )

    return matches[0]


def load_commuting():
    workbook = pd.ExcelFile(
        COMMUTING_XLSX
    )

    candidates = []

    origin_aliases = [
        "ORIGIN_PRO_COM",
        "origin_PRO_COM",
        "origin_pro_com",
    ]

    destination_aliases = [
        "DESTINATION_PRO_COM",
        "destination_PRO_COM",
        "destination_pro_com",
    ]

    value_aliases = [
        "C_ij_ISTAT_VEH_DAY",
        "C_ij_ISTAT",
        "C_ij_ISTAT_LIGHT",
        "C_ij_LIGHT_VEH_DAY",
    ]

    for sheet in workbook.sheet_names:
        probe = pd.read_excel(
            COMMUTING_XLSX,
            sheet_name=sheet,
            nrows=5,
        )

        try:
            origin_col = resolve_column(
                probe.columns,
                origin_aliases,
                "commuting origin PRO_COM",
            )

            destination_col = resolve_column(
                probe.columns,
                destination_aliases,
                "commuting destination PRO_COM",
            )

            value_col = resolve_column(
                probe.columns,
                value_aliases,
                "C_ij^ISTAT",
            )

        except RuntimeError:
            continue

        candidates.append(
            (
                sheet,
                origin_col,
                destination_col,
                value_col,
            )
        )

    if len(candidates) != 1:
        raise RuntimeError(
            "Could not uniquely identify commuting sheet/schema. "
            f"Candidates={candidates}; "
            f"sheets={workbook.sheet_names}"
        )

    (
        sheet,
        origin_col,
        destination_col,
        value_col,
    ) = candidates[0]

    df = pd.read_excel(
        COMMUTING_XLSX,
        sheet_name=sheet,
    )

    out = pd.DataFrame(
        {
            "origin_PRO_COM":
                df[origin_col].map(
                    normalize_pro_com
                ),
            "destination_PRO_COM":
                df[destination_col].map(
                    normalize_pro_com
                ),
            "C_ij_ISTAT":
                pd.to_numeric(
                    df[value_col],
                    errors="raise",
                ).astype(
                    np.float64
                ),
        }
    )

    if len(out) != 46010:
        raise RuntimeError(
            "Expected 46010 commuting OD rows, "
            f"found {len(out)}"
        )

    if out[
        [
            "origin_PRO_COM",
            "destination_PRO_COM",
        ]
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate commuting OD keys."
        )

    c_values = out[
        "C_ij_ISTAT"
    ].to_numpy(
        dtype=np.float64
    )

    if not np.isfinite(
        c_values
    ).all():
        raise RuntimeError(
            "Non-finite C_ij_ISTAT values."
        )

    if np.any(
        c_values < 0
    ):
        raise RuntimeError(
            "Negative C_ij_ISTAT values."
        )

    schema = {
        "sheet": sheet,
        "origin_col": str(
            origin_col
        ),
        "destination_col": str(
            destination_col
        ),
        "value_col": str(
            value_col
        ),
    }

    return out, schema


# =============================================================================
# TARGET B5 SLOT MASK
# =============================================================================

def build_slot_mask(
    b5_edgeid,
    sensitivity_rows,
):
    # 13 sensitivities -> 13 bits, therefore uint16 is sufficient.
    section_bit = {
        row["SECTION_ID"]: (
            np.uint16(1 << idx)
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

    edge_qa = []

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

            count = int(
                len(matches)
            )

            edge_qa.append(
                (
                    section_id,
                    edge_id,
                    count,
                )
            )

            if count == 0:
                raise RuntimeError(
                    f"{section_id}: canonical EDGE_ID "
                    f"{edge_id} not present in B5 edge-id data."
                )

            slot_mask[
                matches
            ] |= bit

    return (
        section_bit,
        slot_mask,
        edge_qa,
    )


# =============================================================================
# SCAN FROZEN PATHS
# =============================================================================

def scan_paths(
    offsets,
    transition_slots,
    slot_mask,
    section_bit,
):
    section_path_hits = {
        section_id: set()
        for section_id
        in section_bit
    }

    n_slots = len(
        transition_slots
    )

    print()
    print("G. FROZEN TRANSITION SLOT SCAN")
    print("-" * 100)

    print(
        "TRANSITION_SLOTS =",
        f"{n_slots:,}",
    )

    print(
        "SCAN_CHUNK_SIZE  =",
        f"{SCAN_CHUNK_SIZE:,}",
    )

    next_progress = 10

    for lo in range(
        0,
        n_slots,
        SCAN_CHUNK_SIZE,
    ):
        hi = min(
            lo + SCAN_CHUNK_SIZE,
            n_slots,
        )

        slots = transition_slots[
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
                    matched_masks & bit
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

                section_path_hits[
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

            while (
                next_progress
                <= progress
            ):
                next_progress += 10

    return section_path_hits


# =============================================================================
# PATH HITS -> p_ij^a
# =============================================================================

def aggregate_exposure(
    access_paths,
    sensitivity_rows,
    section_path_hits,
):
    results = []

    for meta in sensitivity_rows:
        section_id = meta[
            "SECTION_ID"
        ]

        path_indices = np.asarray(
            sorted(
                section_path_hits[
                    section_id
                ]
            ),
            dtype=np.int64,
        )

        if len(path_indices) == 0:
            path_hits = 0
            od_p_gt_0 = 0
            p_max = 0.0
            exposure = pd.DataFrame(
                columns=[
                    "origin_PRO_COM",
                    "destination_PRO_COM",
                    "p_ij_a",
                ]
            )

        else:
            hit_rows = access_paths.iloc[
                path_indices
            ][
                [
                    "origin_PRO_COM",
                    "destination_PRO_COM",
                    "pair_weight",
                ]
            ].copy()

            exposure = (
                hit_rows.groupby(
                    [
                        "origin_PRO_COM",
                        "destination_PRO_COM",
                    ],
                    as_index=False,
                    sort=True,
                )["pair_weight"]
                .sum()
                .rename(
                    columns={
                        "pair_weight":
                            "p_ij_a"
                    }
                )
            )

            p_values = exposure[
                "p_ij_a"
            ].to_numpy(
                dtype=np.float64
            )

            if np.any(
                p_values <= 0
            ):
                raise RuntimeError(
                    f"{section_id}: non-positive "
                    f"p_ij_a after aggregation."
                )

            if np.any(
                p_values > 1.0 + 1e-10
            ):
                raise RuntimeError(
                    f"{section_id}: p_ij_a > 1."
                )

            exposure[
                "p_ij_a"
            ] = np.minimum(
                exposure["p_ij_a"],
                1.0,
            )

            path_hits = int(
                len(path_indices)
            )

            od_p_gt_0 = int(
                len(exposure)
            )

            p_max = float(
                exposure[
                    "p_ij_a"
                ].max()
            )

        results.append(
            {
                **meta,
                "PATH_HITS":
                    path_hits,
                "OD_P_GT_0":
                    od_p_gt_0,
                "P_MAX":
                    p_max,
                "_EXPOSURE_DF":
                    exposure,
            }
        )

    return results


# =============================================================================
# COMMUTING ASSIGNMENT
# =============================================================================

def assign_commuting(
    results,
    commuting,
):
    commuting_keys = set(
        zip(
            commuting[
                "origin_PRO_COM"
            ],
            commuting[
                "destination_PRO_COM"
            ],
        )
    )

    for result in results:
        exposure = result[
            "_EXPOSURE_DF"
        ]

        if exposure.empty:
            result[
                "C_a_ISTAT"
            ] = 0.0

            result[
                "MODEL_EXPOSURE"
            ] = "NO"

            continue

        joined = exposure.merge(
            commuting,
            on=[
                "origin_PRO_COM",
                "destination_PRO_COM",
            ],
            how="left",
            validate="one_to_one",
        )

        missing = int(
            joined[
                "C_ij_ISTAT"
            ].isna().sum()
        )

        if missing != 0:
            raise RuntimeError(
                f"{result['SECTION_ID']}: "
                f"{missing} exposed OD missing "
                f"from commuting input."
            )

        c_a = float(
            np.sum(
                joined[
                    "p_ij_a"
                ].to_numpy(
                    dtype=np.float64
                )
                *
                joined[
                    "C_ij_ISTAT"
                ].to_numpy(
                    dtype=np.float64
                )
            )
        )

        if not np.isfinite(
            c_a
        ):
            raise RuntimeError(
                f"{result['SECTION_ID']}: "
                f"non-finite C_a_ISTAT."
            )

        result[
            "C_a_ISTAT"
        ] = c_a

        result[
            "MODEL_EXPOSURE"
        ] = (
            "YES"
            if result[
                "OD_P_GT_0"
            ] > 0
            else "NO"
        )


# =============================================================================
# OUTPUT
# =============================================================================

def write_output(
    results,
):
    fieldnames = [
        "SECTION_ID",
        "ROAD",
        "TGMA_LIGHT_2024",
        "QUALITY_CLASS",
        "CORRIDOR_GROUP",
        "EXTERNAL_EXPOSURE",
        "INFORMATION_ROLE",
        "QGIS_REVIEW_STATUS",
        "MEASUREMENT_OPERATOR",
        "RELEVANT_DIRECTED_EDGE_IDS",
        "PATH_HITS",
        "OD_P_GT_0",
        "P_MAX",
        "C_a_ISTAT",
        "MODEL_EXPOSURE",
        "SAME_CORRIDOR_AS_EXISTING_PRIMARY",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    "SECTION_ID":
                        result[
                            "SECTION_ID"
                        ],
                    "ROAD":
                        result[
                            "ROAD"
                        ],
                    "TGMA_LIGHT_2024":
                        f"{result['TGMA_LIGHT_2024']:.6f}",
                    "QUALITY_CLASS":
                        result[
                            "QUALITY_CLASS"
                        ],
                    "CORRIDOR_GROUP":
                        result[
                            "CORRIDOR_GROUP"
                        ],
                    "EXTERNAL_EXPOSURE":
                        result[
                            "EXTERNAL_EXPOSURE"
                        ],
                    "INFORMATION_ROLE":
                        result[
                            "INFORMATION_ROLE"
                        ],
                    "QGIS_REVIEW_STATUS":
                        result[
                            "QGIS_REVIEW_STATUS"
                        ],
                    "MEASUREMENT_OPERATOR":
                        result[
                            "MEASUREMENT_OPERATOR"
                        ],
                    "RELEVANT_DIRECTED_EDGE_IDS":
                        "|".join(
                            str(x)
                            for x in result[
                                "EDGE_IDS"
                            ]
                        ),
                    "PATH_HITS":
                        result[
                            "PATH_HITS"
                        ],
                    "OD_P_GT_0":
                        result[
                            "OD_P_GT_0"
                        ],
                    "P_MAX":
                        f"{result['P_MAX']:.15f}",
                    "C_a_ISTAT":
                        f"{result['C_a_ISTAT']:.12f}",
                    "MODEL_EXPOSURE":
                        result[
                            "MODEL_EXPOSURE"
                        ],
                    "SAME_CORRIDOR_AS_EXISTING_PRIMARY":
                        (
                            "YES"
                            if result[
                                "CORRIDOR_GROUP"
                            ] in PRIMARY_CORRIDOR_GROUPS
                            else "NO"
                        ),
                }
            )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 100)
    print(
        "E1-C — ANAS SENSITIVITY MODEL-EXPOSURE SCREEN"
    )
    print("=" * 100)

    # -----------------------------------------------------------------
    # A. File preflight
    # -----------------------------------------------------------------

    print()
    print("A. FILE PREFLIGHT")
    print("-" * 100)

    for path in [
        ANAS_MAPPING,
        ACCESS_PATHS,
        PATH_OFFSETS,
        TRANSITION_SLOTS,
        B5_EDGEID,
        COMMUTING_XLSX,
    ]:
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

    require_output_absent(
        OUTPUT_CSV
    )

    # -----------------------------------------------------------------
    # B. Sensitivity mapping
    # -----------------------------------------------------------------

    sensitivity_rows = (
        load_sensitivity_mapping()
    )

    print()
    print("B. CANONICAL SENSITIVITY SET")
    print("-" * 100)

    print(
        "SENSITIVITY_ROWS =",
        len(
            sensitivity_rows
        ),
    )

    for row in sensitivity_rows:
        print(
            f"{row['SECTION_ID']} | "
            f"ROAD={row['ROAD']} | "
            f"QUALITY={row['QUALITY_CLASS']} | "
            f"EXTERNAL={row['EXTERNAL_EXPOSURE']} | "
            f"CORRIDOR={row['CORRIDOR_GROUP']} | "
            f"INFO={row['INFORMATION_ROLE']} | "
            f"QGIS={row['QGIS_REVIEW_STATUS']} | "
            f"EDGES={row['EDGE_IDS']}"
        )

    # -----------------------------------------------------------------
    # C. Access paths
    # -----------------------------------------------------------------

    access_paths, max_weight_error = (
        load_access_paths()
    )

    print()
    print("C. FROZEN ACCESS PATHS")
    print("-" * 100)

    print(
        "PATH_ROWS =",
        len(access_paths),
    )

    print(
        "OD_ROWS =",
        len(access_paths) // 9,
    )

    print(
        "PATHS_PER_OD = 9"
    )

    print(
        "MAX_OD_PAIR_WEIGHT_SUM_ERROR =",
        f"{max_weight_error:.3e}",
    )

    # -----------------------------------------------------------------
    # D. Commuting
    # -----------------------------------------------------------------

    commuting, commuting_schema = (
        load_commuting()
    )

    print()
    print("D. ISTAT COMMUTING")
    print("-" * 100)

    print(
        "COMMUTING_ROWS =",
        len(commuting),
    )

    print(
        "SHEET =",
        commuting_schema[
            "sheet"
        ],
    )

    print(
        "ORIGIN_COLUMN =",
        commuting_schema[
            "origin_col"
        ],
    )

    print(
        "DESTINATION_COLUMN =",
        commuting_schema[
            "destination_col"
        ],
    )

    print(
        "VALUE_COLUMN =",
        commuting_schema[
            "value_col"
        ],
    )

    # Exact OD-domain join.
    path_od = (
        access_paths[
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ]
        ]
        .drop_duplicates()
    )

    od_join = path_od.merge(
        commuting[
            [
                "origin_PRO_COM",
                "destination_PRO_COM",
            ]
        ],
        on=[
            "origin_PRO_COM",
            "destination_PRO_COM",
        ],
        how="outer",
        indicator=True,
    )

    if not (
        od_join["_merge"]
        == "both"
    ).all():
        counts = (
            od_join["_merge"]
            .value_counts()
            .to_dict()
        )

        raise RuntimeError(
            "Access-path / commuting OD domains differ: "
            f"{counts}"
        )

    print(
        "ACCESS_PATH_COMMUTING_OD_JOIN = "
        "46010 / 46010"
    )

    # -----------------------------------------------------------------
    # E. Frozen sequence system
    # -----------------------------------------------------------------

    offsets = np.load(
        PATH_OFFSETS,
        mmap_mode="r",
    )

    transition_slots = np.load(
        TRANSITION_SLOTS,
        mmap_mode="r",
    )

    b5_edgeid = (
        load_npz(
            B5_EDGEID
        )
        .tocsr()
    )

    print()
    print("E. FROZEN SEQUENCE SYSTEM")
    print("-" * 100)

    print(
        "OFFSETS =",
        len(offsets),
    )

    print(
        "TRANSITION_SLOTS =",
        len(transition_slots),
    )

    print(
        "B5_EDGEID_NNZ =",
        b5_edgeid.nnz,
    )

    if (
        len(offsets)
        != len(access_paths) + 1
    ):
        raise RuntimeError(
            "Offsets/access-path count mismatch."
        )

    # -----------------------------------------------------------------
    # F. Canonical edge QA
    # -----------------------------------------------------------------

    (
        section_bit,
        slot_mask,
        edge_qa,
    ) = build_slot_mask(
        b5_edgeid,
        sensitivity_rows,
    )

    print()
    print("F. CANONICAL EDGE QA")
    print("-" * 100)

    for (
        section_id,
        edge_id,
        count,
    ) in edge_qa:
        print(
            f"{section_id} | "
            f"EDGE_ID={edge_id} | "
            f"B5_SLOT_OCCURRENCES={count}"
        )

    # -----------------------------------------------------------------
    # G. Frozen path scan
    # -----------------------------------------------------------------

    section_path_hits = scan_paths(
        offsets,
        transition_slots,
        slot_mask,
        section_bit,
    )

    # -----------------------------------------------------------------
    # H. Aggregate p_ij^a
    # -----------------------------------------------------------------

    results = aggregate_exposure(
        access_paths,
        sensitivity_rows,
        section_path_hits,
    )

    assign_commuting(
        results,
        commuting,
    )

    # -----------------------------------------------------------------
    # I. Complete 13/13 table
    # -----------------------------------------------------------------

    print()
    print("H. COMPLETE 13/13 EXPOSURE TABLE")
    print("=" * 160)

    header = (
        f"{'SECTION':<9} "
        f"{'ROAD':<9} "
        f"{'Q':<3} "
        f"{'EXT':<8} "
        f"{'MODEL':<5} "
        f"{'PATH_HITS':>10} "
        f"{'OD_GT_0':>8} "
        f"{'P_MAX':>10} "
        f"{'C_a_ISTAT':>14} "
        f"{'CORRIDOR':<32} "
        f"{'INFO':<12}"
    )

    print(
        header
    )

    print(
        "-" * 160
    )

    for result in results:
        print(
            f"{result['SECTION_ID']:<9} "
            f"{result['ROAD']:<9} "
            f"{result['QUALITY_CLASS']:<3} "
            f"{result['EXTERNAL_EXPOSURE']:<8} "
            f"{result['MODEL_EXPOSURE']:<5} "
            f"{result['PATH_HITS']:>10d} "
            f"{result['OD_P_GT_0']:>8d} "
            f"{result['P_MAX']:>10.6f} "
            f"{result['C_a_ISTAT']:>14.3f} "
            f"{result['CORRIDOR_GROUP']:<32} "
            f"{result['INFORMATION_ROLE']:<12}"
        )

    # -----------------------------------------------------------------
    # I. No-exposure list
    # -----------------------------------------------------------------

    no_exposure = [
        result
        for result in results
        if result[
            "MODEL_EXPOSURE"
        ] == "NO"
    ]

    exposed = [
        result
        for result in results
        if result[
            "MODEL_EXPOSURE"
        ] == "YES"
    ]

    print()
    print("I. MODEL EXPOSURE SUMMARY")
    print("=" * 100)

    print(
        "SENSITIVITY_TOTAL =",
        len(results),
    )

    print(
        "MODEL_EXPOSURE_YES =",
        len(exposed),
    )

    print(
        "MODEL_EXPOSURE_NO =",
        len(no_exposure),
    )

    print(
        "NO_EXPOSURE_SECTION_IDS =",
        (
            "|".join(
                r["SECTION_ID"]
                for r in no_exposure
            )
            if no_exposure
            else "NONE"
        ),
    )

    # -----------------------------------------------------------------
    # J. Structural candidate view
    # -----------------------------------------------------------------

    print()
    print("J. STRUCTURAL CANDIDATE VIEW")
    print("=" * 140)

    print(
        "NOTE = This is NOT an automatic replacement selection."
    )

    print(
        "ORDERING_INPUTS = "
        "MODEL_EXPOSURE / QUALITY / EXTERNAL_EXPOSURE / "
        "CORRIDOR_DISTINCTION / INFORMATION_ROLE"
    )

    print()

    for result in exposed:
        same_corridor = (
            result[
                "CORRIDOR_GROUP"
            ]
            in PRIMARY_CORRIDOR_GROUPS
        )

        print(
            f"{result['SECTION_ID']} | "
            f"ROAD={result['ROAD']} | "
            f"QUALITY={result['QUALITY_CLASS']} | "
            f"EXTERNAL={result['EXTERNAL_EXPOSURE']} | "
            f"CORRIDOR={result['CORRIDOR_GROUP']} | "
            f"SAME_AS_EXISTING_PRIMARY="
            f"{'YES' if same_corridor else 'NO'} | "
            f"INFO={result['INFORMATION_ROLE']} | "
            f"OD_P_GT_0={result['OD_P_GT_0']} | "
            f"P_MAX={result['P_MAX']:.6f} | "
            f"C_a_ISTAT={result['C_a_ISTAT']:.3f}"
        )

    # -----------------------------------------------------------------
    # K. Output
    # -----------------------------------------------------------------

    write_output(
        results
    )

    print()
    print("K. OUTPUT")
    print("-" * 100)

    print(
        "OUTPUT_FILE =",
        OUTPUT_CSV,
    )

    print(
        "OUTPUT_ROWS =",
        len(results),
    )

    print(
        "OUTPUT_STATUS = "
        "TEMPORARY / SCREENING ONLY / NOT FROZEN"
    )

    # -----------------------------------------------------------------
    # L. Gate status
    # -----------------------------------------------------------------

    print()
    print("L. E1-C STATE")
    print("=" * 100)

    print(
        "SENSITIVITY_SCREEN_COMPLETE = YES"
    )

    print(
        "REPLACEMENT_PRIMARY_SELECTED = NO"
    )

    print(
        "Q_CALIBRATED = NO"
    )

    print(
        "BETA_CALIBRATED = NO"
    )

    print(
        "LOSS_SELECTED = NO"
    )

    print(
        "ANAS_2025_USED = NO"
    )

    print(
        "E2_STARTED = NO"
    )

    print(
        "NEXT_ACTION = "
        "RETURN ANAS_SENSITIVITY_EXPOSURE_REPORT TO CHAT"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

