#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ======================================================================================
# B1-EXT-GH 04 — GRAPHHOPPER PROFILE + IMPORT PREFLIGHT
#
# SAFE GATE ONLY:
#   - validates frozen/materialized identities;
#   - audits B2 CORE road classes/speeds;
#   - validates GraphHopper 11 JAR capabilities;
#   - materializes a versioned candidate custom model + import config;
#   - uses Dropwizard's "check" command if exposed by the JAR;
#   - DOES NOT import the GraphHopper graph;
#   - DOES NOT route;
#   - DOES NOT modify frozen project artifacts.
#
# Architecture:
#   INTERNAL_ROUTER = B5_FROZEN
#   EXTERNAL_ROUTER = GRAPHHOPPER_11
#   EXTERNAL_PROFILE = B5_COMPATIBLE_STATIC_TIME
#   CH/LM = DISABLED for the first low-memory import baseline
# ======================================================================================

EXPECTED = {
    "italy_pbf": (
        r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1\italy-260801.osm.pbf",
        "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538",
    ),
    "b2": (
        r"Tesi_QGIS\02_package\grafo_operativo_osm\osm_directed_edges_v02.sqlite",
        "04809af9e13dc32de45e18a34a0917222e3ab9c0794406b1b242a8bab6c11859",
    ),
    "gh_jar": (
        r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar",
        "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def",
    ),
    "jre_zip": (
        r"tools\graphhopper\b1_ext_v01\downloads\OpenJDK21U-jre_x64_windows_hotspot_21.0.10_7.zip",
        "a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae",
    ),
    "topology_way_audit": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_way_audit_v01.csv",
        "f3949a0c9cd6cf3ddb16b6c6a05a525fc69d5ba6c27b36be81d3051ec266a1e9",
    ),
    "topology_geo_audit": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_geo_audit_v01.csv",
        "281d116da9b86374e1e4add02d72255a9db11fa70cc70a06265c5e7f1326a2bd",
    ),
    "topology_gateway_audit": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_gateway_audit_v01.csv",
        "723e9f5466e6a2a14fb1f9b8aa896ece42731ccec0d9a80d8fd90b32e8f42191",
    ),
    "topology_summary": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_topology_summary_v01.json",
        "6e9aaa388d9a1fb4dbd8e6748fd35bc61d097a76e569e8c18a02533b8b206940",
    ),
    "topology_manifest": (
        r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
        r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_topology_manifest_v01.json",
        "77b9dfc8dd6177d01a802ed47e8acaffd8def841e9bc7901e72f2e5dacf1d173",
    ),
}

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
MODEL_FILENAME = "b1_ext_car_b5_compat_v01.json"
CHECK_CONFIG_FILENAME = "graphhopper_b1_ext_check_v01.yml"
IMPORT_CONFIG_FILENAME = "graphhopper_b1_ext_import_v01.yml"
CHECK_LOG_FILENAME = "graphhopper_config_check_v01.log"
B2_AUDIT_FILENAME = "B1_EXT_GH_b2_core_profile_audit_v01.csv"
SUMMARY_FILENAME = "B1_EXT_GH_profile_import_preflight_summary_v01.json"
MANIFEST_FILENAME = "B1_EXT_GH_profile_import_preflight_manifest_v01.json"

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01"
)

FUTURE_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"

# Frozen B5 static operational speed caps.
B5_SPEED_CAPS = {
    "motorway": 90.0,
    "motorway_link": 45.0,
    "trunk": 85.0,
    "trunk_link": 40.0,
    "primary": 65.0,
    "primary_link": 30.0,
    "secondary": 55.0,
    "secondary_link": 25.0,
    "tertiary": 40.0,
    "tertiary_link": 20.0,
    "unclassified": 25.0,
    "residential": 25.0,
    "living_street": 10.0,
}

# GraphHopper 11 CarAverageSpeedParser defaults.
# Used only to build a transparent compatibility factor before applying
# the frozen B5 cap. The final max_speed rule restores the exact OSM limit
# where GraphHopper's base car speed uses 0.9*maxspeed.
GH11_DEFAULT_SPEEDS = {
    "motorway": 100.0,
    "motorway_link": 70.0,
    "trunk": 70.0,
    "trunk_link": 65.0,
    "primary": 65.0,
    "primary_link": 60.0,
    "secondary": 60.0,
    "secondary_link": 50.0,
    "tertiary": 50.0,
    "tertiary_link": 40.0,
    "unclassified": 30.0,
    "residential": 30.0,
    "living_street": 6.0,
}

# GraphHopper caps bad surfaces to 30 km/h for classes whose base speed is above 30.
GH11_BAD_SURFACE_CAP = 30.0

# Unsupported classes are blocked by the custom profile. They can also be skipped
# during OSM import to reduce memory/disk use. service remains excluded because the
# frozen thesis contract treats it as auxiliary rather than ordinary through-routing.
IGNORED_HIGHWAYS = [
    "footway", "construction", "cycleway", "path", "steps",
    "pedestrian", "platform", "corridor", "bridleway",
    "track", "service", "road", "busway",
]


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def posix_win(path: Path) -> str:
    return path.resolve().as_posix()


def get_java_major(java_exe: Path) -> tuple[int | None, str]:
    p = subprocess.run(
        [str(java_exe), "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    text = p.stdout or ""
    first = text.splitlines()[0] if text.splitlines() else ""
    m = re.search(r'version\s+"?(\d+)', first)
    return (int(m.group(1)) if m else None, text)


def find_java(runtime_root: Path) -> Path:
    candidates = sorted(
        p for p in runtime_root.rglob("java.exe")
        if p.parent.name.lower() == "bin"
    )
    for p in candidates:
        major, _ = get_java_major(p)
        if major is not None and major >= 17:
            return p
    raise FileNotFoundError(f"No Java >=17 found under {runtime_root}")


def memory_windows() -> tuple[float | None, float | None]:
    if os.name != "nt":
        return None, None

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

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    if not ok:
        return None, None
    return status.ullTotalPhys / (1024**3), status.ullAvailPhys / (1024**3)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def b2_core_audit(db: Path) -> list[dict]:
    uri = db.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            """
            SELECT
                highway,
                COUNT(*) AS n_edges,
                MIN(speed_kmh) AS min_speed_kmh,
                MAX(speed_kmh) AS max_speed_kmh,
                COUNT(DISTINCT speed_kmh) AS distinct_speed_values,
                SUM(CASE WHEN routing_code=1 AND core_eligible=1 THEN 1 ELSE 0 END) AS n_core
            FROM directed_edges
            WHERE routing_code=1 AND core_eligible=1
            GROUP BY highway
            ORDER BY highway
            """
        ).fetchall()
        return [
            {
                "highway": "" if r[0] is None else str(r[0]),
                "n_edges": int(r[1]),
                "min_speed_kmh": float(r[2]),
                "max_speed_kmh": float(r[3]),
                "distinct_speed_values": int(r[4]),
                "n_core": int(r[5]),
            }
            for r in rows
        ]
    finally:
        con.close()


def make_speed_factor(highway: str) -> float:
    """
    Factor large enough to:
      1) reverse GraphHopper's 0.9 factor on explicit maxspeed;
      2) reach the frozen B5 class cap on missing maxspeed;
      3) neutralize GH's 30 km/h bad-surface cap for B5 classes >30.
    The subsequent class cap and max_speed cap then bound the final speed.
    """
    target = B5_SPEED_CAPS[highway]
    gh_default = GH11_DEFAULT_SPEEDS[highway]
    floor = min(gh_default, GH11_BAD_SURFACE_CAP) if gh_default > GH11_BAD_SURFACE_CAP else gh_default
    return max(1.0 / 0.9, target / gh_default, target / floor)


def condition_for(highway: str) -> str:
    if highway.endswith("_link"):
        base = highway[:-5].upper()
        return f"road_class == {base} && road_class_link"
    if highway in {"motorway", "trunk", "primary", "secondary", "tertiary"}:
        return f"road_class == {highway.upper()} && !road_class_link"
    return f"road_class == {highway.upper()}"


def build_custom_model() -> dict:
    allowed_base = [
        "MOTORWAY", "TRUNK", "PRIMARY", "SECONDARY", "TERTIARY",
        "UNCLASSIFIED", "RESIDENTIAL", "LIVING_STREET",
    ]
    unsupported = " && ".join(f"road_class != {x}" for x in allowed_base)

    speed = [
        {"if": "true", "limit_to": "car_average_speed"},
    ]

    for highway in B5_SPEED_CAPS:
        cond = condition_for(highway)
        factor = round(make_speed_factor(highway), 10)
        cap = B5_SPEED_CAPS[highway]
        speed.append({"if": cond, "multiply_by": f"{factor:.10f}"})
        speed.append({"if": cond, "limit_to": f"{cap:g}"})

    # Missing max_speed is +infinity in GraphHopper. maxspeed=none can be 150,
    # while all B5 class caps are <=90, so only values <150 need to bind here.
    speed.append({"if": "max_speed < 150", "limit_to": "max_speed"})

    return {
        "distance_influence": 0,
        "priority": [
            {"if": "!car_access", "multiply_by": "0"},
            {"if": unsupported, "multiply_by": "0"},
        ],
        "speed": speed,
    }


def yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def make_config(
    pbf: Path,
    graph_location: Path,
    custom_model_dir: Path,
) -> str:
    encoded = (
        "car_access, car_average_speed, road_class, road_class_link, "
        "max_speed, osm_way_id"
    )
    ignored = ",".join(IGNORED_HIGHWAYS)

    return f"""graphhopper:
  datareader.file: {yaml_quote(posix_win(pbf))}
  graph.location: {yaml_quote(posix_win(graph_location))}

  profiles:
    - name: {PROFILE_NAME}
      turn_costs:
        vehicle_types: [motorcar, motor_vehicle]
        u_turn_costs: 0
      custom_model_files: [{MODEL_FILENAME}]

  custom_models.directory: {yaml_quote(posix_win(custom_model_dir))}

  profiles_ch: []
  profiles_lm: []

  graph.encoded_values: {encoded}

  graph.dataaccess.default_type: MMAP
  prepare.min_network_size: 200
  prepare.subnetworks.threads: 1

  import.osm.ignored_highways: {ignored}

logging:
  level: WARN
  appenders:
    - type: console
"""


def jar_capability_audit(jar: Path) -> dict:
    required_suffixes = {
        "car_model": "com/graphhopper/custom_models/car.json",
        "road_class_link": "com/graphhopper/routing/ev/RoadClassLink.class",
        "max_speed": "com/graphhopper/routing/ev/MaxSpeed.class",
        "osm_maxspeed_parser": "com/graphhopper/routing/util/parsers/OSMMaxSpeedParser.class",
        "car_speed_parser": "com/graphhopper/routing/util/parsers/CarAverageSpeedParser.class",
    }

    with zipfile.ZipFile(jar, "r") as z:
        names = set(z.namelist())
        hits = {}
        for key, suffix in required_suffixes.items():
            matches = sorted(n for n in names if n.endswith(suffix))
            hits[key] = matches

        manifest_text = ""
        if "META-INF/MANIFEST.MF" in names:
            manifest_text = z.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")

        car_json_text = ""
        car_matches = hits["car_model"]
        if car_matches:
            car_json_text = z.read(car_matches[0]).decode("utf-8", errors="replace")

    return {
        "required_resource_hits": hits,
        "manifest_text": manifest_text,
        "embedded_car_model_text": car_json_text,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\Tesi")
    args = ap.parse_args()

    root = Path(args.root)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    future_graph = root / Path(FUTURE_GRAPH_REL)

    tool_root = root / r"tools\graphhopper\b1_ext_v01"
    runtime_root = tool_root / "temurin_jre_21_0_10_7"

    print("=" * 124)
    print("B1-EXT-GH 04 — GRAPHHOPPER PROFILE + IMPORT PREFLIGHT")
    print("=" * 124)
    print("NO GRAPH IMPORT / NO ROUTING / VERSIONED CONFIG MATERIALIZATION ONLY")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(f"Unexpected staging exists: {staging}")
    if future_graph.exists():
        raise FileExistsError(
            f"NO OVERWRITE: future GraphHopper graph location already exists: {future_graph}"
        )

    paths: dict[str, Path] = {}
    failures: list[str] = []
    warnings: list[str] = []

    try:
        # ------------------------------------------------------------------
        # A. Strict identity gate before writes
        # ------------------------------------------------------------------
        print("A. STRICT IDENTITY GATE")
        for key, (rel, expected) in EXPECTED.items():
            p = root / Path(rel)
            paths[key] = p
            if not p.is_file():
                raise FileNotFoundError(p)
            actual = sha256(p)
            ok = actual == expected
            print(f"{key:<24} {'PASS' if ok else 'FAIL':<5} {actual}")
            if not ok:
                raise RuntimeError(f"SHA256 mismatch: {key}")

        topology_summary = load_json(paths["topology_summary"])
        topology_ok = (
            topology_summary.get("verdict") == "PASS"
            and topology_summary.get("hard_stop", {}).get("graph_import") == "NOT_STARTED"
            and topology_summary.get("hard_stop", {}).get("routing") == "NOT_STARTED"
            and topology_summary.get("gateway_failures") == []
        )
        print(f"topology gate             {'PASS' if topology_ok else 'FAIL'}")
        if not topology_ok:
            raise RuntimeError("Targeted shared-boundary topology gate is not PASS")

        # ------------------------------------------------------------------
        # B. Hardware / Java
        # ------------------------------------------------------------------
        print()
        print("B. HARDWARE / JAVA PREFLIGHT")

        java_exe = find_java(runtime_root)
        java_major, java_version_text = get_java_major(java_exe)
        print(f"Java executable = {java_exe}")
        print(f"Java major      = {java_major}")
        if java_major is None or java_major < 17:
            raise RuntimeError("Java >=17 required")

        total_ram, avail_ram = memory_windows()
        if total_ram is not None:
            print(f"RAM total       = {total_ram:.2f} GiB")
            print(f"RAM available   = {avail_ram:.2f} GiB")
            if total_ram < 15.0:
                failures.append("RAM_TOTAL_LT_15_GIB")
            if avail_ram < 8.0:
                warnings.append("AVAILABLE_RAM_LT_8_GIB_CLOSE_OTHER_APPS_BEFORE_IMPORT")
        else:
            warnings.append("RAM_QUERY_UNAVAILABLE")

        disk = shutil.disk_usage(root)
        free_gib = disk.free / (1024**3)
        print(f"Disk free       = {free_gib:.2f} GiB")
        if free_gib < 25.0:
            failures.append("DISK_FREE_LT_25_GIB")

        recommended_heap_gib = 10
        print(f"Candidate import heap = -Xms1g -Xmx{recommended_heap_gib}g")
        print("Graph storage mode    = MMAP")
        print("CH / LM preparations  = DISABLED")

        # ------------------------------------------------------------------
        # C. B2 CORE profile audit
        # ------------------------------------------------------------------
        print()
        print("C. B2 CORE PROFILE AUDIT")

        b2_rows = b2_core_audit(paths["b2"])
        core_classes = {r["highway"] for r in b2_rows}
        allowed = set(B5_SPEED_CAPS)
        unexpected_core = sorted(core_classes - allowed)
        missing_expected = sorted(allowed - core_classes)

        print("B2 CORE highway classes:")
        for r in b2_rows:
            cap = B5_SPEED_CAPS.get(r["highway"])
            cap_ok = cap is not None and r["max_speed_kmh"] <= cap + 1e-9 and r["min_speed_kmh"] > 0
            print(
                f"  {r['highway']:<18} edges={r['n_edges']:>8} "
                f"speed=[{r['min_speed_kmh']:g},{r['max_speed_kmh']:g}] "
                f"cap={cap if cap is not None else 'UNMAPPED'} "
                f"{'PASS' if cap_ok else 'FAIL'}"
            )
            if not cap_ok:
                failures.append(f"B2_SPEED_CONTRACT_{r['highway']}")

        print(f"Unexpected CORE classes = {unexpected_core}")
        print(f"Allowed classes absent from CORE = {missing_expected}")

        if unexpected_core:
            failures.append("UNEXPECTED_B2_CORE_HIGHWAY_CLASS")
        if missing_expected:
            warnings.append("SOME_FROZEN_SPEED_CLASSES_ABSENT_FROM_CURRENT_B2_CORE")

        # ------------------------------------------------------------------
        # D. JAR capability audit
        # ------------------------------------------------------------------
        print()
        print("D. GRAPHHOPPER 11 JAR CAPABILITY AUDIT")

        jar_audit = jar_capability_audit(paths["gh_jar"])
        for key, hits in jar_audit["required_resource_hits"].items():
            ok = len(hits) >= 1
            print(f"{key:<24} {'PASS' if ok else 'FAIL'} {hits[:1]}")
            if not ok:
                failures.append(f"GH_JAR_CAPABILITY_{key}")

        car_model = jar_audit["embedded_car_model_text"]
        embedded_contract_ok = (
            "car_access" in car_model
            and "car_average_speed" in car_model
        )
        print(f"embedded car base model  {'PASS' if embedded_contract_ok else 'FAIL'}")
        if not embedded_contract_ok:
            failures.append("GH_EMBEDDED_CAR_MODEL_UNEXPECTED")

        # ------------------------------------------------------------------
        # E. Build versioned candidate config in staging
        # ------------------------------------------------------------------
        print()
        print("E. MATERIALIZE CANDIDATE PROFILE / CONFIG")

        if failures:
            print("Materialization skipped because blocking preflight failures exist.")
            raise RuntimeError("Blocking preflight failures: " + "|".join(failures))

        staging.mkdir(parents=True, exist_ok=False)

        model = build_custom_model()
        model_path = staging / MODEL_FILENAME
        model_path.write_text(
            json.dumps(model, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # JSON round-trip before GraphHopper check.
        with model_path.open("r", encoding="utf-8") as f:
            round_trip = json.load(f)
        if round_trip != model:
            raise RuntimeError("Custom model JSON round-trip mismatch")

        check_graph = staging / "_CHECK_GRAPH_MUST_NOT_BE_IMPORTED"
        check_config = make_config(
            paths["italy_pbf"],
            check_graph,
            staging,
        )
        check_config_path = staging / CHECK_CONFIG_FILENAME
        check_config_path.write_text(check_config, encoding="utf-8")

        # Final import config points to the future versioned graph cache and to the
        # post-rename final custom-model directory.
        import_config = make_config(
            paths["italy_pbf"],
            future_graph,
            final_dir,
        )
        import_config_path = staging / IMPORT_CONFIG_FILENAME
        import_config_path.write_text(import_config, encoding="utf-8")

        # B2 audit CSV
        b2_audit_path = staging / B2_AUDIT_FILENAME
        with b2_audit_path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "highway", "n_edges", "min_speed_kmh", "max_speed_kmh",
                "distinct_speed_values", "n_core", "b5_cap_kmh",
                "gh11_default_kmh", "compatibility_factor",
            ]
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in b2_rows:
                h = r["highway"]
                w.writerow({
                    **r,
                    "b5_cap_kmh": B5_SPEED_CAPS[h],
                    "gh11_default_kmh": GH11_DEFAULT_SPEEDS[h],
                    "compatibility_factor": round(make_speed_factor(h), 10),
                })

        # ------------------------------------------------------------------
        # F. Native GraphHopper config check (NO IMPORT)
        # ------------------------------------------------------------------
        print()
        print("F. NATIVE GRAPHHOPPER CONFIG CHECK — NO IMPORT")

        help_proc = subprocess.run(
            [str(java_exe), "-Xms128m", "-Xmx512m", "-jar", str(paths["gh_jar"]), "--help"],
            cwd=staging,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        help_text = help_proc.stdout or ""
        has_check = bool(re.search(r"(?im)^\s*check\b|\bcheck\s+config", help_text))
        print(f"JAR --help return code = {help_proc.returncode}")
        print(f"Dropwizard check command exposed = {'YES' if has_check else 'NO'}")

        if not has_check:
            raise RuntimeError(
                "GraphHopper JAR does not expose a recognizable safe 'check' command. "
                "Refusing to use 'server' because that could start graph import."
            )

        check_proc = subprocess.run(
            [
                str(java_exe),
                "-Xms128m",
                "-Xmx1g",
                "-jar",
                str(paths["gh_jar"]),
                "check",
                str(check_config_path),
            ],
            cwd=staging,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
        )
        check_text = check_proc.stdout or ""
        check_log_path = staging / CHECK_LOG_FILENAME
        check_log_path.write_text(check_text, encoding="utf-8")

        print(f"GraphHopper check return code = {check_proc.returncode}")
        if check_proc.returncode != 0:
            print(check_text[-6000:])
            raise RuntimeError("GraphHopper native config check failed")

        if check_graph.exists():
            raise RuntimeError(
                "Unexpected graph directory created by 'check'; refusing to proceed."
            )

        print("GRAPHHOPPER_NATIVE_CONFIG_CHECK = PASS")
        print("GRAPH_IMPORT_SIDE_EFFECT = NONE")

        # ------------------------------------------------------------------
        # G. Summary / manifest
        # ------------------------------------------------------------------
        print()
        print("G. SUMMARY / MANIFEST")

        summary = {
            "schema": "B1_EXT_GH_PROFILE_IMPORT_PREFLIGHT_SUMMARY_V01",
            "verdict": "PASS",
            "architecture": {
                "internal_router": "B5_FROZEN",
                "external_router": "GRAPHHOPPER_11",
                "profile": PROFILE_NAME,
                "cost": "STATIC_TIME",
                "distance_influence": 0,
                "turn_restrictions": ["motorcar", "motor_vehicle"],
                "u_turn_costs_s": 0,
                "profiles_ch": [],
                "profiles_lm": [],
                "graph_dataaccess": "MMAP",
            },
            "source": {
                "national_pbf": str(paths["italy_pbf"]),
                "national_pbf_sha256": EXPECTED["italy_pbf"][1],
            },
            "speed_contract": {
                "b5_caps_kmh": B5_SPEED_CAPS,
                "gh11_base_defaults_kmh": GH11_DEFAULT_SPEEDS,
                "compatibility_method": (
                    "GH car_average_speed -> class-specific upward compatibility factor "
                    "-> frozen B5 class cap -> exact max_speed cap when max_speed<150"
                ),
                "service_through_routing": "EXCLUDED",
            },
            "b2_core": {
                "classes": sorted(core_classes),
                "unexpected_classes": unexpected_core,
                "allowed_classes_absent": missing_expected,
            },
            "resources": {
                "ram_total_gib": total_ram,
                "ram_available_gib_at_preflight": avail_ram,
                "disk_free_gib_at_preflight": free_gib,
                "recommended_heap": f"-Xms1g -Xmx{recommended_heap_gib}g",
            },
            "native_check": {
                "command_exposed": has_check,
                "return_code": check_proc.returncode,
                "graph_side_effect": False,
            },
            "warnings": warnings,
            "hard_stop": {
                "graph_import": "NOT_STARTED",
                "routing": "NOT_STARTED",
                "frozen_artifacts_modified": False,
            },
            "next_gate": "HEAVY_GRAPHHOPPER_IMPORT",
        }
        summary_path = staging / SUMMARY_FILENAME
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        output_paths = [
            model_path,
            check_config_path,
            import_config_path,
            check_log_path,
            b2_audit_path,
            summary_path,
        ]

        manifest = {
            "schema": "B1_EXT_GH_PROFILE_IMPORT_PREFLIGHT_MANIFEST_V01",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                key: {
                    "path": str(paths[key]),
                    "sha256": expected,
                }
                for key, (_, expected) in EXPECTED.items()
            },
            "java": {
                "path": str(java_exe),
                "major": java_major,
                "version_output": java_version_text.strip(),
            },
            "outputs": [
                {
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "sha256": sha256(p),
                }
                for p in output_paths
            ],
            "future_graph_location": str(future_graph),
            "hard_stop": summary["hard_stop"],
            "next_gate": summary["next_gate"],
        }
        manifest_path = staging / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # Finalize additive evidence.
        staging.rename(final_dir)

        print(f"Final preflight package = {final_dir}")
        for name in [
            MODEL_FILENAME,
            CHECK_CONFIG_FILENAME,
            IMPORT_CONFIG_FILENAME,
            CHECK_LOG_FILENAME,
            B2_AUDIT_FILENAME,
            SUMMARY_FILENAME,
            MANIFEST_FILENAME,
        ]:
            p = final_dir / name
            print(f"{name} SHA256 = {sha256(p)}")

        # Final guardrails.
        if future_graph.exists():
            raise RuntimeError("Future graph location unexpectedly exists after preflight")

        print()
        print("=" * 124)
        print("B1_EXT_GH_04_PROFILE_IMPORT_PREFLIGHT = PASS")
        print(f"PROFILE = {PROFILE_NAME}")
        print("COST = STATIC_TIME")
        print("DISTANCE_INFLUENCE = 0")
        print("TURN_RESTRICTIONS = motorcar|motor_vehicle")
        print("U_TURN_COSTS_S = 0")
        print("SERVICE_THROUGH_ROUTING = EXCLUDED")
        print("GRAPH_DATAACCESS = MMAP")
        print("PROFILES_CH = DISABLED")
        print("PROFILES_LM = DISABLED")
        print(f"IMPORT_HEAP_CANDIDATE = -Xms1g -Xmx{recommended_heap_gib}g")
        print("GRAPHHOPPER_NATIVE_CONFIG_CHECK = PASS")
        print("GRAPH_IMPORT = NOT_STARTED")
        print("ROUTING = NOT_STARTED")
        print("FROZEN_ARTIFACTS_MODIFIED = NO")
        print("NEXT_GATE = HEAVY_GRAPHHOPPER_IMPORT")
        if warnings:
            print("WARNINGS = " + "|".join(warnings))
        else:
            print("WARNINGS = 0")
        print("=== RUN COMPLETATA ===")

        return 0

    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
