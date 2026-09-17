# TESI FRLM FVG

Repository canonico e leggero della tesi.

## Fonte autorevole

Il solo notebook metodologico/scientifico autorevole è:
`00_NOTEBOOK/Tesi_FRLM_FVG.ipynb`.

Le copie storiche in OneDrive non sono fonti autorevoli.

## Ruoli dello storage

- `C:\dev\tesi-frlm-fvg` = notebook, codice, governance e file piccoli versionabili.
- `TESI_BASELINE_SAFE` = baseline fisica comune POST-5.8E / PRE-5.9D; non va modificata in-place.
- `TESI_THESIS_STORAGE` = dati e artifact persistenti post-baseline e mirror di preservazione esplicitamente registrati.
- `Tesi_QGIS` = progetto QGIS, stili e export cartografici; non storage canonico dei dataset.
- `90_ARCHIVE` = materiale storico / superseded / non-authoritative.
- cache e temporanei = locali, fuori da Git e OneDrive quando possibile.

I file pesanti (GPKG, PBF, NPY, NPZ e grandi output GIS) restano fuori da Git e sono referenziati tramite governance/Artifact Register.

## Ambienti Python

- `.venv` nella repo = runtime scientifico/operativo del progetto.
- `%USERPROFILE%\.venvs\tesi-build` = ambiente dedicato esclusivamente alla build del notebook.
- non esiste ancora un dependency contract unico di root: verrà congelato quando lo stack scientifico sarà sufficientemente stabile.

## Git

- `thesis` = linea scientifica stabile corrente.
- feature branch = sviluppo scientifico WIP.
- `delivery-october` = linea della delivery separata.
- `main` = baseline comune consolidata.
- `chore/repo-reorg` = riorganizzazione tecnica corrente.
- `C:\dev\tesi-dirty-frlm` = repository storico del demonstrator; non è la repo canonica e non va cancellato finché l'archiviazione finale non è chiusa.

## VS Code

`.vscode/settings.json` contiene solo configurazione relativa al progetto e viene versionato.
Configurazioni personali/macchina-specifiche non devono essere aggiunte alla repo.

## Build tesi

Pipeline: `02_CODE/BUILD_TESI`.
Il watcher osserva il notebook canonico nella repo.
I build PASS append-only sono conservati in `TESI_THESIS_STORAGE/07_DELIVERIES/THESIS_BUILDS`.

## QGIS

Il progetto `.qgz` vive in OneDrive sotto `Tesi_QGIS/01_progetto`.
Dataset persistenti nuovi vanno in `TESI_THESIS_STORAGE`, mentre cache e temporanei QGIS restano locali.
`Tesi_QGIS/02_package` non è più destinazione per nuovi dataset canonici.

## Bibliografia e dati legacy

`Ricerca bibliografica` contiene ora solo letteratura e riferimenti. La vecchia raccolta `Dataset - Dati grezzi` è stata spostata senza modificarne il contenuto in `TESI_THESIS_STORAGE/01_RAW/LEGACY_DATASET_COLLECTION`.
