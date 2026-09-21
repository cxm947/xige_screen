#!/usr/bin/env python3
"""Build a cast ledger and whole-turn references from a reviewed scene plan."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from redub_core import init_project, import_asset, atomic_json, require_valid, RedubError
from redub_media import ffmpeg_path, run, probe


def prepare(project, video, plan_path):
    project, video, plan_path = map(lambda x: Path(x).resolve(), (project, video, plan_path))
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    ff = ffmpeg_path(None)
    meta = probe(video, ff)
    duration = float(plan.get('duration', meta['duration']))
    p = init_project(project, plan.get('url', video.as_uri()), plan['topic'])
    work = project / 'work/references'
    work.mkdir(parents=True, exist_ok=True)
    p['source'] = {'asset': import_asset(project, p, video, 'video', plan.get('url', 'User provided local video')), 'duration': duration}
    p['source_candidates'].append({'asset': p['source']['asset'], 'measured': meta})
    p['scene'] = {'keep': plan.get('keep', [{'start': 0, 'end': duration}]), 'evidence': plan['source_evidence']}
    p['claims'] = plan.get('claims', [])
    p['render'].update(plan.get('render', {}))

    def extract(span, name, kind, provenance):
        a, b = map(float, span)
        if not 0 <= a < b <= duration:
            raise ValueError(f'Invalid reference interval: {name} {a}-{b}')
        dest = work / (name + '.wav')
        run([ff, '-v', 'error', '-y', '-ss', str(a), '-i', video, '-t', str(b-a), '-vn', '-ac', '1',
             '-ar', str(p['settings']['sample_rate']), '-c:a', 'pcm_s16le', dest])
        return import_asset(project, p, dest, kind, provenance)

    if plan.get('bed_file'):
        p['mix']['bed_asset'] = import_asset(project, p, (plan_path.parent / plan['bed_file']).resolve(), 'bed', plan['bed_evidence'])
    elif plan.get('roomtone'):
        p['mix']['roomtone_asset'] = extract(plan['roomtone'], 'roomtone', 'roomtone', plan['bed_evidence'])
        p['mix']['replace_regions'] = plan['replace_regions']
    else:
        raise ValueError('Provide bed_file or a reviewed dialogue-free roomtone interval; the tool will not leave old speech underneath.')
    p['mix']['preserve_regions'] = plan.get('preserve_regions', [])
    for i, (speaker, spec) in enumerate(plan['speakers'].items()):
        rid = extract(spec['reference'], f'speaker-{i}', 'reference', spec['evidence'])
        p['speakers'][speaker] = {'label': spec['label'], 'timbre_asset': rid}
    for i, spec in enumerate(plan['turns']):
        t = dict(spec)
        span = t.pop('performance', [t['start'], t['end']])
        t.setdefault('action', 'generate')
        t.setdefault('tts_text', t['text'])
        t.setdefault('claim_ids', [])
        t.setdefault('captions', [])
        if t['action'] == 'generate':
            t['performance_asset'] = extract(span, f'turn-{i}', 'reference', t['cast_evidence'])
        p['turns'].append(t)
    atomic_json(project / 'project.json', p)
    require_valid(project, p, 'generate')
    return {'project': str(project), 'turns': len(p['turns']), 'next': 'Review source/script, then Run.cmd generate PROJECT --turn ID --select'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('project'); ap.add_argument('--video', required=True); ap.add_argument('--plan', required=True)
    args = ap.parse_args()
    try:
        print(json.dumps(prepare(args.project, args.video, args.plan), ensure_ascii=False, indent=2))
    except (OSError, KeyError, ValueError, RedubError) as exc:
        ap.exit(2, str(exc) + '\n')
