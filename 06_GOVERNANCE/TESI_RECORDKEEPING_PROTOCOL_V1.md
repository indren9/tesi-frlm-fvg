# TESI_RECORDKEEPING_PROTOCOL_V1

**Project:** TESI FRLM FVG  
**Status:** V1 — operational protocol  
**Canonical scientific/methodological source:** `Tesi_FRLM_FVG.ipynb`  
**Principle:** minimum recordkeeping that preserves reproducibility and project memory.

---

## 1. Architecture

The permanent memory of the project is split into three complementary layers:

1. **NOTEBOOK** — methodological/scientific authority.
2. **ARTIFACT REGISTER** — canonical index of relevant artifacts.
3. **GIT HISTORY** — version history of notebook, register, scripts, documentation and other suitable small files.

Large/binary artifacts may remain outside Git. Their identity and location are preserved in the Artifact Register.

Chat is a coordination environment, not sufficient permanent storage.

---

## 2. What belongs in the notebook

Write in `Tesi_FRLM_FVG.ipynb` only information that materially preserves:

- methodological decisions;
- relevant scientific results;
- gate status and freeze decisions;
- open questions;
- roadmap state;
- references to important artifacts.

Do **not** use the notebook as:

- a complete file inventory;
- a console-log dump;
- a repository of transient diagnostics;
- a duplicate of the Artifact Register.

Integration with the existing notebook:

- **§20 — Decisioni metodologiche consolidate:** only consolidated methodological/project decisions.
- **§22 — Questioni ancora aperte:** only unresolved methodological/scientific questions.
- **§23 — Roadmap operativa:** current/next operational phase and material dependencies.
- **§24 — Registro aggiornamenti:** concise record of meaningful notebook/project-state changes.

If the notebook is modified, `build_tesi.py` must return `STATUS = PASS` before closure.

---

## 3. What belongs in the Artifact Register

Register an artifact only if losing its exact identity would make future recovery, verification or reuse materially difficult.

Typical registered artifacts:

- frozen/current datasets;
- matrices and graph packages;
- canonical manifests;
- final validation outputs needed as evidence;
- models or result packages used downstream;
- critical intermediate outputs that would be expensive or risky to reconstruct.

Do **not** register every temporary file, cache, exploratory export, scratch table or disposable log.

The single canonical register is:

`ARTIFACT_REGISTER.csv`

No overlapping secondary artifact register should be created.

---

## 4. Canonical Artifact Register schema

Fields:

- `artifact_id` — stable unique identifier for this artifact version.
- `phase` — thesis/project phase that produced or governs the artifact.
- `name` — short human-readable name.
- `artifact_status` — lifecycle status.
- `storage_root` — storage root, independent from the logical identity.
- `logical_relative_path` — path relative to `storage_root`.
- `version` — artifact version, normally `v01`, `v02`, ...
- `source` — principal upstream source/artifact(s).
- `producer` — script, notebook cell, pipeline step, or other producer.
- `date` — materialization/freeze date in ISO `YYYY-MM-DD`.
- `sha256` — SHA-256 when required/available.
- `size_bytes` — exact byte size when useful and available.
- `preservation_status` — `VERIFIED`, `TO_VERIFY`, or `N/A`.
- `note` — short exceptional note only.

`storage_root + logical_relative_path` is the canonical location reference.

An absolute Windows path may be derivable from `storage_root`, but the artifact must not be identified by an absolute path alone.

---

## 5. Artifact status semantics

Allowed V1 statuses:

### CURRENT
Authoritative artifact currently in active use but not frozen. It may be replaced by a later version.

### FROZEN
Approved immutable artifact. It must never be overwritten or regenerated in-place.

A FROZEN artifact is authoritative for the scope in which it was frozen until explicitly superseded.

### SUPERSEDED
Previously authoritative artifact replaced by a newer artifact/version. It remains preserved for provenance.

### HISTORICAL_NON_AUTHORITATIVE
Artifact retained only as historical evidence, rejected attempt, benchmark, or non-authoritative materialization.

Artifact status is distinct from gate status. A gate can be PASS/CLOSED while its artifacts have their own lifecycle states.

---

## 6. Naming and versioning

For new artifacts, prefer:

`<descriptive_name>_vNN.<ext>`

Examples:

`gravity_seed_fvg_v01.csv`  
`external_gateway_paths_v02.npz`

Rules:

- use zero-padded versions: `v01`, `v02`, ...;
- do not encode `CURRENT`, `FINAL` or `FROZEN` in new filenames by default;
- lifecycle state belongs in the Register;
- do not rename legacy FROZEN artifacts merely to enforce the new convention;
- correction of a FROZEN artifact requires a **new version**, never in-place overwrite;
- when `v02` replaces `v01`, update `v01 → SUPERSEDED` and register `v02` separately.

`artifact_id` should be unique per artifact version, e.g. `F57_OD_PATH_SYSTEM_OSM_V01`.

---

## 7. SHA-256 and preservation

SHA-256 is **required** for:

- FROZEN critical files;
- canonical manifests;
- other artifacts whose exact byte identity matters.

SHA-256 is optional for:

- ordinary CURRENT files that are cheap to regenerate;
- non-critical small documentation already fully versioned by Git.

For a directory/package without one canonical byte stream:

- do not invent a directory SHA;
- register the package as a logical artifact;
- use a canonical manifest containing member hashes when available;
- register the manifest hash.

A hash is an identity check, **not a backup**.

Before treating a FROZEN/critical artifact as fully closed, verify:

1. the artifact actually exists at the registered location;
2. its expected bytes/hash are recoverable where applicable;
3. preservation/back-up availability has been checked.

Until this has been directly verified, use:

`preservation_status = TO_VERIFY`

Do not infer `VERIFIED` from a hash alone.

---

## 8. Temporary outputs and logs

### TEMPORARY
A file is temporary when:

- it is reproducible at low cost;
- it has no independent historical or downstream value;
- its exact byte identity is not important.

Temporary files are not individually registered.

### LOG / EVIDENCE
Preserve a log/report only when it provides evidence not already adequately stored elsewhere, for example:

- command/parameters;
- environment;
- cardinality checks;
- validation results;
- freeze verification;
- hash verification.

Do not create permanent logs for routine runs merely because they exist.

---

## 9. SESSION CLOSE PROCEDURE V1

Explicit trigger:

`SESSION CLOSE`

The procedure is **change-driven**.

### Step 1 — Determine what actually changed
Reconstruct the completed task and identify:

- decisions/results;
- artifacts created or changed;
- methodological memory;
- downstream impact.

### Step 2 — Decide whether permanent changes are required
Set explicitly:

`NOTEBOOK_CHANGE = YES / NO`  
`REGISTER_CHANGE = YES / NO`  
`GIT_COMMIT_REQUIRED = YES / NO`

All three may legitimately be `NO`.

### Step 3 — Artifact check
For every relevant artifact:

- determine status;
- ensure no FROZEN artifact was overwritten;
- register new/superseded artifacts only when needed;
- calculate SHA-256 where required;
- verify preservation for FROZEN/critical artifacts when operational access permits.

### Step 4 — Notebook check
Update the notebook only if new permanent methodological/scientific memory exists.

Use §20/§22/§23/§24 according to their existing roles.

If modified:

`build_tesi.py → STATUS = PASS`

is mandatory.

### Step 5 — Git check
Git actions occur only if there are relevant versionable changes.

The future `delivery-october` / `thesis` strategy is not assumed until separately defined.

If the Git target is required but cannot be determined safely, ask Andrea.

Use explicit staging only:

`git add <file1> <file2>`

Never default to:

`git add .`

If direct repository access is unavailable, provide the exact Bash commands Andrea must run.

### Step 6 — Final closure output
Return a compact closure containing:

- task/result;
- `NOTEBOOK_CHANGE`;
- `REGISTER_CHANGE`;
- `GIT_COMMIT_REQUIRED`;
- artifacts affected and status;
- build status if applicable;
- preservation verification status if applicable;
- explicit files to version if any;
- next operational step.

Do not create a separate permanent SESSION_CLOSE report by default.

---

## 10. Git rules before the historical baseline is defined

Allowed now:

- design the set of files that should eventually be versioned;
- create/update the canonical Register;
- prepare explicit staging/commit commands when relevant.

Not allowed to assume or implement without the separate Git-baseline task:

- existence of `delivery-october` or `thesis` branches;
- historical fork point;
- branch creation;
- merge/cherry-pick policy;
- baseline reconstruction strategy.

Heavy binary artifacts are not automatically added to normal Git history.

---

## 11. Pilot test — Fase 5.7 OD PATH SYSTEM

The pilot uses the already frozen Phase 5.7 without modifying its artifacts.

The notebook identifies:

- `FASE 5.7 = CLOSED / FROZEN`;
- `OD_PATH_SYSTEM_OSM = FROZEN`;
- canonical impedance `TIME_B5`;
- `PRODUCT_LAMBDA_PATH_WEIGHTS = FROZEN`;
- 46,010 ordered municipal OD;
- 414,090 access-pair paths;
- final package at `C:\Tesi\Tesi_QGIS\02_package\od_paths_osm_light\`;
- canonical manifest `OSM_OD_PATHS_manifest_v01.json`;
- manifest SHA-256 `9c3279c604685dbb8ebf52d18910658efc5fb7fe0ab1069d36d313476abb8fff`.

The V1 Register records the package as one logical artifact plus its canonical manifest.

This is intentionally **not** a row-per-file inventory.

### Pilot recovery result

Using only notebook + register, V1 can quickly recover:

- **what was done:** persistent internal FVG OSM OD path system;
- **correct artifact:** `F57_OD_PATH_SYSTEM_OSM_V01`;
- **where:** `C:\Tesi\Tesi_QGIS\02_package` + `od_paths_osm_light`;
- **frozen version:** `v01`;
- **integrity reference:** canonical manifest and its SHA-256;
- **associated methodological decision:** Phase 5.7 frozen with `TIME_B5` and PRODUCT-LAMBDA.

One gap is intentionally exposed by the pilot:

- the exact producer **script filename** is not recoverable from the notebook material inspected for Phase 5.7.

Therefore the Register records the producer at pipeline level and marks the exact script identity as unresolved. This is a useful V1 rule: future permanent artifacts should record the real producer script at materialization/Session Close time instead of trying to reconstruct it months later.

Preservation status is `TO_VERIFY` because this chat does not have operational access to the actual frozen package storage.

**Pilot verdict: PASS WITH TWO OPERATIONAL FOLLOW-UPS**
1. verify physical preservation of the frozen Phase 5.7 package;
2. recover the exact producer script only if it can be done cheaply during the future baseline/workspace audit.

Neither follow-up reopens or modifies Phase 5.7.

---

## 12. Implementation plan

### Implemented in V1
- canonical protocol defined;
- canonical CSV Register created;
- schema and lifecycle status fixed;
- Session Close procedure defined;
- Phase 5.7 pilot inserted into the Register.

### Next implementation steps
1. Place `ARTIFACT_REGISTER.csv` in the future Git-controlled thesis project root during the Git-baseline task.
2. Verify `storage_root` conventions against the real workspace.
3. Verify preservation for the pilot FROZEN artifacts.
4. During baseline reconstruction, add only significant CURRENT/FROZEN/SUPERSEDED/HISTORICAL artifacts worth recovering.
5. Do not attempt to inventory every historical temporary file.
6. Start using `SESSION CLOSE` prospectively after the baseline strategy is ratified.

---

## 13. Structural decisions still outside this mandate

Still reserved to Chat Madre / separate Git-baseline task:

- historical Git baseline;
- exact repository root;
- creation/existence of `delivery-october` and `thesis`;
- fork point and branch policy;
- merge/cherry-pick/synchronization policy.

No scientific or methodological gate is reopened by this protocol.
