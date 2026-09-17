# 5.9D-B1 external dependency preservation note

Date: 2026-09-17

The B1 GraphHopper support dependencies are external/rematerializable inputs, not thesis FROZEN artifacts.

## Recorded dependencies

- `italy-260801.osm.pbf` — 2,215,945,433 bytes; project SHA256 `f7b305c6a267a426619fd03dd0c63b3da3ec72f89defe6431dee71d64b172538`; official MD5 `da57eabc25eb8c27cc44a4916122902e`.
- `graphhopper-web-11.0.jar` — SHA256 `b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def`.
- Temurin JRE 21.0.10+7 ZIP — SHA256 `a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae`.
- GraphHopper graph `graph_italy_260801_b5compat_v01` — regenerable cache; 9 files, 467,711,112 bytes; member hashes are preserved by the B1 graph manifest.

## Recovery audit

`RECOVERY_QGIS_PC_AZIENDALE_20260917.zip` preserves B1 manifests, run logs, configurations and analytical outputs, but does not contain the PBF, GraphHopper JAR, JRE ZIP or final graph directory.

On 2026-09-17 the recorded Geofabrik PBF URL returned HTTP 200 with the expected size and its `.md5` endpoint still returned the recorded official MD5. The pinned GraphHopper 11.0 and Temurin 21.0.10+7 release URLs also returned HTTP 200 with the expected release-asset sizes.

The acquisition URLs remain encoded in `B1_EXT_GH_00_preflight.ps1` and `B1_EXT_GH_01_materialize_v06.ps1`.

Conclusion: the external dependency bytes are not locally preserved in the QGIS recovery archive, but the exact versions, hashes, acquisition URLs and rebuild provenance needed for controlled rematerialization are preserved in Git.
