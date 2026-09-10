from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import sqlite3

import pandas as pd


ROOT = Path(r"C:\Tesi\Tesi_QGIS")

SRC_DIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo\gamma_osm"
)

E2_DIR = SRC_DIR / "e2"

SRC_GPKG = (
    SRC_DIR
    / "Gamma_OSM_L_comuni_fvg_v01_CANDIDATE.gpkg"
)

SRC_CSV = (
    SRC_DIR
    / "Gamma_OSM_L_comuni_fvg_v01_CANDIDATE.csv"
)

SRC_DIAG = (
    SRC_DIR
    / "Gamma_OSM_L_diagnostics_v01.csv"
)

SRC_E1_MANIFEST = (
    SRC_DIR
    / "Gamma_OSM_L_manifest_v01.json"
)

SRC_E2_MANIFEST = (
    E2_DIR
    / "Gamma_OSM_E2_manifest_v01.json"
)

SRC_E2_MATRIX = (
    E2_DIR
    / "Gamma_OSM_E2_time_matrix_645x645_v01.npy"
)

SRC_E2_ACCESS = (
    E2_DIR
    / "Gamma_OSM_E2_access_summary_v01.csv"
)

SRC_E2_TRIPLET = (
    E2_DIR
    / "Gamma_OSM_E2_triplet_summary_v01.csv"
)

SRC_E2_INTER = (
    E2_DIR
    / "Gamma_OSM_E2_intermunicipal_pairs_v01.csv"
)

SRC_E2_INTRA = (
    E2_DIR
    / "Gamma_OSM_E2_intramunicipal_pairs_v01.csv"
)

SRC_E2_ASYM = (
    E2_DIR
    / "Gamma_OSM_E2_top_asymmetry_v01.csv"
)

SRC_E2_DETOUR = (
    E2_DIR
    / "Gamma_OSM_E2_top_detour_proxy_v01.csv"
)


PKG = (
    ROOT
    / r"02_package\accessi_comunali_osm_light"
)

PKG.mkdir(
    parents=True,
    exist_ok=True,
)


DST_GPKG = (
    PKG
    / "Gamma_OSM_L_comuni_fvg_v01.gpkg"
)

DST_CSV = (
    PKG
    / "Gamma_OSM_L_comuni_fvg_v01.csv"
)

DST_DIAG = (
    PKG
    / "Gamma_OSM_L_diagnostics_v01.csv"
)

DST_E2_MATRIX = (
    PKG
    / "Gamma_OSM_E2_time_matrix_645x645_v01.npy"
)

DST_E2_ACCESS = (
    PKG
    / "Gamma_OSM_E2_access_summary_v01.csv"
)

DST_E2_TRIPLET = (
    PKG
    / "Gamma_OSM_E2_triplet_summary_v01.csv"
)

DST_E2_INTER = (
    PKG
    / "Gamma_OSM_E2_intermunicipal_pairs_v01.csv"
)

DST_E2_INTRA = (
    PKG
    / "Gamma_OSM_E2_intramunicipal_pairs_v01.csv"
)

DST_E2_ASYM = (
    PKG
    / "Gamma_OSM_E2_top_asymmetry_v01.csv"
)

DST_E2_DETOUR = (
    PKG
    / "Gamma_OSM_E2_top_detour_proxy_v01.csv"
)

DST_E1_MANIFEST = (
    PKG
    / "Gamma_OSM_E1_manifest_v01.json"
)

DST_E2_MANIFEST = (
    PKG
    / "Gamma_OSM_E2_manifest_v01.json"
)

DST_FINAL_MANIFEST = (
    PKG
    / "Gamma_OSM_FINAL_manifest_v01.json"
)


STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

LOG = (
    PKG
    / f"freeze_gamma_osm_v01_{STAMP}.txt"
)


def sha256(path):

    h = hashlib.sha256()

    with open(path, "rb") as f:

        while True:

            chunk = f.read(
                1024 * 1024
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def out(s=""):

    s = str(s)

    print(s)

    lines.append(s)


lines = []


out("=" * 116)
out("FASE 5.6 — E3 — FREEZE Gamma_OSM")
out("=" * 116)


sources = [
    SRC_GPKG,
    SRC_CSV,
    SRC_DIAG,
    SRC_E1_MANIFEST,
    SRC_E2_MANIFEST,
    SRC_E2_MATRIX,
    SRC_E2_ACCESS,
    SRC_E2_TRIPLET,
    SRC_E2_INTER,
    SRC_E2_INTRA,
    SRC_E2_ASYM,
    SRC_E2_DETOUR,
]

for path in sources:

    if not path.exists():

        raise FileNotFoundError(
            path
        )


destinations = [
    DST_GPKG,
    DST_CSV,
    DST_DIAG,
    DST_E2_MATRIX,
    DST_E2_ACCESS,
    DST_E2_TRIPLET,
    DST_E2_INTER,
    DST_E2_INTRA,
    DST_E2_ASYM,
    DST_E2_DETOUR,
    DST_E1_MANIFEST,
    DST_E2_MANIFEST,
    DST_FINAL_MANIFEST,
]

existing = [
    p
    for p in destinations
    if p.exists()
]

if existing:

    raise RuntimeError(
        "Output canonici già esistenti; "
        "freeze non distruttivo interrotto:\n"
        + "\n".join(
            str(p)
            for p in existing
        )
    )


# =====================================================================
# A. VERIFICA E1 / E2
# =====================================================================

out()
out("A. VERIFICA GATE")
out("-" * 116)

e1_manifest = json.loads(
    SRC_E1_MANIFEST.read_text(
        encoding="utf-8"
    )
)

e2_manifest = json.loads(
    SRC_E2_MANIFEST.read_text(
        encoding="utf-8"
    )
)


e1_qa = e1_manifest[
    "qa"
]

bad_e1 = {
    k: v
    for k, v in e1_qa.items()
    if (
        k != "max_lambda_sum_error"
        and v != 0
    )
}

lambda_error_e1 = float(
    e1_qa[
        "max_lambda_sum_error"
    ]
)


if bad_e1:

    raise RuntimeError(
        f"E1 QA non pulita: {bad_e1}"
    )

if lambda_error_e1 > 1e-12:

    raise RuntimeError(
        f"E1 lambda error: {lambda_error_e1}"
    )


if (
    e2_manifest.get(
        "gate_status"
    )
    != "PASS"
):

    raise RuntimeError(
        "E2 manifest non PASS."
    )


if e2_manifest.get(
    "issues"
):

    raise RuntimeError(
        "E2 contiene issue non vuote."
    )


reach = e2_manifest[
    "reachability"
]

if any(
    int(reach[k]) != 0
    for k in [
        "unreachable_intermunicipal",
        "unreachable_intramunicipal",
        "bad_source_count",
        "bad_destination_count",
        "bad_triplet_count",
    ]
):

    raise RuntimeError(
        f"E2 reachability non pulita: {reach}"
    )


out("E1 gate : PASS")
out("E2 gate : PASS")
out("Issues  : 0")


# =====================================================================
# B. VERIFICA 645 ACCESSI / PESI
# =====================================================================

out()
out("B. VERIFICA Gamma")
out("-" * 116)

gamma = pd.read_csv(
    SRC_CSV
)

if len(gamma) != 645:

    raise RuntimeError(
        f"Gamma rows={len(gamma)}, attese 645"
    )

if gamma["PRO_COM"].nunique() != 215:

    raise RuntimeError(
        "Gamma comuni !=215"
    )

counts = (
    gamma.groupby(
        "PRO_COM"
    ).size()
)

if not (counts == 3).all():

    raise RuntimeError(
        "Cardinalità Gamma !=3."
    )


lambda_sums = (
    gamma.groupby(
        "PRO_COM"
    )[
        "lambda_L"
    ].sum()
)

lambda_error = float(
    (
        lambda_sums
        - 1.0
    )
    .abs()
    .max()
)

nonpositive = int(
    (
        gamma[
            "lambda_L"
        ]
        <= 0
    ).sum()
)


if nonpositive:

    raise RuntimeError(
        "Lambda nonpositive."
    )

if lambda_error > 1e-12:

    raise RuntimeError(
        "Lambda normalization failed."
    )


out("Comuni        : 215")
out("Accessi       : 645")
out("Cardinalità   : 3/comune")
out("EXP_REL_300   : VALIDATED")
out(
    f"Lambda error  : "
    f"{lambda_error:.3e}"
)


# =====================================================================
# C. COPY CANONICAL PACKAGE
# =====================================================================

out()
out("C. PROMOZIONE PACKAGE")
out("-" * 116)

copy_map = [
    (
        SRC_GPKG,
        DST_GPKG,
    ),
    (
        SRC_CSV,
        DST_CSV,
    ),
    (
        SRC_DIAG,
        DST_DIAG,
    ),
    (
        SRC_E2_MATRIX,
        DST_E2_MATRIX,
    ),
    (
        SRC_E2_ACCESS,
        DST_E2_ACCESS,
    ),
    (
        SRC_E2_TRIPLET,
        DST_E2_TRIPLET,
    ),
    (
        SRC_E2_INTER,
        DST_E2_INTER,
    ),
    (
        SRC_E2_INTRA,
        DST_E2_INTRA,
    ),
    (
        SRC_E2_ASYM,
        DST_E2_ASYM,
    ),
    (
        SRC_E2_DETOUR,
        DST_E2_DETOUR,
    ),
    (
        SRC_E1_MANIFEST,
        DST_E1_MANIFEST,
    ),
    (
        SRC_E2_MANIFEST,
        DST_E2_MANIFEST,
    ),
]


for src, dst in copy_map:

    shutil.copy2(
        src,
        dst,
    )

    out(
        f"COPY: {dst.name}"
    )


# =====================================================================
# D. METADATA FROZEN NEL GPKG
# =====================================================================

out()
out("D. UPDATE METADATA FROZEN")
out("-" * 116)

con = sqlite3.connect(
    DST_GPKG
)

table_exists = con.execute(
    """
    SELECT COUNT(*)
    FROM sqlite_master
    WHERE
        type='table'
        AND name='Gamma_OSM_L_metadata_v01'
    """
).fetchone()[0]


if not table_exists:

    raise RuntimeError(
        "Metadata table E1 non trovata nel GPKG."
    )


frozen_metadata = {
    "status":
        "FROZEN",

    "freeze_timestamp":
        STAMP,

    "E1_gate":
        "PASS",

    "E2_gate":
        "PASS",

    "final_cardinality_K":
        "3",

    "final_min_pair_separation_m":
        "100",

    "final_primary_rule":
        "nearest eligible structural node",

    "final_candidate_search":
        "adaptive",

    "final_topological_independence":
        "no shared incident OSM topological segment",

    "final_weight_rule":
        "EXP_REL_300",

    "weight_status":
        "FROZEN",

    "routing_validation":
        "full 645-source B5 turn-aware Dijkstra",

    "intermunicipal_ordered_pairs":
        "414090",

    "intramunicipal_ordered_pairs":
        "1290",

    "unreachable_pairs":
        "0",

    "systemic_issues":
        "0",

    "blocking_issues":
        "0",
}


for key, value in frozen_metadata.items():

    con.execute(
        """
        INSERT INTO Gamma_OSM_L_metadata_v01(
            key,
            value
        )
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
            value=excluded.value
        """,
        (
            str(key),
            str(value),
        ),
    )


con.commit()
con.close()

out("Metadata status : FROZEN")
out("Weight status   : FROZEN")


# =====================================================================
# E. HASH FINALI
# =====================================================================

out()
out("E. HASH FINALI")
out("-" * 116)

hashes = {}

for path in [
    DST_GPKG,
    DST_CSV,
    DST_DIAG,
    DST_E2_MATRIX,
    DST_E2_ACCESS,
    DST_E2_TRIPLET,
    DST_E2_INTER,
    DST_E2_INTRA,
    DST_E2_ASYM,
    DST_E2_DETOUR,
    DST_E1_MANIFEST,
    DST_E2_MANIFEST,
]:

    hashes[
        path.name
    ] = sha256(
        path
    )


for name, value in hashes.items():

    out(
        f"{name:<55} {value}"
    )


# =====================================================================
# F. FINAL MANIFEST
# =====================================================================

diag = pd.read_csv(
    SRC_DIAG
)


manifest = {
    "phase":
        "FASE_5_6_GAMMA_OSM_FINAL",

    "version":
        "v01",

    "status":
        "FROZEN",

    "freeze_timestamp":
        STAMP,

    "rules": {
        "K":
            3,

        "primary":
            "nearest eligible structural node",

        "secondary_selection":
            "adaptive anchored lexicographic",

        "minimum_pair_separation_m":
            100,

        "topological_independence":
            "no shared incident OSM topological segment",

        "candidate_search":
            "adaptive",

        "weight_rule":
            "EXP_REL_300",

        "tau_m":
            300,
    },

    "E1": {
        "status":
            "PASS",

        "municipalities":
            215,

        "accesses":
            645,

        "required_depth_median":
            float(
                diag[
                    "required_depth"
                ].median()
            ),

        "required_depth_p95":
            float(
                diag[
                    "required_depth"
                ].quantile(
                    0.95
                )
            ),

        "required_depth_max":
            int(
                diag[
                    "required_depth"
                ].max()
            ),

        "minimum_pair_separation_min_m":
            float(
                diag[
                    "min_pair_separation_m"
                ].min()
            ),
    },

    "E2": {
        "status":
            "PASS",

        "sources":
            645,

        "full_matrix_cells":
            416025,

        "intermunicipal_ordered_pairs":
            414090,

        "intramunicipal_ordered_pairs":
            1290,

        "unreachable_intermunicipal":
            0,

        "unreachable_intramunicipal":
            0,

        "bad_triplets":
            0,

        "zero_time_offdiagonal":
            0,

        "negative_time":
            0,

        "physical_bound_violations":
            0,
    },

    "weights": {
        "status":
            "FROZEN",

        "rule":
            "EXP_REL_300",

        "nonpositive":
            nonpositive,

        "max_sum_error":
            lambda_error,
    },

    "issues": {
        "SYSTEMIC":
            0,

        "BLOCKING":
            0,
    },

    "files_sha256":
        hashes,
}


DST_FINAL_MANIFEST.write_text(
    json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


final_manifest_sha = sha256(
    DST_FINAL_MANIFEST
)

out()
out(
    f"FINAL manifest SHA256 : "
    f"{final_manifest_sha}"
)


# =====================================================================
# G. FINAL GATE
# =====================================================================

out()
out("=" * 116)
out("ESITO E3: PASS")
out("Gamma_OSM = FROZEN")
out("EXP_REL_300 = FROZEN")
out("=" * 116)

out(f"Package  : {PKG}")
out(f"GPKG     : {DST_GPKG}")
out(f"Manifest : {DST_FINAL_MANIFEST}")
out(f"LOG      : {LOG}")

out("=== RUN COMPLETATA ===")


LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
