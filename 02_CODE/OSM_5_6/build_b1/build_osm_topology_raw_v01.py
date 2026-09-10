from pathlib import Path
from datetime import datetime
from collections import Counter
import hashlib
import json
import re
import sqlite3
import sys

import osmium


# =====================================================================
# CONFIG
# =====================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

PBF = (
    ROOT
    / r"00_originali\rete_stradale\osm"
    / "nord-est_2026-08-03.osm.pbf"
)

SOURCE_GPKG = (
    ROOT
    / r"02_package"
    / "rete_stradale_osm_fvg.gpkg"
)

# Layer più maturo disponibile: serve SOLO per ricavare le OSM way
# appartenenti alla rete light già filtrata.
SOURCE_LAYER = "osm_rete_light_20km_tempi_base_v3"

OUTDIR = (
    ROOT
    / r"03_output_temporanei"
    / r"fase_5_6_osm_operativo"
    / "build_b1"
)

OUTDIR.mkdir(parents=True, exist_ok=True)

OUTDB = OUTDIR / "osm_topology_raw_v01.sqlite"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUTDIR / f"build_osm_topology_raw_v01_{STAMP}.txt"


# =====================================================================
# LOG
# =====================================================================

lines = []

def out(s=""):
    s = str(s)
    print(s)
    lines.append(s)


def sha256_file(path, block=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def tag_dict(taglist):
    return {t.k: t.v for t in taglist}


def parse_osm_id(value):
    """
    Accetta:
      123456
      '123456'
      'way/123456'
      'w123456'

    Restituisce int oppure None.
    """
    if value is None:
        return None

    if isinstance(value, int):
        return value

    s = str(value).strip()

    if not s:
        return None

    if re.fullmatch(r"\d+", s):
        return int(s)

    m = re.search(r"(\d+)$", s)

    if m:
        return int(m.group(1))

    return None


# =====================================================================
# PREFLIGHT OUTPUT
# =====================================================================

if OUTDB.exists():
    raise RuntimeError(
        f"Output già esistente: {OUTDB}\n"
        "Non sovrascrivo un output versionato."
    )

if not PBF.exists():
    raise FileNotFoundError(PBF)

if not SOURCE_GPKG.exists():
    raise FileNotFoundError(SOURCE_GPKG)


out("=" * 100)
out("FASE 5.6 — BUILD B1 — OSM RAW TOPOLOGY")
out("=" * 100)

out(f"PBF          : {PBF}")
out(f"Source GPKG  : {SOURCE_GPKG}")
out(f"Source layer : {SOURCE_LAYER}")
out(f"Output DB    : {OUTDB}")

PBF_SHA256 = sha256_file(PBF)

out(f"PBF SHA256   : {PBF_SHA256}")


# =====================================================================
# 1. RECUPERO WAY_ID DAL NETWORK LIGHT STORICO
# =====================================================================

out()
out("A. RECUPERO OSM WAY ID DAL NETWORK LIGHT VALIDATO")
out("-" * 100)

src = sqlite3.connect(SOURCE_GPKG)
src_cur = src.cursor()

exists = src_cur.execute(
    """
    SELECT COUNT(*)
    FROM gpkg_contents
    WHERE table_name = ?
    """,
    (SOURCE_LAYER,),
).fetchone()[0]

if not exists:
    raise RuntimeError(
        f"Layer non trovato nel GPKG: {SOURCE_LAYER}"
    )

cols = [
    r[1]
    for r in src_cur.execute(
        f'PRAGMA table_info("{SOURCE_LAYER}")'
    ).fetchall()
]

out("Campi disponibili:")
out("  " + ", ".join(cols))

lower_to_real = {c.lower(): c for c in cols}

ID_CANDIDATES = [
    "osm_id",
    "osm_way_id",
    "way_id",
    "osmid",
    "osm_wayid",
]

id_field = None

for candidate in ID_CANDIDATES:
    if candidate in lower_to_real:
        id_field = lower_to_real[candidate]
        break

if id_field is None:
    out()
    out("ERRORE: nessun campo OSM way-id riconosciuto.")
    out("Serve identificare il campo corretto prima di continuare.")
    out("=== RUN COMPLETATA CON ERRORE ===")
    LOG.write_text("\n".join(lines), encoding="utf-8")
    sys.exit(2)

out()
out(f"Campo way-id scelto: {id_field}")

rows = src_cur.execute(
    f'''
    SELECT DISTINCT "{id_field}"
    FROM "{SOURCE_LAYER}"
    WHERE "{id_field}" IS NOT NULL
    '''
).fetchall()

src.close()

wanted_way_ids = set()

unparsed_values = []

for (value,) in rows:
    wid = parse_osm_id(value)

    if wid is None:
        if len(unparsed_values) < 30:
            unparsed_values.append(value)
    else:
        wanted_way_ids.add(wid)

out(f"Distinct valori sorgente : {len(rows):,}")
out(f"Way ID validi            : {len(wanted_way_ids):,}")
out(f"Valori non interpretabili: {len(unparsed_values):,}")

if unparsed_values:
    out(f"Esempi non interpretabili: {unparsed_values[:10]}")

if not wanted_way_ids:
    raise RuntimeError("Nessun OSM way_id recuperato.")


# =====================================================================
# 2. DATABASE INTERMEDIO
# =====================================================================

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

    CREATE TABLE ways (
        way_id INTEGER PRIMARY KEY,
        highway TEXT,
        node_count INTEGER NOT NULL,
        tags_json TEXT NOT NULL
    );

    CREATE TABLE way_nodes (
        way_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        node_id INTEGER NOT NULL,
        PRIMARY KEY (way_id, seq)
    );

    CREATE INDEX idx_way_nodes_node
        ON way_nodes(node_id);

    CREATE TABLE nodes (
        node_id INTEGER PRIMARY KEY,
        lon REAL NOT NULL,
        lat REAL NOT NULL
    );

    CREATE TABLE restrictions_raw (
        relation_id INTEGER PRIMARY KEY,

        restriction_key TEXT,
        restriction_value TEXT,

        restriction_generic TEXT,
        restriction_vehicle TEXT,
        restriction_motor_vehicle TEXT,
        restriction_motorcar TEXT,
        restriction_conditional TEXT,

        except_raw TEXT,

        applies_to_motorcar INTEGER NOT NULL,

        from_count INTEGER NOT NULL,
        via_count INTEGER NOT NULL,
        to_count INTEGER NOT NULL,

        via_class TEXT NOT NULL,

        canonical_structure INTEGER NOT NULL,
        in_scope INTEGER NOT NULL,

        status TEXT NOT NULL,

        members_json TEXT NOT NULL,
        tags_json TEXT NOT NULL
    );
    """
)

metadata = {
    "pipeline_phase": "FASE_5_6_BUILD_B1",
    "pipeline_version": "v01",
    "created_at": STAMP,
    "python": sys.version.replace("\n", " "),
    "osmium_version": getattr(osmium, "__version__", "unknown"),
    "source_pbf": str(PBF),
    "source_pbf_sha256": PBF_SHA256,
    "source_filter_gpkg": str(SOURCE_GPKG),
    "source_filter_layer": SOURCE_LAYER,
    "source_way_id_field": id_field,
}

cur.executemany(
    "INSERT INTO metadata(key, value) VALUES (?, ?)",
    [(k, str(v)) for k, v in metadata.items()],
)

db.commit()


# =====================================================================
# 3. PASS 1 — WAY + RESTRICTIONS
# =====================================================================

out()
out("B. PASS 1 — ESTRAZIONE WAY + RELATION")
out("-" * 100)

found_way_ids = set()
needed_node_ids = set()

restriction_stats = Counter()

way_counter = 0
way_node_counter = 0


class TopologyHandler(osmium.SimpleHandler):

    def way(self, w):
        global way_counter, way_node_counter

        wid = int(w.id)

        if wid not in wanted_way_ids:
            return

        tags = tag_dict(w.tags)

        node_refs = [int(n.ref) for n in w.nodes]

        cur.execute(
            """
            INSERT INTO ways(
                way_id,
                highway,
                node_count,
                tags_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                wid,
                tags.get("highway"),
                len(node_refs),
                json.dumps(
                    tags,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )

        cur.executemany(
            """
            INSERT INTO way_nodes(
                way_id,
                seq,
                node_id
            )
            VALUES (?, ?, ?)
            """,
            [
                (wid, seq, nid)
                for seq, nid in enumerate(node_refs)
            ],
        )

        found_way_ids.add(wid)
        needed_node_ids.update(node_refs)

        way_counter += 1
        way_node_counter += len(node_refs)

        if way_counter % 5000 == 0:
            db.commit()
            out(
                f"  way estratte: {way_counter:,} | "
                f"way-node: {way_node_counter:,} | "
                f"node distinti richiesti: {len(needed_node_ids):,}"
            )

    def relation(self, r):

        tags = tag_dict(r.tags)

        if tags.get("type") != "restriction":
            return

        members = []

        from_members = []
        via_members = []
        to_members = []

        all_way_members = []

        for m in r.members:

            item = {
                "type": m.type,
                "ref": int(m.ref),
                "role": m.role,
            }

            members.append(item)

            if m.type == "w":
                all_way_members.append(int(m.ref))

            if m.role == "from":
                from_members.append(item)

            elif m.role == "via":
                via_members.append(item)

            elif m.role == "to":
                to_members.append(item)

        # Conserviamo solo restriction che toccano almeno una
        # delle way del network light regionale.
        if not any(
            wid in wanted_way_ids
            for wid in all_way_members
        ):
            return

        restriction_stats["relevant_raw"] += 1

        from_ways = [
            x for x in from_members
            if x["type"] == "w"
        ]

        to_ways = [
            x for x in to_members
            if x["type"] == "w"
        ]

        via_nodes = [
            x for x in via_members
            if x["type"] == "n"
        ]

        via_ways = [
            x for x in via_members
            if x["type"] == "w"
        ]

        if via_members and len(via_nodes) == len(via_members):
            via_class = "VIA_NODE"

        elif via_members and len(via_ways) == len(via_members):
            via_class = "VIA_WAY"

        elif not via_members:
            via_class = "NO_VIA"

        else:
            via_class = "VIA_MIXED"

        # Una restriction è realmente interna al nostro network
        # soltanto se TUTTE le way necessarie sono presenti.
        in_scope = (
            len(all_way_members) > 0
            and all(
                wid in wanted_way_ids
                for wid in all_way_members
            )
        )

        # Restriction statica pertinente alle automobili:
        # precedenza dalla più specifica alla generica.
        restriction_key = None
        restriction_value = None

        for k in (
            "restriction:motorcar",
            "restriction:motor_vehicle",
            "restriction:vehicle",
            "restriction",
        ):
            if tags.get(k):
                restriction_key = k
                restriction_value = tags[k]
                break

        conditional = tags.get(
            "restriction:conditional"
        )

        except_raw = tags.get("except")

        except_tokens = set()

        if except_raw:
            for token in re.split(r"[;,]", except_raw):
                token = token.strip().lower()
                if token:
                    except_tokens.add(token)

        motorcar_exempt = bool(
            {
                "motorcar",
                "motor_vehicle",
                "vehicle",
            }
            & except_tokens
        )

        if restriction_value is None:
            applies_to_motorcar = 0

        elif motorcar_exempt:
            applies_to_motorcar = 0

        else:
            applies_to_motorcar = 1

        # Struttura canonica:
        # 1 from-way
        # 1 to-way
        # + 1 via-node
        # oppure >=1 via-way.
        canonical = (
            len(from_ways) == 1
            and len(to_ways) == 1
            and (
                (
                    len(via_nodes) == 1
                    and len(via_ways) == 0
                )
                or
                (
                    len(via_ways) >= 1
                    and len(via_nodes) == 0
                )
            )
        )

        if not in_scope:
            status = "OUT_OF_SCOPE"

        elif not applies_to_motorcar:
            if conditional and not restriction_value:
                status = "CONDITIONAL_ONLY"
            else:
                status = "NOT_APPLICABLE_MOTORCAR"

        elif not canonical:
            status = "NONCANONICAL_STRUCTURE"

        elif conditional:
            status = "STATIC_PLUS_CONDITIONAL"

        else:
            status = "STATIC_CANONICAL"

        restriction_stats[via_class] += 1
        restriction_stats[status] += 1

        cur.execute(
            """
            INSERT INTO restrictions_raw(
                relation_id,
                restriction_key,
                restriction_value,

                restriction_generic,
                restriction_vehicle,
                restriction_motor_vehicle,
                restriction_motorcar,
                restriction_conditional,

                except_raw,

                applies_to_motorcar,

                from_count,
                via_count,
                to_count,

                via_class,

                canonical_structure,
                in_scope,

                status,

                members_json,
                tags_json
            )
            VALUES (
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?,
                ?,
                ?, ?, ?,
                ?,
                ?, ?,
                ?,
                ?, ?
            )
            """,
            (
                int(r.id),

                restriction_key,
                restriction_value,

                tags.get("restriction"),
                tags.get("restriction:vehicle"),
                tags.get("restriction:motor_vehicle"),
                tags.get("restriction:motorcar"),
                conditional,

                except_raw,

                int(applies_to_motorcar),

                len(from_members),
                len(via_members),
                len(to_members),

                via_class,

                int(canonical),
                int(in_scope),

                status,

                json.dumps(
                    members,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),

                json.dumps(
                    tags,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )


handler = TopologyHandler()
handler.apply_file(str(PBF), locations=False)

db.commit()

out()
out(f"Way richieste       : {len(wanted_way_ids):,}")
out(f"Way trovate nel PBF : {len(found_way_ids):,}")
out(f"Way-node estratti   : {way_node_counter:,}")
out(f"Node distinti       : {len(needed_node_ids):,}")

missing_way_ids = wanted_way_ids - found_way_ids

out(f"Way mancanti        : {len(missing_way_ids):,}")

if missing_way_ids:
    out(
        "Esempio way mancanti: "
        + ", ".join(
            str(x)
            for x in sorted(missing_way_ids)[:30]
        )
    )


# =====================================================================
# 4. PASS 2 — COORDINATE NODI
# =====================================================================

out()
out("C. PASS 2 — RECUPERO COORDINATE NODE")
out("-" * 100)

node_found = 0
node_batch = []


class NodeHandler(osmium.SimpleHandler):

    def node(self, n):
        global node_found, node_batch

        nid = int(n.id)

        if nid not in needed_node_ids:
            return

        try:
            lon = float(n.location.lon)
            lat = float(n.location.lat)
        except Exception:
            return

        node_batch.append(
            (nid, lon, lat)
        )

        node_found += 1

        if len(node_batch) >= 10000:

            cur.executemany(
                """
                INSERT INTO nodes(
                    node_id,
                    lon,
                    lat
                )
                VALUES (?, ?, ?)
                """,
                node_batch,
            )

            db.commit()

            node_batch.clear()

            if node_found % 100000 == 0:
                out(
                    f"  node coordinate recuperate: "
                    f"{node_found:,}"
                )


node_handler = NodeHandler()
node_handler.apply_file(
    str(PBF),
    locations=False,
)

if node_batch:
    cur.executemany(
        """
        INSERT INTO nodes(
            node_id,
            lon,
            lat
        )
        VALUES (?, ?, ?)
        """,
        node_batch,
    )

db.commit()

missing_nodes = len(needed_node_ids) - node_found

out()
out(f"Node richiesti : {len(needed_node_ids):,}")
out(f"Node trovati   : {node_found:,}")
out(f"Node mancanti  : {missing_nodes:,}")


# =====================================================================
# 5. QA RESTRICTIONS REGIONALI
# =====================================================================

out()
out("D. RESTRICTIONS CHE TOCCANO IL NETWORK")
out("-" * 100)

restriction_rows = cur.execute(
    """
    SELECT
        status,
        via_class,
        COUNT(*)
    FROM restrictions_raw
    GROUP BY status, via_class
    ORDER BY status, via_class
    """
).fetchall()

for status, via_class, n in restriction_rows:
    out(
        f"{status:<30} "
        f"{via_class:<12} "
        f"{n:>8,}"
    )

out()
out("Restriction STATIC_CANONICAL per tipo")
out("-" * 100)

rows = cur.execute(
    """
    SELECT
        restriction_value,
        via_class,
        COUNT(*)
    FROM restrictions_raw
    WHERE status IN (
        'STATIC_CANONICAL',
        'STATIC_PLUS_CONDITIONAL'
    )
    GROUP BY restriction_value, via_class
    ORDER BY COUNT(*) DESC
    """
).fetchall()

for restriction, via_class, n in rows:
    out(
        f"{str(restriction):<30} "
        f"{via_class:<12} "
        f"{n:>8,}"
    )


# =====================================================================
# 6. METADATA FINALI B1
# =====================================================================

final_metadata = {
    "wanted_way_count": len(wanted_way_ids),
    "found_way_count": len(found_way_ids),
    "missing_way_count": len(missing_way_ids),

    "way_node_count": way_node_counter,

    "needed_node_count": len(needed_node_ids),
    "found_node_count": node_found,
    "missing_node_count": missing_nodes,

    "restriction_relevant_raw_count":
        restriction_stats["relevant_raw"],
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


# =====================================================================
# 7. FINALIZZAZIONE SQLITE
# =====================================================================

out()
out("E. FINALIZZAZIONE DATABASE")
out("-" * 100)

cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
db.commit()
db.close()

out(f"SQLite prodotto : {OUTDB}")
out(f"Dimensione       : {OUTDB.stat().st_size:,} bytes")

out()
out("=" * 100)

if missing_way_ids or missing_nodes:
    out("ESITO BUILD B1: ATTENZIONE — verificare missing IDs")
else:
    out("ESITO BUILD B1: PASS")

out("=" * 100)
out(f"LOG: {LOG}")
out("=== RUN COMPLETATA ===")

LOG.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
