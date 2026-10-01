# CHAT 10.13 — LIGHT B5 — HEAVY FINITE ENCODING REUSE AUDIT

**Ruolo:** chat operativa atomica / audit metodologico-computazionale.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Data apertura:** 2026-10-01.

## Obiettivo unico

Capire se il problema B5 del LIGHT MODEL V1 — rappresentare in modo matematicamente sufficiente la posizione fisica delle nuove stations all'interno dell'edge_id selezionato — può riusare o adattare la soluzione già approvata nel ramo Heavy/AFIR, in particolare D34 **Selective Exact Expansion** e D36 **Minimal Heavy/AFIR MILP concept**.

L'obiettivo è **recuperare, non ricostruire**: identificare ciò che è già consolidato, verificare l'equivalenza o le differenze rispetto al LIGHT, e restituire alla Madre una proposta minima di riuso/adattamento. Nessuna nuova metodologia diventa APPROVED in questa chat.

## Autorità

Andrea
→ Project GPT Instructions
→ Governance Live
→ `Tesi_FRLM_FVG.ipynb`
→ Artifact Register / manifest / hash
→ Git
→ chat.

## Retrieval obbligatorio — register first

Per qualsiasi artifact già esistente:
1. `06_GOVERNANCE/ARTIFACT_REGISTER.csv`;
2. artifact CURRENT/FROZEN applicabile;
3. storage_root + logical_relative_path;
4. manifest se presente;
5. canonical storage-root resolver;
6. verifica fisica/hash se necessaria;
7. ricerca per filename/storage solo come fallback.

Non ricostruire artifact esistenti e non scegliere copie legacy/archivio se esiste CURRENT/FROZEN.

Artifact Heavy già individuato dal Register e da verificare per pertinenza:
- `HEAVY_AFIR_MACRO_UNIT_INVENTORY_V04`
- status CURRENT / VERIFIED
- `TESI_THESIS_STORAGE\07_DELIVERIES\HEAVY_AFIR_2030\CHAT_9_46_HEAVY_AFIR_MACRO_UNIT_INVENTORY_v04.csv`
- SHA-256 `5bdd78a089c353981aed58384f3ca5906fe5834db492b08bcc74f570edd7f935`
- 88 candidate units; 128/128 directional relations PASS.

## Fonti metodologiche Heavy da leggere integralmente

Nel notebook autorevole individuare almeno:
- D29–D33: macro-unit, windows, access groups, robust/incompatible/location-sensitive;
- **D34 — Selective Exact Expansion / finite encoding**;
- D35 — Dmin standard rule;
- **D36 — Minimal Heavy/AFIR MILP concept**.

Punti Heavy già consolidati da NON reinventare:
- `ROBUST_COMPATIBLE` → nessuna espansione interna;
- `INCOMPATIBLE` → esclusione;
- `LOCATION_SENSITIVE` → fragment states direzionati automatici;
- una sola configurazione interna globale `(state, coordinata continua)`;
- la coordinata continua è solo **witness matematico**, non sito esecutivo;
- stessa configurazione interna condivisa upstream/downstream;
- distanze con shortest-path precomputati + coefficienti geometrici;
- nessuna griglia/sampling/punto manuale;
- preprocessing fuori dal MILP;
- full MILP/solver Heavy non è stato canonizzato.

## Baseline LIGHT corrente da preservare

Decisioni correnti: D57-D84, in particolare:
- `N_new = 611`;
- D51 + D82: ogni nuova station = 150 kW total shared + 2 AFIR recharging points individualmente >=150 kW;
- D83: max 4 nuove stations per physical point;
- D50: 1 km Euclidean tra physical points distinti rilevanti;
- D59: decision unit canonica = singolo `edge_id` direzionale;
- D69: boundary gaps inclusi;
- D70-D73: 61 PUN validate per vincoli geografici/path-based;
- D74-D77: copertura territoriale 10 km su rete per tutti i 215 comuni + FVG-only;
- D78-D81: contratto TEN-T/AFIR;
- D84: AFIR specific-location micro-siting è esecutivo; MODEL V1 marca le stations appartenenti allo stesso pool ma non sceglie parcheggio/piazzola/particella.

Artifact longitudinale:
- `LIGHT_PATH_EDGE_LONGITUDINAL_V01` = CURRENT / VERIFIED;
- 411,084 positive-flow paths;
- 594,804,180 path-edge occurrences;
- no rerouting.

## Domande obbligatorie

1. **Che problema risolveva esattamente D34 nel Heavy?**
   Ricostruire problema, input, classificazioni e significato del witness continuo.

2. **Quali componenti di D34 sono riusabili 1:1 nel LIGHT B5?**
   Valutare separatamente:
   - continuous coordinate witness;
   - selective expansion;
   - fragment states;
   - shared witness across multiple constraints;
   - precomputed shortest-path/geometric coefficients;
   - preprocessing outside MILP.

3. **Quali componenti NON sono trasferibili direttamente?**
   Confrontare esplicitamente:
   - Heavy macro-unit `(comune,corridoio[,direzione])` vs LIGHT `edge_id`;
   - Heavy consecutive AFIR chain vs LIGHT 411k canonical positive-flow paths;
   - Heavy 60 km pairwise pool relations vs LIGHT 100 km full-path gaps;
   - LIGHT B3 10 km territorial coverage;
   - LIGHT D50 1 km Euclidean separation;
   - LIGHT D83 max4 co-location;
   - LIGHT D84 execution-level AFIR specific location.

4. **Serve davvero una coordinata continua su ogni edge LIGHT?**
   Verificare se gran parte degli edge può essere trattata senza posizione interna esplicita e solo i casi realmente location-sensitive richiedono espansione, come nel Heavy.

5. **Come definire “location-sensitive” nel LIGHT senza inventare un nuovo criterio arbitrario?**
   Individuare quali hard constraints possono dipendere dalla posizione interna sull'edge e quali no:
   - path gap 100 km;
   - AFIR access/gap;
   - B3 10 km;
   - D50;
   - FVG boundary;
   - co-location max4.

6. **Più stations sullo stesso edge.**
   Stabilire se il riuso Heavy permette di rappresentare:
   - 1 physical witness con 1–4 stations co-localizzate;
   - più physical witnesses distinti sullo stesso edge quando necessario;
   - senza trasformare il modello in micro-siting esecutivo.

7. **Verdetto di riuso.**
   Classificare una sola delle seguenti:
   - `REUSE_AS_IS`
   - `REUSE_WITH_LIGHT_ADAPTATION`
   - `PARTIAL_REUSE_ONLY`
   - `NOT_REUSABLE`

## Analisi minima richiesta

Produrre una tabella:
`Heavy element | Heavy purpose | LIGHT analogue | reusable? | required adaptation | risk`.

Poi proporre **massimo 3 opzioni B5**, ordinate dal minimo cambiamento concettuale al massimo, senza sceglierne una e senza assegnare score/ranking numerici.

Per ogni opzione indicare:
- variabili/witness necessari;
- quali preprocessing;
- quali hard constraints riesce a verificare;
- impatto atteso sulla dimensione del problema;
- se richiede una nuova decisione Andrea.

## Non fare

- non modificare D57-D84;
- non modificare FROZEN;
- non fare rerouting;
- non scegliere solver/cut architecture B6;
- non lanciare il Phase I solve;
- non creare una nuova griglia di candidati per comodità;
- non scegliere punti manuali;
- non promuovere automaticamente la soluzione Heavy a LIGHT;
- non creare artifact persistenti salvo necessità strettamente dimostrata e previa autorizzazione della Madre;
- non aggiornare notebook/Register autonomamente.

Sono ammessi test scratch/read-only per verificare fattibilità concettuale o cardinalità, senza persistenza come artifact canonico.

## Output richiesto alla Chat 10.0

1. verdetto di riuso in 5 righe;
2. tabella Heavy → LIGHT;
3. identificazione precisa del “nocciolo” riusabile di D34/D36;
4. massimo 3 opzioni B5;
5. una sola **decisione minima** da portare ad Andrea come next step;
6. elenco di blocker residui per B5;
7. `NOTEBOOK_CHANGE`, `REGISTER_CHANGE`, `GIT_COMMIT_REQUIRED`;
8. HANDOFF alla Chat 10.0.

## Quality gate

PASS solo se:
- le fonti Heavy sono state recuperate da notebook/Register senza ricostruzioni inutili;
- è dimostrata la differenza tra witness matematico e micro-siting esecutivo;
- non viene confuso `edge_id` LIGHT con la macro-unit Heavy;
- nessuna nuova metodologia viene dichiarata APPROVED;
- il riuso proposto preserva D50, D59, D69-D84 e i FROZEN.
