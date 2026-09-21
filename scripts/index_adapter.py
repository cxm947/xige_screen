#!/usr/bin/env python3
"""Optional local IndexTTS 2.5 adapter. Run INSIDE the model's working environment.

No downloads, environment mutation, provider calls or credential handling. Model
license and installation remain upstream responsibilities; see references/backends.md.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from redub_core import (RedubError, atomic_json, asset_path, digest, fail, load_project,
                        read_json, register_take, require_valid, sha256, take_fingerprint,
                        turn_by_id, writer_lock)


def tree_manifest(root,extensions):
    root=Path(root).resolve()
    files=[p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in extensions and "__pycache__" not in p.parts and ".git" not in p.parts]
    if not files:
        fail("BACKEND_FILES",f"No fingerprintable model/source files: {root}")
    return {p.relative_to(root).as_posix():sha256(p) for p in sorted(files)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project");ap.add_argument("--config",required=True)
    ap.add_argument("--turn",action="append",required=True,help="Repeat for a bounded batch of immutable turn IDs")
    ap.add_argument("--seed",type=int,default=117);ap.add_argument("--alpha",type=float,default=1.0)
    ap.add_argument("--duration-factor",type=float,default=1.0)
    ap.add_argument("--select",action="store_true",help="Select generated clips; does not mark them auditioned")
    ap.add_argument("--dry-run",action="store_true",help="Check project/references/config without loading or hashing model weights")
    args=ap.parse_args()
    if not .5<=args.duration_factor<=1.35 or not 0<=args.alpha<=1:
        fail("PARAMETER_RANGE","duration-factor must be .5–1.35; alpha must be 0–1")
    root=Path(args.project).resolve();p=load_project(root);config=read_json(args.config)
    require_valid(root,p,"generate")
    jobs=[turn_by_id(p,uid) for uid in args.turn]
    if len({t["id"] for t in jobs})!=len(jobs):
        fail("DUPLICATE_JOB","A turn was requested twice")
    for t in jobs:
        if t["action"]!="generate":
            fail("RETAINED_TURN",t["id"])
    repo=Path(config["repo"]).expanduser().resolve();models=Path(config["model_dir"]).expanduser().resolve()
    if not (repo/"indextts/infer_v2_5.py").is_file() or not (models/"config.yaml").is_file():
        fail("BACKEND_PATHS","Expected IndexTTS 2.5 source and model config.yaml")
    if args.dry_run:
        print(json.dumps({"jobs":[t["id"] for t in jobs],"whole_utterance":True,"model_loading":False},ensure_ascii=False))
        return
    # Explicit runtime overlays are a local configuration detail, never patched into
    # a global Python installation. Keep this adapter in the repository's own venv.
    runtime=[str(Path(v).expanduser().resolve()) for v in config.get("runtime_paths",[])]
    sys.path[:0]=runtime+[str(repo)]
    os.environ.setdefault("HF_HUB_OFFLINE","1")
    import numpy as np
    import torch
    import soundfile as sf
    import transformers
    from indextts.infer_v2_5 import IndexTTS2
    from redub_media import decode,ffmpeg_path,audio_metrics
    torch.set_num_threads(config.get("cpu_threads",4))
    runtime_versions={"python":sys.version.split()[0],"torch":torch.__version__,"transformers":transformers.__version__}
    for pkg in ("numpy","soundfile","tokenizers","protobuf"):
        try:runtime_versions[pkg]=importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:runtime_versions[pkg]="unavailable"
    print("Fingerprinting model/source files; first run reads model weights once.",flush=True)
    model_manifest=tree_manifest(models,{".yaml",".yml",".json",".safetensors",".pt",".pth",".bin",".model",".tiktoken"})
    code_manifest=tree_manifest(repo/"indextts",{".py",".yaml",".yml",".json"})
    backend={"name":"IndexTTS","version":"2.5","model_manifest_hash":digest(model_manifest),
             "code_manifest_hash":digest(code_manifest),"runtime":runtime_versions,
             "params":{"seed":args.seed,"emo_alpha":args.alpha,"duration_factor":args.duration_factor,
                       "temperature":.8,"top_p":.8,"top_k":30,"lang":config.get("lang","ZH"),
                       "use_bf16":config.get("use_bf16",True),"device":config.get("device","cuda:0")}}
    with writer_lock(root):
        p=load_project(root);require_valid(root,p,"generate")
        pending=[];saved=[]
        for uid in args.turn:
            t=turn_by_id(p,uid);key=take_fingerprint(p,t,backend)
            cached=None
            for path in sorted((root/"takes"/uid).glob("*.json")):
                rec=read_json(path)
                if rec.get("fingerprint")==key:
                    audio=asset_path(root,p,rec["asset"])
                    if sha256(audio)==rec["audio_sha256"]:
                        cached=rec;break
            if cached:
                saved.append(cached)
                if args.select:t["selected_take"]=cached["id"]
                print(f"Verified cache: {uid}",flush=True)
            else:pending.append(t)
        if pending:
            model=IndexTTS2(cfg_path=str(models/"config.yaml"),model_dir=str(models),
                            use_bf16=config.get("use_bf16",True),device=config.get("device","cuda:0"),
                            use_cuda_kernel=False,use_deepspeed=False,use_accel=False,use_qwen_emo=False)
            folder=root/"work"/"index";folder.mkdir(parents=True,exist_ok=True)
            atomic_json(folder/(digest(backend)+".backend.json"),{"backend":backend,"models":model_manifest,"code":code_manifest})
            ff=ffmpeg_path(config.get("ffmpeg"))
            for t in pending:
                random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
                if torch.cuda.is_available():torch.cuda.manual_seed_all(args.seed)
                print(f"Generating complete turn {t['id']}",flush=True)
                timbre=asset_path(root,p,p["speakers"][t["speaker"]]["timbre_asset"])
                performance=asset_path(root,p,t["performance_asset"])
                result=model.infer(spk_audio_prompt=str(timbre),emo_audio_prompt=str(performance),
                                   text=t.get("tts_text") or t["text"],output_path=None,lang=backend["params"]["lang"],
                                   emo_alpha=args.alpha,use_emo_text=False,use_random=False,interval_silence=0,
                                   max_text_tokens_per_segment=180,stream_return=False,
                                   duration_factor=args.duration_factor,temperature=.8,top_p=.8,top_k=30)
                sample_rate,pcm=result
                # Upstream 2.5 returns int16-scale PCM; validate before converting.
                arr=np.asarray(pcm)
                if not np.issubdtype(arr.dtype,np.integer):
                    fail("BACKEND_CONTRACT","Upstream PCM dtype changed; inspect the return contract instead of guessing amplitude")
                x=arr.astype(np.float32).squeeze()/32768.0
                if x.ndim!=1 or not len(x) or not np.isfinite(x).all():
                    fail("BACKEND_CONTRACT","Expected a nonempty mono waveform")
                raw=folder/(t["id"]+".raw.wav");sf.write(raw,x,sample_rate,subtype="FLOAT")
                x=decode(raw,p["settings"]["sample_rate"],ff)
                dest=folder/(t["id"]+".wav");sf.write(dest,x,p["settings"]["sample_rate"],subtype="FLOAT")
                met=audio_metrics(x,p["settings"]["sample_rate"])
                if met["rms"]<p["settings"]["min_turn_rms"]:
                    fail("SILENT_TAKE",t["id"])
                receipt=register_take(root,p,t["id"],dest,backend,met,"Whole utterance generated with same-scene performance reference; audition pending")
                saved.append(receipt)
                if args.select:t["selected_take"]=receipt["id"]
                atomic_json(root/"project.json",p)
                print(f"Saved {t['id']}: {met['duration']:.3f}s (slot {t['end']-t['start']:.3f}s)",flush=True)
                if torch.cuda.is_available():torch.cuda.empty_cache()
        atomic_json(root/"project.json",p)
        print(json.dumps({"takes":[{"turn":r["turn"],"id":r["id"],"metrics":r["measurements"]} for r in saved]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    try:main()
    except RedubError as exc:
        print(json.dumps({"error":exc.code,"message":str(exc)},ensure_ascii=False));raise SystemExit(2)
