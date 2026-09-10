from pathlib import Path
from urllib.parse import quote
import sqlite3
import sys

DB = Path(
    r"C:\Tesi\Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite"
)

TABLE = "directed_edges"

CASES = [
    {
        "SECTION_ID": "920022",
        "PRIMARY_SEGMENT": "203141242:23",
        "OPPOSITE_SEGMENT": "104915080:18",
    },
    {
        "SECTION_ID": "920044",
        "PRIMARY_SEGMENT": "148319235:8",
        "OPPOSITE_SEGMENT": "832928883:0",
    },
    {
        "SECTION_ID": "920034",
        "PRIMARY_SEGMENT": "787078230:14",
        "OPPOSITE_SEGMENT": "26283853:0",
    },
    {
        "SECTION_ID": "920035",
        "PRIMARY_SEGMENT": "26259796:11",
        "OPPOSITE_SEGMENT": "350457892:2",
    },
    {
        "SECTION_ID": "920024",
        "PRIMARY_SEGMENT": "42941151:4",
        "OPPOSITE_SEGMENT": "191942226:1",
    },
    {
        "SECTION_ID": "920026",
        "PRIMARY_SEGMENT": "156185537:0",
        "OPPOSITE_SEGMENT": "156185538:0",
    },
    {
        "SECTION_ID": "920042",
        "PRIMARY_SEGMENT": "191946557:1",
        "OPPOSITE_SEGMENT": "28521224:2",
    },
]


def connect_read_only(path):
    raw = str(path.resolve()).replace("\\", "/")
    uri = "file:" + quote(raw, safe="/:") + "?mode=ro"

    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")

    return conn


def lookup(conn, segment_uid):
    rows = conn.execute(
        f"""
        SELECT
            edge_id,
            segment_uid,
            u,
            v
        FROM {TABLE}
        WHERE CAST(segment_uid AS TEXT) = ?
        ORDER BY edge_id
        """,
        (segment_uid,),
    ).fetchall()

    return rows


print("=" * 92)
print("FASE 5.8D — FINAL DIRECTED EDGE LOOKUP")
print("=" * 92)

print(f"DB_EXISTS = {'YES' if DB.exists() else 'NO'}")
print(f"DB        = {DB}")

if not DB.exists():
    sys.exit("FAIL: B2 database not found")

conn = connect_read_only(DB)

try:

    all_ok = True

    for case in CASES:

        section = case["SECTION_ID"]
        primary = case["PRIMARY_SEGMENT"]
        opposite = case["OPPOSITE_SEGMENT"]

        p_rows = lookup(conn, primary)
        o_rows = lookup(conn, opposite)

        print("-" * 92)
        print(f"SECTION_ID       = {section}")
        print(f"PRIMARY_SEGMENT  = {primary}")

        if len(p_rows) == 1:
            p = p_rows[0]
            print(
                f"PRIMARY_EDGE     = {p[0]} "
                f"| u={p[2]} | v={p[3]}"
            )
        else:
            print(f"PRIMARY_EDGE     = ERROR_COUNT_{len(p_rows)}")
            all_ok = False

        print(f"OPPOSITE_SEGMENT = {opposite}")

        if len(o_rows) == 1:
            o = o_rows[0]
            print(
                f"OPPOSITE_EDGE    = {o[0]} "
                f"| u={o[2]} | v={o[3]}"
            )
        else:
            print(f"OPPOSITE_EDGE    = ERROR_COUNT_{len(o_rows)}")
            all_ok = False

        if len(p_rows) == 1 and len(o_rows) == 1:
            print(
                "MEASUREMENT       = "
                f"FLOW_{p_rows[0][0]} + FLOW_{o_rows[0][0]}"
            )

    print("=" * 92)

    if all_ok:
        print("VERDICT            = PASS_ALL_7")
        print("MEASUREMENT_RULE   = BIDIRECTIONAL_SUM")
    else:
        print("VERDICT            = CHECK_REQUIRED")

    print("DB_MODIFIED         = NO")
    print("ROUTING_RECOMPUTED  = NO")
    print("SHORTEST_PATH_RUN   = NO")
    print("=" * 92)

finally:
    conn.close()

