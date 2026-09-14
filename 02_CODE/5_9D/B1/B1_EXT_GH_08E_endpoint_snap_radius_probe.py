#!/usr/bin/env python3
"""
B1-EXT-GH 08E — TARGETED ENDPOINT SNAP RADIUS PROBE

Goal
----
Causally test the GH08 blocker on ONLY the 19 disconnected external
municipal destinations by loading the already-imported Italy graph with
a larger runtime LocationIndex search region.

The ONLY intended behavioral change relative to GH08 is:
    index.max_region_search: 64

Everything else remains:
- same GraphHopper 11 JAR
- same frozen profile/model
- same existing Italy graph
- same blank snap_prevention
- no PBF passed to server
- no import
- no B5 routing
- no change to GH08 outputs

The probe is diagnostic only. It DOES NOT authorize a final endpoint
connector rule or a final snap-distance threshold.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# --------------------------------------------------------------------------------------
# Frozen/evidence inputs
# --------------------------------------------------------------------------------------

GH08D_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_blocking_diagnostics_v01"
)
GH08D_DEST_NAME = "B1_EXT_GH_08D_unreachable_destinations_v01.csv"
GH08D_DEST_SHA256 = "9f7254562d6e92888e23183279badefc5439dfbb4fe6066efa0d9652aaea44a0"
GH08D_MANIFEST_NAME = "B1_EXT_GH_08D_blocking_diagnostics_manifest_v01.json"
GH08D_MANIFEST_SHA256 = "b3c401029ed31cbc557dbbe74a1c4ad2292904c60b80b28b58ae0e237a78e5f0"

GH08_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v01"
)
GH08_MANIFEST_NAME = "B1_EXT_GH_08_hybrid_routing_materialization_manifest_v01.json"
GH08_MANIFEST_SHA256 = "cc47279a8a47b9c69621d1ae71af12adfca48c230b21c0db434b465c8015512c"

GH07_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_runtime_preflight_v01"
)
GH07_MAPPING_NAME = "B1_EXT_GH_07_crossing_b5_mapping_v01.csv"
GH07_MAPPING_SHA256 = "57026868b57e29944d1234fad43078db2c0b15a565039d07a4c1d30ed20ce2cc"

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"

PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"

HEAVY_RUNS_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\heavy_import_runs"
)
EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"

EXPECTED_DESTINATIONS = 19
EXPECTED_CROSSINGS = 49
ANCHOR_GEO_ID = "GEO_0198"

# --------------------------------------------------------------------------------------
# Probe runtime
# --------------------------------------------------------------------------------------

APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 120
HTTP_WORKERS = 4

PROBE_MAX_REGION_SEARCH = 64

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_endpoint_snap_radius_probe_v01"
)
SERVER_CONFIG_NAME = "graphhopper_b1_ext_server_gh08e_v01.yml"
SERVER_LOG_NAME = "graphhopper_b1_ext_server_gh08e_v01.log"
RESULT_CSV = "B1_EXT_GH_08E_endpoint_snap_radius_probe_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_08E_endpoint_snap_radius_probe_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_08E_endpoint_snap_radius_probe_manifest_v01.json"


# ======================================================================================
# Generic helpers
# ======================================================================================

def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def strict_hash(label: str, path: Path, expected: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    ok = actual == expected.lower()
    print(f"{label:<28} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = list(reader.fieldnames or [])
    if not columns:
        raise RuntimeError(f"CSV has no header: {path}")
    return rows, columns


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("Cannot write empty result CSV")
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2.0) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    )
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def percentile_linear(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("empty values")
    if not (0 <= q <= 1):
        raise ValueError(q)
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def graph_inventory(graph_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(x for x in graph_dir.rglob("*") if x.is_file()):
        rows.append({
            "relative_path": p.relative_to(graph_dir).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return rows


def normalized_inventory(rows: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
    return sorted(
        (
            str(r["relative_path"]),
            int(r["size_bytes"]),
            str(r["sha256"]).lower(),
        )
        for r in rows
    )


def find_graph_manifest(root: Path) -> tuple[Path, dict[str, Any]]:
    runs_root = root / Path(HEAVY_RUNS_REL)
    if not runs_root.is_dir():
        raise FileNotFoundError(runs_root)
    candidates = sorted(runs_root.rglob("B1_EXT_GH_graph_file_manifest.json"))
    matches = [p for p in candidates if sha256(p) == EXPECTED_GRAPH_MANIFEST_SHA256]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one graph manifest with SHA256 "
            f"{EXPECTED_GRAPH_MANIFEST_SHA256}; found {len(matches)}"
        )
    path = matches[0]
    with path.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError("Invalid graph manifest JSON")
    return path, obj


def graph_manifest_rows(obj: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("files", "graph_files", "inventory"):
        rows = obj.get(key)
        if isinstance(rows, list):
            # normalize likely field aliases
            out = []
            for r in rows:
                if not isinstance(r, dict):
                    raise RuntimeError("Invalid graph manifest row")
                rel = (
                    r.get("relative_path")
                    or r.get("filename")
                    or r.get("name")
                    or r.get("path")
                )
                size = r.get("size_bytes")
                digest = r.get("sha256")
                if rel is None or size is None or digest is None:
                    raise RuntimeError(f"Cannot normalize graph manifest row: {r}")
                out.append({
                    "relative_path": str(rel).replace("\\", "/"),
                    "size_bytes": int(size),
                    "sha256": str(digest).lower(),
                })
            return out
    raise RuntimeError(f"Could not find graph file inventory in manifest keys={list(obj)}")


def find_java(runtime_root: Path) -> Path:
    candidates = sorted(runtime_root.rglob("java.exe"))
    candidates = [p for p in candidates if p.parent.name.lower() == "bin"]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one java.exe under {runtime_root}; got {candidates}")
    return candidates[0]


def helper_self_tests() -> None:
    d = haversine_m(13.0, 46.0, 13.0, 46.0)
    if abs(d) > 1e-9:
        raise AssertionError("haversine self-test")
    vals = [1.0, 2.0, 3.0, 4.0]
    if abs(percentile_linear(vals, 0.5) - 2.5) > 1e-12:
        raise AssertionError("percentile self-test")
    if normalized_inventory([
        {"relative_path": "b", "size_bytes": 2, "sha256": "bb"},
        {"relative_path": "a", "size_bytes": 1, "sha256": "aa"},
    ])[0][0] != "a":
        raise AssertionError("inventory self-test")


# ======================================================================================
# YAML/server helpers
# ======================================================================================

def replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if line.lstrip().startswith(key + ":")]
    if len(hits) != 1:
        raise RuntimeError(f"Expected exactly one '{key}:' line; found {len(hits)}")
    i = hits[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    escaped = value.replace("'", "''")
    lines[i] = f"{indent}{key}: '{escaped}'"
    return "\n".join(lines) + "\n"


def set_or_append_yaml_int(text: str, key: str, value: int) -> tuple[str, str]:
    # Active key only; commented examples do not count.
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if line.lstrip().startswith(key + ":")]
    if len(hits) > 1:
        raise RuntimeError(f"Multiple active '{key}:' lines")
    if len(hits) == 1:
        i = hits[0]
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        old = lines[i].strip()
        lines[i] = f"{indent}{key}: {int(value)}"
        return "\n".join(lines) + "\n", f"REPLACED [{old}]"
    # Root-level key is valid in GraphHopper config.
    lines.append(f"{key}: {int(value)}")
    return "\n".join(lines) + "\n", "APPENDED_NEW_ACTIVE_KEY"


def make_server_config(
    import_config: Path,
    graph_dir: Path,
    run_dir: Path,
) -> tuple[str, str]:
    text = import_config.read_text(encoding="utf-8")
    sentinel = run_dir / "__NO_IMPORT__" / "missing.osm.pbf"
    text = replace_yaml_scalar(
        text, "datareader.file", sentinel.resolve().as_posix()
    )
    text = replace_yaml_scalar(
        text, "graph.location", graph_dir.resolve().as_posix()
    )
    text, region_action = set_or_append_yaml_int(
        text, "index.max_region_search", PROBE_MAX_REGION_SEARCH
    )
    if re.search(r"(?m)^server:\s*$", text):
        raise RuntimeError("Candidate import config unexpectedly already contains server block")
    text += "\n".join([
        "",
        "server:",
        "  application_connectors:",
        "  - type: http",
        f"    port: {APP_PORT}",
        "    bind_host: localhost",
        "    max_request_header_size: 50k",
        "  request_log:",
        "      appenders: []",
        "  admin_connectors:",
        "  - type: http",
        f"    port: {ADMIN_PORT}",
        "    bind_host: localhost",
        "",
    ])
    return text, region_action


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for_server(proc: subprocess.Popen) -> None:
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"GraphHopper server exited early with code {proc.returncode}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", APP_PORT)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(f"GraphHopper server did not open port {APP_PORT}")


def stop_server(proc: subprocess.Popen | None) -> str:
    if proc is None:
        return "NOT_STARTED"
    if proc.poll() is not None:
        return f"ALREADY_EXITED_{proc.returncode}"
    proc.terminate()
    try:
        proc.wait(timeout=20)
        return f"TERMINATED_{proc.returncode}"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        return f"KILLED_{proc.returncode}"


# ======================================================================================
# Routing probe
# ======================================================================================

def route_request(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict[str, Any]:
    params = [
        ("point", f"{start_lat:.8f},{start_lon:.8f}"),
        ("point", f"{end_lat:.8f},{end_lon:.8f}"),
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "false"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
    ]
    url = f"http://127.0.0.1:{APP_PORT}/route?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-GH08E/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=ROUTE_TIMEOUT_S) as response:
            body = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        low = body.lower()
        if "cannot find point" in low:
            return {
                "status": "POINT_NOT_FOUND",
                "http_status": int(exc.code),
                "error": body[:1000],
            }
        if "no path" in low or "connection" in low or "not found" in low:
            return {
                "status": "NO_PATH",
                "http_status": int(exc.code),
                "error": body[:1000],
            }
        return {
            "status": "HTTP_ERROR",
            "http_status": int(exc.code),
            "error": body[:1000],
        }
    except Exception as exc:
        return {
            "status": "TECHNICAL_ERROR",
            "http_status": None,
            "error": repr(exc),
        }

    if status != 200:
        return {
            "status": "HTTP_ERROR",
            "http_status": status,
            "error": f"Unexpected HTTP status {status}",
        }

    try:
        data = json.loads(body)
        paths = data.get("paths", [])
        if not paths:
            return {
                "status": "NO_PATH",
                "http_status": 200,
                "error": "No route path",
            }
        path = paths[0]
        coords = path.get("snapped_waypoints", {}).get("coordinates", [])
        if len(coords) != 2:
            return {
                "status": "TECHNICAL_ERROR",
                "http_status": 200,
                "error": f"Expected two snapped_waypoints; got {coords}",
            }
        snap_start_lon, snap_start_lat = map(float, coords[0][:2])
        snap_end_lon, snap_end_lat = map(float, coords[1][:2])
        return {
            "status": "PASS",
            "http_status": 200,
            "time_s": int(path["time"]) / 1000.0,
            "distance_m": float(path["distance"]),
            "weight": float(path["weight"]),
            "snap_start_lon": snap_start_lon,
            "snap_start_lat": snap_start_lat,
            "snap_end_lon": snap_end_lon,
            "snap_end_lat": snap_end_lat,
            "snap_start_m": haversine_m(
                start_lon, start_lat, snap_start_lon, snap_start_lat
            ),
            "snap_end_m": haversine_m(
                end_lon, end_lat, snap_end_lon, snap_end_lat
            ),
            "error": "",
        }
    except Exception as exc:
        return {
            "status": "TECHNICAL_ERROR",
            "http_status": 200,
            "error": repr(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_08E_HELPER_SELF_TESTS = PASS")
        return 0

    root = Path(args.root)
    gh08d_dir = root / Path(GH08D_DIR_REL)
    gh08_dir = root / Path(GH08_DIR_REL)
    gh07_dir = root / Path(GH07_DIR_REL)
    graph_dir = root / Path(FINAL_GRAPH_REL)
    gh_jar = root / Path(GH_JAR_REL)
    runtime_root = root / Path(RUNTIME_REL)
    profile_config = root / Path(PROFILE_CONFIG_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 08E — TARGETED ENDPOINT SNAP RADIUS PROBE")
    print("=" * 124)
    print("19 GH08 DISCONNECTED DESTINATIONS / EXISTING GRAPH ONLY / NO PBF IMPORT / NO B5")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    gh08d_dest = gh08d_dir / GH08D_DEST_NAME
    gh08d_manifest = gh08d_dir / GH08D_MANIFEST_NAME
    gh08_manifest = gh08_dir / GH08_MANIFEST_NAME
    gh07_mapping = gh07_dir / GH07_MAPPING_NAME

    print("A. STRICT EVIDENCE / GRAPH IDENTITY")
    strict_hash("GH08D destinations", gh08d_dest, GH08D_DEST_SHA256)
    strict_hash("GH08D manifest", gh08d_manifest, GH08D_MANIFEST_SHA256)
    strict_hash("GH08 manifest", gh08_manifest, GH08_MANIFEST_SHA256)
    strict_hash("GH07 mapping", gh07_mapping, GH07_MAPPING_SHA256)
    strict_hash("GH JAR", gh_jar, GH_JAR_SHA256)
    strict_hash("profile config", profile_config, PROFILE_CONFIG_SHA256)

    graph_manifest_path, graph_manifest_obj = find_graph_manifest(root)
    expected_graph_rows = graph_manifest_rows(graph_manifest_obj)
    graph_before = graph_inventory(graph_dir)
    if normalized_inventory(graph_before) != normalized_inventory(expected_graph_rows):
        raise RuntimeError("Existing Italy graph differs from frozen graph manifest")
    print(f"graph manifest             PASS  {sha256(graph_manifest_path)}")
    print(f"graph files                = {len(graph_before)}")
    print(f"graph size GiB             = {sum(r['size_bytes'] for r in graph_before)/(1024**3):.3f}")
    print("helper self-tests          PASS")

    print()
    print("B. TARGET SET / CONTROLLED ANCHOR")
    dest_rows, dest_cols = read_csv(gh08d_dest)
    required_dest = {
        "destination_key",
        "dest_code_raw",
        "dest_code_join",
        "dest_COMUNE",
        "dest_lon",
        "dest_lat",
        "b1_rows",
        "Pendolari_raw_sum",
        "flow_daily_sum",
    }
    missing = required_dest - set(dest_cols)
    if missing:
        raise RuntimeError(f"GH08D destinations CSV missing fields: {sorted(missing)}")
    if len(dest_rows) != EXPECTED_DESTINATIONS:
        raise RuntimeError(
            f"Disconnected destination count {len(dest_rows)} != {EXPECTED_DESTINATIONS}"
        )

    mapping_rows, mapping_cols = read_csv(gh07_mapping)
    if len(mapping_rows) != EXPECTED_CROSSINGS:
        raise RuntimeError(f"GH07 crossing rows {len(mapping_rows)} != {EXPECTED_CROSSINGS}")
    anchor_matches = [r for r in mapping_rows if r.get("geo_id") == ANCHOR_GEO_ID]
    if len(anchor_matches) != 1:
        raise RuntimeError(f"Expected one {ANCHOR_GEO_ID}, got {len(anchor_matches)}")
    anchor = anchor_matches[0]
    anchor_lon = float(anchor["best_anchor_lon"])
    anchor_lat = float(anchor["best_anchor_lat"])
    print(f"disconnected destinations = {len(dest_rows)}")
    print(f"probe anchor              = {ANCHOR_GEO_ID} / {anchor['gateway_id']}")
    print(f"anchor lon/lat            = {anchor_lon:.8f}, {anchor_lat:.8f}")

    print()
    print("C. SAFE EXISTING-GRAPH SERVER WITH EXTENDED LOCATION INDEX SEARCH")
    if not port_is_free(APP_PORT):
        raise RuntimeError(f"Application port {APP_PORT} already in use")
    if not port_is_free(ADMIN_PORT):
        raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")

    staging.mkdir(parents=True, exist_ok=False)
    server_config_path = staging / SERVER_CONFIG_NAME
    server_text, region_action = make_server_config(
        profile_config, graph_dir, staging
    )
    server_config_path.write_text(server_text, encoding="utf-8")
    print(f"index.max_region_search   = {PROBE_MAX_REGION_SEARCH}")
    print(f"config action             = {region_action}")
    print("snap_prevention           = BLANK")
    print("national PBF passed       = NO")
    print("bind host                 = localhost")

    java_exe = find_java(runtime_root)
    server_log_path = staging / SERVER_LOG_NAME
    server_log_handle = server_log_path.open(
        "w", encoding="utf-8", errors="replace"
    )
    cmd = [
        str(java_exe),
        f"-Xms{SERVER_XMS_MIB}m",
        f"-Xmx{SERVER_XMX_GIB}g",
        "-XX:+UseParallelGC",
        "-jar",
        str(gh_jar),
        "server",
        str(server_config_path),
    ]

    proc: subprocess.Popen | None = None
    results: list[dict[str, Any]] = []
    shutdown_status = "NOT_STARTED"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=staging,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_server(proc)
        print("SERVER_LOAD                = PASS")

        print()
        print("D. TARGETED 19 x 2 DIRECTION PROBE")
        tasks = []
        for d in dest_rows:
            dest_lat = float(d["dest_lat"])
            dest_lon = float(d["dest_lon"])
            tasks.append((d, "IE", anchor_lat, anchor_lon, dest_lat, dest_lon))
            tasks.append((d, "EI", dest_lat, dest_lon, anchor_lat, anchor_lon))

        with ThreadPoolExecutor(max_workers=HTTP_WORKERS) as pool:
            futures = {}
            for d, direction, slat, slon, elat, elon in tasks:
                fut = pool.submit(route_request, slat, slon, elat, elon)
                futures[fut] = (d, direction, slat, slon, elat, elon)

            completed = 0
            for fut in as_completed(futures):
                d, direction, slat, slon, elat, elon = futures[fut]
                r = fut.result()
                if direction == "IE":
                    destination_snap_m = r.get("snap_end_m")
                    snap_lon = r.get("snap_end_lon")
                    snap_lat = r.get("snap_end_lat")
                    crossing_snap_m = r.get("snap_start_m")
                else:
                    destination_snap_m = r.get("snap_start_m")
                    snap_lon = r.get("snap_start_lon")
                    snap_lat = r.get("snap_start_lat")
                    crossing_snap_m = r.get("snap_end_m")
                row = {
                    "destination_key": d["destination_key"],
                    "dest_code_raw": d["dest_code_raw"],
                    "dest_code_join": d["dest_code_join"],
                    "dest_COMUNE": d["dest_COMUNE"],
                    "dest_lon": float(d["dest_lon"]),
                    "dest_lat": float(d["dest_lat"]),
                    "b1_rows": int(float(d["b1_rows"])),
                    "Pendolari_raw_sum": float(d["Pendolari_raw_sum"]),
                    "flow_daily_sum": float(d["flow_daily_sum"]),
                    "direction": direction,
                    "probe_anchor_geo_id": ANCHOR_GEO_ID,
                    "probe_anchor_gateway_id": anchor["gateway_id"],
                    "max_region_search": PROBE_MAX_REGION_SEARCH,
                    "route_status": r["status"],
                    "http_status": r.get("http_status"),
                    "route_time_s": r.get("time_s"),
                    "route_distance_m": r.get("distance_m"),
                    "crossing_snap_m": crossing_snap_m,
                    "destination_snap_m": destination_snap_m,
                    "snapped_destination_lon": snap_lon,
                    "snapped_destination_lat": snap_lat,
                    "error": r.get("error", ""),
                }
                results.append(row)
                completed += 1
                print(
                    f"  {completed:02d}/{len(tasks)} "
                    f"{direction} {d['dest_COMUNE']:<34} "
                    f"{r['status']}"
                    + (
                        f" dest_snap={float(destination_snap_m):.1f} m"
                        if destination_snap_m is not None
                        else ""
                    )
                )

    finally:
        shutdown_status = stop_server(proc)
        server_log_handle.close()

    results.sort(
        key=lambda r: (str(r["dest_COMUNE"]), str(r["destination_key"]), str(r["direction"]))
    )

    print()
    print("E. SHUTDOWN / BYTE-INTEGRITY")
    print(f"server shutdown            = {shutdown_status}")
    graph_after = graph_inventory(graph_dir)
    graph_unchanged = normalized_inventory(graph_after) == normalized_inventory(graph_before)
    print(f"Italy graph unchanged      = {'PASS' if graph_unchanged else 'FAIL'}")
    if not graph_unchanged:
        raise RuntimeError("Italy graph byte identity changed during probe")

    # Aggregate per destination.
    by_dest: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_dest.setdefault(str(r["destination_key"]), []).append(r)

    pass_both = 0
    point_not_found_any = 0
    no_path_any = 0
    technical_any = 0
    snap_values: list[float] = []
    destination_summary: list[dict[str, Any]] = []

    for key, rows in sorted(by_dest.items()):
        if len(rows) != 2:
            raise RuntimeError(f"{key}: expected 2 probe rows")
        statuses = {str(r["direction"]): str(r["route_status"]) for r in rows}
        both = statuses.get("IE") == "PASS" and statuses.get("EI") == "PASS"
        if both:
            pass_both += 1
        if "POINT_NOT_FOUND" in statuses.values():
            point_not_found_any += 1
        if "NO_PATH" in statuses.values():
            no_path_any += 1
        if any(s in {"HTTP_ERROR", "TECHNICAL_ERROR"} for s in statuses.values()):
            technical_any += 1
        snaps = [
            float(r["destination_snap_m"])
            for r in rows
            if r["destination_snap_m"] is not None
        ]
        snap_values.extend(snaps)
        base = rows[0]
        destination_summary.append({
            "destination_key": key,
            "dest_COMUNE": base["dest_COMUNE"],
            "Pendolari_raw_sum": base["Pendolari_raw_sum"],
            "b1_rows": base["b1_rows"],
            "IE_status": statuses.get("IE"),
            "EI_status": statuses.get("EI"),
            "IE_destination_snap_m": next(
                (r["destination_snap_m"] for r in rows if r["direction"] == "IE"),
                None,
            ),
            "EI_destination_snap_m": next(
                (r["destination_snap_m"] for r in rows if r["direction"] == "EI"),
                None,
            ),
            "max_destination_snap_m": max(snaps) if snaps else None,
        })

    all_resolved = (
        pass_both == EXPECTED_DESTINATIONS
        and point_not_found_any == 0
        and no_path_any == 0
        and technical_any == 0
    )

    if snap_values:
        snap_max = max(snap_values)
        snap_med = median(snap_values)
        snap_p95 = percentile_linear(snap_values, 0.95)
    else:
        snap_max = snap_med = snap_p95 = None

    print()
    print("F. CAUSAL CLASSIFICATION")
    print(f"destinations PASS both dir = {pass_both}/{EXPECTED_DESTINATIONS}")
    print(f"POINT_NOT_FOUND remaining  = {point_not_found_any}")
    print(f"NO_PATH remaining          = {no_path_any}")
    print(f"technical failures         = {technical_any}")
    if snap_values:
        print(f"destination snap median m  = {snap_med:.3f}")
        print(f"destination snap p95 m     = {snap_p95:.3f}")
        print(f"destination snap max m     = {snap_max:.3f}")

    if all_resolved:
        verdict = "PASS"
        cause = "LOCATION_INDEX_SEARCH_RADIUS_LIMIT"
        next_gate = "DEFINE_CONTROLLED_EXTERNAL_ENDPOINT_CONNECTOR_RULE"
    else:
        verdict = "NOT_READY"
        cause = "MIXED_OR_UNRESOLVED"
        next_gate = "REVIEW_GH08E_REMAINING_ENDPOINT_FAILURES"

    result_path = staging / RESULT_CSV
    write_csv(result_path, results)

    summary = {
        "schema": "B1_EXT_GH_08E_ENDPOINT_SNAP_RADIUS_PROBE_SUMMARY_V01",
        "verdict": verdict,
        "cause_classification": cause,
        "probe_change_only": {
            "index.max_region_search": PROBE_MAX_REGION_SEARCH,
            "snap_prevention": "BLANK",
            "same_existing_graph": True,
            "same_profile": PROFILE_NAME,
            "pbf_passed_to_server": False,
        },
        "destinations_tested": EXPECTED_DESTINATIONS,
        "directions_tested": 2,
        "routes_attempted": len(results),
        "destinations_pass_both_directions": pass_both,
        "destinations_with_point_not_found": point_not_found_any,
        "destinations_with_no_path": no_path_any,
        "destinations_with_technical_failure": technical_any,
        "destination_snap_m": {
            "median": snap_med,
            "p95": snap_p95,
            "max": snap_max,
        },
        "destination_results": destination_summary,
        "graph_byte_identical_after_probe": graph_unchanged,
        "methodological_guardrail": (
            "This probe diagnoses the mechanism only. It does not freeze a final "
            "snap threshold or authorize use of arbitrarily distant centroid connectors."
        ),
        "next_gate": next_gate,
    }
    summary_path = staging / SUMMARY_JSON
    write_json(summary_path, summary)

    manifest = {
        "schema": "B1_EXT_GH_08E_ENDPOINT_SNAP_RADIUS_PROBE_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "inputs": {
            GH08D_DEST_NAME: sha256(gh08d_dest),
            GH08D_MANIFEST_NAME: sha256(gh08d_manifest),
            GH08_MANIFEST_NAME: sha256(gh08_manifest),
            GH07_MAPPING_NAME: sha256(gh07_mapping),
            Path(GH_JAR_REL).name: sha256(gh_jar),
            Path(PROFILE_CONFIG_REL).name: sha256(profile_config),
            graph_manifest_path.name: sha256(graph_manifest_path),
        },
        "outputs": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in (server_config_path, server_log_path, result_path, summary_path)
        ],
        "graph_before": graph_before,
        "graph_after_identical": graph_unchanged,
        "next_gate": next_gate,
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    # Promote only after all outputs and integrity checks are complete.
    staging.rename(final_dir)

    print()
    print("=" * 124)
    print(f"B1_EXT_GH_08E_ENDPOINT_SNAP_RADIUS_PROBE = {verdict}")
    print(f"CAUSE_CLASSIFICATION = {cause}")
    print(f"PROBE_MAX_REGION_SEARCH = {PROBE_MAX_REGION_SEARCH}")
    print(f"DESTINATIONS_TESTED = {EXPECTED_DESTINATIONS}")
    print(f"DESTINATIONS_PASS_BOTH_DIRECTIONS = {pass_both}/{EXPECTED_DESTINATIONS}")
    print(f"POINT_NOT_FOUND_REMAINING = {point_not_found_any}")
    print(f"NO_PATH_REMAINING = {no_path_any}")
    print(f"TECHNICAL_FAILURES = {technical_any}")
    if snap_values:
        print(f"DESTINATION_SNAP_MEDIAN_M = {snap_med:.3f}")
        print(f"DESTINATION_SNAP_P95_M = {snap_p95:.3f}")
        print(f"DESTINATION_SNAP_MAX_M = {snap_max:.3f}")
    print("PBF_IMPORT = NOT_STARTED")
    print("B5_ROUTING = NOT_STARTED")
    print(f"ITALY_GRAPH_BYTE_IDENTICAL_AFTER_PROBE = {'YES' if graph_unchanged else 'NO'}")
    print("GH08_OUTPUTS_MODIFIED = NO")
    print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
    print(f"NEXT_GATE = {next_gate}")
    print(f"{RESULT_CSV} SHA256 = {sha256(final_dir / RESULT_CSV)}")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print("=== RUN COMPLETATA ===")

    print()
    print("DESTINATION SNAP RESULTS")
    for r in sorted(
        destination_summary,
        key=lambda x: (
            -(float(x["max_destination_snap_m"]) if x["max_destination_snap_m"] is not None else -1),
            str(x["dest_COMUNE"]),
        ),
    ):
        snap = r["max_destination_snap_m"]
        snap_txt = f"{float(snap):9.1f} m" if snap is not None else "       NA"
        print(
            f"  {str(r['dest_COMUNE']):<35} "
            f"IE={r['IE_status']:<16} EI={r['EI_status']:<16} "
            f"max_snap={snap_txt} raw={float(r['Pendolari_raw_sum']):7.1f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
