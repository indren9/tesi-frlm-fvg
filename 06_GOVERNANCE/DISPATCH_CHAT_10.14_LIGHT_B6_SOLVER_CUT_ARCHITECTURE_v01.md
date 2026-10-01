# CHAT 10.14 — LIGHT MODEL V1 — B6 SOLVER / CUT ARCHITECTURE

**Ruolo:** chat operativa atomica / optimization architecture.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Data apertura:** 2026-10-01.

## Obiettivo unico

Chiudere il **B6 computational architecture contract** del LIGHT MODEL V1: determinare come implementare e risolvere in modo praticabile la Phase I feasibility con esattamente 611 nuove stations, preservando integralmente D57-D86 e senza cambiare la metodologia scientifica.

La chat deve arrivare a una proposta implementativa concreta e verificabile, con eventuali benchmark scratch, ma **non deve lanciare il run canonico Phase I** e non può approvare autonomamente una nuova architettura: la decisione finale torna ad Andrea.

## Autorità

Andrea
→ Project GPT Instructions
→ Governance Live
→ `Tesi_FRLM_FVG.ipynb`
→ Artifact Register / manifest / hash
→ Git/GitHub
→ cloud storage
→ chat.

## Baseline corrente da preservare

- `N_new = 611`;
- D43: solo path canonici con `path_flow_veh_day > 0`;
- D50: distanza minima fra physical points distinti = 1.000 m Euclidea;
- D51+D82: station standard 150 kW total shared + 2 AFIR recharging points individualmente >=150 kW;
- D59: decision unit = singolo `edge_id` direzionale; variabile canonica `n_e`;
- D69-D77: boundary gaps, PUN validate, B3 10 km per 215 comuni, FVG-only;
- D78-D84: TEN-T/AFIR + specific-location execution contract;
- D83: max4 nuove stations per physical point;
- **D85: B5 CLOSED / Selective Exact Expansion LIGHT**;
- **D86: ISS-003 over-clustering DEFERRED / NOT CANCELLED**, non blocker per B6 o per il primo run diagnostico Phase I; nessuna regola anti-clustering va aggiunta in B6.

FROZEN e CURRENT da non riaprire:
- `G_OSM_operativo`;
- `Gamma_OSM`;
- `OD_PATH_SYSTEM_OSM`;
- `LIGHT_PATH_EDGE_LONGITUDINAL_V01 = CURRENT / VERIFIED`;
- routing canonico = NO REROUTING.

Scala già verificata:
- 411.084 positive-flow canonical paths;
- 594.804.180 path-edge occurrences;
- ~284.913 `edge_id` direzionali sui path positive-flow.

## Retrieval obbligatorio — Register first

Prima di cercare file:
1. `06_GOVERNANCE/ARTIFACT_REGISTER.csv`;
2. artifact CURRENT/FROZEN applicabili;
3. storage_root + logical_relative_path;
4. manifest;
5. canonical storage-root resolver;
6. verifica fisica/hash se necessaria;
7. filename/storage search solo fallback.

Non ricostruire artifact esistenti.

Per codice locale:
- verificare branch/status prima di qualsiasi attività;
- ispezionare l'eventuale `02_CODE/LIGHT_MODEL_V1/` **in sola lettura all'inizio**;
- se è untracked/non governato non assumerlo canonico;
- non cancellarlo, non sovrascriverlo e non versionarlo automaticamente.

## Fonti obbligatorie

Leggere:
- notebook autorevole, in particolare §20, §22, §23, §24 e le decisioni D57-D86;
- `06_GOVERNANCE/LIGHT_MODEL_V1.md`;
- handoff 10.11 / H-074 e successivi H-075…H-088;
- audit Chat 10.13 / H-087 per B5;
- Artifact Register + manifest di `LIGHT_PATH_EDGE_LONGITUDINAL_V01`.

## Famiglie architetturali da valutare

La specifica corrente conserva come candidate almeno:
- full-cover path/sub-path covering;
- fixed-threshold covering con constraint/row generation;
- Branch-and-Cut con dynamic separation;
- Benders decomposition;
- Logic-Based Benders per separare edge allocation e geometric feasibility.

Non assumere che una di queste sia già approvata.

## Domande obbligatorie B6

1. **Master problem minimo**
   Definire quali variabili/discrete decisions devono essere presenti fin dall'inizio:
   - `n_e`;
   - eventuali activation/count auxiliaries;
   - eventuali pool flags TEN-T/AFIR;
   - cosa NON deve stare nel master per default.

2. **Path-gap constraints**
   Con 411k path e 594.8M occurrence:
   - quali vincoli si materializzano upfront;
   - quali si separano dinamicamente;
   - algoritmo di separation/check per trovare path o subpath violati;
   - come trattare boundary gaps D69 e PUN/new witnesses.

3. **B5 geometric feasibility**
   Tradurre D85 in architettura:
   - robust/incompatible/location-sensitive preprocessing;
   - quando creare witness variables;
   - come gestire i rarissimi multi-witness;
   - come verificare D50 Euclidea;
   - come mantenere lo stesso witness tra B3, path gap, AFIR, FVG boundary.

4. **B3 territorial coverage**
   Decidere se i 215 vincoli comunali sono piccoli abbastanza da materializzare upfront e quali coefficienti/preprocessing servono.

5. **TEN-T/AFIR**
   Stabilire come incorporare:
   - direzionalità;
   - exit relation;
   - access leg <=3 km;
   - 60 km;
   - 300/600 kW pool power;
   - D84 pool marking;
   senza micro-siting esecutivo.

6. **Existing PUN**
   Come rappresentare le 61 posizioni validate come fixed opportunities nei checks di gap/B3/AFIR senza creare variabili decisionali spurie.

7. **Scalabilità**
   Stimare cardinalità del master, constraints iniziali e separation workload.
   Verificare RAM/disk/solver feasibility sul PC disponibile oppure indicare chiaramente se serve una macchina/solver diverso.

8. **Solver**
   Identificare solver/libreria concretamente disponibili o installabili nel progetto e compatibili con la strategia.
   Non installare software commerciale/licenziato o cambiare ambiente persistente senza Andrea.
   Open-source benchmark scratch è ammesso se reversibile e isolato.

9. **Failure diagnostics**
   Phase I deve distinguere almeno:
   - infeasibility reale;
   - preprocessing/data contract failure;
   - geometric witness failure;
   - solver timeout/resource failure.

10. **Reproducibility**
    Definire log, seed/tolerance se pertinenti, checkpoints e QA minimi del primo run.

## Benchmark scratch consentiti

Sono consentiti benchmark **non canonici e reversibili** su subset o synthetic instances per confrontare architetture, purché:
- non modifichino FROZEN/CURRENT;
- non vengano presentati come risultato scientifico;
- non lancino il solve canonico 611 completo;
- non creino artifact persistenti senza motivazione e approvazione.

## Output richiesto

1. **Verdetto architetturale breve**.
2. Tabella:
   `component | upfront/master | preprocessing | dynamic separation | geometric check | expected scale`.
3. Confronto delle famiglie candidate con motivazione tecnica.
4. **Una architettura proposta** per il primo diagnostic Phase I run.
5. Pseudocodice end-to-end del solve loop.
6. Variabili e famiglie di vincoli effettivamente necessarie.
7. Strategia B5 witness coerente con D85.
8. Strategia di diagnostica infeasibility/timeouts.
9. Stima di memoria/tempo e solver requirements.
10. Una sola decisione minima da portare ad Andrea.
11. Blocker residui.
12. `PHASE_I_RUN_READY = YES/NO`.
13. `NOTEBOOK_CHANGE`, `REGISTER_CHANGE`, `GIT_COMMIT_REQUIRED`.
14. HANDOFF alla Chat 10.0.

## Non fare

- non modificare D57-D86;
- non riaprire D85/B5;
- non introdurre anti-clustering: ISS-003 è deferita da D86;
- non fare rerouting;
- non modificare FROZEN;
- non lanciare il run canonico Phase I;
- non scegliere implicitamente un nuovo objective;
- non cambiare 611 o 150 kW;
- non trasformare witness matematici in siti esecutivi;
- non fare `git add .`;
- non installare dipendenze persistenti senza preflight e approvazione.

## Quality gate

PASS solo se:
- architettura proposta preserva D57-D86;
- scala 411k / 594.8M è trattata esplicitamente;
- path constraints e geometry non sono materializzati ingenuamente se non giustificato;
- B5/D85 è implementato senza riaprire la metodologia;
- il primo Phase I run può essere lanciato con un contratto computazionale chiaro oppure sono identificati blocker specifici e verificabili.
