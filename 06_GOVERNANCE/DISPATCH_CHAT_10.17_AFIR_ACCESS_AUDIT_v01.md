# CHAT 10.17 — LIGHT MODEL V1 — AFIR OFFICIAL ACCESS UNIVERSE AUDIT

**Ruolo:** chat operativa atomica / source-first AFIR access audit.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Upstream:** Chat 10.16.
**Data apertura:** 2026-10-05.

## Obiettivo unico

Eseguire l'opzione **A** emersa dall'handoff di Chat 10.16: completare un audit **source-first** dell'intero universo ufficiale degli accessi AFIR rilevanti sugli assi:

- A/SS202
- A23
- A4
- RA13
- RA14
- A28

e verificare ogni accesso ufficiale contro il grafo LIGHT FROZEN.

L'obiettivo è stabilire l'universo completo degli `access_group` AFIR ammessi dal contratto D89-D90 e consegnare a Chat 10.15 una base completa per chiudere il mapping exit/access/re-entry/boundary di B6-B.

## Baseline APPROVED da preservare

- D78-D80: AFIR off-mainline, direzionale, access leg <=3 km, spacing operativo <=60 km.
- D81-D84: pool power, station standard, max4, specific location execution contract.
- D85: Selective Exact Expansion.
- D87: B6-A approvata; solver non scelto.
- D88: PUN-61 CLOSED / CURRENT / VERIFIED.
- **D89:** identità `access_group` AFIR = **source-first**. La sola topologia/prossimità OSM/FROZEN non crea una uscita reale.
- **D90:** accessi ufficiali ad aree di servizio/parcheggio possono costituire `access_group` se supportati da fonte ufficiale/governata e confermati dal FROZEN con exit/re-entry compatibili per direzione.
- Le 110 transizioni raw mainline→rampa verificate da Chat 10.16 sono **diagnostiche** e non sono assunte come exit set completo.
- `AFIR_MAPPING_READY = NO`.
- `PHASE_I_RUN_READY = NO`.

## Autorità e retrieval

Ordine:
Andrea → Project GPT Instructions → Governance Live → `Tesi_FRLM_FVG.ipynb` → Artifact Register/manifest/hash → registry autorevole 5 HUB → Git/GitHub → cloud storage → chat.

### Tesi
Usare Register-first.

### 5 HUB / TEN-T
Usare il pointer già governato:
`SRC-0059 → F3_SRC_TENTEC_001`

Seguire il registry autorevole 5 HUB. Non duplicare automaticamente SOURCE_ID, artifact_id o registry nella Tesi.

Prima recuperare:
- manifest;
- crosswalk;
- audit;
- source inventory;
- eventuali layer/package ufficiali già governati.

## Cosa significa "universo ufficiale"

Deve includere, se presenti nelle fonti governate/ufficiali:
- svincoli ordinari;
- accessi ufficiali a aree di servizio;
- accessi ufficiali a parcheggi/aree di sosta;
- eventuali accessi dedicati rilevanti ai sensi D89-D90.

Non includere un accesso solo perché:
- esiste una rampa OSM;
- due rampe sono vicine;
- condividono un nodo;
- una PUN è vicina;
- un nome OSM sembra plausibile.

## Fase A — Inventario ufficiale source-first

Per ciascun asse:
1. identificare tutte le fonti ufficiali/governate disponibili;
2. estrarre l'inventario completo degli accessi nominati/identificati;
3. classificare tipo:
   - EXIT_INTERCHANGE
   - SERVICE_AREA_ACCESS
   - PARKING_REST_ACCESS
   - OTHER_OFFICIAL_ACCESS
4. mantenere direzione/lato quando la fonte lo specifica;
5. registrare provenance precisa.

Output minimo per record:
`axis_id, official_access_id, official_name, access_type, direction_or_side, source_id/source_ref, source_evidence, notes`.

## Fase B — Reconciliation con le 110 raw transitions

Confrontare l'inventario ufficiale con tutte le 110 transizioni raw verificate in Chat 10.16.

Classificare ogni raw transition:
- MATCHED_TO_OFFICIAL_ACCESS
- DUPLICATE_TRANSITION_SAME_ACCESS
- GRAPH_ONLY_NOT_OFFICIAL
- AMBIGUOUS
- OUT_OF_SCOPE con motivazione.

Classificare ogni accesso ufficiale:
- GRAPH_CONFIRMED
- GRAPH_PARTIAL
- GRAPH_NOT_FOUND
- SOURCE_AMBIGUOUS.

Il totale delle 110 transizioni deve essere completamente contabilizzato.

## Fase C — Verifica FROZEN

Per ogni accesso ufficiale:
- verificare mainline anchor;
- exit transition;
- rampa;
- re-entry compatibile nella stessa direzione, quando richiesto;
- connettività direzionale;
- asse corretto;
- assenza di cross-direction transfer implicito;
- eventuali multi-ramp / multi-node representation.

Il FROZEN serve a verificare e mappare un accesso source-first, non a inventarne l'identità.

## Fase D — Service area / parking

Applicare D90 esplicitamente.

Per ogni area ufficiale:
- fonte/identità;
- lato/direzione;
- accesso dalla mainline;
- rientro;
- compatibilità con D78-D80;
- eventuale relazione con PUN solo se realmente verificata, senza inferire automaticamente un pool D84.

## Fase E — Boundary / terminal audit

Auditare:
- ingresso/uscita FVG;
- inizio/fine degli assi nel dominio;
- raccordi con rete esterna;
- eventuali accessi immediatamente fuori dominio.

Regole:
- il confine NON è charging opportunity;
- non creare pseudo-pool;
- non inventare opportunità esterne;
- se il primo/ultimo gap AFIR necessita una condizione esterna non determinata dalle fonti correnti, STOP e portare ad Andrea una sola decisione minima.

## Fase F — Cardinalità finali

Riportare:
- numero accessi ufficiali totali;
- numero per asse;
- numero per tipo;
- numero per direzione;
- numero confermato dal FROZEN;
- numero con exit+re-entry completi;
- numero unresolved;
- numero raw transitions assorbite per access_group;
- accessi ufficiali presenti in fonte ma assenti dalle 110 raw;
- raw transitions senza identità ufficiale.

## Artifact

Solo se l'universo è sufficientemente completo e verificato:
- proporre/materializzare un package logico tipo
  `LIGHT_AFIR_OFFICIAL_ACCESS_UNIVERSE_V01`
  oppure nome equivalente coerente con il Register;
- manifest + QA;
- package status solo se supera gate.

Non promuovere un artifact CURRENT se restano ambiguità metodologiche che richiedono Andrea.

## Non fare

- non ridurre il perimetro B6-B;
- non scegliere solver;
- non benchmarkare backend;
- non lanciare Phase I;
- non modificare FROZEN;
- non rifare routing LIGHT;
- non creare access_group da sola geometria OSM;
- non trattare le 110 raw transitions come universo completo;
- non aggregare aree per sola prossimità;
- non inventare regole boundary;
- non usare `git add .`.

## Output richiesto

1. Verdetto: `OFFICIAL_AFIR_ACCESS_UNIVERSE_READY = YES/NO`.
2. Inventario ufficiale completo per asse/direzione/tipo/fonte.
3. Reconciliation 110 raw transitions.
4. Verifica FROZEN exit/re-entry.
5. Audit service-area/parking D90.
6. Audit boundary/terminal.
7. Cardinalità finali.
8. Eventuale package governato + manifest/hash/Register.
9. Blocker residui.
10. `AFIR_MAPPING_READY` impact.
11. Una sola decisione minima per Andrea solo se necessaria.
12. `NOTEBOOK_CHANGE`, `REGISTER_CHANGE`, `GIT_COMMIT_REQUIRED`.
13. HANDOFF a Chat 10.0 e Chat 10.15.

## Quality gate

PASS solo se:
- l'universo parte da fonti ufficiali/governate;
- tutti i 6 assi sono auditati;
- tutte le 110 raw transitions sono riconciliate;
- D89-D90 sono rispettate;
- direzione/exit/re-entry sono verificati sul FROZEN;
- boundary/terminal non sono trattati con assunzioni implicite;
- nessun solver/benchmark/Phase I viene avviato;
- il risultato consente a Chat 10.15 di completare B6-B oppure identifica esattamente il blocker residuo.
