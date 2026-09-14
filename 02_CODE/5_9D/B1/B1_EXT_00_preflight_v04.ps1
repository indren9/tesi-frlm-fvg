param(
    [string]$Root = "C:\Tesi",
    [string]$PythonExe = "C:\Tesi\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$PbfUrl = "https://download.geofabrik.de/europe/italy-260801.osm.pbf"
$Md5Url = "https://download.geofabrik.de/europe/italy-260801.osm.pbf.md5"
$ExpectedPbfSize = 2215945433L
$DockerImage = "ghcr.io/project-osrm/osrm-backend:26.7.3-debian@sha256:a7091038e39a73659767f34ef2d389909b42ea80b09bd2bdca482dce2991cbad"

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
    "{0,-36} {1,-5} {2}" -f $Name, $status, $Detail
}

Write-Host ("=" * 110)
Write-Host "B1-EXT-RUN - READ-ONLY PREFLIGHT"
Write-Host ("=" * 110)
Write-Host "THIS SCRIPT DOES NOT CREATE DIRECTORIES, DOWNLOAD FILES, PULL IMAGES, OR MODIFY ARTIFACTS."
Write-Host ""

$fail = 0
$warn = 0

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
missing=[]
versions={}
for m in mods:
    try:
        mod=importlib.import_module(m)
        versions[m]=getattr(mod,"__version__","unknown")
    except Exception as e:
        missing.append(f"{m}: {e}")
print("VERSIONS="+repr(versions))
if missing:
    print("MISSING="+repr(missing))
    sys.exit(2)
'@
    $importCode | & $PythonExe -
    $pkgOk = ($LASTEXITCODE -eq 0)
    Write-Check "Required Python packages" $pkgOk "pandas/geopandas/shapely/pyproj/pyogrio/numpy/osmium"
    if (-not $pkgOk) { $fail++ }
}

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

Write-Host ""
Write-Host "A0 PHYSICAL-CROSSING ARTIFACT"
$dedupExpected = "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe"
$dedupCandidates = @(Get-ChildItem -Path $Root -Filter "deduplicated_physical_crossings_v02.csv" -File -Recurse -ErrorAction SilentlyContinue)
$dedupMatches = @()
foreach ($f in $dedupCandidates) {
    $h = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLowerInvariant()
    if ($h -eq $dedupExpected) { $dedupMatches += $f.FullName }
}
$dedupOk = ($dedupMatches.Count -ge 1)
Write-Check "A0 dedup exact-hash copy" $dedupOk ("matches=" + $dedupMatches.Count)
if ($dedupMatches.Count -gt 0) { $dedupMatches | ForEach-Object { Write-Host "  $_" } }
if (-not $dedupOk) { $fail++ }

Write-Host ""
Write-Host "HARDWARE / DISK"
$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$ramOk = $ramGB -ge 15.0
Write-Check "Physical RAM nominal 16 GB" $ramOk ("{0} GiB usable (recommended 24 GB or more)" -f $ramGB)
if (-not $ramOk) { $fail++ }

$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($Root).Substring(0,1))
$freeGB = [math]::Round($drive.Free / 1GB, 1)
$diskOk = $freeGB -ge 25
Write-Check "Free disk >= 25 GB" $diskOk ("{0} GB (recommended 40 GB or more)" -f $freeGB)
if (-not $diskOk) { $fail++ }

Write-Host ""
Write-Host "DOCKER / OSRM"
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
$dockerOk = $null -ne $dockerCmd
Write-Check "docker command" $dockerOk ($(if($dockerOk){$dockerCmd.Source}else{"NOT FOUND"}))
if (-not $dockerOk) {
    $fail++
    Write-Host "  ACTION REQUIRED: install/start Docker Desktop with Linux containers before execution."
    Write-Host "  Do not run the execute script until Docker passes this preflight."
} else {
    try {
        $osType = (docker info --format '{{.OSType}}' 2>$null).Trim()
        $daemonOk = ($LASTEXITCODE -eq 0)
        Write-Check "Docker daemon" $daemonOk $osType
        if (-not $daemonOk) { $fail++ }
        if ($daemonOk) {
            $linuxOk = ($osType -eq "linux")
            Write-Check "Docker Linux containers" $linuxOk $osType
            if (-not $linuxOk) { $fail++ }
            $memRaw = (docker info --format '{{.MemTotal}}' 2>$null).Trim()
            if ($memRaw -match '^\d+$') {
                $dockerMemGB = [math]::Round(([double]$memRaw / 1GB),1)
                $dockerMemOk = $dockerMemGB -ge 15.0
                Write-Check "Docker memory nominal 16 GB" $dockerMemOk ("{0} GiB available (recommended 24 GB or more)" -f $dockerMemGB)
                if (-not $dockerMemOk) { $fail++ }
            } else {
                Write-Check "Docker memory readable" $false $memRaw
                $fail++
            }
        }
        docker image inspect $DockerImage *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Check "Pinned OSRM image local" $true "already present"
        } else {
            Write-Check "Pinned OSRM image local" $true "PULL_REQUIRED_AFTER_PREFLIGHT"
            $warn++
        }
    } catch {
        Write-Check "Docker preflight" $false $_.Exception.Message
        $fail++
    }
}

Write-Host ""
Write-Host "SOURCE AVAILABILITY - HEAD ONLY / NO PBF DOWNLOAD"
try {
    $head = Invoke-WebRequest -Method Head -Uri $PbfUrl -UseBasicParsing -TimeoutSec 30
    $rawLen = $head.Headers["Content-Length"]
    if ($rawLen -is [System.Array]) {
        $rawLen = $rawLen | Select-Object -First 1
    }
    $lenText = ([string]$rawLen).Trim()
    $len = [int64]::Parse($lenText, [System.Globalization.CultureInfo]::InvariantCulture)
    $sizeOk = ($len -eq $ExpectedPbfSize)
    Write-Check "Geofabrik PBF HEAD" $sizeOk "HTTP=$($head.StatusCode) bytes=$len expected=$ExpectedPbfSize"
    if (-not $sizeOk) { $fail++ }
} catch {
    Write-Check "Geofabrik PBF HEAD" $false $_.Exception.Message
    $fail++
}
try {
    $head2 = Invoke-WebRequest -Method Head -Uri $Md5Url -UseBasicParsing -TimeoutSec 30
    Write-Check "Geofabrik MD5 HEAD" ($head2.StatusCode -eq 200) "HTTP=$($head2.StatusCode)"
    if ($head2.StatusCode -ne 200) { $fail++ }
} catch {
    Write-Check "Geofabrik MD5 HEAD" $false $_.Exception.Message
    $fail++
}

Write-Host ""
Write-Host "OD LAYER READ-ONLY QA"
if ($pyOk -and $baseOk) {
    $odCode = @'
import sys, pyogrio
p=sys.argv[1]
df=pyogrio.read_dataframe(p, layer="pendolari_extra_regione_fvg_2021_od_xy", read_geometry=False)
print("OD_ROWS="+str(len(df)))
print("OD_COLUMNS="+repr(list(df.columns)))
sys.exit(0 if len(df)==2895 else 3)
'@
    $odCode | & $PythonExe - $BaseGpkg
    $odOk = ($LASTEXITCODE -eq 0)
    Write-Check "OD layer rows = 2895" $odOk "pendolari_extra_regione_fvg_2021_od_xy"
    if (-not $odOk) { $fail++ }
}

Write-Host ""
Write-Host ("=" * 110)
if ($fail -eq 0) {
    Write-Host "B1_EXT_PREFLIGHT = PASS_TO_EXECUTE"
    Write-Host "WARNINGS = $warn"
    Write-Host "No files were created or modified."
    Write-Host "=== RUN COMPLETATA ==="
    exit 0
} else {
    Write-Host "B1_EXT_PREFLIGHT = FAIL"
    Write-Host "FAILURES = $fail"
    Write-Host "WARNINGS = $warn"
    Write-Host "DO NOT RUN B1_EXT_01_execute.ps1."
    Write-Host "=== RUN COMPLETATA ==="
    exit 2
}
