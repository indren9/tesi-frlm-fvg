#!/usr/bin/env python3
"""
B1-EXT-GH 10E — GATEWAY AGGREGATION OF EXTERNAL COMMUTING FLOWS

Task contract
-------------
Close B1 by aggregating the already-routed canonical GH10D V03 commuting
component over the 12 Veneto modelling gateways.

STRICTLY OFFLINE:
- NO new routing
- NO GraphHopper
- NO PBF
- NO B5 routing
- NO Gravity
- NO EE / residual-demand estimation
- NO modification of GH10D or frozen graph artifacts

Inputs are read exclusively from canonical:
    GH10D V03 APPEND-ONLY

Outputs:
- canonical 12-row gateway aggregation table, sorted by TOTAL_commuting_daily DESC
- physical-crossing detail table
- observed-count diagnostic table for already-materialized Veneto observations
- summary JSON
- final text report
- manifest with SHA256

The observed comparison is diagnostic only. It does NOT compute residual demand.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DEFAULT = r"C:\Tesi"

# =============================================================================
# Frozen task contract
# =============================================================================

DAILY_FACTOR = 0.42855
EXPECTED_ROWS_PER_DIRECTION = 2895
EXPECTED_RAW_PER_DIRECTION = 14458.0
EXPECTED_DAILY_PER_DIRECTION = 6195.97590
EXPECTED_BIDIRECTIONAL_DAILY = 12391.95180
NUMERIC_TOL = 1e-5

GH10D_DIR_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\targeted_external_route_override_materialization_v03"
)

GH10D_SUMMARY = "B1_EXT_GH_10D_targeted_external_route_override_summary_v03.json"
GH10D_SUMMARY_SHA256 = "f342f00b7a692f2c34b1fc47f71a9220ead0519736b4f2f44b6c54dac904b3f9"

GH10D_MANIFEST = "B1_EXT_GH_10D_targeted_external_route_override_manifest_v03.json"
GH10D_MANIFEST_SHA256 = "d77aff2741d287a812093446439e9faa01cd04bee34872d5fccd96b0eb43bc67"

IE_CSV = "B1_EXT_GH_10D_IE_routing_v03.csv"
EI_CSV = "B1_EXT_GH_10D_EI_routing_v03.csv"
CROSSING_FLOW_CSV = "B1_EXT_GH_10D_crossing_flow_attribution_v03.csv"
GATEWAY_FLOW_CSV = "B1_EXT_GH_10D_gateway_flow_attribution_v03.csv"

GATEWAY_ORDER = [
    "VE01", "VE02", "VE03", "VE04", "VE05", "VE06",
    "A1V01", "A1V02", "A1V03", "A1V04", "A1V05", "A1V06",
]

GATEWAY_NAMES = {
    "VE01": "A4 regional boundary",
    "VE02": "A28 south / Portogruaro-Sesto",
    "VE03": "A28 west / Sacile-Cordignano",
    "VE04": "SS13 / Sacile group",
    "VE05": "SS14 Latisana-Fossalta",
    "VE06": "SR251 Erto-Bellunese",
    "A1V01": "SS52 Passo Mauria",
    "A1V02": "SR355 Sappada",
    "A1V03": "Brugnera-Prata/Livenza",
    "A1V04": "Postumia/SR53",
    "A1V05": "Cordovado/SR463",
    "A1V06": "Bevazzana-Lignano",
}

# Existing B0 observations. These are OFFICIAL but OBSERVED_PROXY/contextual,
# hence used only for the requested diagnostic comparison.
OBSERVED_DIAGNOSTIC = {
    "VE04": {
        "observed_gateway_count": 9871.0,
        "reference_year": "2024",
        "count_status": "OBSERVED_PROXY",
        "source": "ANAS station 920074 Cordignano",
        "semantics": "BIDIRECTIONAL_TOTAL_ALL_VEHICLES_CONTEXTUAL",
    },
    "VE05": {
        "observed_gateway_count": 16233.0,
        "reference_year": "2024",
        "count_status": "OBSERVED_PROXY",
        "source": "ANAS station 3192 Fossalta di Portogruaro",
        "semantics": "BIDIRECTIONAL_TOTAL_ALL_VEHICLES_CONTEXTUAL",
    },
}

OUTPUT_REL = (
    r"Tesi_QGIS\03_output_temporanei\fase_5_9D_B1_ext_support"
    r"\gateway_commuting_aggregation_v01"
)

GATEWAY_OUT = "B1_EXT_GH_10E_gateway_commuting_aggregation_v01.csv"
CROSSING_OUT = "B1_EXT_GH_10E_crossing_commuting_detail_v01.csv"
OBSERVED_OUT = "B1_EXT_GH_10E_gateway_observed_diagnostic_v01.csv"
SUMMARY_OUT = "B1_EXT_GH_10E_gateway_commuting_aggregation_summary_v01.json"
REPORT_OUT = "FASE_5_9D_B1_CLOSE_GATEWAY_AGGREGATION_REPORT.txt"
MANIFEST_OUT = "B1_EXT_GH_10E_gateway_commuting_aggregation_manifest_v01.json"

# =============================================================================
# Helpers
# =============================================================================

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
    print(f"{label:<34} {'PASS' if ok else 'FAIL':<5} {actual}")
    if not ok:
        raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual


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


def assert_close(actual: float, expected: float, label: str, tol: float = NUMERIC_TOL) -> None:
    if abs(float(actual) - float(expected)) > tol:
        raise RuntimeError(
            f"{label}: actual={actual:.12f}, expected={expected:.12f}, tol={tol}"
        )


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not fields:
        raise RuntimeError(f"CSV has no header: {path}")
    return rows, fields


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def manifest_outputs(manifest: dict[str, Any]) -> dict[str, str]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise RuntimeError("GH10D manifest missing outputs list")
    result: dict[str, str] = {}
    for item in outputs:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid GH10D manifest output item")
        fn = str(item.get("filename", ""))
        digest = str(item.get("sha256", "")).lower()
        if not fn or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Invalid GH10D manifest output item: {item}")
        result[fn] = digest
    return result


def verify_manifest_files(base: Path, manifest: dict[str, Any]) -> dict[str, str]:
    outputs = manifest_outputs(manifest)
    required = {IE_CSV, EI_CSV, CROSSING_FLOW_CSV, GATEWAY_FLOW_CSV}
    missing = required - set(outputs)
    if missing:
        raise RuntimeError(f"GH10D manifest missing required files: {sorted(missing)}")
    for fn, digest in sorted(outputs.items()):
        p = base / fn
        if not p.is_file():
            raise FileNotFoundError(p)
        if sha256(p) != digest:
            raise RuntimeError(f"GH10D output changed: {fn}")
    return outputs


def normalize_direction(value: Any) -> str:
    d = str(value).strip().upper()
    if d not in {"IE", "EI"}:
        raise RuntimeError(f"Unexpected direction {value!r}")
    return d


def validate_routing_rows(rows: list[dict[str, str]], direction: str) -> None:
    if len(rows) != EXPECTED_ROWS_PER_DIRECTION:
        raise RuntimeError(
            f"{direction}: rows={len(rows)}, expected={EXPECTED_ROWS_PER_DIRECTION}"
        )

    ids = [parse_int(r["b1_row_id"]) for r in rows]
    if len(set(ids)) != len(ids):
        raise RuntimeError(f"{direction}: duplicate b1_row_id")

    pass_rows = [r for r in rows if str(r["route_status"]).strip() == "PASS"]
    if len(pass_rows) != EXPECTED_ROWS_PER_DIRECTION:
        failed = len(rows) - len(pass_rows)
        raise RuntimeError(f"{direction}: non-PASS rows={failed}")

    gateways = {str(r["selected_gateway_id"]).strip() for r in pass_rows}
    unexpected = gateways - set(GATEWAY_ORDER)
    if unexpected:
        raise RuntimeError(
            f"{direction}: unexpected non-Veneto gateway IDs: {sorted(unexpected)}"
        )

    blank_gateway = [
        parse_int(r["b1_row_id"])
        for r in pass_rows
        if not str(r["selected_gateway_id"]).strip()
    ]
    blank_geo = [
        parse_int(r["b1_row_id"])
        for r in pass_rows
        if not str(r["selected_geo_id"]).strip()
    ]
    if blank_gateway or blank_geo:
        raise RuntimeError(
            f"{direction}: blank gateway={len(blank_gateway)} blank geo={len(blank_geo)}"
        )

    raw = sum(parse_float(r["Pendolari_raw"]) for r in pass_rows)
    daily = sum(parse_float(r["flow_daily"]) for r in pass_rows)
    assert_close(raw, EXPECTED_RAW_PER_DIRECTION, f"{direction} raw total")
    assert_close(daily, EXPECTED_DAILY_PER_DIRECTION, f"{direction} daily total")

    # Verify the frozen conversion row-by-row.
    for r in pass_rows:
        expected_daily = parse_float(r["Pendolari_raw"]) * DAILY_FACTOR
        assert_close(
            parse_float(r["flow_daily"]),
            expected_daily,
            f"{direction} b1_row_id={r['b1_row_id']} daily factor",
            1e-8,
        )


def aggregate_from_routing(
    ie_rows: list[dict[str, str]],
    ei_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gateway_acc = {
        gid: {
            "IE_OD_count": 0,
            "EI_OD_count": 0,
            "IE_raw_commuters": 0.0,
            "EI_raw_commuters": 0.0,
            "IE_commuting_daily": 0.0,
            "EI_commuting_daily": 0.0,
        }
        for gid in GATEWAY_ORDER
    }

    crossing_acc: dict[tuple[str, str], dict[str, Any]] = {}

    for direction, rows in (("IE", ie_rows), ("EI", ei_rows)):
        for r in rows:
            if str(r["route_status"]).strip() != "PASS":
                continue
            gid = str(r["selected_gateway_id"]).strip()
            geo = str(r["selected_geo_id"]).strip()
            raw = parse_float(r["Pendolari_raw"])
            daily = parse_float(r["flow_daily"])

            g = gateway_acc[gid]
            g[f"{direction}_OD_count"] += 1
            g[f"{direction}_raw_commuters"] += raw
            g[f"{direction}_commuting_daily"] += daily

            key = (gid, geo)
            if key not in crossing_acc:
                crossing_acc[key] = {
                    "gateway_id": gid,
                    "gateway_name": GATEWAY_NAMES[gid],
                    "physical_crossing_id": geo,
                    "crossing_IE_OD_count": 0,
                    "crossing_EI_OD_count": 0,
                    "crossing_IE_raw_commuters": 0.0,
                    "crossing_EI_raw_commuters": 0.0,
                    "crossing_IE_flow": 0.0,
                    "crossing_EI_flow": 0.0,
                }
            c = crossing_acc[key]
            c[f"crossing_{direction}_OD_count"] += 1
            c[f"crossing_{direction}_raw_commuters"] += raw
            c[f"crossing_{direction}_flow"] += daily

    used_crossings_by_gateway: dict[str, set[str]] = defaultdict(set)
    for (gid, geo), c in crossing_acc.items():
        if c["crossing_IE_OD_count"] > 0 or c["crossing_EI_OD_count"] > 0:
            used_crossings_by_gateway[gid].add(geo)

    gateway_rows: list[dict[str, Any]] = []
    for gid in GATEWAY_ORDER:
        g = gateway_acc[gid]
        ie_d = float(g["IE_commuting_daily"])
        ei_d = float(g["EI_commuting_daily"])
        total = ie_d + ei_d
        gateway_rows.append({
            "gateway_id": gid,
            "gateway_name": GATEWAY_NAMES[gid],
            **g,
            "TOTAL_commuting_daily": total,
            "IE_share_of_regional_total": ie_d / EXPECTED_DAILY_PER_DIRECTION,
            "EI_share_of_regional_total": ei_d / EXPECTED_DAILY_PER_DIRECTION,
            "TOTAL_share_of_bidirectional_commuting": total / EXPECTED_BIDIRECTIONAL_DAILY,
            "number_of_physical_crossings_used": len(used_crossings_by_gateway.get(gid, set())),
        })

    gateway_rows.sort(
        key=lambda r: (-float(r["TOTAL_commuting_daily"]), str(r["gateway_id"]))
    )

    crossing_rows = list(crossing_acc.values())
    for r in crossing_rows:
        r["crossing_TOTAL_flow"] = (
            float(r["crossing_IE_flow"]) + float(r["crossing_EI_flow"])
        )
    crossing_rows.sort(
        key=lambda r: (
            GATEWAY_ORDER.index(str(r["gateway_id"])),
            -float(r["crossing_TOTAL_flow"]),
            str(r["physical_crossing_id"]),
        )
    )
    return gateway_rows, crossing_rows


def verify_preaggregated_consistency(
    gateway_rows: list[dict[str, Any]],
    crossing_rows: list[dict[str, Any]],
    canonical_gateway_csv: list[dict[str, str]],
    canonical_crossing_csv: list[dict[str, str]],
) -> None:
    # Canonical GH10D gateway table is direction-specific.
    expected_gateway = {
        (normalize_direction(r["direction"]), str(r["gateway_id"]).strip()): r
        for r in canonical_gateway_csv
    }

    for g in gateway_rows:
        gid = str(g["gateway_id"])
        for d in ("IE", "EI"):
            key = (d, gid)
            local_count = parse_int(g[f"{d}_OD_count"])
            local_raw = parse_float(g[f"{d}_raw_commuters"])
            local_daily = parse_float(g[f"{d}_commuting_daily"])

            if local_count == 0:
                # A zero-flow gateway may be absent from the sparse canonical table.
                if key in expected_gateway:
                    r = expected_gateway[key]
                    if (
                        parse_int(r["b1_rows"]) != 0
                        or abs(parse_float(r["Pendolari_raw_sum"])) > NUMERIC_TOL
                        or abs(parse_float(r["flow_daily_sum"])) > NUMERIC_TOL
                    ):
                        raise RuntimeError(f"Gateway preaggregate mismatch {key}")
                continue

            if key not in expected_gateway:
                raise RuntimeError(f"Gateway missing from GH10D preaggregate: {key}")

            r = expected_gateway[key]
            if parse_int(r["b1_rows"]) != local_count:
                raise RuntimeError(f"Gateway row-count mismatch {key}")
            assert_close(parse_float(r["Pendolari_raw_sum"]), local_raw, f"gateway raw {key}")
            assert_close(parse_float(r["flow_daily_sum"]), local_daily, f"gateway daily {key}")

    local_cross = {
        (str(r["gateway_id"]), str(r["physical_crossing_id"])): r
        for r in crossing_rows
    }
    canonical_cross: dict[tuple[str, str, str], dict[str, str]] = {
        (
            normalize_direction(r["direction"]),
            str(r["gateway_id"]).strip(),
            str(r["geo_id"]).strip(),
        ): r
        for r in canonical_crossing_csv
    }

    for (gid, geo), r in local_cross.items():
        for d in ("IE", "EI"):
            key = (d, gid, geo)
            local_count = parse_int(r[f"crossing_{d}_OD_count"])
            local_raw = parse_float(r[f"crossing_{d}_raw_commuters"])
            local_daily = parse_float(r[f"crossing_{d}_flow"])
            if local_count == 0:
                if key in canonical_cross:
                    c = canonical_cross[key]
                    if (
                        parse_int(c["b1_rows"]) != 0
                        or abs(parse_float(c["Pendolari_raw_sum"])) > NUMERIC_TOL
                        or abs(parse_float(c["flow_daily_sum"])) > NUMERIC_TOL
                    ):
                        raise RuntimeError(f"Crossing preaggregate mismatch {key}")
                continue
            if key not in canonical_cross:
                raise RuntimeError(f"Crossing missing from GH10D preaggregate: {key}")
            c = canonical_cross[key]
            if parse_int(c["b1_rows"]) != local_count:
                raise RuntimeError(f"Crossing row-count mismatch {key}")
            assert_close(parse_float(c["Pendolari_raw_sum"]), local_raw, f"crossing raw {key}")
            assert_close(parse_float(c["flow_daily_sum"]), local_daily, f"crossing daily {key}")


def make_observed_diagnostic(
    gateway_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(r["gateway_id"]): r for r in gateway_rows}
    out: list[dict[str, Any]] = []
    for gid in ("VE04", "VE05"):
        obs = OBSERVED_DIAGNOSTIC[gid]
        commuting = parse_float(by_id[gid]["TOTAL_commuting_daily"])
        observed = parse_float(obs["observed_gateway_count"])
        out.append({
            "gateway_id": gid,
            "gateway_name": GATEWAY_NAMES[gid],
            "reference_year": obs["reference_year"],
            "count_status": obs["count_status"],
            "observed_source": obs["source"],
            "observed_semantics": obs["semantics"],
            "observed_gateway_count": observed,
            "commuting_component": commuting,
            "commuting_share_of_observed": commuting / observed,
            "residual_demand": "NOT_CALCULATED",
            "interpretation": "DIAGNOSTIC_ONLY_NOT_CORDON_EQUALITY",
        })
    return out


def fmt(x: float, digits: int = 5) -> str:
    return f"{x:.{digits}f}"


def make_report(
    gateway_rows: list[dict[str, Any]],
    observed_rows: list[dict[str, Any]],
) -> str:
    total_ie = sum(parse_float(r["IE_commuting_daily"]) for r in gateway_rows)
    total_ei = sum(parse_float(r["EI_commuting_daily"]) for r in gateway_rows)
    total_bi = sum(parse_float(r["TOTAL_commuting_daily"]) for r in gateway_rows)
    top = gateway_rows[0]
    zero = [
        str(r["gateway_id"])
        for r in gateway_rows
        if abs(parse_float(r["TOTAL_commuting_daily"])) <= NUMERIC_TOL
    ]

    lines: list[str] = []
    lines.append("FASE_5_9D_B1_CLOSE_GATEWAY_AGGREGATION_REPORT")
    lines.append("")
    lines.append("=" * 100)
    lines.append("VERDETTO")
    lines.append("=" * 100)
    lines.append("")
    lines.append("FASE_5_9D_B1 = PASS")
    lines.append("GATEWAYS_AGGREGATED = 12 / 12")
    lines.append(f"TOTAL_IE = {fmt(total_ie)}")
    lines.append(f"TOTAL_EI = {fmt(total_ei)}")
    lines.append(f"TOTAL_BIDIRECTIONAL = {fmt(total_bi)}")
    lines.append(
        "TOP_GATEWAY_BY_COMMUTING_FLOW = "
        f"{top['gateway_id']} / {top['gateway_name']} / "
        f"{fmt(parse_float(top['TOTAL_commuting_daily']))}"
    )
    lines.append(
        "ZERO_FLOW_GATEWAYS = " + ("NONE" if not zero else " | ".join(zero))
    )
    lines.append("MASS_BALANCE = PASS")
    lines.append("AMBIGUOUS = 0")
    lines.append("UNASSIGNED_ROWS = 0")
    lines.append("ALL_IE_ROWS_ASSIGNED = 2895 / 2895")
    lines.append("ALL_EI_ROWS_ASSIGNED = 2895 / 2895")
    lines.append("")
    lines.append("=" * 100)
    lines.append("CANONICAL GATEWAY TABLE — OBSERVED COMMUTING COMPONENT OF GATEWAY FLOW")
    lines.append("=" * 100)
    lines.append("")
    header = (
        "gateway_id | gateway_name | IE_OD | EI_OD | IE_raw | EI_raw | "
        "IE_daily | EI_daily | TOTAL_daily | IE_share | EI_share | TOTAL_share | crossings_used"
    )
    lines.append(header)
    for r in gateway_rows:
        lines.append(
            f"{r['gateway_id']} | {r['gateway_name']} | "
            f"{r['IE_OD_count']} | {r['EI_OD_count']} | "
            f"{parse_float(r['IE_raw_commuters']):.0f} | "
            f"{parse_float(r['EI_raw_commuters']):.0f} | "
            f"{fmt(parse_float(r['IE_commuting_daily']))} | "
            f"{fmt(parse_float(r['EI_commuting_daily']))} | "
            f"{fmt(parse_float(r['TOTAL_commuting_daily']))} | "
            f"{100*parse_float(r['IE_share_of_regional_total']):.4f}% | "
            f"{100*parse_float(r['EI_share_of_regional_total']):.4f}% | "
            f"{100*parse_float(r['TOTAL_share_of_bidirectional_commuting']):.4f}% | "
            f"{r['number_of_physical_crossings_used']}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append("OBSERVED GATEWAY COUNT — DIAGNOSTIC ONLY")
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "Only VE04 and VE05 currently have materialized Veneto counts; both are OBSERVED_PROXY/contextual, "
        "not hard cordon equalities."
    )
    lines.append("NO residual demand is calculated.")
    for r in observed_rows:
        lines.append(
            f"{r['gateway_id']} | {r['gateway_name']} | "
            f"observed={fmt(parse_float(r['observed_gateway_count']), 2)} | "
            f"commuting={fmt(parse_float(r['commuting_component']))} | "
            f"commuting_share_of_observed={100*parse_float(r['commuting_share_of_observed']):.4f}% | "
            f"{r['count_status']} | {r['interpretation']}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append("MASS BALANCE QA")
    lines.append("=" * 100)
    lines.append("")
    lines.append(f"SUM_GATEWAYS_IE = {fmt(total_ie)}")
    lines.append(f"SUM_GATEWAYS_EI = {fmt(total_ei)}")
    lines.append(f"SUM_GATEWAYS_TOTAL = {fmt(total_bi)}")
    lines.append("EXPECTED_IE = 6195.97590")
    lines.append("EXPECTED_EI = 6195.97590")
    lines.append("EXPECTED_TOTAL = 12391.95180")
    lines.append("MASS_BALANCE = PASS")
    lines.append("")
    lines.append("=" * 100)
    lines.append("SCOPE")
    lines.append("=" * 100)
    lines.append("")
    lines.append("This table is the OBSERVED COMMUTING COMPONENT OF GATEWAY FLOW.")
    lines.append("It is NOT total gateway traffic.")
    lines.append("No non-commuting traffic, residual demand, EE, Gravity or ANAS 2025 is used.")
    lines.append("")
    lines.append("=" * 100)
    lines.append("HARD STOP")
    lines.append("=" * 100)
    lines.append("")
    lines.append("NO NEW ROUTING EXECUTED.")
    lines.append("GH10D / G_EXT_ITALY_B1_v01 NOT MODIFIED.")
    lines.append("RETURN CONTROL TO CHAT MADRE.")
    lines.append("")
    return "\n".join(lines)


def helper_self_tests() -> None:
    # Minimal symmetric two-gateway fixture.
    ie = [
        {
            "b1_row_id": "1", "route_status": "PASS",
            "selected_gateway_id": "VE01", "selected_geo_id": "GEO_A",
            "Pendolari_raw": "2", "flow_daily": str(2 * DAILY_FACTOR),
        },
        {
            "b1_row_id": "2", "route_status": "PASS",
            "selected_gateway_id": "VE02", "selected_geo_id": "GEO_B",
            "Pendolari_raw": "3", "flow_daily": str(3 * DAILY_FACTOR),
        },
    ]
    ei = [
        {
            "b1_row_id": "1", "route_status": "PASS",
            "selected_gateway_id": "VE02", "selected_geo_id": "GEO_B",
            "Pendolari_raw": "2", "flow_daily": str(2 * DAILY_FACTOR),
        },
        {
            "b1_row_id": "2", "route_status": "PASS",
            "selected_gateway_id": "VE01", "selected_geo_id": "GEO_A",
            "Pendolari_raw": "3", "flow_daily": str(3 * DAILY_FACTOR),
        },
    ]
    gw, cr = aggregate_from_routing(ie, ei)
    by = {r["gateway_id"]: r for r in gw}
    assert by["VE01"]["IE_OD_count"] == 1
    assert by["VE01"]["EI_OD_count"] == 1
    assert_close(by["VE01"]["TOTAL_commuting_daily"], 5 * DAILY_FACTOR, "fixture total", 1e-12)
    assert len([r for r in cr if r["gateway_id"] == "VE01"]) == 1


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()

    helper_self_tests()
    if args.self_test_only:
        print("B1_EXT_GH_10E_HELPER_SELF_TESTS = PASS")
        return 0

    root = Path(args.root)
    src = root / Path(GH10D_DIR_REL)
    final_dir = root / Path(OUTPUT_REL)
    staging = final_dir.with_name(
        final_dir.name + "_STAGING_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    print("=" * 110)
    print("B1-EXT-GH 10E — GATEWAY AGGREGATION OF EXTERNAL COMMUTING FLOWS")
    print("=" * 110)
    print("OFFLINE / GH10D V03 ONLY / NO ROUTING / NO RESIDUAL DEMAND")
    print()

    if final_dir.exists():
        raise FileExistsError(f"NO OVERWRITE: {final_dir}")
    if staging.exists():
        raise FileExistsError(staging)

    print("A. STRICT GH10D LINEAGE")
    strict_hash("GH10D summary", src / GH10D_SUMMARY, GH10D_SUMMARY_SHA256)
    strict_hash("GH10D manifest", src / GH10D_MANIFEST, GH10D_MANIFEST_SHA256)
    manifest = read_json(src / GH10D_MANIFEST)
    output_hashes = verify_manifest_files(src, manifest)
    print(f"GH10D outputs verified          = {len(output_hashes)}")
    print("helper self-tests               = PASS")

    print()
    print("B. LOAD CANONICAL V03 ROUTING")
    ie_rows, _ = read_csv(src / IE_CSV)
    ei_rows, _ = read_csv(src / EI_CSV)
    canonical_crossing, _ = read_csv(src / CROSSING_FLOW_CSV)
    canonical_gateway, _ = read_csv(src / GATEWAY_FLOW_CSV)

    validate_routing_rows(ie_rows, "IE")
    validate_routing_rows(ei_rows, "EI")
    print("IE assigned                     = 2895 / 2895")
    print("EI assigned                     = 2895 / 2895")
    print("unassigned                      = 0")
    print("ambiguous                       = 0")

    print()
    print("C. GATEWAY + PHYSICAL-CROSSING AGGREGATION")
    gateway_rows, crossing_rows = aggregate_from_routing(ie_rows, ei_rows)
    if len(gateway_rows) != 12:
        raise RuntimeError(f"Expected 12 gateway rows, got {len(gateway_rows)}")

    verify_preaggregated_consistency(
        gateway_rows, crossing_rows,
        canonical_gateway, canonical_crossing,
    )
    print("gateway rows                    = 12 / 12")
    print(f"used gateway-crossing pairs     = {len(crossing_rows)}")
    print("GH10D preaggregate consistency  = PASS")

    total_ie = sum(parse_float(r["IE_commuting_daily"]) for r in gateway_rows)
    total_ei = sum(parse_float(r["EI_commuting_daily"]) for r in gateway_rows)
    total_bi = sum(parse_float(r["TOTAL_commuting_daily"]) for r in gateway_rows)

    assert_close(total_ie, EXPECTED_DAILY_PER_DIRECTION, "SUM_GATEWAYS_IE")
    assert_close(total_ei, EXPECTED_DAILY_PER_DIRECTION, "SUM_GATEWAYS_EI")
    assert_close(total_bi, EXPECTED_BIDIRECTIONAL_DAILY, "SUM_GATEWAYS_TOTAL")

    print()
    print("D. MASS BALANCE")
    print(f"SUM_GATEWAYS_IE                 = {total_ie:.5f}")
    print(f"SUM_GATEWAYS_EI                 = {total_ei:.5f}")
    print(f"SUM_GATEWAYS_TOTAL              = {total_bi:.5f}")
    print("MASS_BALANCE                    = PASS")

    print()
    print("E. OBSERVED-COUNT DIAGNOSTIC")
    observed_rows = make_observed_diagnostic(gateway_rows)
    print("materialized Veneto observations = 2")
    print("VE04 / VE05 status               = OBSERVED_PROXY / DIAGNOSTIC_ONLY")
    print("residual demand                  = NOT_CALCULATED")

    print()
    print("F. MATERIALIZE APPEND-ONLY CLOSE PACKAGE")
    staging.mkdir(parents=True, exist_ok=False)

    gateway_fields = [
        "gateway_id", "gateway_name",
        "IE_OD_count", "EI_OD_count",
        "IE_raw_commuters", "EI_raw_commuters",
        "IE_commuting_daily", "EI_commuting_daily",
        "TOTAL_commuting_daily",
        "IE_share_of_regional_total",
        "EI_share_of_regional_total",
        "TOTAL_share_of_bidirectional_commuting",
        "number_of_physical_crossings_used",
    ]
    crossing_fields = [
        "gateway_id", "gateway_name", "physical_crossing_id",
        "crossing_IE_OD_count", "crossing_EI_OD_count",
        "crossing_IE_raw_commuters", "crossing_EI_raw_commuters",
        "crossing_IE_flow", "crossing_EI_flow", "crossing_TOTAL_flow",
    ]
    observed_fields = [
        "gateway_id", "gateway_name", "reference_year", "count_status",
        "observed_source", "observed_semantics",
        "observed_gateway_count", "commuting_component",
        "commuting_share_of_observed", "residual_demand", "interpretation",
    ]

    write_csv(staging / GATEWAY_OUT, gateway_rows, gateway_fields)
    write_csv(staging / CROSSING_OUT, crossing_rows, crossing_fields)
    write_csv(staging / OBSERVED_OUT, observed_rows, observed_fields)

    top = gateway_rows[0]
    zero = [
        str(r["gateway_id"])
        for r in gateway_rows
        if abs(parse_float(r["TOTAL_commuting_daily"])) <= NUMERIC_TOL
    ]

    summary = {
        "schema": "B1_EXT_GH_10E_GATEWAY_COMMUTING_AGGREGATION_SUMMARY_V01",
        "verdict": "PASS",
        "source": {
            "canonical_materialization": "GH10D_V03_APPEND_ONLY",
            "GH10D_summary_sha256": GH10D_SUMMARY_SHA256,
            "GH10D_manifest_sha256": GH10D_MANIFEST_SHA256,
        },
        "gateways_aggregated": 12,
        "IE_rows_assigned": len(ie_rows),
        "EI_rows_assigned": len(ei_rows),
        "unassigned_rows": 0,
        "ambiguous_rows": 0,
        "total_IE": total_ie,
        "total_EI": total_ei,
        "total_bidirectional": total_bi,
        "mass_balance": "PASS",
        "top_gateway_by_commuting_flow": {
            "gateway_id": top["gateway_id"],
            "gateway_name": top["gateway_name"],
            "TOTAL_commuting_daily": top["TOTAL_commuting_daily"],
        },
        "zero_flow_gateways": zero,
        "observed_gateway_diagnostic": {
            "gateways_compared": ["VE04", "VE05"],
            "role": "DIAGNOSTIC_ONLY",
            "residual_demand": "NOT_CALCULATED",
        },
        "routing_executed": False,
        "GH10D_modified": False,
        "G_EXT_ITALY_B1_v01_modified": False,
        "gravity_used": False,
        "ANAS_2025_used": False,
        "next": "RETURN_CONTROL_TO_CHAT_MADRE",
    }
    write_json(staging / SUMMARY_OUT, summary)

    report = make_report(gateway_rows, observed_rows)
    (staging / REPORT_OUT).write_text(report, encoding="utf-8")

    outputs = [
        staging / GATEWAY_OUT,
        staging / CROSSING_OUT,
        staging / OBSERVED_OUT,
        staging / SUMMARY_OUT,
        staging / REPORT_OUT,
    ]

    print()
    print("G. FINAL SOURCE INTEGRITY")
    # Re-verify source bytes after all output operations.
    strict_hash("GH10D summary post-run", src / GH10D_SUMMARY, GH10D_SUMMARY_SHA256)
    strict_hash("GH10D manifest post-run", src / GH10D_MANIFEST, GH10D_MANIFEST_SHA256)
    verify_manifest_files(src, manifest)
    print("GH10D source outputs modified     = NO")

    manifest_out = {
        "schema": "B1_EXT_GH_10E_GATEWAY_COMMUTING_AGGREGATION_MANIFEST_V01",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS",
        "inputs": {
            "GH10D_summary": {
                "path": str(src / GH10D_SUMMARY),
                "sha256": sha256(src / GH10D_SUMMARY),
            },
            "GH10D_manifest": {
                "path": str(src / GH10D_MANIFEST),
                "sha256": sha256(src / GH10D_MANIFEST),
            },
            "GH10D_IE_routing": {
                "path": str(src / IE_CSV),
                "sha256": sha256(src / IE_CSV),
            },
            "GH10D_EI_routing": {
                "path": str(src / EI_CSV),
                "sha256": sha256(src / EI_CSV),
            },
            "GH10D_crossing_flow": {
                "path": str(src / CROSSING_FLOW_CSV),
                "sha256": sha256(src / CROSSING_FLOW_CSV),
            },
            "GH10D_gateway_flow": {
                "path": str(src / GATEWAY_FLOW_CSV),
                "sha256": sha256(src / GATEWAY_FLOW_CSV),
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
        "routing_executed": False,
        "residual_demand_calculated": False,
        "next": "RETURN_CONTROL_TO_CHAT_MADRE",
    }
    write_json(staging / MANIFEST_OUT, manifest_out)

    staging.rename(final_dir)

    print()
    print("=" * 110)
    print("FASE_5_9D_B1_CLOSE_GATEWAY_AGGREGATION_REPORT")
    print("=" * 110)
    print("FASE_5_9D_B1 = PASS")
    print("GATEWAYS_AGGREGATED = 12 / 12")
    print(f"TOTAL_IE = {total_ie:.5f}")
    print(f"TOTAL_EI = {total_ei:.5f}")
    print(f"TOTAL_BIDIRECTIONAL = {total_bi:.5f}")
    print(
        "TOP_GATEWAY_BY_COMMUTING_FLOW = "
        f"{top['gateway_id']} / {top['gateway_name']} / "
        f"{parse_float(top['TOTAL_commuting_daily']):.5f}"
    )
    print("ZERO_FLOW_GATEWAYS = " + ("NONE" if not zero else "|".join(zero)))
    print("MASS_BALANCE = PASS")
    print("AMBIGUOUS = 0")
    print("ALL_IE_ROWS_ASSIGNED = 2895 / 2895")
    print("ALL_EI_ROWS_ASSIGNED = 2895 / 2895")
    print("UNASSIGNED_ROWS = 0")
    print("NEW_ROUTING = NO")
    print("RESIDUAL_GATEWAY_DEMAND = NOT_CALCULATED")
    print("GH10D_MODIFIED = NO")
    print("G_EXT_ITALY_B1_v01_MODIFIED = NO")
    print(f"{GATEWAY_OUT} SHA256 = {sha256(final_dir / GATEWAY_OUT)}")
    print(f"{CROSSING_OUT} SHA256 = {sha256(final_dir / CROSSING_OUT)}")
    print(f"{SUMMARY_OUT} SHA256 = {sha256(final_dir / SUMMARY_OUT)}")
    print(f"{REPORT_OUT} SHA256 = {sha256(final_dir / REPORT_OUT)}")
    print(f"{MANIFEST_OUT} SHA256 = {sha256(final_dir / MANIFEST_OUT)}")
    print("=== RUN COMPLETATA ===")
    print("HARD STOP — RETURN CONTROL TO CHAT MADRE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
