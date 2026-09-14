param(
    [string]$Root = "C:\Tesi",
    [string]$PythonExe = "C:\Tesi\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"

# ==========================================================================================
# B1-EXT-GH - MATERIALIZATION V06
#
# PURPOSE
#   1) Re-verify the frozen FVG/Nord-Est source and its internal Geofabrik provenance.
#   2) Materialize the Chat-Madre-approved national candidate italy-260801.osm.pbf.
#   3) Materialize GraphHopper 11.0 and a portable Temurin JRE 21.
#   4) Verify all downloaded bytes and record a manifest.
#
# IMPORTANT SOURCE SEMANTICS
#   - The frozen Nord-Est PBF is NOT byte-identical to archived nord-est-260801.
#   - Its internal header proves Geofabrik Nord-Est provenance with timestamp
#     2026-08-03T20:21:36Z, sequence 3928.
#   - italy-260801 is therefore used as an APPROVED NEAR-CONTEMPORANEOUS national
#     support candidate, not as an identical snapshot.
#
# HARD STOP
#   - NO GraphHopper graph import.
#   - NO routing.
#   - NO edits to frozen G_OSM / B2 / B4 / B5 / Gamma / OD_PATH_SYSTEM.
# ==========================================================================================

$FrozenPbf = Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf"

$ItalyPbfUrl = "https://download.geofabrik.de/europe/italy-260801.osm.pbf"
$ItalyMd5Url = "https://download.geofabrik.de/europe/italy-260801.osm.pbf.md5"

$GraphHopperJarUrl = "https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar"
$GraphHopperJarSha256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"

$TemurinJreUrl = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.10%2B7/OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip"
$TemurinJreSha256 = "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae"

$ToolRoot = Join-Path $Root "tools\graphhopper\b1_ext_v01"
$DownloadRoot = Join-Path $ToolRoot "downloads"
$RuntimeRoot = Join-Path $ToolRoot "temurin_jre_21_0_10_7"
$GraphHopperJar = Join-Path $ToolRoot "graphhopper-web-11.0.jar"
$JreZip = Join-Path $DownloadRoot "OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip"

$PbfRoot = Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\external_b1"
$ItalyPbf = Join-Path $PbfRoot "italy-260801.osm.pbf"

$ManifestRoot = Join-Path $Root "Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
$ManifestPath = Join-Path $ManifestRoot "B1_EXT_GH_materialization_manifest_v01.json"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$StageRoot = Join-Path $ToolRoot ("_STAGING_" + $Stamp)
$StageJar = Join-Path $StageRoot "graphhopper-web-11.0.jar"
$StageJreZip = Join-Path $StageRoot "OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip"
$StageJre = Join-Path $StageRoot "jre"
$StageItaly = Join-Path $PbfRoot ("italy-260801.osm.pbf.part_" + $Stamp)

# Frozen byte identities already validated in previous gates.
$GosmRoot = Join-Path $Root "Tesi_QGIS\02_package\grafo_operativo_osm"
$GammaCsv = Join-Path $Root "Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv"
$OdRoot = Join-Path $Root "Tesi_QGIS\02_package\od_paths_osm_light"

$FrozenHashes = [ordered]@{}
$FrozenHashes[$FrozenPbf] = "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"
$FrozenHashes[(Join-Path $GosmRoot "G_OSM_operativo_v01.gpkg")] = "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3"
$FrozenHashes[(Join-Path $GosmRoot "osm_directed_edges_v02.sqlite")] = "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859"
$FrozenHashes[(Join-Path $GosmRoot "osm_turn_restrictions_compiled_v01.sqlite")] = "53b352e12aac674513bf6e37458b30775712892a52a9f4011e9bd75d62fcf4bd"
$FrozenHashes[(Join-Path $GosmRoot "osm_turn_state_time_v01.npz")] = "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72"
$FrozenHashes[(Join-Path $GosmRoot "osm_turn_state_length_v01.npz")] = "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2"
$FrozenHashes[(Join-Path $GosmRoot "osm_turn_state_edgeid_v01.npz")] = "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185"
$FrozenHashes[$GammaCsv] = "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5"
$FrozenHashes[(Join-Path $OdRoot "OSM_OD_access_paths_v01.csv")] = "3c0a8786a05719db4ca2a4258250bde8937b8dd017d93fea0c8f4a8a101c8dd3"
$FrozenHashes[(Join-Path $OdRoot "OSM_OD_path_offsets_v01.npy")] = "478efd3a3f6eba6964db9f0a785dfd9405d5ae61af30e4f84538b0699a7a3a08"
$FrozenHashes[(Join-Path $OdRoot "OSM_OD_transition_slots_v01.npy")] = "2a6b06d21b6d3eea7132a0154bbb4c74d305a4ea582d780e07b5abeed24d2c1d"

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $status = if ($Ok) { "PASS" } else { "FAIL" }
    "{0,-48} {1,-5} {2}" -f $Name, $status, $Detail
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-Md5([string]$Path) {
    return (Get-FileHash -Algorithm MD5 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-RemoteText([string]$Url) {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 60
    if ([int]$r.StatusCode -ne 200) {
        throw "HTTP $($r.StatusCode) for $Url"
    }
    $c = $r.Content
    if ($c -is [byte[]]) {
        return ([System.Text.Encoding]::UTF8.GetString($c)).Trim()
    }
    if ($c -is [System.Array]) {
        try {
            return ([System.Text.Encoding]::UTF8.GetString([byte[]]$c)).Trim()
        }
        catch {
            return (($c | ForEach-Object { [string]$_ }) -join "").Trim()
        }
    }
    return ([string]$c).Trim()
}

function Parse-Md5([string]$Text) {
    $m = [regex]::Match($Text.ToLowerInvariant(), '\b[a-f0-9]{32}\b')
    if (-not $m.Success) {
        throw "Cannot parse MD5 from: $Text"
    }
    return $m.Value
}

function Get-Head([string]$Url) {
    $r = Invoke-WebRequest -Method Head -Uri $Url -UseBasicParsing -TimeoutSec 60
    $rawLen = $r.Headers["Content-Length"]
    if ($rawLen -is [System.Array]) {
        $rawLen = $rawLen | Select-Object -First 1
    }
    $len = $null
    if ($null -ne $rawLen -and ([string]$rawLen).Trim() -ne "") {
        $len = [int64]::Parse(([string]$rawLen).Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
    }
    return [ordered]@{
        status = [int]$r.StatusCode
        length = $len
        last_modified = [string]$r.Headers["Last-Modified"]
    }
}

function Verify-Frozen {
    foreach ($kv in $FrozenHashes.GetEnumerator()) {
        if (-not (Test-Path $kv.Key -PathType Leaf)) {
            throw "Frozen artifact missing: $($kv.Key)"
        }
        $h = Get-Sha256 $kv.Key
        if ($h -ne ([string]$kv.Value).ToLowerInvariant()) {
            throw "Frozen SHA256 mismatch: $($kv.Key)"
        }
    }
}

function Ensure-Dir([string]$Path) {
    if (-not (Test-Path $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Download-Small([string]$Url, [string]$Destination) {
    if (Test-Path $Destination -PathType Leaf) {
        Remove-Item -LiteralPath $Destination -Force
    }
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 0
}

function Download-Large([string]$Url, [string]$Destination) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -eq $curl) {
        throw "curl.exe not available for robust large-file download"
    }
    if (Test-Path $Destination -PathType Leaf) {
        Remove-Item -LiteralPath $Destination -Force
    }
    & $curl.Source -L --fail --retry 5 --retry-delay 5 --output $Destination $Url
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe failed for $Url"
    }
}

function Get-JavaMajor([string]$JavaExe) {
    $line = (& $JavaExe -version 2>&1 | Select-Object -First 1)
    $text = [string]$line
    if ($text -match '"([0-9]+)(?:\.[0-9]+)*') {
        return [int]$Matches[1]
    }
    if ($text -match 'version\s+([0-9]+)') {
        return [int]$Matches[1]
    }
    return -1
}

function Get-PbfHeader([string]$Path) {
    # Windows PowerShell 5.1 may auto-convert ISO date strings when parsing JSON.
    # Use plain TAB-delimited text so timestamp values remain exact strings.
    $code = @'
import sys
import osmium

p = sys.argv[1]
r = osmium.io.Reader(p)
try:
    h = r.header()
    values = {
        "generator": h.get("generator", ""),
        "base_url": h.get("osmosis_replication_base_url", ""),
        "sequence": h.get("osmosis_replication_sequence_number", ""),
        "timestamp": h.get("osmosis_replication_timestamp", "") or h.get("timestamp", ""),
    }
finally:
    r.close()

for key in ("generator", "base_url", "sequence", "timestamp"):
    value = str(values.get(key, "")).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    print(key + "\t" + value)
'@

    $rawLines = @($code | & $PythonExe - $Path)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read PBF header: $Path"
    }

    $values = @{}
    foreach ($line in $rawLines) {
        $parts = ([string]$line) -split "`t", 2
        if ($parts.Count -eq 2) {
            $values[[string]$parts[0]] = [string]$parts[1]
        }
    }

    foreach ($required in @("generator", "base_url", "sequence", "timestamp")) {
        if (-not $values.ContainsKey($required)) {
            throw "PBF header field missing: $required in $Path"
        }
    }

    return (New-Object PSObject -Property @{
        generator = [string]$values["generator"]
        base_url  = [string]$values["base_url"]
        sequence  = [string]$values["sequence"]
        timestamp = [string]$values["timestamp"]
    })
}

function Cleanup-Staging {
    if (Test-Path $StageItaly -PathType Leaf) {
        Remove-Item -LiteralPath $StageItaly -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $StageRoot -PathType Container) {
        Remove-Item -LiteralPath $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    Write-Host ("=" * 126)
    Write-Host "B1-EXT-GH - MATERIALIZATION V06"
    Write-Host ("=" * 126)
    Write-Host "NO GRAPH IMPORT / NO ROUTING / ADDITIVE MATERIALIZATION ONLY"
    Write-Host ""

    # ----------------------------------------------------------------------------------
    # A. BEFORE-WRITE GATE
    # ----------------------------------------------------------------------------------
    Write-Host "A. BEFORE-WRITE GATE"

    if (-not (Test-Path $PythonExe -PathType Leaf)) {
        throw "Project Python missing: $PythonExe"
    }

    Verify-Frozen
    Write-Check "Frozen byte-integrity before run" $true "ALL EXPECTED SHA256 MATCH"

    $frozenHeader = Get-PbfHeader $FrozenPbf
    $frozenTimestampText = [string]$frozenHeader.timestamp
    $frozenSequenceText = [string]$frozenHeader.sequence
    $frozenBaseUrlText = [string]$frozenHeader.base_url
    $frozenProvOk = (($frozenBaseUrlText -match "download\.geofabrik\.de/europe/italy/nord-est-updates") -and ($frozenSequenceText -eq "3928") -and ($frozenTimestampText -eq "2026-08-03T20:21:36Z"))
    Write-Check "Frozen Geofabrik provenance" $frozenProvOk (
        "timestamp=" + $frozenHeader.timestamp +
        " sequence=" + $frozenHeader.sequence +
        " generator=" + $frozenHeader.generator
    )
    if (-not $frozenProvOk) {
        throw "Frozen PBF provenance does not match the validated diagnostic."
    }

    $frozenMd5 = Get-Md5 $FrozenPbf
    Write-Host ("Frozen MD5 = " + $frozenMd5)

    $italyMd5Text = Get-RemoteText $ItalyMd5Url
    $expectedItalyMd5 = Parse-Md5 $italyMd5Text
    Write-Host ("Italy 260801 official MD5 sidecar = " + $italyMd5Text)

    $italyHead = Get-Head $ItalyPbfUrl
    $italyRemoteOk = (($italyHead.status -eq 200) -and ($null -ne $italyHead.length) -and ([int64]$italyHead.length -gt 2000000000L))
    Write-Check "Italy 260801 remote PBF" $italyRemoteOk (
        "HTTP=" + $italyHead.status +
        " bytes=" + $italyHead.length +
        " Last-Modified=" + $italyHead.last_modified
    )
    if (-not $italyRemoteOk) {
        throw "Italy 260801 remote PBF gate failed"
    }

    $driveLetter = ([IO.Path]::GetPathRoot($Root)).Substring(0,1)
    $drive = Get-PSDrive -Name $driveLetter
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    $diskOk = $freeGB -ge 20.0
    Write-Check "Free disk >= 20 GiB" $diskOk ("{0} GiB" -f $freeGB)
    if (-not $diskOk) {
        throw "Insufficient free disk"
    }

    Write-Host ""
    Write-Host "SOURCE POLICY = ACCEPTED"
    Write-Host "Frozen source provenance = Geofabrik Nord-Est @ 2026-08-03T20:21:36Z."
    Write-Host "National candidate = Geofabrik italy-260801, approved as near-contemporaneous."
    Write-Host "No claim of byte-identical or same-sequence snapshot is made."
    Write-Host ""

    # ----------------------------------------------------------------------------------
    # B. ADDITIVE DIRECTORIES
    # ----------------------------------------------------------------------------------
    Write-Host "B. ADDITIVE DIRECTORIES"
    Ensure-Dir (Join-Path $Root "tools\graphhopper")
    Ensure-Dir $ToolRoot
    Ensure-Dir $DownloadRoot
    Ensure-Dir $PbfRoot
    Ensure-Dir $ManifestRoot
    Ensure-Dir $StageRoot

    # ----------------------------------------------------------------------------------
    # C. GRAPHHOPPER JAR
    # ----------------------------------------------------------------------------------
    Write-Host ""
    Write-Host "C. GRAPHHOPPER 11.0 JAR"

    if (Test-Path $GraphHopperJar -PathType Leaf) {
        $h = Get-Sha256 $GraphHopperJar
        if ($h -ne $GraphHopperJarSha256) {
            throw "Existing GraphHopper JAR has wrong SHA256; refusing overwrite."
        }
        Write-Check "Existing GraphHopper JAR" $true $h
    }
    else {
        Download-Small $GraphHopperJarUrl $StageJar
        $h = Get-Sha256 $StageJar
        Write-Check "Downloaded GraphHopper JAR SHA256" ($h -eq $GraphHopperJarSha256) $h
        if ($h -ne $GraphHopperJarSha256) {
            throw "GraphHopper JAR SHA256 mismatch"
        }
        Move-Item -LiteralPath $StageJar -Destination $GraphHopperJar
    }

    # ----------------------------------------------------------------------------------
    # D. PORTABLE JRE
    # ----------------------------------------------------------------------------------
    Write-Host ""
    Write-Host "D. PORTABLE TEMURIN JRE 21"

    $javaExe = $null
    if (Test-Path $RuntimeRoot -PathType Container) {
        $candidates = @(Get-ChildItem -Path $RuntimeRoot -Filter "java.exe" -File -Recurse |
            Where-Object { $_.FullName -match "\\bin\\java\.exe$" })
        foreach ($j in $candidates) {
            if ((Get-JavaMajor $j.FullName) -ge 17) {
                $javaExe = $j.FullName
                break
            }
        }
        if ($null -eq $javaExe) {
            throw "Existing portable runtime is invalid; refusing overwrite."
        }
        Write-Check "Existing portable Java" $true ("major=" + (Get-JavaMajor $javaExe))
    }
    else {
        if (-not (Test-Path $JreZip -PathType Leaf)) {
            Download-Small $TemurinJreUrl $StageJreZip
            $h = Get-Sha256 $StageJreZip
            Write-Check "Downloaded Temurin ZIP SHA256" ($h -eq $TemurinJreSha256) $h
            if ($h -ne $TemurinJreSha256) {
                throw "Temurin ZIP SHA256 mismatch"
            }
            Move-Item -LiteralPath $StageJreZip -Destination $JreZip
        }
        else {
            $h = Get-Sha256 $JreZip
            if ($h -ne $TemurinJreSha256) {
                throw "Existing Temurin ZIP has wrong SHA256; refusing overwrite."
            }
            Write-Check "Existing Temurin ZIP" $true $h
        }

        New-Item -ItemType Directory -Path $StageJre | Out-Null
        Expand-Archive -LiteralPath $JreZip -DestinationPath $StageJre -Force

        $candidates = @(Get-ChildItem -Path $StageJre -Filter "java.exe" -File -Recurse |
            Where-Object { $_.FullName -match "\\bin\\java\.exe$" })
        foreach ($j in $candidates) {
            if ((Get-JavaMajor $j.FullName) -ge 17) {
                $javaExe = $j.FullName
                break
            }
        }
        if ($null -eq $javaExe) {
            throw "No valid Java >=17 in extracted Temurin runtime"
        }

        Move-Item -LiteralPath $StageJre -Destination $RuntimeRoot

        $candidates = @(Get-ChildItem -Path $RuntimeRoot -Filter "java.exe" -File -Recurse |
            Where-Object { $_.FullName -match "\\bin\\java\.exe$" })
        $javaExe = $null
        foreach ($j in $candidates) {
            if ((Get-JavaMajor $j.FullName) -ge 17) {
                $javaExe = $j.FullName
                break
            }
        }
        if ($null -eq $javaExe) {
            throw "Portable Java validation failed after materialization"
        }
        Write-Check "Portable Java" $true ("major=" + (Get-JavaMajor $javaExe) + " path=" + $javaExe)
    }

    # ----------------------------------------------------------------------------------
    # E. ITALY PBF
    # ----------------------------------------------------------------------------------
    Write-Host ""
    Write-Host "E. ITALY 260801 PBF"

    if (Test-Path $ItalyPbf -PathType Leaf) {
        $md5 = Get-Md5 $ItalyPbf
        if ($md5 -ne $expectedItalyMd5) {
            throw "Existing Italy PBF MD5 mismatch; refusing overwrite."
        }
        Write-Check "Existing Italy PBF MD5" $true $md5
    }
    else {
        Write-Host "Large download starting (~2.1 GiB)."
        Download-Large $ItalyPbfUrl $StageItaly

        $actualSize = (Get-Item -LiteralPath $StageItaly).Length
        $sizeOk = ($actualSize -eq [int64]$italyHead.length)
        Write-Check "Downloaded Italy PBF size" $sizeOk (
            "actual=" + $actualSize + " expected=" + $italyHead.length
        )
        if (-not $sizeOk) {
            throw "Italy PBF byte-size mismatch"
        }

        $md5 = Get-Md5 $StageItaly
        $md5Ok = ($md5 -eq $expectedItalyMd5)
        Write-Check "Downloaded Italy PBF MD5" $md5Ok $md5
        if (-not $md5Ok) {
            throw "Italy PBF MD5 mismatch"
        }

        Move-Item -LiteralPath $StageItaly -Destination $ItalyPbf
    }

    Write-Host "Computing project SHA256 for national PBF..."
    $italySha = Get-Sha256 $ItalyPbf
    $italyMd5 = Get-Md5 $ItalyPbf
    $italyHeader = Get-PbfHeader $ItalyPbf

    Write-Check "Italy PBF official MD5" ($italyMd5 -eq $expectedItalyMd5) $italyMd5
    Write-Check "Italy PBF project SHA256" $true $italySha
    Write-Host (
        "Italy internal header: timestamp=" + $italyHeader.timestamp +
        " sequence=" + $italyHeader.sequence +
        " generator=" + $italyHeader.generator +
        " base_url=" + $italyHeader.base_url
    )

    $frozenTs = [DateTimeOffset]::Parse(
        $frozenTimestampText,
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    $italyTs = [DateTimeOffset]::Parse(
        [string]$italyHeader.timestamp,
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    $offsetHours = [math]::Round(($frozenTs - $italyTs).TotalHours, 3)
    Write-Host ("TEMPORAL_OFFSET_FROZEN_MINUS_ITALY_HOURS = " + $offsetHours)

    # ----------------------------------------------------------------------------------
    # F. FINAL FROZEN INTEGRITY
    # ----------------------------------------------------------------------------------
    Write-Host ""
    Write-Host "F. FROZEN BYTE-INTEGRITY POSTCHECK"
    Verify-Frozen
    Write-Check "Frozen byte-integrity after run" $true "UNCHANGED"

    # ----------------------------------------------------------------------------------
    # G. MANIFEST
    # ----------------------------------------------------------------------------------
    Write-Host ""
    Write-Host "G. MANIFEST"

    $manifest = [ordered]@{
        schema = "B1_EXT_GH_MATERIALIZATION_MANIFEST_V01"
        created_local = (Get-Date).ToString("o")
        role = "EXTERNAL_ITALY_ROUTING_SUPPORT_ONLY"
        source_policy = "NEAR_CONTEMPORANEOUS_CANDIDATE"
        frozen_source = [ordered]@{
            path = $FrozenPbf
            sha256 = Get-Sha256 $FrozenPbf
            md5 = $frozenMd5
            generator = [string]$frozenHeader.generator
            replication_base_url = $frozenBaseUrlText
            replication_sequence = $frozenSequenceText
            replication_timestamp = $frozenTimestampText
        }
        national_source = [ordered]@{
            file = "italy-260801.osm.pbf"
            path = $ItalyPbf
            url = $ItalyPbfUrl
            official_md5_url = $ItalyMd5Url
            official_md5 = $expectedItalyMd5
            verified_md5 = $italyMd5
            project_sha256 = $italySha
            size_bytes = (Get-Item -LiteralPath $ItalyPbf).Length
            generator = [string]$italyHeader.generator
            replication_base_url = [string]$italyHeader.base_url
            replication_sequence = [string]$italyHeader.sequence
            replication_timestamp = [string]$italyHeader.timestamp
            frozen_minus_italy_temporal_offset_hours = $offsetHours
            identity_relation = "NOT_IDENTICAL_NEAR_CONTEMPORANEOUS"
        }
        graphhopper = [ordered]@{
            version = "11.0"
            jar_path = $GraphHopperJar
            jar_sha256 = Get-Sha256 $GraphHopperJar
        }
        java = [ordered]@{
            distribution = "Eclipse Temurin"
            version = "21.0.10+7"
            java_exe = $javaExe
            major = Get-JavaMajor $javaExe
            zip_sha256 = Get-Sha256 $JreZip
        }
        hard_stop = [ordered]@{
            graph_import = "NOT_STARTED"
            routing = "NOT_STARTED"
            frozen_artifacts_modified = $false
            next_gate = "HYBRID_B5_GRAPHHOPPER_INTERFACE_VALIDATION"
        }
    }

    if (Test-Path $ManifestPath -PathType Leaf) {
        throw "NO OVERWRITE: manifest already exists: $ManifestPath"
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
    $manifestSha = Get-Sha256 $ManifestPath
    Write-Check "Manifest" $true $ManifestPath
    Write-Check "Manifest SHA256" $true $manifestSha

    Cleanup-Staging

    Write-Host ""
    Write-Host ("=" * 126)
    Write-Host "B1_EXT_GH_MATERIALIZATION = PASS"
    Write-Host "FROZEN_SOURCE_PROVENANCE = GEOFABRIK_NORD_EST_2026-08-03_CONFIRMED"
    Write-Host "NATIONAL_SOURCE = GEOFABRIK_ITALY_260801_VERIFIED"
    Write-Host "SOURCE_RELATION = NEAR_CONTEMPORANEOUS_NOT_IDENTICAL"
    Write-Host ("TEMPORAL_OFFSET_HOURS = " + $offsetHours)
    Write-Host ("ITALY_PBF_SHA256 = " + $italySha)
    Write-Host "PORTABLE_JAVA = MATERIALIZED_AND_VERIFIED"
    Write-Host "GRAPHHOPPER_11 = MATERIALIZED_AND_VERIFIED"
    Write-Host "FROZEN_INTERNAL_HASHES = UNCHANGED"
    Write-Host "GRAPH_IMPORT = NOT_STARTED"
    Write-Host "ROUTING = NOT_STARTED"
    Write-Host "NEXT_GATE = HYBRID_B5_GRAPHHOPPER_INTERFACE_VALIDATION"
    Write-Host "=== RUN COMPLETATA ==="
    exit 0
}
catch {
    Write-Host ""
    Write-Host ("=" * 126)
    Write-Host "B1_EXT_GH_MATERIALIZATION = FAIL"
    Write-Host ("ERROR = " + $_.Exception.Message)
    Write-Host "ROLLBACK = CURRENT STAGING ONLY"
    Cleanup-Staging
    Write-Host "GRAPH_IMPORT = NOT_STARTED"
    Write-Host "ROUTING = NOT_STARTED"
    Write-Host "=== RUN COMPLETATA ==="
    exit 2
}
