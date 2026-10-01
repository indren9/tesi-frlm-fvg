"""Verify and preserve the Andrea-approved Chat 10.15 reconstruction (D88).

No rematching, OD rerouting, FROZEN writes, or AFIR qualification.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--onedrive', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    reg = pd.read_csv(args.repo / '06_GOVERNANCE/ARTIFACT_REGISTER.csv').set_index('artifact_id')
    roots = {name: args.onedrive / 'Università/UniUD/Tesi' / name
             for name in ['TESI_BASELINE_SAFE', 'TESI_THESIS_STORAGE']}
    evidence = []

    def verify(path, expected, identity):
        actual = digest(path)
        assert actual == expected.lower(), (identity, actual, expected)
        evidence.append(dict(identity=identity, sha256=actual, size_bytes=path.stat().st_size))
        return path

    def resolve(artifact):
        row = reg.loc[artifact]
        assert row.artifact_status in ['CURRENT', 'FROZEN']
        p = roots[row.storage_root] / row.logical_relative_path.replace('\\', '/')
        return verify(p, row.sha256, artifact)

    source = resolve('LIGHT_PUN_ELIGIBLE_EVSE_V02')
    resolve('LIGHT_PUN_ELIGIBLE_EVSE_MANIFEST_V02')
    graph = resolve('F56_G_OSM_OPERATIVO_V01')
    mf = resolve('F56_G_OSM_FINAL_MANIFEST_V01')
    manifest = json.loads(mf.read_text(encoding='utf-8'))
    dbmember = next(m for m in manifest['computational_artifacts'] if m['filename'] == 'osm_directed_edges_v02.sqlite')
    db = verify(mf.parent / dbmember['filename'], dbmember['sha256'], 'F56_G_OSM_FINAL_MANIFEST_V01::' + dbmember['filename'])
    scratch = args.repo / '.scratch_chat10_15'
    v = pd.read_csv(scratch / 'pun_validated_positions_61_v01.csv')
    r = pd.read_csv(scratch / 'pun_edge_relations_61_v01.csv')
    m = pd.read_csv(scratch / 'pun_matching_candidates.csv')
    d = pd.read_csv(scratch / 'pun_d71_reconstruction.csv')
    pun = pd.read_csv(source, sep=';')
    assert len(v) == 61 and v.pun_position_id.nunique() == 61
    assert not v.duplicated(['latitude', 'longitude']).any()
    assert v.validation_stage.value_counts().to_dict() == {'D71_D72_FIRST42': 42, 'D73_SECOND_AUTOMATCH19': 19}
    assert v.groupby('validation_stage').evse_count.sum().to_dict() == {'D71_D72_FIRST42': 108, 'D73_SECOND_AUTOMATCH19': 55}
    assert len(r) == 106 and r.edge_id.nunique() == 93
    assert set(r.pun_position_id) == set(v.pun_position_id)
    assert not r.duplicated(['pun_position_id', 'edge_id']).any()
    assert r.routing_code.eq(1).all()
    assert len(pun) == 302 and pun.ID_EVSE.nunique() == 302
    ids = [x for row in v.evse_ids for x in row.split('|')]
    assert len(ids) == len(set(ids)) == 163
    assert set(ids) <= set(pun.ID_EVSE.astype(str))
    for row in v.itertuples():
        pp = pun[(pun.latitude == row.latitude) & (pun.longitude == row.longitude)]
        assert set(pp.ID_EVSE.astype(str)) == set(row.evse_ids.split('|'))
        assert len(pp) == row.evse_count
        assert np.isclose(pp.power_nominal_kw.sum(), row.power_kw)
    excluded = pun[~pun.ID_EVSE.astype(str).isin(ids)]
    assert len(excluded) == 139 and len(excluded.groupby(['latitude', 'longitude'])) == 29

    # Preserve the approved exact first-stage membership, including the five
    # explicitly reconstructed normalization/coherence cases, without inferring
    # a new general matching rule for future data.
    extra = {(45.799738,13.061159),(45.92452,13.61436),(45.942023,13.6342),(45.953791,13.615149),(46.098878,13.226335)}
    dfirst = set(map(tuple, d.loc[d.D71_AUTO, ['latitude','longitude']].to_numpy())) | extra
    first = v[v.validation_stage.eq('D71_D72_FIRST42')]
    assert set(map(tuple, first[['latitude','longitude']].to_numpy())) == dfirst
    joined = m.merge(d[['latitude','longitude','nearest_m']], on=['latitude','longitude'], validate='one_to_one', how='left')
    joined['is_first'] = [tuple(x) in dfirst for x in joined[['latitude','longitude']].to_numpy()]
    delta = joined.best_match_m - joined.nearest_m
    selected = joined[(~joined.is_first) & (joined.best_match_m <= 75) & (delta <= 6)]
    second = v[v.validation_stage.eq('D73_SECOND_AUTOMATCH19')]
    assert set(map(tuple, selected[['latitude','longitude']].to_numpy())) == set(map(tuple, second[['latitude','longitude']].to_numpy()))
    assert (selected.match_ref_evidence | selected.match_name_evidence).all()
    assert second.best_match_m.le(75).all() and second.delta_match_vs_nearest_m.le(6).all()

    uids = sorted(v.matched_segment_uid.unique())
    con = sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)
    edges = pd.read_sql_query('SELECT edge_id,segment_uid,u,v,way_direction,length_m,routing_code FROM directed_edges WHERE segment_uid IN (' + ','.join('?' for _ in uids) + ')', con, params=uids)
    con.close()
    expected = v[['pun_position_id','matched_segment_uid']].merge(edges, left_on='matched_segment_uid', right_on='segment_uid')
    assert set(zip(expected.pun_position_id, expected.edge_id)) == set(zip(r.pun_position_id, r.edge_id))
    cmp = r.merge(edges, on='edge_id', suffixes=('', '_source'), validate='many_to_one')
    for col in ['segment_uid', 'u', 'v', 'way_direction', 'routing_code']:
        assert cmp[col].equals(cmp[col + '_source'])
    assert np.allclose(cmp.length_m, cmp.length_m_source, rtol=0, atol=1e-10)
    where = 'segment_uid IN (' + ','.join("'" + x.replace("'", "''") + "'" for x in uids) + ')'
    geo = pyogrio.read_dataframe(graph, layer='G_OSM_operativo_segments_v01', columns=['segment_uid','osm_u','osm_v'], where=where).set_index('segment_uid')
    assert geo.crs.to_epsg() == 32632
    pts = gpd.GeoSeries(gpd.points_from_xy(v.longitude, v.latitude), crs=4326).to_crs(geo.crs)
    errors = []
    for i, row in v.iterrows():
        g = geo.loc[row.matched_segment_uid]
        frac = float(shapely.line_locate_point(g.geometry, pts.iloc[i]) / g.geometry.length)
        assert abs(frac - row.segment_geometry_fraction_osm_u_to_v) < 1e-12
        rel = r[r.pun_position_id.eq(row.pun_position_id)]
        for rr in rel.itertuples():
            assert rr.way_direction in ['FWD','BWD']
            assert (rr.u,rr.v) == ((g.osm_u,g.osm_v) if rr.way_direction == 'FWD' else (g.osm_v,g.osm_u))
            offset = (frac if rr.way_direction == 'FWD' else 1-frac) * rr.length_m
            errors.append(abs(offset - rr.edge_offset_from_start_m))
            assert -1e-9 <= rr.edge_offset_from_start_m <= rr.length_m + 1e-9
    assert max(errors) < 1e-8
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    for name in ['pun_validated_positions_61_v01.csv','pun_edge_relations_61_v01.csv','pun_matching_candidates.csv','pun_d71_reconstruction.csv','pun_mapping_summary_v01.json','pun_reconstruct.py','pun_second.py','materialize_pun61_mapping.py']:
        shutil.copyfile(scratch / name, out / name)
    shutil.copyfile(__file__, out / 'promote_pun61_v01.py')
    qa = dict(status='PASS', decision='D88', date='2026-10-01', positions=61, first_stage=42, second_stage=19, eligible_evse=302, validated_evse=163, excluded_positions=29, excluded_evse=139, directed_relations=106, unique_directed_edges=93, max_offset_error_m=max(errors), source_hashes=evidence, phase_i_run_ready='NO', afir_qualification='NOT_INFERRED', b3_coverage='SEPARATE_PREPROCESSING')
    (out / 'QA_v01.json').write_text(json.dumps(qa, indent=2, ensure_ascii=False)+'\n',encoding='utf-8')
    (out / 'README.md').write_text('''# LIGHT PUN-61 solver-ready membership v01

CURRENT under D88, explicitly approved by Andrea on 2026-10-01.
Preserves the exact approved Chat 10.15 reconstruction: 42 first-stage + 19
second-automatch positions, 163 EVSE; 29 residual positions/139 EVSE stay in
power accounting but contribute neither geographic gaps nor B3.

Second stage: strong road name/ref match <=75 m and distance no more than
6 m above the physically nearest segment. First-stage reconstruction includes
the five normalization/coherence cases recorded in the preserved producer.
This approves this exact membership, not a new generic matcher for future data.

The two pun_*61_v01.csv files are the solver-facing membership and directed
edge/offset tables. IDs PUNPOS_001..061 are scoped to this package version.
FWD/BWD follow D72: 16 single-direction and 45 bidirectional positions, 106
relations on 93 distinct directed edges. Do not sum power over relation rows:
they refer to the same physical PUN. Power remains EVSE nominal power.

Progressiva is the projection fraction on the frozen EPSG:32632 segment,
scaled by the frozen directed edge length; BWD uses 1-fraction. On an actual
occurrence in LIGHT_PATH_EDGE_LONGITUDINAL_V01, join by edge_id and compute
path_offset_m = cum_start_m + edge_offset_from_start_m. Keep path_idx and
edge_order: repeated traversals are distinct. No nearest positive-flow snap
and no OD rerouting. This package does not duplicate the longitudinal artifact.

Remaining files preserve reconstruction evidence and original scratch
producers byte-for-byte. Their historical scratch/non-promoted wording and
Windows paths are provenance only; D88 and this manifest govern promotion.
promote_pun61_v01.py verifies registered inputs and exact preserved membership.
Resolve storage through TESI_RECORDKEEPING_PROTOCOL_V1, not legacy paths.

AFIR exit/re-entry/boundary relations and PUN AFIR pool qualification remain
separate and open. B3 coverage is separate preprocessing under D74/D77.
No solver selected; no Phase I run; D57-D87 and FROZEN are unchanged.
''',encoding='utf-8')
    members = [dict(relative_path=p.name, sha256=digest(p), size_bytes=p.stat().st_size) for p in sorted(out.iterdir())]
    package = dict(artifact_id='LIGHT_PUN61_SOLVER_READY_PACKAGE_V01', artifact_status='CURRENT', storage_root='TESI_THESIS_STORAGE', logical_relative_path='07_DELIVERIES/LIGHT_MODEL_V1/LIGHT_PUN61_SOLVER_READY_v01.zip', decision='D88', approval_reference='Andrea explicit approval; Chat 10.15 continuation 2026-10-01; prior conversation 6abe310c-64c0-83ed-beb7-ffd62ab79638', source_hashes=evidence, members=members)
    (out/'manifest_v01.json').write_text(json.dumps(package,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    archive = out.parent / 'LIGHT_PUN61_SOLVER_READY_v01.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):
            info = zipfile.ZipInfo(p.name, date_time=(2026,10,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    print(json.dumps(dict(qa=qa, manifest_sha256=digest(out/'manifest_v01.json'), members=len(members)),indent=2))


if __name__ == '__main__':
    main()
