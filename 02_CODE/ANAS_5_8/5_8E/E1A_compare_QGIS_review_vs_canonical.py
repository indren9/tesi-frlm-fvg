"""
E1-A — QGIS REVIEW VS CANONICAL ANAS MAPPING

PURPOSE
-------
Verificare che tutte le informazioni operative della review manuale QGIS
ANAS 5.8D siano correttamente rappresentate nel mapping canonico frozen
usato dalla fase E1.

INPUTS
------
1. ANAS_5_8D_QGIS_review.csv
   nella working directory corrente.

2. C:\\Tesi\\Tesi_QGIS\\02_package\\anas_calibration_v0\\
   ANAS_5_8D_calibration_mapping_v01.csv

OUTPUTS
-------
Solo report console:
- identità delle SECTION_ID;
- confronto campo per campo delle 16 sezioni;
- verifica dei campi aggregati canonici;
- elenco esplicito di eventuali mismatch.

ASSUMPTIONS
-----------
- SECTION_ID identifica univocamente una sezione.
- Entrambi i file usano ';' come delimitatore.
- ROLE nel canonico corrisponde a ROLE_PROPOSAL nella review.
- OSM_PHYSICAL_SEGMENT è la concatenazione dei segmenti primary/opposite.
- RELEVANT_DIRECTED_EDGE_IDS è la concatenazione degli edge primary/opposite.
- SHORT_REASON è descrittivo e non entra nel confronto operativo.
- Eventuali ';' interni a SHORT_REASON non devono invalidare il confronto.

FROZEN ARTIFACTS USED
---------------------
ANAS_5_8D_calibration_mapping_v01.csv — READ ONLY.

FILES WRITTEN
-------------
NESSUNO.

FILES NEVER MODIFIED
--------------------
ANAS_5_8D_QGIS_review.csv
ANAS_5_8D_calibration_mapping_v01.csv
Qualsiasi artefatto sotto 02_package.
"""

from pathlib import Path
import csv


WORKDIR = Path.cwd()

REVIEW = WORKDIR / "ANAS_5_8D_QGIS_review.csv"

CANONICAL = Path(
    r"C:\Tesi\Tesi_QGIS\02_package\anas_calibration_v0"
) / "ANAS_5_8D_calibration_mapping_v01.csv"


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def split_pipe(value):
    value = clean(value)

    if not value:
        return []

    return [
        x.strip()
        for x in value.split("|")
        if x.strip()
    ]


def joined(primary, opposite):
    return "|".join(
        split_pipe(primary) + split_pipe(opposite)
    )


def read_semicolon_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"FILE NOT FOUND: {path}")

    delimiter = ";"

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter=delimiter,
        )

        if reader.fieldnames is None:
            raise RuntimeError(
                f"Header non trovato: {path}"
            )

        fieldnames = [
            clean(x)
            for x in reader.fieldnames
        ]

        rows = []

        for raw_row in reader:
            row = {}

            for key, value in raw_row.items():

                # csv.DictReader mette eventuali colonne extra
                # sotto la chiave None.
                # Questo può accadere nella review perché SHORT_REASON
                # è l'ultimo campo e può contenere ';' non quotati.
                if key is None:
                    continue

                row[clean(key)] = clean(value)

            rows.append(row)

    return fieldnames, rows, delimiter


def require_fields(
    label,
    available_fields,
    required_fields,
):
    missing = [
        field
        for field in required_fields
        if field not in available_fields
    ]

    if missing:
        raise RuntimeError(
            f"{label}: campi mancanti: {missing}"
        )


def main():
    print("=" * 100)
    print("E1-A — QGIS REVIEW VS CANONICAL ANAS MAPPING")
    print("=" * 100)

    # ==================================================================
    # INPUT
    # ==================================================================

    print()
    print("A. INPUT")
    print("-" * 100)

    print("REVIEW    =", REVIEW)
    print("CANONICAL =", CANONICAL)

    (
        review_fields,
        review_rows,
        review_sep,
    ) = read_semicolon_csv(REVIEW)

    (
        canon_fields,
        canon_rows,
        canon_sep,
    ) = read_semicolon_csv(CANONICAL)

    print()
    print("REVIEW_DELIMITER    =", repr(review_sep))
    print("CANONICAL_DELIMITER =", repr(canon_sep))
    print("REVIEW_ROWS         =", len(review_rows))
    print("CANONICAL_ROWS      =", len(canon_rows))

    # ==================================================================
    # REQUIRED SCHEMA
    # ==================================================================

    review_required = [
        "SECTION_ID",
        "ROAD",
        "TGMA_LIGHT_2024",
        "QUALITY_CLASS",
        "MEASUREMENT_OPERATOR",
        "PRIMARY_SEGMENT_UID",
        "OPPOSITE_SEGMENT_UID",
        "PRIMARY_EDGE_IDS",
        "OPPOSITE_EDGE_IDS",
        "EXTERNAL_EXPOSURE",
        "ROLE_PROPOSAL",
        "CORRIDOR_GROUP",
        "INFORMATION_ROLE",
        "QGIS_REVIEW_STATUS",
    ]

    canonical_required = [
        "SECTION_ID",
        "ROAD",
        "TGMA_LIGHT_2024",
        "QUALITY_CLASS",
        "ROLE",
        "MEASUREMENT_OPERATOR",
        "OSM_PHYSICAL_SEGMENT",
        "RELEVANT_DIRECTED_EDGE_IDS",
        "PRIMARY_SEGMENT_UID",
        "OPPOSITE_SEGMENT_UID",
        "PRIMARY_EDGE_IDS",
        "OPPOSITE_EDGE_IDS",
        "EXTERNAL_EXPOSURE",
        "CORRIDOR_GROUP",
        "INFORMATION_ROLE",
        "QGIS_REVIEW_STATUS",
    ]

    require_fields(
        "REVIEW",
        review_fields,
        review_required,
    )

    require_fields(
        "CANONICAL",
        canon_fields,
        canonical_required,
    )

    print("REVIEW_SCHEMA        = PASS")
    print("CANONICAL_SCHEMA     = PASS")

    if len(review_rows) != 16:
        raise RuntimeError(
            f"Review: attese 16 righe, trovate {len(review_rows)}."
        )

    if len(canon_rows) != 16:
        raise RuntimeError(
            f"Canonical: attese 16 righe, trovate {len(canon_rows)}."
        )

    # ==================================================================
    # UNIQUE SECTION IDS
    # ==================================================================

    review_by_id = {}

    for row in review_rows:
        section_id = clean(
            row.get("SECTION_ID")
        )

        if not section_id:
            raise RuntimeError(
                "SECTION_ID vuoto nella review."
            )

        if section_id in review_by_id:
            raise RuntimeError(
                f"SECTION_ID duplicato nella review: {section_id}"
            )

        review_by_id[section_id] = row

    canon_by_id = {}

    for row in canon_rows:
        section_id = clean(
            row.get("SECTION_ID")
        )

        if not section_id:
            raise RuntimeError(
                "SECTION_ID vuoto nel canonical."
            )

        if section_id in canon_by_id:
            raise RuntimeError(
                f"SECTION_ID duplicato nel canonical: {section_id}"
            )

        canon_by_id[section_id] = row

    review_ids = set(review_by_id)
    canon_ids = set(canon_by_id)

    missing_in_canonical = sorted(
        review_ids - canon_ids
    )

    extra_in_canonical = sorted(
        canon_ids - review_ids
    )

    domain_match = (
        review_ids == canon_ids
        and len(review_ids) == 16
    )

    print()
    print("B. SECTION DOMAIN")
    print("-" * 100)

    print(
        "REVIEW_SECTION_IDS    =",
        len(review_ids),
    )

    print(
        "CANONICAL_SECTION_IDS =",
        len(canon_ids),
    )

    print(
        "MISSING_IN_CANONICAL  =",
        missing_in_canonical,
    )

    print(
        "EXTRA_IN_CANONICAL    =",
        extra_in_canonical,
    )

    print(
        "SECTION_IDS_MATCH     =",
        "YES" if domain_match else "NO",
    )

    # ==================================================================
    # DIRECT FIELD COMPARISON
    # ==================================================================

    direct_fields = [
        (
            "ROAD",
            "ROAD",
        ),
        (
            "TGMA_LIGHT_2024",
            "TGMA_LIGHT_2024",
        ),
        (
            "QUALITY_CLASS",
            "QUALITY_CLASS",
        ),
        (
            "MEASUREMENT_OPERATOR",
            "MEASUREMENT_OPERATOR",
        ),
        (
            "PRIMARY_SEGMENT_UID",
            "PRIMARY_SEGMENT_UID",
        ),
        (
            "OPPOSITE_SEGMENT_UID",
            "OPPOSITE_SEGMENT_UID",
        ),
        (
            "PRIMARY_EDGE_IDS",
            "PRIMARY_EDGE_IDS",
        ),
        (
            "OPPOSITE_EDGE_IDS",
            "OPPOSITE_EDGE_IDS",
        ),
        (
            "EXTERNAL_EXPOSURE",
            "EXTERNAL_EXPOSURE",
        ),
        (
            "ROLE_PROPOSAL",
            "ROLE",
        ),
        (
            "CORRIDOR_GROUP",
            "CORRIDOR_GROUP",
        ),
        (
            "INFORMATION_ROLE",
            "INFORMATION_ROLE",
        ),
        (
            "QGIS_REVIEW_STATUS",
            "QGIS_REVIEW_STATUS",
        ),
    ]

    mismatches = []
    section_pass = {}

    print()
    print("C. FIELD-BY-FIELD CHECK")
    print("-" * 100)

    for section_id in sorted(review_ids):

        if section_id not in canon_by_id:
            section_pass[section_id] = False
            continue

        review_row = review_by_id[
            section_id
        ]

        canon_row = canon_by_id[
            section_id
        ]

        local_errors = []

        # --------------------------------------------------------------
        # Direct fields
        # --------------------------------------------------------------

        for (
            review_field,
            canon_field,
        ) in direct_fields:

            review_value = clean(
                review_row.get(
                    review_field
                )
            )

            canon_value = clean(
                canon_row.get(
                    canon_field
                )
            )

            if review_value != canon_value:

                local_errors.append(
                    (
                        review_field,
                        canon_field,
                        review_value,
                        canon_value,
                    )
                )

        # --------------------------------------------------------------
        # Derived OSM_PHYSICAL_SEGMENT
        # --------------------------------------------------------------

        expected_segments = joined(
            review_row.get(
                "PRIMARY_SEGMENT_UID"
            ),
            review_row.get(
                "OPPOSITE_SEGMENT_UID"
            ),
        )

        actual_segments = clean(
            canon_row.get(
                "OSM_PHYSICAL_SEGMENT"
            )
        )

        if (
            expected_segments
            != actual_segments
        ):
            local_errors.append(
                (
                    "PRIMARY+OPPOSITE_SEGMENT_UID",
                    "OSM_PHYSICAL_SEGMENT",
                    expected_segments,
                    actual_segments,
                )
            )

        # --------------------------------------------------------------
        # Derived RELEVANT_DIRECTED_EDGE_IDS
        # --------------------------------------------------------------

        expected_edges = joined(
            review_row.get(
                "PRIMARY_EDGE_IDS"
            ),
            review_row.get(
                "OPPOSITE_EDGE_IDS"
            ),
        )

        actual_edges = clean(
            canon_row.get(
                "RELEVANT_DIRECTED_EDGE_IDS"
            )
        )

        if expected_edges != actual_edges:
            local_errors.append(
                (
                    "PRIMARY+OPPOSITE_EDGE_IDS",
                    "RELEVANT_DIRECTED_EDGE_IDS",
                    expected_edges,
                    actual_edges,
                )
            )

        section_pass[
            section_id
        ] = not local_errors

        status = (
            "PASS"
            if not local_errors
            else "FAIL"
        )

        print(
            f"SECTION_ID={section_id} | "
            f"ROAD={clean(review_row.get('ROAD')):<8} | "
            f"{status}"
        )

        for error in local_errors:
            mismatches.append(
                (section_id,) + error
            )

    # ==================================================================
    # SUMMARY
    # ==================================================================

    n_pass = sum(
        1
        for value in section_pass.values()
        if value
    )

    n_fail = (
        len(section_pass)
        - n_pass
    )

    print()
    print("D. SUMMARY")
    print("=" * 100)

    print(
        "SECTIONS_CHECKED       =",
        len(section_pass),
    )

    print(
        "SECTIONS_PASS          =",
        n_pass,
    )

    print(
        "SECTIONS_FAIL          =",
        n_fail,
    )

    print(
        "MISMATCHES             =",
        len(mismatches),
    )

    # ==================================================================
    # MISMATCH DETAILS
    # ==================================================================

    if mismatches:

        print()
        print("E. MISMATCH DETAIL")
        print("-" * 100)

        for (
            section_id,
            review_field,
            canon_field,
            review_value,
            canon_value,
        ) in mismatches:

            print()
            print(
                "SECTION_ID       =",
                section_id,
            )

            print(
                "REVIEW_FIELD     =",
                review_field,
            )

            print(
                "CANONICAL_FIELD  =",
                canon_field,
            )

            print(
                "REVIEW_VALUE     =",
                review_value,
            )

            print(
                "CANONICAL_VALUE  =",
                canon_value,
            )

    # ==================================================================
    # REVIEW-ONLY FIELDS
    # ==================================================================

    print()
    print("F. REVIEW-ONLY / NON-OPERATOR FIELDS")
    print("-" * 100)

    review_only = [
        "OSM_MATCH",
        "MATCH_DISTANCE_M",
        "ROAD_REF_NOTE",
        "SHORT_REASON",
    ]

    for field in review_only:

        if field in review_fields:
            status = "PRESENT_IN_REVIEW"
        else:
            status = "NOT_PRESENT"

        print(
            f"{field:<22} = "
            f"{status} / "
            f"NOT_REQUIRED_IN_OPERATOR_MAPPING"
        )

    # ==================================================================
    # FINAL VERDICT
    # ==================================================================

    overall_pass = (
        domain_match
        and n_pass == 16
        and len(mismatches) == 0
    )

    print()
    print("G. FINAL VERDICT")
    print("=" * 100)

    if overall_pass:

        print(
            "QGIS_REVIEW_TRANSFER = PASS"
        )

        print(
            "SECTION_IDS_MATCH     = YES"
        )

        print(
            "MAPPING_FIELDS_MATCH  = 16/16"
        )

        print(
            "MISMATCHES            = 0"
        )

        print(
            "READY_TO_RESUME_E1    = YES"
        )

    else:

        print(
            "QGIS_REVIEW_TRANSFER = FAIL"
        )

        print(
            "SECTION_IDS_MATCH     =",
            "YES"
            if domain_match
            else "NO",
        )

        print(
            f"MAPPING_FIELDS_MATCH  = "
            f"{n_pass}/{len(section_pass)}"
        )

        print(
            "MISMATCHES            =",
            len(mismatches),
        )

        print(
            "READY_TO_RESUME_E1    = NO"
        )


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print()
        print(
            "ERROR =",
            repr(exc),
        )

        print(
            "QGIS_REVIEW_TRANSFER = FAIL"
        )

        print(
            "READY_TO_RESUME_E1    = NO"
        )

    finally:
        print("=== RUN COMPLETATA ===")


