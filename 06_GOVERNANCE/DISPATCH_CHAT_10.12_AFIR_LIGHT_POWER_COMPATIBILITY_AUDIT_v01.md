# CHAT 10.12 — AFIR LIGHT — POWER / RECHARGING POINT COMPATIBILITY AUDIT

**Ruolo:** chat operativa atomica di verifica normativa/tecnica.
**Parent:** Chat 10.0 — Chat Madre Tesi.
**Data apertura:** 2026-09-30.

## Obiettivo unico

Verificare con fonti ufficiali primarie che cosa richiede realmente AFIR per i pool di ricarica LIGHT lungo TEN-T al 2030 e stabilire se, e in quali condizioni, tali requisiti siano compatibili con la taglia standard LIGHT D51:

- 1 nuova infrastruttura = **150 kW complessivi**;
- **2 punti presa**;
- D51 NON assume 75+75 kW;
- D51 NON definisce ancora la potenza individuale dei due punti.

La chat deve produrre una diagnosi normativa/tecnica, NON una nuova decisione metodologica.

## Fonti autorevoli

Ordine interno progetto:
Andrea → Project GPT Instructions → Governance Live → Tesi_FRLM_FVG.ipynb → Artifact Register → Git → chat.

Fonti AFIR da verificare direttamente e citare:
1. **SRC-0008** — Regolamento (UE) 2023/1804, testo consolidato corrente EUR-Lex.
2. **SRC-0010** — Commissione europea / DG MOVE, AFIR Questions & Answers.
3. **SRC-0009** — Regolamento delegato (UE) 2025/656, solo se pertinente alle specifiche tecniche.

Usare prima EUR-Lex e Commissione europea. Fonti secondarie solo come supporto e chiaramente separate.

Non assumere corrette le sintesi delle chat precedenti: verificare il testo normativo originale e la versione vigente.

## Baseline progetto da auditare, NON da modificare

- D51 APPROVED: 150 kW complessivi + 2 punti presa; nessuna ripartizione 75+75 implicita.
- D52-D53: 611 nuove infrastrutture derivano dalla taglia standard 150 kW e dal power balance.
- D78-D80: contratto geografico/direzionale TEN-T e AFIR già approvato nel progetto.
- D81 APPROVED sulla base della lettura preliminare: Core 600 kW + 2 punti >=150 kW; Comprehensive 300 kW + 1 punto >=150 kW, per direzione.
- 06_GOVERNANCE/LIGHT_MODEL_V1.md è la specifica corrente.

D81 NON va usata come prova del significato di AFIR. Se il testo ufficiale la contraddice o richiede qualifiche, segnalarlo alla Madre. Nessuna decisione APPROVED viene corretta autonomamente.

## Domande obbligatorie

1. Definire con il lessico AFIR:
   - recharging point;
   - recharging station;
   - recharging pool;
   - total power output / power output;
   - individual power output;
   - publicly accessible;
   - "along the TEN-T road network".

2. Verificare esattamente i requisiti LIGHT applicabili al **2030** per:
   - TEN-T Core;
   - TEN-T Comprehensive;
   - ciascuna direzione di marcia;
   - eventuali eccezioni che permettano a un pool di servire entrambe le direzioni.

3. Stabilire se il requisito "recharging point >=150 kW" riguarda la capacità individuale del singolo punto e come interagisce con eventuale power sharing / limite complessivo della station.

4. Mappare D51 alle definizioni AFIR SENZA inventare equivalenze:
   - "2 punti presa" del progetto equivalgono davvero a 2 "recharging points" AFIR?
   - 150 kW complessivi con 2 punti è sufficiente a dimostrare che almeno uno o entrambi i punti hanno individual power output >=150 kW?
   - se ciascun punto può erogare 150 kW singolarmente ma la station è limitata a 150 kW complessivi condivisi, come viene valutata ai fini AFIR?
   - ai fini del total power output del pool, quanto contribuisce una unità D51?

5. Classificare la compatibilità D51 come una sola delle seguenti:
   - **COMPATIBLE AS WRITTEN**
   - **CONDITIONALLY COMPATIBLE**
   - **CONFLICT**
   - **NOT DETERMINABLE FROM CURRENT D51**

La classificazione deve essere motivata articolo per articolo / definizione per definizione.

## Test tecnici minimi

Valutare esplicitamente almeno questi casi, senza assumerli come configurazione reale:

A. 150 kW totali, 2 punti da massimo 75 kW ciascuno.
B. 150 kW totali condivisi, 2 punti ciascuno capace di 150 kW quando usato singolarmente.
C. 150 kW totali, un punto capace di 150 kW e un secondo punto inferiore.
D. Più unità D51 co-localizzate in un unico pool, rispettando D38 max 3 nuove infrastrutture per punto fisico.

Per ciascun caso dire:
- contributo alla potenza totale del pool;
- soddisfazione o meno del requisito sui punti individuali;
- eventuale informazione tecnica mancante.

## Controllo di coerenza aggiuntivo

Verificare se D38 (max 3 nuove infrastrutture co-localizzate) crea incompatibilità matematica con i requisiti AFIR di potenza del pool quando si usano esclusivamente nuove unità D51:
- massimo teorico con D51+D38 = 3 × 150 kW = 450 kW;
- verificare le conseguenze per Core e Comprehensive;
- NON concludere che il modello è infeasible se capacità PUN/esistente o altra interpretazione normativa può concorrere: distinguere chiaramente i casi.

Se una correzione fosse necessaria, proporre SOLO alternative, ad esempio:
- chiarire la capacità individuale dei punti senza cambiare 150 kW totali;
- introdurre una variante tecnica AFIR della nuova infrastruttura;
- modificare la taglia standard;
- altra soluzione supportata dalle fonti.

Nessuna alternativa diventa APPROVED senza Andrea.

## Non fare

- non modificare D51-D53, D78-D81;
- non cambiare 611;
- non cambiare 91,65 MW;
- non cambiare D38;
- non avviare il solver;
- non fare rerouting OD;
- non modificare FROZEN;
- non usare blog/commerciali come fonte normativa principale;
- non confondere connector, EVSE, recharging point, station e pool;
- non registrare nuove fonti se non realmente usate.

## Output richiesto

Restituire alla Chat 10.0:
1. **verdetto tecnico-normativo breve** sulla compatibilità D51;
2. tabella requisiti AFIR verificati con articolo/paragrafo e fonte;
3. tabella dei casi A-D;
4. eventuali correzioni necessarie a D81;
5. opzioni minime da portare ad Andrea, SENZA sceglierne una;
6. HANDOFF con NOTEBOOK_CHANGE, REGISTER_CHANGE, GIT_COMMIT_REQUIRED.

Se vengono usate nuove fonti esterne rilevanti non già presenti in SOURCES, segnalarle per registrazione.