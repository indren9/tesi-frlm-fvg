# TESI — CHAT MADRE SUCCESSION PROTOCOL

**Status:** CURRENT — governance protocol  
**Scope:** succession of the TESI Chat Madre only  
**Authority:** Andrea → Project Instructions → Governance Live → domain authorities  
**Repository role:** governance / infrastructure common

## 1. Purpose

This protocol governs replacement of the current Chat Madre without transferring scientific authority through conversation history. It preserves continuity while keeping persistent live sources authoritative.

A succession prompt is an orientation and recovery instrument. It is never itself an authority source.

## 2. Who is the current Madre

The only chat that holds the Madre role is the chat explicitly identified by `CURRENT_MADRE` in `TESI — GPT GOVERNANCE LIVE / STATUS` after a completed cutover/bootstrap.

A prompt, chat title, handoff, self-description, or audit mandate does not confer the Madre role by itself. If these disagree with `CURRENT_MADRE`, Governance Live prevails and the discrepancy must be reported.

## 3. Trigger

Succession is activated before the current Madre's conversational context becomes unreliable, or when Andrea explicitly orders replacement/migration.

After activation, the outgoing Madre must not:
- open new substantial work;
- launch new runs;
- dispatch non-essential new operative chats;
- make new scientific/methodological decisions;
- modify FROZEN implicitly.

It may complete the minimum persistence and verification needed for a safe handover.

## 4. Persistent authority first

The succession prompt must direct the successor to persistent live sources instead of copying large historical dumps.

Minimum verification order:
1. Project Instructions;
2. Governance Live — STATUS, DECISIONS, ISSUES; CHATS/HANDOFFS only as needed;
3. authoritative scientific notebook only when the resume point requires scientific/methodological state;
4. Artifact Register / manifest / canonical storage-root resolver only when artifacts are relevant;
5. GitHub/Git or cloud storage only for facts belonging to those domains.

If sources conflict, authority-by-domain and freshness govern. No implicit reconciliation is allowed.

## 5. What the handover transfers

Transfer only fragile conversational state that cannot be recovered reliably from persistent sources, when relevant:
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

When comparing the succession prompt with live sources, use:
- `COHERENT` — prompt and authority agree;
- `STALE` — prompt reflects an older state;
- `PENDING_SYNC` — approved/current state exists but a secondary source still requires synchronization;
- `HISTORICAL_BY_DESIGN` — older information is intentionally preserved as history;
- `UNKNOWN` — current state cannot yet be established.

These are freshness/discrepancy labels, not scientific artifact lifecycle states.

If the prompt diverges from a live authority, the domain authority prevails and the discrepancy is reported. Do not silently reconcile.

## 8. First turn of the successor

The first turn is `BOOTSTRAP + VERIFICA DELLA SUCCESSIONE` and is READ-ONLY.

The successor must:
1. identify itself as the successor in bootstrap; assume the Madre role only if Governance Live already names it as `CURRENT_MADRE`, otherwise remain successor-pending-cutover;
2. read the Project Instructions;
3. verify Governance Live;
4. read only relevant decisions/issues;
5. verify notebook/Git/Register only when needed;
6. compare the succession prompt with live sources;
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

Then STOP.

## 9. Bootstrap gate

`PASS` requires that the successor can reconstruct CURRENT from persistent sources without relying on chat history and can identify the exact resume point without reopening approved decisions.

Use `PASS WITH LIMITATIONS` only when continuity is safe but a non-blocking source or sync is unavailable.

Use `STOP` when CURRENT, current Madre identity, authoritative source resolution, or the resume point cannot be established reliably.

## 10. Relationship with ordinary handoff and SESSION CLOSE

Ordinary `HANDOFFS` remain the standard mechanism for operational transfers. This protocol does not create a second handoff system.

`SESSION CLOSE` remains change-driven and does not by itself trigger succession.

A Madre succession may use a HANDOFF row, but the successor must still perform the read-only bootstrap above. Handoff content never overrides the authoritative live sources.

## 11. Scope guardrails

Succession does not authorize:
- scientific or methodological redesign;
- reopening APPROVED decisions;
- overwriting FROZEN artifacts;
- changing the Artifact Register except for independently required artifact governance;
- destructive Git operations;
- continuation of scientific execution during bootstrap.

Andrea remains final decision authority.
