from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import json
import sqlite3

import numpy as np

from scipy.sparse import csr_matrix, save_npz
from scipy.sparse.csgraph import dijkstra


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

B3 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b3\osm_core_connectivity_qa_v01.sqlite"
)

B4 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b4\osm_turn_restrictions_compiled_v01.sqlite"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b5"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUTDB = OUTDIR / "osm_turn_state_index_v01.sqlite"

TIME_NPZ = OUTDIR / "osm_turn_state_time_v01.npz"
LENGTH_NPZ = OUTDIR / "osm_turn_state_length_v01.npz"
EDGEID_NPZ = OUTDIR / "osm_turn_state_edgeid_v01.npz"

BASE_NODES_NPY = OUTDIR / "osm_turn_state_base_nodes_v01.npy"
STATE_NODE_NPY = OUTDIR / "osm_turn_state_node_id_v01.npy"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"build_osm_turn_aware_state_graph_v01_{STAMP}.txt"


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
out("FASE 5.6 — BUILD B5 — TURN-AWARE SELECTIVE STATE GRAPH")
out("=" * 110)

out(f"B2 directed      : {B2}")
out(f"B3 connectivity  : {B3}")
out(f"B4 restrictions  : {B4}")
out(f"Output index     : {OUTDB}")

for p in [B2, B3, B4]:
    if not p.exists():
        raise FileNotFoundError(p)

for p in [
    OUTDB,
    TIME_NPZ,
    LENGTH_NPZ,
    EDGEID_NPZ,
    BASE_NODES_NPY,
    STATE_NODE_NPY,
]:
    if p.exists():
        raise RuntimeError(
            f"Output già esistente: {p}\n"
            "Non sovrascrivo output versionati."
        )


# =============================================================================
# A. LOAD CORE RESTRICTION SEQUENCES
# =============================================================================

out()
out("A. CARICAMENTO RESTRICTION CORE")
out("-" * 110)

b4 = sqlite3.connect(B4)
b4.row_factory = sqlite3.Row
c4 = b4.cursor()

rows = c4.execute(
    """
    SELECT
        sequence_id,
        relation_id,
        rule_kind,
        edge_ids_json

    FROM restriction_sequences

    WHERE core_only = 1

    ORDER BY
        relation_id,
        variant_index
    """
).fetchall()

sequences = []

for r in rows:

    edge_ids = tuple(
        int(x)
        for x in json.loads(
            r["edge_ids_json"]
        )
    )

    sequences.append({
        "sequence_id":
            int(r["sequence_id"]),

        "relation_id":
            int(r["relation_id"]),

        "rule_kind":
            str(r["rule_kind"]),

        "edges":
            edge_ids,
    })

out(f"Sequenze CORE: {len(sequences):,}")

rule_counts = Counter(
    x["rule_kind"]
    for x in sequences
)

for k, n in rule_counts.items():
    out(f"{k:<25} {n:>8,}")


# =============================================================================
# B. BUILD PREFIX AUTOMATON RULES
# =============================================================================

out()
out("B. COSTRUZIONE PREFIX AUTOMATON")
out("-" * 110)

prefix_set = set()

no_forbidden = defaultdict(set)

# prefix -> relation_id -> allowed next edges
only_allowed = defaultdict(
    lambda: defaultdict(set)
)

for s in sequences:

    seq = s["edges"]
    relation_id = s["relation_id"]
    rule_kind = s["rule_kind"]

    if len(seq) < 2:
        raise RuntimeError(
            f"Restriction troppo corta: {s}"
        )

    # Tutti i prefissi propri servono
    # come memoria dell'automa.
    for k in range(1, len(seq)):
        prefix_set.add(
            seq[:k]
        )

    if rule_kind == "NO_SEQUENCE":

        prefix = seq[:-1]
        forbidden = seq[-1]

        no_forbidden[
            prefix
        ].add(
            forbidden
        )

    elif rule_kind == "ONLY_SEQUENCE":

        # Una volta entrati nella manovra ONLY,
        # ogni prefisso deve continuare sulla
        # sequenza autorizzata.
        for k in range(
            1,
            len(seq)
        ):

            prefix = seq[:k]
            allowed_next = seq[k]

            only_allowed[
                prefix
            ][
                relation_id
            ].add(
                allowed_next
            )

    else:
        raise RuntimeError(
            f"rule_kind sconosciuto: {rule_kind}"
        )


prefixes = sorted(
    prefix_set,
    key=lambda p: (
        len(p),
        p,
    )
)

max_prefix_len = max(
    len(p)
    for p in prefixes
)

out(f"Prefissi distinti      : {len(prefixes):,}")
out(f"Lunghezza max prefisso : {max_prefix_len}")


# =============================================================================
# C. EDGE METADATA PER I PREFISSI
# =============================================================================

out()
out("C. CARICAMENTO EDGE CORE B2")
out("-" * 110)

b2 = sqlite3.connect(B2)
b2.row_factory = sqlite3.Row
c2 = b2.cursor()

core_edge_count = c2.execute(
    """
    SELECT COUNT(*)
    FROM directed_edges
    WHERE core_eligible = 1
    """
).fetchone()[0]

edge_ids = np.empty(
    core_edge_count,
    dtype=np.int64,
)

u_ids = np.empty(
    core_edge_count,
    dtype=np.int64,
)

v_ids = np.empty(
    core_edge_count,
    dtype=np.int64,
)

time_s = np.empty(
    core_edge_count,
    dtype=np.float64,
)

length_m = np.empty(
    core_edge_count,
    dtype=np.float64,
)

i = 0

read = c2.execute(
    """
    SELECT
        edge_id,
        u,
        v,
        time_s,
        length_m

    FROM directed_edges

    WHERE core_eligible = 1

    ORDER BY edge_id
    """
)

for r in read:

    edge_ids[i] = int(
        r["edge_id"]
    )

    u_ids[i] = int(
        r["u"]
    )

    v_ids[i] = int(
        r["v"]
    )

    time_s[i] = float(
        r["time_s"]
    )

    length_m[i] = float(
        r["length_m"]
    )

    i += 1

if i != core_edge_count:
    raise RuntimeError(
        "Core edge count mismatch."
    )

if np.any(
    edge_ids[1:]
    <= edge_ids[:-1]
):
    raise RuntimeError(
        "edge_id CORE non strettamente ordinati."
    )

out(f"Edge CORE caricati: {core_edge_count:,}")


# =============================================================================
# D. BASE STATES
# =============================================================================

out()
out("D. COSTRUZIONE BASE STATES")
out("-" * 110)

base_node_ids = np.unique(
    np.concatenate(
        [
            u_ids,
            v_ids,
        ]
    )
)

base_state_count = len(
    base_node_ids
)

np.save(
    BASE_NODES_NPY,
    base_node_ids,
)

out(f"Base states / nodi CORE: {base_state_count:,}")


def node_to_base_state(
    node_id,
):

    idx = int(
        np.searchsorted(
            base_node_ids,
            int(node_id),
        )
    )

    if (
        idx >= base_state_count
        or
        base_node_ids[idx]
        != int(node_id)
    ):
        raise RuntimeError(
            f"Nodo CORE non trovato: {node_id}"
        )

    return idx


# =============================================================================
# E. PREFIX STATES
# =============================================================================

out()
out("E. COSTRUZIONE PREFIX STATES")
out("-" * 110)

# Recupero v dell'ultimo edge di ogni prefisso.
restricted_edge_ids = sorted(
    {
        eid
        for p in prefixes
        for eid in p
    }
)

edge_end_node = {}

for eid in restricted_edge_ids:

    pos = int(
        np.searchsorted(
            edge_ids,
            eid,
        )
    )

    if (
        pos >= len(edge_ids)
        or
        edge_ids[pos] != eid
    ):
        raise RuntimeError(
            f"Edge restriction non CORE: {eid}"
        )

    edge_end_node[eid] = int(
        v_ids[pos]
    )


prefix_state_id = {}

prefix_state_node = {}

for j, p in enumerate(
    prefixes
):

    sid = (
        base_state_count
        + j
    )

    prefix_state_id[p] = sid

    prefix_state_node[p] = (
        edge_end_node[
            p[-1]
        ]
    )


prefix_state_count = len(
    prefixes
)

state_count = (
    base_state_count
    + prefix_state_count
)

state_node_id = np.empty(
    state_count,
    dtype=np.int64,
)

state_node_id[
    :base_state_count
] = base_node_ids

for p in prefixes:

    state_node_id[
        prefix_state_id[p]
    ] = prefix_state_node[p]

np.save(
    STATE_NODE_NPY,
    state_node_id,
)

out(f"Prefix states : {prefix_state_count:,}")
out(f"State totali  : {state_count:,}")


# =============================================================================
# F. RESTRICTION LOGIC
# =============================================================================

def active_suffixes(prefix):

    for k in range(
        1,
        len(prefix) + 1
    ):

        suffix = prefix[-k:]

        if (
            suffix in no_forbidden
            or
            suffix in only_allowed
        ):
            yield suffix


def candidate_allowed(
    prefix,
    candidate_edge,
):

    candidate_edge = int(
        candidate_edge
    )

    for suffix in active_suffixes(
        prefix
    ):

        # NO restriction
        if (
            candidate_edge
            in
            no_forbidden.get(
                suffix,
                set(),
            )
        ):
            return False

        # ONLY restriction:
        # tutte le relation attive devono
        # ammettere il candidate edge.
        rel_map = only_allowed.get(
            suffix
        )

        if rel_map:

            for allowed_set in rel_map.values():

                if (
                    candidate_edge
                    not in allowed_set
                ):
                    return False

    return True


def advance_prefix(
    prefix,
    candidate_edge,
):

    combined = (
        prefix
        + (int(candidate_edge),)
    )

    max_len = min(
        len(combined),
        max_prefix_len,
    )

    for k in range(
        max_len,
        0,
        -1,
    ):

        suffix = combined[-k:]

        if suffix in prefix_set:
            return suffix

    return ()


# =============================================================================
# G. RULE SELF-TEST
# =============================================================================

out()
out("F. SELF-TEST RESTRICTION RULES")
out("-" * 110)

rule_errors = []

for s in sequences:

    seq = s["edges"]
    relation_id = s["relation_id"]
    rule_kind = s["rule_kind"]

    if rule_kind == "NO_SEQUENCE":

        p = seq[:-1]

        if (
            seq[-1]
            not in
            no_forbidden[p]
        ):

            rule_errors.append(
                (
                    relation_id,
                    "NO_RULE_MISSING",
                )
            )

    elif rule_kind == "ONLY_SEQUENCE":

        for k in range(
            1,
            len(seq)
        ):

            p = seq[:k]
            expected = seq[k]

            allowed = (
                only_allowed[
                    p
                ][
                    relation_id
                ]
            )

            if expected not in allowed:

                rule_errors.append(
                    (
                        relation_id,
                        "ONLY_RULE_MISSING",
                        k,
                    )
                )


out(f"Errori rule self-test: {len(rule_errors):,}")

if rule_errors:

    out(
        "Esempi: "
        + str(rule_errors[:20])
    )

    raise RuntimeError(
        "Restriction rule self-test fallito."
    )


# =============================================================================
# H. BASE TRANSITIONS
# =============================================================================

out()
out("G. COSTRUZIONE TRANSIZIONI BASE")
out("-" * 110)

base_src = np.searchsorted(
    base_node_ids,
    u_ids,
).astype(
    np.int64
)

base_dst = np.searchsorted(
    base_node_ids,
    v_ids,
).astype(
    np.int64
)

# Se un edge apre almeno una restriction,
# invece di entrare nello stato base del nodo
# si entra nello stato di memoria (edge,).
single_prefix = {
    p[0]: prefix_state_id[p]

    for p in prefixes
    if len(p) == 1
}

for eid, sid in single_prefix.items():

    pos = int(
        np.searchsorted(
            edge_ids,
            eid,
        )
    )

    if (
        pos >= len(edge_ids)
        or
        edge_ids[pos] != eid
    ):
        raise RuntimeError(
            f"First restriction edge assente: {eid}"
        )

    base_dst[pos] = sid


out(
    f"Transizioni base: "
    f"{len(base_src):,}"
)

out(
    f"Edge che attivano memoria: "
    f"{len(single_prefix):,}"
)


# =============================================================================
# I. PREFIX TRANSITIONS
# =============================================================================

out()
out("H. COSTRUZIONE TRANSIZIONI MEMORY-STATE")
out("-" * 110)

extra_src = []
extra_dst = []
extra_edge = []
extra_time = []
extra_length = []

blocked_total = 0
blocked_no = 0
blocked_only = 0


for number, p in enumerate(
    prefixes,
    start=1,
):

    source_state = prefix_state_id[p]

    physical_node = prefix_state_node[p]

    outgoing = c2.execute(
        """
        SELECT
            edge_id,
            v,
            time_s,
            length_m

        FROM directed_edges

        WHERE
            core_eligible = 1
            AND u = ?

        ORDER BY edge_id
        """,
        (physical_node,),
    ).fetchall()

    for r in outgoing:

        eid = int(
            r["edge_id"]
        )

        allowed = candidate_allowed(
            p,
            eid,
        )

        if not allowed:

            blocked_total += 1

            # Diagnostica prevalente
            is_no = False
            is_only = False

            for suffix in active_suffixes(p):

                if (
                    eid
                    in
                    no_forbidden.get(
                        suffix,
                        set(),
                    )
                ):
                    is_no = True

                rel_map = only_allowed.get(
                    suffix
                )

                if rel_map:

                    for aset in rel_map.values():

                        if eid not in aset:
                            is_only = True

            if is_no:
                blocked_no += 1

            if is_only:
                blocked_only += 1

            continue

        new_prefix = advance_prefix(
            p,
            eid,
        )

        if new_prefix:

            target_state = (
                prefix_state_id[
                    new_prefix
                ]
            )

        else:

            target_state = (
                node_to_base_state(
                    int(r["v"])
                )
            )

        extra_src.append(
            source_state
        )

        extra_dst.append(
            target_state
        )

        extra_edge.append(
            eid
        )

        extra_time.append(
            float(r["time_s"])
        )

        extra_length.append(
            float(r["length_m"])
        )

    if number % 1000 == 0:

        out(
            f"  prefix states "
            f"{number:>7,}/"
            f"{len(prefixes):,} | "
            f"extra transitions="
            f"{len(extra_src):>8,} | "
            f"blocked="
            f"{blocked_total:>7,}"
        )


extra_src = np.asarray(
    extra_src,
    dtype=np.int64,
)

extra_dst = np.asarray(
    extra_dst,
    dtype=np.int64,
)

extra_edge = np.asarray(
    extra_edge,
    dtype=np.int64,
)

extra_time = np.asarray(
    extra_time,
    dtype=np.float64,
)

extra_length = np.asarray(
    extra_length,
    dtype=np.float64,
)

out()
out(f"Extra transition      : {len(extra_src):,}")
out(f"Transition bloccate   : {blocked_total:,}")
out(f"  con NO coinvolta    : {blocked_no:,}")
out(f"  con ONLY coinvolta  : {blocked_only:,}")


# =============================================================================
# J. MERGE TRANSITIONS
# =============================================================================

out()
out("I. MERGE STATE GRAPH")
out("-" * 110)

all_src = np.concatenate(
    [
        base_src,
        extra_src,
    ]
)

all_dst = np.concatenate(
    [
        base_dst,
        extra_dst,
    ]
)

all_edge = np.concatenate(
    [
        edge_ids,
        extra_edge,
    ]
)

all_time = np.concatenate(
    [
        time_s,
        extra_time,
    ]
)

all_length = np.concatenate(
    [
        length_m,
        extra_length,
    ]
)

transition_count = len(
    all_src
)

out(
    f"Transizioni totali: "
    f"{transition_count:,}"
)


# =============================================================================
# K. UNIQUE SRC-DST CHECK
# =============================================================================

out()
out("J. CHECK UNICITÀ STATE TRANSITIONS")
out("-" * 110)

packed = (
    all_src.astype(np.int64)
    * np.int64(state_count)
    + all_dst.astype(np.int64)
)

unique_transition_count = len(
    np.unique(packed)
)

duplicate_transition_count = (
    transition_count
    - unique_transition_count
)

out(
    f"Duplicati src→dst: "
    f"{duplicate_transition_count:,}"
)

if duplicate_transition_count != 0:

    raise RuntimeError(
        "State graph contiene transizioni "
        "src→dst multiple: path reconstruction "
        "non univoca."
    )


# =============================================================================
# L. BUILD SPARSE MATRICES
# =============================================================================

out()
out("K. COSTRUZIONE MATRICI SPARSE")
out("-" * 110)

shape = (
    state_count,
    state_count,
)

TIME = csr_matrix(
    (
        all_time,
        (
            all_src,
            all_dst,
        ),
    ),
    shape=shape,
)

LENGTH = csr_matrix(
    (
        all_length,
        (
            all_src,
            all_dst,
        ),
    ),
    shape=shape,
)

EDGEID = csr_matrix(
    (
        all_edge,
        (
            all_src,
            all_dst,
        ),
    ),
    shape=shape,
    dtype=np.int64,
)

TIME.sum_duplicates()
LENGTH.sum_duplicates()
EDGEID.sum_duplicates()

if (
    TIME.nnz != transition_count
    or
    LENGTH.nnz != transition_count
    or
    EDGEID.nnz != transition_count
):
    raise RuntimeError(
        "Sparse matrix nnz mismatch."
    )

save_npz(
    TIME_NPZ,
    TIME,
)

save_npz(
    LENGTH_NPZ,
    LENGTH,
)

save_npz(
    EDGEID_NPZ,
    EDGEID,
)

out(f"TIME nnz   : {TIME.nnz:,}")
out(f"LENGTH nnz : {LENGTH.nnz:,}")
out(f"EDGEID nnz : {EDGEID.nnz:,}")


# =============================================================================
# M. WRITE INDEX DB
# =============================================================================

out()
out("L. MATERIALIZZAZIONE STATE INDEX")
out("-" * 110)

db = sqlite3.connect(OUTDB)
cur = db.cursor()

cur.executescript(
    """
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;

    CREATE TABLE metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE prefix_states (
        state_id INTEGER PRIMARY KEY,

        physical_node_id INTEGER NOT NULL,

        prefix_len INTEGER NOT NULL,

        prefix_edge_ids_json TEXT NOT NULL
    );

    CREATE INDEX idx_prefix_node
        ON prefix_states(physical_node_id);

    CREATE TABLE no_rules (
        prefix_edge_ids_json TEXT NOT NULL,
        forbidden_edge_id INTEGER NOT NULL,

        PRIMARY KEY(
            prefix_edge_ids_json,
            forbidden_edge_id
        )
    );

    CREATE TABLE only_rules (
        prefix_edge_ids_json TEXT NOT NULL,
        relation_id INTEGER NOT NULL,
        allowed_edge_id INTEGER NOT NULL,

        PRIMARY KEY(
            prefix_edge_ids_json,
            relation_id,
            allowed_edge_id
        )
    );
    """
)

metadata = {
    "phase":
        "FASE_5_6_BUILD_B5",

    "version":
        "v01",

    "created_at":
        STAMP,

    "source_b2":
        str(B2),

    "source_b4":
        str(B4),

    "routing_scope":
        "CORE edges only",

    "restriction_model":
        "selective prefix-state expansion",

    "base_state_count":
        base_state_count,

    "prefix_state_count":
        prefix_state_count,

    "total_state_count":
        state_count,

    "transition_count":
        transition_count,

    "restriction_sequence_core_count":
        len(sequences),

    "max_prefix_length":
        max_prefix_len,

    "blocked_transition_count":
        blocked_total,

    "time_matrix":
        str(TIME_NPZ),

    "length_matrix":
        str(LENGTH_NPZ),

    "edgeid_matrix":
        str(EDGEID_NPZ),

    "base_nodes_array":
        str(BASE_NODES_NPY),

    "state_node_array":
        str(STATE_NODE_NPY),
}

cur.executemany(
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


cur.executemany(
    """
    INSERT INTO prefix_states(
        state_id,
        physical_node_id,
        prefix_len,
        prefix_edge_ids_json
    )
    VALUES (?, ?, ?, ?)
    """,
    [
        (
            int(prefix_state_id[p]),

            int(
                prefix_state_node[p]
            ),

            len(p),

            json.dumps(
                list(p),
                separators=(",", ":"),
            ),
        )
        for p in prefixes
    ],
)


no_rows = []

for p, forbidden_set in (
    no_forbidden.items()
):

    p_json = json.dumps(
        list(p),
        separators=(",", ":"),
    )

    for eid in forbidden_set:

        no_rows.append(
            (
                p_json,
                int(eid),
            )
        )

cur.executemany(
    """
    INSERT INTO no_rules(
        prefix_edge_ids_json,
        forbidden_edge_id
    )
    VALUES (?, ?)
    """,
    no_rows,
)


only_rows = []

for p, rel_map in (
    only_allowed.items()
):

    p_json = json.dumps(
        list(p),
        separators=(",", ":"),
    )

    for relation_id, allowed_set in (
        rel_map.items()
    ):

        for eid in allowed_set:

            only_rows.append(
                (
                    p_json,
                    int(relation_id),
                    int(eid),
                )
            )

cur.executemany(
    """
    INSERT INTO only_rules(
        prefix_edge_ids_json,
        relation_id,
        allowed_edge_id
    )
    VALUES (?, ?, ?)
    """,
    only_rows,
)

db.commit()

cur.execute(
    "PRAGMA wal_checkpoint(TRUNCATE)"
)

db.commit()
db.close()


# =============================================================================
# N. ROUTING SMOKE TEST
# =============================================================================

out()
out("M. TURN-AWARE ROUTING SMOKE TEST")
out("-" * 110)

b3 = sqlite3.connect(B3)
c3 = b3.cursor()

source_node = c3.execute(
    """
    SELECT node_id
    FROM node_components
    WHERE in_giant_scc = 1
    ORDER BY node_id
    LIMIT 1
    """
).fetchone()[0]

b3.close()

source_state = node_to_base_state(
    source_node
)

out(f"Source node  : {source_node}")
out(f"Source state : {source_state}")

dist = dijkstra(
    TIME,
    directed=True,
    indices=source_state,
    return_predecessors=False,
)

finite_states = np.isfinite(
    dist
)

reachable_state_count = int(
    finite_states.sum()
)

reachable_physical_nodes = len(
    np.unique(
        state_node_id[
            finite_states
        ]
    )
)

out(
    f"State raggiungibili       : "
    f"{reachable_state_count:,}"
)

out(
    f"Nodi fisici raggiungibili : "
    f"{reachable_physical_nodes:,}"
)

out(
    f"Quota nodi CORE            : "
    f"{100.0 * reachable_physical_nodes / base_state_count:.4f}%"
)

if reachable_physical_nodes < 0.95 * base_state_count:

    raise RuntimeError(
        "Smoke test turn-aware: reachability "
        "insolitamente bassa (<95% CORE)."
    )


# =============================================================================
# O. FINAL QA
# =============================================================================

out()
out("N. FINAL QA")
out("-" * 110)

out(
    f"Base states            : "
    f"{base_state_count:,}"
)

out(
    f"Prefix states          : "
    f"{prefix_state_count:,}"
)

out(
    f"Incremento stati       : "
    f"{100.0 * prefix_state_count / base_state_count:.4f}%"
)

out(
    f"Transition base        : "
    f"{core_edge_count:,}"
)

out(
    f"Transition extra       : "
    f"{len(extra_src):,}"
)

out(
    f"Transition totali      : "
    f"{transition_count:,}"
)

out(
    f"Restriction CORE       : "
    f"{len(sequences):,}"
)

out(
    f"Rule self-test errors  : "
    f"{len(rule_errors):,}"
)

out(
    f"Duplicate state arcs   : "
    f"{duplicate_transition_count:,}"
)


# =============================================================================
# P. FINALIZZAZIONE
# =============================================================================

b2.close()
b4.close()

out()
out("O. FINALIZZAZIONE")
out("-" * 110)

out(f"Index DB       : {OUTDB}")
out(f"TIME matrix    : {TIME_NPZ}")
out(f"LENGTH matrix  : {LENGTH_NPZ}")
out(f"EDGEID matrix  : {EDGEID_NPZ}")

out()
out("=" * 110)
out("ESITO BUILD B5: PASS")
out("=" * 110)

out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
