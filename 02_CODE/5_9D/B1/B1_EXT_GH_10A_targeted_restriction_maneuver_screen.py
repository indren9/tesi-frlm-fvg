#!/usr/bin/env python3
"""
B1-EXT-GH 10A — TARGETED IGNORED-RESTRICTION MANEUVER SCREEN

Context
-------
GH09 closed every routing/integrity check but remained NOT_READY because
132 ignored OSM restriction relations had at least one member way in the
UNION of OSM ways used by selected B1 external routes.

That GH09 test was deliberately conservative. A single member-way overlap
does NOT prove that any selected route traverses the restricted maneuver.

Goal
----
Refine ONLY those 132 GH09 candidates to route/maneuver level.

This script:
1. verifies GH09, GH08F, frozen graph/profile evidence;
2. reparses the same frozen GraphHopper heavy-import log;
3. re-queries ONLY the 2,048 selected external legs from GH09, preserving:
      - DEFAULT LocationIndex semantics for ordinary destinations;
      - index.max_region_search=64 only for the proven fallback destinations;
4. extracts the ordered osm_way_id sequence for each selected route;
5. intersects the 132 ignored relations with individual selected routes;
6. classifies relation structure and whether a selected route actually contains
   an ordered from -> via-way(s) -> to maneuver (or a direct from -> to
   adjacency when the malformed relation has no via member);
7. materializes only diagnostic evidence.

NO:
- PBF import
- B5 routing
- gateway reselection
- modification of GH09/GH08F/frozen FVG
- national broad restriction audit

Interpretation
--------------
A relation is escalated to Stage 2 only when the available malformed relation
still contains enough FROM/TO way structure to identify a route-level maneuver
candidate. Relations missing FROM or TO are structurally incapable of defining
a complete prohibited/mandatory transition and are retained as evidence but
not escalated solely because one surviving member way is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Lineage
# ======================================================================================

GH08_TOOL_REL = r"tools\B1_EXT_GH_08_hybrid_routing_materialization.py"
GH08_TOOL_SHA256 = "e60b6655644e50d554c1399a0c7a61cae590ed7add4d12b4970d816c8ee1fe38"

GH09_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\selected_route_diagnostics_final_gate_v01"
)
GH09_SUMMARY = "B1_EXT_GH_09_selected_route_diagnostics_summary_v01.json"
GH09_SUMMARY_SHA256 = "ab71ef8b762b30abb764fe88df0bc005e6af1f8e46585fc99458325fa1f8926e"
GH09_MANIFEST = "B1_EXT_GH_09_selected_route_diagnostics_manifest_v01.json"
GH09_MANIFEST_SHA256 = "88241bf4294b3a7ac02b0406460a26aeb5dae1b60fe85e04a16815a94e8e9fa9"
GH09_FINAL_REPORT = "B1_EXT_FINAL_GATE_REPORT.txt"
GH09_FINAL_REPORT_SHA256 = "3712ee6bc06bf477e53e618c837c6d86e4cecd155c20c7663883aa0cf829bd5a"
GH09_SELECTED_KEYS = "B1_EXT_GH_09_selected_external_route_keys_v01.csv"
GH09_RESTRICTIONS = "B1_EXT_GH_09_ignored_restriction_intersection_v01.csv"

GH08F_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v02_endpoint_fallback"
)
GH08F_EXTERNAL = "B1_EXT_GH_08F_external_crossing_route_cache_v02.csv"
GH08F_EXTERNAL_SHA256 = "a43569eac857c1f879d493ec96756a904042576ee13d74582eb944b7dac8d386"
GH08F_SUMMARY = "B1_EXT_GH_08F_targeted_endpoint_fallback_summary_v02.json"
GH08F_SUMMARY_SHA256 = "08341355f95fd1bcc17a85db74a276888376b1f729db2e07ae014d4fe9aebac3"

GH08D_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_blocking_diagnostics_v01"
)
GH08D_DEST = "B1_EXT_GH_08D_unreachable_destinations_v01.csv"
GH08D_DEST_SHA256 = "9f7254562d6e92888e23183279badefc5439dfbb4fe6066efa0d9652aaea44a0"

# ======================================================================================
# GraphHopper identity
# ======================================================================================

PROFILE_NAME = "b1_ext_car_b5_compat_v01"
GH_JAR_REL = r"tools\graphhopper\b1_ext_v01\graphhopper-web-11.0.jar"
GH_JAR_SHA256 = "b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def"
RUNTIME_REL = r"tools\graphhopper\b1_ext_v01\temurin_jre_21_0_10_7"
FINAL_GRAPH_REL = r"tools\graphhopper\b1_ext_v01\graph_italy_260801_b5compat_v01"

PROFILE_CONFIG_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\profile_import_preflight_v01\graphhopper_b1_ext_import_v01.yml"
)
PROFILE_CONFIG_SHA256 = "b0302a58670447e684f35acc170ac2b06d9057ea3d7d212ce499ba0dfa3a8ade"

EXPECTED_GRAPH_MANIFEST_SHA256 = "710b2013429cde70eb9fba1652d7af7f4e24a73504be64b9d609ea619fd93189"
EXPECTED_IMPORT_LOG_SHA256 = "baddbb9ebcf47b40ea84eeaac27eb156bbd277a609945b891ed5e186d6a9e852"

# ======================================================================================
# Expected counts from GH09
# ======================================================================================

EXPECTED_SELECTED_ROUTES = 2_048
EXPECTED_DEFAULT_ROUTES = 1_959
EXPECTED_FALLBACK64_ROUTES = 89
EXPECTED_GH09_CANDIDATE_RELATIONS = 132
EXPECTED_FALLBACK_DESTINATIONS = 19

# ======================================================================================
# Runtime
# ======================================================================================

APP_PORT = 18989
ADMIN_PORT = 18990
SERVER_XMS_MIB = 256
SERVER_XMX_GIB = 2
SERVER_START_TIMEOUT_S = 120
ROUTE_TIMEOUT_S = 120
HTTP_WORKERS_DEFAULT = 6
FALLBACK_MAX_REGION_SEARCH = 64

TIME_TOL_S = 1e-9
DIST_TOL_M = 1e-6

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_diagnosis_stage1_v01"
)

ROUTE_WAYS_CSV = "B1_EXT_GH_10A_selected_route_way_sequences_v01.csv"
RELATION_STRUCTURE_CSV = "B1_EXT_GH_10A_relation_structure_v01.csv"
ROUTE_RELATION_CSV = "B1_EXT_GH_10A_route_relation_incidence_v01.csv"
MANEUVER_CANDIDATES_CSV = "B1_EXT_GH_10A_maneuver_candidates_v01.csv"
DEFAULT_CONFIG = "graphhopper_b1_ext_server_gh10a_default_v01.yml"
DEFAULT_LOG = "graphhopper_b1_ext_server_gh10a_default_v01.log"
FALLBACK_CONFIG = "graphhopper_b1_ext_server_gh10a_fallback64_v01.yml"
FALLBACK_LOG = "graphhopper_b1_ext_server_gh10a_fallback64_v01.log"
SUMMARY_JSON = "B1_EXT_GH_10A_targeted_restriction_maneuver_screen_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_10A_targeted_restriction_maneuver_screen_manifest_v01.json"

PRINT_LOCK = threading.Lock()


# ======================================================================================
# Helpers
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
    print(f"{label:<36} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    if not cols:
        raise RuntimeError(f"Missing CSV header: {path}")
    return rows, cols


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    if fieldnames is None:
        if not rows:
            raise RuntimeError(
                f"Cannot infer empty CSV schema for {path}; fieldnames required"
            )
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_float(value: Any) -> float:
    x = float(str(value).strip())
    if not math.isfinite(x):
        raise ValueError(value)
    return x


def parse_int(value: Any) -> int:
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        x = float(s)
        if not math.isfinite(x) or abs(x - round(x)) > 1e-9:
            raise
        return int(round(x))


def assert_close(actual: float, expected: float, label: str, tol: float) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(
            f"{label}: {actual} != {expected} (tol={tol})"
        )


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("gh08_authoritative", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_output_map(manifest: dict[str, Any]) -> dict[str, str]:
    rows = manifest.get("outputs")
    if not isinstance(rows, list):
        raise RuntimeError("Manifest missing outputs list")
    out: dict[str, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid manifest output item")
        name = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid manifest output item: {item}")
        if name in out:
            raise RuntimeError(f"Duplicate manifest output: {name}")
        out[name] = digest
    return out


def collapse_adjacent(values: list[int]) -> list[int]:
    out: list[int] = []
    for value in values:
        if not out or out[-1] != value:
            out.append(value)
    return out


def ordered_pair_positions(
    sequence: list[int],
    from_ids: set[int],
    to_ids: set[int],
) -> list[tuple[int, int]]:
    hits = []
    for i, value in enumerate(sequence):
        if value not in from_ids:
            continue
        for j in range(i + 1, len(sequence)):
            if sequence[j] in to_ids:
                hits.append((i, j))
    return hits


def direct_from_to_adjacency(
    sequence: list[int],
    from_ids: set[int],
    to_ids: set[int],
) -> list[tuple[int, int]]:
    return [
        (i, i + 1)
        for i in range(len(sequence) - 1)
        if sequence[i] in from_ids and sequence[i + 1] in to_ids
    ]


def exact_way_pattern_matches(
    sequence: list[int],
    from_ids: set[int],
    via_way_ids_ordered: list[int],
    to_ids: set[int],
) -> list[tuple[int, int]]:
    if not from_ids or not to_ids:
        return []
    width = 2 + len(via_way_ids_ordered)
    if width > len(sequence):
        return []
    hits = []
    for i in range(len(sequence) - width + 1):
        if sequence[i] not in from_ids:
            continue
        if sequence[i + 1:i + 1 + len(via_way_ids_ordered)] != via_way_ids_ordered:
            continue
        if sequence[i + width - 1] not in to_ids:
            continue
        hits.append((i, i + width - 1))
    return hits


def parse_member_tokens(members_text: str) -> list[dict[str, Any]]:
    """
    Parse GraphHopper's warning rendering, e.g.
      from way 123, via node 456, to way 789
      node 5612277457
    """
    out = []
    for ordinal, raw in enumerate(members_text.split(",")):
        token = raw.strip()
        if not token:
            continue
        m = re.fullmatch(
            r"(?:(from|to|via)\s+)?(way|node|relation)\s+(\d+)",
            token,
        )
        if not m:
            raise RuntimeError(f"Unparsed restriction member token: {token!r}")
        out.append({
            "ordinal": ordinal,
            "role": m.group(1) or "",
            "member_type": m.group(2),
            "member_id": int(m.group(3)),
            "raw": token,
        })
    return out


def parse_ignored_restrictions(log_path: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            if "Restriction relation " not in line or "Relation ignored." not in line:
                continue
            m = re.search(
                r"Restriction relation\s+(\d+)\s+(.*?)"
                r"tags:\s*(\{.*?\}),\s*members:\s*\[(.*?)\]\.\s*Relation ignored\.",
                line,
            )
            if not m:
                raise RuntimeError(
                    f"Could not parse ignored restriction warning "
                    f"at line {line_no}: {line[:1200]}"
                )
            relation_id = int(m.group(1))
            members_text = m.group(4).strip()
            members = parse_member_tokens(members_text)
            restriction_match = re.search(
                r"(?:^|[, {])restriction=([^,}]+)",
                m.group(3),
            )
            row = {
                "relation_id": relation_id,
                "reason": m.group(2).strip(),
                "tags": m.group(3).strip(),
                "restriction": (
                    restriction_match.group(1).strip()
                    if restriction_match else ""
                ),
                "members_text": members_text,
                "members": members,
                "line_no": line_no,
            }
            if relation_id in out:
                raise RuntimeError(
                    f"Duplicate ignored relation warning: {relation_id}"
                )
            out[relation_id] = row
    if not out:
        raise RuntimeError("No ignored restrictions parsed from import log")
    return out


def relation_structure(relation: dict[str, Any]) -> dict[str, Any]:
    members = relation["members"]

    from_ways = [
        m["member_id"]
        for m in members
        if m["role"] == "from" and m["member_type"] == "way"
    ]
    to_ways = [
        m["member_id"]
        for m in members
        if m["role"] == "to" and m["member_type"] == "way"
    ]
    via_ways_ordered = [
        m["member_id"]
        for m in members
        if m["role"] == "via" and m["member_type"] == "way"
    ]
    via_nodes = [
        m["member_id"]
        for m in members
        if m["role"] == "via" and m["member_type"] == "node"
    ]
    empty_role = [m for m in members if not m["role"]]
    all_way_ids = [
        m["member_id"]
        for m in members
        if m["member_type"] == "way"
    ]

    if not from_ways and not to_ways:
        structural_class = "MISSING_FROM_AND_TO"
    elif not from_ways:
        structural_class = "MISSING_FROM"
    elif not to_ways:
        structural_class = "MISSING_TO"
    elif via_ways_ordered:
        structural_class = "HAS_FROM_TO_VIA_WAY"
    elif via_nodes:
        structural_class = "HAS_FROM_TO_VIA_NODE"
    else:
        structural_class = "HAS_FROM_TO_NO_VIA"

    return {
        "from_ways": from_ways,
        "to_ways": to_ways,
        "via_ways_ordered": via_ways_ordered,
        "via_nodes": via_nodes,
        "empty_role_count": len(empty_role),
        "all_way_ids": all_way_ids,
        "structural_class": structural_class,
    }


def classify_route_relation(
    sequence: list[int],
    structure: dict[str, Any],
) -> dict[str, Any]:
    route_set = set(sequence)
    member_way_set = set(structure["all_way_ids"])
    matched = sorted(route_set & member_way_set)

    from_set = set(structure["from_ways"])
    to_set = set(structure["to_ways"])
    via_way_ids = list(structure["via_ways_ordered"])

    from_hit = sorted(route_set & from_set)
    to_hit = sorted(route_set & to_set)
    via_way_hit = sorted(route_set & set(via_way_ids))

    if not matched:
        return {
            "classification": "NO_MEMBER_WAY_HIT",
            "escalate": False,
            "matched_way_ids": [],
            "from_hit": [],
            "to_hit": [],
            "via_way_hit": [],
            "match_positions": [],
        }

    if not from_set or not to_set:
        return {
            "classification": "STRUCTURALLY_INCOMPLETE_MISSING_FROM_OR_TO",
            "escalate": False,
            "matched_way_ids": matched,
            "from_hit": from_hit,
            "to_hit": to_hit,
            "via_way_hit": via_way_hit,
            "match_positions": [],
        }

    if via_way_ids:
        exact = exact_way_pattern_matches(
            sequence,
            from_set,
            via_way_ids,
            to_set,
        )
        if exact:
            return {
                "classification": "ORDERED_FROM_VIAWAY_TO_MANEUVER_MATCH",
                "escalate": True,
                "matched_way_ids": matched,
                "from_hit": from_hit,
                "to_hit": to_hit,
                "via_way_hit": via_way_hit,
                "match_positions": exact,
            }

        ordered = ordered_pair_positions(sequence, from_set, to_set)
        if ordered:
            return {
                "classification": "FROM_TO_ORDERED_BUT_VIAWAY_PATTERN_NOT_MATCHED",
                "escalate": False,
                "matched_way_ids": matched,
                "from_hit": from_hit,
                "to_hit": to_hit,
                "via_way_hit": via_way_hit,
                "match_positions": ordered,
            }

    else:
        direct = direct_from_to_adjacency(
            sequence,
            from_set,
            to_set,
        )
        if direct:
            if structure["via_nodes"]:
                cls = "DIRECT_FROM_TO_WITH_VIA_NODE_UNVERIFIED"
            else:
                cls = "DIRECT_FROM_TO_MISSING_VIA_RECOVERABLE_CANDIDATE"
            return {
                "classification": cls,
                "escalate": True,
                "matched_way_ids": matched,
                "from_hit": from_hit,
                "to_hit": to_hit,
                "via_way_hit": via_way_hit,
                "match_positions": direct,
            }

        ordered = ordered_pair_positions(sequence, from_set, to_set)
        if ordered:
            return {
                "classification": "FROM_TO_SAME_ROUTE_NOT_ADJACENT",
                "escalate": False,
                "matched_way_ids": matched,
                "from_hit": from_hit,
                "to_hit": to_hit,
                "via_way_hit": via_way_hit,
                "match_positions": ordered,
            }

    if from_hit and to_hit:
        cls = "FROM_AND_TO_PRESENT_NO_ORDERED_MANEUVER"
    elif from_hit:
        cls = "FROM_WAY_HIT_ONLY"
    elif to_hit:
        cls = "TO_WAY_HIT_ONLY"
    else:
        cls = "OTHER_MEMBER_WAY_HIT_ONLY"

    return {
        "classification": cls,
        "escalate": False,
        "matched_way_ids": matched,
        "from_hit": from_hit,
        "to_hit": to_hit,
        "via_way_hit": via_way_hit,
        "match_positions": [],
    }


def helper_self_tests() -> None:
    members = parse_member_tokens(
        "from way 10, via node 20, to way 30"
    )
    if [(m["role"], m["member_type"], m["member_id"]) for m in members] != [
        ("from", "way", 10),
        ("via", "node", 20),
        ("to", "way", 30),
    ]:
        raise AssertionError("member parser self-test")

    rel = {
        "members": parse_member_tokens(
            "from way 10, to way 30"
        )
    }
    s = relation_structure(rel)
    c = classify_route_relation([1, 10, 30, 40], s)
    if not c["escalate"]:
        raise AssertionError("missing-via direct candidate self-test")

    c2 = classify_route_relation([1, 10, 20, 30], s)
    if c2["escalate"]:
        raise AssertionError("nonadjacent from/to self-test")

    rel2 = {
        "members": parse_member_tokens(
            "from way 10, via way 20, to way 30"
        )
    }
    s2 = relation_structure(rel2)
    c3 = classify_route_relation([10, 20, 30], s2)
    if not c3["escalate"]:
        raise AssertionError("via-way pattern self-test")

    if collapse_adjacent([1, 1, 2, 2, 1]) != [1, 2, 1]:
        raise AssertionError("collapse self-test")


# ======================================================================================
# YAML / server helpers
# ======================================================================================

def set_or_insert_graphhopper_yaml_int(
    text: str,
    key: str,
    value: int,
) -> tuple[str, str]:
    lines = text.splitlines()
    hits = [
        i for i, line in enumerate(lines)
        if line.lstrip().startswith(key + ":")
    ]
    if len(hits) > 1:
        raise RuntimeError(f"Multiple active '{key}:' lines")

    gh_hits = [i for i, line in enumerate(lines) if line == "graphhopper:"]
    if len(gh_hits) != 1:
        raise RuntimeError(
            f"Expected exactly one root-level graphhopper section; found {len(gh_hits)}"
        )
    gh_i = gh_hits[0]

    gh_end = len(lines)
    for i in range(gh_i + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent_len = len(lines[i]) - len(lines[i].lstrip())
        if indent_len == 0:
            gh_end = i
            break

    if len(hits) == 1:
        i = hits[0]
        if not (gh_i < i < gh_end):
            raise RuntimeError(f"Active '{key}' outside graphhopper section")
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        if not indent:
            raise RuntimeError(f"Unsafe root-level '{key}'")
        old = lines[i].strip()
        lines[i] = f"{indent}{key}: {int(value)}"
        return "\n".join(lines) + "\n", f"REPLACED_IN_GRAPHHOPPER [{old}]"

    refs = []
    for ref_key in ("graph.location", "datareader.file"):
        for i in range(gh_i + 1, gh_end):
            if lines[i].lstrip().startswith(ref_key + ":"):
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                if indent:
                    refs.append((i, indent))
    if not refs:
        raise RuntimeError("Could not infer graphhopper scalar indentation")
    indents = {indent for _, indent in refs}
    if len(indents) != 1:
        raise RuntimeError(f"Inconsistent graphhopper indentation: {indents}")
    indent = next(iter(indents))
    graph_loc = [
        i for i in range(gh_i + 1, gh_end)
        if lines[i].lstrip().startswith("graph.location:")
    ]
    insert_at = graph_loc[0] + 1 if len(graph_loc) == 1 else max(i for i, _ in refs) + 1
    lines.insert(insert_at, f"{indent}{key}: {int(value)}")
    return "\n".join(lines) + "\n", "INSERTED_IN_GRAPHHOPPER_SECTION"


def make_server_config(
    gh08,
    profile_config: Path,
    graph_dir: Path,
    staging: Path,
    fallback64: bool,
) -> tuple[str, str]:
    text = gh08.make_server_config(
        profile_config,
        graph_dir,
        staging,
    )
    if not fallback64:
        return text, "DEFAULT_LOCATION_INDEX"
    text, action = set_or_insert_graphhopper_yaml_int(
        text,
        "index.max_region_search",
        FALLBACK_MAX_REGION_SEARCH,
    )
    return text, action


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
        f"GraphHopper server did not open port {APP_PORT}"
    )


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
# Route way-sequence request
# ======================================================================================

def route_way_sequence_request(cache_row: dict[str, str]) -> dict[str, Any]:
    direction = str(cache_row["direction"])
    crossing_lat = parse_float(cache_row["crossing_lat"])
    crossing_lon = parse_float(cache_row["crossing_lon"])
    dest_lat = parse_float(cache_row["dest_lat"])
    dest_lon = parse_float(cache_row["dest_lon"])

    if direction == "IE":
        start_lat, start_lon = crossing_lat, crossing_lon
        end_lat, end_lon = dest_lat, dest_lon
    elif direction == "EI":
        start_lat, start_lon = dest_lat, dest_lon
        end_lat, end_lon = crossing_lat, crossing_lon
    else:
        raise ValueError(direction)

    params = [
        ("point", f"{start_lat:.8f},{start_lon:.8f}"),
        ("point", f"{end_lat:.8f},{end_lon:.8f}"),
        ("profile", PROFILE_NAME),
        ("instructions", "false"),
        ("calc_points", "false"),
        ("points_encoded", "false"),
        ("snap_prevention", ""),
        ("details", "osm_way_id"),
    ]
    url = f"http://127.0.0.1:{APP_PORT}/route?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Tesi-B1-EXT-GH10A/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=ROUTE_TIMEOUT_S) as response:
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
    if len(paths) != 1:
        raise RuntimeError(f"Expected one route path; got {len(paths)}")
    path = paths[0]

    route_time_s = parse_int(path["time"]) / 1000.0
    route_distance_m = parse_float(path["distance"])
    assert_close(
        route_time_s,
        parse_float(cache_row["external_time_s"]),
        f"time regression {cache_row['destination_key']} {cache_row['geo_id']} {direction}",
        TIME_TOL_S,
    )
    assert_close(
        route_distance_m,
        parse_float(cache_row["external_distance_m"]),
        f"distance regression {cache_row['destination_key']} {cache_row['geo_id']} {direction}",
        DIST_TOL_M,
    )

    details = path.get("details", {})
    way_details = details.get("osm_way_id")
    if not isinstance(way_details, list) or not way_details:
        raise RuntimeError("osm_way_id path details missing/empty")

    raw_way_sequence = []
    for item in way_details:
        if not isinstance(item, list) or len(item) != 3:
            raise RuntimeError(f"Invalid osm_way_id detail: {item}")
        if item[2] is None:
            raise RuntimeError("Null osm_way_id path detail")
        raw_way_sequence.append(parse_int(item[2]))

    sequence = collapse_adjacent(raw_way_sequence)
    if not sequence:
        raise RuntimeError("Empty collapsed OSM way sequence")

    return {
        "destination_key": str(cache_row["destination_key"]),
        "dest_COMUNE": str(cache_row["dest_COMUNE"]),
        "gateway_id": str(cache_row["gateway_id"]),
        "geo_id": str(cache_row["geo_id"]),
        "direction": direction,
        "external_time_s": route_time_s,
        "external_distance_m": route_distance_m,
        "way_detail_count": len(raw_way_sequence),
        "collapsed_way_count": len(sequence),
        "way_sequence": sequence,
    }


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument(
        "--http-workers",
        type=int,
        default=HTTP_WORKERS_DEFAULT,
    )
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_10A_HELPER_SELF_TESTS = PASS")
        return 0

    if not (1 <= args.http_workers <= 16):
        raise ValueError("--http-workers must be in [1,16]")

    root = Path(args.root)
    gh08_tool = root / Path(GH08_TOOL_REL)
    gh09_dir = root / Path(GH09_DIR_REL)
    gh08f_dir = root / Path(GH08F_DIR_REL)
    gh08d_dir = root / Path(GH08D_DIR_REL)
    graph_dir = root / Path(FINAL_GRAPH_REL)
    gh_jar = root / Path(GH_JAR_REL)
    runtime_root = root / Path(RUNTIME_REL)
    profile_config = root / Path(PROFILE_CONFIG_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name
        + "_STAGING_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 10A — TARGETED IGNORED-RESTRICTION MANEUVER SCREEN")
    print("=" * 124)
    print(
        "132 GH09 USED-WAY CANDIDATES -> INDIVIDUAL SELECTED ROUTES / ORDERED OSM WAY SEQUENCES"
    )
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Lineage
    # ------------------------------------------------------------------
    print("A. STRICT LINEAGE / EVIDENCE IDENTITY")
    strict_hash("GH08 tool", gh08_tool, GH08_TOOL_SHA256)
    strict_hash(
        "GH09 summary",
        gh09_dir / GH09_SUMMARY,
        GH09_SUMMARY_SHA256,
    )
    strict_hash(
        "GH09 manifest",
        gh09_dir / GH09_MANIFEST,
        GH09_MANIFEST_SHA256,
    )
    strict_hash(
        "GH09 final report",
        gh09_dir / GH09_FINAL_REPORT,
        GH09_FINAL_REPORT_SHA256,
    )
    strict_hash(
        "GH08F external cache",
        gh08f_dir / GH08F_EXTERNAL,
        GH08F_EXTERNAL_SHA256,
    )
    strict_hash(
        "GH08F summary",
        gh08f_dir / GH08F_SUMMARY,
        GH08F_SUMMARY_SHA256,
    )
    strict_hash(
        "GH08D fallback destinations",
        gh08d_dir / GH08D_DEST,
        GH08D_DEST_SHA256,
    )
    strict_hash("GH JAR", root / Path(GH_JAR_REL), GH_JAR_SHA256)
    strict_hash("profile config", profile_config, PROFILE_CONFIG_SHA256)

    gh09_summary = read_json(gh09_dir / GH09_SUMMARY)
    if gh09_summary.get("verdict") != "NOT_READY":
        raise RuntimeError("Expected GH09 verdict NOT_READY")
    if int(
        gh09_summary["ignored_restrictions"]["candidate_intersections"]
    ) != EXPECTED_GH09_CANDIDATE_RELATIONS:
        raise RuntimeError("GH09 candidate count drift")

    gh09_manifest = read_json(gh09_dir / GH09_MANIFEST)
    gh09_output_hashes = manifest_output_map(gh09_manifest)
    for filename, digest in sorted(gh09_output_hashes.items()):
        p = gh09_dir / filename
        if not p.is_file():
            raise FileNotFoundError(p)
        if sha256(p) != digest:
            raise RuntimeError(f"GH09 output changed: {filename}")
    print(f"GH09 outputs verified            = {len(gh09_output_hashes)}")

    if GH09_SELECTED_KEYS not in gh09_output_hashes:
        raise RuntimeError("GH09 selected-key CSV absent from manifest")
    if GH09_RESTRICTIONS not in gh09_output_hashes:
        raise RuntimeError("GH09 restriction CSV absent from manifest")

    import_log_path = Path(
        gh09_summary["ignored_restrictions"]["import_log_path"]
    )
    if sha256(import_log_path) != EXPECTED_IMPORT_LOG_SHA256:
        raise RuntimeError("Frozen heavy-import log SHA mismatch")
    print(f"import log                      PASS  {sha256(import_log_path)}")

    gh08 = load_module(gh08_tool)
    gh08.helper_self_tests()
    print("GH08 helper self-tests           PASS")
    print("GH10A helper self-tests          PASS")

    graph_manifest_path, graph_manifest = gh08.find_graph_manifest(root)
    if sha256(graph_manifest_path) != EXPECTED_GRAPH_MANIFEST_SHA256:
        raise RuntimeError("Frozen graph manifest SHA mismatch")
    graph_before = gh08.graph_inventory(graph_dir)
    if gh08.normalized_inventory(graph_before) != gh08.normalized_inventory(
        graph_manifest.get("files", [])
    ):
        raise RuntimeError("Italy graph differs from frozen manifest")
    print("Italy graph identity             PASS")

    # ------------------------------------------------------------------
    # B. Candidate relation structures
    # ------------------------------------------------------------------
    print()
    print("B. 132 RELATION STRUCTURE PARSE")

    gh09_restriction_rows, _ = read_csv(
        gh09_dir / GH09_RESTRICTIONS
    )
    gh09_candidate_ids = {
        parse_int(r["relation_id"])
        for r in gh09_restriction_rows
        if r["classification"] == "USED_WAY_MEMBER_INTERSECTION_CANDIDATE"
    }
    if len(gh09_candidate_ids) != EXPECTED_GH09_CANDIDATE_RELATIONS:
        raise RuntimeError(
            f"GH09 candidate relation IDs = {len(gh09_candidate_ids)}"
        )

    all_ignored = parse_ignored_restrictions(import_log_path)
    missing_ids = gh09_candidate_ids - set(all_ignored)
    if missing_ids:
        raise RuntimeError(
            f"GH09 candidate IDs absent from import log: {sorted(missing_ids)[:20]}"
        )

    relation_objects = {
        rid: all_ignored[rid]
        for rid in sorted(gh09_candidate_ids)
    }
    structures = {
        rid: relation_structure(rel)
        for rid, rel in relation_objects.items()
    }

    structural_counts = Counter(
        s["structural_class"] for s in structures.values()
    )
    for key, value in sorted(structural_counts.items()):
        print(f"  {key:<34} {value:4d}")

    # ------------------------------------------------------------------
    # C. Selected route keys and cache lookup
    # ------------------------------------------------------------------
    print()
    print("C. SELECTED ROUTE KEY / CACHE AUDIT")

    selected_rows, _ = read_csv(
        gh09_dir / GH09_SELECTED_KEYS
    )
    if len(selected_rows) != EXPECTED_SELECTED_ROUTES:
        raise RuntimeError(
            f"GH09 selected routes = {len(selected_rows)}"
        )

    external_rows, _ = read_csv(
        gh08f_dir / GH08F_EXTERNAL
    )
    external_lookup = {
        (
            str(r["destination_key"]),
            str(r["geo_id"]),
            str(r["direction"]),
        ): r
        for r in external_rows
    }

    selected_keys = []
    selected_meta: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in selected_rows:
        key = (
            str(r["destination_key"]),
            str(r["geo_id"]),
            str(r["direction"]),
        )
        if key in selected_meta:
            raise RuntimeError(f"Duplicate selected route key: {key}")
        cache = external_lookup.get(key)
        if cache is None:
            raise RuntimeError(f"Missing external cache row: {key}")
        selected_keys.append(key)
        selected_meta[key] = {
            "selected_row": r,
            "cache_row": cache,
        }

    default_keys = [
        k for k in selected_keys
        if selected_meta[k]["selected_row"]["search_mode"] == "DEFAULT"
    ]
    fallback_keys = [
        k for k in selected_keys
        if selected_meta[k]["selected_row"]["search_mode"] == "FALLBACK64"
    ]
    if len(default_keys) != EXPECTED_DEFAULT_ROUTES:
        raise RuntimeError(f"Default selected routes = {len(default_keys)}")
    if len(fallback_keys) != EXPECTED_FALLBACK64_ROUTES:
        raise RuntimeError(f"Fallback64 selected routes = {len(fallback_keys)}")

    print(f"selected external routes        = {len(selected_keys):,}")
    print(f"default routes                  = {len(default_keys):,}")
    print(f"fallback64 routes               = {len(fallback_keys):,}")

    # ------------------------------------------------------------------
    # D. Re-query route way sequences
    # ------------------------------------------------------------------
    staging.mkdir(parents=True, exist_ok=False)
    java_exe = gh08.find_java(runtime_root)

    route_results: dict[tuple[str, str, str], dict[str, Any]] = {}

    def run_phase(
        title: str,
        keys: list[tuple[str, str, str]],
        fallback64: bool,
        config_name: str,
        log_name: str,
    ) -> None:
        if not keys:
            return

        print()
        print(title)

        if not port_is_free(APP_PORT):
            raise RuntimeError(f"Application port {APP_PORT} already in use")
        if not port_is_free(ADMIN_PORT):
            raise RuntimeError(f"Admin port {ADMIN_PORT} already in use")

        config_text, action = make_server_config(
            gh08,
            profile_config,
            graph_dir,
            staging,
            fallback64,
        )
        config_path = staging / config_name
        config_path.write_text(config_text, encoding="utf-8")
        print(f"config action                   = {action}")
        print(
            "index.max_region_search         = "
            + (
                str(FALLBACK_MAX_REGION_SEARCH)
                if fallback64 else "DEFAULT"
            )
        )
        print("national PBF passed             = NO")
        print("bind host                       = localhost")

        log_path = staging / log_name
        log_handle = log_path.open(
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
            str(root / Path(GH_JAR_REL)),
            "server",
            str(config_path),
        ]
        proc: subprocess.Popen | None = None

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=staging,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            wait_for_server(proc)
            print("SERVER_LOAD                     = PASS")

            started = time.time()
            completed = 0
            with ThreadPoolExecutor(
                max_workers=args.http_workers
            ) as pool:
                futures = {
                    pool.submit(
                        route_way_sequence_request,
                        selected_meta[key]["cache_row"],
                    ): key
                    for key in keys
                }
                for fut in as_completed(futures):
                    key = futures[fut]
                    result = fut.result()
                    result["search_mode"] = (
                        "FALLBACK64" if fallback64 else "DEFAULT"
                    )
                    result["selected_b1_relations"] = parse_int(
                        selected_meta[key]["selected_row"]["selected_b1_relations"]
                    )
                    result["Pendolari_raw_sum"] = parse_float(
                        selected_meta[key]["selected_row"]["Pendolari_raw_sum"]
                    )
                    result["flow_daily_sum"] = parse_float(
                        selected_meta[key]["selected_row"]["flow_daily_sum"]
                    )
                    route_results[key] = result
                    completed += 1

                    if completed % 100 == 0 or completed == len(keys):
                        elapsed = max(time.time() - started, 1e-9)
                        rate = completed / elapsed
                        eta = (
                            len(keys) - completed
                        ) / max(rate, 1e-9)
                        with PRINT_LOCK:
                            print(
                                f"  ways {completed:,}/{len(keys):,} "
                                f"({100*completed/len(keys):5.1f}%) "
                                f"rate={rate:5.1f}/s "
                                f"ETA={eta/60:5.1f} min"
                            )
        finally:
            status = stop_server(proc)
            log_handle.close()
            print(f"server shutdown                 = {status}")

    run_phase(
        "D.1 DEFAULT SELECTED ROUTE WAY SEQUENCES",
        default_keys,
        False,
        DEFAULT_CONFIG,
        DEFAULT_LOG,
    )
    run_phase(
        "D.2 FALLBACK64 SELECTED ROUTE WAY SEQUENCES",
        fallback_keys,
        True,
        FALLBACK_CONFIG,
        FALLBACK_LOG,
    )

    if len(route_results) != EXPECTED_SELECTED_ROUTES:
        raise RuntimeError(
            f"Route way sequences = {len(route_results)}"
        )

    route_way_rows = []
    route_way_sets: dict[tuple[str, str, str], set[int]] = {}
    for key in sorted(route_results):
        r = route_results[key]
        seq = r["way_sequence"]
        route_way_sets[key] = set(seq)
        route_way_rows.append({
            "destination_key": r["destination_key"],
            "dest_COMUNE": r["dest_COMUNE"],
            "gateway_id": r["gateway_id"],
            "geo_id": r["geo_id"],
            "direction": r["direction"],
            "search_mode": r["search_mode"],
            "selected_b1_relations": r["selected_b1_relations"],
            "Pendolari_raw_sum": r["Pendolari_raw_sum"],
            "flow_daily_sum": r["flow_daily_sum"],
            "external_time_s": r["external_time_s"],
            "external_distance_m": r["external_distance_m"],
            "way_detail_count": r["way_detail_count"],
            "collapsed_way_count": r["collapsed_way_count"],
            "osm_way_sequence": "|".join(str(x) for x in seq),
        })
    write_csv(staging / ROUTE_WAYS_CSV, route_way_rows)

    # ------------------------------------------------------------------
    # E. Relation-route incidence
    # ------------------------------------------------------------------
    print()
    print("E. RELATION -> INDIVIDUAL SELECTED ROUTE MANEUVER SCREEN")

    # Inverted way -> selected route keys, so we do not evaluate all 132x2048.
    way_to_routes: defaultdict[int, set[tuple[str, str, str]]] = defaultdict(set)
    for key, way_set in route_way_sets.items():
        for way_id in way_set:
            way_to_routes[way_id].add(key)

    incidence_rows: list[dict[str, Any]] = []
    maneuver_rows: list[dict[str, Any]] = []
    relation_summary_rows: list[dict[str, Any]] = []

    global_class_counts = Counter()

    for rid in sorted(relation_objects):
        rel = relation_objects[rid]
        s = structures[rid]
        candidate_route_keys: set[tuple[str, str, str]] = set()
        for way_id in s["all_way_ids"]:
            candidate_route_keys.update(way_to_routes.get(way_id, set()))

        relation_class_counts = Counter()
        escalated_route_keys = []
        matched_route_keys = []

        for key in sorted(candidate_route_keys):
            seq = route_results[key]["way_sequence"]
            c = classify_route_relation(seq, s)
            if c["classification"] == "NO_MEMBER_WAY_HIT":
                continue

            matched_route_keys.append(key)
            relation_class_counts[c["classification"]] += 1
            global_class_counts[c["classification"]] += 1

            meta = selected_meta[key]["selected_row"]
            incidence = {
                "relation_id": rid,
                "restriction": rel["restriction"],
                "reason": rel["reason"],
                "structural_class": s["structural_class"],
                "route_classification": c["classification"],
                "escalate_stage2": c["escalate"],
                "destination_key": key[0],
                "dest_COMUNE": route_results[key]["dest_COMUNE"],
                "gateway_id": route_results[key]["gateway_id"],
                "geo_id": key[1],
                "direction": key[2],
                "selected_b1_relations": parse_int(
                    meta["selected_b1_relations"]
                ),
                "Pendolari_raw_sum": parse_float(
                    meta["Pendolari_raw_sum"]
                ),
                "flow_daily_sum": parse_float(
                    meta["flow_daily_sum"]
                ),
                "from_way_ids": "|".join(
                    str(x) for x in s["from_ways"]
                ),
                "via_way_ids": "|".join(
                    str(x) for x in s["via_ways_ordered"]
                ),
                "via_node_ids": "|".join(
                    str(x) for x in s["via_nodes"]
                ),
                "to_way_ids": "|".join(
                    str(x) for x in s["to_ways"]
                ),
                "matched_member_way_ids": "|".join(
                    str(x) for x in c["matched_way_ids"]
                ),
                "from_hit_way_ids": "|".join(
                    str(x) for x in c["from_hit"]
                ),
                "via_hit_way_ids": "|".join(
                    str(x) for x in c["via_way_hit"]
                ),
                "to_hit_way_ids": "|".join(
                    str(x) for x in c["to_hit"]
                ),
                "match_positions": "|".join(
                    f"{a}:{b}"
                    for a, b in c["match_positions"]
                ),
                "osm_way_sequence": "|".join(
                    str(x) for x in seq
                ),
            }
            incidence_rows.append(incidence)

            if c["escalate"]:
                maneuver_rows.append(incidence.copy())
                escalated_route_keys.append(key)

        relation_summary_rows.append({
            "relation_id": rid,
            "restriction": rel["restriction"],
            "reason": rel["reason"],
            "tags": rel["tags"],
            "members": rel["members_text"],
            "structural_class": s["structural_class"],
            "from_way_ids": "|".join(
                str(x) for x in s["from_ways"]
            ),
            "via_way_ids": "|".join(
                str(x) for x in s["via_ways_ordered"]
            ),
            "via_node_ids": "|".join(
                str(x) for x in s["via_nodes"]
            ),
            "to_way_ids": "|".join(
                str(x) for x in s["to_ways"]
            ),
            "empty_role_count": s["empty_role_count"],
            "selected_routes_with_any_member_way_hit": len(
                matched_route_keys
            ),
            "selected_routes_escalated_stage2": len(
                escalated_route_keys
            ),
            "route_classification_counts": json.dumps(
                dict(sorted(relation_class_counts.items())),
                sort_keys=True,
            ),
            "stage2_required": bool(escalated_route_keys),
        })

    relation_fieldnames = [
        "relation_id", "restriction", "reason", "tags", "members",
        "structural_class", "from_way_ids", "via_way_ids", "via_node_ids",
        "to_way_ids", "empty_role_count",
        "selected_routes_with_any_member_way_hit",
        "selected_routes_escalated_stage2",
        "route_classification_counts", "stage2_required",
    ]
    incidence_fieldnames = [
        "relation_id", "restriction", "reason", "structural_class",
        "route_classification", "escalate_stage2",
        "destination_key", "dest_COMUNE", "gateway_id", "geo_id", "direction",
        "selected_b1_relations", "Pendolari_raw_sum", "flow_daily_sum",
        "from_way_ids", "via_way_ids", "via_node_ids", "to_way_ids",
        "matched_member_way_ids", "from_hit_way_ids", "via_hit_way_ids",
        "to_hit_way_ids", "match_positions", "osm_way_sequence",
    ]

    write_csv(
        staging / RELATION_STRUCTURE_CSV,
        relation_summary_rows,
        relation_fieldnames,
    )
    write_csv(
        staging / ROUTE_RELATION_CSV,
        incidence_rows,
        incidence_fieldnames,
    )
    write_csv(
        staging / MANEUVER_CANDIDATES_CSV,
        maneuver_rows,
        incidence_fieldnames,
    )

    escalated_relations = sorted({
        parse_int(r["relation_id"])
        for r in maneuver_rows
    })
    escalated_route_pairs = len(maneuver_rows)
    structurally_incomplete = sum(
        1
        for s in structures.values()
        if s["structural_class"] in {
            "MISSING_FROM_AND_TO",
            "MISSING_FROM",
            "MISSING_TO",
        }
    )

    print(f"route-relation incidences       = {len(incidence_rows):,}")
    print(f"structurally incomplete rels    = {structurally_incomplete}")
    print(f"stage2 maneuver relations       = {len(escalated_relations)}")
    print(f"stage2 route-relation pairs     = {escalated_route_pairs}")

    print("route classification counts:")
    for key, value in sorted(global_class_counts.items()):
        print(f"  {key:<48} {value:5d}")

    # ------------------------------------------------------------------
    # F. Integrity and gate
    # ------------------------------------------------------------------
    print()
    print("F. BYTE-INTEGRITY / GATE")

    graph_after = gh08.graph_inventory(graph_dir)
    graph_unchanged = (
        gh08.normalized_inventory(graph_before)
        == gh08.normalized_inventory(graph_after)
    )
    if not graph_unchanged:
        raise RuntimeError("Italy graph changed during GH10A")

    # GH09 and GH08F must remain byte-identical.
    for filename, digest in sorted(gh09_output_hashes.items()):
        if sha256(gh09_dir / filename) != digest:
            raise RuntimeError(f"GH09 output changed: {filename}")
    if sha256(gh08f_dir / GH08F_EXTERNAL) != GH08F_EXTERNAL_SHA256:
        raise RuntimeError("GH08F external cache changed")
    if sha256(gh08f_dir / GH08F_SUMMARY) != GH08F_SUMMARY_SHA256:
        raise RuntimeError("GH08F summary changed")

    if escalated_relations:
        verdict = "PASS"
        blocker_state = "REFINED_TO_MANEUVER_LEVEL_CANDIDATES"
        next_gate = "GH10B_TARGETED_PBF_TOPOLOGY_RESTRICTION_CHECK"
    else:
        verdict = "PASS"
        blocker_state = "NO_ROUTE_LEVEL_RESTRICTION_MANEUVER_CANDIDATE"
        next_gate = "B1_FINAL_GATE_REASSESSMENT_AFTER_FALSE_POSITIVE_REFINEMENT"

    print(f"Italy graph unchanged           = {'PASS' if graph_unchanged else 'FAIL'}")
    print("GH09 outputs modified           = NO")
    print("GH08F outputs modified          = NO")

    summary = {
        "schema": "B1_EXT_GH_10A_TARGETED_RESTRICTION_MANEUVER_SCREEN_SUMMARY_V01",
        "verdict": verdict,
        "GH09_status": "NOT_READY",
        "GH09_candidate_relations": EXPECTED_GH09_CANDIDATE_RELATIONS,
        "selected_external_routes_screened": len(route_results),
        "default_routes_screened": len(default_keys),
        "fallback64_routes_screened": len(fallback_keys),
        "relation_structure_counts": dict(sorted(structural_counts.items())),
        "route_relation_incidence_count": len(incidence_rows),
        "route_classification_counts": dict(
            sorted(global_class_counts.items())
        ),
        "structurally_incomplete_relations": structurally_incomplete,
        "stage2_maneuver_candidate_relations": len(escalated_relations),
        "stage2_maneuver_candidate_relation_ids": escalated_relations,
        "stage2_route_relation_pairs": escalated_route_pairs,
        "blocker_refinement": blocker_state,
        "methodological_rule": (
            "GH09 used-way union overlap is a conservative screen. "
            "Stage 2 escalation requires a selected route to contain an "
            "ordered FROM->VIA-WAY(s)->TO pattern, or direct FROM->TO "
            "adjacency when the ignored relation lacks a usable VIA member. "
            "Relations missing FROM or TO are retained as malformed evidence "
            "but do not define a complete restriction maneuver."
        ),
        "integrity": {
            "italy_graph_byte_identical_after_run": graph_unchanged,
            "GH09_outputs_modified": False,
            "GH08F_outputs_modified": False,
            "PBF_import": "NOT_STARTED",
            "B5_routing": "NOT_STARTED",
        },
        "next_gate": next_gate,
    }
    summary_path = staging / SUMMARY_JSON
    write_json(summary_path, summary)

    output_files = [
        staging / ROUTE_WAYS_CSV,
        staging / RELATION_STRUCTURE_CSV,
        staging / ROUTE_RELATION_CSV,
        staging / MANEUVER_CANDIDATES_CSV,
        staging / DEFAULT_CONFIG,
        staging / DEFAULT_LOG,
        staging / FALLBACK_CONFIG,
        staging / FALLBACK_LOG,
        summary_path,
    ]
    output_files = [p for p in output_files if p.exists()]

    manifest = {
        "schema": "B1_EXT_GH_10A_TARGETED_RESTRICTION_MANEUVER_SCREEN_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "inputs": {
            "GH09_manifest": {
                "path": str(gh09_dir / GH09_MANIFEST),
                "sha256": sha256(gh09_dir / GH09_MANIFEST),
            },
            "GH09_summary": {
                "path": str(gh09_dir / GH09_SUMMARY),
                "sha256": sha256(gh09_dir / GH09_SUMMARY),
            },
            "GH08F_external": {
                "path": str(gh08f_dir / GH08F_EXTERNAL),
                "sha256": sha256(gh08f_dir / GH08F_EXTERNAL),
            },
            "graph_manifest": {
                "path": str(graph_manifest_path),
                "sha256": sha256(graph_manifest_path),
            },
            "import_log": {
                "path": str(import_log_path),
                "sha256": sha256(import_log_path),
            },
        },
        "outputs": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in output_files
        ],
        "stage2_maneuver_candidate_relation_ids": escalated_relations,
        "next_gate": next_gate,
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    staging.rename(final_dir)

    print()
    print("=" * 124)
    print(
        f"B1_EXT_GH_10A_TARGETED_RESTRICTION_MANEUVER_SCREEN = {verdict}"
    )
    print(f"GH09 = NOT_READY")
    print(
        f"GH09_USED_WAY_CANDIDATE_RELATIONS = "
        f"{EXPECTED_GH09_CANDIDATE_RELATIONS}"
    )
    print(
        f"SELECTED_EXTERNAL_ROUTES_SCREENED = "
        f"{len(route_results)}"
    )
    print(
        f"STRUCTURALLY_INCOMPLETE_RELATIONS = "
        f"{structurally_incomplete}"
    )
    print(
        f"STAGE2_MANEUVER_CANDIDATE_RELATIONS = "
        f"{len(escalated_relations)}"
    )
    print(
        f"STAGE2_ROUTE_RELATION_PAIRS = "
        f"{escalated_route_pairs}"
    )
    print(f"BLOCKER_REFINEMENT = {blocker_state}")
    print("PBF_IMPORT = NOT_STARTED")
    print("B5_ROUTING = NOT_STARTED")
    print("ITALY_GRAPH_BYTE_IDENTICAL_AFTER_RUN = YES")
    print("GH09_OUTPUTS_MODIFIED = NO")
    print("GH08F_OUTPUTS_MODIFIED = NO")
    print(f"NEXT_GATE = {next_gate}")
    print(
        f"{MANEUVER_CANDIDATES_CSV} SHA256 = "
        f"{sha256(final_dir / MANEUVER_CANDIDATES_CSV)}"
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

    if escalated_relations:
        print(
            "HARD STOP — DO NOT RETURN TO CHAT MADRE; "
            "RUN TARGETED STAGE-2 TOPOLOGY CHECK ONLY."
        )
    else:
        print(
            "HARD STOP — GH09 COARSE INTERSECTION SCREEN REFINED TO ZERO "
            "MANEUVER CANDIDATES; FINAL GATE REASSESSMENT REQUIRED."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
