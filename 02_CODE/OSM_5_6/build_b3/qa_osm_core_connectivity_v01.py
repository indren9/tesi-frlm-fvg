from pathlib import Path
from datetime import datetime
from importlib.metadata import version
import sqlite3
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b3"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUTDB = OUTDIR / "osm_core_connectivity_qa_v01.sqlite"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"qa_osm_core_connectivity_v01_{STAMP}.txt"

BATCH = 200_000


# =============================================================================
# LOG
# =============================================================================

lines = []


def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


# =============================================================================
# PREFLIGHT
# =============================================================================

out("=" * 110)
out("FASE 5.6 — BUILD B3 — QA STRUTTURALE CORE OSM")
out("=" * 110)

out(f"Input B2_v02 : {B2}")
out(f"Output QA    : {OUTDB}")
out(f"Python       : {sys.version.replace(chr(10), ' ')}")
out(f"NumPy        : {version('numpy')}")
out(f"SciPy        : {version('scipy')}")

if not B2.exists():
    raise FileNotFoundError(B2)

if OUTDB.exists():
    raise RuntimeError(
        f"Output già esistente: {OUTDB}\n"
        "Non sovrascrivo output versionati."
    )


# =============================================================================
# A. NODI FISICI
# =============================================================================

out()
out("A. CARICAMENTO NODI")
out("-" * 110)

src = sqlite3.connect(B2)
cur = src.cursor()

physical_node_count = cur.execute(
    "SELECT COUNT(*) FROM nodes"
).fetchone()[0]

core_edge_count = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE core_eligible = 1
    """
).fetchone()[0]

local_edge_count = cur.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE core_eligible = 0
    """
).fetchone()[0]

out(f"Nodi fisici B2 : {physical_node_count:,}")
out(f"Edge CORE      : {core_edge_count:,}")
out(f"Edge LOCAL     : {local_edge_count:,}")

node_ids = np.empty(
    physical_node_count,
    dtype=np.int64,
)

i = 0

for (nid,) in cur.execute(
    """
    SELECT node_id
    FROM nodes
    ORDER BY node_id
    """
):
    node_ids[i] = int(nid)
    i += 1

if i != physical_node_count:
    raise RuntimeError("Node count mismatch.")

if np.any(node_ids[1:] <= node_ids[:-1]):
    raise RuntimeError(
        "node_id non strettamente ordinati/univoci."
    )

out("Node index costruito: OK")


# =============================================================================
# B. EDGE CORE → INDICI DENSI
# =============================================================================

out()
out("B. CARICAMENTO EDGE CORE")
out("-" * 110)

src_idx = np.empty(
    core_edge_count,
    dtype=np.int32,
)

dst_idx = np.empty(
    core_edge_count,
    dtype=np.int32,
)

read = src.cursor()

read.execute(
    """
    SELECT u, v
    FROM directed_edges
    WHERE core_eligible = 1
    ORDER BY edge_id
    """
)

pos = 0

while True:

    rows = read.fetchmany(BATCH)

    if not rows:
        break

    u_ids = np.fromiter(
        (int(r[0]) for r in rows),
        dtype=np.int64,
        count=len(rows),
    )

    v_ids = np.fromiter(
        (int(r[1]) for r in rows),
        dtype=np.int64,
        count=len(rows),
    )

    ui = np.searchsorted(
        node_ids,
        u_ids,
    )

    vi = np.searchsorted(
        node_ids,
        v_ids,
    )

    if (
        np.any(ui >= physical_node_count)
        or np.any(vi >= physical_node_count)
    ):
        raise RuntimeError(
            "Edge riferisce node_id inesistente."
        )

    if (
        np.any(node_ids[ui] != u_ids)
        or np.any(node_ids[vi] != v_ids)
    ):
        raise RuntimeError(
            "Edge riferisce node_id inesistente."
        )

    n = len(rows)

    src_idx[pos:pos+n] = ui.astype(
        np.int32,
        copy=False,
    )

    dst_idx[pos:pos+n] = vi.astype(
        np.int32,
        copy=False,
    )

    pos += n

    out(
        f"  edge caricati: "
        f"{pos:>10,} / {core_edge_count:,}"
    )

if pos != core_edge_count:
    raise RuntimeError(
        f"Edge caricati {pos}, attesi {core_edge_count}"
    )


# =============================================================================
# C. MATRICE SPARSA
# =============================================================================

out()
out("C. COSTRUZIONE MATRICE SPARSA CORE")
out("-" * 110)

data = np.ones(
    core_edge_count,
    dtype=np.bool_,
)

A = csr_matrix(
    (
        data,
        (
            src_idx,
            dst_idx,
        ),
    ),
    shape=(
        physical_node_count,
        physical_node_count,
    ),
    dtype=np.bool_,
)

A.sum_duplicates()
A.eliminate_zeros()

unique_arc_count = int(A.nnz)

parallel_directed_edges = (
    core_edge_count
    - unique_arc_count
)

out(f"Edge CORE originali : {core_edge_count:,}")
out(f"Archi u→v distinti  : {unique_arc_count:,}")
out(f"Parallelismi u→v    : {parallel_directed_edges:,}")


# =============================================================================
# D. DEGREE
# =============================================================================

out()
out("D. DEGREE QA")
out("-" * 110)

out_degree = np.bincount(
    src_idx,
    minlength=physical_node_count,
).astype(np.int32)

in_degree = np.bincount(
    dst_idx,
    minlength=physical_node_count,
).astype(np.int32)

core_incident = (
    (in_degree + out_degree) > 0
)

core_incident_count = int(
    core_incident.sum()
)

core_isolated_count = (
    physical_node_count
    - core_incident_count
)

source_only_count = int(
    (
        (in_degree == 0)
        & (out_degree > 0)
    ).sum()
)

sink_only_count = int(
    (
        (in_degree > 0)
        & (out_degree == 0)
    ).sum()
)

out(f"Nodi incidenti CORE : {core_incident_count:,}")
out(f"Nodi senza CORE     : {core_isolated_count:,}")
out(f"Source-only         : {source_only_count:,}")
out(f"Sink-only           : {sink_only_count:,}")


# =============================================================================
# E. WCC
# =============================================================================

out()
out("E. WEAKLY CONNECTED COMPONENTS")
out("-" * 110)

n_wcc, wcc_labels = connected_components(
    A,
    directed=True,
    connection="weak",
    return_labels=True,
)

wcc_sizes = np.bincount(
    wcc_labels,
    minlength=n_wcc,
)

# Componenti di singoli nodi senza CORE non ci interessano
# per definire la giant WCC stradale.
wcc_core_sizes = np.bincount(
    wcc_labels[core_incident],
    minlength=n_wcc,
)

giant_wcc_id = int(
    np.argmax(wcc_core_sizes)
)

giant_wcc_nodes = int(
    wcc_core_sizes[giant_wcc_id]
)

giant_wcc_pct_core = (
    100.0
    * giant_wcc_nodes
    / core_incident_count
)

out(f"WCC totali incl. isolati : {n_wcc:,}")
out(f"Giant WCC id             : {giant_wcc_id}")
out(f"Giant WCC nodi CORE      : {giant_wcc_nodes:,}")
out(f"Giant WCC / CORE         : {giant_wcc_pct_core:.4f}%")


# =============================================================================
# F. SCC
# =============================================================================

out()
out("F. STRONGLY CONNECTED COMPONENTS")
out("-" * 110)

n_scc, scc_labels = connected_components(
    A,
    directed=True,
    connection="strong",
    return_labels=True,
)

scc_core_sizes = np.bincount(
    scc_labels[core_incident],
    minlength=n_scc,
)

giant_scc_id = int(
    np.argmax(scc_core_sizes)
)

giant_scc_nodes = int(
    scc_core_sizes[giant_scc_id]
)

giant_scc_pct_core = (
    100.0
    * giant_scc_nodes
    / core_incident_count
)

giant_scc_pct_giant_wcc = (
    100.0
    * giant_scc_nodes
    / giant_wcc_nodes
)

out(f"SCC totali incl. isolati : {n_scc:,}")
out(f"Giant SCC id             : {giant_scc_id}")
out(f"Giant SCC nodi CORE      : {giant_scc_nodes:,}")
out(f"Giant SCC / CORE         : {giant_scc_pct_core:.4f}%")
out(
    f"Giant SCC / giant WCC    : "
    f"{giant_scc_pct_giant_wcc:.4f}%"
)


# =============================================================================
# G. UNDIRECTED NEIGHBOUR DEGREE / DANGLING
# =============================================================================

out()
out("G. DANGLING / TOPOLOGIA LOCALE")
out("-" * 110)

U = A.maximum(A.transpose()).tocsr()

undirected_degree = np.diff(
    U.indptr
).astype(np.int32)

dangling_count = int(
    (
        core_incident
        & (undirected_degree == 1)
    ).sum()
)

degree_zero_count = int(
    (
        undirected_degree == 0
    ).sum()
)

out(
    f"Nodi con 1 vicino fisico CORE : "
    f"{dangling_count:,}"
)

out(
    f"Nodi con 0 vicini CORE        : "
    f"{degree_zero_count:,}"
)


# =============================================================================
# H. TOP COMPONENTS
# =============================================================================

out()
out("H. TOP 20 SCC")
out("-" * 110)

scc_order = np.argsort(
    scc_core_sizes
)[::-1]

for rank, cid in enumerate(
    scc_order[:20],
    start=1,
):

    n = int(
        scc_core_sizes[cid]
    )

    if n == 0:
        continue

    out(
        f"{rank:>2}. "
        f"SCC {int(cid):>8} "
        f"nodes={n:>10,}"
    )


out()
out("I. TOP 20 WCC")
out("-" * 110)

wcc_order = np.argsort(
    wcc_core_sizes
)[::-1]

for rank, cid in enumerate(
    wcc_order[:20],
    start=1,
):

    n = int(
        wcc_core_sizes[cid]
    )

    if n == 0:
        continue

    out(
        f"{rank:>2}. "
        f"WCC {int(cid):>8} "
        f"nodes={n:>10,}"
    )


# =============================================================================
# I. OUTPUT SQLITE
# =============================================================================

out()
out("J. MATERIALIZZAZIONE QA")
out("-" * 110)

qa = sqlite3.connect(OUTDB)
q = qa.cursor()

q.executescript(
    """
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE node_components (
        node_id INTEGER PRIMARY KEY,

        in_degree INTEGER NOT NULL,
        out_degree INTEGER NOT NULL,
        undirected_degree INTEGER NOT NULL,

        core_incident INTEGER NOT NULL,

        scc_id INTEGER NOT NULL,
        wcc_id INTEGER NOT NULL,

        in_giant_scc INTEGER NOT NULL,
        in_giant_wcc INTEGER NOT NULL
    );

    CREATE INDEX idx_node_giant_scc
        ON node_components(in_giant_scc);

    CREATE INDEX idx_node_giant_wcc
        ON node_components(in_giant_wcc);

    CREATE INDEX idx_node_scc
        ON node_components(scc_id);

    CREATE INDEX idx_node_wcc
        ON node_components(wcc_id);

    CREATE TABLE scc_summary (
        component_id INTEGER PRIMARY KEY,
        core_node_count INTEGER NOT NULL,
        is_giant INTEGER NOT NULL
    );

    CREATE TABLE wcc_summary (
        component_id INTEGER PRIMARY KEY,
        core_node_count INTEGER NOT NULL,
        is_giant INTEGER NOT NULL
    );
    """
)

metadata = {
    "phase":
        "FASE_5_6_BUILD_B3",

    "version":
        "v01",

    "created_at":
        STAMP,

    "source_b2":
        str(B2),

    "graph_scope":
        "directed_edges where core_eligible=1",

    "physical_node_count":
        physical_node_count,

    "core_incident_node_count":
        core_incident_count,

    "core_isolated_physical_node_count":
        core_isolated_count,

    "core_edge_count":
        core_edge_count,

    "unique_directed_arc_count":
        unique_arc_count,

    "parallel_directed_edge_count":
        parallel_directed_edges,

    "source_only_node_count":
        source_only_count,

    "sink_only_node_count":
        sink_only_count,

    "dangling_core_node_count":
        dangling_count,

    "scc_count":
        n_scc,

    "giant_scc_id":
        giant_scc_id,

    "giant_scc_node_count":
        giant_scc_nodes,

    "giant_scc_pct_core":
        giant_scc_pct_core,

    "wcc_count":
        n_wcc,

    "giant_wcc_id":
        giant_wcc_id,

    "giant_wcc_node_count":
        giant_wcc_nodes,

    "giant_wcc_pct_core":
        giant_wcc_pct_core,

    "giant_scc_pct_giant_wcc":
        giant_scc_pct_giant_wcc,
}

q.executemany(
    """
    INSERT INTO metadata(
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


# ---------------------------------------------------------------------
# node_components
# ---------------------------------------------------------------------

insert_sql = """
INSERT INTO node_components(
    node_id,

    in_degree,
    out_degree,
    undirected_degree,

    core_incident,

    scc_id,
    wcc_id,

    in_giant_scc,
    in_giant_wcc
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

rows = []

for idx in range(
    physical_node_count
):

    rows.append(
        (
            int(node_ids[idx]),

            int(in_degree[idx]),
            int(out_degree[idx]),
            int(
                undirected_degree[idx]
            ),

            int(core_incident[idx]),

            int(scc_labels[idx]),
            int(wcc_labels[idx]),

            int(
                core_incident[idx]
                and
                scc_labels[idx]
                == giant_scc_id
            ),

            int(
                core_incident[idx]
                and
                wcc_labels[idx]
                == giant_wcc_id
            ),
        )
    )

    if len(rows) >= 100_000:

        q.executemany(
            insert_sql,
            rows,
        )

        qa.commit()

        rows.clear()

        out(
            f"  node_components: "
            f"{idx + 1:>10,} / "
            f"{physical_node_count:,}"
        )

if rows:
    q.executemany(
        insert_sql,
        rows,
    )

    qa.commit()


# ---------------------------------------------------------------------
# component summaries
# ---------------------------------------------------------------------

q.executemany(
    """
    INSERT INTO scc_summary(
        component_id,
        core_node_count,
        is_giant
    )
    VALUES (?, ?, ?)
    """,
    [
        (
            int(cid),
            int(n),
            int(cid == giant_scc_id),
        )
        for cid, n
        in enumerate(scc_core_sizes)
        if n > 0
    ],
)

q.executemany(
    """
    INSERT INTO wcc_summary(
        component_id,
        core_node_count,
        is_giant
    )
    VALUES (?, ?, ?)
    """,
    [
        (
            int(cid),
            int(n),
            int(cid == giant_wcc_id),
        )
        for cid, n
        in enumerate(wcc_core_sizes)
        if n > 0
    ],
)

qa.commit()

q.execute(
    "PRAGMA wal_checkpoint(TRUNCATE)"
)

qa.commit()
qa.close()


# =============================================================================
# K. FINALIZZAZIONE
# =============================================================================

src.close()

out()
out("K. FINALIZZAZIONE")
out("-" * 110)

out(f"QA SQLite prodotto : {OUTDB}")
out(f"Dimensione          : {OUTDB.stat().st_size:,} bytes")

out()
out("=" * 110)
out("ESITO BUILD B3: QA_READY")
out("=" * 110)

out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
