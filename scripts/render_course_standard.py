"""Render a separate standard copy from immutable captured native RGB, never physics."""
import argparse,csv,json
from pathlib import Path
import numpy as np
from go2_ppo.course_media import CourseRecorder
from go2_ppo.video_materials import sha


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--subdir',default='standard-final');a=p.parse_args()
    if Path(a.subdir).name!=a.subdir or a.subdir in ('.','..'):p.error('one new subdirectory name required')
    run=a.run.resolve();media=run/'native-media'
    if (media/a.subdir).exists():raise FileExistsError('Preserve existing output; choose a new subdirectory')
    data=np.load(media/'terrain-input.npz');rec=object.__new__(CourseRecorder)
    rec.output=media;rec.closed=True;rec.terrain={'x':data['x'],'y':data['y'],'height_m':data['height_m']}
    rec.records=[json.loads(l) for l in (media/'camera-frame-map.jsonl').read_text().splitlines()]
    for r in rec.records:
        if sha(Path(r['raw_png']))!=r['raw_png_sha256']:raise ValueError('Captured RGB SHA mismatch')
    with (run/'states.csv').open() as f:states=list(csv.DictReader(f))
    originals={str(p):sha(p) for p in media.glob('native-*-raw.mp4')}
    result=json.loads((run/'result.json').read_text())
    videos=rec.present(result,states,end_card_frames=0,standard_subdir=a.subdir)
    assert all(sha(Path(p))==h for p,h in originals.items())
    (media/a.subdir/'render-provenance.json').write_text(json.dumps({'input_result_sha256':sha(run/'result.json'),'states_sha256':sha(run/'states.csv'),'course_media_sha256':sha(Path(__file__).resolve().parents[1]/'src/go2_ppo/course_media.py'),'source_frames_unchanged':True,'original_raw_unchanged':originals,'physics_steps':0,'PPO_updates':0,'videos':videos},indent=2)+'\n')
    print(f'Rendered three standards from unchanged native RGB: {media/a.subdir}')

if __name__=='__main__':main()
