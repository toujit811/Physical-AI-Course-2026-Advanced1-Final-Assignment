"""Common provisional media helpers; no learning or physical control changes."""
import csv,json,hashlib,struct,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import imageio.v2 as imageio
import imageio_ffmpeg
from .stage2_visual_diagnostic import texture_rgb

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/video-materials-20261030'
MEDIA=ROOT/'logs/video-materials-20261030'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def dump(p,o):Path(p).write_text(json.dumps(o,indent=2,allow_nan=False))
def rows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))
def csvout(p,records):
    if not records:return
    with Path(p).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in records for k in r)));w.writeheader();w.writerows(records)
def flat_rgb():return texture_rgb(np.array([[0.]],dtype=np.float32))[0,0]
def frame_indices(times):
    t=np.asarray(times,dtype=float)
    if len(t)<2 or np.any(np.diff(t)<=0):raise ValueError('Need monotonic recorded times')
    wanted=np.arange(int(np.floor((t[-1]-t[0])*25+1e-7))+1)/25+t[0]
    indices=np.searchsorted(t,wanted-1e-8)
    if np.max(abs(t[indices]-wanted))>1e-6:raise ValueError('Saved times do not support exact 25fps replay')
    return indices.tolist()
def post_terminal(t,terminal):return terminal is not None and t>terminal+1e-8
def font(size):
    f=next(iter(Path('/System/Library/Fonts').glob('*W3.ttc')),None)
    return ImageFont.truetype(str(f),size) if f else ImageFont.load_default(size=size)
def preview_frame(rgb,title,t,flat):
    im=Image.new('RGB',(1280,720),(240,244,248));im.paste(Image.fromarray(rgb).resize((960,540),Image.Resampling.LANCZOS),(160,80))
    d=ImageDraw.Draw(im);d.text((26,9),'PROTOTYPE / レイアウト未確定',fill=(120,55,20),font=font(25))
    d.text((26,44),title+f'  t={t:.2f}s',fill=(25,40,55),font=font(23))
    d.text((25,640),'地形の高さ (cm)',fill=(25,40,55),font=font(25))
    bar=Image.fromarray(texture_rgb(np.linspace(-.012,.04,800)[:,None])).resize((800,24));im.paste(bar,(350,640));d=ImageDraw.Draw(im)
    for value in [-1.2,0.,2.,4.]:
        x=350+(value+1.2)/5.2*800;d.line((x,666,x,674),fill=(20,30,40),width=2)
        d.text((x-18,675),f'{value:g}',fill=(25,40,55),font=font(22))
    if flat:
        x=350+1.2/5.2*800;d.polygon([(x,635),(x-8,625),(x+8,625)],fill=(220,40,40))
        d.text((25,679),'FLAT / 全域0cm',fill=(25,40,55),font=font(19))
    return np.asarray(im)
def writer(p):
    return imageio.get_writer(str(p),fps=25,codec='libx264',pixelformat='yuv420p',macro_block_size=2,
        ffmpeg_params=['-profile:v','high','-crf','18','-maxrate','5M','-bufsize','10M','-movflags','+faststart',
        '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
        '-vf','scale=out_color_matrix=bt709:out_range=tv,setsar=1,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709',
        '-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709','-an'])
def inspect_video(p,decode=True):
    reader=imageio.get_reader(p);meta=reader.get_meta_data();count=0
    if decode:
        for frame in reader:
            if frame.shape!=(720,1280,3):raise ValueError((p,frame.shape))
            count+=1
    else:count=reader.count_frames()
    reader.close()
    probe=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(p),'-f','null','-'],capture_output=True,text=True)
    if probe.returncode:raise ValueError(probe.stderr[-2000:])
    header=probe.stderr.split('Output #')[0]
    assert all(s in header for s in ['Video: h264 (High)','yuv420p(tv, bt709, progressive)','1280x720','25 fps']),header
    assert 'Audio:' not in header
    atoms=[]
    with Path(p).open('rb') as f:
        while True:
            b=f.read(8)
            if len(b)<8:break
            size,typ=struct.unpack('>I4s',b)
            if size==1:size=struct.unpack('>Q',f.read(8))[0];skip=16
            else:skip=8
            atoms.append(typ.decode('ascii',errors='replace'))
            if size==0:break
            f.seek(size-skip,1)
    assert atoms.index('moov')<atoms.index('mdat')
    return dict(path=str(Path(p).resolve()),sha256=sha(p),frames=count,fps=meta['fps'],size=meta['size'],duration_s=count/25,
        codec='H.264 High',pixel_format='yuv420p',color='SDR BT.709',progressive=True,audio=False,faststart=True,bytes=Path(p).stat().st_size)
