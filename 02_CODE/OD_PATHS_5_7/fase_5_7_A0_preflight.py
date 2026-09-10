# -*- coding: utf-8 -*-

from pathlib import Path
import hashlib
import json
import sqlite3
import sys

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Tesi\Tesi_QGIS")

PBF = ROOT / r"00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf"

BACKBONE_DIR = ROOT / r"02_package\grafo_operativo_osm"
GAMMA_DIR = ROOT / r"02_package\accessi_comunali_osm_light"

OUT_DIR = ROOT / r"03_output_temporanei\fase_5_7\A0_preflight"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOG = OUT_DIR / "FASE_5_7_A0_preflight.txt"

EXPECTED_HASHES = {
    PBF:
        "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813",

    BACKBONE_DIR / "G_OSM_operativo_v01.gpkg":
        "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3",

    BACKBONE_DIR / "G_OSM_FINAL_manifest_v01.json":
        "c4ea80c9c660f6a513b20400d0c3edb2f9e6ec10c3364f0a4b0beed91af55da3",

    GAMMA_DIR / "Gamma_OSM_L_comuni_fvg_v01.gpkg":
        "b899a2e0e29d7ef366c42f4b68ef43a25b4ba1150052b6275770dd9ae23e1d3f",

    GAMMA_DIR / "Gamma_OSM_L_comuni_fvg_v01.csv":
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",

    GAMMA_DIR / "Gamma_OSM_E2_time_matrix_645x645_v01.npy":
        "b787665e7c4064cf6ec68e1905d8db5654a69aad1538919f1d0a92adafa006db",

    GAMMA_DIR / "Gamma_OSM_FINAL_manifest_v01.json":
        "31ee2d78cd06c75cdf07014a8cecac4af2c58adeb26ec7285362ab4c02b11416",
}


_lines = []


def emit(msg=""):
    msg = str(msg)
    print(msg)
    _lines.append(msg)


def sha256_file(path: Path, chunk_size=16 * 1024 * 1024):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_exact(root: Path, filename: str):
    hits = sorted(root.rglob(filename))

    emit(f"\nSEARCH: {filename}")
    emit(f"hits = {len(hits)}")

    for p in hits:
        emit(f"  {p}")

    if len(hits) != 1:
        raise RuntimeError(
            f"Expected exactly one {filename}, found {len(hits)}"
        )

    return hits[0]


def inspect_sqlite(path: Path):
    emit("\n" + "=" * 100)
    emit(f"SQLITE: {path}")
    emit("=" * 100)

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    try:
        tables = [
            r[0]
            for r in con.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
        ]

        emit(f"tables ({len(tables)}):")
        for t in tables:
            emit(f"  - {t}")

        for t in tables:
            emit("\n" + "-" * 100)
            emit(f"TABLE: {t}")

            cols = con.execute(f'PRAGMA table_info("{t}")').fetchall()

            emit("columns:")
            for c in cols:
                # cid, name, type, notnull, default, pk
                emit(
                    f"  cid={c[0]:>3} "
                    f"name={c[1]!r:<35} "
                    f"type={c[2]!r:<15} "
                    f"notnull={c[3]} "
                    f"pk={c[5]}"
                )

            try:
                n = con.execute(
                    f'SELECT COUNT(*) FROM "{t}"'
                ).fetchone()[0]
                emit(f"row_count = {n:,}")
            except Exception as e:
                emit(f"row_count ERROR: {e}")

            try:
                rows = con.execute(
                    f'SELECT * FROM "{t}" LIMIT 3'
                ).fetchall()
                emit("sample_rows:")
                for r in rows:
                    emit(f"  {r}")
            except Exception as e:
                emit(f"sample ERROR: {e}")

        emit("\nINDEXES:")
        indexes = con.execute("""
            SELECT name, tbl_name, sql
            FROM sqlite_master
            WHERE type='index'
            ORDER BY tbl_name, name
        """).fetchall()

        for name, table, sql in indexes:
            emit(f"  {table} :: {name} :: {sql}")

    finally:
        con.close()


def inspect_npz(path: Path):
    emit("\n" + "=" * 100)
    emit(f"NPZ: {path}")
    emit("=" * 100)

    with np.load(path, allow_pickle=False) as z:
        emit(f"keys = {list(z.files)}")

        for key in z.files:
            a = z[key]
            emit(
                f"{key}: shape={a.shape}, dtype={a.dtype}, ndim={a.ndim}"
            )

            if a.size:
                flat = a.reshape(-1)
                emit(f"  first = {flat[:5].tolist()}")
                emit(f"  last  = {flat[-5:].tolist()}")


def inspect_json(path: Path):
    emit("\n" + "=" * 100)
    emit(f"JSON: {path}")
    emit("=" * 100)

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        emit(f"top-level keys = {list(data.keys())}")
    else:
        emit(f"top-level type = {type(data).__name__}")

    txt = json.dumps(data, indent=2, ensure_ascii=False)
    emit("\nMANIFEST PREVIEW:")
    emit(txt[:15000])

    if len(txt) > 15000:
        emit("\n... manifest preview truncated ...")


try:
    emit("=" * 110)
    emit("FASE 5.7 — A0 — PREFLIGHT READ-ONLY")
    emit("=" * 110)

    emit(f"Python      : {sys.executable}")
    emit(f"Python ver. : {sys.version}")
    emit(f"ROOT        : {ROOT}")
    emit(f"Backbone    : {BACKBONE_DIR}")
    emit(f"Gamma       : {GAMMA_DIR}")
    emit(f"Output      : {OUT_DIR}")

    # ------------------------------------------------------------------
    # 1. EXISTENCE + CANONICAL HASHES
    # ------------------------------------------------------------------

    emit("\n" + "=" * 110)
    emit("1. FROZEN IDENTITY CHECK")
    emit("=" * 110)

    hash_failures = 0

    for path, expected in EXPECTED_HASHES.items():
        emit(f"\nFILE: {path}")

        if not path.exists():
            emit("STATUS: MISSING")
            hash_failures += 1
            continue

        emit(f"SIZE : {path.stat().st_size:,} bytes")
        emit("SHA256 calculation...")

        actual = sha256_file(path)

        emit(f"expected = {expected}")
        emit(f"actual   = {actual}")

        if actual.lower() == expected.lower():
            emit("STATUS   = PASS")
        else:
            emit("STATUS   = HASH_MISMATCH")
            hash_failures += 1

    if hash_failures:
        raise RuntimeError(
            f"Frozen identity check failed: {hash_failures} issue(s)"
        )

    # ------------------------------------------------------------------
    # 2. LOCATE ROUTING ARTIFACTS
    # ------------------------------------------------------------------

    emit("\n" + "=" * 110)
    emit("2. ROUTING ARTIFACT DISCOVERY")
    emit("=" * 110)

    b2 = find_exact(
        BACKBONE_DIR,
        "osm_directed_edges_v02.sqlite"
    )

    b4 = find_exact(
        BACKBONE_DIR,
        "osm_turn_restrictions_compiled_v01.sqlite"
    )

    b5_index = find_exact(
        BACKBONE_DIR,
        "osm_turn_state_index_v01.sqlite"
    )

    b5_time = find_exact(
        BACKBONE_DIR,
        "osm_turn_state_time_v01.npz"
    )

    # ------------------------------------------------------------------
    # 3. MANIFESTS
    # ------------------------------------------------------------------

    inspect_json(
        BACKBONE_DIR / "G_OSM_FINAL_manifest_v01.json"
    )

    inspect_json(
        GAMMA_DIR / "Gamma_OSM_FINAL_manifest_v01.json"
    )

    # ------------------------------------------------------------------
    # 4. SQLITE SCHEMAS
    # ------------------------------------------------------------------

    inspect_sqlite(b2)
    inspect_sqlite(b4)
    inspect_sqlite(b5_index)

    # ------------------------------------------------------------------
    # 5. B5 NUMERIC ARRAYS
    # ------------------------------------------------------------------

    inspect_npz(b5_time)

    # ------------------------------------------------------------------
    # 6. GAMMA CSV
    # ------------------------------------------------------------------

    gamma_csv = GAMMA_DIR / "Gamma_OSM_L_comuni_fvg_v01.csv"

    emit("\n" + "=" * 110)
    emit("6. GAMMA CSV")
    emit("=" * 110)

    gamma = pd.read_csv(gamma_csv)

    emit(f"shape   = {gamma.shape}")
    emit(f"columns = {list(gamma.columns)}")
    emit("\ndtypes:")
    emit(gamma.dtypes.to_string())

    emit("\nfirst 10 rows:")
    emit(gamma.head(10).to_string(index=False))

    # Case-insensitive detection only for structural QA.
    lower = {str(c).lower(): c for c in gamma.columns}

    pro_col = lower.get("pro_com")
    order_col = lower.get("access_order")

    if pro_col is not None:
        emit(
            f"\nunique municipalities ({pro_col}) = "
            f"{gamma[pro_col].nunique()}"
        )

    if order_col is not None:
        emit(
            f"access-order counts ({order_col}):\n"
            f"{gamma[order_col].value_counts(dropna=False).sort_index()}"
        )

    # Candidate lambda columns: discovery only, no assumption.
    lambda_candidates = [
        c for c in gamma.columns
        if "lambda" in str(c).lower()
        or "exp_rel" in str(c).lower()
    ]

    emit(
        f"\nlambda/EXP_REL candidate columns = "
        f"{lambda_candidates}"
    )

    # ------------------------------------------------------------------
    # 7. E2 MATRIX
    # ------------------------------------------------------------------

    e2_path = GAMMA_DIR / "Gamma_OSM_E2_time_matrix_645x645_v01.npy"

    emit("\n" + "=" * 110)
    emit("7. E2 MATRIX")
    emit("=" * 110)

    e2 = np.load(e2_path, mmap_mode="r")

    emit(f"shape = {e2.shape}")
    emit(f"dtype = {e2.dtype}")
    emit(f"finite = {np.isfinite(e2).sum():,} / {e2.size:,}")
    emit(f"nonfinite = {(~np.isfinite(e2)).sum():,}")

    if e2.ndim == 2 and e2.shape[0] == e2.shape[1]:
        diag = np.asarray(np.diag(e2))
        emit(f"diag min = {diag.min()}")
        emit(f"diag max = {diag.max()}")

        mask = ~np.eye(e2.shape[0], dtype=bool)
        off = np.asarray(e2)[mask]

        emit(f"offdiag min = {off.min()}")
        emit(f"offdiag max = {off.max()}")
        emit(f"offdiag <= 0 = {(off <= 0).sum():,}")

    # ------------------------------------------------------------------
    # 8. DISCOVER E2 MAPPING / PAIR ARTIFACTS
    # ------------------------------------------------------------------

    emit("\n" + "=" * 110)
    emit("8. E2 / PAIR MAPPING ARTIFACTS")
    emit("=" * 110)

    candidates = []

    for p in GAMMA_DIR.rglob("*"):
        if not p.is_file():
            continue

        s = p.name.lower()

        if (
            "e2" in s
            or "pair" in s
            or "index" in s
            or "mapping" in s
        ):
            candidates.append(p)

    for p in sorted(set(candidates)):
        emit(
            f"{p.name:<60} "
            f"{p.stat().st_size:>15,} bytes"
        )

    # ------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------

    emit("\n" + "=" * 110)
    emit("A0 PREFLIGHT RESULT = PASS")
    emit("Frozen artifacts were READ ONLY.")
    emit("No backbone/Gamma artifact was modified.")
    emit("=" * 110)

    emit("\n=== RUN COMPLETATA CORRETTAMENTE ===")

except Exception as exc:
    emit("\n" + "=" * 110)
    emit("A0 PREFLIGHT RESULT = FAIL")
    emit(f"{type(exc).__name__}: {exc}")
    emit("=" * 110)

    emit("\n=== RUN TERMINATA CON ERRORE ===")

    LOG.write_text(
        "\n".join(_lines),
        encoding="utf-8"
    )

    raise

finally:
    LOG.write_text(
        "\n".join(_lines),
        encoding="utf-8"
    )

    print(f"\nLog salvato in:\n{LOG}")
