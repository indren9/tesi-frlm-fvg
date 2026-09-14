param(
    [string]$Root = "C:\Tesi",
    [string]$PythonExe = "C:\Tesi\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ======================================================================================
# B1-EXT GraphHopper native-Windows preflight
# READ-ONLY: no directories, downloads, installs, extraction, graph build or file writes.
# ======================================================================================

$GeofabrikPbfUrl = "https://download.geofabrik.de/europe/italy-260801.osm.pbf"
$GeofabrikMd5Url = "https://download.geofabrik.de/europe/italy-260801.osm.pbf.md5"
$ExpectedPbfSize = 2215945433L

$GraphHopperJarUrl = "https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar"
$ExpectedGraphHopperJarSize = 47346509L
$ExpectedGraphHopperJarSha256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"

$TemurinJreUrl = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.10%2B7/OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip"
$ExpectedTemurinJreSize = 48963112L
$ExpectedTemurinJreSha256 = "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae"

$BaseGpkg = Join-Path $Root "Tesi_QGIS\02_package\base_territoriale_fvg.gpkg"
$GosmRoot = Join-Path $Root "Tesi_QGIS\02_package\grafo_operativo_osm"
$GammaCsv = Join-Path $Root "Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv"
$OdRoot = Join-Path $Root "Tesi_QGIS\02_package\od_paths_osm_light"
$FrozenPbf = Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf"

$ExpectedHashes = [ordered]@{}
$ExpectedHashes[$FrozenPbf] = "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"
$ExpectedHashes[(Join-Path $GosmRoot "G_OSM_operativo_v01.gpkg")] = "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3"
$ExpectedHashes[(Join-Path $GosmRoot "osm_directed_edges_v02.sqlite")] = "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859"
$ExpectedHashes[(Join-Path $GosmRoot "osm_turn_restrictions_compiled_v01.sqlite")] = "53b352e12aac674513bf6e37458b30775712892a52a9f4011e9bd75d62fcf4bd"
$ExpectedHashes[(Join-Path $GosmRoot "osm_turn_state_time_v01.npz")] = "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"
$ExpectedHashes[(Join-Path $GosmRoot "osm_turn_state_length_v01.npz")] = "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2"
$ExpectedHashes[(Join-Path $GosmRoot "osm_turn_state_edgeid_v01.npz")] = "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185"
$ExpectedHashes[$GammaCsv] = "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
$ExpectedHashes[(Join-Path $OdRoot "OSM_OD_access_paths_v01.csv")] = "3c0a8786a05719db4ca2a4258250bde8937b8dd017d93fea0c8f4a8a101c8dd3"
$ExpectedHashes[(Join-Path $OdRoot "OSM_OD_path_offsets_v01.npy")] = "478efd3a3f6eba6964db9f0a785dfd9405d5ae61af30e4f84538b0699a7a3a08"
$ExpectedHashes[(Join-Path $OdRoot "OSM_OD_transition_slots_v01.npy")] = "2a6b06d21b6d3eea7132a0154bbb4c74d305a4ea582d780e07b5abeed24d2c1d"

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $status = if ($Ok) { "PASS" } else { "FAIL" }
    "{0,-42} {1,-5} {2}" -f $Name, $status, $Detail
}

function Get-HeadContentLength([string]$Url) {
    $head = Invoke-WebRequest -Method Head -Uri $Url -UseBasicParsing -TimeoutSec 45
    $rawLen = $head.Headers["Content-Length"]
    if ($rawLen -is [System.Array]) {
        $rawLen = $rawLen | Select-Object -First 1
    }
    if ($null -eq $rawLen -or ([string]$rawLen).Trim() -eq "") {
        throw "HEAD returned no Content-Length"
    }
    $lenText = ([string]$rawLen).Trim()
    $len = [int64]::Parse($lenText, [System.Globalization.CultureInfo]::InvariantCulture)
    return @{
        StatusCode = [int]$head.StatusCode
        Length = $len
    }
}

function Get-JavaMajor([string]$JavaExe) {
    try {
        $first = (& $JavaExe -version 2>&1 | Select-Object -First 1)
        $text = [string]$first
        if ($text -match '"([0-9]+)(?:\.[0-9]+)*') {
            return [int]$Matches[1]
        }
        if ($text -match 'version\s+([0-9]+)') {
            return [int]$Matches[1]
        }
        return -1
    } catch {
        return -1
    }
}

Write-Host ("=" * 118)
Write-Host "B1-EXT-GH - READ-ONLY PREFLIGHT"
Write-Host ("=" * 118)
Write-Host "NO DOWNLOADS / NO INSTALLS / NO EXTRACTION / NO GRAPH BUILD / NO FILE WRITES"
Write-Host ""

$fail = 0
$warn = 0

# --------------------------------------------------------------------------------------
# A. PROJECT ROOT / PYTHON
# --------------------------------------------------------------------------------------
$rootOk = Test-Path $Root -PathType Container
Write-Check "C:\Tesi root" $rootOk $Root
if (-not $rootOk) { $fail++ }

$baseOk = Test-Path $BaseGpkg -PathType Leaf
Write-Check "base_territoriale_fvg.gpkg" $baseOk $BaseGpkg
if (-not $baseOk) { $fail++ }

$pyOk = Test-Path $PythonExe -PathType Leaf
Write-Check "Project Python" $pyOk $PythonExe
if (-not $pyOk) { $fail++ }

if ($pyOk) {
    $importCode = @'
import importlib, sys
mods = ["pandas","geopandas","shapely","pyproj","pyogrio","numpy","osmium"]
missing = []
versions = {}
for m in mods:
    try:
        mod = importlib.import_module(m)
        versions[m] = getattr(mod, "__version__", "unknown")
    except Exception as e:
        missing.append("%s: %s" % (m, e))
print("VERSIONS=" + repr(versions))
if missing:
    print("MISSING=" + repr(missing))
    sys.exit(2)
'@
    $importCode | & $PythonExe -
    $pkgOk = ($LASTEXITCODE -eq 0)
    Write-Check "Required Python packages" $pkgOk "pandas/geopandas/shapely/pyproj/pyogrio/numpy/osmium"
    if (-not $pkgOk) { $fail++ }
}

# --------------------------------------------------------------------------------------
# B. FROZEN BYTE-INTEGRITY
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "FROZEN BYTE-INTEGRITY PRECHECK"
foreach ($item in $ExpectedHashes.GetEnumerator()) {
    $p = [string]$item.Key
    $expected = [string]$item.Value
    if (-not (Test-Path $p -PathType Leaf)) {
        Write-Check ([IO.Path]::GetFileName($p)) $false "MISSING: $p"
        $fail++
        continue
    }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $p).Hash.ToLowerInvariant()
    $ok = ($actual -eq $expected.ToLowerInvariant())
    Write-Check ([IO.Path]::GetFileName($p)) $ok $actual
    if (-not $ok) { $fail++ }
}

# --------------------------------------------------------------------------------------
# C. A0 PHYSICAL-CROSSING ARTIFACT
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "A0 PHYSICAL-CROSSING ARTIFACT"
$dedupExpected = "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe"
$dedupCandidates = @(Get-ChildItem -Path $Root -Filter "deduplicated_physical_crossings_v02.csv" -File -Recurse -ErrorAction SilentlyContinue)
$dedupMatches = @()
foreach ($f in $dedupCandidates) {
    $h = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLowerInvariant()
    if ($h -eq $dedupExpected) {
        $dedupMatches += $f.FullName
    }
}
$dedupOk = ($dedupMatches.Count -ge 1)
Write-Check "A0 dedup exact-hash copy" $dedupOk ("matches=" + $dedupMatches.Count)
if ($dedupMatches.Count -gt 0) {
    $dedupMatches | ForEach-Object { Write-Host "  $_" }
}
if (-not $dedupOk) { $fail++ }

# --------------------------------------------------------------------------------------
# D. HARDWARE / DISK
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "HARDWARE / DISK"
$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$ramOk = $ramGB -ge 15.0
Write-Check "Physical RAM nominal 16 GB" $ramOk ("{0} GiB usable" -f $ramGB)
if (-not $ramOk) { $fail++ }

$driveLetter = ([IO.Path]::GetPathRoot($Root)).Substring(0,1)
$drive = Get-PSDrive -Name $driveLetter
$freeGB = [math]::Round($drive.Free / 1GB, 1)
$diskOk = $freeGB -ge 25.0
Write-Check "Free disk >= 25 GB" $diskOk ("{0} GiB free; 40+ GiB preferred" -f $freeGB)
if (-not $diskOk) { $fail++ }

if ($ramOk -and $ramGB -lt 24.0) {
    Write-Host "  NOTE: 16 GB class machine. Materialization is allowed, but GraphHopper import remains memory-sensitive."
    Write-Host "  Heavy import will be a separate gate; this preflight does NOT authorize it."
    $warn++
}

# --------------------------------------------------------------------------------------
# E. LOCAL JAVA DISCOVERY (OPTIONAL AT THIS STAGE)
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "JAVA DISCOVERY - OPTIONAL FOR PREFLIGHT"

$javaCandidates = @()

$ghToolRoot = Join-Path $Root "tools\graphhopper"
if (Test-Path $ghToolRoot -PathType Container) {
    $portable = @(Get-ChildItem -Path $ghToolRoot -Filter "java.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\bin\\java\.exe$" })
    foreach ($j in $portable) {
        $javaCandidates += $j.FullName
    }
}

$globalJava = Get-Command java.exe -ErrorAction SilentlyContinue
if ($null -ne $globalJava) {
    $javaCandidates += $globalJava.Source
}

$javaCandidates = @($javaCandidates | Select-Object -Unique)
$java17Ok = $false
if ($javaCandidates.Count -eq 0) {
    Write-Host "JAVA_LOCAL_STATUS = NOT_PRESENT"
    Write-Host "PORTABLE_JAVA_DOWNLOAD_REQUIRED = YES"
    Write-Host "This is NOT a preflight failure."
} else {
    foreach ($j in $javaCandidates) {
        $major = Get-JavaMajor $j
        $ok = ($major -ge 17)
        Write-Check "Java >= 17" $ok ("major=$major path=$j")
        if ($ok) { $java17Ok = $true }
    }
    if (-not $java17Ok) {
        Write-Host "PORTABLE_JAVA_DOWNLOAD_REQUIRED = YES"
        Write-Host "Existing Java is too old or unparseable; this is NOT a preflight failure."
    } else {
        Write-Host "PORTABLE_JAVA_DOWNLOAD_REQUIRED = NO"
    }
}

# --------------------------------------------------------------------------------------
# F. REMOTE SOURCE / TOOLCHAIN AVAILABILITY - HEAD ONLY
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "REMOTE AVAILABILITY - HEAD ONLY"

try {
    $r = Get-HeadContentLength $GeofabrikPbfUrl
    $ok = ($r.StatusCode -eq 200 -and $r.Length -eq $ExpectedPbfSize)
    Write-Check "Geofabrik Italy PBF" $ok ("HTTP={0} bytes={1} expected={2}" -f $r.StatusCode,$r.Length,$ExpectedPbfSize)
    if (-not $ok) { $fail++ }
} catch {
    Write-Check "Geofabrik Italy PBF" $false $_.Exception.Message
    $fail++
}

try {
    $headMd5 = Invoke-WebRequest -Method Head -Uri $GeofabrikMd5Url -UseBasicParsing -TimeoutSec 45
    $ok = ([int]$headMd5.StatusCode -eq 200)
    Write-Check "Geofabrik MD5 sidecar" $ok ("HTTP={0}" -f $headMd5.StatusCode)
    if (-not $ok) { $fail++ }
} catch {
    Write-Check "Geofabrik MD5 sidecar" $false $_.Exception.Message
    $fail++
}

try {
    $r = Get-HeadContentLength $GraphHopperJarUrl
    $ok = ($r.StatusCode -eq 200 -and $r.Length -eq $ExpectedGraphHopperJarSize)
    Write-Check "GraphHopper 11.0 JAR" $ok ("HTTP={0} bytes={1} expected={2}" -f $r.StatusCode,$r.Length,$ExpectedGraphHopperJarSize)
    if (-not $ok) { $fail++ }
} catch {
    Write-Check "GraphHopper 11.0 JAR" $false $_.Exception.Message
    $fail++
}

try {
    $r = Get-HeadContentLength $TemurinJreUrl
    $ok = ($r.StatusCode -eq 200 -and $r.Length -eq $ExpectedTemurinJreSize)
    Write-Check "Temurin 21 portable JRE ZIP" $ok ("HTTP={0} bytes={1} expected={2}" -f $r.StatusCode,$r.Length,$ExpectedTemurinJreSize)
    if (-not $ok) { $fail++ }
} catch {
    Write-Check "Temurin 21 portable JRE ZIP" $false $_.Exception.Message
    $fail++
}

Write-Host ""
Write-Host "FROZEN REMOTE IDENTITIES FOR MATERIALIZATION"
Write-Host ("GraphHopper JAR expected SHA256 = " + $ExpectedGraphHopperJarSha256)
Write-Host ("Temurin JRE ZIP expected SHA256 = " + $ExpectedTemurinJreSha256)
Write-Host "The future materialization script MUST verify these SHA256 values after download."

# --------------------------------------------------------------------------------------
# G. B1 ENDPOINT / SOURCE DATA QA
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "B1 ENDPOINT / SOURCE DATA QA"

if ($pyOk -and $baseOk) {
    $odCode = @'
import sys
import pandas as pd
import pyogrio

p = sys.argv[1]

od = pyogrio.read_dataframe(
    p,
    layer="pendolari_extra_regione_fvg_2021_od_xy",
    read_geometry=False
)
fvg = pyogrio.read_dataframe(
    p,
    layer="centroidi_popolazione_comuni_fvg_final"
)
ita = pyogrio.read_dataframe(
    p,
    layer="centroidi_geometrici_italia_2026_xy"
)
bnd = pyogrio.read_dataframe(
    p,
    layer="confine_fvg_dissolto"
)

required = ["Procom_res", "Procom_lav", "Pendolari"]
missing = [c for c in required if c not in od.columns]

print("OD_ROWS=" + str(len(od)))
print("OD_REQUIRED_COLUMNS_MISSING=" + repr(missing))
print("FVG_CENTROIDS=" + str(len(fvg)))
print("ITALY_CENTROIDS=" + str(len(ita)))
print("BOUNDARY_ROWS=" + str(len(bnd)))

if "Procom_lav" in od.columns:
    ext = pd.to_numeric(od["Procom_lav"], errors="coerce")
    print("DISTINCT_EXTERNAL_MUNICIPALITIES=" + str(ext.nunique(dropna=True)))
    print("NULL_EXTERNAL_PROCOM=" + str(int(ext.isna().sum())))

ok = (
    len(od) == 2895
    and not missing
    and len(fvg) == 215
    and len(ita) == 7896
    and len(bnd) == 1
)
sys.exit(0 if ok else 3)
'@
    $odCode | & $PythonExe - $BaseGpkg
    $odOk = ($LASTEXITCODE -eq 0)
    Write-Check "B1 source/endpoint layers" $odOk "OD=2895; FVG centroids=215; Italy centroids=7896; boundary=1"
    if (-not $odOk) { $fail++ }
}

# --------------------------------------------------------------------------------------
# H. ARCHITECTURE GUARDRAILS
# --------------------------------------------------------------------------------------
Write-Host ""
Write-Host "ARCHITECTURE GUARDRAILS"
Write-Host "G_EXT_ITALY_B1_v01 role            = EXTERNAL ITALY ROUTING SUPPORT ONLY"
Write-Host "GraphHopper full-FVG replacement   = FORBIDDEN"
Write-Host "Frozen B2/B4/B5 modification       = FORBIDDEN"
Write-Host "Gamma_OSM modification             = FORBIDDEN"
Write-Host "OD_PATH_SYSTEM_OSM modification    = FORBIDDEN"
Write-Host "Full Italy manual arc audit        = FORBIDDEN"
Write-Host "Heavy graph import                 = NOT AUTHORIZED BY THIS PREFLIGHT"
Write-Host "Next technical gate                = MATERIALIZE PORTABLE JAVA + GH JAR + PBF, THEN VERIFY HYBRID B5/GH COUPLING"

Write-Host ""
Write-Host ("=" * 118)
if ($fail -eq 0) {
    Write-Host "B1_EXT_GH_PREFLIGHT = PASS_TO_MATERIALIZE"
    Write-Host "FAILURES = 0"
    Write-Host "WARNINGS = $warn"
    Write-Host "NO FILES WERE CREATED OR MODIFIED."
    Write-Host "=== RUN COMPLETATA ==="
    exit 0
} else {
    Write-Host "B1_EXT_GH_PREFLIGHT = FAIL"
    Write-Host "FAILURES = $fail"
    Write-Host "WARNINGS = $warn"
    Write-Host "DO NOT MATERIALIZE OR BUILD THE GRAPH."
    Write-Host "=== RUN COMPLETATA ==="
    exit 2
}
