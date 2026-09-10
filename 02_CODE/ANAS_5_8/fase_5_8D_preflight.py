from pathlib import Path
import sys

GPKG = Path(
    r"C:\Tesi\Tesi_QGIS\02_package\grafo_operativo_osm\G_OSM_operativo_v01.gpkg"
)

EXPECTED_LAYER = "G_OSM_operativo_segments_v01"
EXPECTED_CRS = "EPSG:32632"

print("=" * 78)
print("FASE 5.8D — PASSO 1 — PREFLIGHT G_OSM_operativo")
print("=" * 78)

# ---------------------------------------------------------------------
# 1. File existence
# ---------------------------------------------------------------------

print(f"GPKG_PATH          = {GPKG}")
print(f"GPKG_EXISTS        = {'YES' if GPKG.exists() else 'NO'}")

if not GPKG.exists():
    print("VERDICT            = FAIL_GPKG_NOT_FOUND")
    sys.exit(1)

try:
    import pyogrio
except Exception as e:
    print(f"PYOGRIO_IMPORT     = FAIL: {type(e).__name__}: {e}")
    print("VERDICT            = FAIL_ENVIRONMENT")
    sys.exit(1)

print(f"PYOGRIO_VERSION    = {pyogrio.__version__}")

# ---------------------------------------------------------------------
# 2. Layers
# ---------------------------------------------------------------------

try:
    layers_raw = pyogrio.list_layers(GPKG)
    layers = [str(row[0]) for row in layers_raw]
except Exception as e:
    print(f"LAYER_SCAN         = FAIL: {type(e).__name__}: {e}")
    print("VERDICT            = FAIL_LAYER_SCAN")
    sys.exit(1)

print(f"LAYER_COUNT        = {len(layers)}")
print(f"EXPECTED_LAYER     = {EXPECTED_LAYER}")
print(
    f"EXPECTED_FOUND     = "
    f"{'YES' if EXPECTED_LAYER in layers else 'NO'}"
)

if EXPECTED_LAYER not in layers:
    print("AVAILABLE_LAYERS   = " + " | ".join(layers))
    print("VERDICT            = FAIL_EXPECTED_LAYER_NOT_FOUND")
    sys.exit(1)

# ---------------------------------------------------------------------
# 3. Read metadata only — no feature loading / no writes
# ---------------------------------------------------------------------

try:
    info = pyogrio.read_info(GPKG, layer=EXPECTED_LAYER)
except Exception as e:
    print(f"READ_INFO          = FAIL: {type(e).__name__}: {e}")
    print("VERDICT            = FAIL_READ_INFO")
    sys.exit(1)

fields = [str(x) for x in info.get("fields", [])]

crs = str(info.get("crs"))
feature_count = info.get("features")
geometry_type = info.get("geometry_type")
fid_column = info.get("fid_column")

print(f"FEATURE_COUNT      = {feature_count}")
print(f"GEOMETRY_TYPE      = {geometry_type}")
print(f"CRS                = {crs}")
print(f"EXPECTED_CRS       = {EXPECTED_CRS}")

crs_match = (
    crs.upper().replace(" ", "") == EXPECTED_CRS.upper().replace(" ", "")
)

print(f"CRS_MATCH          = {'YES' if crs_match else 'NO'}")
print(f"FID_COLUMN         = {fid_column}")
print(f"FIELD_COUNT        = {len(fields)}")
print("FIELDS             = " + " | ".join(fields))

# ---------------------------------------------------------------------
# 4. Identify potentially useful matching fields
# ---------------------------------------------------------------------

def select_fields(tokens):
    out = []
    for f in fields:
        low = f.lower()
        if any(token in low for token in tokens):
            out.append(f)
    return out

id_like = select_fields([
    "id", "osm", "way", "edge", "segment", "seg"
])

ref_like = select_fields([
    "ref", "road", "route", "strada"
])

name_like = select_fields([
    "name", "nome"
])

print(
    "ID_LIKE_FIELDS     = "
    + (" | ".join(id_like) if id_like else "<NONE>")
)

print(
    "REF_LIKE_FIELDS    = "
    + (" | ".join(ref_like) if ref_like else "<NONE>")
)

print(
    "NAME_LIKE_FIELDS   = "
    + (" | ".join(name_like) if name_like else "<NONE>")
)

# ---------------------------------------------------------------------
# 5. Manifest presence only
# ---------------------------------------------------------------------

manifest = GPKG.parent / "G_OSM_FINAL_manifest_v01.json"

print(f"MANIFEST_EXISTS    = {'YES' if manifest.exists() else 'NO'}")

# ---------------------------------------------------------------------
# 6. Final verdict
# ---------------------------------------------------------------------

if crs_match:
    print("VERDICT            = PASS_PREFLIGHT")
else:
    print("VERDICT            = FAIL_CRS_MISMATCH")

print("MODE               = READ_ONLY")
print("=" * 78)

