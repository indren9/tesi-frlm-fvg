param(
    [string]$Notebook = "Tesi_FRLM_FVG.ipynb",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript = Join-Path $ScriptDir "build_tesi.py"
$VenvPython = Join-Path $env:USERPROFILE ".venvs\tesi-build\Scripts\python.exe"

if (-not (Test-Path $PyScript)) {
    throw "build_tesi.py non trovato accanto a build_tesi.ps1"
}

if (-not (Test-Path $VenvPython)) {
    throw "Python della venv Tesi non trovato: $VenvPython"
}

$argsList = @($PyScript, $Notebook)
if ($OutDir -ne "") {
    $argsList += @("--out-dir", $OutDir)
}

Write-Host "TESI BUILD v5 - OVERLEAF ONLY / APPEND-ONLY PUBLISH"
Write-Host "Runtime bloccato sulla venv:"
Write-Host "  $VenvPython"
Write-Host "Nessuna compilazione LaTeX locale."
Write-Host "Ogni build PASS viene pubblicato in una nuova cartella timestamped."

& $VenvPython @argsList

if ($LASTEXITCODE -ne 0) {
    throw "Build tesi FALLITA. Nessun build PASS precedente viene modificato."
}
