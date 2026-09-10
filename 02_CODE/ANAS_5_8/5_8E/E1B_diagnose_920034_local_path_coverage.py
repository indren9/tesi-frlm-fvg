"""
E1-B — DIAGNOSTIC OF ANAS 920034 LOCAL PATH COVERAGE

PURPOSE
-------
Capire perché la sezione ANAS PRIMARY 920034 ha:

    PATH_HITS = 0
    OD_P_GT_0 = 0

nel calibration operator E1.

Il test NON modifica il mapping ANAS e NON ricostruisce shortest paths.

Vengono esaminati:

1. gli edge OSM canonici della sezione 920034;
2. gli edge immediatamente vicini appartenenti allo stesso OSM way;
3. gli edge che condividono un nodo con gli edge della sezione.

Per ciascun edge viene verificato se compare nei path frozen della Fase 5.7.

INPUTS
------
- ANAS_5_8D_calibration_mapping_v01.csv
- osm_directed_edges_v02.sqlite
- osm_turn_state_edgeid_v01.npz
- OSM_OD_path_offsets_v01.npy
- OSM_OD_transition_slots_v01.npy
- OSM_OD_access_paths_v01.csv

OUTPUTS
-------
Solo report console.

ASSUMPTIONS
-----------
- Il mapping canonico ANAS è quello già verificato contro la review QGIS.
- I path frozen rappresentano esclusivamente il dominio OD intercomunale
  utilizzato dalla Gravity v0.
- L'assenza di path sull'edge target NON implica automaticamente
  un errore del mapping.
- La presenza di path sugli edge vicini è solo evidenza diagnostica.

FROZEN ARTIFACTS USED
---------------------
- G_OSM_operativo
- OD_PATH_SYSTEM_OSM
- ANAS_5_8D_calibration_mapping_v01

FILES WRITTEN
-------------
NESSUNO.

FILES NEVER MODIFIED
--------------------
Qualsiasi artefatto sotto:
C:\\Tesi\\Tesi_QGIS\\02_package\\
"""

from pathlib import Path
import csv
import sqlite3
from collections import defaultdict

import numpy as np
from scipy.sparse import load_npz


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

ANAS_MAPPING = (
    ROOT
    / "02_package"
    / "anas_calibration_v0"
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

GRAPH_ROOT = (
    ROOT
    / "02_package"
    / "grafo_operativo_osm"
)

B2_SQLITE = (
    GRAPH_ROOT
    / "osm_directed_edges_v02.sqlite"
)

B5_EDGEID = (
    GRAPH_ROOT
    / "osm_turn_state_edgeid_v01.npz"
)

OD_ROOT = (
    ROOT
    / "02_package"
    / "od_paths_osm_light"
)

PATH_OFFSETS = (
    OD_ROOT
    / "OSM_OD_path_offsets_v01.npy"
)

TRANSITION_SLOTS = (
    OD_ROOT
    / "OSM_OD_transition_slots_v01.npy"
)

ACCESS_PATHS = (
    OD_ROOT
    / "OSM_OD_access_paths_v01.csv"
)

SECTION_ID = "920034"

SCAN_CHUNK_SIZE = 10_000_000


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


def parse_pipe_ints(value):
    text = clean(value)

    if not text:
        return []

    return [
        int(x.strip())
        for x in text.split("|")
        if x.strip()
    ]


# =============================================================================
# LOAD ANAS TARGET
# =============================================================================

def load_target():
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
            if clean(row["SECTION_ID"]) == SECTION_ID:

                return {
                    "road": clean(
                        row["ROAD"]
                    ),
                    "segments": clean(
                        row[
                            "OSM_PHYSICAL_SEGMENT"
                        ]
                    ),
                    "edges": parse_pipe_ints(
                        row[
                            "RELEVANT_DIRECTED_EDGE_IDS"
                        ]
                    ),
                    "tgma": float(
                        row[
                            "TGMA_LIGHT_2024"
                        ]
                    ),
                }

    raise RuntimeError(
        f"SECTION_ID {SECTION_ID} non trovata."
    )


# =============================================================================
# LOAD PATH METADATA
# =============================================================================

def load_path_metadata():
    origins = []
    destinations = []
    origin_names = []
    destination_names = []
    pair_weights = []

    with ACCESS_PATHS.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for expected_idx, row in enumerate(reader):

            idx = int(
                row["path_idx"]
            )

            if idx != expected_idx:
                raise RuntimeError(
                    f"path_idx non contiguo: "
                    f"atteso={expected_idx}, "
                    f"trovato={idx}"
                )

            origins.append(
                clean(
                    row["origin_PRO_COM"]
                )
            )

            destinations.append(
                clean(
                    row[
                        "destination_PRO_COM"
                    ]
                )
            )

            origin_names.append(
                clean(
                    row["origin_COMUNE"]
                )
            )

            destination_names.append(
                clean(
                    row[
                        "destination_COMUNE"
                    ]
                )
            )

            pair_weights.append(
                float(
                    row["pair_weight"]
                )
            )

    return (
        np.asarray(origins),
        np.asarray(destinations),
        np.asarray(origin_names),
        np.asarray(destination_names),
        np.asarray(
            pair_weights,
            dtype=np.float64,
        ),
    )


# =============================================================================
# GRAPH NEIGHBOURHOOD
# =============================================================================

def load_graph_neighbourhood(
    target_edge_ids,
):
    con = sqlite3.connect(
        f"file:{B2_SQLITE.as_posix()}?mode=ro",
        uri=True,
    )

    con.row_factory = sqlite3.Row

    try:
        placeholders = ",".join(
            "?"
            for _ in target_edge_ids
        )

        target_rows = con.execute(
            f"""
            SELECT
                edge_id,
                segment_uid,
                way_id,
                seq,
                u,
                v,
                way_direction,
                length_m,
                highway,
                routing_status
            FROM directed_edges
            WHERE edge_id IN ({placeholders})
            ORDER BY edge_id
            """,
            target_edge_ids,
        ).fetchall()

        if (
            len(target_rows)
            != len(target_edge_ids)
        ):
            found = {
                int(row["edge_id"])
                for row in target_rows
            }

            missing = (
                set(target_edge_ids)
                - found
            )

            raise RuntimeError(
                f"Target edge mancanti B2: "
                f"{sorted(missing)}"
            )

        target_set = set(
            target_edge_ids
        )

        # --------------------------------------------------------------
        # SAME WAY ±2 segments
        # --------------------------------------------------------------

        same_way = {}

        for row in target_rows:

            way_id = int(
                row["way_id"]
            )

            seq = int(
                row["seq"]
            )

            rows = con.execute(
                """
                SELECT
                    edge_id,
                    segment_uid,
                    way_id,
                    seq,
                    u,
                    v,
                    way_direction,
                    length_m,
                    highway,
                    routing_status
                FROM directed_edges
                WHERE way_id = ?
                  AND seq BETWEEN ? AND ?
                ORDER BY seq, edge_id
                """,
                (
                    way_id,
                    seq - 2,
                    seq + 2,
                ),
            ).fetchall()

            for candidate in rows:

                edge_id = int(
                    candidate["edge_id"]
                )

                if edge_id not in target_set:
                    same_way[
                        edge_id
                    ] = candidate

        # --------------------------------------------------------------
        # NODE-SHARING neighbours
        # --------------------------------------------------------------

        target_nodes = sorted(
            {
                int(row["u"])
                for row in target_rows
            }
            |
            {
                int(row["v"])
                for row in target_rows
            }
        )

        node_placeholders = ",".join(
            "?"
            for _ in target_nodes
        )

        node_rows = con.execute(
            f"""
            SELECT
                edge_id,
                segment_uid,
                way_id,
                seq,
                u,
                v,
                way_direction,
                length_m,
                highway,
                routing_status
            FROM directed_edges
            WHERE u IN ({node_placeholders})
               OR v IN ({node_placeholders})
            ORDER BY way_id, seq, edge_id
            """,
            target_nodes + target_nodes,
        ).fetchall()

        node_neighbours = {}

        for candidate in node_rows:

            edge_id = int(
                candidate["edge_id"]
            )

            if edge_id not in target_set:
                node_neighbours[
                    edge_id
                ] = candidate

    finally:
        con.close()

    return (
        target_rows,
        same_way,
        node_neighbours,
    )


# =============================================================================
# PATH USAGE SCAN
# =============================================================================

def scan_candidate_edges(
    candidate_edge_ids,
    offsets,
    transition_slots,
    b5_edgeid,
):
    edge_ids = sorted(
        candidate_edge_ids
    )

    edge_to_code = {
        edge_id: code
        for code, edge_id
        in enumerate(
            edge_ids,
            start=1,
        )
    }

    code_to_edge = {
        code: edge_id
        for edge_id, code
        in edge_to_code.items()
    }

    # One value for every B5 CSR data slot.
    slot_code = np.zeros(
        b5_edgeid.nnz,
        dtype=np.uint16,
    )

    b5_slot_counts = {}

    for edge_id in edge_ids:

        mask = (
            b5_edgeid.data
            == edge_id
        )

        count = int(
            np.count_nonzero(mask)
        )

        b5_slot_counts[
            edge_id
        ] = count

        if count > 0:

            slot_code[
                mask
            ] = edge_to_code[
                edge_id
            ]

    path_sets = {
        edge_id: set()
        for edge_id in edge_ids
    }

    n_slots = len(
        transition_slots
    )

    print()
    print("F. FROZEN PATH SCAN")
    print("-" * 100)

    print(
        "TRANSITION_SLOTS =",
        f"{n_slots:,}",
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

        codes = slot_code[
            slots
        ]

        local_positions = np.flatnonzero(
            codes
        )

        if local_positions.size:

            global_positions = (
                local_positions
                + lo
            )

            path_idx = (
                np.searchsorted(
                    offsets,
                    global_positions,
                    side="right",
                )
                - 1
            )

            matched_codes = codes[
                local_positions
            ]

            for code in np.unique(
                matched_codes
            ):

                edge_id = code_to_edge[
                    int(code)
                ]

                paths = path_idx[
                    matched_codes
                    == code
                ]

                path_sets[
                    edge_id
                ].update(
                    map(
                        int,
                        np.unique(paths),
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
                f"SCAN_PROGRESS = "
                f"{progress:3d}%"
            )

            while (
                next_progress
                <= progress
            ):
                next_progress += 10

    return (
        b5_slot_counts,
        path_sets,
    )


# =============================================================================
# SUMMARIES
# =============================================================================

def summarize_group(
    label,
    edge_ids,
    path_sets,
    origins,
    destinations,
    pair_weights,
):
    all_paths = set()

    for edge_id in edge_ids:
        all_paths.update(
            path_sets.get(
                edge_id,
                set(),
            )
        )

    path_idx = np.asarray(
        sorted(all_paths),
        dtype=np.int64,
    )

    if path_idx.size == 0:

        od_count = 0
        weighted_path_mass = 0.0

    else:

        od_pairs = {
            (
                origins[p],
                destinations[p],
            )
            for p in path_idx
        }

        od_count = len(
            od_pairs
        )

        weighted_path_mass = float(
            pair_weights[
                path_idx
            ].sum()
        )

    print(
        f"{label:<28} | "
        f"EDGES={len(edge_ids):>3} | "
        f"PATH_HITS={len(all_paths):>7} | "
        f"OD_HITS={od_count:>6} | "
        f"WEIGHT_MASS={weighted_path_mass:.6f}"
    )

    return (
        len(all_paths),
        od_count,
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 100)
    print(
        "E1-B — DIAGNOSTIC 920034 LOCAL PATH COVERAGE"
    )
    print("=" * 100)

    # -----------------------------------------------------------------
    # A. Preflight
    # -----------------------------------------------------------------

    print()
    print("A. FILE PREFLIGHT")
    print("-" * 100)

    for path in [
        ANAS_MAPPING,
        B2_SQLITE,
        B5_EDGEID,
        PATH_OFFSETS,
        TRANSITION_SLOTS,
        ACCESS_PATHS,
    ]:
        require_file(path)
        print(
            "PASS =",
            path,
        )

    # -----------------------------------------------------------------
    # B. Target
    # -----------------------------------------------------------------

    target = load_target()

    print()
    print("B. ANAS TARGET")
    print("-" * 100)

    print(
        "SECTION_ID =",
        SECTION_ID,
    )

    print(
        "ROAD       =",
        target["road"],
    )

    print(
        "TGMA_2024  =",
        target["tgma"],
    )

    print(
        "SEGMENTS   =",
        target["segments"],
    )

    print(
        "EDGE_IDS   =",
        target["edges"],
    )

    # -----------------------------------------------------------------
    # C. Graph neighbourhood
    # -----------------------------------------------------------------

    (
        target_rows,
        same_way,
        node_neighbours,
    ) = load_graph_neighbourhood(
        target["edges"]
    )

    print()
    print("C. TARGET EDGE METADATA")
    print("-" * 100)

    for row in target_rows:

        print(
            f"EDGE={row['edge_id']} | "
            f"SEG={row['segment_uid']} | "
            f"WAY={row['way_id']} | "
            f"SEQ={row['seq']} | "
            f"U={row['u']} | "
            f"V={row['v']} | "
            f"DIR={row['way_direction']} | "
            f"HIGHWAY={row['highway']}"
        )

    print()
    print("D. LOCAL NEIGHBOURHOOD SIZE")
    print("-" * 100)

    print(
        "TARGET_EDGES             =",
        len(
            target["edges"]
        ),
    )

    print(
        "SAME_WAY_NEIGHBOURS      =",
        len(same_way),
    )

    print(
        "NODE_SHARING_NEIGHBOURS  =",
        len(node_neighbours),
    )

    # -----------------------------------------------------------------
    # E. Candidate universe
    # -----------------------------------------------------------------

    all_candidate_edges = (
        set(
            target["edges"]
        )
        | set(
            same_way
        )
        | set(
            node_neighbours
        )
    )

    print()
    print("E. CANDIDATE EDGE UNIVERSE")
    print("-" * 100)

    print(
        "UNIQUE_EDGES_TO_CHECK =",
        len(
            all_candidate_edges
        ),
    )

    # -----------------------------------------------------------------
    # F. Frozen sequence system
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

    (
        origins,
        destinations,
        origin_names,
        destination_names,
        pair_weights,
    ) = load_path_metadata()

    if (
        len(offsets) - 1
        != len(origins)
    ):
        raise RuntimeError(
            "Path metadata / offsets mismatch."
        )

    (
        b5_slot_counts,
        path_sets,
    ) = scan_candidate_edges(
        all_candidate_edges,
        offsets,
        transition_slots,
        b5_edgeid,
    )

    # -----------------------------------------------------------------
    # G. Per-edge usage
    # -----------------------------------------------------------------

    print()
    print("G. TARGET EDGE PATH USAGE")
    print("=" * 100)

    for edge_id in target[
        "edges"
    ]:

        paths = path_sets[
            edge_id
        ]

        print(
            f"EDGE_ID={edge_id} | "
            f"B5_SLOTS="
            f"{b5_slot_counts[edge_id]} | "
            f"PATH_HITS="
            f"{len(paths)}"
        )

    print()
    print("H. SAME-WAY NEIGHBOURS")
    print("=" * 100)

    for edge_id, row in sorted(
        same_way.items(),
        key=lambda x: (
            x[1]["way_id"],
            x[1]["seq"],
            x[0],
        ),
    ):

        paths = path_sets[
            edge_id
        ]

        print(
            f"EDGE={edge_id} | "
            f"SEG={row['segment_uid']} | "
            f"WAY={row['way_id']} | "
            f"SEQ={row['seq']} | "
            f"U={row['u']} | "
            f"V={row['v']} | "
            f"PATH_HITS={len(paths)}"
        )

    print()
    print("I. NODE-SHARING NEIGHBOURS")
    print("=" * 100)

    for edge_id, row in sorted(
        node_neighbours.items(),
        key=lambda x: (
            x[1]["way_id"],
            x[1]["seq"],
            x[0],
        ),
    ):

        paths = path_sets[
            edge_id
        ]

        print(
            f"EDGE={edge_id} | "
            f"SEG={row['segment_uid']} | "
            f"WAY={row['way_id']} | "
            f"SEQ={row['seq']} | "
            f"U={row['u']} | "
            f"V={row['v']} | "
            f"PATH_HITS={len(paths)}"
        )

    # -----------------------------------------------------------------
    # J. Group summary
    # -----------------------------------------------------------------

    print()
    print("J. GROUP SUMMARY")
    print("=" * 100)

    (
        target_paths,
        target_ods,
    ) = summarize_group(
        "TARGET",
        set(
            target["edges"]
        ),
        path_sets,
        origins,
        destinations,
        pair_weights,
    )

    (
        same_way_paths,
        same_way_ods,
    ) = summarize_group(
        "SAME_WAY_NEIGHBOURS",
        set(
            same_way
        ),
        path_sets,
        origins,
        destinations,
        pair_weights,
    )

    (
        node_paths,
        node_ods,
    ) = summarize_group(
        "NODE_NEIGHBOURS",
        set(
            node_neighbours
        ),
        path_sets,
        origins,
        destinations,
        pair_weights,
    )

    # -----------------------------------------------------------------
    # K. Examples
    # -----------------------------------------------------------------

    neighbour_paths = set()

    for edge_id in (
        set(same_way)
        | set(node_neighbours)
    ):
        neighbour_paths.update(
            path_sets[
                edge_id
            ]
        )

    print()
    print("K. EXAMPLE OD USING LOCAL NEIGHBOURHOOD")
    print("-" * 100)

    if not neighbour_paths:

        print(
            "NONE"
        )

    else:

        seen_od = set()
        printed = 0

        for path_idx in sorted(
            neighbour_paths
        ):

            od = (
                origins[path_idx],
                destinations[path_idx],
            )

            if od in seen_od:
                continue

            seen_od.add(
                od
            )

            print(
                f"{origins[path_idx]} "
                f"{origin_names[path_idx]}"
                f" -> "
                f"{destinations[path_idx]} "
                f"{destination_names[path_idx]}"
            )

            printed += 1

            if printed >= 10:
                break

    # -----------------------------------------------------------------
    # L. Diagnostic signal
    # -----------------------------------------------------------------

    print()
    print("L. DIAGNOSTIC SIGNAL")
    print("=" * 100)

    if target_paths > 0:

        print(
            "TARGET_PATH_ACTIVITY = YES"
        )

        print(
            "RESULT = UNEXPECTED_TARGET_ACTIVITY"
        )

    elif (
        same_way_paths > 0
        or node_paths > 0
    ):

        print(
            "TARGET_PATH_ACTIVITY = NO"
        )

        print(
            "LOCAL_NEIGHBOUR_ACTIVITY = YES"
        )

        print(
            "RESULT = LOCAL_REPRESENTATION_OR_MAPPING_SIGNAL"
        )

        print(
            "INTERPRETATION = "
            "la zona è usata dai path intercomunali, "
            "ma non gli edge canonici della sezione 920034"
        )

    else:

        print(
            "TARGET_PATH_ACTIVITY = NO"
        )

        print(
            "LOCAL_NEIGHBOUR_ACTIVITY = NO"
        )

        print(
            "RESULT = DEMAND_DOMAIN_COVERAGE_SIGNAL"
        )

        print(
            "INTERPRETATION = "
            "anche l'immediato intorno della sezione "
            "non è utilizzato dai path intercomunali"
        )

    print()
    print(
        "E1_STATUS = "
        "ONE_SMALL_TEST_COMPLETED / "
        "NO E2 STARTED"
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

