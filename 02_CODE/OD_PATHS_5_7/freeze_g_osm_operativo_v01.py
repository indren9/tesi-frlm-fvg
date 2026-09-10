from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from pyproj import Transformer
from scipy.sparse import load_npz


# =============================================================================
# FASE 5.6 — E4
# FINAL FREEZE G_OSM_operativo_v01
#
# Principio:
#
# - NON modifica B1-B5;
# - NON modifica Gamma_OSM;
# - NON esegue nuovi audit;
# - verifica i gate finali già prodotti;
# - materializza una rappresentazione spaziale GPKG;
# - copia gli artefatti computazionali B1-B5;
# - copia le evidenze F1-F2-F3;
# - calcola SHA256;
# - promuove atomicamente il package canonico.
#
# Routing canonico:
#
#   B5 selective state-expanded turn-aware graph
#
# GPKG:
#
#   rappresentazione spaziale dei segmenti fisici OSM,
#   NON sostituisce il routing B5.
# =============================================================================


START = time.perf_counter()

ROOT = Path(
    r"C:\Tesi\Tesi_QGIS"
)

PACKAGE_PARENT = (
    ROOT
    / "02_package"
)

FINAL_DIR = (
    PACKAGE_PARENT
    / "grafo_operativo_osm"
)

STAMP = time.strftime(
    "%Y%m%d_%H%M%S"
)

STAGE_DIR = (
    PACKAGE_PARENT
    / f"_STAGING_grafo_operativo_osm_v01_{STAMP}"
)


# =============================================================================
# INPUT — FROZEN PBF
# =============================================================================

PBF = (
    ROOT
    / "00_originali"
    / "rete_stradale"
    / "osm"
    / "nord-est_2026-08-03.osm.pbf"
)

EXPECTED_PBF_SHA256 = (
    "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"
)


# =============================================================================
# INPUT — B1/B2/B3/B4/B5
# =============================================================================

BUILD_ROOT = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_6_osm_operativo"
)

B1 = (
    BUILD_ROOT
    / "build_b1"
    / "osm_topology_raw_v01.sqlite"
)

B2 = (
    BUILD_ROOT
    / "build_b2"
    / "osm_directed_edges_v02.sqlite"
)

B3 = (
    BUILD_ROOT
    / "build_b3"
    / "osm_core_connectivity_qa_v01.sqlite"
)

B4 = (
    BUILD_ROOT
    / "build_b4"
    / "osm_turn_restrictions_compiled_v01.sqlite"
)

B5_DIR = (
    BUILD_ROOT
    / "build_b5"
)

B5_INDEX = (
    B5_DIR
    / "osm_turn_state_index_v01.sqlite"
)

B5_TIME = (
    B5_DIR
    / "osm_turn_state_time_v01.npz"
)

B5_LENGTH = (
    B5_DIR
    / "osm_turn_state_length_v01.npz"
)

B5_EDGEID = (
    B5_DIR
    / "osm_turn_state_edgeid_v01.npz"
)

B5_BASE = (
    B5_DIR
    / "osm_turn_state_base_nodes_v01.npy"
)

B5_STATE_NODE = (
    B5_DIR
    / "osm_turn_state_node_id_v01.npy"
)


# =============================================================================
# INPUT — FINAL GATES
# =============================================================================

F1_DIR = (
    BUILD_ROOT
    / "final_gate"
    / "f1"
)

F1_MOVEMENTS = (
    F1_DIR
    / "G_OSM_F1_shadow_regression_movements_v01.csv"
)

F1_SUMMARY = (
    F1_DIR
    / "G_OSM_F1_shadow_regression_summary_v01.csv"
)

F1_MANIFEST = (
    F1_DIR
    / "G_OSM_F1_shadow_regression_manifest_v01.json"
)


F2_DIR = (
    BUILD_ROOT
    / "final_gate"
    / "f2"
)

F2_SAMPLES = (
    F2_DIR
    / "G_OSM_F2_build_fidelity_samples_v02.csv"
)

F2_DETAIL = (
    F2_DIR
    / "G_OSM_F2_build_fidelity_detail_v02.csv"
)

F2_MANIFEST = (
    F2_DIR
    / "G_OSM_F2_build_fidelity_manifest_v02.json"
)


F3_DIR = (
    BUILD_ROOT
    / "final_gate"
    / "f3"
)

F3_PAIR = (
    F3_DIR
    / "G_OSM_F3_access_pair_timeoptimal_v01.csv"
)

F3_OD = (
    F3_DIR
    / "G_OSM_F3_OD_metric_audit_v01.csv"
)

F3_EXTREMES = (
    F3_DIR
    / "G_OSM_F3_extreme_outliers_v01.csv"
)

F3_SUMMARY = (
    F3_DIR
    / "G_OSM_F3_summary_v01.json"
)


# =============================================================================
# INPUT — Gamma frozen reference
# =============================================================================

GAMMA_DIR = (
    ROOT
    / "02_package"
    / "accessi_comunali_osm_light"
)

GAMMA_GPKG = (
    GAMMA_DIR
    / "Gamma_OSM_L_comuni_fvg_v01.gpkg"
)

GAMMA_CSV = (
    GAMMA_DIR
    / "Gamma_OSM_L_comuni_fvg_v01.csv"
)

GAMMA_MANIFEST = (
    GAMMA_DIR
    / "Gamma_OSM_FINAL_manifest_v01.json"
)

EXPECTED_GAMMA_GPKG_SHA256 = (
    "b899a2e0e29d7ef366c42f4b68ef43a25b4ba1150052b6275770dd9ae23e1d3f"
)

EXPECTED_GAMMA_CSV_SHA256 = (
    "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
)

EXPECTED_GAMMA_MANIFEST_SHA256 = (
    "31ee2d78cd06c75cdf07014a8cecac4af2c58adeb26ec7285362ab4c02b11416"
)


# =============================================================================
# FINAL FILES
# =============================================================================

FINAL_GPKG_NAME = (
    "G_OSM_operativo_v01.gpkg"
)

FINAL_MANIFEST_NAME = (
    "G_OSM_FINAL_manifest_v01.json"
)

FINAL_MANIFEST_SHA_NAME = (
    "G_OSM_FINAL_manifest_v01.sha256"
)

FINAL_REPORT_NAME = (
    "G_OSM_FINAL_GATE_REPORT_v01.txt"
)

README_NAME = (
    "README_G_OSM_operativo_v01.txt"
)

GPKG_LAYER = (
    "G_OSM_operativo_segments_v01"
)

GPKG_METADATA_TABLE = (
    "G_OSM_operativo_metadata_v01"
)


SEP = "=" * 132
SUB = "-" * 132


# =============================================================================
# HELPERS
# =============================================================================

def require_file(
    path: Path,
    label: str,
) -> None:

    if not path.is_file():

        raise FileNotFoundError(
            f"{label} non trovato: {path}"
        )


def sha256_file(
    path: Path,
) -> str:

    h = hashlib.sha256()

    with path.open(
        "rb"
    ) as f:

        while True:

            block = f.read(
                1024 * 1024
            )

            if not block:
                break

            h.update(
                block
            )

    return h.hexdigest()


def json_load(
    path: Path,
):

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(
            f
        )


def qident(
    name: str,
) -> str:

    return (
        '"'
        + str(name).replace(
            '"',
            '""',
        )
        + '"'
    )


def copy_verified(
    src: Path,
    dst_dir: Path,
):

    dst = (
        dst_dir
        / src.name
    )

    if dst.exists():

        raise RuntimeError(
            f"Destination già esistente: {dst}"
        )


    print(
        f"COPY: {src.name}"
    )


    shutil.copy2(
        src,
        dst,
    )


    src_hash = sha256_file(
        src
    )

    dst_hash = sha256_file(
        dst
    )


    if src_hash != dst_hash:

        raise RuntimeError(
            f"Hash mismatch dopo COPY: {src.name}"
        )


    return {
        "filename":
            src.name,

        "source_path":
            str(
                src
            ),

        "canonical_path":
            str(
                FINAL_DIR
                / src.name
            ),

        "size_bytes":
            int(
                dst.stat().st_size
            ),

        "sha256":
            dst_hash,
    }


def read_b2_counts(
    path: Path,
):

    con = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )

    try:

        nodes = con.execute(
            "SELECT COUNT(*) FROM nodes"
        ).fetchone()[0]

        segments = con.execute(
            "SELECT COUNT(*) FROM segments"
        ).fetchone()[0]

        directed = con.execute(
            "SELECT COUNT(*) FROM directed_edges"
        ).fetchone()[0]

        core = con.execute(
            """
            SELECT COUNT(*)
            FROM directed_edges
            WHERE routing_code = 1
            """
        ).fetchone()[0]

        local = con.execute(
            """
            SELECT COUNT(*)
            FROM directed_edges
            WHERE routing_code = 2
            """
        ).fetchone()[0]

        suppressed = con.execute(
            """
            SELECT COUNT(*)
            FROM directed_edges
            WHERE routing_code = 0
            """
        ).fetchone()[0]

    finally:

        con.close()


    return {
        "nodes":
            int(
                nodes
            ),

        "segments":
            int(
                segments
            ),

        "directed_edges":
            int(
                directed
            ),

        "CORE":
            int(
                core
            ),

        "LOCAL":
            int(
                local
            ),

        "code0_rows_materialized":
            int(
                suppressed
            ),
    }


def read_b4_counts(
    path: Path,
):

    con = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )

    try:

        relations = con.execute(
            """
            SELECT COUNT(*)
            FROM relation_compile_summary
            """
        ).fetchone()[0]

        sequences = con.execute(
            """
            SELECT COUNT(*)
            FROM restriction_sequences
            """
        ).fetchone()[0]

        sequence_edges = con.execute(
            """
            SELECT COUNT(*)
            FROM restriction_sequence_edges
            """
        ).fetchone()[0]

        core_sequences = con.execute(
            """
            SELECT COUNT(*)
            FROM restriction_sequences
            WHERE core_only = 1
            """
        ).fetchone()[0]

    finally:

        con.close()


    return {
        "relations":
            int(
                relations
            ),

        "sequences":
            int(
                sequences
            ),

        "sequence_edges":
            int(
                sequence_edges
            ),

        "core_sequences":
            int(
                core_sequences
            ),
    }


# =============================================================================
# PREFLIGHT
# =============================================================================

print(SEP)
print(
    "FASE 5.6 — E4 — FINAL FREEZE G_OSM_operativo_v01"
)
print(SEP)


required = [

    (PBF, "Frozen PBF"),

    (B1, "B1"),

    (B2, "B2"),

    (B3, "B3"),

    (B4, "B4"),

    (B5_INDEX, "B5 index"),

    (B5_TIME, "B5 time"),

    (B5_LENGTH, "B5 length"),

    (B5_EDGEID, "B5 edgeid"),

    (B5_BASE, "B5 base nodes"),

    (B5_STATE_NODE, "B5 state node"),

    (F1_MOVEMENTS, "F1 movements"),

    (F1_SUMMARY, "F1 summary"),

    (F1_MANIFEST, "F1 manifest"),

    (F2_SAMPLES, "F2 samples"),

    (F2_DETAIL, "F2 detail"),

    (F2_MANIFEST, "F2 manifest"),

    (F3_PAIR, "F3 access pairs"),

    (F3_OD, "F3 OD audit"),

    (F3_EXTREMES, "F3 extremes"),

    (F3_SUMMARY, "F3 summary"),

    (GAMMA_GPKG, "Gamma frozen GPKG"),

    (GAMMA_CSV, "Gamma frozen CSV"),

    (GAMMA_MANIFEST, "Gamma frozen manifest"),
]


for path, label in required:

    require_file(
        path,
        label,
    )


if FINAL_DIR.exists():

    raise RuntimeError(
        "Package canonico già esistente. "
        f"NON sovrascrivo: {FINAL_DIR}"
    )


if STAGE_DIR.exists():

    raise RuntimeError(
        f"Staging già esistente: {STAGE_DIR}"
    )


STAGE_DIR.mkdir(
    parents=True,
    exist_ok=False,
)


print()
print("A. PREFLIGHT")
print(SUB)

print(
    f"Final package : {FINAL_DIR}"
)

print(
    f"Staging       : {STAGE_DIR}"
)

print(
    "Overwrite     : FORBIDDEN"
)


# =============================================================================
# VERIFY FROZEN SOURCE IDENTITIES
# =============================================================================

print()
print("B. SOURCE IDENTITY")
print(SUB)


pbf_hash = sha256_file(
    PBF
)


print(
    f"PBF SHA256    : {pbf_hash}"
)


if (
    pbf_hash
    != EXPECTED_PBF_SHA256
):

    raise RuntimeError(
        "Frozen PBF SHA256 mismatch."
    )


gamma_gpkg_hash = sha256_file(
    GAMMA_GPKG
)

gamma_csv_hash = sha256_file(
    GAMMA_CSV
)

gamma_manifest_hash = sha256_file(
    GAMMA_MANIFEST
)


print(
    f"Gamma GPKG    : {gamma_gpkg_hash}"
)

print(
    f"Gamma CSV     : {gamma_csv_hash}"
)

print(
    f"Gamma manifest: {gamma_manifest_hash}"
)


if (
    gamma_gpkg_hash
    != EXPECTED_GAMMA_GPKG_SHA256
):

    raise RuntimeError(
        "Gamma GPKG frozen hash mismatch."
    )


if (
    gamma_csv_hash
    != EXPECTED_GAMMA_CSV_SHA256
):

    raise RuntimeError(
        "Gamma CSV frozen hash mismatch."
    )


if (
    gamma_manifest_hash
    != EXPECTED_GAMMA_MANIFEST_SHA256
):

    raise RuntimeError(
        "Gamma manifest frozen hash mismatch."
    )


# =============================================================================
# VERIFY FINAL GATES
# =============================================================================

print()
print("C. VERIFY FINAL GATES")
print(SUB)


f1 = json_load(
    F1_MANIFEST
)

f2 = json_load(
    F2_MANIFEST
)

f3 = json_load(
    F3_SUMMARY
)


f1_status = (
    f1.get(
        "overall_status"
    )
)

f2_status = (
    f2.get(
        "status"
    )
)

f3_status = (
    f3.get(
        "status"
    )
)


print(
    f"F1 : {f1_status}"
)

print(
    f"F2 : {f2_status}"
)

print(
    f"F3 : {f3_status}"
)


if (
    f1_status
    != "PASS"
):

    raise RuntimeError(
        f"F1 non PASS: {f1_status}"
    )


if (
    f2_status
    != "PASS"
):

    raise RuntimeError(
        f"F2 non PASS: {f2_status}"
    )


if (
    f3_status
    != "PASS_NO_SYSTEMIC_SIGNAL"
):

    raise RuntimeError(
        f"F3 non PASS: {f3_status}"
    )


f3_counts = f3.get(
    "counts",
    {}
)

f3_flags = f3.get(
    "systemic_flags",
    {}
)


if int(
    f3_counts.get(
        "N_unreachable",
        -1,
    )
) != 0:

    raise RuntimeError(
        "F3 contiene OD unreachable."
    )


if any(
    bool(
        value
    )
    for value
    in f3_flags.values()
):

    raise RuntimeError(
        f"F3 contiene systemic flag: {f3_flags}"
    )


print(
    "F1/F2/F3 gate verification: PASS"
)


# =============================================================================
# VERIFY CORE BUILD CARDINALITIES
# =============================================================================

print()
print("D. BUILD CARDINALITIES")
print(SUB)


b2_counts = read_b2_counts(
    B2
)

b4_counts = read_b4_counts(
    B4
)


print(
    f"B2 nodes          : "
    f"{b2_counts['nodes']:,}"
)

print(
    f"B2 segments       : "
    f"{b2_counts['segments']:,}"
)

print(
    f"B2 directed edges : "
    f"{b2_counts['directed_edges']:,}"
)

print(
    f"B2 CORE           : "
    f"{b2_counts['CORE']:,}"
)

print(
    f"B2 LOCAL          : "
    f"{b2_counts['LOCAL']:,}"
)

print(
    f"B4 relations      : "
    f"{b4_counts['relations']:,}"
)

print(
    f"B4 sequences      : "
    f"{b4_counts['sequences']:,}"
)

print(
    f"B4 CORE sequences : "
    f"{b4_counts['core_sequences']:,}"
)


if (
    b2_counts[
        "nodes"
    ]
    != 912_562
):

    raise RuntimeError(
        "B2 node cardinality mismatch."
    )


if (
    b2_counts[
        "segments"
    ]
    != 944_219
):

    raise RuntimeError(
        "B2 segment cardinality mismatch."
    )


if (
    b2_counts[
        "directed_edges"
    ]
    != 1_698_857
):

    raise RuntimeError(
        "B2 directed-edge cardinality mismatch."
    )


if (
    b2_counts[
        "CORE"
    ]
    != 1_691_766
):

    raise RuntimeError(
        "B2 CORE cardinality mismatch."
    )


if (
    b2_counts[
        "LOCAL"
    ]
    != 7_091
):

    raise RuntimeError(
        "B2 LOCAL cardinality mismatch."
    )


if (
    b4_counts[
        "relations"
    ]
    != 6_876
):

    raise RuntimeError(
        "B4 relation cardinality mismatch."
    )


if (
    b4_counts[
        "sequences"
    ]
    != 6_833
):

    raise RuntimeError(
        "B4 sequence cardinality mismatch."
    )


# =============================================================================
# VERIFY B5
# =============================================================================

print()
print("E. VERIFY B5")
print(SUB)


TIME = load_npz(
    B5_TIME
).tocsr()

LENGTH = load_npz(
    B5_LENGTH
).tocsr()

EDGEID = load_npz(
    B5_EDGEID
).tocsr()

BASE = np.load(
    B5_BASE,
    allow_pickle=False,
)

STATE_NODE = np.load(
    B5_STATE_NODE,
    allow_pickle=False,
)


if not (
    TIME.shape
    == LENGTH.shape
    == EDGEID.shape
):

    raise RuntimeError(
        "B5 matrix shape mismatch."
    )


if not (
    TIME.nnz
    == LENGTH.nnz
    == EDGEID.nnz
):

    raise RuntimeError(
        "B5 matrix nnz mismatch."
    )


if TIME.shape != (
    904_607,
    904_607,
):

    raise RuntimeError(
        f"B5 state shape inattesa: {TIME.shape}"
    )


if (
    TIME.nnz
    != 1_699_994
):

    raise RuntimeError(
        "B5 transition count mismatch."
    )


if len(
    BASE
) != 897_857:

    raise RuntimeError(
        "B5 base-state count mismatch."
    )


if len(
    STATE_NODE
) != 904_607:

    raise RuntimeError(
        "B5 state-node count mismatch."
    )


print(
    f"B5 states      : {TIME.shape[0]:,}"
)

print(
    f"B5 base states : {len(BASE):,}"
)

print(
    f"B5 transitions : {TIME.nnz:,}"
)

print(
    "B5 verification: PASS"
)


# =============================================================================
# BUILD SPATIAL GPKG
# =============================================================================

print()
print("F. MATERIALIZE G_OSM_operativo_v01.gpkg")
print(SUB)


GPKG = (
    STAGE_DIR
    / FINAL_GPKG_NAME
)


# Il GPKG contiene i segmenti fisici OSM consecutivi.
# Le regole routing complete restano negli artefatti B2/B4/B5.

con = sqlite3.connect(
    f"file:{B2}?mode=ro",
    uri=True,
)


query = """
SELECT

    s.segment_uid,
    s.way_id,
    s.seq,
    s.osm_u,
    s.osm_v,
    s.length_m,
    s.highway,
    s.name,
    s.ref,
    s.oneway_raw,
    s.junction_raw,
    s.bridge_raw,
    s.tunnel_raw,
    s.layer_raw,
    s.access_raw,
    s.vehicle_raw,
    s.motor_vehicle_raw,
    s.motorcar_raw,
    s.direction_status,
    s.direction_code,
    s.access_conditional_flag,
    s.direction_conditional_flag,
    s.speed_conditional_flag,

    nu.lon AS u_lon,
    nu.lat AS u_lat,

    nv.lon AS v_lon,
    nv.lat AS v_lat

FROM segments AS s

JOIN nodes AS nu
  ON nu.node_id = s.osm_u

JOIN nodes AS nv
  ON nv.node_id = s.osm_v

ORDER BY
    s.way_id,
    s.seq
"""


transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32632",
    always_xy=True,
)


written = 0

chunk_size = 100_000


for chunk_number, chunk in enumerate(

    pd.read_sql_query(
        query,
        con,
        chunksize=chunk_size,
    ),

    start=1,
):

    required_coords = [
        "u_lon",
        "u_lat",
        "v_lon",
        "v_lat",
    ]


    if (
        chunk[
            required_coords
        ]
        .isna()
        .any()
        .any()
    ):

        raise RuntimeError(
            "Coordinate NULL durante materializzazione GPKG."
        )


    u_lon = chunk[
        "u_lon"
    ].to_numpy(
        dtype=float
    )

    u_lat = chunk[
        "u_lat"
    ].to_numpy(
        dtype=float
    )

    v_lon = chunk[
        "v_lon"
    ].to_numpy(
        dtype=float
    )

    v_lat = chunk[
        "v_lat"
    ].to_numpy(
        dtype=float
    )


    ux, uy = transformer.transform(
        u_lon,
        u_lat,
    )

    vx, vy = transformer.transform(
        v_lon,
        v_lat,
    )


    n = len(
        chunk
    )


    coords = np.empty(
        (
            n * 2,
            2,
        ),
        dtype=np.float64,
    )


    coords[
        0::2,
        0
    ] = ux

    coords[
        0::2,
        1
    ] = uy

    coords[
        1::2,
        0
    ] = vx

    coords[
        1::2,
        1
    ] = vy


    indices = np.repeat(
        np.arange(
            n,
            dtype=np.intp,
        ),
        2,
    )


    geometry = shapely.linestrings(
        coords,
        indices=indices,
    )


    attrs = chunk.drop(
        columns=required_coords
    )


    gdf = gpd.GeoDataFrame(
        attrs,
        geometry=geometry,
        crs="EPSG:32632",
    )


    pyogrio.write_dataframe(

        gdf,

        GPKG,

        layer=GPKG_LAYER,

        driver="GPKG",

        append=(
            chunk_number
            > 1
        ),
    )


    written += n


    print(
        f"  chunk "
        f"{chunk_number:>2} "
        f"| written="
        f"{written:,}/"
        f"{b2_counts['segments']:,}"
    )


con.close()


if (
    written
    != b2_counts[
        "segments"
    ]
):

    raise RuntimeError(
        f"GPKG segment count="
        f"{written:,}, "
        f"atteso "
        f"{b2_counts['segments']:,}"
    )


# =============================================================================
# GPKG METADATA
# =============================================================================

gcon = sqlite3.connect(
    GPKG
)


try:

    actual_layer_count = gcon.execute(
        f"""
        SELECT COUNT(*)
        FROM {qident(GPKG_LAYER)}
        """
    ).fetchone()[0]


    if (
        actual_layer_count
        != 944_219
    ):

        raise RuntimeError(
            "GPKG layer cardinality mismatch."
        )


    existing = gcon.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (
            GPKG_METADATA_TABLE,
        ),
    ).fetchone()


    if existing is not None:

        raise RuntimeError(
            "Metadata table GPKG già esistente."
        )


    gcon.execute(
        f"""
        CREATE TABLE {qident(GPKG_METADATA_TABLE)}
        (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


    metadata_rows = [

        (
            "artifact",
            "G_OSM_operativo",
        ),

        (
            "version",
            "v01",
        ),

        (
            "status",
            "FROZEN",
        ),

        (
            "freeze_phase",
            "FASE_5.6_E4",
        ),

        (
            "routing_backend",
            "B5_selective_state_expanded_turn_aware",
        ),

        (
            "spatial_layer_role",
            (
                "physical OSM segments for GIS/reference; "
                "canonical routing behavior is B5"
            ),
        ),

        (
            "crs",
            "EPSG:32632",
        ),

        (
            "frozen_pbf",
            str(
                PBF
            ),
        ),

        (
            "frozen_pbf_sha256",
            pbf_hash,
        ),

        (
            "Gamma_OSM_status",
            "FROZEN",
        ),

        (
            "Gamma_OSM_manifest",
            str(
                GAMMA_MANIFEST
            ),
        ),

        (
            "F1",
            "PASS",
        ),

        (
            "F2",
            "PASS",
        ),

        (
            "F3",
            "PASS_NO_SYSTEMIC_SIGNAL",
        ),

        (
            "network_audit_status",
            "STOP_AFTER_FREEZE",
        ),
    ]


    gcon.executemany(
        f"""
        INSERT INTO {qident(GPKG_METADATA_TABLE)}
        (key, value)
        VALUES (?, ?)
        """,
        metadata_rows,
    )


    gcon.commit()


finally:

    gcon.close()


gpkg_hash = sha256_file(
    GPKG
)


print()
print(
    f"GPKG features : {written:,}"
)

print(
    f"GPKG SHA256   : {gpkg_hash}"
)


# =============================================================================
# COPY COMPUTATIONAL BACKBONE
# =============================================================================

print()
print("G. COPY CANONICAL COMPUTATIONAL ARTIFACTS")
print(SUB)


computational_sources = [

    B1,

    B2,

    B3,

    B4,

    B5_INDEX,

    B5_TIME,

    B5_LENGTH,

    B5_EDGEID,

    B5_BASE,

    B5_STATE_NODE,
]


canonical_artifacts = []


for src in computational_sources:

    canonical_artifacts.append(
        copy_verified(
            src,
            STAGE_DIR,
        )
    )


# =============================================================================
# COPY FINAL-GATE EVIDENCE
# =============================================================================

print()
print("H. COPY FINAL-GATE EVIDENCE")
print(SUB)


gate_sources = [

    F1_MOVEMENTS,

    F1_SUMMARY,

    F1_MANIFEST,

    F2_SAMPLES,

    F2_DETAIL,

    F2_MANIFEST,

    F3_PAIR,

    F3_OD,

    F3_EXTREMES,

    F3_SUMMARY,

    GAMMA_MANIFEST,
]


gate_artifacts = []


for src in gate_sources:

    gate_artifacts.append(
        copy_verified(
            src,
            STAGE_DIR,
        )
    )


# =============================================================================
# README
# =============================================================================

README = (
    STAGE_DIR
    / README_NAME
)


readme_text = f"""
G_OSM_operativo_v01
===================

STATUS
------
FROZEN

Frozen OSM snapshot:
{PBF}

SHA256:
{pbf_hash}

ROUTING CANONICO
----------------
Il routing canonico NON è il solo layer GeoPackage.

Il backend operativo è:

B2 directed graph
+
B4 compiled OSM turn restrictions
+
B5 selective state-expanded turn-aware graph.

Artefatti runtime principali:

- osm_directed_edges_v02.sqlite
- osm_turn_restrictions_compiled_v01.sqlite
- osm_turn_state_index_v01.sqlite
- osm_turn_state_time_v01.npz
- osm_turn_state_length_v01.npz
- osm_turn_state_edgeid_v01.npz
- osm_turn_state_base_nodes_v01.npy
- osm_turn_state_node_id_v01.npy

GPKG
----
{FINAL_GPKG_NAME}

Layer:
{GPKG_LAYER}

Il GPKG materializza i segmenti fisici OSM in EPSG:32632
per uso GIS, ispezione e tracciabilità.

NON deve essere utilizzato in sostituzione del B5 quando
sono richieste le turn restrictions.

FINAL FUNCTIONAL GATE
---------------------
F1 = PASS
F2 = PASS
F3 = PASS_NO_SYSTEMIC_SIGNAL

Gamma_OSM = FROZEN
EXP_REL_300 = FROZEN

NETWORK AUDIT
-------------
STOP dopo il freeze.

La rete si riapre soltanto in presenza di un errore downstream
dimostrato BLOCKING.
""".strip()


README.write_text(
    readme_text,
    encoding="utf-8",
)


# =============================================================================
# FINAL MANIFEST
# =============================================================================

print()
print("I. FINAL MANIFEST")
print(SUB)


f3_ratio = f3.get(
    "ratio_distribution",
    {}
)

f3_errors = f3.get(
    "errors_km",
    {}
)

f3_anomalies = f3.get(
    "anomaly_classes",
    {}
)


manifest = {

    "artifact":
        "G_OSM_operativo",

    "version":
        "v01",

    "status":
        "FROZEN",

    "phase":
        "5.6",

    "freeze_gate":
        "E4",

    "canonical_directory":
        str(
            FINAL_DIR
        ),

    "frozen_source":
        {

            "PBF":
                str(
                    PBF
                ),

            "PBF_sha256":
                pbf_hash,
        },

    "routing_contract":
        {

            "graph":
                "directed OSM light automobile graph",

            "turn_model":
                "B5 selective state-expanded turn-aware",

            "source_semantics":
                "physical node base-state",

            "destination_semantics":
                (
                    "minimum over all B5 states "
                    "sharing target physical node"
                ),

            "ordinary_routing":
                "routing_code=1 CORE",

            "local_restricted":
                (
                    "routing_code=2; excluded from "
                    "ordinary through-routing/B5 CORE"
                ),
        },

    "structural_metrics":
        {

            "B1_unique_OSM_ways":
                112_209,

            "B1_distinct_nodes":
                914_333,

            "B2_physical_nodes":
                b2_counts[
                    "nodes"
                ],

            "B2_segments":
                b2_counts[
                    "segments"
                ],

            "B2_directed_edges":
                b2_counts[
                    "directed_edges"
                ],

            "B2_CORE_edges":
                b2_counts[
                    "CORE"
                ],

            "B2_LOCAL_edges":
                b2_counts[
                    "LOCAL"
                ],

            "B3_giant_SCC_nodes":
                889_440,

            "B4_canonical_relations":
                b4_counts[
                    "relations"
                ],

            "B4_sequences":
                b4_counts[
                    "sequences"
                ],

            "B5_base_states":
                int(
                    len(
                        BASE
                    )
                ),

            "B5_total_states":
                int(
                    len(
                        STATE_NODE
                    )
                ),

            "B5_transitions":
                int(
                    TIME.nnz
                ),
        },

    "final_gate":
        {

            "F1":
                {

                    "status":
                        "PASS",

                    "sites":
                        4,

                    "technical_failures":
                        0,

                    "B5_regressions":
                        0,
                },

            "F2":
                {

                    "status":
                        "PASS",

                    "way_semantic_samples":
                        6,

                    "turn_restriction_samples":
                        4,

                    "pipeline_discordances":
                        0,
                },

            "F3":
                {

                    "status":
                        "PASS_NO_SYSTEMIC_SIGNAL",

                    "N_OD":
                        int(
                            f3_counts[
                                "N_OD"
                            ]
                        ),

                    "N_finite":
                        int(
                            f3_counts[
                                "N_finite"
                            ]
                        ),

                    "N_unreachable":
                        int(
                            f3_counts[
                                "N_unreachable"
                            ]
                        ),

                    "ratio_median":
                        float(
                            f3_ratio[
                                "median"
                            ]
                        ),

                    "ratio_p95":
                        float(
                            f3_ratio[
                                "p95"
                            ]
                        ),

                    "MAE_km":
                        float(
                            f3_errors[
                                "MAE"
                            ]
                        ),

                    "median_absolute_error_km":
                        float(
                            f3_errors[
                                "median_absolute_error"
                            ]
                        ),

                    "p95_absolute_error_km":
                        float(
                            f3_errors[
                                "p95_absolute_error"
                            ]
                        ),

                    "systemic_flags":
                        f3_flags,

                    "anomaly_classes":
                        f3_anomalies,
                },
        },

    "Gamma_OSM_reference":
        {

            "status":
                "FROZEN",

            "EXP_REL_300":
                "FROZEN",

            "GPKG":
                str(
                    GAMMA_GPKG
                ),

            "GPKG_sha256":
                gamma_gpkg_hash,

            "CSV":
                str(
                    GAMMA_CSV
                ),

            "CSV_sha256":
                gamma_csv_hash,

            "manifest":
                str(
                    GAMMA_MANIFEST
                ),

            "manifest_sha256":
                gamma_manifest_hash,
        },

    "spatial_artifact":
        {

            "filename":
                FINAL_GPKG_NAME,

            "canonical_path":
                str(
                    FINAL_DIR
                    / FINAL_GPKG_NAME
                ),

            "layer":
                GPKG_LAYER,

            "CRS":
                "EPSG:32632",

            "features":
                int(
                    written
                ),

            "sha256":
                gpkg_hash,

            "role":
                (
                    "GIS/reference representation of "
                    "physical OSM segments"
                ),
        },

    "computational_artifacts":
        canonical_artifacts,

    "gate_evidence":
        gate_artifacts,

    "freeze_rule":
        {

            "network_audit":
                "STOP",

            "reopen_only_if":
                (
                    "downstream error demonstrated "
                    "BLOCKING"
                ),

            "next_phase":
                (
                    "impedenze/costi definitivi -> "
                    "shortest path OD -> gateway/rete esterna -> "
                    "seed matrix -> assignment -> ANAS -> "
                    "calibration -> path flows -> FRLM"
                ),
        },

    "elapsed_seconds_before_manifest":
        float(
            time.perf_counter()
            - START
        ),
}


MANIFEST = (
    STAGE_DIR
    / FINAL_MANIFEST_NAME
)


MANIFEST.write_text(

    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),

    encoding="utf-8",
)


manifest_hash = sha256_file(
    MANIFEST
)


MANIFEST_SHA = (
    STAGE_DIR
    / FINAL_MANIFEST_SHA_NAME
)


MANIFEST_SHA.write_text(

    f"{manifest_hash}  {FINAL_MANIFEST_NAME}\n",

    encoding="ascii",
)


print(
    f"Final manifest SHA256 : {manifest_hash}"
)


# =============================================================================
# FINAL REPORT FILE
# =============================================================================

REPORT = (
    STAGE_DIR
    / FINAL_REPORT_NAME
)


report_text = f"""
G_OSM_FINAL_GATE_REPORT

======================================================================
VERDETTO
======================================================================

F1 shadow regression                  = PASS
F2 build fidelity                     = PASS
F3 regional metric audit              = PASS_NO_SYSTEMIC_SIGNAL

Gamma_OSM                             = FROZEN
EXP_REL_300                           = FROZEN

SYSTEMIC_CONNECTIVITY_ERROR           = NO
SYSTEMIC_DISTANCE_INFLATION           = NO
SYSTEMIC_ROUTING_BIAS                 = NO

SYSTEMIC issues                       = 0
BLOCKING issues                       = 0

G_OSM_operativo                       = FROZEN

======================================================================
BACKBONE
======================================================================

Version                                = G_OSM_operativo_v01
Frozen PBF                             = nord-est_2026-08-03.osm.pbf
PBF SHA256                             = {pbf_hash}

B2 physical nodes                      = {b2_counts['nodes']:,}
B2 segments                            = {b2_counts['segments']:,}
B2 directed edges                      = {b2_counts['directed_edges']:,}
B2 CORE edges                          = {b2_counts['CORE']:,}
B2 LOCAL edges                         = {b2_counts['LOCAL']:,}

B3 giant SCC nodes                     = 889,440

B4 canonical relations                 = {b4_counts['relations']:,}
B4 compiled sequences                  = {b4_counts['sequences']:,}

B5 base states                         = {len(BASE):,}
B5 total states                        = {len(STATE_NODE):,}
B5 transitions                         = {TIME.nnz:,}

======================================================================
F1
======================================================================

Sites                                  = 4
Technical failures                     = 0
B5 regressions                         = 0

SHADOW-01                              = PASS
SHADOW-02                              = PASS/PASS
SHADOW-03                              = PASS/PASS
SHADOW-04B                             = PASS/PASS

F1                                     = PASS

======================================================================
F2
======================================================================

Way-semantic samples                   = 6
Turn-restriction samples               = 4
Total samples                          = 10
Pipeline discordances                  = 0

F2                                     = PASS

======================================================================
F3
======================================================================

N_OD                                   = {int(f3_counts['N_OD']):,}
N_finite                               = {int(f3_counts['N_finite']):,}
N_unreachable                          = {int(f3_counts['N_unreachable']):,}

Median D_OSM_TIME / KM_TOT             = {float(f3_ratio['median']):.6f}
p95 D_OSM_TIME / KM_TOT                = {float(f3_ratio['p95']):.6f}

MAE                                    = {float(f3_errors['MAE']):.4f} km
Median absolute error                  = {float(f3_errors['median_absolute_error']):.4f} km
p95 absolute error                     = {float(f3_errors['p95_absolute_error']):.4f} km

POSSIBLE_SYSTEMIC                      = {int(f3_anomalies.get('POSSIBLE_SYSTEMIC', 0))}
UNRESOLVED                             = {int(f3_anomalies.get('UNRESOLVED', 0))}

F3                                     = PASS_NO_SYSTEMIC_SIGNAL

======================================================================
GAMMA REFERENCE
======================================================================

Gamma_OSM                              = FROZEN
EXP_REL_300                            = FROZEN

Gamma GPKG SHA256:
{gamma_gpkg_hash}

Gamma FINAL manifest SHA256:
{gamma_manifest_hash}

======================================================================
CANONICAL PACKAGE
======================================================================

{FINAL_DIR}

Spatial artifact:
{FINAL_GPKG_NAME}

GPKG SHA256:
{gpkg_hash}

Final manifest:
{FINAL_MANIFEST_NAME}

Final manifest SHA256:
{manifest_hash}

======================================================================
FREEZE RULE
======================================================================

G_OSM_operativo = FROZEN

STOP NETWORK AUDIT.

NON riaprire:
- audit GSFVG;
- Gamma sensitivity;
- directional sampling;
- shadow review;
- metric audit;
- structural build B1-B5.

Riapertura consentita esclusivamente in presenza di errore downstream
dimostrato BLOCKING.

NEXT:
impedenze/costi definitivi -> shortest path OD -> gateway/rete esterna ->
seed matrix -> assignment -> ANAS -> calibrazione -> path flows -> FRLM.
""".strip()


REPORT.write_text(
    report_text,
    encoding="utf-8",
)


# =============================================================================
# FINAL STAGING VALIDATION
# =============================================================================

print()
print("J. FINAL STAGING VALIDATION")
print(SUB)


must_exist = [

    GPKG,

    MANIFEST,

    MANIFEST_SHA,

    REPORT,

    README,

]


for path in must_exist:

    if not path.is_file():

        raise RuntimeError(
            f"Final staging file missing: {path}"
        )


print(
    f"GPKG SHA256     : {gpkg_hash}"
)

print(
    f"Manifest SHA256 : {manifest_hash}"
)

print(
    "Staging validation: PASS"
)


# =============================================================================
# ATOMIC PROMOTION
# =============================================================================

print()
print("K. PROMOTION")
print(SUB)


if FINAL_DIR.exists():

    raise RuntimeError(
        f"Final package appeared during run: {FINAL_DIR}"
    )


STAGE_DIR.rename(
    FINAL_DIR
)


print(
    f"PROMOTED: {FINAL_DIR}"
)


# =============================================================================
# FINAL
# =============================================================================

elapsed = (
    time.perf_counter()
    - START
)


print()
print(SEP)
print("ESITO E4: PASS")
print("G_OSM_operativo = FROZEN")
print("NETWORK AUDIT = STOP")
print(SEP)

print(
    f"Package  : {FINAL_DIR}"
)

print(
    f"GPKG     : "
    f"{FINAL_DIR / FINAL_GPKG_NAME}"
)

print(
    f"Manifest : "
    f"{FINAL_DIR / FINAL_MANIFEST_NAME}"
)

print(
    f"Report   : "
    f"{FINAL_DIR / FINAL_REPORT_NAME}"
)

print(
    f"GPKG SHA256     : {gpkg_hash}"
)

print(
    f"Manifest SHA256 : {manifest_hash}"
)

print(
    f"Elapsed         : {elapsed:.2f} s"
)

print(
    "=== RUN COMPLETATA ==="
)
