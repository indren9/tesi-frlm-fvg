# CHAT 10.16 — LIGHT MODEL V1 — B6-B AFIR EXIT / ACCESS / RE-ENTRY MAPPING

**Ruolo:** chat operativa atomica / AFIR solver-ready preprocessing.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Upstream:** Chat 10.15 — B6-B solver-ready domain & backend benchmark.
**Data apertura:** 2026-10-03.

## Obiettivo unico

Chiudere, se deterministico dalle fonti governate, il blocker AFIR residuo di B6-B individuato da H-093/H-094:

- costruire un **exit/access set direzionale solver-ready** per il LIGHT MODEL V1;
- governare il raggruppamento delle transizioni mainline→rampa in uscite/access_group reali;
- associare uscita e rientro compatibili per direzione;
- definire i relativi access leg necessari a D78-D80;
- trattare correttamente le opportunità terminali / ai confini senza inventare pseudo-pool;
- quantificare le righe/relazioni AFIR necessarie al master B6-A.

Se uno di questi punti richiede una nuova scelta metodologica non già determinata da D78-D84, **STOP** e riportare ad Andrea la minima decisione necessaria. Non colmare ambiguità con euristiche non approvate.

## Autorità

Andrea  
→ Project GPT Instructions  
→ Governance Live  
→ `Tesi_FRLM_FVG.ipynb`  
→ Artifact Register / manifest / hash  
→ registry autorevole del progetto 5 HUB per TEN-T/AFIR  
→ Git/GitHub  
→ storage cloud  
→ chat.

## Baseline approvata da preservare

- D57-D77 invariati.
- D78: TEN-T off-mainline e direzionalità; nessun trasferimento automatico verso la direzione opposta.
- D79: il gap TEN-T include il ramo uscita→station.
- D80: AFIR hard sovrapposto; station off-mainline entro 3 km driving dalla pertinente uscita; spacing operativo 60 km con access legs; nuove stations non sulla motorway TEN-T mainline.
- D81: Core per direzione >=600 kW + >=2 points >=150 kW; Comprehensive per direzione >=300 kW + >=1 point >=150 kW.
- D82-D84: station standard / max4 / specific location execution contract.
- D85: B5 Selective Exact Expansion.
- D86: ISS-003 over-clustering DEFERRED / NOT CANCELLED.
- D87: B6-A = master MILP + outer row generation + logic-based geometry oracle; solver non scelto.
- D88: PUN-61 membership/directed-edge-progressiva CLOSED / CURRENT / VERIFIED.
- `PHASE_I_RUN_READY = NO`.

## Stato upstream H-094

Già verificato e da NON rifare:
- registry 5 HUB / pointer TEN-T recuperato;
- manifest e artifact crosswalk/audit verificati;
- 6 assi baseline: `A/SS202, A23, A4, RA13, RA14, A28`;
- 110/110 transizioni raw mainline→rampa risultano ammesse nel grafo B5 FROZEN;
- 99 nodi raw;
- queste 110 coppie **NON sono un exit set definitivo**.

Blocker residui:
1. exit/access grouping;
2. uscita↔rientro direzionale;
3. access legs station↔exit/re-entry;
4. opportunità terminali / esterne / di confine;
5. conseguente cardinalità AFIR solver-ready.

## Retrieval obbligatorio

### Tesi
Seguire sempre:
Artifact Register → CURRENT/FROZEN → storage_root + logical path → manifest → resolver canonico → verifica fisica/hash se necessaria → ricerca storage solo fallback.

Usare almeno, se pertinenti:
- `F56_G_OSM_OPERATIVO_V01`;
- `LIGHT_PUN61_SOLVER_READY_PACKAGE_V01`;
- `LIGHT_PATH_EDGE_LONGITUDINAL_V01`;
- gli artifact solver-ready / scratch di Chat 10.15 solo come working evidence, mai come autorità se non registrati.

### 5 HUB / TEN-T
Seguire il pointer Tesi già governato verso il registry autorevole 5 HUB:
- `SRC-0059 → F3_SRC_TENTEC_001`.

Non duplicare automaticamente fonti, SOURCE_ID, artifact_id o registry del progetto 5 HUB.

Recuperare prima manifest/crosswalk/audit già governati nel progetto sorgente. Non ricostruire da zero ciò che esiste.

## Fase A — Inventory e identità dell’uscita

Partendo dalle 110 transizioni raw:
- identificare gli oggetti topologici coinvolti: mainline directed edge, nodo di divergenza, ramp/link, eventuale rete secondaria;
- verificare quali transizioni appartengono allo stesso svincolo/accesso fisico;
- proporre un `access_group_id` deterministico solo se derivabile da topologia + attributi governati;
- mantenere separata la direzione di marcia;
- evitare grouping per sola prossimità geometrica se non supportato.

Produrre:
- numero raw transitions;
- numero access_group fisici;
- numero access_group direzionali;
- assi e direzioni coperti;
- casi ambigui/non raggruppabili.

## Fase B — Uscita / rientro

Per ciascun access_group direzionale:
- individuare l’uscita dalla mainline;
- individuare il rientro compatibile nella stessa direzione quando esiste;
- verificare connettività sul grafo FROZEN;
- non assumere che ogni exit abbia automaticamente un re-entry simmetrico;
- non usare automaticamente la rampa della direzione opposta.

Produrre almeno:
`axis_id, direction_id, access_group_id, exit_transition_id, reentry_transition_id/status, mainline anchors, QA`.

Se il pairing non è deterministico, classificare il caso e STOP sul minimo blocker invece di inventare.

## Fase C — Access legs D78-D80

Costruire il contratto solver-ready per la verifica station↔access:
- driving path direzionalmente compatibile;
- station entro 3 km dalla pertinent exit;
- distanza operativa per spacing 60 km = access leg + tratto TEN-T + access leg secondo D79-D80;
- nessun rerouting dei path LIGHT canonici;
- eventuale shortest-path locale ausiliario può essere usato solo sul grafo FROZEN e solo per il contratto AFIR approvato.

Definire chiaramente quali relazioni possono essere precomputate e quali restano witness-sensitive sotto D85.

## Fase D — Confini / terminali

Auditare separatamente:
- ingresso/uscita del dominio FVG;
- inizio/fine di un asse TEN-T nel dominio modellato;
- connessioni transfrontaliere / esterne;
- PUN validate eventualmente pertinenti.

Regole rigide:
- **non usare il confine come pseudo-stazione o pseudo-pool**;
- origine/destinazione LIGHT non sono automaticamente opportunità AFIR;
- non inventare opportunità esterne non governate;
- se per verificare il primo/ultimo gap AFIR serve una condizione esterna non determinata dalle decisioni correnti, riportare ad Andrea una decisione minima.

## Fase E — Mapping solver-ready e cardinalità

Se A-D sono deterministici, materializzare il mapping necessario a Chat 10.15:
- access_group direzionali;
- exit/re-entry;
- axis Core/Comprehensive;
- candidate off-mainline edge/subdomain compatibili;
- access legs;
- ordering/progressive lungo l’asse necessari al 60 km;
- coefficienti pool 2/4 units;
- PUN AFIR solo dove realmente qualificabili secondo D84, senza aggregazioni artificiali.

Quantificare:
- numero candidate AFIR edge;
- numero access groups;
- numero relazioni candidate edge→access_group;
- numero rows/auxiliaries AFIR upfront stimati;
- numero casi LOCATION_SENSITIVE;
- nnz AFIR stimati;
- casi terminal/boundary unresolved.

## Artifact

Se il mapping è deterministico e supera QA, può essere proposto/materializzato un package logico, ad esempio:

`LIGHT_AFIR_EXIT_ACCESS_SOLVER_READY_PACKAGE_V01`

con manifest e QA.

Prima:
- verificare Register per evitare duplicati;
- non sovrascrivere FROZEN;
- registrare solo se il package è effettivamente solver-ready;
- per package registrare il package logico, non ogni membro se il manifest governa adeguatamente.

Se restano scelte metodologiche aperte, **non promuovere** il package come CURRENT.

## Non fare

- non modificare D57-D88;
- non riaprire PUN-61;
- non riaprire B5/B6-A;
- non scegliere solver;
- non eseguire benchmark backend;
- non lanciare Phase I;
- non fare rerouting LIGHT;
- non modificare FROZEN;
- non trasformare le 110 transizioni raw in exit set per semplice rinomina;
- non inventare grouping basato soltanto su distanza;
- non trattare il confine come charging opportunity;
- non creare regole AFIR nuove senza Andrea;
- non usare `git add .`.

## Output richiesto

1. Verdetto breve: `AFIR_MAPPING_READY = YES/NO`.
2. Inventario raw→access_group con cardinalità.
3. Exit/re-entry pairing per direzione con QA.
4. Access-leg contract e metriche.
5. Trattamento terminal/boundary.
6. Mapping solver-ready e cardinalità AFIR, se deterministico.
7. Eventuale package + manifest/hash/Register status.
8. Blocker residui.
9. Se serve nuova decisione: **una sola decisione minima** da portare ad Andrea.
10. Impatto su `PHASE_I_RUN_READY`.
11. `NOTEBOOK_CHANGE`, `REGISTER_CHANGE`, `GIT_COMMIT_REQUIRED`.
12. HANDOFF a Chat 10.0 e Chat 10.15.

## Quality gate

PASS soltanto se:
- ogni access_group è tracciabile alle fonti/governed graph;
- direzione e exit/re-entry non sono inferiti arbitrariamente;
- access legs rispettano D78-D80;
- i confini non diventano pseudo-pool;
- qualsiasi PUN AFIR rispetta D84;
- 110 raw transitions sono completamente riconciliate oppure gli scarti sono spiegati;
- nessuna nuova metodologia è stata approvata implicitamente;
- il risultato consente a Chat 10.15 di completare A-D e procedere ai benchmark, oppure identifica precisamente la singola decisione che lo impedisce.
