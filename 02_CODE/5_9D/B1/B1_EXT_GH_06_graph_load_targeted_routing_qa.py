#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer

# ======================================================================================
# B1-EXT-GH 06 — GRAPH LOAD + TARGETED EXTERNAL ROUTING QA
#
# Existing imported graph only.
# No PBF import.
# No full B1 routing.
# No B5 routing.
# No gateway assignment.
# ======================================================================================

ROOT_DEFAULT = r"C:\Tesi"

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 60

FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"

GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"

PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"

PROFILE_MODEL_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\b1_ext_car_b5_compat_v01.json"
)
PROFILE_MODEL_SHA256 = "29ad0a3a425b43b039c52d1013d0706894d842120995ed607f57406a1f01ea79"

GEO_AUDIT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_topology_scan_v01\B1_EXT_shared_boundary_geo_audit_v01.csv"
)
GEO_AUDIT_SHA256 = "281d116da9b86374e1e4add02d72255a9db11fa70cc70a06265c5e7f1326a2bd"

BASE_GPKG_REL = r"Tesi_QGIS\02_package\base_territoriale_fvg.gpkg"
B1_TABLE = "pendolari_extra_regione_fvg_2021_od_xy"
EXPECTED_B1_ROWS = 2895

HEAVY_RUNS_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\heavy_import_runs"
)
EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\graph_load_targeted_routing_qa_v01"
)

ROUTE_CSV = "B1_EXT_GH_targeted_route_qa_v01.csv"
ANCHOR_CSV = "B1_EXT_GH_gateway_anchor_selection_v01.csv"
DEST_CSV = "B1_EXT_GH_targeted_destinations_v01.csv"
SERVER_CONFIG = "graphhopper_b1_ext_server_qa_v01.yml"
SERVER_LOG = "graphhopper_b1_ext_server_qa_v01.log"
SUMMARY_JSON = "B1_EXT_GH_graph_load_targeted_routing_qa_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_graph_load_targeted_routing_qa_manifest_v01.json"

MAX_GATEWAY_SNAP_M = 5.0
MAX_DESTINATION_SNAP_M = 10_000.0


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def write_json(path: Path, obj: object) -> None:
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
        text = proc.stdout or ""
        match = re.search(r'version\s+"?(\d+)', text)
        if match and int(match.group(1)) >= 17:
            return java
    raise RuntimeError(f"No Java >=17 found under {runtime_root}")


def graph_inventory(graph_dir: Path) -> list[dict]:
    rows = []
    for p in sorted(x for x in graph_dir.rglob("*") if x.is_file()):
        rows.append({
            "relative_path": p.relative_to(graph_dir).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return rows


def normalized_inventory(rows: list[dict]) -> list[tuple[str, int, str]]:
    return sorted(
        (
            str(r["relative_path"]),
            int(r["size_bytes"]),
            str(r["sha256"]).lower(),
        )
        for r in rows
    )


def find_graph_manifest(root: Path) -> tuple[Path, dict]:
    runs_root = root / Path(HEAVY_RUNS_REL)
    if not runs_root.is_dir():
        raise FileNotFoundError(runs_root)

    candidates = sorted(
        runs_root.rglob("B1_EXT_GH_graph_file_manifest.json")
    )
    matches = [
        p for p in candidates
        if sha256(p) == EXPECTED_GRAPH_MANIFEST_SHA256
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one graph manifest with frozen SHA256; "
            f"found {len(matches)}"
        )

    path = matches[0]
    with path.open("r", encoding="utf-8-sig") as f:
        return path, json.load(f)


def ci_column(columns: list[str], candidates: list[str]) -> str | None:
    lookup = {c.lower(): c for c in columns}
    for candidate in candidates:
        hit = lookup.get(candidate.lower())
        if hit is not None:
            return hit
    return None


def load_top_destinations(
    gpkg: Path,
    top_n: int = 3,
) -> tuple[list[dict], dict]:
    uri = gpkg.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        columns = [
            row[1]
            for row in con.execute(
                f'PRAGMA table_info("{B1_TABLE}")'
            )
        ]
        if not columns:
            raise RuntimeError(f"Missing B1 table: {B1_TABLE}")

        row_count = int(
            con.execute(
                f'SELECT COUNT(*) FROM "{B1_TABLE}"'
            ).fetchone()[0]
        )
        if row_count != EXPECTED_B1_ROWS:
            raise RuntimeError(
                f"B1 row count {row_count} != expected {EXPECTED_B1_ROWS}"
            )

        dest_name = ci_column(columns, ["dest_COMUNE"])
        dest_x = ci_column(columns, ["dest_xcoord"])
        dest_y = ci_column(columns, ["dest_ycoord"])
        flow = ci_column(columns, ["Pendolari_uscita", "Pendolari"])

        if any(x is None for x in (dest_name, dest_x, dest_y, flow)):
            raise RuntimeError(
                "Required B1 destination/flow fields not found. "
                f"Actual columns: {columns}"
            )

        sql = (
            f'SELECT "{dest_name}" AS destination, '
            f'CAST("{dest_x}" AS REAL) AS x, '
            f'CAST("{dest_y}" AS REAL) AS y, '
            f'SUM(CAST("{flow}" AS REAL)) AS commuters, '
            f'COUNT(*) AS od_rows '
            f'FROM "{B1_TABLE}" '
            f'WHERE CAST("{flow}" AS REAL) > 0 '
            f'AND "{dest_x}" IS NOT NULL '
            f'AND "{dest_y}" IS NOT NULL '
            f'GROUP BY "{dest_name}", "{dest_x}", "{dest_y}" '
            f'ORDER BY commuters DESC, destination ASC '
            f'LIMIT ?'
        )

        rows = con.execute(sql, (top_n,)).fetchall()
        if len(rows) != top_n:
            raise RuntimeError(
                f"Expected {top_n} sampled destinations, got {len(rows)}"
            )

        transformer = Transformer.from_crs(
            "EPSG:32632",
            "EPSG:4326",
            always_xy=True,
        )

        destinations = []
        for rank, row in enumerate(rows, start=1):
            name, x, y, commuters, od_rows = row
            lon, lat = transformer.transform(float(x), float(y))
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise RuntimeError(
                    f"Invalid transformed coordinate for destination {name}"
                )
            destinations.append({
                "rank": rank,
                "destination": str(name),
                "x_epsg32632": float(x),
                "y_epsg32632": float(y),
                "lon": float(lon),
                "lat": float(lat),
                "commuters_sum": float(commuters),
                "od_rows": int(od_rows),
            })

        metadata = {
            "row_count": row_count,
            "columns": columns,
            "flow_field": flow,
            "destination_name_field": dest_name,
            "destination_x_field": dest_x,
            "destination_y_field": dest_y,
            "source_crs": "EPSG:32632",
            "route_crs": "EPSG:4326",
        }
        return destinations, metadata
    finally:
        con.close()


def load_gateway_anchors(geo_audit: Path) -> list[dict]:
    with geo_audit.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    required = {
        "gateway_id",
        "geo_id",
        "best_anchor_lon",
        "best_anchor_lat",
        "best_anchor_distance_m",
        "status",
    }
    if not rows:
        raise RuntimeError("GEO audit is empty")
    missing = required - set(rows[0])
    if missing:
        raise RuntimeError(
            f"GEO audit missing columns: {sorted(missing)}"
        )

    by_gateway: dict[str, list[dict]] = {}
    for row in rows:
        if row["status"] != "SHARED_EXACT_B2_CORE_ANCHOR":
            continue
        by_gateway.setdefault(row["gateway_id"], []).append(row)

    anchors = []
    for gateway in sorted(by_gateway):
        candidates = sorted(
            by_gateway[gateway],
            key=lambda r: (
                float(r["best_anchor_distance_m"]),
                r["geo_id"],
            ),
        )
        chosen = candidates[0]
        anchors.append({
            "gateway_id": gateway,
            "geo_id": chosen["geo_id"],
            "lon": float(chosen["best_anchor_lon"]),
            "lat": float(chosen["best_anchor_lat"]),
            "a0_to_anchor_m": float(chosen["best_anchor_distance_m"]),
            "eligible_geo_count": len(candidates),
        })

    if len(anchors) != 12:
        raise RuntimeError(
            f"Expected 12 Veneto gateway anchors, got {len(anchors)}"
        )
    return anchors


def replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    hits = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith(key + ":")
    ]
    if len(hits) != 1:
        raise RuntimeError(
            f"Expected exactly one '{key}:' line; found {len(hits)}"
        )

    i = hits[0]
    indent_len = len(lines[i]) - len(lines[i].lstrip())
    indent = lines[i][:indent_len]
    escaped = value.replace("'", "''")
    lines[i] = f"{indent}{key}: '{escaped}'"
    return "\n".join(lines) + "\n"


def make_server_config(
    import_config: Path,
    graph_dir: Path,
    run_dir: Path,
) -> str:
    text = import_config.read_text(encoding="utf-8")

    sentinel = run_dir / "__NO_IMPORT__" / "missing.osm.pbf"
    text = replace_yaml_scalar(
        text,
        "datareader.file",
        sentinel.resolve().as_posix(),
    )
    text = replace_yaml_scalar(
        text,
        "graph.location",
        graph_dir.resolve().as_posix(),
    )

    if re.search(r"(?m)^server:\s*$", text):
        raise RuntimeError(
            "Candidate import config unexpectedly already contains server block"
        )

    server_lines = [
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
    ]
    return text + "\n".join(server_lines)


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for_server(proc: subprocess.Popen) -> None:
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"GraphHopper server exited early with code {proc.returncode}"
            )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", APP_PORT)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(
        f"GraphHopper server did not open port {APP_PORT} "
        f"within {SERVER_START_TIMEOUT_S}s"
    )


def route_request(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> dict:
    params = [
        ("point", f"{start_lat:.8f},{start_lon:.8f}"),
        ("point", f"{end_lat:.8f},{end_lon:.8f}"),
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "false"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
    ]
    query = urllib.parse.urlencode(params)
    url = f"http://127.0.0.1:{APP_PORT}/route?{query}"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-QA/1.0"},
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=ROUTE_TIMEOUT_S,
        ) as response:
            body = response.read().decode("utf-8")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GraphHopper HTTP {exc.code}: {body[:2000]}"
        ) from exc

    if status != 200:
        raise RuntimeError(f"Unexpected HTTP status: {status}")

    data = json.loads(body)
    paths = data.get("paths", [])
    if not paths:
        raise RuntimeError(f"No route path in response: {data}")

    path = paths[0]
    snapped = path.get("snapped_waypoints", {})
    coordinates = snapped.get("coordinates", [])

    if len(coordinates) != 2:
        raise RuntimeError(
            f"Expected two snapped waypoints, got {coordinates}"
        )

    snap_start_lon, snap_start_lat = map(float, coordinates[0][:2])
    snap_end_lon, snap_end_lat = map(float, coordinates[1][:2])

    return {
        "distance_m": float(path["distance"]),
        "time_s": int(path["time"]) / 1000.0,
        "weight": float(path["weight"]),
        "snap_start_m": haversine_m(
            start_lon,
            start_lat,
            snap_start_lon,
            snap_start_lat,
        ),
        "snap_end_m": haversine_m(
            end_lon,
            end_lat,
            snap_end_lon,
            snap_end_lat,
        ),
    }


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    args = parser.parse_args()

    root = Path(args.root)

    final_graph = root / Path(FINAL_GRAPH_REL)
    gh_jar = root / Path(GH_JAR_REL)
    import_config = root / Path(PROFILE_CONFIG_REL)
    profile_model = root / Path(PROFILE_MODEL_REL)
    geo_audit = root / Path(GEO_AUDIT_REL)
    base_gpkg = root / Path(BASE_GPKG_REL)
    runtime_root = (
        root
        / r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"
    )

    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name
        + "_STAGING_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 06 — GRAPH LOAD + TARGETED EXTERNAL ROUTING QA")
    print("=" * 124)
    print(
        "EXISTING GRAPH LOAD ONLY / NO PBF IMPORT / "
        "NO FULL B1 ROUTING"
    )
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(
            f"Unexpected staging exists: {staging}"
        )

    proc = None
    server_log_handle = None

    try:
        # ------------------------------------------------------------------
        # A. Identities and imported-graph byte manifest
        # ------------------------------------------------------------------
        print("A. STRICT INPUT / GRAPH IDENTITY")

        fixed_checks = [
            ("gh_jar", gh_jar, GH_JAR_SHA256),
            (
                "profile_config",
                import_config,
                PROFILE_CONFIG_SHA256,
            ),
            (
                "profile_model",
                profile_model,
                PROFILE_MODEL_SHA256,
            ),
            ("geo_audit", geo_audit, GEO_AUDIT_SHA256),
        ]

        for name, path, expected in fixed_checks:
            if not path.is_file():
                raise FileNotFoundError(path)
            actual = sha256(path)
            ok = actual == expected
            print(
                f"{name:<20} "
                f"{'PASS' if ok else 'FAIL':<5} "
                f"{actual}"
            )
            if not ok:
                raise RuntimeError(
                    f"SHA256 mismatch: {name}"
                )

        if not final_graph.is_dir():
            raise FileNotFoundError(final_graph)
        if not base_gpkg.is_file():
            raise FileNotFoundError(base_gpkg)

        graph_manifest_path, graph_manifest = find_graph_manifest(root)
        graph_before = graph_inventory(final_graph)

        graph_manifest_ok = (
            normalized_inventory(graph_before)
            == normalized_inventory(
                graph_manifest.get("files", [])
            )
        )

        graph_size_bytes = sum(
            row["size_bytes"] for row in graph_before
        )

        print(
            f"graph manifest hash = "
            f"{sha256(graph_manifest_path)}"
        )
        print(f"graph files         = {len(graph_before)}")
        print(
            f"graph size GiB      = "
            f"{graph_size_bytes / (1024**3):.3f}"
        )
        print(
            f"graph manifest      = "
            f"{'PASS' if graph_manifest_ok else 'FAIL'}"
        )

        if not graph_manifest_ok:
            raise RuntimeError(
                "Imported graph differs from frozen graph manifest"
            )

        # ------------------------------------------------------------------
        # B. Endpoint sample
        # ------------------------------------------------------------------
        print()
        print("B. TARGET ENDPOINT SELECTION")

        anchors = load_gateway_anchors(geo_audit)
        destinations, b1_meta = load_top_destinations(
            base_gpkg,
            top_n=3,
        )

        print(f"gateway anchors = {len(anchors)}")
        print(f"B1 rows         = {b1_meta['row_count']}")
        print(f"B1 flow field   = {b1_meta['flow_field']}")
        print("top external destinations:")
        for destination in destinations:
            print(
                f"  rank={destination['rank']} "
                f"{destination['destination']} "
                f"commuters={destination['commuters_sum']:g} "
                f"lon={destination['lon']:.6f} "
                f"lat={destination['lat']:.6f}"
            )

        # ------------------------------------------------------------------
        # C. Existing-graph server start
        # ------------------------------------------------------------------
        print()
        print("C. SAFE EXISTING-GRAPH SERVER START")

        if not port_is_free(APP_PORT):
            raise RuntimeError(
                f"Application port {APP_PORT} already in use"
            )
        if not port_is_free(ADMIN_PORT):
            raise RuntimeError(
                f"Admin port {ADMIN_PORT} already in use"
            )

        java_exe = find_java(runtime_root)

        print(f"Java = {java_exe}")
        print(f"application port = {APP_PORT}")
        print(f"admin port       = {ADMIN_PORT}")
        print("bind host        = localhost")
        print("datareader.file  = GUARANTEED-MISSING SENTINEL")
        print("national PBF passed to server = NO")

        staging.mkdir(parents=True, exist_ok=False)

        server_config_path = staging / SERVER_CONFIG
        server_config_path.write_text(
            make_server_config(
                import_config,
                final_graph,
                staging,
            ),
            encoding="utf-8",
        )

        anchor_csv_path = staging / ANCHOR_CSV
        with anchor_csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(anchors[0].keys()),
            )
            writer.writeheader()
            writer.writerows(anchors)

        dest_csv_path = staging / DEST_CSV
        with dest_csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(destinations[0].keys()),
            )
            writer.writeheader()
            writer.writerows(destinations)

        server_log_path = staging / SERVER_LOG
        server_log_handle = server_log_path.open(
            "w",
            encoding="utf-8",
            errors="replace",
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

        proc = subprocess.Popen(
            cmd,
            cwd=staging,
            stdout=server_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

        wait_for_server(proc)
        print("SERVER_LOAD = PASS")

        # ------------------------------------------------------------------
        # D. 12 gateways x 3 destinations x 2 directions
        # ------------------------------------------------------------------
        print()
        print("D. TARGETED DIRECTED ROUTES")

        route_rows = []
        errors = []

        for anchor in anchors:
            for destination in destinations:
                directions = (
                    "GATEWAY_TO_DEST",
                    "DEST_TO_GATEWAY",
                )

                for direction in directions:
                    if direction == "GATEWAY_TO_DEST":
                        start_lat = anchor["lat"]
                        start_lon = anchor["lon"]
                        end_lat = destination["lat"]
                        end_lon = destination["lon"]
                    else:
                        start_lat = destination["lat"]
                        start_lon = destination["lon"]
                        end_lat = anchor["lat"]
                        end_lon = anchor["lon"]

                    try:
                        result = route_request(
                            start_lat,
                            start_lon,
                            end_lat,
                            end_lon,
                        )

                        if direction == "GATEWAY_TO_DEST":
                            gateway_snap_m = result["snap_start_m"]
                            destination_snap_m = result["snap_end_m"]
                        else:
                            gateway_snap_m = result["snap_end_m"]
                            destination_snap_m = result["snap_start_m"]

                        finite_positive = (
                            math.isfinite(result["distance_m"])
                            and math.isfinite(result["time_s"])
                            and math.isfinite(result["weight"])
                            and result["distance_m"] > 0
                            and result["time_s"] > 0
                        )
                        gateway_snap_ok = (
                            gateway_snap_m <= MAX_GATEWAY_SNAP_M
                        )
                        destination_snap_ok = (
                            destination_snap_m
                            <= MAX_DESTINATION_SNAP_M
                        )

                        status = (
                            "PASS"
                            if (
                                finite_positive
                                and gateway_snap_ok
                                and destination_snap_ok
                            )
                            else "FLAG"
                        )

                        route_rows.append({
                            "gateway_id": anchor["gateway_id"],
                            "geo_id": anchor["geo_id"],
                            "destination_rank": destination["rank"],
                            "destination": destination["destination"],
                            "direction": direction,
                            "distance_m": result["distance_m"],
                            "time_s": result["time_s"],
                            "weight": result["weight"],
                            "gateway_snap_m": gateway_snap_m,
                            "destination_snap_m": destination_snap_m,
                            "finite_positive": finite_positive,
                            "gateway_snap_ok": gateway_snap_ok,
                            "destination_snap_ok": destination_snap_ok,
                            "status": status,
                        })

                    except Exception as exc:
                        errors.append({
                            "gateway_id": anchor["gateway_id"],
                            "geo_id": anchor["geo_id"],
                            "destination_rank": destination["rank"],
                            "destination": destination["destination"],
                            "direction": direction,
                            "error": repr(exc),
                        })

        expected_routes = (
            len(anchors)
            * len(destinations)
            * 2
        )

        flags = [
            row
            for row in route_rows
            if row["status"] != "PASS"
        ]

        print(f"routes expected = {expected_routes}")
        print(f"routes returned = {len(route_rows)}")
        print(f"route errors    = {len(errors)}")
        print(f"route flags     = {len(flags)}")

        if len(route_rows) != expected_routes or errors:
            raise RuntimeError(
                "Directed route coverage failed: "
                f"{len(route_rows)}/{expected_routes}, "
                f"errors={len(errors)}"
            )

        route_csv_path = staging / ROUTE_CSV
        with route_csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(route_rows[0].keys()),
            )
            writer.writeheader()
            writer.writerows(route_rows)

        pair_map: dict[tuple[str, int], dict[str, dict]] = {}
        for row in route_rows:
            key = (
                row["gateway_id"],
                int(row["destination_rank"]),
            )
            pair_map.setdefault(key, {})[
                row["direction"]
            ] = row

        asymmetry = []
        for pair in pair_map.values():
            forward = pair["GATEWAY_TO_DEST"]["time_s"]
            reverse = pair["DEST_TO_GATEWAY"]["time_s"]
            asymmetry.append(
                max(forward, reverse)
                / min(forward, reverse)
            )

        # ------------------------------------------------------------------
        # E. Shutdown + byte integrity
        # ------------------------------------------------------------------
        print()
        print("E. SERVER SHUTDOWN / GRAPH BYTE-INTEGRITY")

        stop_status = stop_server(proc)
        proc = None

        server_log_handle.close()
        server_log_handle = None

        graph_after = graph_inventory(final_graph)
        graph_unchanged = (
            normalized_inventory(graph_before)
            == normalized_inventory(graph_after)
        )

        print(f"server shutdown = {stop_status}")
        print(
            f"graph unchanged = "
            f"{'PASS' if graph_unchanged else 'FAIL'}"
        )

        if not graph_unchanged:
            raise RuntimeError(
                "Graph files changed during load/routing QA"
            )

        # ------------------------------------------------------------------
        # F. Gate verdict
        # ------------------------------------------------------------------
        verdict = "PASS" if not flags else "NOT_READY"

        summary = {
            "schema": (
                "B1_EXT_GH_GRAPH_LOAD_TARGETED_ROUTING_QA_SUMMARY_V01"
            ),
            "verdict": verdict,
            "graph": {
                "path": str(final_graph),
                "file_manifest_path": str(graph_manifest_path),
                "file_manifest_sha256": (
                    EXPECTED_GRAPH_MANIFEST_SHA256
                ),
                "file_count": len(graph_before),
                "total_size_bytes": graph_size_bytes,
                "byte_identical_after_qa": graph_unchanged,
            },
            "profile": PROFILE_NAME,
            "server": {
                "bind_host": "localhost",
                "application_port": APP_PORT,
                "admin_port": ADMIN_PORT,
                "heap": (
                    f"-Xms{SERVER_XMS_MIB}m "
                    f"-Xmx{SERVER_XMX_GIB}g"
                ),
                "national_pbf_passed": False,
                "shutdown": stop_status,
            },
            "b1_endpoint_sample": {
                "table": B1_TABLE,
                "table_rows": b1_meta["row_count"],
                "flow_field": b1_meta["flow_field"],
                "source_crs": "EPSG:32632",
                "route_crs": "EPSG:4326",
                "destinations": destinations,
            },
            "gateway_anchor_count": len(anchors),
            "directed_routes_expected": expected_routes,
            "directed_routes_returned": len(route_rows),
            "route_errors": errors,
            "route_flags": flags,
            "gateway_snap_threshold_m": MAX_GATEWAY_SNAP_M,
            "destination_snap_threshold_m": (
                MAX_DESTINATION_SNAP_M
            ),
            "asymmetry_ratio_max": max(asymmetry),
            "scope_guardrail": {
                "full_b1_routing": "NOT_STARTED",
                "gateway_assignment": "NOT_STARTED",
                "b5_routing": "NOT_STARTED",
                "pbf_import": "NOT_STARTED",
                "frozen_fvg_artifacts_modified": False,
            },
            "next_gate": (
                "B1_HYBRID_ROUTING_IMPLEMENTATION"
                if verdict == "PASS"
                else "REVIEW_TARGETED_ROUTING_FLAGS"
            ),
        }

        summary_path = staging / SUMMARY_JSON
        write_json(summary_path, summary)

        outputs = [
            route_csv_path,
            anchor_csv_path,
            dest_csv_path,
            server_config_path,
            server_log_path,
            summary_path,
        ]

        manifest = {
            "schema": (
                "B1_EXT_GH_GRAPH_LOAD_TARGETED_ROUTING_QA_MANIFEST_V01"
            ),
            "created_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "inputs": {
                "graph_manifest": {
                    "path": str(graph_manifest_path),
                    "sha256": EXPECTED_GRAPH_MANIFEST_SHA256,
                },
                "gh_jar": {
                    "path": str(gh_jar),
                    "sha256": GH_JAR_SHA256,
                },
                "profile_config": {
                    "path": str(import_config),
                    "sha256": PROFILE_CONFIG_SHA256,
                },
                "profile_model": {
                    "path": str(profile_model),
                    "sha256": PROFILE_MODEL_SHA256,
                },
                "geo_audit": {
                    "path": str(geo_audit),
                    "sha256": GEO_AUDIT_SHA256,
                },
                "base_gpkg": {
                    "path": str(base_gpkg),
                    "role": "READ_ONLY_B1_ENDPOINT_SAMPLE",
                },
            },
            "outputs": [
                {
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "sha256": sha256(p),
                }
                for p in outputs
            ],
            "verdict": verdict,
            "scope_guardrail": summary["scope_guardrail"],
            "next_gate": summary["next_gate"],
        }

        manifest_path = staging / MANIFEST_JSON
        write_json(manifest_path, manifest)

        staging.rename(final_dir)

        print()
        print("=" * 124)
        print(
            "B1_EXT_GH_06_GRAPH_LOAD_TARGETED_ROUTING_QA "
            f"= {verdict}"
        )
        print(
            f"VENETO_GATEWAYS_TESTED = {len(anchors)}"
        )
        print(
            f"B1_DESTINATIONS_TESTED = {len(destinations)}"
        )
        print(
            f"DIRECTED_ROUTES = "
            f"{len(route_rows)}/{expected_routes}"
        )
        print(f"ROUTE_ERRORS = {len(errors)}")
        print(f"ROUTE_FLAGS = {len(flags)}")
        print(
            "GATEWAY_SNAP_MAX_M = "
            f"{max(r['gateway_snap_m'] for r in route_rows):.3f}"
        )
        print(
            "DESTINATION_SNAP_MAX_M = "
            f"{max(r['destination_snap_m'] for r in route_rows):.3f}"
        )
        print(
            "ASYMMETRY_RATIO_MAX = "
            f"{max(asymmetry):.6f}"
        )
        print("GRAPH_BYTE_IDENTICAL_AFTER_QA = YES")
        print("FULL_B1_ROUTING = NOT_STARTED")
        print("GATEWAY_ASSIGNMENT = NOT_STARTED")
        print("B5_ROUTING = NOT_STARTED")
        print("PBF_IMPORT = NOT_STARTED")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print(f"NEXT_GATE = {summary['next_gate']}")
        print(
            f"{ROUTE_CSV} SHA256 = "
            f"{sha256(final_dir / ROUTE_CSV)}"
        )
        print(
            f"{SUMMARY_JSON} SHA256 = "
            f"{sha256(final_dir / SUMMARY_JSON)}"
        )
        print(
            f"{MANIFEST_JSON} SHA256 = "
            f"{sha256(final_dir / MANIFEST_JSON)}"
        )
        print("=== RUN COMPLETATA ===")

        return 0 if verdict == "PASS" else 2

    except Exception as exc:
        stop_status = stop_server(proc)
        proc = None

        if server_log_handle is not None:
            server_log_handle.close()
            server_log_handle = None

        print()
        print("=" * 124)
        print(
            "B1_EXT_GH_06_GRAPH_LOAD_TARGETED_ROUTING_QA = FAIL"
        )
        print(f"ERROR = {exc}")
        print(f"SERVER_SHUTDOWN = {stop_status}")
        print(
            "DIAGNOSTIC_STAGING = "
            f"{staging if staging.exists() else 'NONE'}"
        )
        print("FULL_B1_ROUTING = NOT_STARTED")
        print("GATEWAY_ASSIGNMENT = NOT_STARTED")
        print("B5_ROUTING = NOT_STARTED")
        print("PBF_IMPORT = NOT_STARTED")
        print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
        print(
            "NEXT_GATE = "
            "REVIEW_GRAPH_LOAD_OR_ROUTING_FAILURE"
        )
        print("=== RUN COMPLETATA ===")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
