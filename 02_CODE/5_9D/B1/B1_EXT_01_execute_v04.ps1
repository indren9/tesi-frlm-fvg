param(
    [string]$Root = "C:\Tesi",
    [string]$PythonExe = "C:\Tesi\.venv\Scripts\python.exe",
    [string]$ScriptDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Preflight = Join-Path $ScriptDir "B1_EXT_00_preflight_v04.ps1"
$Worker = Join-Path $ScriptDir "b1_ext_route_and_qa.py"

if (-not (Test-Path $Preflight)) { throw "Missing $Preflight" }
if (-not (Test-Path $Worker)) { throw "Missing $Worker" }

Write-Host ("=" * 110)
Write-Host "B1-EXT-RUN - EXECUTION"
Write-Host ("=" * 110)
Write-Host "Re-running mandatory read-only preflight..."
& $Preflight -Root $Root -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) {
    throw "PREFLIGHT FAILED - no execution started."
}

$PbfUrl = "https://download.geofabrik.de/europe/italy-260801.osm.pbf"
$Md5Url = "https://download.geofabrik.de/europe/italy-260801.osm.pbf.md5"
$ExpectedPbfSize = 2215945433L
$Image = "ghcr.io/project-osrm/osrm-backend:26.7.3-debian@sha256:a7091038e39a73659767f34ef2d389909b42ea80b09bd2bdca482dce2991cbad"
$ContainerName = "b1-ext-osrm-v01"

$BaseGpkg = Join-Path $Root "Tesi_QGIS\02_package\base_territoriale_fvg.gpkg"
$GosmRoot = Join-Path $Root "Tesi_QGIS\02_package\grafo_operativo_osm"
$GosmGpkg = Join-Path $GosmRoot "G_OSM_operativo_v01.gpkg"
$GammaCsv = Join-Path $Root "Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv"
$OdRoot = Join-Path $Root "Tesi_QGIS\02_package\od_paths_osm_light"

$SourceDir = Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\italy_archive"
$SourcePbf = Join-Path $SourceDir "italy-260801.osm.pbf"
$SourceMd5 = Join-Path $SourceDir "italy-260801.osm.pbf.md5"

$RunBase = Join-Path $Root "Tesi_QGIS\03_output_temporanei\fase_5_9D\B1_EXT"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $RunBase "G_EXT_ITALY_B1_v01_run_$Stamp"
$OsrmDir = Join-Path $RunDir "osrm"
$OutputDir = Join-Path $RunDir "outputs"
$LogDir = Join-Path $RunDir "logs"
$ProvDir = Join-Path $RunDir "provenance"

if (Test-Path $RunDir) { throw "NO OVERWRITE: $RunDir already exists" }

# Frozen integrity dictionary. The same values are checked before and after.
$Frozen = [ordered]@{}
$Frozen[(Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf")] = "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"
$Frozen[$GosmGpkg] = "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3"
$Frozen[(Join-Path $GosmRoot "osm_directed_edges_v02.sqlite")] = "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859"
$Frozen[(Join-Path $GosmRoot "osm_turn_restrictions_compiled_v01.sqlite")] = "53b352e12aac674513bf6e37458b30775712892a52a9f4011e9bd75d62fcf4bd"
$Frozen[(Join-Path $GosmRoot "osm_turn_state_time_v01.npz")] = "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"
$Frozen[(Join-Path $GosmRoot "osm_turn_state_length_v01.npz")] = "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2"
$Frozen[(Join-Path $GosmRoot "osm_turn_state_edgeid_v01.npz")] = "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185"
$Frozen[$GammaCsv] = "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
$Frozen[(Join-Path $OdRoot "OSM_OD_access_paths_v01.csv")] = "3c0a8786a05719db4ca2a4258250bde8937b8dd017d93fea0c8f4a8a101c8dd3"
$Frozen[(Join-Path $OdRoot "OSM_OD_path_offsets_v01.npy")] = "478efd3a3f6eba6964db9f0a785dfd9405d5ae61af30e4f84538b0699a7a3a08"
$Frozen[(Join-Path $OdRoot "OSM_OD_transition_slots_v01.npy")] = "2a6b06d21b6d3eea7132a0154bbb4c74d305a4ea582d780e07b5abeed24d2c1d"

function FrozenSnapshot {
    param([System.Collections.IDictionary]$Items)
    $out = [ordered]@{}
    foreach ($kv in $Items.GetEnumerator()) {
        $actual = (Get-FileHash -Algorithm SHA256 -Path $kv.Key).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$kv.Value).ToLowerInvariant()) {
            throw "FROZEN HASH MISMATCH before/after run: $($kv.Key)"
        }
        $out[$kv.Key] = $actual
    }
    return $out
}

$before = FrozenSnapshot $Frozen

# From here onward execution is additive only.
New-Item -ItemType Directory -Path $SourceDir -Force | Out-Null
New-Item -ItemType Directory -Path $RunDir,$OsrmDir,$LogDir,$ProvDir | Out-Null

$before | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $ProvDir "frozen_hashes_before.json")

Write-Host ""
Write-Host "SOURCE ACQUISITION"
if (-not (Test-Path $SourceMd5)) {
    & curl.exe -L --fail --retry 5 --retry-delay 3 -o $SourceMd5 $Md5Url
    if ($LASTEXITCODE -ne 0) { throw "MD5 download failed" }
}
if (-not (Test-Path $SourcePbf)) {
    & curl.exe -L --fail --retry 5 --retry-delay 5 -o $SourcePbf $PbfUrl
    if ($LASTEXITCODE -ne 0) { throw "PBF download failed" }
} else {
    Write-Host "PBF already exists; it will be verified and reused."
}

$size = (Get-Item $SourcePbf).Length
if ($size -ne $ExpectedPbfSize) {
    throw "PBF size mismatch: actual=$size expected=$ExpectedPbfSize"
}
$expectedMd5 = ((Get-Content $SourceMd5 -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actualMd5 = (Get-FileHash -Algorithm MD5 -Path $SourcePbf).Hash.ToLowerInvariant()
if ($expectedMd5 -ne $actualMd5) {
    throw "Geofabrik MD5 mismatch: expected=$expectedMd5 actual=$actualMd5"
}
$pbfSha = (Get-FileHash -Algorithm SHA256 -Path $SourcePbf).Hash.ToLowerInvariant()

$sourceProv = [ordered]@{
    artifact = "G_EXT_ITALY_B1_v01"
    source_file = $SourcePbf
    source_url = $PbfUrl
    source_md5_url = $Md5Url
    source_size_bytes = $size
    source_md5 = $actualMd5
    source_sha256 = $pbfSha
    source_candidate = "Geofabrik italy-260801.osm.pbf"
    architecture = "SEPARATE_VERSIONED_ADDITIVE"
}
$sourceProv | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $ProvDir "source_identity.json")

Write-Host "SOURCE_SHA256 = $pbfSha"

Write-Host ""
Write-Host "PINNED OSRM IMAGE"
docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    docker pull $Image
    if ($LASTEXITCODE -ne 0) { throw "Pinned OSRM image pull failed" }
}
$imageId = (docker image inspect $Image --format '{{.Id}}').Trim()
$imageRepoDigest = (docker image inspect $Image --format '{{json .RepoDigests}}').Trim()
"IMAGE=$Image`nID=$imageId`nREPO_DIGESTS=$imageRepoDigest" |
    Set-Content -Encoding UTF8 (Join-Path $ProvDir "osrm_image_identity.txt")

# Copy bundled car.lua byte-for-byte from the pinned image for provenance.
docker run --rm -v "${ProvDir}:/prov" $Image cp /opt/car.lua /prov/car_osrm_v26.7.3.lua
if ($LASTEXITCODE -ne 0) { throw "Could not materialize bundled car.lua" }
$carSha = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $ProvDir "car_osrm_v26.7.3.lua")).Hash.ToLowerInvariant()
Write-Host "CAR_LUA_SHA256 = $carSha"

# Hardlink source PBF into the run working directory. If hardlinks are unavailable,
# copy it. No source bytes are changed.
$RunPbf = Join-Path $OsrmDir "italy-260801.osm.pbf"
try {
    New-Item -ItemType HardLink -Path $RunPbf -Target $SourcePbf | Out-Null
    Write-Host "PBF run copy = NTFS HARDLINK"
} catch {
    Copy-Item -LiteralPath $SourcePbf -Destination $RunPbf
    Write-Host "PBF run copy = FULL COPY"
}

Write-Host ""
Write-Host "OSRM MLD BUILD"
docker run --rm -t -v "${OsrmDir}:/data" $Image `
    osrm-extract -p /opt/car.lua /data/italy-260801.osm.pbf *>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "01_osrm_extract.log")
if ($LASTEXITCODE -ne 0) { throw "osrm-extract failed" }

docker run --rm -t -v "${OsrmDir}:/data" $Image `
    osrm-partition /data/italy-260801.osrm *>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "02_osrm_partition.log")
if ($LASTEXITCODE -ne 0) { throw "osrm-partition failed" }

docker run --rm -t -v "${OsrmDir}:/data" $Image `
    osrm-customize /data/italy-260801.osrm *>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "03_osrm_customize.log")
if ($LASTEXITCODE -ne 0) { throw "osrm-customize failed" }

# Locate the exact A0 dedup artifact by SHA.
$dedupExpected = "74029ef6e4a8169970d307be89cd01ed061b6ac9efded9aa1a1c35c96d32c3fe"
$Dedup = $null
foreach ($f in Get-ChildItem -Path $Root -Filter "deduplicated_physical_crossings_v02.csv" -File -Recurse -ErrorAction SilentlyContinue) {
    $h = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLowerInvariant()
    if ($h -eq $dedupExpected) { $Dedup = $f.FullName; break }
}
if (-not $Dedup) { throw "Exact A0 dedup artifact not found" }
Write-Host "A0_DEDUP = $Dedup"

Write-Host ""
Write-Host "START LOCAL OSRM SERVER"
docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch $ContainerName | ForEach-Object {
    throw "Container $ContainerName already exists. Refusing to remove it automatically."
}
docker run --rm -d --name $ContainerName -p 5005:5000 -v "${OsrmDir}:/data:ro" `
    $Image osrm-routed --algorithm mld --mmap /data/italy-260801.osrm | Out-Null
if ($LASTEXITCODE -ne 0) { throw "osrm-routed start failed" }

try {
    $healthy = $false
    for ($i=0; $i -lt 60; $i++) {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:5005/nearest/v1/driving/13.2380,46.0679?number=1" -TimeoutSec 5
            $healthy = $true
            break
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $healthy) { throw "OSRM server did not become healthy" }

    Write-Host ""
    Write-Host "B1 ROUTING + TARGETED QA"
    & $PythonExe $Worker `
        --base-gpkg $BaseGpkg `
        --dedup-csv $Dedup `
        --gosm-gpkg $GosmGpkg `
        --pbf $SourcePbf `
        --outdir $OutputDir `
        --server "http://127.0.0.1:5005"
    if ($LASTEXITCODE -ne 0) { throw "Python B1 worker failed" }
}
finally {
    docker stop $ContainerName *> $null
}

Write-Host ""
Write-Host "FROZEN BYTE-INTEGRITY POSTCHECK"
$after = FrozenSnapshot $Frozen
$after | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $ProvDir "frozen_hashes_after.json")

$unchanged = $true
foreach ($k in $before.Keys) {
    if ($before[$k] -ne $after[$k]) { $unchanged = $false }
}
if (-not $unchanged) { throw "FROZEN HASH MISMATCH after run" }

# Final manifest of user-facing outputs. OSRM preprocessing intermediates are
# intentionally excluded from the hash list because they are build support, not
# B1 analytical outputs; source/image/profile identities are recorded separately.
$manifestFiles = @()
Get-ChildItem -Path $OutputDir,$ProvDir -File -Recurse | ForEach-Object {
    $manifestFiles += [ordered]@{
        path = $_.FullName
        size_bytes = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    artifact = "G_EXT_ITALY_B1_v01"
    run_dir = $RunDir
    created_at = (Get-Date).ToString("o")
    source = $sourceProv
    osrm_image = $Image
    osrm_image_id = $imageId
    car_lua_sha256 = $carSha
    routing_algorithm = "MLD"
    frozen_internal_hashes = "UNCHANGED"
    output_files = $manifestFiles
}
$manifestPath = Join-Path $RunDir "B1_EXT_manifest_v01.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $manifestPath
$manifestSha = (Get-FileHash -Algorithm SHA256 -Path $manifestPath).Hash.ToLowerInvariant()

Write-Host ""
Write-Host ("=" * 110)
Write-Host "B1_EXT_LOCAL_RUN = COMPLETED"
Write-Host "RUN_DIR = $RunDir"
Write-Host "SOURCE_SHA256 = $pbfSha"
Write-Host "FROZEN_INTERNAL_HASHES = UNCHANGED"
Write-Host "MANIFEST = $manifestPath"
Write-Host "MANIFEST_SHA256 = $manifestSha"
Write-Host "SUMMARY = $(Join-Path $OutputDir 'B1_EXT_summary_v01.json')"
Write-Host "=== RUN COMPLETATA ==="
