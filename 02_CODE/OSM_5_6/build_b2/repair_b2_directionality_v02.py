from pathlib import Path
from datetime import datetime
from collections import Counter
import math
import shutil
import sqlite3
import sys


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2_V01 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v01.sqlite"
)

SOURCE_GPKG = (
    ROOT
    / r"02_package\rete_stradale_osm_fvg.gpkg"
)

SOURCE_LAYER = "osm_rete_light_20km_tempi_base_v3"

OUTDB = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

LOG = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2"
    / f"repair_b2_directionality_v02_{STAMP}.txt"
)

BATCH_SIZE = 100_000


# =============================================================================
# LOG
# =============================================================================

lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def to_int_code(x):
    if x is None:
        raise RuntimeError("routing_code NULL")

    try:
        value = int(x)
    except Exception:
        raise RuntimeError(
            f"routing_code non interpretabile: {x!r}"
        )

    if value not in (0, 1, 2):
        raise RuntimeError(
            f"routing_code fuori dominio: {value}"
        )

    return value


def to_positive_float(x, label):
    try:
        value = float(x)
    except Exception:
        raise RuntimeError(
            f"{label} non numerico: {x!r}"
        )

    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(
            f"{label} non valido: {value}"
        )

    return value


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 110)
out("FASE 5.6 — BUILD B2_v02 — REPAIR DIREZIONALITÀ")
out("=" * 110)

out(f"Input B2_v01   : {B2_V01}")
out(f"Semantic GPKG  : {SOURCE_GPKG}")
out(f"Semantic layer : {SOURCE_LAYER}")
out(f"Output B2_v02  : {OUTDB}")

if not B2_V01.exists():
    raise FileNotFoundError(B2_V01)

if not SOURCE_GPKG.exists():
    raise FileNotFoundError(SOURCE_GPKG)

if OUTDB.exists():
    raise RuntimeError(
        f"Output già esistente: {OUTDB}\n"
        "Non sovrascrivo output versionati."
    )


# =============================================================================
# A. LETTURA SEMANTICA AUTOREVOLE
# =============================================================================

out()
out("A. VALIDAZIONE CONTRATTO routing_*_code / status")
out("-" * 110)

src = sqlite3.connect(SOURCE_GPKG)
src_cur = src.cursor()

required = [
    "osm_id",

    "direction_status",

    "routing_fwd_status",
    "routing_bwd_status",

    "routing_fwd_code",
    "routing_bwd_code",

    "routing_fwd_closure_cause",
    "routing_bwd_closure_cause",

    "access_fwd_class",
    "access_bwd_class",

    "speed_fwd_model_kmh",
    "speed_bwd_model_kmh",

    "speed_fwd_model_source",
    "speed_bwd_model_source",

    "access_conditional_flag",
    "direction_conditional_flag",
    "speed_conditional_flag",
]

cols = [
    r[1]
    for r in src_cur.execute(
        f'PRAGMA table_info("{SOURCE_LAYER}")'
    ).fetchall()
]

missing = [x for x in required if x not in cols]

if missing:
    raise RuntimeError(
        "Campi mancanti: " + ", ".join(missing)
    )


STATUS_CODE_CONTRACT = {
    "open": 1,
    "local_restricted": 2,
    "closed_access": 0,
    "closed_direction": 0,
}


sql = f'''
SELECT
    {", ".join('"' + c + '"' for c in required)}
FROM "{SOURCE_LAYER}"
ORDER BY CAST(osm_id AS INTEGER)
'''

semantics = {}
signatures = {}

bad_contract = []
duplicate_rows = 0
semantic_conflicts = []

feature_fwd_codes = Counter()
feature_bwd_codes = Counter()

feature_fwd_status = Counter()
feature_bwd_status = Counter()


for row in src_cur.execute(sql):

    d = dict(zip(required, row))

    wid = int(d["osm_id"])

    fwd_code = to_int_code(
        d["routing_fwd_code"]
    )

    bwd_code = to_int_code(
        d["routing_bwd_code"]
    )

    fwd_status = str(
        d["routing_fwd_status"]
    )

    bwd_status = str(
        d["routing_bwd_status"]
    )

    feature_fwd_codes[fwd_code] += 1
    feature_bwd_codes[bwd_code] += 1

    feature_fwd_status[fwd_status] += 1
    feature_bwd_status[bwd_status] += 1

    expected_fwd = STATUS_CODE_CONTRACT.get(
        fwd_status
    )

    expected_bwd = STATUS_CODE_CONTRACT.get(
        bwd_status
    )

    if expected_fwd != fwd_code:
        bad_contract.append(
            (
                wid,
                "FWD",
                fwd_status,
                fwd_code,
                expected_fwd,
            )
        )

    if expected_bwd != bwd_code:
        bad_contract.append(
            (
                wid,
                "BWD",
                bwd_status,
                bwd_code,
                expected_bwd,
            )
        )

    sf = (
        float(d["speed_fwd_model_kmh"])
        if d["speed_fwd_model_kmh"] is not None
        else None
    )

    sb = (
        float(d["speed_bwd_model_kmh"])
        if d["speed_bwd_model_kmh"] is not None
        else None
    )

    signature = (
        d["direction_status"],

        fwd_status,
        bwd_status,

        fwd_code,
        bwd_code,

        d["routing_fwd_closure_cause"],
        d["routing_bwd_closure_cause"],

        d["access_fwd_class"],
        d["access_bwd_class"],

        sf,
        sb,

        d["speed_fwd_model_source"],
        d["speed_bwd_model_source"],

        d["access_conditional_flag"],
        d["direction_conditional_flag"],
        d["speed_conditional_flag"],
    )

    if wid in signatures:

        duplicate_rows += 1

        if signatures[wid] != signature:
            semantic_conflicts.append(wid)

        continue

    signatures[wid] = signature

    semantics[wid] = {
        "direction_status":
            d["direction_status"],

        "fwd_status":
            fwd_status,

        "bwd_status":
            bwd_status,

        "fwd_code":
            fwd_code,

        "bwd_code":
            bwd_code,

        "fwd_closure":
            d["routing_fwd_closure_cause"],

        "bwd_closure":
            d["routing_bwd_closure_cause"],

        "fwd_access":
            d["access_fwd_class"],

        "bwd_access":
            d["access_bwd_class"],

        "fwd_speed":
            sf,

        "bwd_speed":
            sb,

        "fwd_speed_source":
            d["speed_fwd_model_source"],

        "bwd_speed_source":
            d["speed_bwd_model_source"],

        "access_conditional_flag":
            d["access_conditional_flag"],

        "direction_conditional_flag":
            d["direction_conditional_flag"],

        "speed_conditional_flag":
            d["speed_conditional_flag"],
    }


out(f"Way consolidate       : {len(semantics):,}")
out(f"Righe duplicate       : {duplicate_rows:,}")
out(f"Conflitti semantici   : {len(semantic_conflicts):,}")
out(f"Violazioni contratto  : {len(bad_contract):,}")

if semantic_conflicts:
    out(
        "Esempi conflitti: "
        + str(semantic_conflicts[:20])
    )
    raise RuntimeError(
        "Conflitto semantico tra feature "
        "della stessa OSM way."
    )

if bad_contract:
    out(
        "Esempi violazioni: "
        + str(bad_contract[:20])
    )
    raise RuntimeError(
        "Contratto routing status/code violato."
    )


out()
out("Feature-level routing codes")
out("-" * 110)

for code in (0, 1, 2):
    out(
        f"FWD code={code}: "
        f"{feature_fwd_codes[code]:>8,} | "
        f"BWD code={code}: "
        f"{feature_bwd_codes[code]:>8,}"
    )


# =============================================================================
# B. CONTROLLI SPECIALI
# =============================================================================

out()
out("B. CONTROLLI DIREZIONALI SPECIALI")
out("-" * 110)

special_errors = []

for wid, sem in semantics.items():

    ds = sem["direction_status"]

    fc = sem["fwd_code"]
    bc = sem["bwd_code"]

    if ds == "explicit_oneway":

        if bc != 0:
            special_errors.append(
                (wid, ds, fc, bc)
            )

    elif ds in (
        "implicit_roundabout",
        "implicit_circular",
    ):

        if bc != 0:
            special_errors.append(
                (wid, ds, fc, bc)
            )

    elif ds == "explicit_reverse":

        if fc != 0 or bc not in (1, 2):
            special_errors.append(
                (wid, ds, fc, bc)
            )


out(
    f"Violazioni speciali: "
    f"{len(special_errors):,}"
)

if special_errors:
    out(
        "Esempi: "
        + str(special_errors[:20])
    )

    raise RuntimeError(
        "Incoerenza nelle categorie direzionali speciali."
    )


# =============================================================================
# C. COPIA NON DISTRUTTIVA B2_v01 → B2_v02
# =============================================================================

out()
out("C. COPIA NON DISTRUTTIVA DELLA TOPOLOGIA B2_v01")
out("-" * 110)

src.close()

shutil.copy2(
    B2_V01,
    OUTDB,
)

out(
    f"Copiato: "
    f"{B2_V01.stat().st_size:,} bytes"
)


# =============================================================================
# D. RICOSTRUZIONE directed_edges
# =============================================================================

out()
out("D. RICOSTRUZIONE EDGE DIRETTI")
out("-" * 110)

db = sqlite3.connect(OUTDB)
cur = db.cursor()

cur.execute(
    "DROP TABLE IF EXISTS directed_edges"
)

cur.executescript(
    """
    CREATE TABLE directed_edges (
        edge_id INTEGER PRIMARY KEY,

        edge_uid TEXT NOT NULL UNIQUE,

        segment_uid TEXT NOT NULL,

        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,

        u INTEGER NOT NULL,
        v INTEGER NOT NULL,

        way_direction TEXT NOT NULL,

        length_m REAL NOT NULL,

        speed_kmh REAL NOT NULL,
        time_s REAL NOT NULL,

        highway TEXT,

        direction_status TEXT,

        routing_status TEXT NOT NULL,
        routing_code INTEGER NOT NULL,

        closure_cause TEXT,

        access_class TEXT,

        speed_source TEXT,

        edge_role TEXT NOT NULL,

        core_eligible INTEGER NOT NULL,

        access_conditional_flag TEXT,
        direction_conditional_flag TEXT,
        speed_conditional_flag TEXT,

        CHECK (
            routing_code IN (1, 2)
        ),

        CHECK (
            core_eligible IN (0, 1)
        )
    );

    CREATE INDEX idx_edges_u
        ON directed_edges(u);

    CREATE INDEX idx_edges_v
        ON directed_edges(v);

    CREATE INDEX idx_edges_way
        ON directed_edges(way_id);

    CREATE INDEX idx_edges_segment
        ON directed_edges(segment_uid);

    CREATE INDEX idx_edges_core
        ON directed_edges(core_eligible);

    CREATE INDEX idx_edges_routing_code
        ON directed_edges(routing_code);
    """
)

db.commit()


segment_count = cur.execute(
    "SELECT COUNT(*) FROM segments"
).fetchone()[0]

out(f"Segmenti input: {segment_count:,}")


read_cur = db.cursor()

read_cur.execute(
    """
    SELECT
        segment_uid,
        way_id,
        seq,
        osm_u,
        osm_v,
        length_m,
        highway
    FROM segments
    ORDER BY way_id, seq
    """
)


edge_id = 0

expected_edges = 0

expected_core = 0
expected_local = 0

suppressed_code0 = 0

generated_fwd = 0
generated_bwd = 0

generated_core = 0
generated_local = 0

segment_patterns = Counter()

processed_segments = 0


while True:

    rows = read_cur.fetchmany(BATCH_SIZE)

    if not rows:
        break

    edge_batch = []

    for (
        segment_uid,
        wid,
        seq,
        osm_u,
        osm_v,
        length_m,
        highway,
    ) in rows:

        wid = int(wid)
        seq = int(seq)

        u = int(osm_u)
        v = int(osm_v)

        length_m = float(length_m)

        sem = semantics.get(wid)

        if sem is None:
            raise RuntimeError(
                f"Semantica assente per way {wid}"
            )

        fc = sem["fwd_code"]
        bc = sem["bwd_code"]

        segment_patterns[(fc, bc)] += 1

        # =============================================================
        # FWD
        # =============================================================

        if fc == 0:

            suppressed_code0 += 1

        elif fc in (1, 2):

            expected_edges += 1

            speed = to_positive_float(
                sem["fwd_speed"],
                f"FWD speed way={wid}",
            )

            time_s = (
                length_m
                * 3.6
                / speed
            )

            if fc == 1:
                edge_role = "CORE"
                core_eligible = 1
                expected_core += 1
            else:
                edge_role = "LOCAL_ENDPOINT_ONLY"
                core_eligible = 0
                expected_local += 1

            edge_id += 1

            edge_batch.append(
                (
                    edge_id,

                    f"{wid}:{seq}:F",

                    segment_uid,

                    wid,
                    seq,

                    u,
                    v,

                    "FWD",

                    length_m,

                    speed,
                    time_s,

                    highway,

                    sem["direction_status"],

                    sem["fwd_status"],
                    fc,

                    sem["fwd_closure"],

                    sem["fwd_access"],

                    sem["fwd_speed_source"],

                    edge_role,
                    core_eligible,

                    sem[
                        "access_conditional_flag"
                    ],
                    sem[
                        "direction_conditional_flag"
                    ],
                    sem[
                        "speed_conditional_flag"
                    ],
                )
            )

            generated_fwd += 1

            if core_eligible:
                generated_core += 1
            else:
                generated_local += 1

        # =============================================================
        # BWD
        # =============================================================

        if bc == 0:

            suppressed_code0 += 1

        elif bc in (1, 2):

            expected_edges += 1

            speed = to_positive_float(
                sem["bwd_speed"],
                f"BWD speed way={wid}",
            )

            time_s = (
                length_m
                * 3.6
                / speed
            )

            if bc == 1:
                edge_role = "CORE"
                core_eligible = 1
                expected_core += 1
            else:
                edge_role = "LOCAL_ENDPOINT_ONLY"
                core_eligible = 0
                expected_local += 1

            edge_id += 1

            edge_batch.append(
                (
                    edge_id,

                    f"{wid}:{seq}:B",

                    segment_uid,

                    wid,
                    seq,

                    v,
                    u,

                    "BWD",

                    length_m,

                    speed,
                    time_s,

                    highway,

                    sem["direction_status"],

                    sem["bwd_status"],
                    bc,

                    sem["bwd_closure"],

                    sem["bwd_access"],

                    sem["bwd_speed_source"],

                    edge_role,
                    core_eligible,

                    sem[
                        "access_conditional_flag"
                    ],
                    sem[
                        "direction_conditional_flag"
                    ],
                    sem[
                        "speed_conditional_flag"
                    ],
                )
            )

            generated_bwd += 1

            if core_eligible:
                generated_core += 1
            else:
                generated_local += 1

    if edge_batch:

        cur.executemany(
            """
            INSERT INTO directed_edges(
                edge_id,

                edge_uid,

                segment_uid,

                way_id,
                seq,

                u,
                v,

                way_direction,

                length_m,

                speed_kmh,
                time_s,

                highway,

                direction_status,

                routing_status,
                routing_code,

                closure_cause,

                access_class,

                speed_source,

                edge_role,
                core_eligible,

                access_conditional_flag,
                direction_conditional_flag,
                speed_conditional_flag
            )
            VALUES (
                ?,
                ?,
                ?,
                ?, ?,
                ?, ?,
                ?,
                ?,
                ?, ?,
                ?,
                ?,
                ?, ?,
                ?,
                ?,
                ?,
                ?, ?,
                ?, ?, ?
            )
            """,
            edge_batch,
        )

    processed_segments += len(rows)

    db.commit()

    out(
        f"  segmenti={processed_segments:>9,} | "
        f"edges={edge_id:>9,} | "
        f"core={generated_core:>9,} | "
        f"local={generated_local:>7,}"
    )


# =============================================================================
# E. QA DIREZIONALITÀ
# =============================================================================

out()
out("E. QA DIREZIONALITÀ B2_v02")
out("-" * 110)

db_edge_count = cur.execute(
    "SELECT COUNT(*) FROM directed_edges"
).fetchone()[0]

db_core_count = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE core_eligible = 1
    """
).fetchone()[0]

db_local_count = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE core_eligible = 0
    """
).fetchone()[0]

code0_edges = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE routing_code = 0
    """
).fetchone()[0]

bad_core = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE
        (
            routing_code = 1
            AND core_eligible != 1
        )
        OR
        (
            routing_code = 2
            AND core_eligible != 0
        )
    """
).fetchone()[0]


out(f"Edge attesi           : {expected_edges:,}")
out(f"Edge generati         : {db_edge_count:,}")

out()
out(f"CORE attesi           : {expected_core:,}")
out(f"CORE generati         : {db_core_count:,}")

out(f"LOCAL attesi          : {expected_local:,}")
out(f"LOCAL generati        : {db_local_count:,}")

out()
out(f"Direzioni code=0 escluse : {suppressed_code0:,}")
out(f"Edge code=0 presenti     : {code0_edges:,}")
out(f"Incoerenze core/code     : {bad_core:,}")


# =============================================================================
# F. QA PER VERSO E STATUS
# =============================================================================

out()
out("F. DISTRIBUZIONE EDGE")
out("-" * 110)

for direction, n in cur.execute(
    """
    SELECT
        way_direction,
        COUNT(*)
    FROM directed_edges
    GROUP BY way_direction
    ORDER BY way_direction
    """
):
    out(
        f"{direction:<20} "
        f"{n:>12,}"
    )


out()
out("Routing code")
out("-" * 110)

for code, role, n in cur.execute(
    """
    SELECT
        routing_code,
        edge_role,
        COUNT(*)
    FROM directed_edges
    GROUP BY routing_code, edge_role
    ORDER BY routing_code
    """
):
    out(
        f"code={code} "
        f"{role:<25} "
        f"{n:>12,}"
    )


out()
out("Direction status × verso")
out("-" * 110)

rows = cur.execute(
    """
    SELECT
        direction_status,
        way_direction,
        COUNT(*)
    FROM directed_edges
    GROUP BY
        direction_status,
        way_direction
    ORDER BY
        direction_status,
        way_direction
    """
).fetchall()

for status, direction, n in rows:

    out(
        f"{str(status):<30} "
        f"{direction:<8} "
        f"{n:>12,}"
    )


# =============================================================================
# G. QA SPECIFICO ONEWAY / ROUNDABOUT / REVERSE
# =============================================================================

out()
out("G. QA SPECIALI POST-BUILD")
out("-" * 110)

oneway_bad_bwd = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE
        direction_status = 'explicit_oneway'
        AND way_direction = 'BWD'
    """
).fetchone()[0]

roundabout_bad_bwd = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE
        direction_status IN (
            'implicit_roundabout',
            'implicit_circular'
        )
        AND way_direction = 'BWD'
    """
).fetchone()[0]

reverse_bad_fwd = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE
        direction_status = 'explicit_reverse'
        AND way_direction = 'FWD'
    """
).fetchone()[0]

reverse_bwd = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE
        direction_status = 'explicit_reverse'
        AND way_direction = 'BWD'
    """
).fetchone()[0]


out(
    f"explicit_oneway BWD errati : "
    f"{oneway_bad_bwd:,}"
)

out(
    f"roundabout/circular BWD errati : "
    f"{roundabout_bad_bwd:,}"
)

out(
    f"explicit_reverse FWD errati : "
    f"{reverse_bad_fwd:,}"
)

out(
    f"explicit_reverse BWD validi : "
    f"{reverse_bwd:,}"
)


# =============================================================================
# H. CHECK EDGE COUNT PER SEGMENT
# =============================================================================

out()
out("H. CONSISTENZA SEGMENT → EDGE")
out("-" * 110)

actual_segment_counts = {
    segment_uid: n

    for segment_uid, n in cur.execute(
        """
        SELECT
            segment_uid,
            COUNT(*)
        FROM directed_edges
        GROUP BY segment_uid
        """
    )
}

segment_count_errors = 0
segment_count_error_examples = []

check_cur = db.cursor()

for (
    segment_uid,
    way_id,
) in check_cur.execute(
    """
    SELECT
        segment_uid,
        way_id
    FROM segments
    ORDER BY way_id, seq
    """
):

    sem = semantics[int(way_id)]

    expected = int(
        sem["fwd_code"] in (1, 2)
    ) + int(
        sem["bwd_code"] in (1, 2)
    )

    actual = actual_segment_counts.get(
        segment_uid,
        0,
    )

    if expected != actual:

        segment_count_errors += 1

        if len(segment_count_error_examples) < 20:
            segment_count_error_examples.append(
                (
                    segment_uid,
                    way_id,
                    sem["fwd_code"],
                    sem["bwd_code"],
                    expected,
                    actual,
                )
            )


out(
    f"Segmenti con edge count errato: "
    f"{segment_count_errors:,}"
)

if segment_count_error_examples:

    out(
        "Esempi: "
        + str(segment_count_error_examples)
    )


# =============================================================================
# I. METADATA
# =============================================================================

out()
out("I. METADATA B2_v02")
out("-" * 110)

metadata = {
    "phase":
        "FASE_5_6_BUILD_B2",

    "version":
        "v02",

    "created_at":
        STAMP,

    "parent_build":
        str(B2_V01),

    "parent_build_status":
        "REJECTED_DIRECTION_INCLUSION_BUG",

    "direction_inclusion_rule":
        "routing_code in {1,2}",

    "routing_code_0":
        "UNAVAILABLE",

    "routing_code_1":
        "CORE_ORDINARY",

    "routing_code_2":
        "LOCAL_ENDPOINT_ONLY",

    "core_graph_rule":
        "core_eligible=1 only",

    "time_rule":
        "time_s = length_m * 3.6 / speed_kmh",

    "time_not_used_for_availability":
        "TRUE",

    "final_directed_edge_count":
        db_edge_count,

    "final_core_edge_count":
        db_core_count,

    "final_local_edge_count":
        db_local_count,

    "suppressed_code0_direction_count":
        suppressed_code0,

    "segment_edge_count_error_count":
        segment_count_errors,
}


cur.executemany(
    """
    INSERT OR REPLACE INTO metadata(
        key,
        value
    )
    VALUES (?, ?)
    """,
    [
        (k, str(v))
        for k, v in metadata.items()
    ],
)

db.commit()


# =============================================================================
# J. GATE
# =============================================================================

blocking_errors = []

if db_edge_count != expected_edges:
    blocking_errors.append(
        "EDGE_COUNT_MISMATCH"
    )

if db_core_count != expected_core:
    blocking_errors.append(
        "CORE_COUNT_MISMATCH"
    )

if db_local_count != expected_local:
    blocking_errors.append(
        "LOCAL_COUNT_MISMATCH"
    )

if code0_edges != 0:
    blocking_errors.append(
        "CODE0_EDGE_PRESENT"
    )

if bad_core != 0:
    blocking_errors.append(
        "CORE_CODE_MISMATCH"
    )

if oneway_bad_bwd != 0:
    blocking_errors.append(
        "ONEWAY_REVERSE_EDGE"
    )

if roundabout_bad_bwd != 0:
    blocking_errors.append(
        "ROUNDABOUT_REVERSE_EDGE"
    )

if reverse_bad_fwd != 0:
    blocking_errors.append(
        "EXPLICIT_REVERSE_FWD_EDGE"
    )

if reverse_bwd == 0:
    blocking_errors.append(
        "EXPLICIT_REVERSE_BWD_MISSING"
    )

if segment_count_errors != 0:
    blocking_errors.append(
        "SEGMENT_EDGE_COUNT_ERROR"
    )


# =============================================================================
# K. FINALIZZAZIONE
# =============================================================================

out()
out("J. FINALIZZAZIONE")
out("-" * 110)

cur.execute(
    "PRAGMA wal_checkpoint(TRUNCATE)"
)

db.commit()
db.close()

out(
    f"SQLite prodotto : {OUTDB}"
)

out(
    f"Dimensione      : "
    f"{OUTDB.stat().st_size:,} bytes"
)

out()
out("=" * 110)

if blocking_errors:

    out(
        "ESITO BUILD B2_v02: FAIL"
    )

    for e in blocking_errors:
        out(f"  BLOCKING: {e}")

else:

    out(
        "ESITO BUILD B2_v02: PASS"
    )

out("=" * 110)

out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
