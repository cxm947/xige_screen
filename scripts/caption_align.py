#!/usr/bin/env python3
"""Propose caption times from actual timed ASR words, never character-rate timing.

Input: {chunks:[display strings], words:[{word,start,end}], duration:seconds,
        aliases:{displayTerm:spokenTerm}}. Output proposals require review.
Low text coverage returns no captions instead of fabricating precise timestamps.
"""
import argparse
import difflib
import json
import math
import re
from redub_core import read_json,atomic_json,fail,RedubError


def normalized_chars(text,aliases=None,normalizer=None):
    text=text.casefold()
    for a,b in sorted((aliases or {}).items(),key=lambda item:len(item[0]),reverse=True):
        text=text.replace(a.casefold(),b.casefold())
    chars=[c for c in text if c.isalnum()]
    return [normalizer(c) if normalizer else c for c in chars]


def align(chunks,words,duration,aliases=None,normalizer=None,min_coverage=.85):
    if not chunks or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
        fail("ALIGNMENT_INPUT","Need nonempty chunks and positive duration")
    target=[];ranges=[];observed=[];times=[]
    for chunk in chunks:
        chars=normalized_chars(chunk,aliases,normalizer)
        if not chars:fail("ALIGNMENT_INPUT","Empty caption chunk")
        ranges.append((len(target),len(target)+len(chars)));target.extend(chars)
    previous_start=-1
    for word in words:
        a,b=word.get("start"),word.get("end")
        if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isfinite(a+b) or not 0<=a<=b<=duration+.10 or a<previous_start:
            fail("ALIGNMENT_INPUT","ASR word times must be ordered and inside the utterance")
        previous_start=a
        if a==b:continue
        chars=normalized_chars(word.get("word",""),aliases,normalizer)
        observed.extend(chars)
        # Every character keeps its WHOLE word's timestamps. No proportional split.
        times.extend([(a,min(b,duration))]*len(chars))
    mapping={}
    for block in difflib.SequenceMatcher(None,target,observed,autojunk=False).get_matching_blocks():
        for offset in range(block.size):mapping[block.a+offset]=block.b+offset
    coverage=len(mapping)/max(1,len(target))
    if coverage<min_coverage:
        return {"coverage":coverage,"captions":[],"status":"needs_manual_alignment","reason":"ASR text coverage too low"}
    captions=[]
    for chunk,(start,end) in zip(chunks,ranges):
        matched=[mapping[i] for i in range(start,end) if i in mapping]
        if not matched:
            return {"coverage":coverage,"captions":[],"status":"needs_manual_alignment","reason":"Caption has no matched word"}
        a,b=times[matched[0]][0],times[matched[-1]][1]
        if b<=a or (captions and a<captions[-1]["end"]-1e-7):
            return {"coverage":coverage,"captions":[],"status":"needs_manual_alignment","reason":"Caption boundary splits an ASR word; merge chunks or manually verify"}
        captions.append({"start":round(a,4),"end":round(b,4),"text":chunk})
    return {"coverage":coverage,"captions":captions,"status":"proposed_needs_review",
            "method":"matched whole-word timestamps; no proportional timing"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("input");parser.add_argument("output")
    args=parser.parse_args()
    try:
        data=read_json(args.input);result=align(data["chunks"],data["words"],data["duration"],data.get("aliases"))
        atomic_json(args.output,result);print(json.dumps(result,ensure_ascii=False,indent=2))
    except RedubError as exc:
        print(json.dumps({"error":exc.code,"message":str(exc)},ensure_ascii=False));raise SystemExit(2)
