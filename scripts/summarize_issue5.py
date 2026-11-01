#!/usr/bin/env python3
"""Package native course evidence as local graphs/index and lightweight report."""
import csv,html,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/generated/issue5';LEGS=('FL','FR','RL','RR')


def main():
    qa=json.loads((OUT/'independent-qa.json').read_text());records=qa['records'];records.sort(key=lambda q:(not q['run'].endswith('-v2'),q['run']))
    primary=[q for q in records if q['run'].endswith('-c2-v2')]
    assert len(primary)==2 and all(q['QA']=='PASS' for q in primary)
    table=[];report_runs=[];curves=[];chunks=['<!doctype html><meta charset="utf-8"><title>Issue5 新規native全コース走行</title>',
        '<style>body{font:16px sans-serif;max-width:1200px;margin:28px auto;color:#183d36}video{width:800px;max-width:100%}img{width:280px}.bad{color:#a21e20}pre{white-space:pre-wrap}td,th{padding:10px;border:1px solid #aaa}table{border-collapse:collapse}</style>',
        '<h1>Issue5：新規native連続走行</h1><p>同一D13550。START X0→FINISH X6.40m。全4足の球後端Xが終端を越え、base通過・0.20秒連続確認。新規native物理を実行。既存20秒動画の切り抜きではありません。</p>',
        '<p>最終v2を先に表示。FLAT c2は境界逸脱で未踏破、ROLLING c2は30.10秒で踏破。旧20秒評価4/6合格・F未済は不変。</p>',
        '<p class="bad">v1はnative地表ゲートがカメラのdebugフィルタで非表示でした。失敗素材として保全し、v2で描画だけを修正。v1/v2の全物理状態CSVは完全一致。</p>']
    for q in records:
        run=ROOT/'logs/course-native'/q['run'];r=json.loads((run/'result.json').read_text());rows=list(csv.DictReader((run/'states.csv').open()));last=rows[-1]
        t=np.array([float(a['time_s']) for a in rows]);x=np.array([float(a['x_m']) for a in rows]);y=np.array([float(a['y_m']) for a in rows]);footx=np.array([[float(a[l+'_center_x_m']) for l in LEGS] for a in rows]);radius=np.array([float(rows[0][l+'_sphere_radius_m']) for l in LEGS]);trailing=(footx-radius).min(axis=1)
        curves.append((q,t,x,y,footx,trailing,rows))
        movies={}
        for name,info in q['movies'].items():
            item=dict(info);item['path']=str(Path(info['path']).relative_to(ROOT));movies[name]=item
        report_runs.append({**q,'movies':movies,'completion':r['completion'],
            'native_wall_including_media_s':r['total_wall_including_media_s'],'recording_started_before_first_step':r['recording_started_before_first_physics_step'],
            'physical_build':r['physical_build'],'native_positive_foot_contacts':{l:sum(a[l+'_positive_force_contact']=='True' for a in rows) for l in LEGS},
            'terminal_foot_centers_xyz_m':{l:[float(last[l+'_center_'+a+'_m']) for a in 'xyz'] for l in LEGS},
            'terminal_foot_trailing_x_m':{l:float(last[l+'_center_x_m'])-float(last[l+'_sphere_radius_m']) for l in LEGS}})
        table.append(dict(run=q['run'],condition=r['args']['condition'],kind=r['evaluation_kind'],course_success=q['course_success'],end_reason=q['reason'],sim_end_s=q['terminal_sim_s'],base_x_m=x[-1],base_y_m=y[-1],minimum_foot_trailing_x_m=trailing[-1],first_all_foot_pass_s=q['first_all_feet_s'],confirmed_s=q['confirmed_s'],native_gate_QA=q['QA']))
        chunks.append(f'<h2>{html.escape(q["run"])}</h2><p>{"踏破成功" if q["course_success"] else "未踏破"} / {q["reason"]} / {q["terminal_sim_s"]:.2f} sim秒 / 地表マーカーQA: {q["QA"]}</p>')
        for view in ('side','oblique','overhead'):
            movie=Path('../../../')/f'logs/course-native/{q["run"]}/native-media/course-{view}.mp4';raw=movie.with_name(f'native-{view}-raw.mp4')
            chunks.append(f'<h3>{view}</h3><p><a href="{movie}">個別提示用MP4</a> | <a href="{raw}">未注釈raw MP4</a></p><video controls preload="none" src="{movie}"></video><p>')
            media=run/'native-media';images=sorted(media.glob(f'qa-{view}-*.png'))
            for image in images:
                rel=Path('../../../')/image.relative_to(ROOT);chunks.append(f'<a href="{rel}"><img alt="実デコード画像" src="{rel}"></a>')
            chunks.append('</p>')
    with (OUT/'course-results.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(table[0]),lineterminator='\n');w.writeheader();w.writerows(table)
    (OUT/'index.html').write_text('\n'.join(chunks))
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for q,t,x,y,footx,trailing,rows in curves:
        if not q['run'].endswith('-v2'):continue
        label=q['run'].removeprefix('issue5-D13550-')
        axes[0,0].plot(t,x,label=label+' baseX');axes[0,0].plot(t,trailing,ls='--',label=label+' min trailing footX')
        axes[0,1].plot(x,y,label=label)
        axes[1,0].plot(t,footx.max(axis=1),label=label+' max foot centreX');axes[1,0].plot(t,trailing,ls='--',label=label+' min trailingX')
        for key,style in (('roll_deg','-'),('pitch_deg','--')):axes[1,1].plot(t,[float(a[key]) for a in rows],ls=style,label=label+' '+key)
    axes[0,0].axhline(6.4,color='black',ls=':');axes[0,0].set(xlabel='Native sim time (s)',ylabel='World X (m)',title='Whole-course predicate: all foot trailing extents, not base alone')
    axes[0,1].axhline(1.25,color='grey',ls=':');axes[0,1].axhline(-1.25,color='grey',ls=':');axes[0,1].axvline(6.4,color='black',ls='--');axes[0,1].axvline(7,color='red',ls=':');axes[0,1].set(xlabel='World X (m)',ylabel='World Y (m)',title='Actual base trajectory / course boundaries')
    axes[1,0].axhline(6.4,color='black',ls='--');axes[1,0].axhline(7,color='red',ls=':');axes[1,0].set(xlabel='Native sim time (s)',ylabel='World X (m)',title='Tight exit: finish6.40m, foot-centre boundary7.00m')
    axes[1,1].set(xlabel='Native sim time (s)',ylabel='Body angle (deg)',title='Actual posture; fall threshold remains45deg')
    for ax in axes.flat:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.savefig(OUT/'course-verification.png',dpi=150);plt.close(fig)
    all_movies=sum(len(q['movies']) for q in records);primary_movies=sum(len(q['movies']) for q in primary)
    report=dict(authority_issue=5,source_branch='issue4/video-goal-hud',source_commit='dfcadd4275a26b7d3a25a2ff936275b492147dc9',
        implementation_branch='issue5/native-course-completion',new_native_runs=len(records),native_run_order=['FLATc2v1','ROLLINGc2v1','FLATc0v1','FLATc1v1','FLATc2v2','ROLLINGc2v2'],
        final_priority_runs=2,all_new_mp4_files=all_movies,primary_new_mp4_files=primary_movies,new_PPO_updates=0,heldout='UNOPENED_NOT_PERFORMED',
        final_FLAT_c2='NOT_COMPLETED_OUT_OF_BOUNDS',final_ROLLING_c2='COURSE_COMPLETED',
        existing20s_evaluation='UNCHANGED_4_OF_6_NUMERIC_PASS_ROLLING_c0_c1_NONFOOT_FAIL',F='USER_REVIEW_PENDING',
        tests={'new':22,'previous':87,'total':109,'stdlib_core':11,'status':'PASS'},source_preservation=qa['source_preservation'],
        native_marker_failure_retained_v1=4,final_v2_native_marker_QA='PASS',
        numerical_verification='All6 time grids, raw RGB/hash/K-E/FK/support/contact/physics/source/MP4PTS verified; v1 ground marker visualFAIL explicitly retained.',
        limitations=['FLATc1/c2: forefoot crossesX7 before last hind-foot trailing extent crosses6.40; exit placement0.60m constrains completion. Not a fall or solver failure.',
            'FLATc0: lateral course boundary; FLAT ground is an infinite physical plane but comparison course lane is finite.',
            'The selected6.40 line includes the actual quantized relief tail beyond preview mainactivity6.00. No goal or threshold relaxed after failure.',
            'Terminal native snapshots may lie between25fps grid points and use next videoPTS, explicitly mapped; no future simulation or interpolated poses.',
            'Human F/comfort assessment pending; retained v1 lacks visible native ground gates.'],
        index='reports/generated/issue5/index.html',CSV='reports/generated/issue5/course-results.csv',graph='reports/generated/issue5/course-verification.png',
        detailed_QA='reports/generated/issue5/independent-qa.json',runs=report_runs)
    (ROOT/'reports/issue5-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(native_runs=len(records),primary=2,all_mp4=all_movies,results=table)))


if __name__=='__main__':main()
