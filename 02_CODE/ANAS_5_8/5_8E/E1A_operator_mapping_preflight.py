"""
E1-A — CALIBRATION OPERATOR MAPPING PREFLIGHT

PURPOSE
-------
Verificare in sola lettura la struttura esatta degli artefatti frozen
necessari a costruire p_ij^a per le tre sezioni ANAS PRIMARY.

INPUTS
------
1. ANAS_5_8D_calibration_mapping_v01.csv
2. OSM_OD_access_paths_v01.csv
3. OSM_OD_sequence_contract_v01.json
4. osm_directed_edges_v02.sqlite
5. osm_turn_state_edgeid_v01.npz

OUTPUTS
-------
Solo output console.
Nessun file viene scritto.

ASSUMPTIONS
-----------
- PRIMARY = 920034, 920032, 920039.
- MEASUREMENT_OPERATOR = BIDIRECTIONAL_SUM.
- Nessun nuovo spatial matching.
- Nessun shortest path.
- Nessuna calibrazione.
- Nessun uso di ANAS 2025.

FROZEN ARTIFACTS USED
---------------------
Tutti gli input elencati sopra sono letti esclusivamente dai package frozen.

FILES WRITTEN
-------------
NESSUNO.

FILES NEVER MODIFIED
--------------------
Tutti gli input frozen.
Qualsiasi file sotto 02_package.
"""

from pathlib import Path
import csv
import json
import sqlite3

import numpy as np
from scipy.sparse import load_npz


PRIMARY = {"920034", "920032", "920039"}

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

ANAS = (
    ROOT
    / "02_package"
    / "anas_calibration_v0"
    / "ANAS_5_8D_calibration_mapping_v01.csv"
)

OD_ROOT = (
    ROOT
    / "02_package"
    / "od_paths_osm_light"
)

ACCESS_PATHS = OD_ROOT / "OSM_OD_access_paths_v01.csv"
SEQUENCE_CONTRACT = OD_ROOT / "OSM_OD_sequence_contract_v01.json"

GRAPH_ROOT = (
    ROOT
    / "02_package"
    / "grafo_operativo_osm"
)

B2_SQLITE = GRAPH_ROOT / "osm_directed_edges_v02.sqlite"
B5_EDGEID = GRAPH_ROOT / "osm_turn_state_edgeid_v01.npz"


def detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)

    return csv.Sniffer().sniff(
        sample,
        delimiters=",;\t|",
    ).delimiter


def main():
    print("=" * 100)
    print("E1-A — CALIBRATION OPERATOR MAPPING PREFLIGHT")
    print("=" * 100)

    paths = {
        "ANAS_MAPPING": ANAS,
        "ACCESS_PATHS": ACCESS_PATHS,
        "SEQUENCE_CONTRACT": SEQUENCE_CONTRACT,
        "B2_SQLITE": B2_SQLITE,
        "B5_EDGEID": B5_EDGEID,
    }

    print()
    print("A. FILE EXISTENCE")
    print("-" * 100)

    for name, path in paths.items():
        exists = path.is_file()
        print(f"{name:<20} = {path}")
        print(f"{'':<20}   EXISTS={exists}")

        if not exists:
            raise FileNotFoundError(path)

    # ==================================================================
    # ANAS MAPPING
    # ==================================================================

    print()
    print("B. ANAS CANONICAL MAPPING")
    print("-" * 100)

    sep = detect_delimiter(ANAS)

    with ANAS.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f, delimiter=sep)

        if reader.fieldnames is None:
            raise RuntimeError("ANAS mapping senza header.")

        print("DELIMITER =", repr(sep))
        print("COLUMNS:")

        for i, col in enumerate(reader.fieldnames, start=1):
            print(f"  [{i:02d}] {col}")

        rows = list(reader)

    primary_rows = [
        row
        for row in rows
        if str(row.get("SECTION_ID", "")).strip() in PRIMARY
    ]

    print()
    print("TOTAL_ROWS   =", len(rows))
    print("PRIMARY_ROWS =", len(primary_rows))

    if len(primary_rows) != 3:
        raise RuntimeError(
            f"Attese 3 PRIMARY, trovate {len(primary_rows)}."
        )

    for row in primary_rows:
        print()
        print("#" * 100)
        print("SECTION_ID =", row.get("SECTION_ID"))
        print("#" * 100)

        for col in reader.fieldnames:
            print(f"{col:<35} = {row.get(col)}")

    # ==================================================================
    # ACCESS PATH HEADER
    # ==================================================================

    print()
    print("C. ACCESS-PATH METADATA")
    print("-" * 100)

    sep_paths = detect_delimiter(ACCESS_PATHS)

    with ACCESS_PATHS.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader_paths = csv.DictReader(
            f,
            delimiter=sep_paths,
        )

        if reader_paths.fieldnames is None:
            raise RuntimeError(
                "OSM_OD_access_paths_v01.csv senza header."
            )

        print("DELIMITER =", repr(sep_paths))
        print("COLUMNS:")

        for i, col in enumerate(
            reader_paths.fieldnames,
            start=1,
        ):
            print(f"  [{i:02d}] {col}")

        first = next(reader_paths)

    print()
    print("FIRST_PATH_ROW:")

    for key, value in first.items():
        print(f"{key:<35} = {value}")

    # ==================================================================
    # SEQUENCE CONTRACT
    # ==================================================================

    print()
    print("D. SEQUENCE CONTRACT")
    print("-" * 100)

    with SEQUENCE_CONTRACT.open(
        "r",
        encoding="utf-8",
    ) as f:
        contract = json.load(f)

    print(json.dumps(
        contract,
        indent=2,
        ensure_ascii=False,
    ))

    # ==================================================================
    # B2 DIRECTED EDGE SCHEMA
    # ==================================================================

    print()
    print("E. B2 DIRECTED_EDGES SCHEMA")
    print("-" * 100)

    con = sqlite3.connect(
        f"file:{B2_SQLITE.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        columns = con.execute(
            "PRAGMA table_info(directed_edges)"
        ).fetchall()

        for col in columns:
            print(
                f"cid={col[0]:>2} "
                f"name={col[1]:<25} "
                f"type={col[2]}"
            )

        n_edges = con.execute(
            "SELECT COUNT(*) FROM directed_edges"
        ).fetchone()[0]

        print()
        print("B2_DIRECTED_EDGES =", n_edges)

    finally:
        con.close()

    # ==================================================================
    # B5 EDGE-ID MATRIX
    # ==================================================================

    print()
    print("F. B5 EDGEID MATRIX")
    print("-" * 100)

    edgeid = load_npz(B5_EDGEID).tocsr()

    print("SHAPE      =", edgeid.shape)
    print("NNZ        =", edgeid.nnz)
    print("DATA_DTYPE =", edgeid.data.dtype)
    print("INDICES_DTYPE =", edgeid.indices.dtype)
    print("INDPTR_DTYPE  =", edgeid.indptr.dtype)

    finite = np.isfinite(edgeid.data).all()

    print("EDGEID_DATA_FINITE =", bool(finite))

    if not finite:
        raise RuntimeError(
            "B5 EDGEID contiene valori non finiti."
        )

    print()
    print("=" * 100)
    print("E1-A RESULT = PREFLIGHT_COMPLETE")
    print("NO_FILES_WRITTEN = CONFIRMED")
    print("E1_OPERATOR_BUILT = NO")
    print("E2_STARTED = NO")


if __name__ == "__main__":
    try:
        main()
    finally:
        print("=== RUN COMPLETATA ===")

