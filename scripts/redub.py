#!/usr/bin/env python3
"""Scene Redub CLI. Run from any cwd: python /path/to/skill/scripts/redub.py --help."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from redub_core import (VERSION, RedubError, atomic_json, fail, import_asset, init_project,
                        load_project, project_status, read_json, register_take, require_valid,
                        review, selected_receipt, turn_by_id, validate, writer_lock, digest)


def output(value):
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


def parser():
    p=argparse.ArgumentParser(description="Portable scene-redub ledger, take cache, compositor and checks")
    p.add_argument("--version",action="version",version=VERSION)
    p.add_argument("--ffmpeg",help="FFmpeg executable; otherwise REDUB_FFMPEG, PATH, then imageio-ffmpeg")
    sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("init",help="Create an empty resumable project from URL and topic")
    s.add_argument("project");s.add_argument("--url",required=True);s.add_argument("--topic",required=True)
    sub.add_parser("doctor",help="Read-only environment preflight; never installs/downloads models")
    s=sub.add_parser("inspect-url",help="Read metadata with optional yt-dlp; no media download")
    s.add_argument("url")
    s=sub.add_parser("fetch",help="Download one explicitly selected source URL and import it into project")
    s.add_argument("project");s.add_argument("--url",required=True)
    s=sub.add_parser("asset",help="Copy a local asset into the content-addressed project store")
    s.add_argument("project");s.add_argument("file");s.add_argument("--kind",choices=["video","reference","bed","roomtone","other"],required=True)
    s.add_argument("--provenance",required=True)
    s=sub.add_parser("probe",help="Inspect local audio/video metadata")
    s.add_argument("file")
    s=sub.add_parser("validate",help="Validate structure, cast, timing, references and asset integrity")
    s.add_argument("project");s.add_argument("--stage",choices=["draft","source","script","generate","render"],default="draft")
    s=sub.add_parser("status",help="Show selected takes, stale inputs, review state and writer lock")
    s.add_argument("project")
    s=sub.add_parser("review",help="Record an actual completed review; does not create approval")
    s.add_argument("project");s.add_argument("--stage",choices=["source","script","pilot"],required=True)
    s.add_argument("--by",dest="reviewer",choices=["user","agent"],required=True)
    s.add_argument("--note",required=True);s.add_argument("--evidence",required=True)
    s=sub.add_parser("import-take",help="Register a complete generated/recorded utterance")
    s.add_argument("project");s.add_argument("--turn",required=True);s.add_argument("--audio",required=True)
    s.add_argument("--backend",required=True,help="JSON with actual model/provider/version/settings, or manual recording provenance")
    s.add_argument("--note",required=True)
    s=sub.add_parser("select",help="Choose an existing take without changing any other turn")
    s.add_argument("project");s.add_argument("--turn",required=True);s.add_argument("--take",required=True)
    s=sub.add_parser("render",help="Build immutable MP4/SRT and verify final encoded audio")
    s.add_argument("project");s.add_argument("--preview",action="store_true",help="Render a clearly recorded preview before editorial review; structural checks still apply")
    s=sub.add_parser("report",help="Export a readable cast, dialogue and readiness report")
    s.add_argument("project")
    return p


def yt_metadata(url):
    if not url.startswith(("https://","http://")):
        fail("INVALID_URL","inspect-url accepts HTTP(S); use asset for local files")
    if importlib.util.find_spec("yt_dlp") is None:
        fail("YT_DLP_MISSING","Install yt-dlp in the CLI environment, or use an available browser/tool to inspect and acquire the source")
    result=subprocess.run([sys.executable,"-m","yt_dlp","--ignore-config","--no-playlist","--skip-download","--dump-single-json","--",url],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        fail("SOURCE_UNAVAILABLE",result.stderr.decode("utf-8",errors="replace")[-2500:])
    data=json.loads(result.stdout)
    return {k:data.get(k) for k in ("id","title","duration","width","height","webpage_url","uploader","description","chapters")}


def main(argv=None):
    args=parser().parse_args(argv)
    if args.command=="init":
        p=init_project(args.project,args.url,args.topic)
        return {"project":str(Path(args.project).resolve()),"project_id":p["project_id"],"next":"Inspect source candidates; edit project.json using references/project-contract.md"}
    if args.command=="doctor":
        from redub_media import ffmpeg_path,ff_version
        packages={name:importlib.util.find_spec(name) is not None for name in ("numpy","imageio_ffmpeg","yt_dlp")}
        try:
            ff=ffmpeg_path(args.ffmpeg); ff_info=ff_version(ff)
            filters=subprocess.run([ff,"-hide_banner","-filters"],capture_output=True,text=True).stdout
            required={s:bool(__import__('re').search(r"\s"+s+r"\s",filters)) for s in ("ass","loudnorm","aresample","asetpts")}
        except RedubError as exc:
            ff_info=str(exc);required={}
        return {"version":VERSION,"python":sys.version.split()[0],"packages":packages,"ffmpeg":ff_info,
                "required_filters":required,"voice_backend":"optional external runtime; no GPU/model requirement for project editing"}
    if args.command=="inspect-url":
        return yt_metadata(args.url)
    if args.command=="probe":
        from redub_media import probe,ffmpeg_path
        return probe(args.file,ffmpeg_path(args.ffmpeg))
    root=Path(args.project).resolve();p=load_project(root)
    if args.command=="validate":
        report=validate(root,p,args.stage)
        output(report)
        return 2 if report["errors"] else 0
    if args.command=="status":
        return project_status(root,p)
    if args.command=="report":
        status=project_status(root,p)
        lines=["# Scene Redub project report","",f"Topic: {p['request']['topic']}","",
               f"Ready {status['counts']['ready']}; missing {status['counts']['missing']}; stale {status['counts']['stale']}; original {status['counts']['retained']}.","",
               "| Source time | Speaker | Dialogue | Take |","|---|---|---|---|"]
        for t in p["turns"]:
            txt=t["text"].replace("|","／").replace("\n"," ")
            lines.append(f"| {t['start']:.3f}–{t['end']:.3f} | {t['speaker']} | {txt} | {t.get('selected_take') or t['action']} |")
        target=root/"reports"/"status.md";target.parent.mkdir(exist_ok=True)
        target.write_text("\n".join(lines),encoding="utf-8")
        return {"report":str(target),"status":status}
    with writer_lock(root):
        # Reload after taking the single-writer lock.
        p=load_project(root)
        if args.command=="asset":
            aid=import_asset(root,p,args.file,args.kind,args.provenance)
            atomic_json(root/"project.json",p)
            return {"asset_id":aid,"asset":p["assets"][aid]}
        if args.command=="fetch":
            from redub_media import ffmpeg_path,probe
            metadata=yt_metadata(args.url);ff=ffmpeg_path(args.ffmpeg)
            folder=root/"work"/"download"/digest(args.url)[:16];folder.mkdir(parents=True,exist_ok=True)
            result=subprocess.run([sys.executable,"-m","yt_dlp","--ignore-config","--no-playlist","--no-progress",
                                   "--ffmpeg-location",ff,"-f","bv*[height<=1080]+ba/b[height<=1080]","--merge-output-format","mp4",
                                   "-o",str(folder/"source.%(ext)s"),"--print","after_move:filepath","--",args.url],capture_output=True)
            if result.returncode:
                fail("SOURCE_UNAVAILABLE",result.stderr.decode("utf-8",errors="replace")[-2500:])
            paths=[Path(s) for s in result.stdout.decode("utf-8",errors="replace").splitlines() if s.strip()]
            path=next((s for s in reversed(paths) if s.is_file()),None)
            if path is None:
                fail("DOWNLOAD_PATH","Downloader did not return a local media path")
            aid=import_asset(root,p,path,"video",args.url)
            p["source_candidates"].append({"asset":aid,"metadata":metadata,"measured":probe(path,ff)})
            atomic_json(root/"project.json",p)
            return {"asset_id":aid,"metadata":metadata,"next":"Compare content boundaries; this does not automatically declare the scene complete"}
        if args.command=="review":
            review(root,p,args.stage,args.reviewer,args.note,args.evidence)
            return p["reviews"][args.stage]
        if args.command=="import-take":
            from redub_media import audio_metrics,decode,ffmpeg_path
            require_valid(root,p,"generate")
            backend=read_json(args.backend)
            if not isinstance(backend,dict) or not backend.get("name") or not backend.get("version"):
                fail("BACKEND_RECEIPT","Backend JSON must identify actual name and version")
            x=decode(args.audio,p["settings"]["sample_rate"],ffmpeg_path(args.ffmpeg))
            met=audio_metrics(x,p["settings"]["sample_rate"])
            if met["rms"]<p["settings"]["min_turn_rms"]:
                fail("SILENT_TAKE",args.turn)
            return register_take(root,p,args.turn,args.audio,backend,met,args.note)
        if args.command=="select":
            t=turn_by_id(p,args.turn);t["selected_take"]=args.take
            receipt=selected_receipt(root,p,t)
            atomic_json(root/"project.json",p)
            return {"turn":args.turn,"take":receipt["id"]}
        if args.command=="render":
            from redub_media import ffmpeg_path,render
            return render(root,p,ffmpeg_path(args.ffmpeg),allow_unreviewed=args.preview)
    fail("COMMAND",args.command)


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result=main()
        if isinstance(result,int):
            raise SystemExit(result)
        output(result)
    except RedubError as exc:
        output({"error":exc.code,"message":str(exc)})
        raise SystemExit(2)
    except (OSError,KeyError,TypeError,ValueError) as exc:
        output({"error":"INVALID_INPUT","message":str(exc)})
        raise SystemExit(2)
