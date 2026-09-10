from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone

TARGET_DIR = Path(r"C:\Tesi\Tesi_QGIS\02_package\anas_calibration_v0")
CSV_PATH = TARGET_DIR / "ANAS_5_8D_calibration_mapping_v01.csv"
MANIFEST_PATH = TARGET_DIR / "ANAS_5_8D_calibration_mapping_v01_manifest.json"

ROWS = [
    {
        "SECTION_ID": "920044", "ROAD": "A0", "TGMA_LIGHT_2024": 15345, "QUALITY_CLASS": "A",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "148319235:8", "OPPOSITE_SEGMENT_UID": "832928883:0",
        "PRIMARY_EDGE_IDS": "803475", "OPPOSITE_EDGE_IDS": "1481717",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920022", "ROAD": "RA13", "TGMA_LIGHT_2024": 23143, "QUALITY_CLASS": "A",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "203141242:23", "OPPOSITE_SEGMENT_UID": "104915080:18",
        "PRIMARY_EDGE_IDS": "1013279", "OPPOSITE_EDGE_IDS": "524227",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920028", "ROAD": "SS13", "TGMA_LIGHT_2024": 6088, "QUALITY_CLASS": "A",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "23261016:11", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "11842|11843", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920034", "ROAD": "SS202", "TGMA_LIGHT_2024": 27512, "QUALITY_CLASS": "A",
        "ROLE": "PRIMARY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "787078230:14", "OPPOSITE_SEGMENT_UID": "26283853:0",
        "PRIMARY_EDGE_IDS": "1464765", "OPPOSITE_EDGE_IDS": "42022",
        "EXTERNAL_EXPOSURE": "LOW", "CORRIDOR_GROUP": "SS202_TRIESTE_URBAN", "INFORMATION_ROLE": "DISTINCT",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920035", "ROAD": "SS202", "TGMA_LIGHT_2024": 15618, "QUALITY_CLASS": "A",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "26259796:11", "OPPOSITE_SEGMENT_UID": "350457892:2",
        "PRIMARY_EDGE_IDS": "41526", "OPPOSITE_EDGE_IDS": "1303401",
        "EXTERNAL_EXPOSURE": "UNCERTAIN", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920037", "ROAD": "SS54", "TGMA_LIGHT_2024": 1224, "QUALITY_CLASS": "A",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "110560535:44", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "547133|547134", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920032", "ROAD": "SS54", "TGMA_LIGHT_2024": 6964, "QUALITY_CLASS": "A",
        "ROLE": "PRIMARY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "1324387447:1", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "1645018|1645019", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "LOW", "CORRIDOR_GROUP": "SS54_CIVIDALE_INTERNAL", "INFORMATION_ROLE": "DISTINCT",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920024", "ROAD": "RA13", "TGMA_LIGHT_2024": 21028, "QUALITY_CLASS": "B",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "42941151:4", "OPPOSITE_SEGMENT_UID": "191942226:1",
        "PRIMARY_EDGE_IDS": "237523", "OPPOSITE_EDGE_IDS": "979577",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920026", "ROAD": "RA13", "TGMA_LIGHT_2024": 22770, "QUALITY_CLASS": "B",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "156185537:0", "OPPOSITE_SEGMENT_UID": "156185538:0",
        "PRIMARY_EDGE_IDS": "831098", "OPPOSITE_EDGE_IDS": "831099",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920039", "ROAD": "SS52BIS", "TGMA_LIGHT_2024": 8015, "QUALITY_CLASS": "B",
        "ROLE": "PRIMARY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "904801580:1", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "1509461|1509462", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "LOW", "CORRIDOR_GROUP": "SS52BIS_CARNIA_INTERNAL", "INFORMATION_ROLE": "DISTINCT",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920038", "ROAD": "SS54", "TGMA_LIGHT_2024": 2843, "QUALITY_CLASS": "B",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "779871751:0", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "1462841|1462842", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920042", "ROAD": "A0", "TGMA_LIGHT_2024": 23127, "QUALITY_CLASS": "C",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "191946557:1", "OPPOSITE_SEGMENT_UID": "28521224:2",
        "PRIMARY_EDGE_IDS": "979768", "OPPOSITE_EDGE_IDS": "79663",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920029", "ROAD": "SS13", "TGMA_LIGHT_2024": 2752, "QUALITY_CLASS": "C",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "185800895:1", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "955871|955872", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920030", "ROAD": "SS14", "TGMA_LIGHT_2024": 4646, "QUALITY_CLASS": "C",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "1119710666:3", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "1568406|1568407", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920031", "ROAD": "SS52BIS", "TGMA_LIGHT_2024": 1040, "QUALITY_CLASS": "C",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "184607670:7", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "946205|946206", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "HIGH", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
    {
        "SECTION_ID": "920040", "ROAD": "SS54", "TGMA_LIGHT_2024": 14659, "QUALITY_CLASS": "C",
        "ROLE": "SENSITIVITY", "MEASUREMENT_OPERATOR": "BIDIRECTIONAL_SUM",
        "PRIMARY_SEGMENT_UID": "165350444:6", "OPPOSITE_SEGMENT_UID": "",
        "PRIMARY_EDGE_IDS": "875099|875100", "OPPOSITE_EDGE_IDS": "",
        "EXTERNAL_EXPOSURE": "LOW", "CORRIDOR_GROUP": "", "INFORMATION_ROLE": "N/A_NON_PRIMARY",
        "QGIS_REVIEW_STATUS": "CLOSED",
    },
]

FIELDS = [
    "SECTION_ID",
    "ROAD",
    "TGMA_LIGHT_2024",
    "QUALITY_CLASS",
    "ROLE",
    "MEASUREMENT_OPERATOR",
    "OSM_PHYSICAL_SEGMENT",
    "RELEVANT_DIRECTED_EDGE_IDS",
    "PRIMARY_SEGMENT_UID",
    "OPPOSITE_SEGMENT_UID",
    "PRIMARY_EDGE_IDS",
    "OPPOSITE_EDGE_IDS",
    "EXTERNAL_EXPOSURE",
    "CORRIDOR_GROUP",
    "INFORMATION_ROLE",
    "QGIS_REVIEW_STATUS",
]

PRIMARY_EXPECTED = {"920034", "920032", "920039"}

def combined_segments(row):
    vals = [row["PRIMARY_SEGMENT_UID"], row["OPPOSITE_SEGMENT_UID"]]
    return "|".join(v for v in vals if v)

def combined_edges(row):
    vals = []
    for field in ("PRIMARY_EDGE_IDS", "OPPOSITE_EDGE_IDS"):
        raw = row[field]
        if raw:
            vals.extend(x for x in raw.split("|") if x)
    return "|".join(vals)

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# -------------------------
# PRE-FLIGHT / NO OVERWRITE
# -------------------------
TARGET_DIR.mkdir(parents=True, exist_ok=True)

existing = [str(p) for p in (CSV_PATH, MANIFEST_PATH) if p.exists()]
if existing:
    print("=" * 92)
    print("FASE 5.8D — CANONICAL PROMOTION")
    print("=" * 92)
    print("VERDICT = FAIL_NO_OVERWRITE")
    for p in existing:
        print(f"EXISTING = {p}")
    print("No file was overwritten.")
    raise SystemExit(2)

# -------------------------
# CONTRACT VALIDATION
# -------------------------
assert len(ROWS) == 16
assert len({r["SECTION_ID"] for r in ROWS}) == 16
assert {r["SECTION_ID"] for r in ROWS if r["ROLE"] == "PRIMARY"} == PRIMARY_EXPECTED
assert sum(r["QUALITY_CLASS"] == "A" for r in ROWS) == 7
assert sum(r["QUALITY_CLASS"] == "B" for r in ROWS) == 4
assert sum(r["QUALITY_CLASS"] == "C" for r in ROWS) == 5
assert sum(r["ROLE"] == "PRIMARY" for r in ROWS) == 3
assert sum(r["ROLE"] == "SENSITIVITY" for r in ROWS) == 13
assert all(r["MEASUREMENT_OPERATOR"] == "BIDIRECTIONAL_SUM" for r in ROWS)
assert all(r["QGIS_REVIEW_STATUS"] == "CLOSED" for r in ROWS)
assert all(len(combined_edges(r).split("|")) == 2 for r in ROWS)

# -------------------------
# WRITE CANONICAL CSV
# -------------------------
with CSV_PATH.open("x", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    for r in ROWS:
        out = {k: r.get(k, "") for k in FIELDS}
        out["OSM_PHYSICAL_SEGMENT"] = combined_segments(r)
        out["RELEVANT_DIRECTED_EDGE_IDS"] = combined_edges(r)
        writer.writerow(out)

csv_sha256 = sha256_file(CSV_PATH)

# -------------------------
# WRITE MANIFEST / PROVENANCE
# -------------------------
manifest = {
    "artifact": "ANAS_5_8D_calibration_mapping_v01.csv",
    "artifact_version": "v01",
    "phase": "5.8D",
    "phase_status": "CLOSED / FROZEN",
    "promotion_status": "CANONICAL",
    "created_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
    "target_directory": str(TARGET_DIR),
    "sha256_csv": csv_sha256,
    "row_count": 16,
    "quality_counts": {"A": 7, "B": 4, "C": 5},
    "role_counts": {"PRIMARY": 3, "SENSITIVITY": 13},
    "primary_sections": ["920034", "920032", "920039"],
    "sensitivity_sections": [
        r["SECTION_ID"] for r in ROWS if r["ROLE"] == "SENSITIVITY"
    ],
    "measurement_operator": "BIDIRECTIONAL_SUM",
    "measurement_mapping": "TGMA ANAS compared with the sum of the two relevant directed OSM/B2 edge flows for the same counted physical road section.",
    "provenance": [
        "ANAS 2024 frozen target dataset: TGMA_LIGHT_2024 and quality classes A/B/C.",
        "FASE 5.8D automated spatial match against frozen G_OSM_operativo_v01.",
        "Manual QGIS review completed for all 16 A/B/C logical sections: OSM_MATCH=OK, QGIS_REVIEW_STATUS=CLOSED.",
        "Read-only B2 directed-edge lookup completed for separated carriageways: PASS_ALL_7.",
        "Approved 5.8D role screening preserved unchanged: PRIMARY={920034,920032,920039}; remaining 13=SENSITIVITY.",
        r"Working review register: C:\Users\visen\OneDrive\Università\UniUD\Tesi\Ricerca bibliografica\Dati elaborati\ANAS\ANAS_5_8D_QGIS_review.csv",
    ],
    "frozen_dependencies": {
        "osm_graph": r"C:\Tesi\Tesi_QGIS\02_package\grafo_operativo_osm\G_OSM_operativo_v01.gpkg",
        "osm_segment_layer": "G_OSM_operativo_segments_v01",
        "directed_edge_db": r"C:\Tesi\Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite",
    },
    "safety": {
        "overwrite_policy": "FORBIDDEN",
        "frozen_artifacts_modified": False,
        "routing_recomputed": False,
        "shortest_paths_rerun": False,
        "qgis_reopened_for_analysis": False,
    },
}

with MANIFEST_PATH.open("x", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")

# -------------------------
# FINAL READ-BACK
# -------------------------
with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
    read_rows = list(csv.DictReader(f, delimiter=";"))

read_sha = sha256_file(CSV_PATH)

assert len(read_rows) == 16
assert read_sha == csv_sha256
assert {r["SECTION_ID"] for r in read_rows if r["ROLE"] == "PRIMARY"} == PRIMARY_EXPECTED
assert all(r["MEASUREMENT_OPERATOR"] == "BIDIRECTIONAL_SUM" for r in read_rows)
assert all(len(r["RELEVANT_DIRECTED_EDGE_IDS"].split("|")) == 2 for r in read_rows)

print("=" * 92)
print("FASE 5.8D — CANONICAL PROMOTION")
print("=" * 92)
print("VERDICT                    = PASS")
print(f"TARGET_DIR                 = {TARGET_DIR}")
print(f"CSV                        = {CSV_PATH}")
print(f"MANIFEST                   = {MANIFEST_PATH}")
print(f"CSV_SHA256                 = {csv_sha256}")
print("ROWS                       = 16")
print("QUALITY_A/B/C              = 7 / 4 / 5")
print("PRIMARY                    = 3")
print("SENSITIVITY                = 13")
print("PRIMARY_SECTIONS           = 920034 | 920032 | 920039")
print("MEASUREMENT_OPERATOR       = BIDIRECTIONAL_SUM (16/16)")
print("DIRECTED_EDGE_PAIRS_READY  = 16/16")
print("OVERWRITE                  = FORBIDDEN / NOT USED")
print("FROZEN_FILES_MODIFIED      = NO")
print("ROUTING_RECOMPUTED         = NO")
print("SHORTEST_PATH_RUN          = NO")
print("=" * 92)
