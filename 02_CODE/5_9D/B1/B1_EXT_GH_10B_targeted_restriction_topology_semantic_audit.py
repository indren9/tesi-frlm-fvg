#!/usr/bin/env python3
"""
B1-EXT-GH 10B — TARGETED RESTRICTION TOPOLOGY + SEMANTIC AUDIT

WHY THIS EXISTS
---------------
GH09 found 132 ignored-restriction relations with at least one member way in the
union of selected B1 external routes. GH10A then proved that only a subset has
route-level from/to maneuver proximity, but GH10A's screen was intentionally
coarse and did not yet perform the exact OSM restriction semantics audit.

This stage is deliberately OFFLINE:
- NO GraphHopper server
- NO rerouting
- NO PBF import
- NO B5 routing
- NO gateway reselection

It reads:
1) the already-materialized GH10A selected route OSM-way sequences;
2) the exact 132 relation objects from the frozen Italy PBF;
3) only the OSM ways needed to verify those relations and the immediately
   adjacent route transitions.

It then evaluates the actual semantics separately for:
- no_* restrictions: the specified maneuver is prohibited;
- only_* restrictions: the specified to-maneuver is allowed, while another
  exit from the same restricted junction is potentially prohibited.

This corrects an important limitation of the GH10A coarse screen: a route that
matches from->to for an ``only_*`` restriction is COMPLIANT, not a violation.

OUTPUT INTERPRETATION
---------------------
VIOLATION_CANDIDATE:
    selected route appears to traverse a maneuver forbidden by the ignored
    restriction, after topology verification.

UNRESOLVED:
    relation/route cannot be decided safely from the frozen PBF + collapsed
    OSM-way sequence alone (for example same-way U-turn or ambiguous topology).

CLEAR:
    no selected route violates the ignored restriction under the tested
    semantics.

The final B1 gate can be reassessed only when both violation candidates and
unresolved relations are zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# ======================================================================================
# Frozen lineage
# ======================================================================================

GH10A_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_diagnosis_stage1_v01"
)
GH10A_SUMMARY = "B1_EXT_GH_10A_targeted_restriction_maneuver_screen_summary_v01.json"
GH10A_SUMMARY_SHA256 = "8a7e45a18ba8f0046d1b0403c660337236f8b66e0de3446fd39f1295421afd3e"
GH10A_MANIFEST = "B1_EXT_GH_10A_targeted_restriction_maneuver_screen_manifest_v01.json"
GH10A_MANIFEST_SHA256 = "dadfc62502a979787fea248ea2b263b4f3ba9dbff5140557835e9f998a8e442b"
GH10A_MANEUVER = "B1_EXT_GH_10A_maneuver_candidates_v01.csv"
GH10A_MANEUVER_SHA256 = "ff7cafaa834f50def55d2800fe6b1921a03a863edcb570665ffc1f03500517b9"

GH10A_ROUTE_WAYS = "B1_EXT_GH_10A_selected_route_way_sequences_v01.csv"
GH10A_REL_STRUCTURE = "B1_EXT_GH_10A_relation_structure_v01.csv"

GH09_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\selected_route_diagnostics_final_gate_v01"
)
GH09_SUMMARY = "B1_EXT_GH_09_selected_route_diagnostics_summary_v01.json"
GH09_SUMMARY_SHA256 = "ab71ef8b762b30abb764fe88df0bc005e6af1f8e46585fc99458325fa1f8926e"

ITALY_PBF_REL = (
    r"Tesi_QGIS\00_originali\rete_stradale\osm\external_b1"
    r"\italy-260801.osm.pbf"
)
ITALY_PBF_SHA256 = "f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538"

EXPECTED_GH09_RELATIONS = 132
EXPECTED_GH10A_STAGE2_RELATIONS = 10
EXPECTED_GH10A_STAGE2_PAIRS = 52
EXPECTED_SELECTED_ROUTES = 2048

# ======================================================================================
# Output
# ======================================================================================

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_restriction_topology_semantic_audit_v01"
)

RELATION_PBF_CSV = "B1_EXT_GH_10B_relation_pbf_structure_v01.csv"
ROUTE_AUDIT_CSV = "B1_EXT_GH_10B_route_restriction_semantic_audit_v01.csv"
RELATION_RESULT_CSV = "B1_EXT_GH_10B_relation_results_v01.csv"
VIOLATION_CSV = "B1_EXT_GH_10B_violation_candidates_v01.csv"
UNRESOLVED_CSV = "B1_EXT_GH_10B_unresolved_candidates_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_10B_targeted_restriction_topology_semantic_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_10B_targeted_restriction_topology_semantic_manifest_v01.json"

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
    print(f"{label:<38} {'PASS' if ok else 'FAIL':<5} {actual}")
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
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_int(value: Any) -> int:
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        x = float(s)
        if not math.isfinite(x) or abs(x - round(x)) > 1e-9:
            raise
        return int(round(x))


def parse_float(value: Any) -> float:
    x = float(str(value).strip())
    if not math.isfinite(x):
        raise ValueError(value)
    return x


def pipe_ints(value: Any) -> list[int]:
    s = str(value or "").strip()
    if not s:
        return []
    return [parse_int(x) for x in s.split("|") if str(x).strip()]


def manifest_output_map(manifest: dict[str, Any]) -> dict[str, str]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise RuntimeError("Manifest missing outputs list")
    out: dict[str, str] = {}
    for item in outputs:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid manifest output item")
        name = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid manifest output entry: {item}")
        if name in out:
            raise RuntimeError(f"Duplicate manifest output: {name}")
        out[name] = digest
    return out


def parse_way_sequence(value: Any) -> list[int]:
    seq = pipe_ints(value)
    if not seq:
        raise RuntimeError("Empty OSM way sequence")
    # GH10A already collapsed adjacent duplicate osm_way_id values.
    if any(a == b for a, b in zip(seq[:-1], seq[1:])):
        raise RuntimeError("GH10A route sequence is not adjacent-collapsed")
    return seq


def role_type_key(role: str, member_type: str) -> str:
    return f"{role}:{member_type}"


def normalized_member_type(raw: Any) -> str:
    s = str(raw).strip().lower()
    if s in {"w", "way"} or s.endswith(".way"):
        return "way"
    if s in {"n", "node"} or s.endswith(".node"):
        return "node"
    if s in {"r", "relation"} or s.endswith(".relation"):
        return "relation"
    return s


def restriction_for_car(tags: dict[str, str]) -> str:
    # Most-specific restriction first.
    for key in ("restriction:motorcar", "restriction:motor_vehicle", "restriction"):
        value = str(tags.get(key, "")).strip()
        if value:
            return value
    return ""


def car_is_exempt(tags: dict[str, str]) -> bool:
    raw = str(tags.get("except", "")).strip().lower()
    if not raw:
        return False
    tokens = {
        x.strip()
        for x in re.split(r"[;,]", raw)
        if x.strip()
    }
    return bool(tokens & {"motorcar", "motor_vehicle", "vehicle"})


def restriction_family(value: str) -> str:
    v = str(value).strip().lower()
    if v.startswith("no_"):
        return "NO"
    if v.startswith("only_"):
        return "ONLY"
    return "UNKNOWN"


def shared_nodes(way_nodes: dict[int, tuple[int, ...]], a: int, b: int) -> set[int]:
    if a not in way_nodes or b not in way_nodes:
        return set()
    return set(way_nodes[a]) & set(way_nodes[b])


def unique_shared_node(
    way_nodes: dict[int, tuple[int, ...]],
    a: int,
    b: int,
) -> tuple[str, int | None, list[int]]:
    common = sorted(shared_nodes(way_nodes, a, b))
    if len(common) == 1:
        return "UNIQUE", common[0], common
    if len(common) == 0:
        return "NONE", None, common
    return "MULTIPLE", None, common


def infer_missing_via_for_from(
    way_nodes: dict[int, tuple[int, ...]],
    from_way: int,
    allowed_to_ways: list[int],
) -> tuple[str, int | None, list[int]]:
    """
    For a malformed relation with no via member, infer the junction only when
    every available FROM->TO pair points to the same single physical OSM node.
    """
    if not allowed_to_ways:
        return "NO_TO", None, []
    all_nodes: set[int] = set()
    for to_way in allowed_to_ways:
        common = shared_nodes(way_nodes, from_way, to_way)
        if not common:
            return "PAIR_WITHOUT_SHARED_NODE", None, []
        all_nodes.update(common)
    if len(all_nodes) == 1:
        node = next(iter(all_nodes))
        return "UNIQUE", node, [node]
    return "AMBIGUOUS", None, sorted(all_nodes)


def transition_uses_node(
    way_nodes: dict[int, tuple[int, ...]],
    from_way: int,
    next_way: int,
    via_node: int,
) -> tuple[str, list[int]]:
    """
    Decide whether a consecutive OSM-way transition is uniquely located at the
    proposed via node.

    YES       -> the two ways share exactly that node.
    NO        -> the via node is not a shared node of the two ways.
    AMBIGUOUS -> they share the via node plus one or more additional nodes.
    """
    common = sorted(shared_nodes(way_nodes, from_way, next_way))
    if via_node not in common:
        return "NO", common
    if common == [via_node]:
        return "YES", common
    return "AMBIGUOUS", common


def member_roles(actual_relation: dict[str, Any]) -> dict[str, list[int]]:
    out = {
        "from_way": [],
        "to_way": [],
        "via_way": [],
        "via_node": [],
        "bad_from_type": [],
        "bad_to_type": [],
        "bad_via_type": [],
    }
    for m in actual_relation["members"]:
        role = str(m["role"])
        typ = str(m["type"])
        ref = int(m["ref"])
        if role == "from":
            if typ == "way":
                out["from_way"].append(ref)
            else:
                out["bad_from_type"].append(ref)
        elif role == "to":
            if typ == "way":
                out["to_way"].append(ref)
            else:
                out["bad_to_type"].append(ref)
        elif role == "via":
            if typ == "way":
                out["via_way"].append(ref)
            elif typ == "node":
                out["via_node"].append(ref)
            else:
                out["bad_via_type"].append(ref)
    return out


def relation_structure_class(roles: dict[str, list[int]]) -> str:
    if roles["bad_from_type"] or roles["bad_to_type"] or roles["bad_via_type"]:
        return "INVALID_MEMBER_TYPE"
    if not roles["from_way"] and not roles["to_way"]:
        return "MISSING_FROM_AND_TO"
    if not roles["from_way"]:
        return "MISSING_FROM"
    if not roles["to_way"]:
        return "MISSING_TO"
    if roles["via_way"] and roles["via_node"]:
        return "MIXED_VIA_TYPES"
    if len(roles["via_node"]) > 1:
        return "MULTIPLE_VIA_NODES"
    if roles["via_way"]:
        return "HAS_FROM_TO_VIA_WAY"
    if roles["via_node"]:
        return "HAS_FROM_TO_VIA_NODE"
    return "HAS_FROM_TO_NO_VIA"


def evaluate_route_relation(
    relation_id: int,
    restriction: str,
    roles: dict[str, list[int]],
    structure_class: str,
    route_seq: list[int],
    way_nodes: dict[int, tuple[int, ...]],
    tags: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Evaluate every occurrence of a FROM way on one selected route.

    The output can contain multiple observations because one relation FROM way
    may appear multiple times in a route sequence.
    """
    observations: list[dict[str, Any]] = []
    family = restriction_family(restriction)

    from_ways = list(roles["from_way"])
    to_ways = list(roles["to_way"])
    via_ways = list(roles["via_way"])
    via_nodes = list(roles["via_node"])

    # Relation-level exclusions / unresolved semantics.
    if car_is_exempt(tags):
        return [{
            "relation_id": relation_id,
            "classification": "CLEAR_CAR_EXEMPT",
            "severity": "CLEAR",
            "from_way": "",
            "next_way": "",
            "via_node": "",
            "detail": f"except={tags.get('except','')}",
        }]

    if family == "UNKNOWN":
        if set(route_seq) & set(from_ways):
            return [{
                "relation_id": relation_id,
                "classification": "UNRESOLVED_UNKNOWN_RESTRICTION_SEMANTICS",
                "severity": "UNRESOLVED",
                "from_way": "",
                "next_way": "",
                "via_node": "",
                "detail": f"restriction={restriction!r}",
            }]
        return []

    if structure_class in {
        "INVALID_MEMBER_TYPE",
        "MISSING_FROM_AND_TO",
        "MISSING_FROM",
        "MISSING_TO",
        "MIXED_VIA_TYPES",
        "MULTIPLE_VIA_NODES",
    }:
        if set(route_seq) & set(from_ways):
            return [{
                "relation_id": relation_id,
                "classification": f"UNRESOLVED_{structure_class}",
                "severity": "UNRESOLVED",
                "from_way": "",
                "next_way": "",
                "via_node": "",
                "detail": "",
            }]
        return []

    for i, from_way in enumerate(route_seq):
        if from_way not in from_ways:
            continue

        next_way = route_seq[i + 1] if i + 1 < len(route_seq) else None

        # ------------------------------------------------------------------
        # SAME-WAY U-TURN blind spot of collapsed OSM-way sequence
        # ------------------------------------------------------------------
        if "u_turn" in restriction.lower() and from_way in to_ways:
            # A U-turn on the same OSM way can be hidden by adjacent-value
            # collapsing. Do not pretend it is resolved.
            observations.append({
                "relation_id": relation_id,
                "classification": "UNRESOLVED_SAME_WAY_UTURN_SEQUENCE_LIMITATION",
                "severity": "UNRESOLVED",
                "from_way": from_way,
                "next_way": "" if next_way is None else next_way,
                "via_node": via_nodes[0] if len(via_nodes) == 1 else "",
                "detail": "collapsed osm_way_id sequence cannot prove/disprove same-way U-turn",
            })
            continue

        if next_way is None:
            observations.append({
                "relation_id": relation_id,
                "classification": "CLEAR_ROUTE_END_AFTER_FROM",
                "severity": "CLEAR",
                "from_way": from_way,
                "next_way": "",
                "via_node": "",
                "detail": "",
            })
            continue

        # ------------------------------------------------------------------
        # VIA-WAY restrictions
        # ------------------------------------------------------------------
        if structure_class == "HAS_FROM_TO_VIA_WAY":
            width = len(via_ways)
            via_slice = route_seq[i + 1:i + 1 + width]
            if via_slice != via_ways:
                observations.append({
                    "relation_id": relation_id,
                    "classification": "CLEAR_FROM_HIT_VIAWAY_PATTERN_NOT_ENTERED",
                    "severity": "CLEAR",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": "",
                    "detail": f"expected_via={'|'.join(map(str, via_ways))}",
                })
                continue

            exit_index = i + 1 + width
            if exit_index >= len(route_seq):
                observations.append({
                    "relation_id": relation_id,
                    "classification": "UNRESOLVED_ROUTE_END_AFTER_VIAWAY",
                    "severity": "UNRESOLVED",
                    "from_way": from_way,
                    "next_way": "",
                    "via_node": "",
                    "detail": "",
                })
                continue
            exit_way = route_seq[exit_index]

            if family == "NO":
                if exit_way in to_ways:
                    cls, sev = "VIOLATION_NO_VIAWAY_TO_MATCH", "VIOLATION_CANDIDATE"
                else:
                    cls, sev = "CLEAR_NO_VIAWAY_DIFFERENT_EXIT", "CLEAR"
            else:  # ONLY
                if exit_way in to_ways:
                    cls, sev = "CLEAR_ONLY_VIAWAY_ALLOWED_TO", "CLEAR"
                else:
                    cls, sev = "VIOLATION_ONLY_VIAWAY_OTHER_EXIT", "VIOLATION_CANDIDATE"

            observations.append({
                "relation_id": relation_id,
                "classification": cls,
                "severity": sev,
                "from_way": from_way,
                "next_way": exit_way,
                "via_node": "",
                "detail": f"via={'|'.join(map(str, via_ways))}",
            })
            continue

        # ------------------------------------------------------------------
        # VIA-NODE restrictions
        # ------------------------------------------------------------------
        if structure_class == "HAS_FROM_TO_VIA_NODE":
            via_node = via_nodes[0]
            if from_way not in way_nodes or next_way not in way_nodes:
                observations.append({
                    "relation_id": relation_id,
                    "classification": "UNRESOLVED_MISSING_WAY_TOPOLOGY",
                    "severity": "UNRESOLVED",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": via_node,
                    "detail": "",
                })
                continue

            use_state, common = transition_uses_node(
                way_nodes,
                from_way,
                next_way,
                via_node,
            )
            if use_state == "NO":
                observations.append({
                    "relation_id": relation_id,
                    "classification": "CLEAR_FROM_HIT_TRANSITION_NOT_AT_VIA_NODE",
                    "severity": "CLEAR",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": via_node,
                    "detail": f"shared_nodes={'|'.join(map(str, common))}",
                })
                continue
            if use_state == "AMBIGUOUS":
                observations.append({
                    "relation_id": relation_id,
                    "classification": "UNRESOLVED_MULTIPLE_SHARED_NODES_AT_VIA",
                    "severity": "UNRESOLVED",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": via_node,
                    "detail": f"shared_nodes={'|'.join(map(str, common))}",
                })
                continue

            # Transition is uniquely at the relation's via node.
            if family == "NO":
                if next_way in to_ways:
                    cls, sev = "VIOLATION_NO_VIANODE_TO_MATCH", "VIOLATION_CANDIDATE"
                else:
                    cls, sev = "CLEAR_NO_VIANODE_DIFFERENT_EXIT", "CLEAR"
            else:
                if next_way in to_ways:
                    cls, sev = "CLEAR_ONLY_VIANODE_ALLOWED_TO", "CLEAR"
                else:
                    cls, sev = "VIOLATION_ONLY_VIANODE_OTHER_EXIT", "VIOLATION_CANDIDATE"

            observations.append({
                "relation_id": relation_id,
                "classification": cls,
                "severity": sev,
                "from_way": from_way,
                "next_way": next_way,
                "via_node": via_node,
                "detail": "",
            })
            continue

        # ------------------------------------------------------------------
        # Missing-VIA restrictions: infer topology conservatively.
        # ------------------------------------------------------------------
        if structure_class == "HAS_FROM_TO_NO_VIA":
            if family == "NO":
                if next_way not in to_ways:
                    observations.append({
                        "relation_id": relation_id,
                        "classification": "CLEAR_NO_MISSINGVIA_DIFFERENT_EXIT",
                        "severity": "CLEAR",
                        "from_way": from_way,
                        "next_way": next_way,
                        "via_node": "",
                        "detail": "",
                    })
                    continue

                state, inferred, common = unique_shared_node(
                    way_nodes,
                    from_way,
                    next_way,
                )
                if state == "UNIQUE":
                    observations.append({
                        "relation_id": relation_id,
                        "classification": "VIOLATION_NO_MISSINGVIA_UNIQUE_DIRECT_JUNCTION",
                        "severity": "VIOLATION_CANDIDATE",
                        "from_way": from_way,
                        "next_way": next_way,
                        "via_node": inferred,
                        "detail": "",
                    })
                else:
                    observations.append({
                        "relation_id": relation_id,
                        "classification": f"UNRESOLVED_NO_MISSINGVIA_{state}_SHARED_NODE",
                        "severity": "UNRESOLVED",
                        "from_way": from_way,
                        "next_way": next_way,
                        "via_node": "",
                        "detail": f"shared_nodes={'|'.join(map(str, common))}",
                    })
                continue

            # ONLY restriction with missing via: infer the intended junction
            # from the relation's own FROM->allowed-TO topology.
            state, inferred_via, candidates = infer_missing_via_for_from(
                way_nodes,
                from_way,
                to_ways,
            )
            if state != "UNIQUE" or inferred_via is None:
                observations.append({
                    "relation_id": relation_id,
                    "classification": f"UNRESOLVED_ONLY_MISSINGVIA_INFERENCE_{state}",
                    "severity": "UNRESOLVED",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": "",
                    "detail": f"candidate_nodes={'|'.join(map(str, candidates))}",
                })
                continue

            use_state, common = transition_uses_node(
                way_nodes,
                from_way,
                next_way,
                inferred_via,
            )
            if use_state == "NO":
                observations.append({
                    "relation_id": relation_id,
                    "classification": "CLEAR_ONLY_MISSINGVIA_TRANSITION_ELSEWHERE",
                    "severity": "CLEAR",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": inferred_via,
                    "detail": f"shared_nodes={'|'.join(map(str, common))}",
                })
                continue
            if use_state == "AMBIGUOUS":
                observations.append({
                    "relation_id": relation_id,
                    "classification": "UNRESOLVED_ONLY_MISSINGVIA_MULTIPLE_SHARED_NODES",
                    "severity": "UNRESOLVED",
                    "from_way": from_way,
                    "next_way": next_way,
                    "via_node": inferred_via,
                    "detail": f"shared_nodes={'|'.join(map(str, common))}",
                })
                continue

            if next_way in to_ways:
                cls, sev = "CLEAR_ONLY_MISSINGVIA_ALLOWED_TO", "CLEAR"
            else:
                cls, sev = "VIOLATION_ONLY_MISSINGVIA_OTHER_EXIT", "VIOLATION_CANDIDATE"

            observations.append({
                "relation_id": relation_id,
                "classification": cls,
                "severity": sev,
                "from_way": from_way,
                "next_way": next_way,
                "via_node": inferred_via,
                "detail": "",
            })
            continue

    return observations


def helper_self_tests() -> None:
    ways = {
        10: (1, 2, 3),
        20: (3, 4),
        30: (3, 5),
        40: (2, 6),
        50: (7, 8),
    }

    # no_* via node: exact from->to at via => violation.
    rel_roles = {
        "from_way": [10], "to_way": [20], "via_way": [], "via_node": [3],
        "bad_from_type": [], "bad_to_type": [], "bad_via_type": [],
    }
    obs = evaluate_route_relation(
        1, "no_left_turn", rel_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 20], ways, {}
    )
    assert any(o["severity"] == "VIOLATION_CANDIDATE" for o in obs)

    # only_* via node: from->specified to is compliant.
    obs = evaluate_route_relation(
        2, "only_right_turn", rel_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 20], ways, {}
    )
    assert all(o["severity"] != "VIOLATION_CANDIDATE" for o in obs)

    # only_* via node: from->different exit at same via => violation.
    obs = evaluate_route_relation(
        3, "only_right_turn", rel_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 30], ways, {}
    )
    assert any(o["classification"] == "VIOLATION_ONLY_VIANODE_OTHER_EXIT" for o in obs)

    # Transition from the same FROM way elsewhere is irrelevant.
    obs = evaluate_route_relation(
        4, "no_left_turn", rel_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 40], ways, {}
    )
    assert any(o["classification"] == "CLEAR_FROM_HIT_TRANSITION_NOT_AT_VIA_NODE" for o in obs)

    # Missing via, no_* and unique direct junction => violation.
    rel_no_via = dict(rel_roles)
    rel_no_via["via_node"] = []
    obs = evaluate_route_relation(
        5, "no_left_turn", rel_no_via, "HAS_FROM_TO_NO_VIA",
        [10, 20], ways, {}
    )
    assert any(o["classification"] == "VIOLATION_NO_MISSINGVIA_UNIQUE_DIRECT_JUNCTION" for o in obs)

    # Missing via, only_* and specified allowed TO => compliant.
    obs = evaluate_route_relation(
        6, "only_right_turn", rel_no_via, "HAS_FROM_TO_NO_VIA",
        [10, 20], ways, {}
    )
    assert all(o["severity"] != "VIOLATION_CANDIDATE" for o in obs)

    # Missing via, only_* and other exit at inferred junction => violation.
    obs = evaluate_route_relation(
        7, "only_right_turn", rel_no_via, "HAS_FROM_TO_NO_VIA",
        [10, 30], ways, {}
    )
    assert any(o["classification"] == "VIOLATION_ONLY_MISSINGVIA_OTHER_EXIT" for o in obs)

    # Car exemption.
    obs = evaluate_route_relation(
        8, "no_left_turn", rel_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 20], ways, {"except": "motorcar;bus"}
    )
    assert obs[0]["classification"] == "CLEAR_CAR_EXEMPT"

    # Same-way U-turn limitation must never be silently cleared.
    uturn_roles = dict(rel_roles)
    uturn_roles["to_way"] = [10]
    obs = evaluate_route_relation(
        9, "no_u_turn", uturn_roles, "HAS_FROM_TO_VIA_NODE",
        [10, 30], ways, {}
    )
    assert any(o["severity"] == "UNRESOLVED" for o in obs)

    # Via-way no restriction.
    viaway_roles = {
        "from_way": [10], "to_way": [50], "via_way": [20, 30], "via_node": [],
        "bad_from_type": [], "bad_to_type": [], "bad_via_type": [],
    }
    obs = evaluate_route_relation(
        10, "no_straight_on", viaway_roles, "HAS_FROM_TO_VIA_WAY",
        [10, 20, 30, 50], ways, {}
    )
    assert any(o["severity"] == "VIOLATION_CANDIDATE" for o in obs)


# ======================================================================================
# Main
# ======================================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_10B_HELPER_SELF_TESTS = PASS")
        return 0

    root = Path(args.root)
    gh10a_dir = root / Path(GH10A_DIR_REL)
    gh09_dir = root / Path(GH09_DIR_REL)
    pbf = root / Path(ITALY_PBF_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name
        + "_STAGING_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 10B — TARGETED RESTRICTION TOPOLOGY + SEMANTIC AUDIT")
    print("=" * 124)
    print("OFFLINE / READ-ONLY PBF SCAN / NO GRAPHHOPPER / NO B5 / NO IMPORT")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    # ------------------------------------------------------------------
    # A. Strict lineage
    # ------------------------------------------------------------------
    print("A. STRICT LINEAGE / PRE-FLIGHT")

    strict_hash(
        "GH10A summary",
        gh10a_dir / GH10A_SUMMARY,
        GH10A_SUMMARY_SHA256,
    )
    strict_hash(
        "GH10A manifest",
        gh10a_dir / GH10A_MANIFEST,
        GH10A_MANIFEST_SHA256,
    )
    strict_hash(
        "GH10A maneuver candidates",
        gh10a_dir / GH10A_MANEUVER,
        GH10A_MANEUVER_SHA256,
    )
    strict_hash(
        "GH09 summary",
        gh09_dir / GH09_SUMMARY,
        GH09_SUMMARY_SHA256,
    )
    strict_hash("Italy PBF", pbf, ITALY_PBF_SHA256)

    gh10a_summary = read_json(gh10a_dir / GH10A_SUMMARY)
    if gh10a_summary.get("verdict") != "PASS":
        raise RuntimeError("GH10A is not PASS")
    if int(gh10a_summary["GH09_candidate_relations"]) != EXPECTED_GH09_RELATIONS:
        raise RuntimeError("GH10A GH09 candidate count drift")
    if int(gh10a_summary["stage2_maneuver_candidate_relations"]) != EXPECTED_GH10A_STAGE2_RELATIONS:
        raise RuntimeError("GH10A stage2 relation count drift")
    if int(gh10a_summary["stage2_route_relation_pairs"]) != EXPECTED_GH10A_STAGE2_PAIRS:
        raise RuntimeError("GH10A stage2 pair count drift")

    gh10a_manifest = read_json(gh10a_dir / GH10A_MANIFEST)
    gh10a_outputs = manifest_output_map(gh10a_manifest)
    for filename, digest in sorted(gh10a_outputs.items()):
        path = gh10a_dir / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != digest:
            raise RuntimeError(f"GH10A output changed: {filename}")
    print(f"GH10A outputs verified          = {len(gh10a_outputs)}")

    if GH10A_ROUTE_WAYS not in gh10a_outputs:
        raise RuntimeError("GH10A route-way sequence CSV missing from manifest")
    if GH10A_REL_STRUCTURE not in gh10a_outputs:
        raise RuntimeError("GH10A relation structure CSV missing from manifest")

    try:
        import osmium  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "pyosmium/osmium is required in the official thesis venv for this "
            "read-only PBF audit. Do not install ad-hoc packages elsewhere."
        ) from exc

    print(f"osmium import                   = PASS")
    print("helper semantic tests           = PASS")
    print("GraphHopper server              = NOT_STARTED")
    print("PBF import                      = NOT_STARTED")
    print("PBF access                      = READ_ONLY_SCAN")

    # ------------------------------------------------------------------
    # B. Load GH10A route sequences + 132 relation IDs
    # ------------------------------------------------------------------
    print()
    print("B. GH10A ROUTE / RELATION MATERIALIZATION")

    route_rows, _ = read_csv(gh10a_dir / GH10A_ROUTE_WAYS)
    if len(route_rows) != EXPECTED_SELECTED_ROUTES:
        raise RuntimeError(f"GH10A route rows={len(route_rows)}")

    routes: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in route_rows:
        key = (
            str(row["destination_key"]),
            str(row["geo_id"]),
            str(row["direction"]),
        )
        if key in routes:
            raise RuntimeError(f"Duplicate route key: {key}")
        routes[key] = {
            "destination_key": key[0],
            "geo_id": key[1],
            "direction": key[2],
            "dest_COMUNE": str(row["dest_COMUNE"]),
            "gateway_id": str(row["gateway_id"]),
            "selected_b1_relations": parse_int(row["selected_b1_relations"]),
            "Pendolari_raw_sum": parse_float(row["Pendolari_raw_sum"]),
            "flow_daily_sum": parse_float(row["flow_daily_sum"]),
            "sequence": parse_way_sequence(row["osm_way_sequence"]),
        }

    rel_rows, _ = read_csv(gh10a_dir / GH10A_REL_STRUCTURE)
    if len(rel_rows) != EXPECTED_GH09_RELATIONS:
        raise RuntimeError(f"GH10A relation structure rows={len(rel_rows)}")

    relation_log_meta = {
        parse_int(r["relation_id"]): r
        for r in rel_rows
    }
    relation_ids = set(relation_log_meta)
    if len(relation_ids) != EXPECTED_GH09_RELATIONS:
        raise RuntimeError("Duplicate GH10A relation IDs")

    print(f"selected route sequences        = {len(routes):,}")
    print(f"target ignored relations        = {len(relation_ids)}")

    # ------------------------------------------------------------------
    # C. PBF pass 1: exact relation objects
    # ------------------------------------------------------------------
    print()
    print("C. PBF PASS 1/2 — EXACT 132 RELATION OBJECTS")

    class RelationHandler(osmium.SimpleHandler):
        def __init__(self, wanted: set[int]):
            super().__init__()
            self.wanted = wanted
            self.rows: dict[int, dict[str, Any]] = {}

        def relation(self, r):
            rid = int(r.id)
            if rid not in self.wanted:
                return
            tags = {str(t.k): str(t.v) for t in r.tags}
            members = []
            for m in r.members:
                members.append({
                    "role": str(m.role),
                    "type": normalized_member_type(m.type),
                    "ref": int(m.ref),
                })
            self.rows[rid] = {
                "relation_id": rid,
                "tags": tags,
                "members": members,
            }

    rh = RelationHandler(relation_ids)
    rh.apply_file(str(pbf), locations=False)

    missing_relations = relation_ids - set(rh.rows)
    if missing_relations:
        raise RuntimeError(
            f"Target relation IDs absent from frozen Italy PBF: "
            f"{sorted(missing_relations)[:20]}"
        )

    actual_relations = rh.rows
    print(f"relations found in PBF          = {len(actual_relations)}/{len(relation_ids)}")

    # Build exact roles and collect relation member ways.
    relation_roles: dict[int, dict[str, list[int]]] = {}
    relation_structures: dict[int, str] = {}
    needed_way_ids: set[int] = set()

    for rid, rel in actual_relations.items():
        roles = member_roles(rel)
        structure = relation_structure_class(roles)
        relation_roles[rid] = roles
        relation_structures[rid] = structure
        needed_way_ids.update(roles["from_way"])
        needed_way_ids.update(roles["to_way"])
        needed_way_ids.update(roles["via_way"])

    # Add route-neighbor ways around every target FROM-way occurrence. These are
    # needed to evaluate ONLY restrictions correctly.
    all_from_way_ids = {
        wid
        for roles in relation_roles.values()
        for wid in roles["from_way"]
    }
    for route in routes.values():
        seq = route["sequence"]
        for i, wid in enumerate(seq):
            if wid not in all_from_way_ids:
                continue
            needed_way_ids.add(wid)
            if i + 1 < len(seq):
                needed_way_ids.add(seq[i + 1])

    print(f"needed OSM ways for topology    = {len(needed_way_ids):,}")

    # ------------------------------------------------------------------
    # D. PBF pass 2: exact node refs for only needed ways
    # ------------------------------------------------------------------
    print()
    print("D. PBF PASS 2/2 — TARGET WAY NODE-REFERENCE TOPOLOGY")

    class WayHandler(osmium.SimpleHandler):
        def __init__(self, wanted: set[int]):
            super().__init__()
            self.wanted = wanted
            self.nodes: dict[int, tuple[int, ...]] = {}

        def way(self, w):
            wid = int(w.id)
            if wid not in self.wanted:
                return
            self.nodes[wid] = tuple(int(n.ref) for n in w.nodes)

    wh = WayHandler(needed_way_ids)
    wh.apply_file(str(pbf), locations=False)

    missing_ways = needed_way_ids - set(wh.nodes)
    if missing_ways:
        raise RuntimeError(
            f"Needed ways absent from frozen Italy PBF: "
            f"{sorted(missing_ways)[:30]}"
        )

    way_nodes = wh.nodes
    print(f"needed ways found               = {len(way_nodes)}/{len(needed_way_ids)}")

    # ------------------------------------------------------------------
    # E. Materialize exact PBF relation structures
    # ------------------------------------------------------------------
    print()
    print("E. EXACT RELATION STRUCTURE AUDIT")

    staging.mkdir(parents=True, exist_ok=False)

    relation_pbf_rows = []
    structure_counts = Counter()
    restriction_family_counts = Counter()

    for rid in sorted(relation_ids):
        rel = actual_relations[rid]
        roles = relation_roles[rid]
        structure = relation_structures[rid]
        tags = rel["tags"]
        restriction = restriction_for_car(tags)
        family = restriction_family(restriction)

        structure_counts[structure] += 1
        restriction_family_counts[family] += 1

        relation_pbf_rows.append({
            "relation_id": rid,
            "warning_reason": relation_log_meta[rid]["reason"],
            "restriction_for_car": restriction,
            "restriction_family": family,
            "except": tags.get("except", ""),
            "car_exempt": car_is_exempt(tags),
            "structure_class_pbf": structure,
            "from_way_ids": "|".join(map(str, roles["from_way"])),
            "via_way_ids": "|".join(map(str, roles["via_way"])),
            "via_node_ids": "|".join(map(str, roles["via_node"])),
            "to_way_ids": "|".join(map(str, roles["to_way"])),
            "bad_from_type_refs": "|".join(map(str, roles["bad_from_type"])),
            "bad_to_type_refs": "|".join(map(str, roles["bad_to_type"])),
            "bad_via_type_refs": "|".join(map(str, roles["bad_via_type"])),
            "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
        })

    for k, v in sorted(structure_counts.items()):
        print(f"  {k:<34} {v:4d}")
    print("restriction families:")
    for k, v in sorted(restriction_family_counts.items()):
        print(f"  {k:<34} {v:4d}")

    write_csv(
        staging / RELATION_PBF_CSV,
        relation_pbf_rows,
        [
            "relation_id", "warning_reason", "restriction_for_car",
            "restriction_family", "except", "car_exempt",
            "structure_class_pbf", "from_way_ids", "via_way_ids",
            "via_node_ids", "to_way_ids", "bad_from_type_refs",
            "bad_to_type_refs", "bad_via_type_refs", "tags_json",
        ],
    )

    # ------------------------------------------------------------------
    # F. Semantics-correct route audit across all 132 relations
    # ------------------------------------------------------------------
    print()
    print("F. SEMANTICS-CORRECT SELECTED-ROUTE AUDIT")

    # Invert FROM way -> relation IDs to keep this targeted.
    from_way_to_relations: defaultdict[int, set[int]] = defaultdict(set)
    for rid, roles in relation_roles.items():
        for wid in roles["from_way"]:
            from_way_to_relations[wid].add(rid)

    route_audit_rows: list[dict[str, Any]] = []
    relation_severities: defaultdict[int, set[str]] = defaultdict(set)
    relation_class_counts: defaultdict[int, Counter[str]] = defaultdict(Counter)

    for route_key, route in sorted(routes.items()):
        seq = route["sequence"]
        candidate_relation_ids: set[int] = set()
        for wid in set(seq):
            candidate_relation_ids.update(from_way_to_relations.get(wid, set()))

        for rid in sorted(candidate_relation_ids):
            rel = actual_relations[rid]
            roles = relation_roles[rid]
            structure = relation_structures[rid]
            restriction = restriction_for_car(rel["tags"])

            observations = evaluate_route_relation(
                rid,
                restriction,
                roles,
                structure,
                seq,
                way_nodes,
                rel["tags"],
            )
            for obs in observations:
                severity = str(obs["severity"])
                relation_severities[rid].add(severity)
                relation_class_counts[rid][str(obs["classification"])] += 1

                route_audit_rows.append({
                    "relation_id": rid,
                    "restriction_for_car": restriction,
                    "structure_class_pbf": structure,
                    "warning_reason": relation_log_meta[rid]["reason"],
                    "severity": severity,
                    "classification": obs["classification"],
                    "destination_key": route["destination_key"],
                    "dest_COMUNE": route["dest_COMUNE"],
                    "gateway_id": route["gateway_id"],
                    "geo_id": route["geo_id"],
                    "direction": route["direction"],
                    "selected_b1_relations": route["selected_b1_relations"],
                    "Pendolari_raw_sum": route["Pendolari_raw_sum"],
                    "flow_daily_sum": route["flow_daily_sum"],
                    "from_way": obs["from_way"],
                    "next_way": obs["next_way"],
                    "via_node": obs["via_node"],
                    "detail": obs["detail"],
                })

    route_fieldnames = [
        "relation_id", "restriction_for_car", "structure_class_pbf",
        "warning_reason", "severity", "classification",
        "destination_key", "dest_COMUNE", "gateway_id", "geo_id", "direction",
        "selected_b1_relations", "Pendolari_raw_sum", "flow_daily_sum",
        "from_way", "next_way", "via_node", "detail",
    ]
    write_csv(staging / ROUTE_AUDIT_CSV, route_audit_rows, route_fieldnames)

    # Relation-level result.
    relation_result_rows = []
    violation_relation_ids = []
    unresolved_relation_ids = []

    for rid in sorted(relation_ids):
        severities = relation_severities.get(rid, set())
        classes = relation_class_counts.get(rid, Counter())

        if "VIOLATION_CANDIDATE" in severities:
            result = "VIOLATION_CANDIDATE"
            violation_relation_ids.append(rid)
        elif "UNRESOLVED" in severities:
            result = "UNRESOLVED"
            unresolved_relation_ids.append(rid)
        else:
            result = "CLEAR"

        rel = actual_relations[rid]
        roles = relation_roles[rid]
        relation_result_rows.append({
            "relation_id": rid,
            "result": result,
            "restriction_for_car": restriction_for_car(rel["tags"]),
            "structure_class_pbf": relation_structures[rid],
            "warning_reason": relation_log_meta[rid]["reason"],
            "route_observations": sum(classes.values()),
            "classification_counts_json": json.dumps(
                dict(sorted(classes.items())),
                sort_keys=True,
            ),
            "from_way_ids": "|".join(map(str, roles["from_way"])),
            "via_way_ids": "|".join(map(str, roles["via_way"])),
            "via_node_ids": "|".join(map(str, roles["via_node"])),
            "to_way_ids": "|".join(map(str, roles["to_way"])),
        })

    result_fieldnames = [
        "relation_id", "result", "restriction_for_car",
        "structure_class_pbf", "warning_reason", "route_observations",
        "classification_counts_json", "from_way_ids", "via_way_ids",
        "via_node_ids", "to_way_ids",
    ]
    write_csv(
        staging / RELATION_RESULT_CSV,
        relation_result_rows,
        result_fieldnames,
    )

    violation_rows = [
        r for r in route_audit_rows
        if r["severity"] == "VIOLATION_CANDIDATE"
    ]
    unresolved_rows = [
        r for r in route_audit_rows
        if r["severity"] == "UNRESOLVED"
    ]
    write_csv(staging / VIOLATION_CSV, violation_rows, route_fieldnames)
    write_csv(staging / UNRESOLVED_CSV, unresolved_rows, route_fieldnames)

    global_class_counts = Counter(r["classification"] for r in route_audit_rows)
    print(f"route-relation observations     = {len(route_audit_rows):,}")
    print(f"violation candidate relations   = {len(violation_relation_ids)}")
    print(f"violation candidate route rows  = {len(violation_rows)}")
    print(f"unresolved relations            = {len(unresolved_relation_ids)}")
    print(f"unresolved route rows           = {len(unresolved_rows)}")
    print("top classifications:")
    for cls, n in global_class_counts.most_common(20):
        print(f"  {cls:<58} {n:6d}")

    # ------------------------------------------------------------------
    # G. Integrity / gate
    # ------------------------------------------------------------------
    print()
    print("G. INTEGRITY / NEXT GATE")

    # Re-verify every GH10A output after the read-only PBF audit.
    for filename, digest in sorted(gh10a_outputs.items()):
        if sha256(gh10a_dir / filename) != digest:
            raise RuntimeError(f"GH10A output changed during GH10B: {filename}")

    if violation_relation_ids:
        verdict = "NOT_READY"
        next_gate = "TARGETED_RESTRICTION_CORRECTION_FEASIBILITY"
    elif unresolved_relation_ids:
        verdict = "NOT_READY"
        next_gate = "TARGETED_EDGE_LEVEL_RESTRICTION_RESOLUTION"
    else:
        verdict = "PASS"
        next_gate = "B1_FINAL_GATE_REASSESSMENT"

    summary = {
        "schema": "B1_EXT_GH_10B_TARGETED_RESTRICTION_TOPOLOGY_SEMANTIC_SUMMARY_V01",
        "verdict": verdict,
        "GH09_candidate_relations": EXPECTED_GH09_RELATIONS,
        "GH10A_stage2_relations": EXPECTED_GH10A_STAGE2_RELATIONS,
        "GH10A_stage2_pairs": EXPECTED_GH10A_STAGE2_PAIRS,
        "selected_routes": len(routes),
        "PBF_relations_found": len(actual_relations),
        "PBF_needed_ways_found": len(way_nodes),
        "relation_structure_counts": dict(sorted(structure_counts.items())),
        "restriction_family_counts": dict(sorted(restriction_family_counts.items())),
        "route_observation_count": len(route_audit_rows),
        "route_classification_counts": dict(sorted(global_class_counts.items())),
        "violation_candidate_relations": len(violation_relation_ids),
        "violation_candidate_relation_ids": violation_relation_ids,
        "violation_candidate_route_rows": len(violation_rows),
        "unresolved_relations": len(unresolved_relation_ids),
        "unresolved_relation_ids": unresolved_relation_ids,
        "unresolved_route_rows": len(unresolved_rows),
        "semantic_correction_vs_GH10A": (
            "NO_* prohibits the specified maneuver; ONLY_* allows its specified "
            "TO maneuver and is violated only by another exit from the same "
            "verified restricted junction."
        ),
        "integrity": {
            "Italy_PBF_sha256": sha256(pbf),
            "GH10A_outputs_modified": False,
            "GraphHopper_server": "NOT_STARTED",
            "PBF_import": "NOT_STARTED",
            "PBF_scan": "READ_ONLY",
            "B5_routing": "NOT_STARTED",
        },
        "next_gate": next_gate,
    }
    summary_path = staging / SUMMARY_JSON
    write_json(summary_path, summary)

    outputs = [
        staging / RELATION_PBF_CSV,
        staging / ROUTE_AUDIT_CSV,
        staging / RELATION_RESULT_CSV,
        staging / VIOLATION_CSV,
        staging / UNRESOLVED_CSV,
        summary_path,
    ]

    manifest = {
        "schema": "B1_EXT_GH_10B_TARGETED_RESTRICTION_TOPOLOGY_SEMANTIC_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "inputs": {
            "GH10A_manifest": {
                "path": str(gh10a_dir / GH10A_MANIFEST),
                "sha256": sha256(gh10a_dir / GH10A_MANIFEST),
            },
            "GH10A_summary": {
                "path": str(gh10a_dir / GH10A_SUMMARY),
                "sha256": sha256(gh10a_dir / GH10A_SUMMARY),
            },
            "Italy_PBF": {
                "path": str(pbf),
                "sha256": sha256(pbf),
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
        "violation_candidate_relation_ids": violation_relation_ids,
        "unresolved_relation_ids": unresolved_relation_ids,
        "next_gate": next_gate,
    }
    manifest_path = staging / MANIFEST_JSON
    write_json(manifest_path, manifest)

    staging.rename(final_dir)

    print("GH10A outputs modified          = NO")
    print("GraphHopper server              = NOT_STARTED")
    print("PBF import                      = NOT_STARTED")
    print("B5 routing                      = NOT_STARTED")
    print()
    print("=" * 124)
    print(f"B1_EXT_GH_10B_TARGETED_RESTRICTION_TOPOLOGY_SEMANTIC_AUDIT = {verdict}")
    print(f"GH09_CANDIDATE_RELATIONS = {EXPECTED_GH09_RELATIONS}")
    print(f"GH10A_STAGE2_RELATIONS = {EXPECTED_GH10A_STAGE2_RELATIONS}")
    print(f"GH10A_STAGE2_PAIRS = {EXPECTED_GH10A_STAGE2_PAIRS}")
    print(f"SELECTED_ROUTES_AUDITED = {len(routes)}")
    print(f"VIOLATION_CANDIDATE_RELATIONS = {len(violation_relation_ids)}")
    print(f"VIOLATION_CANDIDATE_ROUTE_ROWS = {len(violation_rows)}")
    print(f"UNRESOLVED_RELATIONS = {len(unresolved_relation_ids)}")
    print(f"UNRESOLVED_ROUTE_ROWS = {len(unresolved_rows)}")
    print("GH10A_OUTPUTS_MODIFIED = NO")
    print("GRAPHHOPPER_SERVER = NOT_STARTED")
    print("PBF_IMPORT = NOT_STARTED")
    print("PBF_SCAN = READ_ONLY")
    print("B5_ROUTING = NOT_STARTED")
    print(f"NEXT_GATE = {next_gate}")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print("=== RUN COMPLETATA ===")

    if verdict == "PASS":
        print(
            "HARD STOP — RESTRICTION BLOCKER CLEARED AT SEMANTIC+TOPOLOGY LEVEL; "
            "FINAL B1 GATE REASSESSMENT REQUIRED."
        )
    else:
        print(
            "HARD STOP — DO NOT RETURN TO CHAT MADRE; "
            f"NEXT TARGETED GATE = {next_gate}"
        )

    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
