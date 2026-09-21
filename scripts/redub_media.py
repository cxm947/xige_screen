"""FFmpeg compositor and final-container checks. Optional dependency: numpy.

Every subprocess uses an argv list. Never interpolates a URL/text into a shell.
"""
from __future__ import annotations
import json
import math
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from redub_core import (VERSION, atomic_json, asset_path, digest, fail, map_interval,
                        require_valid, review_current, selected_receipt, sha256)


def np_module():
    try:
        import numpy as np
        return np
    except ImportError:
        fail("MISSING_DEPENDENCY", "Media commands need numpy; install requirements-media.txt in a separate environment")


def ffmpeg_path(explicit=None):
    configured=explicit or os.environ.get("REDUB_FFMPEG")
    if configured:
        resolved=shutil.which(configured) or (str(Path(configured).resolve()) if Path(configured).is_file() else None)
        if not resolved:
            fail("FFMPEG_MISSING",f"Configured FFmpeg not found: {configured}")
        return resolved
    found=shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError,RuntimeError):
        fail("FFMPEG_MISSING","Install FFmpeg or imageio-ffmpeg, or set REDUB_FFMPEG")


def run(args, cwd=None, input_data=None):
    result=subprocess.run([str(x) for x in args],cwd=cwd,input=input_data,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        fail("MEDIA_COMMAND_FAILED",result.stderr.decode("utf-8",errors="replace")[-5000:])
    return result


def ff_version(ff):
    return run([ff,"-version"]).stdout.decode("utf-8",errors="replace").splitlines()[0]


def probe(path, ff):
    """ffprobe when present; FFmpeg metadata fallback for bundled FFmpeg-only installs."""
    path=Path(path).resolve()
    fp=Path(ff).with_name("ffprobe.exe" if os.name=="nt" else "ffprobe")
    executable=str(fp) if fp.is_file() else shutil.which("ffprobe")
    if executable:
        data=json.loads(run([executable,"-v","error","-show_format","-show_streams","-of","json",path]).stdout)
        video=next((s for s in data["streams"] if s["codec_type"]=="video"),None)
        audio=next((s for s in data["streams"] if s["codec_type"]=="audio"),None)
        return {"duration":float(data["format"].get("duration",0)),
                "width":video.get("width") if video else None,"height":video.get("height") if video else None,
                "audio":bool(audio),"method":"ffprobe"}
    result=subprocess.run([ff,"-hide_banner","-i",str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    info=result.stderr.decode("utf-8",errors="replace")
    dur=re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)",info)
    video=next((s for s in info.splitlines() if "Video:" in s),"")
    dims=re.search(r"\b(\d{2,5})x(\d{2,5})\b",video)
    if not dur:
        fail("PROBE_FAILED",info[-2000:])
    return {"duration":int(dur[1])*3600+int(dur[2])*60+float(dur[3]),
            "width":int(dims[1]) if dims else None,"height":int(dims[2]) if dims else None,
            "audio":"Audio:" in info,"method":"ffmpeg_header"}


def decode(path,rate,ff):
    np=np_module()
    raw=run([ff,"-v","error","-i",Path(path).resolve(),"-vn","-ac","1","-ar",rate,"-f","f32le","-"]).stdout
    x=np.frombuffer(raw,dtype="<f4").copy()
    if not len(x) or not np.isfinite(x).all():
        fail("INVALID_AUDIO",str(path))
    return x


def wav_write(path,x,rate):
    np=np_module()
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),"wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(rate)
        handle.writeframes((np.clip(x,-1,1)*32767).round().astype("<i2").tobytes())


def audio_metrics(x,rate):
    np=np_module()
    step=max(1,round(.01*rate))
    frames=[float(np.sqrt(np.mean(x[i:i+step]**2))) for i in range(0,len(x),step)]
    active=[i for i,v in enumerate(frames) if v>.004]
    return {"duration":len(x)/rate,"rms":float(np.sqrt(np.mean(x*x))),"peak":float(np.max(abs(x))),
            "clipped_fraction":float(np.mean(abs(x)>=.9999)),
            "active_start":active[0]*.01 if active else None,
            "active_end":min(len(x)/rate,(active[-1]+1)*.01) if active else None}


def correlation(a,b):
    np=np_module()
    n=min(len(a),len(b))
    if n<2 or float(np.std(a[:n]))<1e-8 or float(np.std(b[:n]))<1e-8:
        return None
    return float(np.corrcoef(a[:n],b[:n])[0,1])


def srt_time(t):
    ms=round(max(0,t)*1000)
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"


def ass_time(t):
    cs=round(max(0,t)*100)
    return f"{cs//360000:01d}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}"


def ass_escape(text):
    return text.replace("\\","＼").replace("{","｛").replace("}","｝").replace("\n",r"\N")


def write_captions(p,folder,width,height,duration):
    lines=[]; events=[]; index=0
    font=p["render"].get("font","Arial").replace(",","").replace("\n","")
    size=max(20,round(height*.047))
    margin=max(12,round(height*.03))
    head=(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n"
          "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
          f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00111111,&H60000000,0,0,0,0,100,100,0,0,1,2,0,2,30,30,{margin},1\n"
          f"Style: Label,{font},{max(12,size//2)},&H00FFFFFF,&H00FFFFFF,&H00111111,&H60000000,0,0,0,0,100,100,0,0,1,1,0,7,16,16,12,1\n"
          "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    label=p["render"].get("label","")
    if label:
        events.append(f"Dialogue: 1,0:00:00.00,{ass_time(duration)},Label,,0,0,0,,{ass_escape(label)}")
    for t in p["turns"]:
        start,end=map_interval(p["scene"]["keep"],t["start"],t["end"])
        captions=t.get("captions") or [{"start":0,"end":end-start,"text":t["text"]}]
        for c in captions:
            index+=1
            a,b=start+c["start"],start+c["end"]
            lines.append(f"{index}\n{srt_time(a)} --> {srt_time(b)}\n{c['text']}\n")
            events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{ass_escape(c['text'])}")
    (folder/"subtitles.srt").write_text("\n".join(lines),encoding="utf-8-sig")
    (folder/"subtitles.ass").write_text(head+"\n".join(events),encoding="utf-8-sig")


def compose(root,p,ff):
    np=np_module(); rate=p["settings"]["sample_rate"]
    source=decode(asset_path(root,p,p["source"]["asset"]),rate,ff)
    # AAC may decode with a final codec frame beyond the declared video timeline.
    # Use the measured source timeline, not codec padding, to size background stems.
    expected_n=round(p["source"]["duration"]*rate)
    if len(source)<expected_n-round(.08*rate):
        fail("SOURCE_AUDIO_SHORT","Source audio ends materially before the declared video timeline")
    source=np.pad(source,(0,max(0,expected_n-len(source))))[:expected_n]
    bed=p["mix"].get("bed_asset")
    if bed:
        mix=decode(asset_path(root,p,bed),rate,ff)
        if abs(len(mix)-len(source))>round(.025*rate):
            fail("BED_DURATION","Background stem must use the full source timeline")
        mix=np.pad(mix,(0,max(0,len(source)-len(mix))))[:len(source)]
    else:
        mix=source.copy()
        generated=[t for t in p["turns"] if t["action"]=="generate"]
        if generated:
            room_id=p["mix"].get("roomtone_asset")
            if not room_id:
                fail("BACKGROUND_REQUIRED","Supply a source-length dialogue-free bed or a clean room-tone asset and reviewed replacement regions")
            room=decode(asset_path(root,p,room_id),rate,ff)
            if len(room)<rate*.1:
                fail("ROOMTONE_TOO_SHORT","Need at least 100 ms of clean ambience")
            tone=np.resize(room,len(source))
            regions=sorted(p["mix"].get("replace_regions",[]),key=lambda r:r["start"])
            for t in generated:
                if not any(r["start"]<=t["start"]+1e-7 and r["end"]>=t["end"]-1e-7 for r in regions):
                    fail("UNCLEARED_DIALOGUE",f"{t['id']}: replacement region does not cover target turn")
            for r in regions:
                a,b=round(r["start"]*rate),round(r["end"]*rate)
                mix[a:b]=tone[a:b]
    audits=[]
    for t in p["turns"]:
        a,b=round(t["start"]*rate),round(t["end"]*rate); n=b-a
        if b>len(mix):
            fail("SOURCE_TOO_SHORT",t["id"])
        if t["action"]=="retain":
            x=source[a:b].copy()
            receipt=None
        else:
            receipt=selected_receipt(root,p,t)
            x=decode(asset_path(root,p,receipt["asset"]),rate,ff)
            metrics=audio_metrics(x,rate)
            if metrics["rms"]<p["settings"]["min_turn_rms"]:
                fail("SILENT_TAKE",t["id"])
            if len(x)>n:
                tail=x[n:]
                if float(np.sqrt(np.mean(tail*tail)))>.002 or float(np.max(abs(tail)))>.015:
                    fail("VOICED_OVERRUN",f"{t['id']}: generated speech exceeds slot by {(len(x)-n)/rate:.3f}s; regenerate or revise the whole utterance")
                x=x[:n]
            x=np.pad(x,(0,max(0,n-len(x))))
            x*=10**(t.get("gain_db",0)/20)
            fade=min(round(p["settings"].get("fade_ms",6)*rate/1000),n//2)
            if fade:
                x[:fade]*=np.linspace(0,1,fade); x[-fade:]*=np.linspace(1,0,fade)
            x+=mix[a:b]
        mix[a:b]=x
        audits.append({"id":t["id"],"speaker":t["speaker"],"text":t["text"],
                       "take":receipt["id"] if receipt else "original",
                       "audio_sha256":receipt["audio_sha256"] if receipt else p["assets"][p["source"]["asset"]]["sha256"],
                       "final_interval":map_interval(p["scene"]["keep"],t["start"],t["end"]),
                       "metrics":audio_metrics(x,rate)})
    for r in p["mix"].get("preserve_regions",[]):
        a,b=round(r["start"]*rate),round(r["end"]*rate)
        mix[a:b]=source[a:b]
    final=np.concatenate([mix[round(k["start"]*rate):round(k["end"]*rate)] for k in p["scene"]["keep"]])
    if np.max(abs(final))>1:
        fail("MIX_CLIPPING","Pre-encode mix exceeds full scale; lower explicit per-turn gains or the background stem")
    return final,rate,audits


def qc_final(root,p,path,master,rate,ff):
    np=np_module()
    run([ff,"-v","error","-i",path,"-f","null","-"])
    decoded=decode(path,rate,ff)
    if len(decoded)<len(master)-round(.03*rate):
        fail("ENCODED_TAIL_LOST",f"Decoded audio is {(len(master)-len(decoded))/rate:.3f}s short")
    checks=[]
    for t in p["turns"]:
        a,b=map_interval(p["scene"]["keep"],t["start"],t["end"])
        aa,bb=round(a*rate),round(b*rate)
        x=decoded[aa:bb]; expected=master[aa:bb]
        met=audio_metrics(x,rate)
        corr=correlation(expected,x)
        if met["rms"]<p["settings"]["min_turn_rms"]:
            fail("EMPTY_FINAL_TURN",t["id"])
        if corr is None or corr<.90:
            fail("FINAL_WAVEFORM_MISMATCH",f"{t['id']}: encoded audio differs from selected mix ({corr})")
        checks.append({"id":t["id"],"speaker":t["speaker"],"rms":met["rms"],"master_correlation":corr})
    return {"decoded_duration":len(decoded)/rate,"master_duration":len(master)/rate,
            "whole_container_decode":"passed","turn_checks":checks,
            "limitation":"Energy and waveform checks establish audibility/assembly, not lexical accuracy, actor identity or acting quality. Listen to the source/A/B audition and record the decision separately."}


def render(root,p,ff,allow_unreviewed=False):
    require_valid(root,p,"render")
    if not allow_unreviewed and not all(review_current(p,s) for s in ("source","script")):
        fail("REVIEW_STALE","Source or script review missing/stale. Record existing user feedback or an explicitly identified agent review; never invent user approval.")
    takes=[selected_receipt(root,p,t) for t in p["turns"] if t["action"]=="generate"]
    content={k:v for k,v in p.items() if k!="reviews"}
    key=digest({"project":content,"takes":takes,"renderer":VERSION,"ffmpeg":ff_version(ff),"preview":allow_unreviewed})[:24]
    folder=Path(root).resolve()/"renders"/key
    folder.mkdir(parents=True,exist_ok=True)
    dest=folder/"video.mp4"; receipt_path=folder/"receipt.json"
    if dest.exists() and receipt_path.exists():
        receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("sha256")==sha256(dest):
            return {**receipt,"cache_hit":True}
        fail("RENDER_CORRUPT",str(dest))
    master,rate,audits=compose(root,p,ff)
    duration=len(master)/rate
    wav_write(folder/"master.wav",master,rate)
    # Compare final AAC with the quantized WAV actually passed to the encoder.
    master=decode(folder/"master.wav",rate,ff)
    src=asset_path(root,p,p["source"]["asset"])
    meta=probe(src,ff)
    if not meta["width"] or not meta["height"]:
        fail("VIDEO_REQUIRED",str(src))
    width,height=meta["width"],meta["height"]
    write_captions(p,folder,width,height,duration)
    filters=[]; n=len(p["scene"]["keep"])
    if n>1:
        filters.append("[0:v]split="+str(n)+"".join(f"[s{i}]" for i in range(n)))
    for i,k in enumerate(p["scene"]["keep"]):
        vin=f"[s{i}]" if n>1 else "[0:v]"
        filters.append(f"{vin}trim=start={k['start']:.9f}:end={k['end']:.9f},setpts=PTS-STARTPTS[c{i}]")
    filters.append("".join(f"[c{i}]" for i in range(n))+f"concat=n={n}:v=1:a=0,tpad=stop_mode=clone:stop_duration=0.15[cut]")
    vf="[cut]scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if p["render"].get("burn_subtitles",True):
        fraction=p["render"].get("subtitle_band_fraction",.13)
        if not isinstance(fraction,(float,int)) or not 0<=fraction<.5:
            fail("SUBTITLE_BAND","subtitle_band_fraction must be in [0, 0.5)")
        if fraction:
            vf+=f",drawbox=x=0:y=ih*{1-fraction:.6f}:w=iw:h=ih*{fraction:.6f}:color=black:t=fill"
        vf+=",ass=subtitles.ass"
    vf+="[video]";filters.append(vf)
    lufs=p["settings"].get("lufs",-17); peak=p["settings"].get("true_peak",-1.5)
    if not -70<=lufs<=-5 or not -9<=peak<=0:
        fail("LOUDNESS_RANGE","Invalid LUFS/true-peak setting")
    filters.append(f"[1:a]apad=pad_dur=0.3,loudnorm=I={lufs}:TP={peak}:LRA=10,aresample=48000,asetpts=N/SR/TB[audio]")
    tmp=folder/"video.pending.mp4"
    atomic_json(folder/"render_plan.json",{"render_id":key,"status":"running","turns":audits})
    run([ff,"-v","error","-y","-i",src,"-i",folder/"master.wav","-filter_complex",";".join(filters),
         "-map","[video]","-map","[audio]","-c:v","libx264","-preset","fast","-crf","19",
         "-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-b:a","192k","-t",f"{duration:.9f}",
         "-movflags","+faststart",tmp],cwd=folder)
    qc=qc_final(root,p,tmp,master,rate,ff)
    os.replace(tmp,dest)
    receipt={"render_id":key,"version":VERSION,"path":str(dest),"sha256":sha256(dest),
             "status":"verified","preview_only":allow_unreviewed,"qc":qc,"turns":audits,
             "reviews":p["reviews"],"ffmpeg":ff_version(ff),"cache_hit":False}
    atomic_json(receipt_path,receipt)
    return receipt
