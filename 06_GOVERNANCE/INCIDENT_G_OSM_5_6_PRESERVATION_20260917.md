# INCIDENT_G_OSM_5_6_PRESERVATION_20260917

Data verifica: 2026-09-17
Ambito: preservazione artifact FROZEN Fase 5.6.
Esito metodologico: nessuna riapertura della Fase 5.6.

## Artifact interessato

`G_OSM_operativo_v01.gpkg`

Hash FROZEN atteso dal manifest finale 5.6:
`f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3`

Dimensione attesa e osservata:
`244686848` byte.

## Evidenza del disallineamento

La copia presente in `TESI_BASELINE_SAFE` ha SHA256:
`eb2953dfb05ee71d11688a38d6eeed67412a939f95040dd874fb2b9d192cab37`.

Lo stesso byte-stream `EB2953DF...` è presente nel recovery del PC aziendale; la relativa entry ZIP conserva timestamp `2026-09-08 15:22:18 +02:00`.
La materializzazione aziendale del package `grafo_operativo_osm` verso la baseline transfer è registrata il `2026-09-10T09:47:28Z`.
Il manifest finale 5.6, SHA256 `c4ea80c9c660f6a513b20400d0c3edb2f9e6ec10c3364f0a4b0beed91af55da3`, registra per il GPKG l'hash FROZEN `F1D87245...`.

## Recupero del byte-stream corretto

Una copia con hash esattamente uguale al manifest FROZEN è stata trovata nello snapshot storico Dirty:
`90_ARCHIVE/LEGACY_WORKSPACES/Dirty_FRLM/01_INPUT_SNAPSHOT/network/G_OSM_operativo_v01.gpkg`.

Questa copia è stata preservata, senza modificare SAFE, in:
`TESI_THESIS_STORAGE/04_FROZEN_CHECKPOINTS/RECOVERED_BASELINE/OSM_5_6/grafo_operativo_osm/G_OSM_operativo_v01.gpkg`.

SHA256 verificato:
`f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3`.

Lo snapshot Dirty resta materiale storico/non autorevole: viene usato solo come sorgente di recupero perché contiene esattamente i byte identificati dal manifest FROZEN.

## Interpretazione

L'evidenza è coerente con una modifica della working copy aziendale successiva al freeze e precedente alla materializzazione della baseline del 10 settembre.
Non è dimostrabile quale operazione abbia modificato il GeoPackage.
Non vi è evidenza che `TESI_BASELINE_SAFE` sia stato modificato dopo la sua materializzazione.
## Decisione di governance

1. `TESI_BASELINE_SAFE` non viene corretto o sovrascritto in-place.
2. Il byte-stream FROZEN autorevole per `G_OSM_operativo_v01.gpkg` resta quello identificato dal manifest 5.6: SHA256 `F1D87245...`.
3. Il mirror recuperato in `TESI_THESIS_STORAGE` è la copia di preservazione operativa di quel byte-stream.
4. La copia `EB2953DF...` resta evidenza storica della materializzazione contaminata e non viene promossa a nuovo artifact canonico.
5. Una futura correzione del package 5.6 richiederebbe una nuova versione; nessun artifact FROZEN viene sovrascritto.

## Stato

`PRESERVATION_INCIDENT = DOCUMENTED`
`EXPECTED_FROZEN_BYTES = RECOVERED / VERIFIED`
`TESI_BASELINE_SAFE_OVERWRITE = NO`
`METHODOLOGICAL_GATE_REOPENED = NO`

Riferimento Artifact Register:
`F56_G_OSM_OPERATIVO_V01`.
