# LIGHT · Capitolo 4 e pacchetto dati one-shot — handoff 2026-10-22

Questa cartella contiene la **copia di consegna intermedia** della relazione con il Capitolo 4 revisionato da Andrea e il pacchetto dati LIGHT one-shot preparato il 20 ottobre 2026.

## Contenuto e identità

- `FVGE_C4_v01.docx` — 3,666,764 byte; SHA256 `b78ff130ad2d5248e8df6f9872ea883831ea3901397a07aac24d8814dd1a50a4`.
- `LIGHT_ONESHOT_INPUTS_20261020_v01.zip` — 6.207.219.263 byte (ZIP64, 108 membri). SHA256: `459995666b76d3c27e454b967858605c25f7fdd59413f02dac96c8ae6a974f69`.
- `LIGHT_ONESHOT_INPUTS_20261020_v01.zip.sha256` — sidecar originario preservato.
- `FINAL_QA.json` — rapporto QA originario del pacchetto one-shot.
- `HANDOFF_MANIFEST_v01.json` — identificativi e provenienza del bundle.

## Provenienza e limiti

- Word sorgente conservato: https://docs.google.com/document/d/10BbkFSUi-ZJybtSnWNGRkf4iDDRpj_xK/edit
- Word integrato su Drive: https://docs.google.com/document/d/1NqA6EehIagQ6rHxY5cqJP-9Z0wuX4VkM/edit
- Capitolo 4 revisionato: https://docs.google.com/document/d/1j8eiwdd5gQERW_PJeJN2LZ_gOU1JmTvPt7e4_O3Jb_4/edit
- ZIP originale OneDrive: https://onedrive.live.com?cid=9249808A2F6D51A3&id=9249808A2F6D51A3!s01cb4a03050c44b686e92d892af22ad7
- QA proveniente da Chat 12.3: CRC e SHA256 dei 108 membri `PASS`; global scientific readiness `NOT_CERTIFIED`. Controlli cloud metadati / QuickXor non equivalgono a un secondo SHA256 effettuato sui byte della copia.
- I pacchetti aggiuntivi Gamma e OSM del 22 ottobre (`Chat 13.2`) sono derivati separati, NON si afferma che siano inclusi nel ZIP del 20 ottobre; il loro audit di integrità 7/7 è documentato da H-204, ma lo stato scientifico rimane `HISTORICAL_NON_AUTHORITATIVE / TO_VERIFY`.
- Il Capitolo 4 è una versione approvata editorialmente da Andrea per la bozza, senza introdurre nuove decisioni metodologiche. I risultati e gate non ancora completati rimangono tali.

## Conservazione e Git

Copia intermedia separata da FROZEN e dalla sorgente originale; non sovrascrivere quest'ultima. Git può preservare il Word (~3,7 MB), questo README e i relativi SHA; **non committare lo ZIP da 6,21 GB nella cronologia del repository**. Nessun merge implicito della PR Register #1.
