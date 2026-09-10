TESI FRLM FVG — BUILD V5 / OVERLEAF APPEND-ONLY

Authoritative source:
  Tesi_FRLM_FVG.ipynb

Kept locally:
- Python
- %USERPROFILE%\.venvs\tesi-build
- nbconvert
- ipykernel / Jupyter kernel tesi-build
- Pandoc

Not required:
- MiKTeX
- XeLaTeX
- latexmk
- Strawberry Perl

Canonical PDF compilation:
  Overleaf -> XeLaTeX

Publishing policy:
  Every PASS creates:
    Output_Tesi\build_YYYYMMDD_HHMMSS\

  No previous successful build directory is deleted, renamed, or overwritten.
  This avoids OneDrive locking/Access Denied failures.

Command:
  $Base = "C:\Users\visen\OneDrive\Università\UniUD\Tesi\Prompt\Visualizzazioni jupyter e latex"

  & "$Base\Build_Tesi\build_tesi.ps1" `
      -Notebook "$Base\Notebook\Tesi_FRLM_FVG.ipynb" `
      -OutDir "$Base\Output_Tesi"
