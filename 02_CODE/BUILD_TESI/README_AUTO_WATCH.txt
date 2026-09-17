TESI AUTO WATCH

Purpose:
watch the single authoritative notebook in the canonical repo and trigger build_tesi.py only when its content changes.

Canonical notebook:
  C:\dev\tesi-frlm-fvg\00_NOTEBOOK\Tesi_FRLM_FVG.ipynb

Persistent build output:
  %USERPROFILE%\OneDrive\Universita`\UniUD\Tesi\TESI_THESIS_STORAGE\07_DELIVERIES\THESIS_BUILDS

Runtime:
  %USERPROFILE%\.venvs\tesi-build

Scheduled task:
  Tesi Auto Build Watch

Install / refresh task:
  & C:\dev\tesi-frlm-fvg\02_CODE\BUILD_TESI\install_watch_task.ps1

Status:
  & C:\dev\tesi-frlm-fvg\02_CODE\BUILD_TESI\status_watch_task.ps1

Remove task:
  & C:\dev\tesi-frlm-fvg\02_CODE\BUILD_TESI\uninstall_watch_task.ps1

Log:
  %USERPROFILE%\.tesi-build-watch\watch.log

The task command contains only ASCII paths. watch_tesi.py resolves the persistent OneDrive output path internally.
The watcher compares the notebook SHA-256 with the latest PASS BUILD_REPORT and avoids duplicate builds.