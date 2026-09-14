#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

EXPECTED_FROZEN = {
    r"Tesi_QGIS\00_originali\rete_stradale\osm\nord-est_2026-08-03.osm.pbf":
        "e3b8be938c6acc58be516d988f0162c768e092a5674398d9c0f43ea9d9663813",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\G_OSM_operativo_v01.gpkg":
        "f1d87245d1bc28f3ecab16e126514f8a3ab718b73ce7bd244db2f12628697ef3",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite":
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_restrictions_compiled_v01.sqlite":
        "53b352e12aac674513bf6e37458b30775712892a52a9f4011e9bd75d62fcf4bd",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_time_v01.npz":
        "b258872cb4ef23b3a11d8e93e28e5df2ca778f6c2103ed072211d82b130a0c72",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_length_v01.npz":
        "22c108e5f0707f26ff47043de0e98759114d8feffca7c82ecd3d5903e16780a2",
    r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_turn_state_edgeid_v01.npz":
        "dac4b68bb0f1aac363680202f1c0f7881c49d0af9257c727408f6e938ebee185",
    r"Tesi_QGIS\02_package\accessi_comunali_osm_light\Gamma_OSM_L_comuni_fvg_v01.csv":
        "a2ec905f84a2df2f566d670a7522ed583e4d9235664f77e3920f96e3fca1ebb5",
    r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_access_paths_v01.csv":
        "3c0a8786a05719db4ca2a4258250bde8937b8dd017d93fea0c8f4a8a101c8dd3",
    r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_path_offsets_v01.npy":
        "478efd3a3f6eba6964db9f0a785dfd9405d5ae61af30e4f84538b0699a7a3a08",
    r"Tesi_QGIS\02_package\od_paths_osm_light\OSM_OD_transition_slots_v01.npy":
        "2a6b06d21b6d3eea7132a0154bbb4c74d305a4ea582d780e07b5abeed24d2c1d",
}

GH_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
JRE_ZIP_SHA256 = "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae"
FROZEN_TS = "2026-08-03T20:21:36Z"
FROZEN_SEQ = "3928"
FROZEN_BASE_SUFFIX = "/europe/italy/nord-est-updates"
ITALY_MD5_URL = "https://download.geofabrik.de/europe/italy-260801.osm.pbf.md5"

def hash_file(path: Path, algo: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()

def get_pbf_header(path: Path) -> dict[str, str]:
    import osmium
    r = osmium.io.Reader(str(path))
    try:
        h = r.header()
        return {
            "generator": h.get("generator", ""),
            "base_url": h.get("osmosis_replication_base_url", ""),
            "sequence": h.get("osmosis_replication_sequence_number", ""),
            "timestamp": h.get("osmosis_replication_timestamp", "") or h.get("timestamp", ""),
        }
    finally:
        r.close()

def get_official_italy_md5(timeout: int = 30) -> tuple[str | None, str | None]:
    try:
        req = urllib.request.Request(
            ITALY_MD5_URL,
            headers={"User-Agent": "Tesi-B1-EXT-recovery/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read(4096).decode("utf-8", errors="replace").strip()
        m = re.search(r"\b([a-fA-F0-9]{32})\b", text)
        return (m.group(1).lower(), None) if m else (None, f"MD5 non parsabile: {text!r}")
    except Exception as e:
        return None, repr(e)

def java_major(java_exe: Path) -> int | None:
    try:
        p = subprocess.run(
            [str(java_exe), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )
        first = p.stdout.splitlines()[0] if p.stdout else ""
        m = re.search(r'version\s+"?(\d+)', first)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def load_manifest(path: Path) -> dict | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def yn(v: bool) -> str:
    return "PASS" if v else "FAIL"

def main() -> int:
    ap = argparse.ArgumentParser(description="READ-ONLY recovery of B1-EXT GraphHopper materialization state.")
    ap.add_argument("--root", default=r"C:\Tesi")
    args = ap.parse_args()

    root = Path(args.root)
    tool_root = root / "tools" / "graphhopper" / "b1_ext_v01"
    jar = tool_root / "graphhopper-web-11.0.jar"
    jre_zip = tool_root / "downloads" / "OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip"
    runtime_root = tool_root / "temurin_jre_21_0_10_7"
    italy = root / "Tesi_QGIS" / "00_originali" / "rete_stradale" / "osm" / "external_b1" / "italy-260801.osm.pbf"
    manifest = root / "Tesi_QGIS" / "03_output_temporanei" / "fase_5_9D_B1_ext_support" / "B1_EXT_GH_materialization_manifest_v01.json"
    frozen_pbf = root / "Tesi_QGIS" / "00_originali" / "rete_stradale" / "osm" / "nord-est_2026-08-03.osm.pbf"

    print("=" * 116)
    print("B1-EXT-GH - RECOVERY STATUS")
    print("=" * 116)
    print("READ-ONLY: no file is created, modified, downloaded or deleted.")
    print()

    fatal, incomplete = [], []

    print("A. FROZEN BYTE-INTEGRITY")
    frozen_ok = True
    for rel, expected in EXPECTED_FROZEN.items():
        p = root / Path(rel)
        if not p.is_file():
            print(f"{Path(rel).name:<48} FAIL  MISSING")
            frozen_ok = False
            fatal.append(f"Missing frozen artifact: {p}")
            continue
        actual = hash_file(p, "sha256")
        ok = actual == expected
        print(f"{p.name:<48} {yn(ok):<5} {actual}")
        if not ok:
            frozen_ok = False
            fatal.append(f"Frozen SHA256 mismatch: {p}")

    print()
    print("B. FROZEN PBF PROVENANCE")
    try:
        fh = get_pbf_header(frozen_pbf)
        prov_ok = (
            fh["timestamp"] == FROZEN_TS
            and fh["sequence"] == FROZEN_SEQ
            and fh["base_url"].endswith(FROZEN_BASE_SUFFIX)
        )
        print(f"timestamp = {fh['timestamp']}")
        print(f"sequence  = {fh['sequence']}")
        print(f"generator = {fh['generator']}")
        print(f"base_url  = {fh['base_url']}")
        print(f"FROZEN_PBF_PROVENANCE = {yn(prov_ok)}")
        if not prov_ok:
            fatal.append("Frozen PBF provenance mismatch")
    except Exception as e:
        print(f"FROZEN_PBF_PROVENANCE = FAIL ({e!r})")
        fatal.append("Frozen PBF header unreadable")

    print()
    print("C. MATERIALIZATION MANIFEST")
    try:
        m = load_manifest(manifest)
    except Exception as e:
        m = None
        print(f"MANIFEST = FAIL_PARSE ({e!r})")
        fatal.append("Manifest exists but cannot be parsed")
    else:
        if m is None:
            print("MANIFEST = NOT_PRESENT")
            incomplete.append("Materialization manifest not present")
        else:
            print("MANIFEST = PRESENT")
            print(f"schema   = {m.get('schema')}")
            print(f"role     = {m.get('role')}")
            print(f"policy   = {m.get('source_policy')}")
            hard = m.get("hard_stop", {})
            print(f"graph_import = {hard.get('graph_import')}")
            print(f"routing      = {hard.get('routing')}")

    print()
    print("D. GRAPHHOPPER")
    if jar.is_file():
        jar_sha = hash_file(jar, "sha256")
        jar_ok = jar_sha == GH_SHA256
        print(f"JAR_SHA256 = {jar_sha}")
        print(f"GRAPHHOPPER_JAR = {yn(jar_ok)}")
        if not jar_ok:
            fatal.append("GraphHopper JAR SHA256 mismatch")
    else:
        print("GRAPHHOPPER_JAR = NOT_PRESENT")
        incomplete.append("GraphHopper JAR not present")

    print()
    print("E. PORTABLE JAVA")
    if jre_zip.is_file():
        jre_sha = hash_file(jre_zip, "sha256")
        jre_zip_ok = jre_sha == JRE_ZIP_SHA256
        print(f"JRE_ZIP_SHA256 = {jre_sha}")
        print(f"JRE_ZIP = {yn(jre_zip_ok)}")
        if not jre_zip_ok:
            fatal.append("Temurin JRE ZIP SHA256 mismatch")
    else:
        print("JRE_ZIP = NOT_PRESENT")
        incomplete.append("Temurin JRE ZIP not present")

    java_candidates = [p for p in runtime_root.rglob("java.exe") if p.parent.name.lower() == "bin"] if runtime_root.is_dir() else []
    java_ok = False
    java_used = None
    java_ver = None
    for j in java_candidates:
        major = java_major(j)
        if major is not None and major >= 17:
            java_ok, java_used, java_ver = True, j, major
            break
    if java_ok:
        print(f"JAVA_EXE = {java_used}")
        print(f"JAVA_MAJOR = {java_ver}")
        print("PORTABLE_JAVA = PASS")
    else:
        print("PORTABLE_JAVA = NOT_READY")
        incomplete.append("Portable Java runtime not ready")

    print()
    print("F. NATIONAL PBF")
    official_md5 = None
    network_err = None
    if m:
        official_md5 = (
            m.get("national_source", {}).get("official_md5")
            or m.get("national_source", {}).get("verified_md5")
        )
        if official_md5:
            official_md5 = str(official_md5).lower()
    if official_md5 is None:
        official_md5, network_err = get_official_italy_md5()

    if network_err:
        print(f"OFFICIAL_MD5_LOOKUP = UNAVAILABLE ({network_err})")
    elif official_md5:
        print(f"OFFICIAL_MD5 = {official_md5}")

    italy_ok = False
    italy_sha = None
    italy_md5 = None
    if italy.is_file():
        print(f"ITALY_PBF_PATH = {italy}")
        print(f"ITALY_PBF_SIZE = {italy.stat().st_size}")
        italy_md5 = hash_file(italy, "md5")
        italy_sha = hash_file(italy, "sha256")
        print(f"ITALY_PBF_MD5 = {italy_md5}")
        print(f"ITALY_PBF_SHA256 = {italy_sha}")
        if official_md5:
            italy_ok = italy_md5 == official_md5
            print(f"ITALY_PBF_OFFICIAL_MD5 = {yn(italy_ok)}")
            if not italy_ok:
                fatal.append("Italy PBF MD5 mismatch")
        else:
            print("ITALY_PBF_OFFICIAL_MD5 = UNKNOWN")
            incomplete.append("Cannot establish official Italy PBF MD5")
        try:
            ih = get_pbf_header(italy)
            print(
                "ITALY_PBF_HEADER = "
                f"timestamp={ih['timestamp']} sequence={ih['sequence']} "
                f"generator={ih['generator']} base_url={ih['base_url']}"
            )
        except Exception as e:
            print(f"ITALY_PBF_HEADER = FAIL ({e!r})")
            fatal.append("Italy PBF header unreadable")
    else:
        print("ITALY_PBF = NOT_PRESENT")
        incomplete.append("Italy PBF not present")

    print()
    print("G. MANIFEST CONSISTENCY")
    manifest_ok = False
    if m:
        ns = m.get("national_source", {})
        hard = m.get("hard_stop", {})
        checks = {
            "role": m.get("role") == "EXTERNAL_ITALY_ROUTING_SUPPORT_ONLY",
            "italy_sha": (not italy_sha) or (str(ns.get("project_sha256", "")).lower() == italy_sha),
            "italy_md5": (not italy_md5) or (str(ns.get("verified_md5", "")).lower() == italy_md5),
            "graph_import_not_started": hard.get("graph_import") == "NOT_STARTED",
            "routing_not_started": hard.get("routing") == "NOT_STARTED",
            "frozen_not_modified": hard.get("frozen_artifacts_modified") is False,
        }
        for name, ok in checks.items():
            print(f"{name:<32} {yn(ok)}")
        manifest_ok = all(checks.values())
        if not manifest_ok:
            fatal.append("Manifest consistency check failed")
    else:
        print("MANIFEST_CONSISTENCY = NOT_APPLICABLE")

    print()
    print("=" * 116)
    if fatal:
        status = "FAIL"
    elif incomplete:
        status = "INCOMPLETE"
    elif frozen_ok and italy_ok and manifest_ok and java_ok:
        status = "PASS"
    else:
        status = "INCOMPLETE"

    print(f"B1_EXT_GH_RECOVERED_STATUS = {status}")
    print(f"FROZEN_ARTIFACTS = {'UNCHANGED' if frozen_ok else 'PROBLEM'}")
    print("GRAPH_IMPORT = NOT_STARTED")
    print("ROUTING = NOT_STARTED")

    if fatal:
        print("FATAL_ISSUES:")
        for x in fatal:
            print(f"  - {x}")
    if incomplete:
        print("INCOMPLETE_ITEMS:")
        for x in incomplete:
            print(f"  - {x}")

    print("NEXT_GATE = " + ("HYBRID_B5_GRAPHHOPPER_INTERFACE_VALIDATION" if status == "PASS" else "DO_NOT_IMPORT_GRAPH_YET"))
    print("PROJECT_WRITES = NONE")
    print("=== RUN COMPLETATA ===")
    return 0 if status == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
