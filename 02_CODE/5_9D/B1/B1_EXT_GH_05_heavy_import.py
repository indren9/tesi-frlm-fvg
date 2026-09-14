#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ======================================================================================
# B1-EXT-GH 05 — HEAVY NATIONAL GRAPHHOPPER IMPORT
#
# DESTRUCTIVE-SAFE / VERSIONED:
#   - strict hashes before import;
#   - strict RAM/disk gate before any write;
#   - imports ONLY italy-260801.osm.pbf with the already native-validated profile;
#   - imports to a unique staging graph directory;
#   - no routing;
#   - no overwrite of final graph;
#   - on failure, preserves log + failure summary and deletes only the partial
#     staging graph (rollback);
#   - on success, atomically renames staging graph to final versioned location;
#   - writes a file-level SHA256 manifest for the final graph.
#
# This is the first heavy GraphHopper national import.
# ======================================================================================

ROOT_DEFAULT = r"C:\Tesi"

EXPECTED = {
    "italy_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1\italy-260801.osm.pbf",
        "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538",
    ),
    "gh_jar": (
        r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar",
        "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def",
    ),
    "jre_zip": (
        r"tools\graphhopper\b1_ext_v01\downloads\OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip",
        "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae",
    ),
    "profile_model": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\profile_import_preflight_v01\b1_ext_car_b5_compat_v01.json",
        "29ad0a3a425b43b039c52d1013d0706894d842120995ed607f57406a1f01ea79",
    ),
    "import_config": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml",
        "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade",
    ),
    "profile_summary": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\profile_import_preflight_v01\B1_EXT_GH_profile_import_preflight_summary_v01.json",
        "741b5b15370370557d275aded3d4c3bee2a4b6be63f3c14121e4129f056482d1",
    ),
    "profile_manifest": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\profile_import_preflight_v01\B1_EXT_GH_profile_import_preflight_manifest_v01.json",
        "ca57ab790b1f3a80866c174e272c3f34833e08cd369ef90c4ff37ff87571b110",
    ),
}

FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"
RUNS_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\heavy_import_runs"
)

PROFILE_NAME = "b1_ext_car_b5_compat_v01"

# First-attempt memory contract.
# 9 GiB is intentionally below the earlier 10 GiB candidate to leave more headroom
# on a 15.7 GiB machine. There is NO automatic retry with a larger heap.
HEAP_XMS_GIB = 1
HEAP_XMX_GIB = 9
MIN_AVAILABLE_PHYSICAL_GIB = 10.5
MIN_FREE_DISK_GIB = 40.0


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def memory_windows() -> dict[str, float | None]:
    result = {
        "total_phys_gib": None,
        "avail_phys_gib": None,
        "total_pagefile_gib": None,
        "avail_pagefile_gib": None,
        "memory_load_pct": None,
    }
    if os.name != "nt":
        return result

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    s = MEMORYSTATUSEX()
    s.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        return result

    result.update({
        "total_phys_gib": s.ullTotalPhys / (1024**3),
        "avail_phys_gib": s.ullAvailPhys / (1024**3),
        "total_pagefile_gib": s.ullTotalPageFile / (1024**3),
        "avail_pagefile_gib": s.ullAvailPageFile / (1024**3),
        "memory_load_pct": float(s.dwMemoryLoad),
    })
    return result


def find_java(runtime_root: Path) -> Path:
    candidates = sorted(
        p for p in runtime_root.rglob("java.exe")
        if p.parent.name.lower() == "bin"
    )
    for java in candidates:
        proc = subprocess.run(
            [str(java), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        first = (proc.stdout or "").splitlines()
        if not first:
            continue
        import re
        m = re.search(r'version\s+"?(\d+)', first[0])
        if m and int(m.group(1)) >= 17:
            return java
    raise RuntimeError(f"No portable Java >=17 found under {runtime_root}")


def replace_graph_location(config_text: str, staging_graph: Path) -> str:
    lines = config_text.splitlines()
    hits = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith("graph.location:")
    ]
    if len(hits) != 1:
        raise RuntimeError(
            f"Expected exactly one graph.location entry, found {len(hits)}"
        )

    path_text = staging_graph.resolve().as_posix().replace("'", "''")
    indent = lines[hits[0]][:len(lines[hits[0]]) - len(lines[hits[0]].lstrip())]
    lines[hits[0]] = f"{indent}graph.location: '{path_text}'"
    return "\n".join(lines) + "\n"


def inventory_graph(graph_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(x for x in graph_dir.rglob("*") if x.is_file()):
        rows.append({
            "relative_path": p.relative_to(graph_dir).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return rows


def write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    args = ap.parse_args()

    root = Path(args.root)
    tool_root = root / r"tools\graphhopper\b1_ext_v01"
    runtime_root = tool_root / "temurin_jre_21_0_10_7"
    final_graph = root / Path(FINAL_GRAPH_REL)
    runs_root = root / Path(RUNS_REL)

    print("=" * 126)
    print("B1-EXT-GH 05 — HEAVY NATIONAL GRAPHHOPPER IMPORT")
    print("=" * 126)
    print("ITALY IMPORT = AUTHORIZED BY THIS RUN / ROUTING = NO / NO OVERWRITE")
    print()

    paths: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # A. Preflight before ANY project write.
    # ------------------------------------------------------------------
    print("A. STRICT INPUT IDENTITY")
    for key, (rel, expected) in EXPECTED.items():
        p = root / Path(rel)
        paths[key] = p
        if not p.is_file():
            print(f"{key:<22} FAIL  MISSING {p}")
            print("HEAVY_IMPORT = NOT_STARTED")
            print("=== RUN COMPLETATA ===")
            return 2
        actual = sha256(p)
        ok = actual == expected
        print(f"{key:<22} {'PASS' if ok else 'FAIL':<5} {actual}")
        if not ok:
            print("HEAVY_IMPORT = NOT_STARTED")
            print("=== RUN COMPLETATA ===")
            return 2

    # Validate the preceding profile gate.
    summary = load_json(paths["profile_summary"])
    if summary.get("verdict") != "PASS":
        raise RuntimeError("Profile/import preflight summary is not PASS")
    native = summary.get("native_validation", {})
    if native.get("method") != "MICRO_FIXTURE_IMPORT" or native.get("return_code") != 0:
        raise RuntimeError("Native micro-fixture validation is not PASS")
    if summary.get("hard_stop", {}).get("national_graph_import") != "NOT_STARTED":
        raise RuntimeError("Unexpected prior national import state in profile summary")

    print()
    print("B. NO-OVERWRITE / HARDWARE GATE")

    if final_graph.exists():
        print(f"FINAL_GRAPH = EXISTS -> REFUSE OVERWRITE: {final_graph}")
        print("HEAVY_IMPORT = NOT_STARTED")
        print("=== RUN COMPLETATA ===")
        return 2

    java_exe = find_java(runtime_root)
    print(f"Java = {java_exe}")

    mem = memory_windows()
    disk_free_gib = shutil.disk_usage(root).free / (1024**3)

    print(f"RAM total        = {mem['total_phys_gib']:.2f} GiB" if mem["total_phys_gib"] is not None else "RAM total        = UNKNOWN")
    print(f"RAM available    = {mem['avail_phys_gib']:.2f} GiB" if mem["avail_phys_gib"] is not None else "RAM available    = UNKNOWN")
    print(f"Commit available = {mem['avail_pagefile_gib']:.2f} GiB" if mem["avail_pagefile_gib"] is not None else "Commit available = UNKNOWN")
    print(f"Disk free        = {disk_free_gib:.2f} GiB")
    print(f"Heap             = -Xms{HEAP_XMS_GIB}g -Xmx{HEAP_XMX_GIB}g")
    print(f"Required RAM available >= {MIN_AVAILABLE_PHYSICAL_GIB:.1f} GiB")
    print(f"Required disk free     >= {MIN_FREE_DISK_GIB:.1f} GiB")

    if mem["avail_phys_gib"] is None:
        print("RAM_GATE = NOT_READY (cannot read Windows available physical memory)")
        print("HEAVY_IMPORT = NOT_STARTED")
        print("=== RUN COMPLETATA ===")
        return 3

    if mem["avail_phys_gib"] < MIN_AVAILABLE_PHYSICAL_GIB:
        print("RAM_GATE = NOT_READY")
        print("ACTION = close memory-heavy applications and rerun this same script")
        print("HEAVY_IMPORT = NOT_STARTED")
        print("PROJECT_WRITES = NONE")
        print("=== RUN COMPLETATA ===")
        return 3

    if disk_free_gib < MIN_FREE_DISK_GIB:
        print("DISK_GATE = NOT_READY")
        print("HEAVY_IMPORT = NOT_STARTED")
        print("PROJECT_WRITES = NONE")
        print("=== RUN COMPLETATA ===")
        return 3

    print("RAM_GATE = PASS")
    print("DISK_GATE = PASS")

    # ------------------------------------------------------------------
    # C. Create versioned run evidence and staging paths.
    # ------------------------------------------------------------------
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_root / f"run_{stamp}"
    staging_graph = tool_root / f"_STAGING_graph_italy_260801_b5compat_v01_{stamp}"

    if run_dir.exists() or staging_graph.exists():
        raise RuntimeError("Unexpected run/staging path collision")

    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    run_config = run_dir / "graphhopper_b1_ext_import_RUN.yml"
    import_log = run_dir / "graphhopper_b1_ext_heavy_import.log"
    run_summary = run_dir / "B1_EXT_GH_heavy_import_summary.json"
    graph_manifest_path = run_dir / "B1_EXT_GH_graph_file_manifest.json"

    config_text = paths["import_config"].read_text(encoding="utf-8")
    run_config.write_text(
        replace_graph_location(config_text, staging_graph),
        encoding="utf-8",
    )

    # Pre-execution manifest.
    pre = {
        "schema": "B1_EXT_GH_HEAVY_IMPORT_RUN_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "STARTING",
        "profile": PROFILE_NAME,
        "heap": {
            "xms_gib": HEAP_XMS_GIB,
            "xmx_gib": HEAP_XMX_GIB,
        },
        "hardware_preflight": {
            **mem,
            "disk_free_gib": disk_free_gib,
            "min_available_physical_gib": MIN_AVAILABLE_PHYSICAL_GIB,
            "min_free_disk_gib": MIN_FREE_DISK_GIB,
        },
        "inputs": {
            key: {"path": str(paths[key]), "sha256": expected}
            for key, (_, expected) in EXPECTED.items()
        },
        "run_config": {
            "path": str(run_config),
            "sha256": sha256(run_config),
        },
        "staging_graph": str(staging_graph),
        "final_graph": str(final_graph),
        "routing": "NOT_STARTED",
        "frozen_artifacts_modified": False,
    }
    write_json(run_summary, pre)

    # ------------------------------------------------------------------
    # D. Heavy import. Stream stdout/stderr to console AND persistent log.
    # ------------------------------------------------------------------
    print()
    print("C. HEAVY IMPORT START")
    print(f"Run evidence  = {run_dir}")
    print(f"Staging graph = {staging_graph}")
    print(f"Final graph   = {final_graph}")
    print("Automatic retry = NO")
    print()

    cmd = [
        str(java_exe),
        f"-Xms{HEAP_XMS_GIB}g",
        f"-Xmx{HEAP_XMX_GIB}g",
        "-jar",
        str(paths["gh_jar"]),
        "import",
        str(run_config),
    ]

    start_utc = datetime.now(timezone.utc)
    return_code = None
    failure_message = None

    try:
        with import_log.open("w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(
                cmd,
                cwd=run_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="")
                log.write(line)
                log.flush()
            return_code = proc.wait()

        end_utc = datetime.now(timezone.utc)
        elapsed_s = (end_utc - start_utc).total_seconds()

        if return_code != 0:
            failure_message = f"GraphHopper import return code {return_code}"
            raise RuntimeError(failure_message)

        if not staging_graph.is_dir():
            failure_message = "Import returned 0 but staging graph directory is missing"
            raise RuntimeError(failure_message)

        graph_files = [p for p in staging_graph.rglob("*") if p.is_file()]
        if not graph_files:
            failure_message = "Import returned 0 but staging graph contains no files"
            raise RuntimeError(failure_message)

        total_graph_bytes = sum(p.stat().st_size for p in graph_files)
        print()
        print(f"Staging graph files = {len(graph_files)}")
        print(f"Staging graph size  = {total_graph_bytes / (1024**3):.3f} GiB")

        # No-overwrite recheck immediately before finalization.
        if final_graph.exists():
            failure_message = "Final graph appeared during import; refusing rename"
            raise RuntimeError(failure_message)

        staging_graph.rename(final_graph)

        # File-level hashes are computed only after successful finalization.
        graph_inventory = inventory_graph(final_graph)
        graph_manifest = {
            "schema": "B1_EXT_GH_GRAPH_FILE_MANIFEST_V01",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "graph_root": str(final_graph),
            "file_count": len(graph_inventory),
            "total_size_bytes": sum(x["size_bytes"] for x in graph_inventory),
            "files": graph_inventory,
        }
        write_json(graph_manifest_path, graph_manifest)

        final_summary = {
            **pre,
            "status": "PASS",
            "started_utc": start_utc.isoformat(),
            "ended_utc": end_utc.isoformat(),
            "elapsed_seconds": elapsed_s,
            "return_code": return_code,
            "import_log": {
                "path": str(import_log),
                "sha256": sha256(import_log),
                "size_bytes": import_log.stat().st_size,
            },
            "graph": {
                "path": str(final_graph),
                "file_count": graph_manifest["file_count"],
                "total_size_bytes": graph_manifest["total_size_bytes"],
                "file_manifest_path": str(graph_manifest_path),
                "file_manifest_sha256": sha256(graph_manifest_path),
            },
            "staging_graph_after_success": "RENAMED_TO_FINAL",
            "routing": "NOT_STARTED",
            "next_gate": "GRAPH_LOAD_AND_TARGETED_ROUTING_QA",
        }
        write_json(run_summary, final_summary)

        print()
        print("=" * 126)
        print("B1_EXT_GH_05_HEAVY_IMPORT = PASS")
        print(f"GRAPH = {final_graph}")
        print(f"GRAPH_FILES = {graph_manifest['file_count']}")
        print(f"GRAPH_SIZE_GIB = {graph_manifest['total_size_bytes'] / (1024**3):.3f}")
        print(f"IMPORT_ELAPSED_MIN = {elapsed_s / 60.0:.2f}")
        print(f"IMPORT_LOG_SHA256 = {sha256(import_log)}")
        print(f"GRAPH_MANIFEST_SHA256 = {sha256(graph_manifest_path)}")
        print("ROUTING = NOT_STARTED")
        print("FROZEN_ARTIFACTS_MODIFIED = NO")
        print("NEXT_GATE = GRAPH_LOAD_AND_TARGETED_ROUTING_QA")
        print("=== RUN COMPLETATA ===")
        return 0

    except Exception as exc:
        end_utc = datetime.now(timezone.utc)
        elapsed_s = (end_utc - start_utc).total_seconds()

        # Roll back only the partial staging graph. Never touch a final graph.
        rollback = "NO_STAGING_GRAPH"
        if staging_graph.exists():
            try:
                shutil.rmtree(staging_graph)
                rollback = "PARTIAL_STAGING_GRAPH_REMOVED"
            except Exception as cleanup_exc:
                rollback = f"ROLLBACK_FAILED:{cleanup_exc!r}"

        failure = {
            **pre,
            "status": "FAIL",
            "started_utc": start_utc.isoformat(),
            "ended_utc": end_utc.isoformat(),
            "elapsed_seconds": elapsed_s,
            "return_code": return_code,
            "error": repr(exc),
            "rollback": rollback,
            "import_log": {
                "path": str(import_log),
                "exists": import_log.exists(),
                "sha256": sha256(import_log) if import_log.exists() else None,
                "size_bytes": import_log.stat().st_size if import_log.exists() else None,
            },
            "final_graph_exists": final_graph.exists(),
            "routing": "NOT_STARTED",
            "next_gate": "REVIEW_IMPORT_FAILURE",
        }
        write_json(run_summary, failure)

        print()
        print("=" * 126)
        print("B1_EXT_GH_05_HEAVY_IMPORT = FAIL")
        print(f"ERROR = {exc}")
        print(f"ROLLBACK = {rollback}")
        print(f"RUN_EVIDENCE = {run_dir}")
        print("ROUTING = NOT_STARTED")
        print("FROZEN_ARTIFACTS_MODIFIED = NO")
        print("NEXT_GATE = REVIEW_IMPORT_FAILURE")
        print("=== RUN COMPLETATA ===")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
