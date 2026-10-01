# CHAT 10.15 — LIGHT MODEL V1 — B6-B SOLVER-READY DOMAIN & BACKEND BENCHMARK

**Ruolo:** chat operativa atomica / preprocessing + optimization benchmark.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Data apertura:** 2026-10-01.

## Obiettivo unico

Chiudere **B6-B** dopo D87: costruire e verificare il dominio reale solver-ready del LIGHT MODEL V1, quantificare la dimensione effettiva del problema e solo dopo eseguire benchmark rappresentativi dei backend candidati.

La chat NON deve scegliere autonomamente il solver canonico e NON deve lanciare il run canonico Phase I.

## Autorità

Andrea
→ Project GPT Instructions
→ Governance Live
→ `Tesi_FRLM_FVG.ipynb`
→ Artifact Register / manifest / hash
→ Git/GitHub
→ cloud storage
→ chat.

## Baseline approvata

- D57-D86 restano invariati.
- **D87 APPROVED — B6-A**:
  - master MILP discreto su `edge_id / n_e`;
  - `sum_e n_e = 611`;
  - B3 e contratto AFIR finito upfront dopo preprocessing deterministico;
  - gap LIGHT 100 km tramite **outer row generation**;
  - D85 Selective Exact Expansion preservata;
  - D50 / coerenza dei witness tramite **logic-based geometry oracle** con soli conflict/no-good cuts logicamente dimostrati.
- **Solver NON scelto.**
- HiGHS/highspy = candidato tecnico da benchmarkare, non backend canonico.
- `PHASE_I_RUN_READY = NO` finché B6-B non chiude i blocker.

## Retrieval obbligatorio — Register first

Per ogni artifact:
1. `06_GOVERNANCE/ARTIFACT_REGISTER.csv`;
2. CURRENT/FROZEN applicabile;
3. storage_root + logical_relative_path;
4. manifest;
5. canonical storage-root resolver;
6. verifica fisica/hash se necessaria;
7. ricerca per filename/storage solo fallback.

Non ricostruire ciò che è già governato.

## Input minimi da risolvere dal Register

Verificare e usare, se applicabili:
- `F56_G_OSM_OPERATIVO_V01`;
- `F56_GAMMA_OSM_PACKAGE_V01`;
- `F57_OD_PATH_SYSTEM_OSM_V01`;
- `LIGHT_PATH_EDGE_LONGITUDINAL_V01`;
- `LIGHT_PUN_ELIGIBLE_EVSE_V02`;
- `QGIS_BASE_TERRITORIALE_FVG_V01`;
- fonti/pointer TEN-T/AFIR già governati.

Per package consultare prima il manifest.

## Fase A — Candidate universe reale

Costruire in modo deterministico l'universo degli `edge_id` su cui il MODEL V1 può effettivamente assegnare nuove stations.

Non assumere che:
- i 284.913 edge presenti sui path positive-flow siano l'intero dominio;
- tutti gli edge FVG siano candidati;
- un edge candidato per B3 sia automaticamente candidato AFIR;
- un edge esterno al path system sia irrilevante a priori, perché B3/AFIR possono richiedere dominio aggiuntivo.

Applicare almeno:
- FVG-only D76;
- divieto mainline TEN-T per nuove stations D78-D80;
- direzionalità e accessibilità pertinenti;
- geometria/sub-geometria ammissibile D85;
- D50/D83 solo come bound/eligibility dove deterministico, senza anticipare l'oracle.

Produrre cardinalità:
- physical segments considerati;
- directed edge_id candidati;
- edge candidati per normal LIGHT;
- edge candidati per B3;
- edge candidati per AFIR;
- intersezioni fra i tre insiemi;
- edge esclusi per causa.

## Fase B — Mapping solver-ready

Materializzare/verificare gli input necessari al master e agli oracle.

### PUN
Per le 61 posizioni validate:
- mapping a path/progressiva canonica dove applicabile;
- comuni B3 coperti;
- relazione AFIR solo se realmente verificata;
- nessuna aggregazione artificiale.

### B3
Per tutti i 215 comuni:
- relazione sparse comune → candidate edge/subdomain;
- classificazione robust / incompatible / location-sensitive rispetto ai 10 km;
- evidenziare comuni con zero candidati.

### AFIR
Costruire/verificare:
- candidate station domain off-mainline;
- uscita TEN-T pertinente;
- direzione;
- access leg <=3 km;
- Core / Comprehensive;
- relazioni necessarie per 60 km;
- pool-power coefficients 2/4 units;
- D84 common-pool marking senza micro-siting.

### LIGHT 100 km
Non materializzare tutte le rows.
Preparare l'indice solver/separator per i path rilevanti, partendo dal dato audit H-090:
- 49.307 path positive-flow >100 km da verificare;
- boundary gaps D69;
- fixed PUN + future witness positions;
- generazione deterministica delle violated empty-window rows.

## Fase C — B5 geometry-oracle contract implementabile

Senza cambiare D85:
- definire strutture dati per ROBUST / INCOMPATIBLE / LOCATION_SENSITIVE;
- definire physical witness identity condivisa;
- definire rara gestione multi-witness;
- D50 Euclidea;
- conflict-set certificate richiesto prima di emettere no-good cut;
- distinguere `GEOMETRY_INFEASIBLE` da `NUMERICAL_UNRESOLVED`.

Non scegliere parcheggi o coordinate esecutive.

## Fase D — Cardinalità effettive

Prima di qualsiasi confronto solver, riportare:
- numero variabili integer `n_e`;
- upper bounds rilevanti;
- numero binaries/auxiliaries upfront;
- B3 rows upfront;
- AFIR rows upfront;
- stima non-zero matrix iniziale;
- numero di relazioni location-sensitive;
- memoria stimata per master/index/separator;
- storage necessario.

Se i dati mancanti impediscono una stima seria, STOP sul blocker specifico.

## Fase E — Backend benchmark rappresentativo

Solo dopo A-D.

### Regole
- nessun backend diventa canonico;
- nessuna installazione persistente nel project environment senza Andrea;
- sono ammessi ambienti/scratch isolati e reversibili;
- niente solver commerciale/licenziato senza autorizzazione;
- benchmark su problema reale ridotto o matrice rappresentativa derivata dalle cardinalità effettive;
- stesso formulation/data slice per backend confrontati quando tecnicamente possibile.

### Candidati
Valutare almeno:
- **HiGHS/highspy**;
- un secondo backend open-source concretamente disponibile/isolabile se il confronto è tecnicamente sensato.

Se un secondo backend non è installabile/reversibile in modo prudente, documentare il blocker anziché forzarlo.

### Metriche
- build time;
- peak RAM se misurabile;
- presolve;
- first feasible incumbent;
- bound/gap;
- rows/cuts aggiunti;
- tempo per iterazione outer row generation;
- stabilità API/restart;
- supporto pratico al loop esterno e ai no-good cuts.

Non usare un micro-benchmark puramente sintetico come prova della solvibilità del modello reale.

## Output persistenti

Sono ammessi nuovi artifact solo se utili e auditabili per B6-B.

Prima di crearli:
- verificare che non esistano già nel Register;
- usare naming/versioning naturale;
- non sovrascrivere FROZEN;
- registrare solo artifact realmente rilevanti.

Se si crea un package di mapping, preferire:
- package logico + manifest;
- non registrare ogni membro se il manifest governa adeguatamente il package.

## Non fare

- non cambiare D57-D87;
- non riaprire B5;
- non riaprire ISS-003;
- non fare rerouting;
- non modificare FROZEN;
- non lanciare Phase I canonica;
- non canonizzare HiGHS o altro solver;
- non aggiungere anti-clustering;
- non creare una nuova metodologia di domanda/flow;
- non usare `git add .`;
- non assumere l'untracked `02_CODE/LIGHT_MODEL_V1/` come canonico senza audit.

## Output richiesto alla Chat 10.0

1. candidate universe verificato con cardinalità e cause di esclusione;
2. mapping solver-ready PUN/B3/AFIR e loro stato;
3. schema separator 100 km pronto;
4. geometry-oracle contract implementabile;
5. dimensione reale/stimata del master;
6. benchmark backend rappresentativi;
7. confronto tecnico dei backend SENZA selezionare il vincitore;
8. blocker residui;
9. `PHASE_I_RUN_READY = YES/NO`;
10. una sola decisione minima da portare ad Andrea sul backend / run;
11. artifact creati + Register/manifest/hash se pertinenti;
12. `NOTEBOOK_CHANGE`, `REGISTER_CHANGE`, `GIT_COMMIT_REQUIRED`;
13. HANDOFF alla Chat 10.0.

## Quality gate

PASS solo se:
- il dominio reale è derivato da fonti governate, non assunto;
- le cardinalità solver sono basate sul dominio reale;
- PUN/B3/AFIR sono solver-ready o hanno blocker espliciti;
- il benchmark viene dopo la definizione del dominio;
- nessun solver viene dichiarato canonico senza Andrea;
- D85/D87 restano intatti;
- nessun Phase I canonico è stato lanciato.
