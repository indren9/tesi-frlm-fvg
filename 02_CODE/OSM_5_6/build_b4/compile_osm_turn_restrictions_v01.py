from pathlib import Path
from datetime import datetime
from functools import lru_cache
from itertools import product
from collections import Counter
import json
import math
import sqlite3


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B1 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b1\osm_topology_raw_v01.sqlite"
)

B2 = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / r"build_b2\osm_directed_edges_v02.sqlite"
)

OUTDIR = (
    ROOT
    / r"03_output_temporanei\fase_5_6_osm_operativo"
    / "build_b4"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUTDB = OUTDIR / "osm_turn_restrictions_compiled_v01.sqlite"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"compile_osm_turn_restrictions_v01_{STAMP}.txt"

MAX_CONNECTION_COMBINATIONS = 200
MAX_PATH_VARIANTS_PER_WAY = 20


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
out("FASE 5.6 — BUILD B4 — COMPILE OSM TURN RESTRICTIONS")
out("=" * 110)

out(f"B1 restrictions : {B1}")
out(f"B2 directed     : {B2}")
out(f"Output          : {OUTDB}")

if not B1.exists():
    raise FileNotFoundError(B1)

if not B2.exists():
    raise FileNotFoundError(B2)

if OUTDB.exists():
    raise RuntimeError(
        f"Output già esistente: {OUTDB}\n"
        "Non sovrascrivo output versionati."
    )


b1 = sqlite3.connect(B1)
b1.row_factory = sqlite3.Row
c1 = b1.cursor()

b2 = sqlite3.connect(B2)
b2.row_factory = sqlite3.Row
c2 = b2.cursor()


# =============================================================================
# A. CACHE TOPOLOGICA
# =============================================================================

out()
out("A. PREPARAZIONE CACHE TOPOLOGICA")
out("-" * 110)


@lru_cache(maxsize=None)
def get_way_nodes(way_id):

    rows = c1.execute(
        """
        SELECT seq, node_id
        FROM way_nodes
        WHERE way_id = ?
        ORDER BY seq
        """,
        (int(way_id),),
    ).fetchall()

    return tuple(
        int(r["node_id"])
        for r in rows
    )


@lru_cache(maxsize=None)
def get_way_node_set(way_id):
    return frozenset(
        get_way_nodes(way_id)
    )


@lru_cache(maxsize=None)
def get_way_edges(way_id):

    rows = c2.execute(
        """
        SELECT
            edge_id,
            edge_uid,

            way_id,
            seq,

            u,
            v,

            way_direction,

            routing_code,
            core_eligible

        FROM directed_edges

        WHERE way_id = ?

        ORDER BY seq, way_direction
        """,
        (int(way_id),),
    ).fetchall()

    out_rows = []

    for r in rows:

        out_rows.append({
            "edge_id":
                int(r["edge_id"]),

            "edge_uid":
                str(r["edge_uid"]),

            "way_id":
                int(r["way_id"]),

            "seq":
                int(r["seq"]),

            "u":
                int(r["u"]),

            "v":
                int(r["v"]),

            "way_direction":
                str(r["way_direction"]),

            "routing_code":
                int(r["routing_code"]),

            "core_eligible":
                int(r["core_eligible"]),
        })

    return tuple(out_rows)


@lru_cache(maxsize=None)
def get_way_edge_lookup(way_id):

    return {
        (
            e["seq"],
            e["way_direction"],
        ): e

        for e in get_way_edges(way_id)
    }


def incoming_edges(
    way_id,
    node_id,
):

    return [
        e
        for e in get_way_edges(way_id)
        if e["v"] == int(node_id)
    ]


def outgoing_edges(
    way_id,
    node_id,
):

    return [
        e
        for e in get_way_edges(way_id)
        if e["u"] == int(node_id)
    ]


def shared_nodes(
    way_a,
    way_b,
):

    return sorted(
        get_way_node_set(way_a)
        &
        get_way_node_set(way_b)
    )


# =============================================================================
# B. PATH SU UNA SINGOLA OSM WAY
# =============================================================================

def directed_paths_on_way(
    way_id,
    start_node,
    end_node,
):
    """
    Restituisce le sequenze di edge routabili appartenenti a una singola
    OSM way che consentono di andare da start_node a end_node.

    Usa l'ordine nativo dei node della way:
      i < j => FWD
      i > j => BWD
    """

    way_id = int(way_id)
    start_node = int(start_node)
    end_node = int(end_node)

    nodes = get_way_nodes(way_id)
    lookup = get_way_edge_lookup(way_id)

    starts = [
        i for i, n in enumerate(nodes)
        if n == start_node
    ]

    ends = [
        i for i, n in enumerate(nodes)
        if n == end_node
    ]

    variants = []

    for i in starts:

        for j in ends:

            if i == j:
                continue

            seq_edges = []

            valid = True

            # ---------------------------------------------------------
            # FWD
            # ---------------------------------------------------------

            if i < j:

                for seq in range(i, j):

                    e = lookup.get(
                        (seq, "FWD")
                    )

                    if e is None:
                        valid = False
                        break

                    seq_edges.append(e)

            # ---------------------------------------------------------
            # BWD
            # ---------------------------------------------------------

            else:

                for seq in range(
                    i - 1,
                    j - 1,
                    -1,
                ):

                    e = lookup.get(
                        (seq, "BWD")
                    )

                    if e is None:
                        valid = False
                        break

                    seq_edges.append(e)

            if valid and seq_edges:

                # controllo continuità
                ok = True

                for a, b in zip(
                    seq_edges[:-1],
                    seq_edges[1:],
                ):

                    if a["v"] != b["u"]:
                        ok = False
                        break

                if ok:
                    variants.append(
                        tuple(seq_edges)
                    )

    # deduplica per edge_uid
    unique = {}

    for seq_edges in variants:

        key = tuple(
            e["edge_uid"]
            for e in seq_edges
        )

        unique[key] = seq_edges

    variants = list(
        unique.values()
    )

    if len(variants) > MAX_PATH_VARIANTS_PER_WAY:

        return None

    return variants


# =============================================================================
# C. COMPILAZIONE VIA-NODE
# =============================================================================

def compile_via_node(
    from_way,
    via_node,
    to_way,
):

    incoming = incoming_edges(
        from_way,
        via_node,
    )

    outgoing = outgoing_edges(
        to_way,
        via_node,
    )

    sequences = []

    for e_in in incoming:

        for e_out in outgoing:

            if e_in["v"] != e_out["u"]:
                continue

            sequences.append(
                (
                    e_in,
                    e_out,
                )
            )

    unique = {}

    for seq_edges in sequences:

        key = tuple(
            e["edge_uid"]
            for e in seq_edges
        )

        unique[key] = seq_edges

    return list(unique.values())


# =============================================================================
# D. COMPILAZIONE VIA-WAY
# =============================================================================

def compile_via_way(
    from_way,
    via_ways,
    to_way,
):

    chain = (
        [int(from_way)]
        + [int(x) for x in via_ways]
        + [int(to_way)]
    )

    connection_options = []

    for a, b in zip(
        chain[:-1],
        chain[1:],
    ):

        shared = shared_nodes(
            a,
            b,
        )

        if not shared:
            return (
                "NO_SHARED_NODE",
                [],
            )

        connection_options.append(
            shared
        )

    combination_count = 1

    for opts in connection_options:
        combination_count *= len(opts)

    if (
        combination_count
        > MAX_CONNECTION_COMBINATIONS
    ):

        return (
            "AMBIGUOUS_CONNECTIONS",
            [],
        )

    compiled = []

    for connections in product(
        *connection_options
    ):

        entry_node = connections[0]
        exit_node = connections[-1]

        incoming = incoming_edges(
            from_way,
            entry_node,
        )

        outgoing = outgoing_edges(
            to_way,
            exit_node,
        )

        if not incoming or not outgoing:
            continue

        via_path_options = []

        valid_connections = True

        for idx, via_way in enumerate(
            via_ways
        ):

            start = connections[idx]
            end = connections[idx + 1]

            variants = directed_paths_on_way(
                via_way,
                start,
                end,
            )

            if variants is None:
                return (
                    "AMBIGUOUS_VIA_WAY_PATH",
                    [],
                )

            if not variants:
                valid_connections = False
                break

            via_path_options.append(
                variants
            )

        if not valid_connections:
            continue

        for e_in in incoming:

            for via_variant_tuple in product(
                *via_path_options
            ):

                middle = []

                for part in via_variant_tuple:
                    middle.extend(part)

                for e_out in outgoing:

                    seq_edges = (
                        [e_in]
                        + middle
                        + [e_out]
                    )

                    connected = True

                    for a, b in zip(
                        seq_edges[:-1],
                        seq_edges[1:],
                    ):

                        if a["v"] != b["u"]:
                            connected = False
                            break

                    if connected:
                        compiled.append(
                            tuple(seq_edges)
                        )

    unique = {}

    for seq_edges in compiled:

        key = tuple(
            e["edge_uid"]
            for e in seq_edges
        )

        unique[key] = seq_edges

    return (
        "OK",
        list(unique.values()),
    )


# =============================================================================
# E. OUTPUT DB
# =============================================================================

out()
out("B. INIZIALIZZAZIONE OUTPUT")
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

    CREATE TABLE relation_compile_summary (
        relation_id INTEGER PRIMARY KEY,

        restriction_value TEXT,
        via_class TEXT,
        rule_kind TEXT,

        conditional_raw TEXT,
        except_raw TEXT,

        compile_status TEXT NOT NULL,

        sequence_count INTEGER NOT NULL,
        core_sequence_count INTEGER NOT NULL,

        min_edge_count INTEGER,
        max_edge_count INTEGER,

        notes TEXT
    );

    CREATE TABLE restriction_sequences (
        sequence_id INTEGER PRIMARY KEY,

        relation_id INTEGER NOT NULL,
        variant_index INTEGER NOT NULL,

        restriction_value TEXT NOT NULL,
        via_class TEXT NOT NULL,

        rule_kind TEXT NOT NULL,

        edge_count INTEGER NOT NULL,

        start_edge_id INTEGER NOT NULL,
        end_edge_id INTEGER NOT NULL,

        start_node INTEGER NOT NULL,
        end_node INTEGER NOT NULL,

        core_only INTEGER NOT NULL,

        edge_ids_json TEXT NOT NULL,
        edge_uids_json TEXT NOT NULL,

        UNIQUE(
            relation_id,
            variant_index
        )
    );

    CREATE INDEX idx_sequence_relation
        ON restriction_sequences(relation_id);

    CREATE INDEX idx_sequence_core
        ON restriction_sequences(core_only);

    CREATE INDEX idx_sequence_rule
        ON restriction_sequences(rule_kind);

    CREATE TABLE restriction_sequence_edges (
        sequence_id INTEGER NOT NULL,
        position INTEGER NOT NULL,

        edge_id INTEGER NOT NULL,
        edge_uid TEXT NOT NULL,

        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,

        u INTEGER NOT NULL,
        v INTEGER NOT NULL,

        core_eligible INTEGER NOT NULL,

        PRIMARY KEY(
            sequence_id,
            position
        )
    );

    CREATE INDEX idx_rse_edge
        ON restriction_sequence_edges(edge_id);

    CREATE INDEX idx_rse_uid
        ON restriction_sequence_edges(edge_uid);
    """
)


metadata = {
    "phase":
        "FASE_5_6_BUILD_B4",

    "version":
        "v01",

    "created_at":
        STAMP,

    "source_b1":
        str(B1),

    "source_b2":
        str(B2),

    "scope":
        "STATIC_CANONICAL + STATIC_PLUS_CONDITIONAL motorcar restrictions",

    "rule_model":
        "ordered directed-edge sequences",

    "no_rule_semantics":
        "forbid completion of exact sequence",

    "only_rule_semantics":
        "once prefix entered, require continuation of exact sequence",

    "via_node_support":
        "YES",

    "via_way_support":
        "YES",
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

db.commit()


# =============================================================================
# F. INVENTARIO INPUT
# =============================================================================

out()
out("C. INVENTARIO RESTRICTION DA COMPILARE")
out("-" * 110)

restrictions = c1.execute(
    """
    SELECT
        relation_id,
        restriction_value,
        restriction_conditional,
        except_raw,
        via_class,
        members_json,
        status

    FROM restrictions_raw

    WHERE
        in_scope = 1
        AND applies_to_motorcar = 1
        AND canonical_structure = 1
        AND status IN (
            'STATIC_CANONICAL',
            'STATIC_PLUS_CONDITIONAL'
        )

    ORDER BY relation_id
    """
).fetchall()

out(
    f"Restriction canoniche in-scope: "
    f"{len(restrictions):,}"
)

input_via_class = Counter(
    str(r["via_class"])
    for r in restrictions
)

for k, n in input_via_class.items():
    out(
        f"{k:<20} {n:>8,}"
    )


# =============================================================================
# G. COMPILAZIONE
# =============================================================================

out()
out("D. COMPILAZIONE EDGE SEQUENCES")
out("-" * 110)

sequence_id = 0

relation_status = Counter()
sequence_rule = Counter()

compiled_relation_count = 0
compiled_core_relation_count = 0

multi_sequence_relations = 0

edge_count_distribution = Counter()


for number, r in enumerate(
    restrictions,
    start=1,
):

    relation_id = int(
        r["relation_id"]
    )

    restriction_value = str(
        r["restriction_value"]
    )

    via_class = str(
        r["via_class"]
    )

    conditional_raw = (
        r["restriction_conditional"]
    )

    except_raw = r["except_raw"]

    members = json.loads(
        r["members_json"]
    )

    from_members = [
        m
        for m in members
        if m["role"] == "from"
        and m["type"] == "w"
    ]

    via_members = [
        m
        for m in members
        if m["role"] == "via"
    ]

    to_members = [
        m
        for m in members
        if m["role"] == "to"
        and m["type"] == "w"
    ]

    from_way = int(
        from_members[0]["ref"]
    )

    to_way = int(
        to_members[0]["ref"]
    )

    # -------------------------------------------------------------
    # rule kind
    # -------------------------------------------------------------

    if restriction_value.startswith(
        "no_"
    ):

        rule_kind = "NO_SEQUENCE"

    elif restriction_value.startswith(
        "only_"
    ):

        rule_kind = "ONLY_SEQUENCE"

    else:

        compile_status = (
            "UNSUPPORTED_RESTRICTION_VALUE"
        )

        sequences = []

        cur.execute(
            """
            INSERT INTO relation_compile_summary(
                relation_id,
                restriction_value,
                via_class,
                rule_kind,
                conditional_raw,
                except_raw,
                compile_status,
                sequence_count,
                core_sequence_count,
                min_edge_count,
                max_edge_count,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                restriction_value,
                via_class,
                "UNSUPPORTED",
                conditional_raw,
                except_raw,
                compile_status,
                0,
                0,
                None,
                None,
                None,
            ),
        )

        relation_status[
            compile_status
        ] += 1

        continue

    # -------------------------------------------------------------
    # VIA NODE
    # -------------------------------------------------------------

    if via_class == "VIA_NODE":

        via_nodes = [
            int(m["ref"])
            for m in via_members
            if m["type"] == "n"
        ]

        via_node = via_nodes[0]

        sequences = compile_via_node(
            from_way,
            via_node,
            to_way,
        )

        if sequences:
            compile_status = "COMPILED"
        else:
            compile_status = "NO_ROUTABLE_SEQUENCE"

    # -------------------------------------------------------------
    # VIA WAY
    # -------------------------------------------------------------

    elif via_class == "VIA_WAY":

        via_ways = [
            int(m["ref"])
            for m in via_members
            if m["type"] == "w"
        ]

        status, sequences = (
            compile_via_way(
                from_way,
                via_ways,
                to_way,
            )
        )

        if status == "OK":

            if sequences:
                compile_status = "COMPILED"
            else:
                compile_status = "NO_ROUTABLE_SEQUENCE"

        else:
            compile_status = status

    else:

        sequences = []

        compile_status = (
            "UNSUPPORTED_VIA_CLASS"
        )

    # -------------------------------------------------------------
    # WRITE
    # -------------------------------------------------------------

    sequence_count = len(sequences)

    core_sequence_count = sum(
        int(
            all(
                e["core_eligible"] == 1
                for e in seq_edges
            )
        )
        for seq_edges in sequences
    )

    if sequence_count > 0:
        compiled_relation_count += 1

    if core_sequence_count > 0:
        compiled_core_relation_count += 1

    if sequence_count > 1:
        multi_sequence_relations += 1

    min_edges = None
    max_edges = None

    if sequences:

        edge_counts = [
            len(x)
            for x in sequences
        ]

        min_edges = min(edge_counts)
        max_edges = max(edge_counts)

        for x in edge_counts:
            edge_count_distribution[x] += 1

    cur.execute(
        """
        INSERT INTO relation_compile_summary(
            relation_id,
            restriction_value,
            via_class,
            rule_kind,
            conditional_raw,
            except_raw,
            compile_status,
            sequence_count,
            core_sequence_count,
            min_edge_count,
            max_edge_count,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relation_id,
            restriction_value,
            via_class,
            rule_kind,
            conditional_raw,
            except_raw,
            compile_status,
            sequence_count,
            core_sequence_count,
            min_edges,
            max_edges,
            None,
        ),
    )

    relation_status[
        compile_status
    ] += 1

    for variant_index, seq_edges in enumerate(
        sequences,
        start=1,
    ):

        sequence_id += 1

        edge_ids = [
            int(e["edge_id"])
            for e in seq_edges
        ]

        edge_uids = [
            str(e["edge_uid"])
            for e in seq_edges
        ]

        core_only = int(
            all(
                e["core_eligible"] == 1
                for e in seq_edges
            )
        )

        cur.execute(
            """
            INSERT INTO restriction_sequences(
                sequence_id,
                relation_id,
                variant_index,
                restriction_value,
                via_class,
                rule_kind,
                edge_count,
                start_edge_id,
                end_edge_id,
                start_node,
                end_node,
                core_only,
                edge_ids_json,
                edge_uids_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sequence_id,
                relation_id,
                variant_index,

                restriction_value,
                via_class,
                rule_kind,

                len(seq_edges),

                edge_ids[0],
                edge_ids[-1],

                int(seq_edges[0]["u"]),
                int(seq_edges[-1]["v"]),

                core_only,

                json.dumps(
                    edge_ids,
                    separators=(",", ":"),
                ),

                json.dumps(
                    edge_uids,
                    separators=(",", ":"),
                ),
            ),
        )

        cur.executemany(
            """
            INSERT INTO restriction_sequence_edges(
                sequence_id,
                position,
                edge_id,
                edge_uid,
                way_id,
                seq,
                u,
                v,
                core_eligible
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    sequence_id,
                    pos,

                    int(e["edge_id"]),
                    str(e["edge_uid"]),

                    int(e["way_id"]),
                    int(e["seq"]),

                    int(e["u"]),
                    int(e["v"]),

                    int(e["core_eligible"]),
                )

                for pos, e in enumerate(
                    seq_edges
                )
            ],
        )

        sequence_rule[
            rule_kind
        ] += 1

    if number % 500 == 0:

        db.commit()

        out(
            f"  relation={number:>6,}/"
            f"{len(restrictions):,} | "
            f"compiled={compiled_relation_count:>6,} | "
            f"sequences={sequence_id:>7,}"
        )


db.commit()


# =============================================================================
# H. QA
# =============================================================================

out()
out("E. QA COMPILAZIONE")
out("-" * 110)

out(
    f"Restriction input             : "
    f"{len(restrictions):,}"
)

out(
    f"Relation compilate            : "
    f"{compiled_relation_count:,}"
)

out(
    f"Relation con almeno 1 CORE seq: "
    f"{compiled_core_relation_count:,}"
)

out(
    f"Relation multi-sequence       : "
    f"{multi_sequence_relations:,}"
)

out(
    f"Sequenze totali               : "
    f"{sequence_id:,}"
)


out()
out("Compile status")
out("-" * 110)

for status, n in sorted(
    relation_status.items(),
    key=lambda x: (-x[1], x[0]),
):

    out(
        f"{status:<35} "
        f"{n:>8,}"
    )


out()
out("Sequenze per rule kind")
out("-" * 110)

for rule, n in sorted(
    sequence_rule.items()
):

    out(
        f"{rule:<25} "
        f"{n:>8,}"
    )


out()
out("Edge count per sequence")
out("-" * 110)

for edge_count, n in sorted(
    edge_count_distribution.items()
):

    out(
        f"{edge_count:>4} edge : "
        f"{n:>8,} sequence"
    )


out()
out("Via-class × compile status")
out("-" * 110)

rows = cur.execute(
    """
    SELECT
        via_class,
        compile_status,
        COUNT(*)

    FROM relation_compile_summary

    GROUP BY
        via_class,
        compile_status

    ORDER BY
        via_class,
        COUNT(*) DESC
    """
).fetchall()

for via_class, status, n in rows:

    out(
        f"{via_class:<12} "
        f"{status:<35} "
        f"{n:>8,}"
    )


out()
out("Restriction type × compiled")
out("-" * 110)

rows = cur.execute(
    """
    SELECT
        restriction_value,
        compile_status,
        COUNT(*)

    FROM relation_compile_summary

    GROUP BY
        restriction_value,
        compile_status

    ORDER BY
        restriction_value,
        compile_status
    """
).fetchall()

for restriction, status, n in rows:

    out(
        f"{str(restriction):<25} "
        f"{status:<35} "
        f"{n:>8,}"
    )


# =============================================================================
# I. METADATA FINALI
# =============================================================================

final_metadata = {
    "input_relation_count":
        len(restrictions),

    "compiled_relation_count":
        compiled_relation_count,

    "compiled_core_relation_count":
        compiled_core_relation_count,

    "multi_sequence_relation_count":
        multi_sequence_relations,

    "compiled_sequence_count":
        sequence_id,
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
        for k, v in final_metadata.items()
    ],
)

db.commit()


# =============================================================================
# J. FINALIZZAZIONE
# =============================================================================

cur.execute(
    "PRAGMA wal_checkpoint(TRUNCATE)"
)

db.commit()

db.close()
b1.close()
b2.close()

out()
out("F. FINALIZZAZIONE")
out("-" * 110)

out(
    f"SQLite prodotto : {OUTDB}"
)

out(
    f"Dimensione      : "
    f"{OUTDB.stat().st_size:,} bytes"
)

out()
out("=" * 110)
out("ESITO BUILD B4: QA_READY")
out("=" * 110)

out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
