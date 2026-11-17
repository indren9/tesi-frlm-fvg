# TESI — CHAT MADRE SUCCESSION PROTOCOL

**Status:** CURRENT — governance protocol  
**Scope:** succession of the TESI Chat Madre only  
**Authority:** Andrea → Project Instructions → Governance Live → domain authorities  
**Repository role:** governance / infrastructure common  
**Global precedence:** Agent Operating Guide §1-bis governs common trigger, nomination, handoff, protected bootstrap, and STOP; this file retains TESI-specific technical rules.

## 1. Purpose

This protocol governs replacement of the current Chat Madre without transferring scientific authority through conversation history. It preserves continuity while keeping persistent live sources authoritative.

An optional succession prompt or handoff is an orientation and recovery instrument, never an authority source. Its absence is not an automatic succession STOP.

## 2. Who is the current Madre

The only chat that holds the Madre role is the chat explicitly identified by `CURRENT_MADRE` in `TESI — GPT GOVERNANCE LIVE / STATUS` after a completed cutover/bootstrap.

A prompt, chat title, handoff, self-description, or audit mandate does not confer the Madre role by itself. If these disagree with `CURRENT_MADRE`, Governance Live prevails and the discrepancy must be reported.

## 3. Trigger

Andrea authorizes the succession trigger and nominates the successor. Unreliable conversational context may justify proposing replacement but does not itself authorize activation.

After activation, the outgoing Madre must not:
- open new substantial work;
- launch new runs;
- dispatch non-essential new operative chats;
- make new scientific/methodological decisions;
- modify FROZEN implicitly.

It may complete the minimum persistence and verification needed for a safe handover.

## 4. Persistent authority first

Bootstrap relies on persistent live sources, not on a required succession prompt. Any optional handoff or prompt must point to those sources instead of copying large historical dumps.

Minimum verification order:
1. Project Instructions;
2. Governance Live — STATUS, DECISIONS, ISSUES; CHATS/HANDOFFS only as needed;
3. authoritative scientific notebook only when the resume point requires scientific/methodological state;
4. Artifact Register / manifest / canonical storage-root resolver only when artifacts are relevant;
5. GitHub/Git or cloud storage only for facts belonging to those domains.

If sources conflict, authority-by-domain and freshness govern. No implicit reconciliation is allowed.

## 5. What the handover transfers

If useful and feasible, an optional handoff transfers only fragile conversational state that cannot be recovered reliably from persistent sources:
- rationale and trade-offs still needed to continue;
- caveats and blockers;
- work partially completed;
- decisions not yet persisted;
- difference between formal state and operational state;
- local processes still running;
- PID/process handle;
- exact command/configuration/environment;
- log or checkpoint/recovery state;
- results not yet persisted;
- items requiring explicit verification.

Any succession handoff is `HISTORY / DERIVED EVIDENCE`, not `CURRENT`, nomination, or permission. Its absence alone never blocks a source-first bootstrap.

For long local runs, apply `DESKTOP_COMMANDER_PLAYBOOK_v02`: retain the same process handle, recover actual state before retry, and preserve command/config/log/result/artifact evidence.

## 6. Classification in the handover

Every non-trivial transferred item must be distinguishable as one of:
- `APPROVATO / VINCOLANTE`
- `PROPOSTA NON APPROVATA`
- `IPOTESI`
- `RISCHIO`
- `ELEMENTO DA VERIFICARE`

Technical evidence such as `PASS`, build success, QA success, hash match or gate success is evidence of the stated check only. It is not Andrea's approval and must not promote a proposal or methodological choice unless an APPROVED decision exists.

## 7. Freshness / discrepancy labels

When comparing an optional succession prompt or handoff with live sources, use:
- `COHERENT` — prompt and authority agree;
- `STALE` — prompt reflects an older state;
- `PENDING_SYNC` — approved/current state exists but a secondary source still requires synchronization;
- `HISTORICAL_BY_DESIGN` — older information is intentionally preserved as history;
- `UNKNOWN` — current state cannot yet be established.

These are freshness/discrepancy labels, not scientific artifact lifecycle states.

If an optional prompt or handoff diverges from a live authority, the domain authority prevails and the discrepancy is reported. Do not silently reconcile.

## 8. First turn of the successor

The first turn is `BOOTSTRAP + VERIFICA DELLA SUCCESSIONE` and is READ-ONLY.

The successor must:
1. verify Andrea's authorization/nomination and `CURRENT_MADRE` in Governance Live; remain successor-pending-cutover unless the authorized cutover is reflected in LIVE;
2. read the Project Instructions and, when accessible, Agent Operating Guide §1-bis;
3. verify Governance Live;
4. read only relevant decisions/issues;
5. verify notebook/Git/Register only when needed;
6. compare any available optional prompt or handoff with live sources; if absent, reconstruct directly from LIVE;
7. classify discrepancies;
8. identify the exact resume point;
9. report to Andrea.

The successor must not in this first turn:
- modify notebook, Git, Governance Live or Artifact Register;
- launch pipelines or solves;
- start local processes;
- dispatch operative chats;
- resolve `PENDING_SYNC` automatically;
- advance MODEL V1 or another scientific workstream.

Required output:
- role;
- CURRENT;
- sources verified;
- APPROVED/FROZEN items not to reopen;
- gaps/discrepancies with freshness labels;
- exact resume point;
- `BOOTSTRAP = PASS / PASS WITH LIMITATIONS / STOP`.

Then STOP for Andrea's review, even with `PASS`.

## 9. Bootstrap gate

`PASS` requires that the successor can reconstruct CURRENT from persistent sources without relying on chat history and can identify the exact resume point without reopening approved decisions.

Use `PASS WITH LIMITATIONS` only when continuity is safe but a non-blocking source or sync is unavailable. Missing an optional handoff alone is not a limitation.

Use `STOP` when Andrea's nomination, `CURRENT_MADRE`, indispensable LIVE authority, or the exact resume point cannot be established reliably. If Notion is unavailable, report the gap and proceed only with innocuous READ-ONLY activity supported by other adequate sources; STOP on dependent protected actions.

## 10. Relationship with ordinary handoff and SESSION CLOSE

Ordinary `HANDOFFS` remain the standard mechanism for operational transfers. This protocol does not create a second handoff system.

`SESSION CLOSE` remains change-driven and does not by itself trigger succession.

An optional succession handoff may use a row in the existing `HANDOFFS` register; no succession-only row is mandatory. The successor still performs the protected READ-ONLY bootstrap above. Handoff content never overrides authoritative LIVE sources.

## 11. Scope guardrails

Succession does not authorize:
- scientific or methodological redesign;
- reopening APPROVED decisions;
- overwriting FROZEN artifacts;
- changing the Artifact Register except for independently required artifact governance;
- destructive Git operations;
- continuation of scientific execution during bootstrap.

Andrea remains final decision authority.
