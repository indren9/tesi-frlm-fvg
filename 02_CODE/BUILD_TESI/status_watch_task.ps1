$TaskName = "Tesi Auto Build Watch"
$Log = Join-Path $env:USERPROFILE ".tesi-build-watch\watch.log"
Write-Host "`n=== TASK ==="
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object TaskName,State
Write-Host "`n=== TASK INFO ==="
Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Select-Object LastRunTime,LastTaskResult,NextRunTime
Write-Host "`n=== ULTIME 40 RIGHE LOG ==="
if (Test-Path $Log) { Get-Content $Log -Tail 40 } else { Write-Host "Nessun log." }
