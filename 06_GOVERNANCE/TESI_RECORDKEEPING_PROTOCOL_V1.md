# TESI_RECORDKEEPING_PROTOCOL_V1

**Project:** TESI FRLM FVG
**Status:** V1 — operational protocol
**Updated:** 2026-09-17
**Canonical scientific/methodological source:** `00_NOTEBOOK/Tesi_FRLM_FVG.ipynb`
**Principle:** minimum recordkeeping that preserves reproducibility, provenance and project memory without duplicating information.

---

## 1. Purpose and permanent memory

This protocol defines how the project identifies, stores, preserves and versions relevant scientific and technical artifacts.

Permanent project memory is split into three complementary layers:

1. **NOTEBOOK** — methodological/scientific authority.
2. **ARTIFACT REGISTER** — canonical lightweight index of relevant artifacts.
3. **GIT HISTORY** — version history of notebook, register, scripts, governance, documentation and other suitable small files.

Chat is a coordination environment, not sufficient permanent storage. Large/binary artifacts may remain outside Git; their identity, lifecycle state and location are preserved through the Artifact Register.

This protocol is not a file inventory, a changelog, or a replacement for the authoritative notebook.

---
## 2. Authoritative notebook

The only authoritative methodological/scientific notebook is:

`00_NOTEBOOK/Tesi_FRLM_FVG.ipynb`

The notebook preserves only information that materially affects project memory:

- methodological decisions;
- relevant scientific results;
- gate status and freeze decisions;
- open questions;
- roadmap state;
- references to important artifacts.

It must not become a complete file inventory, console-log dump, collection of transient diagnostics, or duplicate of the Artifact Register.

Current internal roles:

- **§20** — consolidated decisions;
- **§22** — open methodological/scientific questions;
- **§23** — operational roadmap;
- **§24** — concise update log.

If the notebook is modified, `build_tesi.py` must complete with `STATUS = PASS` before closure.

---
## 3. Storage architecture

### `C:\dev\tesi-frlm-fvg`
Canonical Git repository for notebook, reproducible code, governance, Artifact Register and small versionable documentation/outputs. Heavy binaries are not added automatically to Git.

### `TESI_BASELINE_SAFE`
Physical common baseline **POST-5.8E / PRE-5.9D**. Treat it as an immutable historical baseline. Do not overwrite FROZEN material in place and do not silently rewrite baseline history.

### `TESI_THESIS_STORAGE`
Persistent thesis storage for post-baseline work and explicit preservation mirrors:

- `01_RAW` — persistent inputs;
- `03_CANONICAL_DATA` — canonical/current datasets;
- `04_FROZEN_CHECKPOINTS` — FROZEN artifacts and verified preservation mirrors;
- `07_DELIVERIES` — deliveries and append-only thesis builds.

### `Tesi_QGIS`
Lightweight QGIS workspace for active `.qgz` projects, styles/layouts and cartographic exports/QA. It is not the canonical long-term container for heavy datasets. `Tesi_QGIS/02_package` is legacy/deprecated for new canonical data.

### `90_ARCHIVE`
Historical/non-authoritative storage for legacy workspaces, superseded material, recovery packages, historical Git bundles and obsolete transfer packages when retention is justified.

Archival presence does not make an artifact authoritative.

---
## 4. Artifact Register

The single canonical register is:

`06_GOVERNANCE/ARTIFACT_REGISTER.csv`

Register an artifact only if losing its exact identity would make future recovery, verification or reuse materially difficult.

Typical registered artifacts:

- FROZEN datasets/packages;
- important CURRENT canonical datasets;
- matrices and graph packages;
- canonical manifests;
- validation outputs required as evidence;
- result/model packages used downstream;
- critical intermediate artifacts expensive or risky to reconstruct.

Do not register every temporary file, cache, exploratory export, scratch table or routine log. No overlapping secondary artifact register should be created.

Canonical location is identified by:

`storage_root + logical_relative_path`

An absolute Windows path may be contextual information, but must not be the artifact identity.

---
## 5. Canonical Register schema

Fields:

- `artifact_id` — stable unique identifier for this artifact version;
- `phase` — thesis/project phase;
- `name` — short human-readable name;
- `artifact_status` — lifecycle status;
- `storage_root` — logical storage root;
- `logical_relative_path` — path relative to `storage_root`;
- `version` — artifact version, normally `v01`, `v02`, ...;
- `source` — principal upstream source/artifact(s);
- `producer` — script, notebook cell or pipeline step;
- `date` — materialization/freeze date in ISO `YYYY-MM-DD`;
- `sha256` — SHA-256 when required/available;
- `size_bytes` — exact byte size when useful;
- `preservation_status` — `VERIFIED`, `TO_VERIFY`, or `N/A`;
- `note` — short exceptional note only.

`artifact_id` must be unique per artifact version. Use a stable project-oriented identifier such as `F57_OD_PATH_SYSTEM_OSM_V01`.

---

## 6. Artifact lifecycle states

Allowed states are `CURRENT`, `FROZEN`, `SUPERSEDED`, and `HISTORICAL_NON_AUTHORITATIVE`.
### CURRENT
Authoritative artifact currently in active use but not frozen. It may later be replaced by a new version.

### FROZEN
Approved immutable artifact. It must never be overwritten or regenerated in place. It remains authoritative for the scope in which it was frozen until explicitly superseded.

### SUPERSEDED
Previously authoritative artifact replaced by a newer artifact/version. It remains preserved for provenance.

### HISTORICAL_NON_AUTHORITATIVE
Material retained only as historical evidence, rejected attempt, benchmark, recovery source or non-authoritative materialization.

Artifact lifecycle state is distinct from methodological gate status. A gate can be `PASS/CLOSED` while its artifacts independently have lifecycle states.

---

## 7. Versioning and no-overwrite rule

For new artifacts, prefer `<descriptive_name>_vNN.<ext>` with zero-padded versions `v01`, `v02`, ...

Rules:

- lifecycle state belongs primarily in the Register, not in filenames;
- do not rename legacy FROZEN artifacts only to enforce new naming conventions;
- correction of a FROZEN artifact requires a **new version**;
- when `v02` replaces `v01`, register `v02` separately and mark `v01` as `SUPERSEDED` where appropriate;
- never overwrite a FROZEN artifact in place.
If a FROZEN preservation mismatch is discovered:

1. do not silently repair the historical location;
2. identify the expected byte-stream from authoritative manifest/provenance;
3. preserve a verified copy separately when recoverable;
4. document the incident;
5. update the Register with the authoritative preservation location.

The Phase 5.6 `G_OSM_operativo_v01.gpkg` incident is the reference implementation:

`06_GOVERNANCE/INCIDENT_G_OSM_5_6_PRESERVATION_20260917.md`

---

## 8. SHA-256 and preservation

SHA-256 is required for critical FROZEN files, canonical manifests, and artifacts whose exact byte identity materially matters.

SHA-256 is optional for ordinary CURRENT files cheap to regenerate and non-critical documentation fully versioned by Git.

For a directory/package without one canonical byte-stream:

- do not invent a directory SHA;
- register the package as a logical artifact;
- use a canonical manifest containing member hashes when available;
- register the manifest hash.

A hash identifies bytes; it is **not a backup**.
Before a FROZEN/critical artifact is considered fully preserved, verify when applicable:

1. physical existence at the registered location;
2. expected byte identity/hash;
3. actual recoverability/preservation.

Until verified, use `preservation_status = TO_VERIFY`. Do not infer `VERIFIED` from a recorded hash alone.

---

## 9. Temporary outputs, logs and recovery packages

A file is temporary when it is cheap to reproduce, has no independent downstream value, and its exact bytes are irrelevant. Temporary files are not individually registered.

Preserve a log/report only when it contains evidence not adequately stored elsewhere, such as parameters, environment identity, cardinality checks, validation results, or freeze/hash verification.

A recovered ZIP/workspace is normally:

`HISTORICAL_NON_AUTHORITATIVE`

until selected contents are independently verified and intentionally promoted/materialized.

Recovery packages should remain intact when they provide rollback/provenance value. Selective materialization is preferred to restoring an entire obsolete workspace.

---

## 10. QGIS recordkeeping
QGIS is used for visualization, QA and cartography; Python remains the reproducible computational layer.

Rules:

- active `.qgz` projects may be `CURRENT` artifacts when operationally important;
- persistent heavy data belongs in `TESI_THESIS_STORAGE` or registered FROZEN storage, not in the QGIS workspace by default;
- recovered QGIS projects must have datasource paths remapped to current registered/canonical storage;
- legacy `02_package` paths are not reused for new canonical datasets;
- caches and disposable processing outputs remain outside permanent storage when possible.

A recovery ZIP remains historical even if selected projects/datasets extracted from it become CURRENT.

---

## 11. Git recordkeeping

Current branch roles are governed separately by `06_GOVERNANCE/GIT_BASELINE_ROADMAP_V1.md`.

Operationally:

- `main` — consolidated common baseline;
- `thesis` — stable scientific thesis line;
- feature branches — scientific WIP;
- `delivery-october` — delivery-specific line;
- `chore/repo-reorg` — technical reorganization branch until closure.

Rules:
- use explicit staging only;
- do not use `git add .` by default;
- do not merge, rebase, reset or delete branches without preflight and explicit approval;
- heavy binary artifacts are not automatically committed;
- Git history complements, but does not replace, physical preservation of heavy/FROZEN artifacts.

Historical repositories no longer used operationally may be retired only after their Git history and any unique non-versioned material have been preserved and verified.

---

## 12. SESSION CLOSE procedure

Explicit trigger:

`SESSION CLOSE`

The procedure is change-driven. Verify at least:

1. what actually changed;
2. decisions/results produced;
3. artifacts to preserve;
4. artifact lifecycle state;
5. whether notebook update is required;
6. whether Artifact Register update is required;
7. whether a Git commit is required;
8. next operational step.
Set explicitly:

`NOTEBOOK_CHANGE = YES / NO`
`REGISTER_CHANGE = YES / NO`
`GIT_COMMIT_REQUIRED = YES / NO`

All three may legitimately be `NO`.

For relevant artifacts:

- ensure no FROZEN artifact was overwritten;
- calculate SHA-256 when required;
- verify preservation when applicable;
- register new or superseded artifacts only when needed.

If the notebook changed, `build_tesi.py → STATUS = PASS` is mandatory.

Use explicit Git staging of only relevant files. Do not create a separate permanent SESSION_CLOSE report by default.

Notebook + Artifact Register + Git history normally constitute the permanent closure memory.

---

## 13. Scope and maintenance

This protocol governs recordkeeping and storage discipline only.

It does not reopen scientific/methodological gates and does not replace phase-specific methodology in the authoritative notebook.

Update this protocol only when project-wide recordkeeping/storage rules materially change. Do not update it for ordinary artifact additions, routine runs or phase-local scientific decisions.
