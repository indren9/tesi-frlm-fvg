from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import csv
import os
import re
import sqlite3
import sys

import pyogrio
from pyproj import Transformer
from shapely.geometry import Point


# =============================================================================
# FASE 5.8D — PASSO 2
# AUTOMATED SPATIAL MATCH + READ-ONLY B2 EDGE LOOKUP
# =============================================================================

GPKG = Path(
    r"C:\Tesi\Tesi_QGIS\02_package\grafo_operativo_osm\G_OSM_operativo_v01.gpkg"
)

LAYER = "G_OSM_operativo_segments_v01"

OUT_DIR = Path(
    r"C:\Tesi\Tesi_QGIS\03_output_temporanei\fase_5_8D"
)

SEARCH_RADIUS_M = 500.0
REF_COHERENT_MAX_M = 300.0
NEARBY_RADIUS_M = 100.0
PAIR_DIAGNOSTIC_RADIUS_M = 60.0

# Solo ricerca di file esistenti. Nessuna modifica.
B2_SEARCH_ROOTS = [
    Path(r"C:\Tesi\Tesi_QGIS\02_package"),
    Path(r"C:\Tesi\Tesi_QGIS\03_output_temporanei"),
]

# -----------------------------------------------------------------------------
# 16 sezioni A/B/C frozen.
#
# Coordinate:
# 2025.04.08_ListaPostazioni.pdf
#
# Quality class + TGMA_LIGHT_2024:
# ANAS_2024_TARGET_FINAL_FROZEN.xlsx
#
# Una sola riga per SECTION_ID logico.
# A/D NON vengono duplicati.
# -----------------------------------------------------------------------------

STATIONS = [
    # A
    {
        "SECTION_ID": "920044",
        "ROAD": "A0",
        "LOCATION": "Muggia",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 15345,
        "LAT": 45.584808,
        "LON": 13.797988,
    },
    {
        "SECTION_ID": "920022",
        "ROAD": "RA13",
        "LOCATION": "Duino Aurisina-Devin Nabrežina",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 23143,
        "LAT": 45.748762,
        "LON": 13.681005,
    },
    {
        "SECTION_ID": "920028",
        "ROAD": "SS13",
        "LOCATION": "Tarvisio",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 6088,
        "LAT": 46.506362,
        "LON": 13.520165,
    },
    {
        "SECTION_ID": "920034",
        "ROAD": "SS202",
        "LOCATION": "Trieste",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 27512,
        "LAT": 45.623798,
        "LON": 13.780887,
    },
    {
        "SECTION_ID": "920035",
        "ROAD": "SS202",
        "LOCATION": "San Dorligo della Valle-Dolina",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 15618,
        "LAT": 45.612027,
        "LON": 13.844900,
    },
    {
        "SECTION_ID": "920037",
        "ROAD": "SS54",
        "LOCATION": "Tarvisio",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 1224,
        "LAT": 46.419115,
        "LON": 13.572257,
    },
    {
        "SECTION_ID": "920032",
        "ROAD": "SS54",
        "LOCATION": "Cividale del Friuli",
        "QUALITY_CLASS": "A",
        "TGMA_LIGHT_2024": 6964,
        "LAT": 46.108223,
        "LON": 13.467217,
    },

    # B
    {
        "SECTION_ID": "920024",
        "ROAD": "RA13",
        "LOCATION": "Trieste",
        "QUALITY_CLASS": "B",
        "TGMA_LIGHT_2024": 21028,
        "LAT": 45.701302,
        "LON": 13.781498,
    },
    {
        "SECTION_ID": "920026",
        "ROAD": "RA13",
        "LOCATION": "Trieste",
        "QUALITY_CLASS": "B",
        "TGMA_LIGHT_2024": 22770,
        "LAT": 45.666973,
        "LON": 13.825377,
    },
    {
        "SECTION_ID": "920039",
        "ROAD": "SS52BIS",
        "LOCATION": "Arta Terme",
        "QUALITY_CLASS": "B",
        "TGMA_LIGHT_2024": 8015,
        "LAT": 46.466750,
        "LON": 13.027043,
    },
    {
        "SECTION_ID": "920038",
        "ROAD": "SS54",
        "LOCATION": "Tarvisio",
        "QUALITY_CLASS": "B",
        "TGMA_LIGHT_2024": 2843,
        "LAT": 46.497332,
        "LON": 13.700880,
    },

    # C
    {
        "SECTION_ID": "920042",
        "ROAD": "A0",
        "LOCATION": "Muggia",
        "QUALITY_CLASS": "C",
        "TGMA_LIGHT_2024": 23127,
        "LAT": 45.604727,
        "LON": 13.824638,
    },
    {
        "SECTION_ID": "920029",
        "ROAD": "SS13",
        "LOCATION": "Tarvisio",
        "QUALITY_CLASS": "C",
        "TGMA_LIGHT_2024": 2752,
        "LAT": 46.531668,
        "LON": 13.638577,
    },
    {
        "SECTION_ID": "920030",
        "ROAD": "SS14",
        "LOCATION": "Trieste",
        "QUALITY_CLASS": "C",
        "TGMA_LIGHT_2024": 4646,
        "LAT": 45.638168,
        "LON": 13.870147,
    },
    {
        "SECTION_ID": "920031",
        "ROAD": "SS52BIS",
        "LOCATION": "Paluzza",
        "QUALITY_CLASS": "C",
        "TGMA_LIGHT_2024": 1040,
        "LAT": 46.594873,
        "LON": 12.954720,
    },
    {
        "SECTION_ID": "920040",
        "ROAD": "SS54",
        "LOCATION": "Remanzacco",
        "QUALITY_CLASS": "C",
        "TGMA_LIGHT_2024": 14659,
        "LAT": 46.084590,
        "LON": 13.318843,
    },
]


# =============================================================================
# HELPERS
# =============================================================================

def clean_value(value):
    if value is None:
        return ""
    try:
        if value != value:  # NaN
            return ""
    except Exception:
        pass
    return str(value).strip()


def normalize_ref_token(value):
    """
    SS 13 -> SS13
    SS52bis -> SS52BIS
    RA 13 -> RA13

    Nessuna equivalenza semantica inventata.
    Esempio: A0 NON viene automaticamente convertita in A4.
    """
    value = clean_value(value).upper()
    return re.sub(r"[^A-Z0-9]", "", value)


def ref_tokens(value):
    """
    Gestisce ref multiple tipo:
    'SS 13; E55'
    """
    value = clean_value(value)
    if not value:
        return set()

    pieces = re.split(r"[;,/|]+", value)

    out = set()
    for p in pieces:
        n = normalize_ref_token(p)
        if n:
            out.add(n)

    return out


def road_ref_matches(anas_road, osm_ref):
    target = normalize_ref_token(anas_road)
    return target in ref_tokens(osm_ref)


def fmt(value):
    value = clean_value(value)
    return value if value else "<NULL>"


def sqlite_ro_connect(path):
    raw = str(path.resolve()).replace("\\", "/")
    uri = "file:" + quote(raw, safe="/:") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def quoted_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


# =============================================================================
# B2 DISCOVERY — READ ONLY
# =============================================================================

def discover_b2_databases():
    """
    Cerca solamente database SQLite esistenti con nomi plausibili.
    Non apre né ricostruisce B2.
    """
    exact = []
    plausible = []

    for root in B2_SEARCH_ROOTS:
        if not root.exists():
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                low = filename.lower()

                if low == "osm_directed_edges_v02.sqlite":
                    exact.append(Path(dirpath) / filename)

                elif (
                    low.endswith((".sqlite", ".sqlite3", ".db"))
                    and "directed" in low
                    and "edge" in low
                ):
                    plausible.append(Path(dirpath) / filename)

    # dedupe
    seen = set()
    result = []

    for p in exact + plausible:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            result.append(p)

    return result


def inspect_edge_database(db_path):
    """
    Cerca una tabella che contenga:
      - identificatore di edge
      - identificatore del segmento fisico

    Preferisce nomi canonici, ma non forza uno schema inventato.
    """

    EDGE_NAMES = [
        "edge_id",
        "directed_edge_id",
    ]

    SEGMENT_NAMES = [
        "segment_uid",
        "segment_id",
        "physical_segment_uid",
        "physical_segment_id",
        "seg_uid",
        "seg_id",
    ]

    ENDPOINT_PAIRS = [
        ("osm_u", "osm_v"),
        ("u", "v"),
        ("from_node", "to_node"),
        ("source", "target"),
        ("from_id", "to_id"),
    ]

    try:
        conn = sqlite_ro_connect(db_path)
    except Exception:
        return None

    try:
        tables = [
            r[0]
            for r in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        best = None

        for table in tables:
            cols_info = conn.execute(
                f"PRAGMA table_info({quoted_identifier(table)})"
            ).fetchall()

            cols = [r[1] for r in cols_info]
            lower_map = {c.lower(): c for c in cols}

            edge_col = None
            segment_col = None

            for candidate in EDGE_NAMES:
                if candidate in lower_map:
                    edge_col = lower_map[candidate]
                    break

            for candidate in SEGMENT_NAMES:
                if candidate in lower_map:
                    segment_col = lower_map[candidate]
                    break

            if edge_col is None or segment_col is None:
                continue

            endpoint_cols = None

            for left, right in ENDPOINT_PAIRS:
                if left in lower_map and right in lower_map:
                    endpoint_cols = (
                        lower_map[left],
                        lower_map[right],
                    )
                    break

            score = 0

            if edge_col.lower() == "edge_id":
                score += 10

            if segment_col.lower() == "segment_uid":
                score += 10

            if endpoint_cols is not None:
                score += 5

            candidate = {
                "db_path": db_path,
                "table": table,
                "edge_col": edge_col,
                "segment_col": segment_col,
                "endpoint_cols": endpoint_cols,
                "all_cols": cols,
                "score": score,
            }

            if best is None or candidate["score"] > best["score"]:
                best = candidate

        return best

    finally:
        conn.close()


def locate_b2():
    db_candidates = discover_b2_databases()

    schemas = []

    for db in db_candidates:
        schema = inspect_edge_database(db)
        if schema is not None:
            schemas.append(schema)

    if not schemas:
        return None

    schemas.sort(key=lambda x: x["score"], reverse=True)

    return schemas[0]


def b2_edges_for_segment(b2_schema, segment_uid):
    if b2_schema is None:
        return [], None

    db_path = b2_schema["db_path"]
    table = b2_schema["table"]
    edge_col = b2_schema["edge_col"]
    segment_col = b2_schema["segment_col"]
    endpoint_cols = b2_schema["endpoint_cols"]

    select_cols = [edge_col]

    if endpoint_cols:
        select_cols += list(endpoint_cols)

    select_sql = ", ".join(quoted_identifier(c) for c in select_cols)

    sql = f"""
        SELECT {select_sql}
        FROM {quoted_identifier(table)}
        WHERE CAST({quoted_identifier(segment_col)} AS TEXT) = ?
        ORDER BY {quoted_identifier(edge_col)}
    """

    conn = sqlite_ro_connect(db_path)

    try:
        rows = conn.execute(sql, (str(segment_uid),)).fetchall()
    finally:
        conn.close()

    return rows, endpoint_cols


def infer_measurement_operator(edge_rows, endpoint_cols):
    """
    IMPORTANTE:
    Il TGMA corrente non fornisce due conteggi direzionali separati.

    Pertanto:
    - BIDIRECTIONAL_SUM solo se B2 dimostra due archi opposti
      sullo stesso segmento fisico;
    - un solo edge NON viene automaticamente interpretato
      come SINGLE_DIRECTION, perché potrebbe servire la carreggiata
      parallela dello stesso attraversamento;
    - altrimenti UNRESOLVED.
    """

    if not edge_rows:
        return (
            "UNRESOLVED",
            "No canonical B2 directed-edge mapping recovered."
        )

    edge_ids = [clean_value(r[0]) for r in edge_rows]

    if len(edge_rows) == 2 and endpoint_cols is not None:
        u1, v1 = clean_value(edge_rows[0][1]), clean_value(edge_rows[0][2])
        u2, v2 = clean_value(edge_rows[1][1]), clean_value(edge_rows[1][2])

        if u1 == v2 and v1 == u2:
            return (
                "BIDIRECTIONAL_SUM",
                "Two canonical B2 edges are exact opposite directions "
                "of the same physical segment."
            )

    if len(edge_rows) == 1:
        return (
            "UNRESOLVED",
            "Matched physical segment has one recovered B2 directed edge, "
            "but ANAS TGMA is not direction-separated; paired carriageway "
            "cannot be assumed automatically."
        )

    return (
        "UNRESOLVED",
        f"{len(edge_ids)} B2 edges recovered but bidirectional semantics "
        "are not uniquely demonstrated."
    )


# =============================================================================
# PREFLIGHT
# =============================================================================

print("=" * 118)
print("FASE 5.8D — PASSO 2 — AUTOMATED SPATIAL MATCH + B2 READ-ONLY LOOKUP")
print("=" * 118)

if not GPKG.exists():
    print(f"FAIL: GPKG not found: {GPKG}")
    sys.exit(1)

print(f"GPKG                  = {GPKG}")
print(f"LAYER                 = {LAYER}")
print(f"SECTIONS_A_B_C        = {len(STATIONS)}")
print(f"SEARCH_RADIUS_M       = {SEARCH_RADIUS_M:.0f}")
print(f"REF_COHERENT_MAX_M   = {REF_COHERENT_MAX_M:.0f}")
print(f"NEARBY_RADIUS_M       = {NEARBY_RADIUS_M:.0f}")

# CRS ANAS WGS84 -> GPKG UTM32N
transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32632",
    always_xy=True,
)

# B2 discovery
print("-" * 118)
print("B2 DISCOVERY — READ ONLY")

b2 = locate_b2()

if b2 is None:
    print("B2_STATUS             = NOT_LOCATED_OR_SCHEMA_NOT_RECOGNIZED")
    print("B2_EDGE_LOOKUP        = UNAVAILABLE")
else:
    print("B2_STATUS             = LOCATED")
    print(f"B2_DB                 = {b2['db_path']}")
    print(f"B2_TABLE              = {b2['table']}")
    print(f"B2_EDGE_COL           = {b2['edge_col']}")
    print(f"B2_SEGMENT_COL        = {b2['segment_col']}")
    print(
        "B2_ENDPOINT_COLS      = "
        + (
            " / ".join(b2["endpoint_cols"])
            if b2["endpoint_cols"]
            else "<NOT FOUND>"
        )
    )

print("-" * 118)
print("SPATIAL MATCH")


# =============================================================================
# SPATIAL MATCH
# =============================================================================

required_columns = [
    "segment_uid",
    "way_id",
    "osm_u",
    "osm_v",
    "length_m",
    "highway",
    "name",
    "ref",
    "direction_status",
    "direction_code",
]

results = []

for station in STATIONS:

    section_id = station["SECTION_ID"]
    road = station["ROAD"]
    location = station["LOCATION"]
    lat = station["LAT"]
    lon = station["LON"]

    x, y = transformer.transform(lon, lat)
    point = Point(x, y)

    bbox = (
        x - SEARCH_RADIUS_M,
        y - SEARCH_RADIUS_M,
        x + SEARCH_RADIUS_M,
        y + SEARCH_RADIUS_M,
    )

    gdf = pyogrio.read_dataframe(
        GPKG,
        layer=LAYER,
        columns=required_columns,
        bbox=bbox,
    )

    if gdf.empty:
        results.append({
            **station,
            "ANAS_X_32632": round(x, 3),
            "ANAS_Y_32632": round(y, 3),
            "NEAREST_OSM_DISTANCE_M": "",
            "MATCH_DISTANCE_M": "",
            "OSM_SEGMENT_ID": "",
            "OSM_PHYSICAL_SEGMENT": "",
            "OSM_WAY_ID": "",
            "OSM_U": "",
            "OSM_V": "",
            "OSM_REF": "",
            "OSM_NAME": "",
            "OSM_HIGHWAY": "",
            "DIRECTION_CODE": "",
            "DIRECTION_STATUS": "",
            "N_CANDIDATES_NEARBY": 0,
            "N_REF_COHERENT_300M": 0,
            "ROAD_REF_COHERENT": "NO",
            "MATCH_SELECTION_BASIS": "NO_CANDIDATE_WITHIN_500M",
            "RELEVANT_DIRECTED_EDGE_IDS": "",
            "MEASUREMENT_OPERATOR_HINT": "UNRESOLVED",
            "MEASUREMENT_REASON": "No OSM physical segment within search radius.",
            "PAIR_DIAGNOSTIC": "",
            "CANDIDATE_SUMMARY": "",
        })

        print(
            f"{section_id:>6} | {station['QUALITY_CLASS']} | "
            f"{road:<8} | NO CANDIDATE <= {SEARCH_RADIUS_M:.0f} m"
        )

        continue

    # distance esatta punto-linea
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf["_distance_m"] = gdf.geometry.distance(point)
    gdf = gdf[gdf["_distance_m"] <= SEARCH_RADIUS_M].copy()

    if gdf.empty:
        print(
            f"{section_id:>6} | {station['QUALITY_CLASS']} | "
            f"{road:<8} | NO GEOMETRY <= {SEARCH_RADIUS_M:.0f} m"
        )
        continue

    gdf["_ref_match"] = gdf["ref"].apply(
        lambda v: road_ref_matches(road, v)
    )

    gdf.sort_values(
        by=["_distance_m", "segment_uid"],
        inplace=True,
        kind="mergesort",
    )

    nearest = gdf.iloc[0]

    coherent = gdf[
        (gdf["_ref_match"])
        & (gdf["_distance_m"] <= REF_COHERENT_MAX_M)
    ].copy()

    if not coherent.empty:
        coherent.sort_values(
            by=["_distance_m", "segment_uid"],
            inplace=True,
            kind="mergesort",
        )
        selected = coherent.iloc[0]
        selection_basis = "ROAD_REF_COHERENT_PLUS_PROXIMITY"
        road_ref_coherent = "YES"
    else:
        # Solo candidato diagnostico.
        # NON viene dichiarato match definitivo.
        selected = nearest
        selection_basis = "NEAREST_ONLY_REF_NOT_CONFIRMED"
        road_ref_coherent = "NO"

    selected_distance = float(selected["_distance_m"])
    nearest_distance = float(nearest["_distance_m"])

    nearby_count = int(
        (gdf["_distance_m"] <= NEARBY_RADIUS_M).sum()
    )

    coherent_count = int(
        (
            (gdf["_ref_match"])
            & (gdf["_distance_m"] <= REF_COHERENT_MAX_M)
        ).sum()
    )

    # Top candidate summary: diagnostica compatta.
    summary_parts = []

    for _, candidate in gdf.head(5).iterrows():
        summary_parts.append(
            "seg={seg},d={d:.1f},ref={ref},name={name},dir={dir}".format(
                seg=fmt(candidate["segment_uid"]),
                d=float(candidate["_distance_m"]),
                ref=fmt(candidate["ref"]),
                name=fmt(candidate["name"]),
                dir=fmt(candidate["direction_code"]),
            )
        )

    candidate_summary = " || ".join(summary_parts)

    # Segmenti ref-coherent molto vicini:
    # utile soltanto come indizio per eventuale dual carriageway.
    pair_candidates = gdf[
        (gdf["_ref_match"])
        & (gdf["_distance_m"] <= PAIR_DIAGNOSTIC_RADIUS_M)
    ].copy()

    pair_parts = []

    for _, candidate in pair_candidates.head(8).iterrows():
        pair_parts.append(
            "{seg}[d={d:.1f},dir={dir}]".format(
                seg=fmt(candidate["segment_uid"]),
                d=float(candidate["_distance_m"]),
                dir=fmt(candidate["direction_code"]),
            )
        )

    pair_diagnostic = " | ".join(pair_parts)

    segment_uid = clean_value(selected["segment_uid"])

    # -------------------------------------------------------------------------
    # B2 lookup
    # -------------------------------------------------------------------------

    edge_rows, endpoint_cols = b2_edges_for_segment(
        b2,
        segment_uid,
    )

    edge_ids = [clean_value(r[0]) for r in edge_rows]

    measurement_operator, measurement_reason = (
        infer_measurement_operator(
            edge_rows,
            endpoint_cols,
        )
    )

    result = {
        **station,
        "ANAS_X_32632": round(x, 3),
        "ANAS_Y_32632": round(y, 3),

        "NEAREST_OSM_DISTANCE_M": round(nearest_distance, 3),
        "MATCH_DISTANCE_M": round(selected_distance, 3),

        "OSM_SEGMENT_ID": segment_uid,
        "OSM_PHYSICAL_SEGMENT": segment_uid,

        "OSM_WAY_ID": clean_value(selected["way_id"]),
        "OSM_U": clean_value(selected["osm_u"]),
        "OSM_V": clean_value(selected["osm_v"]),

        "OSM_REF": clean_value(selected["ref"]),
        "OSM_NAME": clean_value(selected["name"]),
        "OSM_HIGHWAY": clean_value(selected["highway"]),

        "DIRECTION_CODE": clean_value(selected["direction_code"]),
        "DIRECTION_STATUS": clean_value(selected["direction_status"]),

        "N_CANDIDATES_NEARBY": nearby_count,
        "N_REF_COHERENT_300M": coherent_count,

        "ROAD_REF_COHERENT": road_ref_coherent,
        "MATCH_SELECTION_BASIS": selection_basis,

        "RELEVANT_DIRECTED_EDGE_IDS": (
            "|".join(edge_ids) if edge_ids else ""
        ),

        "MEASUREMENT_OPERATOR_HINT": measurement_operator,
        "MEASUREMENT_REASON": measurement_reason,

        "PAIR_DIAGNOSTIC": pair_diagnostic,
        "CANDIDATE_SUMMARY": candidate_summary,
    }

    results.append(result)

    print(
        f"{section_id:>6} | "
        f"{station['QUALITY_CLASS']} | "
        f"{road:<8} | "
        f"d={selected_distance:7.2f} m | "
        f"seg={segment_uid:<18} | "
        f"ref={fmt(selected['ref']):<12} | "
        f"REF_OK={road_ref_coherent:<3} | "
        f"near={nearby_count:<3} | "
        f"edges={('|'.join(edge_ids) if edge_ids else '<NONE>'):<20} | "
        f"op={measurement_operator}"
    )

    if road_ref_coherent == "NO":
        print(
            f"       UNCERTAIN_DETAIL | {candidate_summary}"
        )


# =============================================================================
# OUTPUT CSV — TEMPORARY ONLY
# =============================================================================

OUT_DIR.mkdir(parents=True, exist_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

out_csv = OUT_DIR / f"ANAS_5_8D_spatial_match_{stamp}.csv"

fieldnames = [
    "SECTION_ID",
    "ROAD",
    "LOCATION",
    "QUALITY_CLASS",
    "TGMA_LIGHT_2024",
    "LAT",
    "LON",
    "ANAS_X_32632",
    "ANAS_Y_32632",

    "NEAREST_OSM_DISTANCE_M",
    "MATCH_DISTANCE_M",

    "OSM_SEGMENT_ID",
    "OSM_PHYSICAL_SEGMENT",
    "OSM_WAY_ID",
    "OSM_U",
    "OSM_V",
    "OSM_REF",
    "OSM_NAME",
    "OSM_HIGHWAY",

    "DIRECTION_CODE",
    "DIRECTION_STATUS",

    "N_CANDIDATES_NEARBY",
    "N_REF_COHERENT_300M",
    "ROAD_REF_COHERENT",
    "MATCH_SELECTION_BASIS",

    "RELEVANT_DIRECTED_EDGE_IDS",
    "MEASUREMENT_OPERATOR_HINT",
    "MEASUREMENT_REASON",

    "PAIR_DIAGNOSTIC",
    "CANDIDATE_SUMMARY",
]

with out_csv.open(
    "w",
    newline="",
    encoding="utf-8-sig",
) as f:
    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(results)


# =============================================================================
# COMPACT SUMMARY
# =============================================================================

n_total = len(results)

n_ref_ok = sum(
    r["ROAD_REF_COHERENT"] == "YES"
    for r in results
)

n_op_bidir = sum(
    r["MEASUREMENT_OPERATOR_HINT"] == "BIDIRECTIONAL_SUM"
    for r in results
)

n_op_unresolved = sum(
    r["MEASUREMENT_OPERATOR_HINT"] == "UNRESOLVED"
    for r in results
)

print("-" * 118)
print("PASSO 2 — COMPACT SUMMARY")
print(f"SECTIONS_PROCESSED     = {n_total}")
print(f"ROAD_REF_COHERENT      = {n_ref_ok}")
print(f"ROAD_REF_NOT_CONFIRMED = {n_total - n_ref_ok}")
print(f"BIDIRECTIONAL_SUM_HINT = {n_op_bidir}")
print(f"MEASUREMENT_UNRESOLVED = {n_op_unresolved}")
print(f"TEMP_CSV               = {out_csv}")
print("FROZEN_FILES_MODIFIED  = NO")
print("ROUTING_RECOMPUTED     = NO")
print("SHORTEST_PATH_RUN      = NO")
print("=" * 118)

