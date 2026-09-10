# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import sys
import traceback


# =============================================================================
# CONFIG
# =============================================================================

ROOT = Path(r"C:\Tesi\Tesi_QGIS")

B2 = (
    ROOT
    / "03_output_temporanei"
    / "fase_5_7"
    / "B2_canonical_candidate"
)

PACKAGE_ROOT = ROOT / "02_package"

FINAL = (
    PACKAGE_ROOT
    / "od_paths_osm_light"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

STAGING = (
    PACKAGE_ROOT
    / f"_STAGING_od_paths_osm_light_v01_{STAMP}"
)

B2_MANIFEST = (
    B2
    / "OSM_OD_PATHS_candidate_manifest_v01.json"
)

EXPECTED_B2_MANIFEST_SHA = (
    "f49c0a891a6529f106ea65985e9edabbc0b115de76723f9c0cff2defc48e0269"
)

FINAL_REPORT_NAME = (
    "OSM_OD_PATHS_FINAL_REPORT_v01.txt"
)

FINAL_MANIFEST_NAME = (
    "OSM_OD_PATHS_manifest_v01.json"
)

FINAL_REPORT = (
    STAGING
    / FINAL_REPORT_NAME
)

FINAL_MANIFEST = (
    STAGING
    / FINAL_MANIFEST_NAME
)


EXPECTED_ARTIFACTS = [
    "OSM_OD_access_paths_v01.csv",
    "OSM_OD_municipal_summary_v01.csv",
    "OSM_OD_path_offsets_v01.npy",
    "OSM_OD_transition_slots_v01.npy",
    "OSM_OD_sequence_contract_v01.json",
    "OSM_OD_F1_regression_v01.csv",
]


lines = []


# =============================================================================
# HELPERS
# =============================================================================

def emit(msg=""):

    msg = str(msg)

    print(
        msg,
        flush=True,
    )

    lines.append(
        msg
    )


def hard(condition, message):

    if not condition:
        raise RuntimeError(
            message
        )


def sha256_file(
    path,
    chunk_size=32 * 1024 * 1024,
):

    h = hashlib.sha256()

    with Path(path).open("rb") as f:

        while True:

            block = f.read(
                chunk_size
            )

            if not block:
                break

            h.update(
                block
            )

    return h.hexdigest()


def fmt_size(n):

    n = float(n)

    if n >= 1024**3:
        return f"{n / 1024**3:.3f} GB"

    if n >= 1024**2:
        return f"{n / 1024**2:.3f} MB"

    if n >= 1024:
        return f"{n / 1024:.3f} KB"

    return f"{int(n)} B"


# =============================================================================
# MAIN
# =============================================================================

try:

    emit("=" * 124)

    emit(
        "FASE 5.7 — B3 — FINAL PROMOTION / FREEZE"
    )

    emit("=" * 124)

    emit()

    emit("A. PREFLIGHT")

    emit("-" * 124)

    emit(
        f"Candidate : {B2}"
    )

    emit(
        f"Staging   : {STAGING}"
    )

    emit(
        f"Final     : {FINAL}"
    )

    emit(
        "Overwrite : FORBIDDEN"
    )

    hard(
        B2.is_dir(),
        "B2 candidate directory missing.",
    )

    hard(
        B2_MANIFEST.is_file(),
        "B2 candidate manifest missing.",
    )

    hard(
        not FINAL.exists(),
        (
            "FINAL PACKAGE ALREADY EXISTS. "
            "Overwrite is forbidden."
        ),
    )

    hard(
        not STAGING.exists(),
        "Unexpected staging collision.",
    )


    # =========================================================================
    # B. B2 CANDIDATE IDENTITY
    # =========================================================================

    emit()

    emit(
        "B. B2 CANDIDATE IDENTITY"
    )

    emit("-" * 124)

    actual_b2_manifest_sha = sha256_file(
        B2_MANIFEST
    )

    emit(
        f"B2 candidate manifest SHA256 = "
        f"{actual_b2_manifest_sha}"
    )

    hard(
        actual_b2_manifest_sha
        ==
        EXPECTED_B2_MANIFEST_SHA,
        "B2 candidate manifest SHA mismatch.",
    )

    b2 = json.loads(
        B2_MANIFEST.read_text(
            encoding="utf-8"
        )
    )

    hard(
        b2.get("verdict")
        ==
        "PASS",
        "B2 verdict != PASS.",
    )

    hard(
        b2.get("cost_contract")
        ==
        "TIME_B5",
        "Cost contract != TIME_B5.",
    )

    hard(
        b2.get("distance")
        ==
        "PATH_ATTRIBUTE",
        "Distance semantics mismatch.",
    )

    hard(
        b2.get("weight_contract")
        ==
        "PRODUCT_LAMBDA / EXP_REL_300",
        "Weight contract mismatch.",
    )

    hard(
        b2.get("SYSTEMIC_issues")
        ==
        0,
        "SYSTEMIC issues != 0.",
    )

    hard(
        b2.get("BLOCKING_issues")
        ==
        0,
        "BLOCKING issues != 0.",
    )

    counts = b2[
        "counts"
    ]

    hard(
        int(
            counts[
                "municipal_OD"
            ]
        )
        ==
        46_010,
        "Municipal OD count mismatch.",
    )

    hard(
        int(
            counts[
                "access_pair_paths"
            ]
        )
        ==
        414_090,
        "Access-pair count mismatch.",
    )

    hard(
        int(
            counts[
                "finite"
            ]
        )
        ==
        414_090,
        "Finite path count mismatch.",
    )

    hard(
        int(
            counts[
                "unreachable"
            ]
        )
        ==
        0,
        "Unreachable paths != 0.",
    )

    hard(
        int(
            counts[
                "reconstruction_failures"
            ]
        )
        ==
        0,
        "Reconstruction failures != 0.",
    )

    hard(
        int(
            counts[
                "transition_slots"
            ]
        )
        ==
        598_707_601,
        "Transition slot count mismatch.",
    )


    qa = b2[
        "qa"
    ]

    hard(
        int(
            qa[
                "sequence_discontinuities"
            ]
        )
        ==
        0,
        "Sequence discontinuities != 0.",
    )

    hard(
        int(
            qa[
                "source_mismatch"
            ]
        )
        ==
        0,
        "Source mismatch != 0.",
    )

    hard(
        int(
            qa[
                "destination_mismatch"
            ]
        )
        ==
        0,
        "Destination mismatch != 0.",
    )

    hard(
        int(
            qa[
                "forbidden_transition_slot_violations"
            ]
        )
        ==
        0,
        "Forbidden transition slot violation != 0.",
    )

    hard(
        int(
            qa[
                "F3_matched_paths"
            ]
        )
        ==
        98_559,
        "F3 matched path count mismatch.",
    )

    hard(
        int(
            qa[
                "F3_target_state_mismatches"
            ]
        )
        ==
        0,
        "F3 target-state mismatches != 0.",
    )

    hard(
        int(
            qa[
                "F3_transition_count_mismatches"
            ]
        )
        ==
        0,
        "F3 transition mismatches != 0.",
    )

    hard(
        int(
            qa[
                "F1_sites"
            ]
        )
        ==
        4,
        "F1 site count mismatch.",
    )

    hard(
        qa[
            "F1_result"
        ]
        ==
        "PASS",
        "F1 regression != PASS.",
    )

    emit(
        "B2 candidate gate = PASS"
    )


    # =========================================================================
    # C. VERIFY ALL B2 CANDIDATE ARTIFACTS
    # =========================================================================

    emit()

    emit(
        "C. VERIFY CANDIDATE ARTIFACTS"
    )

    emit("-" * 124)

    candidate_artifacts = b2[
        "candidate_artifacts"
    ]

    source_hashes = {}

    total_bytes = 0

    for name in EXPECTED_ARTIFACTS:

        hard(
            name
            in candidate_artifacts,
            f"Artifact absent from B2 manifest: {name}",
        )

        source = (
            B2
            / name
        )

        hard(
            source.is_file(),
            f"Candidate artifact missing: {name}",
        )

        expected_sha = (
            candidate_artifacts[
                name
            ][
                "sha256"
            ]
        )

        expected_size = int(
            candidate_artifacts[
                name
            ][
                "size_bytes"
            ]
        )

        actual_sha = sha256_file(
            source
        )

        actual_size = (
            source.stat().st_size
        )

        hard(
            actual_sha
            ==
            expected_sha,
            f"Candidate SHA mismatch: {name}",
        )

        hard(
            actual_size
            ==
            expected_size,
            f"Candidate size mismatch: {name}",
        )

        source_hashes[
            name
        ] = actual_sha

        total_bytes += (
            actual_size
        )

        emit(
            f"{name:<45} "
            f"{actual_sha}"
        )

    emit()

    emit(
        f"Candidate payload size = "
        f"{fmt_size(total_bytes)}"
    )


    # =========================================================================
    # D. DISK / STAGING
    # =========================================================================

    emit()

    emit(
        "D. STAGING CREATION"
    )

    emit("-" * 124)

    free_bytes = shutil.disk_usage(
        PACKAGE_ROOT
    ).free

    emit(
        f"Free space = "
        f"{fmt_size(free_bytes)}"
    )

    hard(
        free_bytes
        >
        (
            total_bytes
            +
            1024**3
        ),
        (
            "Insufficient free space. "
            "Require payload + 1 GB margin."
        ),
    )

    STAGING.mkdir(
        parents=False,
        exist_ok=False,
    )

    emit(
        "Staging directory created."
    )


    # =========================================================================
    # E. COPY PAYLOAD
    # =========================================================================

    emit()

    emit(
        "E. COPY CANONICAL PAYLOAD"
    )

    emit("-" * 124)

    for pos, name in enumerate(
        EXPECTED_ARTIFACTS,
        start=1,
    ):

        source = (
            B2
            / name
        )

        target = (
            STAGING
            / name
        )

        emit(
            f"[{pos:02d}/{len(EXPECTED_ARTIFACTS):02d}] "
            f"Copy {name}"
        )

        shutil.copy2(
            source,
            target,
        )

    # Keep exact upstream candidate manifest
    # as an audit artifact.
    shutil.copy2(
        B2_MANIFEST,
        STAGING
        / "OSM_OD_PATHS_B2_candidate_manifest_v01.json",
    )

    emit(
        "Canonical payload copied to staging."
    )


    # =========================================================================
    # F. BYTE / HASH VERIFICATION AFTER COPY
    # =========================================================================

    emit()

    emit(
        "F. POST-COPY HASH VERIFICATION"
    )

    emit("-" * 124)

    staged_artifacts = {}

    for name in EXPECTED_ARTIFACTS:

        target = (
            STAGING
            / name
        )

        target_sha = sha256_file(
            target
        )

        hard(
            target_sha
            ==
            source_hashes[
                name
            ],
            f"Post-copy SHA mismatch: {name}",
        )

        staged_artifacts[
            name
        ] = {
            "size_bytes":
                int(
                    target.stat().st_size
                ),

            "sha256":
                target_sha,
        }

        emit(
            f"{name:<45} "
            f"{target_sha}"
        )

    copied_b2_manifest = (
        STAGING
        / "OSM_OD_PATHS_B2_candidate_manifest_v01.json"
    )

    hard(
        sha256_file(
            copied_b2_manifest
        )
        ==
        EXPECTED_B2_MANIFEST_SHA,
        "Copied B2 manifest SHA mismatch.",
    )

    emit(
        "Post-copy byte identity = PASS"
    )


    # =========================================================================
    # G. FINAL FREEZE REPORT
    # =========================================================================

    emit()

    emit(
        "G. FINAL FREEZE REPORT"
    )

    emit("-" * 124)

    report_lines = [
        "=" * 124,
        "FASE 5.7 — FINAL FREEZE REPORT",
        "=" * 124,
        "",
        "FINAL VERDICT = PASS",
        "",
        "OD_PATH_SYSTEM_OSM = FROZEN",
        "CANONICAL_ROUTE_IMPEDANCE = TIME_B5",
        "DISTANCE = PATH_ATTRIBUTE",
        "PRODUCT_LAMBDA_PATH_WEIGHTS = FROZEN",
        "ACCESS_WEIGHT_MODEL = EXP_REL_300",
        "",
        "DOMAIN",
        "-" * 124,
        "Municipalities                 = 215",
        "Ordered intermunicipal OD      = 46,010",
        "Accesses per municipality      = 3",
        "Access-pair paths              = 414,090",
        "Finite access-pair paths       = 414,090",
        "Unreachable                    = 0",
        "B5 transition slots stored     = 598,707,601",
        "",
        "QA",
        "-" * 124,
        "Path reconstruction            = 100%",
        "Sequence discontinuities       = 0",
        "Source mismatch                = 0",
        "Destination mismatch           = 0",
        "Forbidden transition violation = 0",
        "PRODUCT-LAMBDA                 = PASS",
        "B5/E2/F3 regression            = PASS",
        "F1 SHADOW regression           = PASS",
        "SYSTEMIC issues                = 0",
        "BLOCKING issues                = 0",
        "",
        "CANONICAL REPRESENTATION",
        "-" * 124,
        (
            "Path sequence = ordered CSR-like B5 "
            "transition-slot sequence."
        ),
        (
            "Transition slots reference the frozen "
            "B5 TIME/LENGTH/EDGEID arrays."
        ),
        (
            "Physical directed edges are recovered "
            "through frozen B2 edge_id."
        ),
        "",
        "MUNICIPAL SUMMARY",
        "-" * 124,
        (
            "Municipal time and distance are "
            "PRODUCT-LAMBDA weighted summaries "
            "of the nine access-pair paths."
        ),
        (
            "The municipal summary does NOT replace "
            "the elementary path system."
        ),
        "",
        "REGRESSION",
        "-" * 124,
        "Full F3 matched paths           = 98,559 / 98,559",
        "F3 target-state mismatch        = 0",
        "F3 transition mismatch          = 0",
        "F1 sites                       = 4 / 4 PASS",
        "",
        "FREEZE CONSEQUENCE",
        "-" * 124,
        (
            "Phase 5.7 is closed. "
            "Do not alter canonical routes, "
            "TIME_B5 or PRODUCT-LAMBDA path weights "
            "without formally reopening the causal gate."
        ),
        (
            "The next roadmap block starts downstream "
            "from this frozen OD-path system."
        ),
        "",
        "=== FASE 5.7 CHIUSA ===",
        "",
    ]

    FINAL_REPORT.write_text(
        "\n".join(
            report_lines
        ),
        encoding="utf-8",
    )

    report_sha = sha256_file(
        FINAL_REPORT
    )

    emit(
        f"{FINAL_REPORT_NAME:<45} "
        f"{report_sha}"
    )


    # =========================================================================
    # H. FINAL MANIFEST
    # =========================================================================

    emit()

    emit(
        "H. FINAL MANIFEST"
    )

    emit("-" * 124)

    final_manifest = {
        "phase":
            "FASE_5_7",

        "version":
            "v01",

        "status":
            "FROZEN",

        "verdict":
            "PASS",

        "freeze": {
            "OD_PATH_SYSTEM_OSM":
                "FROZEN",

            "CANONICAL_ROUTE_IMPEDANCE":
                "TIME_B5",

            "DISTANCE":
                "PATH_ATTRIBUTE",

            "PRODUCT_LAMBDA_PATH_WEIGHTS":
                "FROZEN",

            "ACCESS_WEIGHT_MODEL":
                "EXP_REL_300",
        },

        "domain": {
            "municipalities":
                215,

            "ordered_intermunicipal_OD":
                46_010,

            "accesses_per_municipality":
                3,

            "access_pair_paths":
                414_090,

            "finite_paths":
                414_090,

            "unreachable":
                0,

            "transition_slots":
                598_707_601,
        },

        "qa": qa,

        "candidate_manifest_sha256":
            EXPECTED_B2_MANIFEST_SHA,

        "candidate_artifacts":
            staged_artifacts,

        "final_report": {
            "file":
                FINAL_REPORT_NAME,

            "sha256":
                report_sha,
        },

        "upstream": {
            "A1_log_sha256":
                b2[
                    "A1_log_sha256"
                ],

            "B1_gate_sha256":
                b2[
                    "B1_gate_sha256"
                ],

            "frozen_F1_artifacts_sha256":
                b2[
                    "frozen_F1_artifacts_sha256"
                ],
        },

        "method_contract": {
            "route_choice":
                (
                    "One deterministic "
                    "time-optimal B5 path "
                    "per ordered access pair."
                ),

            "route_impedance":
                "TIME_B5",

            "distance":
                (
                    "Physical path length "
                    "computed ex post."
                ),

            "municipal_access_weight":
                (
                    "lambda_origin * "
                    "lambda_destination"
                ),

            "weight_model":
                "EXP_REL_300",

            "municipal_aggregation":
                (
                    "PRODUCT-LAMBDA weighted "
                    "summary over 9 access pairs."
                ),
        },

        "canonical_files": [
            "OSM_OD_access_paths_v01.csv",
            "OSM_OD_municipal_summary_v01.csv",
            "OSM_OD_path_offsets_v01.npy",
            "OSM_OD_transition_slots_v01.npy",
            "OSM_OD_sequence_contract_v01.json",
            "OSM_OD_F1_regression_v01.csv",
            "OSM_OD_PATHS_FINAL_REPORT_v01.txt",
            "OSM_OD_PATHS_B2_candidate_manifest_v01.json",
        ],

        "SYSTEMIC_issues":
            0,

        "BLOCKING_issues":
            0,

        "roadmap_next":
            (
                "Gateway/external block, "
                "then seed demand/assignment/ANAS "
                "according to the authoritative roadmap."
            ),
    }

    FINAL_MANIFEST.write_text(
        json.dumps(
            final_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    final_manifest_sha = sha256_file(
        FINAL_MANIFEST
    )

    emit(
        f"{FINAL_MANIFEST_NAME:<45} "
        f"{final_manifest_sha}"
    )


    # =========================================================================
    # I. COMPLETE STAGING AUDIT
    # =========================================================================

    emit()

    emit(
        "I. COMPLETE STAGING AUDIT"
    )

    emit("-" * 124)

    required_final_files = [
        *EXPECTED_ARTIFACTS,
        "OSM_OD_PATHS_B2_candidate_manifest_v01.json",
        FINAL_REPORT_NAME,
        FINAL_MANIFEST_NAME,
    ]

    for name in required_final_files:

        hard(
            (
                STAGING
                / name
            ).is_file(),
            f"Staging final file missing: {name}",
        )

    hard(
        len(
            list(
                STAGING.iterdir()
            )
        )
        ==
        len(
            required_final_files
        ),
        "Unexpected file count in staging package.",
    )

    emit(
        f"Files in staging package = "
        f"{len(required_final_files)}"
    )

    emit(
        "Complete staging audit = PASS"
    )


    # =========================================================================
    # J. ATOMIC FINAL PROMOTION
    # =========================================================================

    emit()

    emit(
        "J. ATOMIC FINAL PROMOTION"
    )

    emit("-" * 124)

    hard(
        not FINAL.exists(),
        (
            "Final package appeared during run. "
            "Promotion aborted."
        ),
    )

    STAGING.rename(
        FINAL
    )

    hard(
        FINAL.is_dir(),
        "Final package rename failed.",
    )

    hard(
        not STAGING.exists(),
        "Staging directory still exists after promotion.",
    )

    emit(
        f"Promoted to: {FINAL}"
    )


    # =========================================================================
    # K. POST-PROMOTION IDENTITY
    # =========================================================================

    emit()

    emit(
        "K. POST-PROMOTION IDENTITY"
    )

    emit("-" * 124)

    final_manifest_path = (
        FINAL
        / FINAL_MANIFEST_NAME
    )

    hard(
        sha256_file(
            final_manifest_path
        )
        ==
        final_manifest_sha,
        "Final manifest changed after promotion.",
    )

    hard(
        sha256_file(
            FINAL
            / FINAL_REPORT_NAME
        )
        ==
        report_sha,
        "Final report changed after promotion.",
    )

    for name in EXPECTED_ARTIFACTS:

        hard(
            sha256_file(
                FINAL
                / name
            )
            ==
            source_hashes[
                name
            ],
            (
                "Final artifact SHA mismatch "
                f"after promotion: {name}"
            ),
        )

    hard(
        sha256_file(
            FINAL
            / "OSM_OD_PATHS_B2_candidate_manifest_v01.json"
        )
        ==
        EXPECTED_B2_MANIFEST_SHA,
        "Final copied B2 manifest mismatch.",
    )

    emit(
        "Post-promotion SHA identity = PASS"
    )


    # =========================================================================
    # FINAL
    # =========================================================================

    emit()

    emit("=" * 124)

    emit(
        "FASE 5.7 — FINAL GATE = PASS"
    )

    emit()

    emit(
        "A — COST CONTRACT = PASS"
    )

    emit(
        "B — 414,090 / 414,090 PATHS FINITE = PASS"
    )

    emit(
        "C — PATH RECONSTRUCTION 100% = PASS"
    )

    emit(
        "D — PRODUCT-LAMBDA = PASS"
    )

    emit(
        "E — SEQUENCE INTEGRITY = PASS"
    )

    emit(
        "F — F3 + F1 REGRESSION = PASS"
    )

    emit(
        "G — SYSTEMIC issues = 0"
    )

    emit(
        "H — BLOCKING issues = 0"
    )

    emit()

    emit(
        "OD_PATH_SYSTEM_OSM = FROZEN"
    )

    emit(
        "CANONICAL_ROUTE_IMPEDANCE = TIME_B5"
    )

    emit(
        "PRODUCT_LAMBDA_PATH_WEIGHTS = FROZEN"
    )

    emit(
        "DISTANCE = PATH_ATTRIBUTE"
    )

    emit()

    emit(
        f"Final package : {FINAL}"
    )

    emit(
        f"Final manifest SHA256 = "
        f"{final_manifest_sha}"
    )

    emit(
        f"Final report SHA256   = "
        f"{report_sha}"
    )

    emit()

    emit(
        "FASE 5.7 = CLOSED / FROZEN"
    )

    emit(
        "STOP. Do not start the downstream phase "
        "inside this run."
    )

    emit("=" * 124)

    emit()

    emit(
        "=== RUN COMPLETATA CORRETTAMENTE ==="
    )


except Exception as exc:

    emit()

    emit("=" * 124)

    emit(
        "FASE 5.7 — B3 FINAL FREEZE = FAIL"
    )

    emit(
        f"{type(exc).__name__}: {exc}"
    )

    emit()

    if FINAL.exists():

        emit(
            "WARNING: final package path exists. "
            "Do NOT modify/delete it automatically. "
            "Inspect before any action."
        )

    elif STAGING.exists():

        emit(
            f"Temporary staging remains at: "
            f"{STAGING}"
        )

        emit(
            "No final promotion completed."
        )

    else:

        emit(
            "No final package was promoted."
        )

    emit()

    emit(
        "Do NOT reopen B5, Gamma, B1 or B2 "
        "from this error alone."
    )

    emit(
        "Do NOT start downstream phases."
    )

    emit("=" * 124)

    emit()

    emit(
        "=== RUN TERMINATA CON ERRORE ==="
    )

    traceback.print_exc()

    raise
