from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_scene import prepare
from redub_core import asset_path, load_project, RedubError
from redub_media import ffmpeg_path, decode
from make_demo import create


class PrepareTests(unittest.TestCase):
    def test_scene_plan_extracts_each_correct_reference_and_clears_dialogue(self):
        try:
            ff = ffmpeg_path(None)
            import numpy as np
        except (RedubError, ImportError) as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = create(base / 'fixture', ff)
            video = asset_path(base / 'fixture', p, p['source']['asset'])
            plan = {'topic': 'Plan import test', 'source_evidence': p['scene']['evidence'],
                    'roomtone': [2.0, 2.2], 'bed_evidence': 'Synthetic low level tone between scripted turns',
                    'replace_regions': [{'start': .2, 'end': 1.2}, {'start': 3.4, 'end': 4.9}],
                    'speakers': {'A': {'label': 'A', 'reference': [.2, 1.2], 'evidence': 'Fixture A interval'},
                                 'B': {'label': 'B', 'reference': [3.4, 4.9], 'evidence': 'Fixture B interval'}},
                    'turns': []}
            for t in p['turns']:
                plan['turns'].append({k: v for k, v in t.items() if k not in ('selected_take', 'performance_asset')})
            file = base / 'plan.json'
            file.write_text(json.dumps(plan), encoding='utf-8')
            out = base / '中文 空格 project'
            prepare(out, video, file)
            actual = load_project(out)
            self.assertEqual([t['speaker'] for t in actual['turns']], ['A', 'B'])
            self.assertEqual(len(actual['mix']['replace_regions']), 2)
            a = decode(asset_path(out, actual, actual['turns'][0]['performance_asset']), 24000, ff)
            b = decode(asset_path(out, actual, actual['turns'][1]['performance_asset']), 24000, ff)
            self.assertAlmostEqual(len(a) / 24000, 1, places=2)
            self.assertAlmostEqual(len(b) / 24000, 1.5, places=2)
            self.assertNotEqual(actual['turns'][0]['performance_asset'], actual['turns'][1]['performance_asset'])
            self.assertNotIn('source', actual['reviews'])


if __name__ == '__main__':
    unittest.main()
