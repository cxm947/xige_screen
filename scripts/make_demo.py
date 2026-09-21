#!/usr/bin/env python3
"""Create a deterministic synthetic two-speaker ENGINEERING fixture, not a voice demo.

No movie, real voice, account, network access or model required.
"""
from pathlib import Path
import argparse
import math
from redub_core import init_project,import_asset,atomic_json,register_take,review
from redub_media import ffmpeg_path,run,wav_write,audio_metrics,np_module


def create(root,ff=None):
    root=Path(root).resolve();ff=ffmpeg_path(ff);np=np_module();rate=24000
    p=init_project(root,"synthetic://two-speakers","Engineering fixture: verify cast, cuts and final audio; tones are not acting")
    work=root/"work"/"fixture";work.mkdir(parents=True)
    seconds=5
    t=np.arange(rate*seconds)/rate
    source=np.sin(2*np.pi*220*t)*.025
    wav_write(work/"source.wav",source,rate)
    run([ff,"-v","error","-y","-f","lavfi","-i","color=c=0x243344:s=320x180:r=25:d=5",
         "-i",work/"source.wav","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-t","5",work/"source.mp4"])
    sid=import_asset(root,p,work/"source.mp4","video","Generated colored frames and sine tone, no real people")
    bed=np.sin(2*np.pi*100*t)*.0003;wav_write(work/"bed.wav",bed,rate)
    bedid=import_asset(root,p,work/"bed.wav","bed","Synthetic ambience")
    p["source"]={"asset":sid,"duration":5.0}
    p["scene"]={"keep":[{"start":0,"end":2.5},{"start":3,"end":5}],
                 "evidence":{"opening":"Fixture starts at first frame","ending":"Fixture ends at 5s","completeness":"Synthetic duration known by construction"}}
    p["mix"]["bed_asset"]=bedid
    p["mix"]["preserve_regions"]=[{"start":1.6,"end":2.0,"reason":"synthetic original cue"}]
    p["render"]["label"]="SYNTHETIC TEST";p["render"]["font"]="Arial"
    backend={"name":"synthetic-oscillator","version":"1","params":{"purpose":"engineering test only"}}
    for who,freq,start,end in [("A",330,.2,1.2),("B",550,3.4,4.9)]:
        n=round((end-start)*rate)
        tt=np.arange(n)/rate
        envelope=np.minimum(np.minimum(tt/.03,((n-1)/rate-tt)/.03),1).clip(0)
        # Active signal continues close to the last turn's end, exercising encoded tail loss.
        x=.06*np.sin(2*np.pi*freq*tt)*envelope
        file=work/(who+".wav");wav_write(file,x,rate)
        rid=import_asset(root,p,file,"reference","Synthetic oscillator; no real speaker")
        p["speakers"][who]={"label":"Synthetic "+who,"timbre_asset":rid}
        turn={"id":"turn_"+who,"speaker":who,"start":start,"end":end,"source_text":"Synthetic tone",
              "text":"Test "+who,"tts_text":"Test "+who,"action":"generate","cast_evidence":"Known oscillator frequency from fixture",
              "performance_asset":rid,"delivery":"Synthetic test, not a natural voice","beat":"Reply","claim_ids":[],"captions":[]}
        p["turns"].append(turn)
        rec=register_take(root,p,turn["id"],file,backend,audio_metrics(x,rate),"Synthetic fixture")
        turn["selected_take"]=rec["id"]
    atomic_json(root/"project.json",p)
    review(root,p,"source","agent","Checked deterministic fixture bounds","scripts/make_demo.py")
    review(root,p,"script","agent","Checked known fixture cast and turn intervals","scripts/make_demo.py")
    return p


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("project");parser.add_argument("--ffmpeg")
    args=parser.parse_args();create(args.project,args.ffmpeg)
    print("Created synthetic project. Render with: python scripts/redub.py render <project>")
