param(
    [string]$RepoRoot = "C:\dev\tesi-frlm-fvg"
)

$ErrorActionPreference = "Stop"
$TaskName = "Tesi Auto Build Watch"
$Watch = Join-Path $RepoRoot "02_CODE\BUILD_TESI\watch_tesi.py"
$Notebook = Join-Path $RepoRoot "00_NOTEBOOK\Tesi_FRLM_FVG.ipynb"
$PythonW = Join-Path $env:USERPROFILE ".venvs\tesi-build\Scripts\pythonw.exe"

foreach ($P in @($Watch, $Notebook, $PythonW)) {
    if (-not (Test-Path $P)) { throw "File richiesto non trovato: $P" }
}

$Args = "`"$Watch`""
$Action = New-ScheduledTaskAction -Execute $PythonW -Argument $Args
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Auto-build del notebook autorevole nella repo canonica." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Task installato e avviato: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State