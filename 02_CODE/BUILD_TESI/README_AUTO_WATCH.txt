TESI AUTO WATCH ADD-ON v1

Questo add-on NON sostituisce la pipeline v5 gia' validata su Overleaf.
Aggiunge solo l'avvio automatico del build quando cambia il contenuto del master:

  Notebook\Tesi_FRLM_FVG.ipynb

Il watcher confronta SHA-256 del master con NOTEBOOK_SHA256 dell'ultimo BUILD_REPORT PASS.
Se sono diversi, aspetta 15 s, ricontrolla che il file sia stabile e lancia build_tesi.py.
Il build v5 crea automaticamente una nuova cartella append-only:

  Output_Tesi\build_YYYYMMDD_HHMMSS

Se nel frattempo e' terminato un build manuale con lo stesso hash, il watcher NON duplica il build.

TEST MANUALE DEL WATCHER (forza un build):
  $Base = "C:\Users\visen\OneDrive\Università\UniUD\Tesi\Prompt\Visualizzazioni jupyter e latex"
  & "$env:USERPROFILE\.venvs\tesi-build\Scripts\python.exe" `
      "$Base\Build_Tesi\watch_tesi.py" `
      --notebook "$Base\Notebook\Tesi_FRLM_FVG.ipynb" `
      --out-dir "$Base\Output_Tesi" `
      --once --force

INSTALLA TASK A LOGON:
  & "$Base\Build_Tesi\install_watch_task.ps1" -Base $Base

STATO:
  & "$Base\Build_Tesi\status_watch_task.ps1"

RIMOZIONE:
  & "$Base\Build_Tesi\uninstall_watch_task.ps1"

LOG:
  %USERPROFILE%\.tesi-build-watch\watch.log

IMPORTANTE:
Il trigger automatico osserva il percorso canonico. Quando scarichi un nuovo master,
salvalo/sostituiscilo come Notebook\Tesi_FRLM_FVG.ipynb. Le copie versionate possono
restare accanto al master come archivio storico.
