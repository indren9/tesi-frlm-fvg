B1-EXT-RUN PACKAGE — G_EXT_ITALY_B1_v01

ORDER OF EXECUTION
==================
1) Open Windows PowerShell on the company PC.
2) Put these files directly in:
   C:\Tesi\tools\
3) Run ONLY the read-only preflight first:

   Set-ExecutionPolicy -Scope Process Bypass
   cd C:\Tesi\tools
   .\B1_EXT_00_preflight_v02.ps1

4) DO NOT continue unless the final line says:
   B1_EXT_PREFLIGHT = PASS_TO_EXECUTE

5) Then run:
   .\B1_EXT_01_execute_v02.ps1

The execute script:
- re-runs preflight;
- downloads Geofabrik italy-260801 only if absent;
- verifies server MD5, size and records SHA256;
- pulls the pinned OSRM 26.7.3 Debian image only if absent;
- builds MLD in a timestamped additive run directory;
- starts a local server on 127.0.0.1:5005;
- snaps project centroids;
- runs 2,895 IE + 2,895 EI routes separately;
- detects the FVG boundary crossing;
- maps to the frozen A1 gateway mapping without nearest-gateway heuristics;
- creates B1_RELEVANT_ROUTING_SUBGRAPH from actually used OSRM annotation edges;
- performs targeted QA only;
- verifies frozen internal hashes before and after;
- never uses ANAS 2025, Gravity, EE, or phi_EE.

NO-OVERWRITE
============
Every analytical run is written to:
C:\Tesi\Tesi_QGIS\03_output_temporanei\fase_5_9D\B1_EXT\
  G_EXT_ITALY_B1_v01_run_YYYYMMDD_HHMMSS\

The original PBF is stored once under:
C:\Tesi\Tesi_QGIS\00_originali\rete_stradale\osm\italy_archive\

No output is promoted to 02_package by this script.

EXPECTED OUTPUTS
================
outputs\endpoint_snap_table.csv
outputs\gateway_mapping_frozen_A1_v01.csv
outputs\B1_IE_EI_routing_table.csv
outputs\B1_crossing_gateway_attribution.csv
outputs\B1_RELEVANT_ROUTING_SUBGRAPH.csv.gz
outputs\B1_targeted_edge_semantic_QA.csv
outputs\B1_boundary_interface_QA.csv
outputs\B1_targeted_QA_flags.csv
outputs\B1_QGIS_flagged_paths.gpkg      (only if flags exist)
outputs\B1_EXT_summary_v01.json
B1_EXT_manifest_v01.json

When the run completes, send Chat 5.9D:
- the full final console block;
- outputs\B1_EXT_summary_v01.json;
- B1_EXT_manifest_v01.json;
- outputs\B1_targeted_QA_flags.csv if non-empty.

=== RUN COMPLETATA ===
