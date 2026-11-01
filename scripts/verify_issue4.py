#!/usr/bin/env python3
"""Independent offline QA of Issue4 outputs against immutable Issue3 sources."""
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
import imageio.v2 as imageio
from go2_ppo.video_materials import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
    output=a.output.resolve();root=Path(__file__).resolve().parents[1]
    summary=json.loads((output/'summary.json').read_text());assert summary['status']=='PASS'
    old=json.loads((root/'reports/issue3-results.json').read_text());old={q['run']:q for q in old['results']}
    protected=json.loads((output/'source-before.json').read_text())
    known={root/'logs/mixed-d/mixed128-lane-v3/policy_final.pt':'5d7fa7222067ff915942f2be546f9a9b3dcd6126b07eb3d7c8ea7fb4c05a4565',
           root/'logs/mixed-d/mixed128-contact-v4/policy_final.pt':'219c566e34ba832916bb7549cebb9eb989ad8d38f8ffd376ca53ed77f918e284',
           root/'assets/approved/heightfield.npz':'69979149fa5814316b7abea1b4ea01ccb12a0dfd6d36bfe72f55ce79d4071913',
           root.parent/'Physical-AI-Course-2026-Advanced1-Final-Assignment/logs/stage1/natural/training/slip20-margin012-64x1500/model_6500.pt':'c9bd93aa103db4e892623babff4de5c8da2cc7c0af5e31bcca389836738c0a2c'}
    for path,digest in known.items():assert sha(path)==digest,(path,'protected checkpoint/terrain SHA')
    for path,record in protected.items():assert sha(path)==record['sha256'],path
    # Frozen native source contains the actual URDF path; verify the original independently.
    import sys
    urdf=Path(sys.executable).parent.parent/'lib/python3.12/site-packages/genesis/assets/urdf/go2/urdf/go2.urdf'
    assert sha(urdf)=='4f306754e9b3d73930ac8362aa456eb8912f2e886665618e7eced9627c1704a4'
    checks=[];rows=[];progress_curves=[]
    for trial in summary['runs']:
        g=trial['goal'];rid=g['source_run_id'];source=root/'logs/rolling-native'/rid
        states=list(csv.DictReader((source/'states.csv').open()));times=np.array([float(q['time_s']) for q in states]);xs=np.array([float(q['x_m']) for q in states])
        start=xs[0];goal=start+4;first=int(np.flatnonzero(xs>=goal)[0]);arrival=times[first]
        assert abs(arrival-g['first_crossing_sample_s'])<1e-8
        assert xs[first-1]<goal<=xs[first];assert g['crossing_bracket']['before']['x_m']==xs[first-1]
        assert g['historical_numeric_gates']==old[rid]['numeric_gates']
        assert g['historical_numeric_pass']==old[rid]['numeric_pass']
        assert not any(q['physical_fallen']=='True' or q['out_of_terrain']=='True' for q in states)
        contacts=[json.loads(l) for l in (source/'contacts.jsonl').read_text().splitlines()]
        nonfoot_times=sorted(set(float(e['time_s']) for e in contacts if not e['foot']))
        assert nonfoot_times==sorted(set(float(e['time_s']) for e in g['nonfoot_events']))
        views={v['view'] for v in trial['videos']};assert views=={'side','oblique','overhead'}
        expected_last=int(np.ceil((arrival-1e-8)*25));frame_time=expected_last/25
        for v in trial['videos']:
            path=Path(v['path']);directory=path.parent
            assert sha(path)==v['sha256'];assert v['motion_frames']==expected_last+1
            mapping=list(csv.DictReader((directory/'timeline.csv').open()))
            assert len(mapping)==v['frames']==v['motion_frames']+50
            assert all(abs(float(q['video_pts_s'])-i/25)<1e-8 for i,q in enumerate(mapping))
            assert all(float(q['simulation_time_s'])==i/25 for i,q in enumerate(mapping[:v['motion_frames']]))
            assert all(q['simulation_time_s']=='' and q['kind']=='end_card' for q in mapping[v['motion_frames']:])
            audits=[json.loads(l) for l in (directory/'hud-frame-map.jsonl').read_text().splitlines()]
            assert len(audits)==v['motion_frames'];assert {q['baseline_y_px'] for q in audits}=={43.}
            max_error=0.;side_x=[]
            for audit in audits:
                E=np.asarray(audit['actual_camera_E']);K=np.asarray(audit['actual_camera_K'])
                ticks=audit['world_ticks']+audit['start_goal_markers']
                for tick in ticks:
                    local=E@np.array(tick['world_xyz_m']+[1.]);projected=K@local[:3]
                    if local[2]>0:
                        px=224+(projected[0]/projected[2]+.5)*1.3-.5
                        max_error=max(max_error,abs(tick['hud_x_px']-px))
                        assert tick['hud_y_px']==43.
                idx=audit['source_frame'];raw=source/'native-media/raw'/v['view']/f'frame{idx:06d}.png'
                assert sha(raw)==audit['raw_png_sha256']
                assert audit['nonfoot_contact_notified']==any(t<=idx/25+1e-8 for t in nonfoot_times)
                if v['view']=='side':side_x.append(next(q['hud_x_px'] for q in audit['world_ticks'] if q['world_xyz_m'][0]==4.))
            assert max_error<1e-8
            if side_x:assert side_x[-1]<side_x[0], 'Fixed world tick must flow left during net forward camera motion'
            reader=imageio.get_reader(path);first_card=None;card_mad=[]
            for idx,frame in enumerate(reader):
                if idx<v['motion_frames']:continue
                if first_card is None:first_card=frame.astype(float)
                card_mad.append(float(np.abs(frame.astype(float)-first_card).mean()))
            reader.close();assert len(card_mad)==50 and max(card_mad)<.1
            check=dict(run=rid,view=v['view'],goal_reached=True,arrival_sample_s=float(arrival),last_real_frame_s=frame_time,
                video_duration_s=v['frames']/25,source_sim_end_s=20.,card_s=2.,
                historical_pass=g['historical_numeric_pass'],baseline_y_range_px=v['decoded_baseline_y_range_px'],
                maximum_projection_error_px=max_error,decoded_card_max_mean_difference_8bit=max(card_mad),
                output_sha256=v['sha256'],full_decode_and_pts=v['actual_pts']['status'],status='PASS')
            checks.append(check)
        rows.append(dict(run=rid,start_x_m=float(start),goal_x_m=float(goal),crossing_before_s=float(times[first-1]),
            crossing_before_x_m=float(xs[first-1]),arrival_sample_s=float(arrival),arrival_sample_x_m=float(xs[first]),
            last_video_sim_s=frame_time,last_video_x_m=float(xs[expected_last*4]),
            original_20s_distance_m=old[rid]['distance_m'],historical_numeric_pass=g['historical_numeric_pass'],
            nonfoot_first_s=min(nonfoot_times) if nonfoot_times else '',end_reason=g['end_reason']))
        progress_curves.append((rid,times,xs-start,arrival,g['historical_numeric_pass']))
    assert len(checks)==18
    with (output/'goal-results.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    report=dict(status='PASS',files=len(protected),videos=len(checks),new_native_runs=0,new_PPO_updates=0,
        checks=checks,goal_results=rows,URDF_sha256=sha(urdf),all_source_hashes_unchanged=True,
        source_side_camera_Z_tracks=True,source_Z_motion_preserved=True,historical_F='USER_REVIEW_PENDING')
    (output/'independent-qa.json').write_text(json.dumps(report,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    for rid,t,x,arrival,passed in progress_curves:
        axs[0].plot(t,x,label=rid.removeprefix('issue3-D13550-')+(' oldPASS' if passed else ' oldFAIL'))
        axs[0].plot(arrival,4,'o',ms=4)
    axs[0].axhline(4,color='black',ls='--');axs[0].set(xlabel='Recorded simulation time (s)',ylabel='Base +X displacement (m)',title='Existing20s evidence / presentation goal4m');axs[0].legend(fontsize=7)
    for trial in summary['runs']:
        g=trial['goal'];rid=g['source_run_id'];lo,hi=g['original_world_x4_tick_y_range_px']
        axs[1].plot([lo,hi],[rid.removeprefix('issue3-D13550-')]*2,'o-',label=None)
    axs[1].axvline(43,color='black',ls='--',label='New HUD Y=43px (all views)')
    axs[1].set(xlabel='Screen Y (px)',title='Old world-X4 surface tick vs fixed HUD');axs[1].legend(fontsize=7)
    fig.savefig(output/'goal-and-ruler-validation.png',dpi=140);plt.close(fig)
    print(json.dumps({k:report[k] for k in ('status','files','videos','new_native_runs','all_source_hashes_unchanged')}))


if __name__=='__main__':main()
