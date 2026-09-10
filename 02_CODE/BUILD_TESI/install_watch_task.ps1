param(
    [string]$Base = "C:\Users\visen\OneDrive\Università\UniUD\Tesi\Prompt\Visualizzazioni jupyter e latex"
)
$ErrorActionPreference = "Stop"
$TaskName = "Tesi Auto Build Watch"
$Watch = Join-Path $Base "Build_Tesi\watch_tesi.py"
$Notebook = Join-Path $Base "Notebook\Tesi_FRLM_FVG.ipynb"
$OutDir = Join-Path $Base "Output_Tesi"
$PythonW = Join-Path $env:USERPROFILE ".venvs\tesi-build\Scripts\pythonw.exe"
foreach ($P in @($Watch,$Notebook,$PythonW)) { if (-not (Test-Path $P)) { throw "File richiesto non trovato: $P" } }
$Args = "`"$Watch`" --notebook `"$Notebook`" --out-dir `"$OutDir`""
$Action = New-ScheduledTaskAction -Execute $PythonW -Argument $Args
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Auto-build della tesi quando cambia il notebook autorevole." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Task installato e avviato: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
