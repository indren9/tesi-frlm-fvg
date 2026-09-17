TESI FRLM FVG — BUILD V5 / OVERLEAF APPEND-ONLY

Authoritative source:
  C:\dev\tesi-frlm-fvg\00_NOTEBOOK\Tesi_FRLM_FVG.ipynb

Dedicated runtime:
  %USERPROFILE%\.venvs\tesi-build

Required locally:
- Python in tesi-build
- nbconvert
- ipykernel / Jupyter kernel tesi-build
- Pandoc

Not required:
- MiKTeX
- XeLaTeX locale
- latexmk
- Strawberry Perl

Canonical PDF compilation:
  Overleaf -> XeLaTeX

Publishing policy:
  Every PASS creates a new timestamped directory under:
  TESI_THESIS_STORAGE\07_DELIVERIES\THESIS_BUILDS

No previous PASS directory is deleted, renamed or overwritten.

Standard command:
  & C:\dev\tesi-frlm-fvg\02_CODE\BUILD_TESI\build_tesi.ps1

The wrapper resolves the canonical notebook and persistent output directory automatically.