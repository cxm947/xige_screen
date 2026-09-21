"""Portable project model, immutable inputs, review receipts and take cache.

Python 3.10+. No model, network, or media dependencies in this module.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import socket
import time
import uuid
from pathlib import Path

VERSION = "0.2.0"
SCHEMA_VERSION = 1
STAGES = ("source", "script", "pilot")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class RedubError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def fail(code, message):
    raise RedubError(code, message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        fail("INVALID_JSON", f"{path}: {exc}")


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or Path(relative).is_absolute():
        fail("UNSAFE_PATH", f"Project paths must stay relative and inside project: {relative}")
    return path


@contextlib.contextmanager
def writer_lock(root):
    """A failed/live writer never gets silently superseded; release only our own lock."""
    path = Path(root) / ".redub.lock"
    token = uuid.uuid4().hex
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "host": socket.gethostname(), "token": token,
                       "started_at": time.time()}, handle)
    except FileExistsError:
        fail("PROJECT_LOCKED", f"Another writer or interrupted run owns {path}. Inspect its PID/log before removing a stale lock; do not start duplicate GPU jobs.")
    try:
        yield
    finally:
        if path.exists() and read_json(path).get("token") == token:
            path.unlink()


def init_project(root, url, topic):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with writer_lock(root):
        if (root / "project.json").exists():
            fail("ALREADY_EXISTS", f"Project already exists: {root}")
        if not topic.strip() or not url.strip():
            fail("MISSING_REQUEST", "Both URL (or file reference) and topic are required")
        p = {"schema_version": SCHEMA_VERSION, "project_id": uuid.uuid4().hex,
             "request": {"url": url, "topic": topic}, "assets": {}, "source_candidates": [],
             "source": {"asset": None, "duration": None},
             "scene": {"keep": [], "evidence": {"opening": "", "ending": "", "completeness": ""}},
             "speakers": {}, "turns": [], "claims": [], "reviews": {},
             "settings": {"sample_rate": 24000, "fade_ms": 6, "lufs": -17,
                          "true_peak": -1.5, "min_turn_rms": 0.0015},
             "mix": {"bed_asset": None, "roomtone_asset": None,
                     "replace_regions": [], "preserve_regions": []},
             "render": {"subtitle_band_fraction": 0.13, "burn_subtitles": True,
                        "label": "AI 二创 · 改编对白", "font": "Arial"}}
        atomic_json(root / "project.json", p)
    return p


def load_project(root):
    p = read_json(Path(root) / "project.json")
    if not isinstance(p, dict) or p.get("schema_version") != SCHEMA_VERSION:
        fail("SCHEMA_VERSION", f"Expected project schema {SCHEMA_VERSION}; do not silently migrate")
    return p


def import_asset(root, p, filename, kind, provenance):
    path = Path(filename).resolve()
    if not path.is_file():
        fail("MISSING_ASSET", str(path))
    h = sha256(path)
    asset_id = "asset_" + h[:24]
    ext = path.suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext):
        ext = ".bin"
    relative = "assets/" + h + ext
    target = inside(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) != h:
        fail("ASSET_CORRUPT", str(target))
    if not target.exists():
        temp = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(path, temp)
        if sha256(temp) != h:
            temp.unlink(missing_ok=True)
            fail("ASSET_CHANGED", "Source changed while copying")
        os.replace(temp, target)
    old = p["assets"].get(asset_id)
    if old and old["sha256"] != h:
        fail("HASH_COLLISION", asset_id)
    p["assets"][asset_id] = old or {"path": relative, "sha256": h, "bytes": target.stat().st_size,
                                        "kind": kind, "provenance": provenance}
    return asset_id


def asset_path(root, p, asset_id, verify=True):
    if asset_id not in p["assets"]:
        fail("MISSING_ASSET", f"Unknown asset: {asset_id}")
    item = p["assets"][asset_id]
    path = inside(root, item["path"])
    if not path.is_file():
        fail("MISSING_ASSET", str(path))
    if verify and sha256(path) != item["sha256"]:
        fail("ASSET_CORRUPT", f"Asset content changed: {asset_id}")
    return path


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def map_interval(keep, start, end):
    offset = 0.0
    for segment in keep:
        a, b = segment["start"], segment["end"]
        if a - 1e-7 <= start < end <= b + 1e-7:
            return offset + start - a, offset + end - a
        offset += b - a
    fail("CUT_CROSSES_TURN", f"Interval {start:g}–{end:g} crosses a cut or is outside selected scene")


def validate(root, p, stage="draft", verify_assets=True):
    """Structural validation plus temporal/editorial invariants; no aesthetic scoring."""
    errors, warnings = [], []
    def error(code, message):
        errors.append({"code": code, "message": message})
    required = {"request", "source", "scene", "speakers", "turns", "assets", "claims", "reviews", "settings", "mix", "render"}
    if not required.issubset(p):
        return {"errors": [{"code": "SCHEMA", "message": "Missing fields: " + ", ".join(sorted(required - p.keys()))}], "warnings": []}
    if verify_assets:
        for aid in p["assets"]:
            try:
                asset_path(root, p, aid)
            except (RedubError, KeyError, TypeError) as exc:
                error(getattr(exc, "code", "SCHEMA"), str(exc))
    duration = p["source"].get("duration")
    keep = p["scene"].get("keep", [])
    if stage != "draft":
        if p["source"].get("asset") not in p["assets"] or not number(duration) or duration <= 0:
            error("SOURCE_REQUIRED", "Set a media asset and measured positive duration")
        if not keep:
            error("SCENE_REQUIRED", "Select source-time keep intervals")
        for key in ("opening", "ending", "completeness"):
            if not p["scene"].get("evidence", {}).get(key):
                error("SCENE_EVIDENCE", f"Missing boundary/completeness evidence: {key}")
    previous = -1.0
    for segment in keep:
        a, b = segment.get("start"), segment.get("end")
        if not number(a) or not number(b) or a < 0 or a >= b or a < previous or (number(duration) and b > duration + .02):
            error("INVALID_EDIT", f"Keep intervals must be ordered, disjoint and inside source: {segment}")
            return {"errors": errors, "warnings": warnings}
        previous = b
    ids, last_end = set(), -1.0
    claim_ids = {c.get("id") for c in p["claims"]}
    if len(claim_ids)!=len(p["claims"]) or None in claim_ids:
        error("CLAIM_ID","Claim IDs must be present and unique")
    for c in p["claims"]:
        if c.get("status") not in ("verified", "allegation", "rumor", "fiction"):
            error("CLAIM_STATUS", f"Claim {c.get('id')} needs an explicit evidence category")
        if c.get("status") in ("verified", "allegation") and not c.get("source_url"):
            error("CLAIM_SOURCE", f"Claim {c.get('id')} lacks a source")
    for t in p["turns"]:
        uid = t.get("id", "")
        if not isinstance(uid, str) or not IDENTIFIER.fullmatch(uid) or uid in ids:
            error("TURN_ID", f"Invalid or duplicate immutable turn ID: {uid}")
        ids.add(uid)
        sp = t.get("speaker")
        if sp not in p["speakers"]:
            error("UNKNOWN_SPEAKER", f"{uid}: {sp}")
        if t.get("action") not in ("generate", "retain"):
            error("TURN_ACTION", f"{uid}: action must be generate or retain")
        if not isinstance(t.get("text"), str) or not t["text"].strip():
            error("EMPTY_TEXT", uid)
        if t.get("action")=="retain":
            normalized=lambda v:"".join(c for c in str(v).casefold() if c.isalnum())
            if not t.get("source_text") or normalized(t.get("text"))!=normalized(t["source_text"]):
                error("RETAINED_TEXT_CHANGED",f"{uid}: retained audio must use the original words; changed dialogue needs a new take")
        if not number(t.get("gain_db",0)) or not -120<=t.get("gain_db",0)<=120:
            error("GAIN_RANGE",f"{uid}: gain_db must be a finite number within ±120")
        a, b = t.get("start"), t.get("end")
        if not number(a) or not number(b) or a < 0 or b <= a:
            error("TURN_TIME", uid)
            continue
        if a < last_end - 1e-7:
            error("OVERLAPPING_TURNS", f"{uid}: overlapping voices need separate stems; v1 mono compositor will not silently overwrite them")
        last_end = b
        if keep:
            try:
                map_interval(keep, a, b)
            except RedubError as exc:
                error(exc.code, f"{uid}: {exc}")
        if stage in ("script", "generate", "render") and not t.get("cast_evidence"):
            error("CAST_EVIDENCE", f"{uid}: note how the audible speaker was identified; reaction shot is insufficient")
        for cid in t.get("claim_ids", []):
            if cid not in claim_ids:
                error("UNKNOWN_CLAIM", f"{uid}: {cid}")
        if t.get("action") == "generate" and stage in ("generate", "render"):
            for aid in (p["speakers"].get(sp, {}).get("timbre_asset"), t.get("performance_asset")):
                if aid not in p["assets"]:
                    error("REFERENCE_REQUIRED", f"{uid}: missing timbre or scene-performance reference")
        captions = t.get("captions", [])
        last_caption_end = -1.0
        for c in captions:
            ca, cb = c.get("start"), c.get("end")
            if not number(ca) or not number(cb) or ca < 0 or ca >= cb or cb > b-a+.001 or ca < last_caption_end or not c.get("text"):
                error("CAPTION_TIME", f"{uid}: caption offsets must be ordered and inside the turn")
            else:
                last_caption_end = cb
        if len(t.get("text", "")) > 24 and not captions:
            warnings.append({"code": "CAPTION_UNALIGNED", "message": f"{uid}: use word-aligned or manually reviewed captions; no character-proportional timing is inferred"})
    for sid, speaker in p["speakers"].items():
        if not IDENTIFIER.fullmatch(sid) or not speaker.get("label"):
            error("SPEAKER_ID", sid)
    for key in ("replace_regions", "preserve_regions"):
        for r in p["mix"].get(key, []):
            a,b=r.get("start"),r.get("end")
            if not number(a) or not number(b) or a<0 or a>=b or (number(duration) and b>duration+.02):
                error("MIX_REGION", f"{key}: {r}")
    for r in p["mix"].get("preserve_regions", []):
        for t in p["turns"]:
            if t.get("action")=="generate" and number(t.get("start")) and number(t.get("end")) and number(r.get("start")) and number(r.get("end")):
                if max(t["start"],r["start"]) < min(t["end"],r["end"]):
                    error("PRESERVE_CONFLICT", f"{t['id']}: generated speech overlaps a locked original cue")
    if stage in ("script", "generate", "render") and not p["turns"]:
        error("TURNS_REQUIRED", "No dialogue turns")
    if p["settings"].get("sample_rate") not in (16000,22050,24000,44100,48000):
        error("SAMPLE_RATE", "Supported rates: 16000, 22050, 24000, 44100, 48000")
    fade=p["settings"].get("fade_ms",6)
    minimum=p["settings"].get("min_turn_rms",.0015)
    if not number(fade) or not 0<=fade<=50:
        error("FADE_RANGE","fade_ms must be between 0 and 50; fades are for seams, not removing phonemes")
    if not number(minimum) or not 0<minimum<1:
        error("RMS_RANGE","min_turn_rms must be between 0 and 1, excluding endpoints")
    return {"errors": errors, "warnings": warnings}


def require_valid(root, p, stage):
    report = validate(root, p, stage)
    if report["errors"]:
        fail("VALIDATION_FAILED", json.dumps(report, ensure_ascii=False))
    return report


def stage_hash(p, stage):
    source = {k:p[k] for k in ("request", "source", "scene")}
    source["source_hash"] = p["assets"].get(p["source"].get("asset"), {}).get("sha256")
    if stage == "source":
        return digest(source)
    script = [{k:t.get(k) for k in ("id","speaker","start","end","source_text","text","tts_text","action","beat","delivery","claim_ids","cast_evidence")} for t in p["turns"]]
    value = {"source":source, "script":script, "claims":p["claims"],
             "speakers":{k:v.get("label") for k,v in p["speakers"].items()}}
    if stage == "script":
        return digest(value)
    value["selected"] = {t["id"]:t.get("selected_take") for t in p["turns"]}
    return digest(value)


def review(root, p, stage, reviewer, note, evidence):
    if stage not in STAGES or reviewer not in ("user", "agent") or not note.strip() or not evidence.strip():
        fail("REVIEW_REQUIRED", "Review needs stage, reviewer, substantive note and evidence (message/test/audition path)")
    require_valid(root, p, "source" if stage=="source" else "script")
    p["reviews"][stage] = {"hash":stage_hash(p,stage), "reviewer":reviewer,
                           "note":note, "evidence":evidence, "recorded_at":time.time()}
    atomic_json(Path(root)/"project.json", p)


def review_current(p, stage):
    r=p["reviews"].get(stage)
    return bool(r and r.get("hash")==stage_hash(p,stage))


def turn_by_id(p, uid):
    for t in p["turns"]:
        if t["id"]==uid:
            return t
    fail("UNKNOWN_TURN", uid)


def take_fingerprint(p, turn, backend):
    refs = [p["speakers"][turn["speaker"]].get("timbre_asset"),turn.get("performance_asset")]
    return digest({"schema":1, "turn":{k:turn.get(k) for k in ("id","speaker","start","end","text","tts_text","delivery")},
                   "references":[p["assets"].get(r,{}).get("sha256") for r in refs],
                   "source_hash":p["assets"].get(p["source"].get("asset"),{}).get("sha256"),
                   "backend":backend})


def register_take(root, p, uid, filename, backend, measurements, note):
    t=turn_by_id(p,uid)
    if t["action"]!="generate":
        fail("RETAINED_TURN", uid)
    key=take_fingerprint(p,t,backend)
    aid=import_asset(root,p,filename,"take",note)
    # Include audio hash: a nondeterministic retry cannot overwrite an earlier chosen take.
    take_id=key[:24]+"_"+p["assets"][aid]["sha256"][:16]
    receipt={"schema_version":1,"id":take_id,"turn":uid,"speaker":t["speaker"],"fingerprint":key,
             "asset":aid,"audio_sha256":p["assets"][aid]["sha256"],"backend":backend,
             "measurements":measurements,"note":note,"created_at":time.time()}
    dest=Path(root)/"takes"/uid/(take_id+".json")
    if dest.exists():
        old=read_json(dest)
        if old["audio_sha256"]!=receipt["audio_sha256"] or old["fingerprint"]!=key:
            fail("TAKE_COLLISION",take_id)
    else:
        atomic_json(dest,receipt)
    atomic_json(Path(root)/"project.json",p)
    return receipt


def selected_receipt(root,p,t):
    tid=t.get("selected_take")
    if not isinstance(tid,str) or not re.fullmatch(r"[a-f0-9]{24}_[a-f0-9]{16}",tid):
        fail("TAKE_REQUIRED",t["id"])
    receipt=read_json(Path(root)/"takes"/t["id"]/(tid+".json"))
    if receipt.get("turn")!=t["id"] or receipt.get("speaker")!=t["speaker"]:
        fail("CAST_MISMATCH",t["id"])
    if receipt.get("fingerprint")!=take_fingerprint(p,t,receipt["backend"]):
        fail("STALE_TAKE",f"{t['id']}: text, timing, cast, reference or backend changed")
    path=asset_path(root,p,receipt["asset"])
    if sha256(path)!=receipt["audio_sha256"]:
        fail("TAKE_CORRUPT",t["id"])
    return receipt


def project_status(root,p):
    counts={"retained":0,"ready":0,"missing":0,"stale":0}
    issues=[]
    for t in p["turns"]:
        if t.get("action")=="retain":
            counts["retained"]+=1
        else:
            try:
                selected_receipt(root,p,t)
                counts["ready"]+=1
            except RedubError as exc:
                counts["missing" if exc.code=="TAKE_REQUIRED" else "stale"]+=1
                issues.append({"turn":t["id"],"code":exc.code,"message":str(exc)})
    return {"version":VERSION,"project_id":p["project_id"],"counts":counts,"issues":issues,
            "reviews":{s:{"current":review_current(p,s),"receipt":p["reviews"].get(s)} for s in STAGES},
            "lock":read_json(Path(root)/".redub.lock") if (Path(root)/".redub.lock").exists() else None}
