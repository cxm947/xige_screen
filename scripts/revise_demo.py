#!/usr/bin/env python3
"""Demonstrate changing synthetic A while reusing B; never a real speech generator."""
from pathlib import Path
import argparse
import json
from redub_core import (load_project,writer_lock,atomic_json,project_status,fail,review,
                        register_take,selected_receipt,asset_path)
from redub_media import np_module,wav_write,audio_metrics


def revise(root):
    root=Path(root).resolve()
    with writer_lock(root):
        p=load_project(root)
        if p["request"]["url"]!="synthetic://two-speakers" or [t["id"] for t in p["turns"]]!=["turn_A","turn_B"]:
            fail("DEMO_ONLY","This helper only edits an unmodified make_demo project")
        a,b=p["turns"]
        if a["text"]!="Test A":fail("DEMO_ALREADY_REVISED","Use a fresh demo project for this one-time demonstration")
        before_b=selected_receipt(root,p,b)
        a["text"]=a["tts_text"]="Revised test A"
        atomic_json(root/"project.json",p)
        stale=project_status(root,p)
        atomic_json(root/"work"/"demo-stale-status.json",stale)
        if stale["counts"]["ready"]!=1 or stale["counts"]["stale"]!=1:
            fail("DEMO_REGRESSION","Expected only A to become stale")
        np=np_module();rate=p["settings"]["sample_rate"];n=round((a["end"]-a["start"])*rate)
        t=np.arange(n)/rate
        envelope=np.minimum(np.minimum(t/.03,((n-1)/rate-t)/.03),1).clip(0)
        x=.055*np.sin(2*np.pi*330*t)*envelope*(.85+.15*np.sin(2*np.pi*3*t))
        path=root/"work"/"revised-A.wav";wav_write(path,x,rate)
        backend={"name":"synthetic-oscillator","version":"2","params":{"purpose":"engineering revised fixture, not speech"}}
        take=register_take(root,p,a["id"],path,backend,audio_metrics(x,rate),"Complete new synthetic A tone for continuation demonstration")
        a["selected_take"]=take["id"]
        review(root,p,"script","agent","Checked revised synthetic fixture, no claim of human audition","scripts/revise_demo.py")
        after_b=selected_receipt(root,p,b)
        if before_b["id"]!=after_b["id"] or before_b["audio_sha256"]!=after_b["audio_sha256"]:
            fail("DEMO_REGRESSION","B changed unexpectedly")
        return {"stale_before_import":stale["counts"],"new_A_take":take["id"],"B_reused":True,
                "next":"Run redub.py render <project>; both versions will remain available"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("project");args=parser.parse_args()
    print(json.dumps(revise(args.project),ensure_ascii=False,indent=2))
