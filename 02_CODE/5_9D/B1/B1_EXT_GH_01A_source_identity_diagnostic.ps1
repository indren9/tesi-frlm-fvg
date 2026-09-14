param(
    [string]$Root = "C:\Tesi",
    [string]$PythonExe = "C:\Tesi\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"

# ======================================================================================
# B1-EXT-GH SOURCE IDENTITY DIAGNOSTIC
# READ-ONLY:
#   - no directories
#   - no file downloads
#   - no installs
#   - no graph import
#   - no routing
#   - no project writes
# ======================================================================================

$FrozenPbf = Join-Path $Root "Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf"
$FrozenSha = "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813"

$Italy260802Pbf = "https://download.geofabrik.de/europe/italy-260802.osm.pbf"
$Italy260802Md5 = "https://download.geofabrik.de/europe/italy-260802.osm.pbf.md5"

$NordEst260802Pbf = "https://download.geofabrik.de/europe/italy/nord-est-260802.osm.pbf"
$NordEst260802Md5 = "https://download.geofabrik.de/europe/italy/nord-est-260802.osm.pbf.md5"

$NordEst260801Md5 = "https://download.geofabrik.de/europe/italy/nord-est-260801.osm.pbf.md5"

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $status = if ($Ok) { "PASS" } else { "FAIL" }
    "{0,-48} {1,-5} {2}" -f $Name, $status, $Detail
}

function Try-Head([string]$Url) {
    try {
        $r = Invoke-WebRequest -Method Head -Uri $Url -UseBasicParsing -TimeoutSec 45
        $rawLen = $r.Headers["Content-Length"]
        if ($rawLen -is [System.Array]) { $rawLen = $rawLen | Select-Object -First 1 }
        $len = $null
        if ($null -ne $rawLen -and ([string]$rawLen).Trim() -ne "") {
            $len = [int64]::Parse(([string]$rawLen).Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
        }
        return [ordered]@{
            ok = $true
            status = [int]$r.StatusCode
            length = $len
            last_modified = [string]$r.Headers["Last-Modified"]
            error = ""
        }
    }
    catch {
        $status = $null
        try {
            if ($null -ne $_.Exception.Response) {
                $status = [int]$_.Exception.Response.StatusCode
            }
        } catch {}
        return [ordered]@{
            ok = $false
            status = $status
            length = $null
            last_modified = ""
            error = $_.Exception.Message
        }
    }
}

function Try-GetSmallText([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 45
        $content = $r.Content
        if ($content -is [byte[]]) {
            $txt = [System.Text.Encoding]::UTF8.GetString($content)
        }
        elseif ($content -is [System.Array]) {
            try {
                $txt = [System.Text.Encoding]::UTF8.GetString([byte[]]$content)
            }
            catch {
                $txt = (($content | ForEach-Object { [string]$_ }) -join "")
            }
        }
        else {
            $txt = [string]$content
        }
        return [ordered]@{
            ok = $true
            status = [int]$r.StatusCode
            text = $txt.Trim()
            error = ""
        }
    }
    catch {
        $status = $null
        try {
            if ($null -ne $_.Exception.Response) {
                $status = [int]$_.Exception.Response.StatusCode
            }
        } catch {}
        return [ordered]@{
            ok = $false
            status = $status
            text = ""
            error = $_.Exception.Message
        }
    }
}

Write-Host ("=" * 124)
Write-Host "B1-EXT-GH - SOURCE IDENTITY DIAGNOSTIC"
Write-Host ("=" * 124)
Write-Host "READ-ONLY / NO DOWNLOAD OF LARGE PBF FILES"
Write-Host ""

if (-not (Test-Path $FrozenPbf -PathType Leaf)) {
    throw "Frozen PBF missing: $FrozenPbf"
}
if (-not (Test-Path $PythonExe -PathType Leaf)) {
    throw "Project Python missing: $PythonExe"
}

$fi = Get-Item -LiteralPath $FrozenPbf
$actualSha = (Get-FileHash -Algorithm SHA256 -Path $FrozenPbf).Hash.ToLowerInvariant()
$actualMd5 = (Get-FileHash -Algorithm MD5 -Path $FrozenPbf).Hash.ToLowerInvariant()

Write-Check "Frozen SHA256" ($actualSha -eq $FrozenSha) $actualSha
Write-Host ("Frozen MD5              = " + $actualMd5)
Write-Host ("Frozen size bytes       = " + $fi.Length)
Write-Host ("Frozen CreationTime     = " + $fi.CreationTime.ToString("o"))
Write-Host ("Frozen LastWriteTime    = " + $fi.LastWriteTime.ToString("o"))
Write-Host ""

Write-Host "A. INTERNAL PBF HEADER VIA PYOSMIUM"
$py = @'
import json, os, sys
import osmium

p = sys.argv[1]

reader = osmium.io.Reader(p)
try:
    h = reader.header()
    keys = [
        "generator",
        "osmosis_replication_base_url",
        "osmosis_replication_sequence_number",
        "osmosis_replication_timestamp",
        "timestamp",
        "pbf_dense_nodes",
        "sorting",
    ]
    d = {k: h.get(k, "") for k in keys}
    try:
        box = h.box()
        d["bbox_valid"] = bool(box.valid())
        if d["bbox_valid"]:
            d["bbox"] = [
                float(box.bottom_left.lon),
                float(box.bottom_left.lat),
                float(box.top_right.lon),
                float(box.top_right.lat),
            ]
    except Exception as e:
        d["bbox_error"] = repr(e)
finally:
    reader.close()

try:
    from osmium.replication import get_replication_header
    rh = get_replication_header(p)
    d["replication_helper"] = {
        "url": rh.url,
        "sequence": rh.sequence,
        "timestamp": rh.timestamp.isoformat() if rh.timestamp else None,
    }
except Exception as e:
    d["replication_helper_error"] = repr(e)

print(json.dumps(d, indent=2, sort_keys=True))
'@

$py | & $PythonExe - $FrozenPbf
if ($LASTEXITCODE -ne 0) {
    throw "Pyosmium header diagnostic failed"
}

Write-Host ""
Write-Host "B. GEOFABRIK HISTORICAL AVAILABILITY - HEAD ONLY"

$r = Try-Head $Italy260802Pbf
Write-Host ("ITALY_260802_PBF_HEAD = " + ($r | ConvertTo-Json -Compress))
$rItalyPbf = $r

$r = Try-Head $Italy260802Md5
Write-Host ("ITALY_260802_MD5_HEAD = " + ($r | ConvertTo-Json -Compress))
$rItalyMd5 = $r

$r = Try-Head $NordEst260802Pbf
Write-Host ("NORD_EST_260802_PBF_HEAD = " + ($r | ConvertTo-Json -Compress))
$rNordEstPbf = $r

$r = Try-Head $NordEst260802Md5
Write-Host ("NORD_EST_260802_MD5_HEAD = " + ($r | ConvertTo-Json -Compress))
$rNordEstMd5 = $r

Write-Host ""
Write-Host "C. SMALL SIDECARS ONLY"

$t = Try-GetSmallText $Italy260802Md5
Write-Host ("ITALY_260802_MD5_TEXT = " + ($t | ConvertTo-Json -Compress))

$t2 = Try-GetSmallText $NordEst260801Md5
Write-Host ("NORD_EST_260801_MD5_TEXT = " + ($t2 | ConvertTo-Json -Compress))

Write-Host ""
Write-Host "D. INTERPRETATION GUARDRAIL"
Write-Host "Local frozen MD5 != nord-est-260801 has already been established."
Write-Host "This diagnostic does NOT infer source identity from the filename alone."
Write-Host "The decisive evidence now is the PBF internal replication timestamp plus"
Write-Host "availability/metadata of Geofabrik's Italy 260802 national snapshot."
Write-Host ""
Write-Host "GRAPH_IMPORT = NOT_STARTED"
Write-Host "ROUTING = NOT_STARTED"
Write-Host "PROJECT_FILES_WRITTEN = NO"
Write-Host "=== RUN COMPLETATA ==="
