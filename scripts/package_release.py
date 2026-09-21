#!/usr/bin/env python3
"""Build a deterministic text-only skill ZIP and SHA-256 manifest; no project media."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from redub_core import VERSION,sha256,atomic_json,fail,RedubError

ROOT_FILES={"SKILL.md","README.md","LICENSE","RELEASE_NOTES.md","requirements-media.txt","requirements-source.txt",".gitignore"}
OPTIONAL_ROOT_FILES={"CONTRIBUTING.md","CHANGELOG.md"}
ROOT_DIRS={"scripts","references","agents","assets","tests",".github"}
EXTS={".py",".md",".txt",".json",".yaml",".yml"}
SENSITIVE=[re.compile(r"(?i)[a-z]:[\\/](?:Users|wechat_config)[\\/]"),
           re.compile(r"(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_\-]{20,}"),
           re.compile(r"wxid_[A-Za-z0-9_]{8,}"),
           re.compile(r"(?i)(?:api_key|access_token)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")]


def package(root,dest):
    root=Path(root).resolve();dest=Path(dest).resolve();files=[]
    candidates=[]
    for current,dirs,names in os.walk(root,followlinks=False):
        # Git metadata belongs to the checkout, never to a distributable skill.
        dirs[:]=[name for name in dirs if name not in (".git","__pycache__")]
        for name in dirs+names:
            path=Path(current)/name
            if path.is_symlink():fail("SYMLINK_IN_RELEASE",path.relative_to(root).as_posix())
        candidates.extend(Path(current)/name for name in names if name!=".git")
    for path in sorted(candidates):
        if path.is_symlink():fail("SYMLINK_IN_RELEASE",path.relative_to(root).as_posix())
        if not path.is_file():continue
        rel=path.relative_to(root)
        if rel.as_posix()=="release_manifest.json":continue
        if "__pycache__" in rel.parts or path.suffix==".pyc":continue
        allowed=(len(rel.parts)==1 and rel.name in ROOT_FILES|OPTIONAL_ROOT_FILES) or (len(rel.parts)>1 and rel.parts[0] in ROOT_DIRS and path.suffix in EXTS)
        if not allowed:fail("UNEXPECTED_RELEASE_FILE",rel.as_posix())
        if path.stat().st_size>1_000_000:fail("RELEASE_FILE_TOO_LARGE",rel.as_posix())
        try:text=path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:fail("NON_UTF8_FILE",rel.as_posix())
        if any(pattern.search(text) for pattern in SENSITIVE):fail("PRIVATE_DATA_PATTERN",rel.as_posix())
        files.append((path,rel.as_posix()))
    missing=ROOT_FILES-{r for _,r in files}
    if missing:fail("RELEASE_INCOMPLETE",", ".join(sorted(missing)))
    manifest={"name":"scene-redub","version":VERSION,"files":[{"path":rel,"sha256":sha256(path),"bytes":path.stat().st_size} for path,rel in files],
              "scan":"Text-only allowlist; known local private-path/token patterns absent. This scan does not establish exhaustive secret detection."}
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():fail("RELEASE_EXISTS",f"Refusing to overwrite release: {dest}")
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path,rel in files:
            info=zipfile.ZipInfo("scene-redub/"+rel,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,path.read_bytes())
        info=zipfile.ZipInfo("scene-redub/release_manifest.json",date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        archive.writestr(info,json.dumps(manifest,ensure_ascii=False,indent=2).encode("utf-8"))
    result={"zip":dest.name,"sha256":sha256(dest),"bytes":dest.stat().st_size,"file_count":len(files)+1}
    atomic_json(dest.with_suffix(".sha256.json"),result)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",default=str(Path(__file__).resolve().parents[1]));p.add_argument("--output",required=True)
    args=p.parse_args()
    try:print(json.dumps(package(args.root,args.output),ensure_ascii=False,indent=2))
    except RedubError as exc:
        print(json.dumps({"error":exc.code,"message":str(exc)},ensure_ascii=False));raise SystemExit(2)
