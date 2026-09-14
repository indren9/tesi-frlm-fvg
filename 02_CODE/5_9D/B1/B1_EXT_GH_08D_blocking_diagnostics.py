#!/usr/bin/env python3
"""
B1-EXT-GH 08D — BLOCKING DIAGNOSTICS

Purpose
-------
Diagnose GH08 NOT_READY without rerunning GraphHopper or B5 routing.

This script is strictly read-only on:
- GH08 materialized outputs
- frozen project inputs

It identifies whether the GH08 unrouted B1 relations are caused by
destination-level external graph disconnection, and materializes only
diagnostic CSV/JSON artifacts in a new staging directory.

NO GraphHopper server.
NO PBF import.
NO B5 Dijkstra.
NO modification of GH08 or frozen artifacts.
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
from typing import Iterable

ROOT_DEFAULT = r"C:\Tesi"

GH08_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\hybrid_routing_materialization_v01"
)
OUT_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gh08_blocking_diagnostics_v01"
)

GH08_MANIFEST = "B1_EXT_GH_08_hybrid_routing_materialization_manifest_v01.json"
GH08_SUMMARY = "B1_EXT_GH_08_hybrid_routing_materialization_summary_v01.json"
B1_NORMALIZED = "B1_EXT_GH_08_b1_normalized_v01.csv"
EXTERNAL_CACHE = "B1_EXT_GH_08_external_crossing_route_cache_v01.csv"
IE_ROUTING = "B1_EXT_GH_08_IE_routing_v01.csv"
EI_ROUTING = "B1_EXT_GH_08_EI_routing_v01.csv"

EXPECTED_GH08_MANIFEST_SHA256 = (
    "cc47279a8a47b9c69621d1ae71af12adfca48c230b21c0db434b465c8015512c"
)
EXPECTED_GH08_SUMMARY_SHA256 = (
    "2240eb16c11e3b0732814b8f17d9f3f8efcaa94302851948213137a8b411a1f5"
)
EXPECTED_IE_SHA256 = (
    "86e50fdeea4184d80d588f634c42474d312e66c1f26769dafea0de5e7e0de2c3"
)
EXPECTED_EI_SHA256 = (
    "10ee96f5f0ec66df2c8c8414e5b9e83bebfc3e7c6acfc6bbdc587d11a08f6203"
)

EXPECTED_RELATIONS = 2895
EXPECTED_DESTINATIONS = 368
EXPECTED_CROSSINGS = 49
EXPECTED_GATEWAYS = 12
EXPECTED_RAW_FLOW = 14458.0
DAILY_FACTOR = 0.42855
EXPECTED_DAILY_EACH = 6195.97590

# These values are algebraically implied by the GH08 console report:
# 1862 = 19 * 49 * 2.
EXPECTED_FULLY_DISCONNECTED_DESTINATIONS = 19
EXPECTED_UNREACHABLE_RELATIONS_EACH = 162
EXPECTED_EXTERNAL_UNREACHABLE_CANDIDATES = 1862
EXPECTED_MISSING_RAW_FLOW = 782.0
EXPECTED_MISSING_DAILY_FLOW = 335.12610

FLOAT_TOL = 1e-6

DEST_CSV = "B1_EXT_GH_08D_unreachable_destinations_v01.csv"
REL_CSV = "B1_EXT_GH_08D_unreachable_relations_v01.csv"
ERR_CSV = "B1_EXT_GH_08D_error_signatures_v01.csv"
SUMMARY_JSON = "B1_EXT_GH_08D_blocking_diagnostics_summary_v01.json"
MANIFEST_JSON = "B1_EXT_GH_08D_blocking_diagnostics_manifest_v01.json"


def sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return obj


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        if not rows:
            raise RuntimeError(f"Cannot infer CSV columns for empty rows: {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_float(value: object) -> float:
    if value is None:
        raise ValueError("None")
    x = float(str(value).strip())
    if not math.isfinite(x):
        raise ValueError(value)
    return x


def parse_int(value: object) -> int:
    if value is None:
        raise ValueError("None")
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        x = float(s)
        if not math.isfinite(x) or abs(x - round(x)) > 1e-9:
            raise
        return int(round(x))


def normalize_error_signature(error: object) -> str:
    text = str(error or "").strip()
    text = re.sub(r"\s+", " ", text)
    # Remove volatile coordinate-like decimal noise while preserving semantics.
    # We do not use this transformed signature as evidence of exact equality;
    # it is only for grouping diagnostics.
    return text[:700]


def assert_close(actual: float, expected: float, label: str, tol: float = FLOAT_TOL) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(f"{label}: {actual} != expected {expected} (tol={tol})")


def output_hash_map_from_manifest(manifest: dict) -> dict[str, str]:
    out = {}
    rows = manifest.get("outputs")
    if not isinstance(rows, list):
        raise RuntimeError("GH08 manifest missing outputs list")
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid GH08 manifest output entry")
        name = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid GH08 manifest output entry: {item}")
        if name in out:
            raise RuntimeError(f"Duplicate GH08 manifest output: {name}")
        out[name] = digest
    return out


def helper_self_tests() -> None:
    if normalize_error_signature(" a\n  b\tc ") != "a b c":
        raise AssertionError("normalize_error_signature self-test failed")
    assert_close(782.0 * DAILY_FACTOR, EXPECTED_MISSING_DAILY_FLOW, "daily factor self-test")
    if EXPECTED_FULLY_DISCONNECTED_DESTINATIONS * EXPECTED_CROSSINGS * 2 != EXPECTED_EXTERNAL_UNREACHABLE_CANDIDATES:
        raise AssertionError("candidate-count identity self-test failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_08D_HELPER_SELF_TESTS = PASS")
        return 0

    root = Path(args.root)
    gh08 = root / Path(GH08_DIR_REL)
    final_dir = root / Path(OUT_DIR_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 124)
    print("B1-EXT-GH 08D — BLOCKING DIAGNOSTICS")
    print("=" * 124)
    print("READ-ONLY GH08 OUTPUTS / NO GH SERVER / NO B5 ROUTING / NO PBF IMPORT")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(f"Unexpected staging exists: {staging}")
    if not gh08.is_dir():
        raise FileNotFoundError(f"Missing GH08 output directory: {gh08}")

    manifest_path = gh08 / GH08_MANIFEST
    summary_path = gh08 / GH08_SUMMARY
    b1_path = gh08 / B1_NORMALIZED
    external_path = gh08 / EXTERNAL_CACHE
    ie_path = gh08 / IE_ROUTING
    ei_path = gh08 / EI_ROUTING

    for p in (manifest_path, summary_path, b1_path, external_path, ie_path, ei_path):
        if not p.is_file():
            raise FileNotFoundError(p)

    print("A. GH08 EVIDENCE IDENTITY")
    checks = [
        ("gh08_manifest", manifest_path, EXPECTED_GH08_MANIFEST_SHA256),
        ("gh08_summary", summary_path, EXPECTED_GH08_SUMMARY_SHA256),
        ("ie_routing", ie_path, EXPECTED_IE_SHA256),
        ("ei_routing", ei_path, EXPECTED_EI_SHA256),
    ]
    for label, path, expected in checks:
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"{label} SHA256 mismatch: {actual} != {expected}")
        print(f"{label:<24} PASS  {actual}")

    manifest = read_json(manifest_path)
    summary = read_json(summary_path)
    output_hashes = output_hash_map_from_manifest(manifest)

    # Verify every GH08 materialized output that is still present.
    verified_manifest_outputs = 0
    for filename, expected in sorted(output_hashes.items()):
        path = gh08 / filename
        if not path.is_file():
            raise FileNotFoundError(f"GH08 manifest output missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"GH08 output changed: {filename}")
        verified_manifest_outputs += 1
    print(f"manifest outputs verified = {verified_manifest_outputs}")
    print(f"GH08 verdict              = {summary.get('verdict')}")
    print(f"GH08 blocking reasons     = {summary.get('blocking_reasons')}")
    if summary.get("verdict") != "NOT_READY":
        raise RuntimeError("GH08 summary is not NOT_READY; diagnostic contract mismatch")

    print()
    print("B. LOAD MATERIALIZED ROUTING EVIDENCE")
    b1 = read_csv(b1_path)
    external = read_csv(external_path)
    ie = read_csv(ie_path)
    ei = read_csv(ei_path)

    if len(b1) != EXPECTED_RELATIONS:
        raise RuntimeError(f"B1 rows {len(b1)} != {EXPECTED_RELATIONS}")
    if len(ie) != EXPECTED_RELATIONS or len(ei) != EXPECTED_RELATIONS:
        raise RuntimeError("IE/EI routing row count mismatch")
    expected_external_rows = EXPECTED_DESTINATIONS * EXPECTED_CROSSINGS * 2
    if len(external) != expected_external_rows:
        raise RuntimeError(f"External cache rows {len(external)} != {expected_external_rows}")

    unique_dest = {r["destination_key"] for r in b1}
    if len(unique_dest) != EXPECTED_DESTINATIONS:
        raise RuntimeError(f"Unique destinations {len(unique_dest)} != {EXPECTED_DESTINATIONS}")

    raw_total = sum(parse_float(r["Pendolari_raw"]) for r in b1)
    daily_total = sum(parse_float(r["flow_daily"]) for r in b1)
    assert_close(raw_total, EXPECTED_RAW_FLOW, "B1 raw total")
    assert_close(daily_total, EXPECTED_DAILY_EACH, "B1 daily total")
    print(f"B1 relations              = {len(b1):,}")
    print(f"unique destinations       = {len(unique_dest):,}")
    print(f"external cache rows       = {len(external):,}")
    print(f"B1 raw flow               = {raw_total:.5f}")
    print(f"B1 daily flow             = {daily_total:.5f}")

    print()
    print("C. DESTINATION-LEVEL EXTERNAL CONNECTIVITY")

    # destination -> direction -> rows
    ext_by_dest_dir: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in external:
        ext_by_dest_dir[r["destination_key"]][r["direction"]].append(r)

    fully_disconnected: set[str] = set()
    partial_disconnected: set[str] = set()
    destination_diag_rows: list[dict[str, object]] = []

    # B1 destination metadata / flow
    b1_by_dest: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in b1:
        b1_by_dest[r["destination_key"]].append(r)

    for key in sorted(unique_dest):
        dirs = ext_by_dest_dir.get(key, {})
        ie_ext = dirs.get("IE", [])
        ei_ext = dirs.get("EI", [])
        if len(ie_ext) != EXPECTED_CROSSINGS or len(ei_ext) != EXPECTED_CROSSINGS:
            raise RuntimeError(
                f"Destination {key}: expected {EXPECTED_CROSSINGS} external rows per direction, "
                f"got IE={len(ie_ext)} EI={len(ei_ext)}"
            )

        ie_counts = Counter(r["status"] for r in ie_ext)
        ei_counts = Counter(r["status"] for r in ei_ext)
        ie_all_unreach = ie_counts.get("UNREACHABLE", 0) == EXPECTED_CROSSINGS
        ei_all_unreach = ei_counts.get("UNREACHABLE", 0) == EXPECTED_CROSSINGS

        if ie_all_unreach and ei_all_unreach:
            fully_disconnected.add(key)
        elif ie_counts.get("UNREACHABLE", 0) or ei_counts.get("UNREACHABLE", 0):
            partial_disconnected.add(key)

    external_unreachable = sum(1 for r in external if r["status"] == "UNREACHABLE")
    external_errors = sum(1 for r in external if r["status"] == "ERROR")
    external_snap_flags = sum(1 for r in external if r["status"] == "SNAP_FLAG")
    external_pass = sum(1 for r in external if r["status"] == "PASS")

    print(f"fully disconnected destinations = {len(fully_disconnected)}")
    print(f"partially disconnected dest     = {len(partial_disconnected)}")
    print(f"external PASS candidates        = {external_pass:,}")
    print(f"external UNREACHABLE candidates = {external_unreachable:,}")
    print(f"external ERROR candidates       = {external_errors:,}")
    print(f"external SNAP_FLAG candidates   = {external_snap_flags:,}")

    if len(fully_disconnected) != EXPECTED_FULLY_DISCONNECTED_DESTINATIONS:
        raise RuntimeError(
            f"Expected {EXPECTED_FULLY_DISCONNECTED_DESTINATIONS} fully disconnected destinations, "
            f"got {len(fully_disconnected)}"
        )
    if partial_disconnected:
        raise RuntimeError(
            f"Unexpected partial destination disconnection: {len(partial_disconnected)} destinations"
        )
    if external_unreachable != EXPECTED_EXTERNAL_UNREACHABLE_CANDIDATES:
        raise RuntimeError(
            f"External unreachable count {external_unreachable} != "
            f"{EXPECTED_EXTERNAL_UNREACHABLE_CANDIDATES}"
        )
    if external_errors != 0 or external_snap_flags != 0:
        raise RuntimeError("Technical/snap failures exist; not a pure connectivity blocker")

    print()
    print("D. UNROUTED B1 RELATIONS / FLOW CONSERVATION")

    ie_unreach_rows = [r for r in ie if r.get("route_status") == "UNREACHABLE"]
    ei_unreach_rows = [r for r in ei if r.get("route_status") == "UNREACHABLE"]
    ie_unreach_keys = {r["destination_key"] for r in ie_unreach_rows}
    ei_unreach_keys = {r["destination_key"] for r in ei_unreach_rows}

    if len(ie_unreach_rows) != EXPECTED_UNREACHABLE_RELATIONS_EACH:
        raise RuntimeError(f"IE unreachable rows = {len(ie_unreach_rows)}")
    if len(ei_unreach_rows) != EXPECTED_UNREACHABLE_RELATIONS_EACH:
        raise RuntimeError(f"EI unreachable rows = {len(ei_unreach_rows)}")
    if ie_unreach_keys != fully_disconnected or ei_unreach_keys != fully_disconnected:
        raise RuntimeError(
            "Unrouted relation destination keys do not exactly match fully disconnected destinations"
        )

    unreachable_b1 = [r for r in b1 if r["destination_key"] in fully_disconnected]
    missing_raw = sum(parse_float(r["Pendolari_raw"]) for r in unreachable_b1)
    missing_daily = sum(parse_float(r["flow_daily"]) for r in unreachable_b1)
    assert_close(missing_raw, EXPECTED_MISSING_RAW_FLOW, "missing raw flow")
    assert_close(missing_daily, EXPECTED_MISSING_DAILY_FLOW, "missing daily flow")

    routed_ie_daily = sum(
        parse_float(r["flow_daily"]) for r in ie if r.get("route_status") == "PASS"
    )
    routed_ei_daily = sum(
        parse_float(r["flow_daily"]) for r in ei if r.get("route_status") == "PASS"
    )
    assert_close(routed_ie_daily + missing_daily, EXPECTED_DAILY_EACH, "IE flow closure")
    assert_close(routed_ei_daily + missing_daily, EXPECTED_DAILY_EACH, "EI flow closure")

    print(f"unreachable B1 rows each direction = {len(unreachable_b1)}")
    print(f"missing raw commuters              = {missing_raw:.5f}")
    print(f"missing daily flow                 = {missing_daily:.5f}")
    print(f"routed IE daily                    = {routed_ie_daily:.5f}")
    print(f"routed EI daily                    = {routed_ei_daily:.5f}")
    print(f"IE closure                         = {routed_ie_daily + missing_daily:.5f}")
    print(f"EI closure                         = {routed_ei_daily + missing_daily:.5f}")

    print()
    print("E. MATERIALIZE TARGETED BLOCKER EVIDENCE")
    staging.mkdir(parents=True, exist_ok=False)

    error_signature_counter: Counter[tuple[str, str, str, str]] = Counter()

    for key in sorted(fully_disconnected):
        ext_rows = ext_by_dest_dir[key]["IE"] + ext_by_dest_dir[key]["EI"]
        b1_rows = b1_by_dest[key]
        example = b1_rows[0]
        ie_ext = ext_by_dest_dir[key]["IE"]
        ei_ext = ext_by_dest_dir[key]["EI"]

        for r in ext_rows:
            sig = normalize_error_signature(r.get("error", ""))
            error_signature_counter[
                (
                    str(r.get("direction", "")),
                    str(r.get("http_status", "")),
                    str(r.get("status", "")),
                    sig,
                )
            ] += 1

        destination_diag_rows.append({
            "destination_key": key,
            "dest_code_raw": example["dest_code_raw"],
            "dest_code_join": example["dest_code_join"],
            "dest_COMUNE": example["dest_COMUNE"],
            "dest_lon": example["dest_lon"],
            "dest_lat": example["dest_lat"],
            "b1_rows": len(b1_rows),
            "Pendolari_raw_sum": sum(parse_float(r["Pendolari_raw"]) for r in b1_rows),
            "flow_daily_sum": sum(parse_float(r["flow_daily"]) for r in b1_rows),
            "IE_external_candidates": len(ie_ext),
            "IE_unreachable_candidates": sum(r["status"] == "UNREACHABLE" for r in ie_ext),
            "EI_external_candidates": len(ei_ext),
            "EI_unreachable_candidates": sum(r["status"] == "UNREACHABLE" for r in ei_ext),
            "diagnostic_class": "FULLY_DISCONNECTED_FROM_ALL_49_VENETO_CROSSINGS",
        })

    destination_diag_rows.sort(
        key=lambda r: (-float(r["Pendolari_raw_sum"]), str(r["dest_COMUNE"]), str(r["destination_key"]))
    )

    relation_rows: list[dict[str, object]] = []
    for r in unreachable_b1:
        relation_rows.append({
            "b1_row_id": r["b1_row_id"],
            "origin_PRO_COM": r["origin_PRO_COM"],
            "origin_COMUNE": r["origin_COMUNE"],
            "dest_code_raw": r["dest_code_raw"],
            "dest_code_join": r["dest_code_join"],
            "dest_COMUNE": r["dest_COMUNE"],
            "destination_key": r["destination_key"],
            "dest_lon": r["dest_lon"],
            "dest_lat": r["dest_lat"],
            "Pendolari_raw": r["Pendolari_raw"],
            "flow_daily": r["flow_daily"],
            "diagnostic_class": "DESTINATION_FULLY_DISCONNECTED_EXTERNAL_GRAPH",
        })
    relation_rows.sort(
        key=lambda r: (
            str(r["dest_COMUNE"]),
            parse_int(r["origin_PRO_COM"]),
            parse_int(r["b1_row_id"]),
        )
    )

    err_rows = [
        {
            "direction": direction,
            "http_status": http_status,
            "status": status,
            "error_signature": signature,
            "candidate_count": count,
        }
        for (direction, http_status, status, signature), count
        in sorted(
            error_signature_counter.items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
    ]

    dest_path = staging / DEST_CSV
    rel_path = staging / REL_CSV
    err_path = staging / ERR_CSV
    write_csv(dest_path, destination_diag_rows)
    write_csv(rel_path, relation_rows)
    write_csv(err_path, err_rows)

    # Top-level evidence based only on materialized GH08 outputs.
    summary_out = {
        "schema": "B1_EXT_GH_08D_BLOCKING_DIAGNOSTICS_SUMMARY_V01",
        "verdict": "PASS",
        "gh08_verdict": "NOT_READY",
        "diagnostic_result": "PURE_DESTINATION_LEVEL_EXTERNAL_GRAPH_DISCONNECTION",
        "fully_disconnected_destinations": len(fully_disconnected),
        "partially_disconnected_destinations": len(partial_disconnected),
        "external_unreachable_candidates": external_unreachable,
        "external_technical_errors": external_errors,
        "external_snap_flags": external_snap_flags,
        "unreachable_relations_each_direction": len(unreachable_b1),
        "missing_raw_flow_each_direction": missing_raw,
        "missing_daily_flow_each_direction": missing_daily,
        "routed_ie_daily": routed_ie_daily,
        "routed_ei_daily": routed_ei_daily,
        "expected_daily_each": EXPECTED_DAILY_EACH,
        "flow_closure_ie": routed_ie_daily + missing_daily,
        "flow_closure_ei": routed_ei_daily + missing_daily,
        "identity": {
            "candidate_equation": (
                f"{len(fully_disconnected)} destinations * "
                f"{EXPECTED_CROSSINGS} crossings * 2 directions = "
                f"{external_unreachable}"
            ),
            "unrouted_destination_keys_equal_fully_disconnected_set_IE": True,
            "unrouted_destination_keys_equal_fully_disconnected_set_EI": True,
        },
        "interpretation_guardrail": {
            "island_or_ferry_cause_proven": False,
            "graph_profile_defect_proven": False,
            "data_error_proven": False,
            "next_action": (
                "Inspect the 19 destination identities and GraphHopper error signatures; "
                "choose a correction only after the actual cause is demonstrated."
            ),
        },
        "scope_guardrail": {
            "graphhopper_server_started": False,
            "b5_routing_started": False,
            "pbf_import_started": False,
            "gh08_outputs_modified": False,
            "frozen_fvg_artifacts_modified": False,
        },
    }
    summary_out_path = staging / SUMMARY_JSON
    write_json(summary_out_path, summary_out)

    outputs = [dest_path, rel_path, err_path, summary_out_path]
    manifest_out = {
        "schema": "B1_EXT_GH_08D_BLOCKING_DIAGNOSTICS_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS",
        "inputs": {
            "gh08_manifest": {
                "path": str(manifest_path),
                "sha256": sha256(manifest_path),
            },
            "gh08_summary": {
                "path": str(summary_path),
                "sha256": sha256(summary_path),
            },
            "b1_normalized": {
                "path": str(b1_path),
                "sha256": sha256(b1_path),
            },
            "external_cache": {
                "path": str(external_path),
                "sha256": sha256(external_path),
            },
            "ie_routing": {
                "path": str(ie_path),
                "sha256": sha256(ie_path),
            },
            "ei_routing": {
                "path": str(ei_path),
                "sha256": sha256(ei_path),
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
        "next_gate": "CAUSE_CLASSIFICATION_FOR_19_DISCONNECTED_DESTINATIONS",
    }
    manifest_out_path = staging / MANIFEST_JSON
    write_json(manifest_out_path, manifest_out)

    staging.rename(final_dir)

    print(f"diagnostic destinations CSV = {final_dir / DEST_CSV}")
    print(f"diagnostic relations CSV    = {final_dir / REL_CSV}")
    print(f"error signatures CSV        = {final_dir / ERR_CSV}")

    print()
    print("F. DIAGNOSTIC VERDICT")
    print("=" * 124)
    print("B1_EXT_GH_08D_BLOCKING_DIAGNOSTICS = PASS")
    print("GH08 = NOT_READY")
    print(f"FULLY_DISCONNECTED_EXTERNAL_DESTINATIONS = {len(fully_disconnected)}")
    print(f"PARTIALLY_DISCONNECTED_EXTERNAL_DESTINATIONS = {len(partial_disconnected)}")
    print(f"UNREACHABLE_B1_RELATIONS_IE = {len(unreachable_b1)}")
    print(f"UNREACHABLE_B1_RELATIONS_EI = {len(unreachable_b1)}")
    print(f"MISSING_RAW_FLOW_EACH = {missing_raw:.5f}")
    print(f"MISSING_DAILY_FLOW_EACH = {missing_daily:.5f}")
    print(f"EXTERNAL_UNREACHABLE_CANDIDATES = {external_unreachable}")
    print("EXTERNAL_TECHNICAL_OR_SNAP_FAILURES = 0")
    print("BLOCKER_CLASS = PURE_DESTINATION_LEVEL_EXTERNAL_GRAPH_DISCONNECTION")
    print("ISLAND_OR_FERRY_CAUSE = NOT_YET_PROVEN")
    print("GRAPH_PROFILE_DEFECT = NOT_YET_PROVEN")
    print("DATA_ERROR = NOT_YET_PROVEN")
    print("GH_SERVER = NOT_STARTED")
    print("B5_ROUTING = NOT_STARTED")
    print("PBF_IMPORT = NOT_STARTED")
    print("GH08_OUTPUTS_MODIFIED = NO")
    print("FROZEN_FVG_ARTIFACTS_MODIFIED = NO")
    print("NEXT_GATE = CAUSE_CLASSIFICATION_FOR_19_DISCONNECTED_DESTINATIONS")
    print(f"{DEST_CSV} SHA256 = {sha256(final_dir / DEST_CSV)}")
    print(f"{REL_CSV} SHA256 = {sha256(final_dir / REL_CSV)}")
    print(f"{ERR_CSV} SHA256 = {sha256(final_dir / ERR_CSV)}")
    print(f"{SUMMARY_JSON} SHA256 = {sha256(final_dir / SUMMARY_JSON)}")
    print(f"{MANIFEST_JSON} SHA256 = {sha256(final_dir / MANIFEST_JSON)}")
    print("=== RUN COMPLETATA ===")

    print()
    print("TOP DISCONNECTED DESTINATIONS BY RAW FLOW")
    for r in destination_diag_rows[:25]:
        print(
            f"  {str(r['dest_COMUNE']):<35} "
            f"raw={float(r['Pendolari_raw_sum']):8.1f} "
            f"rows={int(r['b1_rows']):3d} "
            f"code={r['dest_code_raw'] or r['dest_code_join']}"
        )

    print()
    print("ERROR SIGNATURES")
    for r in err_rows[:20]:
        print(
            f"  {r['direction']} HTTP={r['http_status']} "
            f"count={r['candidate_count']} :: {r['error_signature']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
