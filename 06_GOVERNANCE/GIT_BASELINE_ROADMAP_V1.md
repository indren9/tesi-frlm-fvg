# GIT_BASELINE_ROADMAP_V1

## FINAL BASELINE DECISION — 10 settembre 2026

Questa sezione SUPERA le conclusioni preliminari di ricostruzione
riportate più sotto nel documento.

COMMON_BASELINE_LOGICAL = POST_5.8E / PRE_5.9D

COMMON_BASELINE_NOTEBOOK =
Tesi_FRLM_FVG v0.29
(canonical repository name: Tesi_FRLM_FVG.ipynb)

COMMON_BASELINE_COMMIT =
d35d9ac13d4fa0543144f80deaf70e0e0f30d690

BASELINE_TAG =
baseline-post-5.8E-pre-5.9D

Il lavoro 5.9D relativo agli external gateways è escluso dalla baseline
comune e appartiene alla successiva linea scientifica della tesi.

I branch:

- thesis
- delivery-october

sono stati materializzati a partire dallo stesso common baseline.

La futura separazione Light Duty / Heavy Duty sarà materializzata solo
al relativo gate naturale e non fa parte della baseline corrente.

---
**Project:** TESI FRLM FVG  
**Timebox massimo:** 2 ore  
**Obiettivo:** arrivare a una baseline Git pronta, con inventario ricostruito e punto di separazione tra linea `delivery-october` e linea `thesis` definito e verificato.

## Baseline finding — 9 settembre 2026

La repository storica `indren9/tesi-dirty-frlm` è stata verificata.

- `DIRTY_START_COMMIT = 39f83846f5b0672665dff55434db196c6897d5d7`
- commit message: `chore: initialize Dirty FRLM demonstrator`
- timestamp: `2026-09-07 14:00:51 +02:00`
- parent commits: **nessuno** (`root commit`)
- il contenuto del root commit è già esplicitamente `DEMONSTRATOR / NON CANONICAL` e separato dalla pipeline canonica della tesi.
- la repository quindi **non contiene un commit pre-dirty** da usare direttamente come common ancestor.

Dal notebook autorevole v0.36, il Registro aggiornamenti mostra come ultimo stato canonico precedente al Dirty:

`5 settembre 2026 — Fase 5.9D-B1 PASS / CLOSED / FROZEN → handoff 5.9D-B2`

Le successive voci sono dell'8 settembre e includono anche working assumptions del demonstrator.

### Baseline logica identificata

`COMMON_BASELINE_LOGICAL = POST_5.9D_B1 / PRE_DIRTY`

cioè lo stato canonico della tesi successivo alla chiusura di 5.9D-B1 e precedente al primo commit Dirty del 7 settembre.


### Exact notebook baseline recovered

The authoritative notebook snapshot immediately preceding the Dirty demonstrator is available:

- source file: `Tesi_FRLM_FVG_v0.34(1).ipynb`
- canonical logical name: `Tesi_FRLM_FVG.ipynb`
- document version: `v0.34`
- last update: `5 settembre 2026`
- state: `5.9D-B1 = PASS / CLOSED / FROZEN`
- next canonical step: `5.9D-B2 — Austria + Slovenia`
- Dirty references in this notebook: `0`
- size: `577725` bytes
- SHA256: `a6a3376cabb2f0bbcabbd6ceccf46da2a496eba89656f89c4d7a9b018ffbedd2`

Therefore:

`COMMON_BASELINE_NOTEBOOK = Tesi_FRLM_FVG v0.34`

This is the byte-level notebook anchor for the historical `POST_5.9D_B1 / PRE_DIRTY` baseline.


### Conseguenza Git

Il root commit del vecchio Dirty **non deve essere usato come common baseline** per il branch `thesis`, perché contiene già struttura e regole specifiche del demonstrator.

Serve quindi materializzare un nuovo commit baseline byte-identical/coerente con lo stato `POST_5.9D_B1 / PRE_DIRTY`.

Solo dopo:

- `thesis` parte dal common baseline;
- `delivery-october` parte dallo stesso common baseline e riceve il lavoro Dirty/October;
- la vecchia repository Dirty resta evidenza storica e sorgente per il recupero del lavoro già svolto.

La scelta esatta tra import dei commit Dirty, cherry-pick o import consolidato sarà presa dopo l'inventario, senza riscrivere distruttivamente la storia esistente.

---

## Sequenza operativa

### STEP 1 — Inventario completo dei file già prodotti
Obiettivo: ottenere una fotografia completa del workspace esistente.

Raccogliere almeno:
- path;
- nome file;
- estensione/tipo;
- dimensione;
- data modifica;
- hash solo quando utile.

Nota:
- questo inventario è una tantum;
- NON coincide con l'Artifact Register;
- può includere anche file temporanei, storici e duplicati.

**Timebox:** 25 min

### STEP 2 — Classificazione rapida
Classificare ogni file o gruppo omogeneo in una delle categorie:

- VERSIONARE_IN_GIT
- ARTIFACT_PESANTE_DA_REGISTRARE
- HISTORICAL_NON_AUTHORITATIVE
- TEMPORARY / IGNORE
- DA_VERIFICARE

Obiettivo: non analizzare perfettamente ogni file, ma separare subito ciò che conta da ciò che non conta.

**Timebox:** 25 min

### STEP 3 — Ricostruzione della baseline comune
Identificare l'ultimo stato del progetto che rappresenta il punto comune prima dell'avvio del filone rapido orientato alla consegna di ottobre.

Verificare:
- notebook autorevole;
- script rilevanti;
- documentazione;
- artifact già congelati;
- eventuali modifiche successive chiaramente riconducibili alla linea October delivery.

**Timebox:** 30 min

### STEP 4 — Definizione del fork
Formalizzare:

- COMMON_BASELINE = <stato/commit/data>
- DELIVERY_OCTOBER_START = <stato/commit/data>
- THESIS_START = COMMON_BASELINE

NON creare ancora branch finché il fork non è verificato.

**Timebox:** 15 min

### STEP 5 — Creazione branch e verifica finale
Solo dopo approvazione del fork:

- creare `delivery-october`;
- creare `thesis`;
- verificare che entrambi partano dal punto corretto;
- controllare Git status;
- nessun file pesante aggiunto per errore;
- Artifact Register e notebook coerenti.

**Timebox:** 15 min

### STEP 6 — Chiusura
Verificare:

- baseline identificata;
- inventario salvato;
- file da versionare definiti;
- artifact pesanti esclusi da Git e registrabili;
- branch creati correttamente;
- working tree coerente;
- next step operativo chiaro.

**Timebox:** 10 min

---

## Regola di tempo

Se un passaggio supera il timebox:
- fermarsi;
- classificare il problema come `DA_VERIFICARE`;
- non bloccare l'intera baseline su dettagli non critici.

Priorità:
1. struttura corretta;
2. preservazione della memoria significativa;
3. fork corretto;
4. perfezione dell'inventario solo dopo.

## Vincoli

- NON usare `git add .`
- NON inserire automaticamente file pesanti/binari in Git
- NON sovrascrivere artifact FROZEN
- NON fare reset/rebase/merge distruttivi
- per modifiche rischiose: PREFLIGHT → BACKUP/ROLLBACK → MODIFICA → VERIFICA

## Esito atteso entro 2 ore

- inventario workspace disponibile;
- classificazione minima completata;
- baseline comune identificata;
- inizio `delivery-october` identificato;
- branch `delivery-october` e `thesis` creati solo se il fork è sufficientemente sicuro;
- Artifact Register pronto a essere popolato dalla baseline significativa.

