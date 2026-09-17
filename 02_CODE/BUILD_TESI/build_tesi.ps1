param(
    [string]$Notebook = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$PyScript = Join-Path $ScriptDir "build_tesi.py"
$VenvPython = Join-Path $env:USERPROFILE ".venvs\tesi-build\Scripts\python.exe"

if ($Notebook -eq "") {
    $Notebook = Join-Path $RepoRoot "00_NOTEBOOK\Tesi_FRLM_FVG.ipynb"
}
if ($OutDir -eq "") {
    $TesiRoot = Join-Path $env:USERPROFILE ("OneDrive\Universit" + [char]0x00E0 + "\UniUD\Tesi")
    $OutDir = Join-Path $TesiRoot "TESI_THESIS_STORAGE\07_DELIVERIES\THESIS_BUILDS"
}

foreach ($P in @($PyScript, $VenvPython, $Notebook)) {
    if (-not (Test-Path $P)) { throw "File richiesto non trovato: $P" }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "TESI BUILD v5 - OVERLEAF ONLY / APPEND-ONLY PUBLISH"
Write-Host "Notebook: $Notebook"
Write-Host "Output:   $OutDir"
Write-Host "Runtime:  $VenvPython"

& $VenvPython $PyScript $Notebook --out-dir $OutDir
if ($LASTEXITCODE -ne 0) {
    throw "Build tesi FALLITA. Nessun build PASS precedente viene modificato."
}