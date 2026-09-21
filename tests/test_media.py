import copy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from redub_core import RedubError,load_project,asset_path,atomic_json,import_asset,register_take
from redub_media import *
from make_demo import create


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ff=ffmpeg_path();np_module()
        except RedubError as exc:
            raise unittest.SkipTest(str(exc))
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="redub media 中文 ")
        self.root=Path(self.temp.name)/"project"
        self.p=create(self.root,self.ff)
    def tearDown(self):self.temp.cleanup()
    def test_render_roundtrip_and_verified_cache(self):
        first=render(self.root,self.p,self.ff)
        self.assertEqual(first["status"],"verified")
        self.assertEqual(len(first["qc"]["turn_checks"]),2)
        self.assertGreaterEqual(first["qc"]["decoded_duration"],4.47)
        final=decode(first["path"],24000,self.ff)
        self.assertGreater(audio_metrics(final[round(4.25*24000):round(4.37*24000)],24000)["rms"],.01)
        second=render(self.root,self.p,self.ff)
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["sha256"],second["sha256"])
    def test_selected_waveform_and_original_cue(self):
        np=np_module();master,rate,audits=compose(self.root,self.p,self.ff)
        self.assertEqual(len(audits),2)
        original=decode(asset_path(self.root,self.p,self.p["source"]["asset"]),rate,self.ff)
        self.assertTrue(np.array_equal(master[round(1.6*rate):round(2*rate)],original[round(1.6*rate):round(2*rate)]))
    def test_silent_take_rejected_before_encode(self):
        np=np_module();f=self.root/"silence.wav";wav_write(f,np.zeros(24000),24000)
        rec=register_take(self.root,self.p,"turn_A",f,{"name":"synthetic","version":"silence"},{},"failure fixture")
        self.p["turns"][0]["selected_take"]=rec["id"]
        with self.assertRaises(RedubError) as caught:compose(self.root,self.p,self.ff)
        self.assertEqual(caught.exception.code,"SILENT_TAKE")
    def test_voiced_overrun_is_not_truncated(self):
        np=np_module();f=self.root/"long.wav";wav_write(f,np.ones(48000)*.05,24000)
        rec=register_take(self.root,self.p,"turn_A",f,{"name":"synthetic","version":"long"},{},"failure fixture")
        self.p["turns"][0]["selected_take"]=rec["id"]
        with self.assertRaises(RedubError) as caught:compose(self.root,self.p,self.ff)
        self.assertEqual(caught.exception.code,"VOICED_OVERRUN")
    def test_original_dialogue_must_be_cleared(self):
        self.p["mix"]["bed_asset"]=None
        with self.assertRaises(RedubError) as caught:compose(self.root,self.p,self.ff)
        self.assertEqual(caught.exception.code,"BACKGROUND_REQUIRED")
    def test_wrong_length_background_stem_rejected(self):
        self.p["mix"]["bed_asset"]=self.p["speakers"]["A"]["timbre_asset"]
        with self.assertRaises(RedubError) as caught:compose(self.root,self.p,self.ff)
        self.assertEqual(caught.exception.code,"BED_DURATION")
    def test_caption_escaping_does_not_execute_ass_tags(self):
        self.assertEqual(ass_escape(r"{\pos(0,0)}hello"),"｛＼pos(0,0)｝hello")
    def test_rounding_timestamp_carries(self):
        self.assertEqual(ass_time(59.999),"0:01:00.00")
        self.assertEqual(srt_time(59.9999),"00:01:00,000")
    def test_documented_revision_demo_preserves_B(self):
        from revise_demo import revise
        original,rate,_=compose(self.root,self.p,self.ff)
        result=revise(self.root)
        self.assertTrue(result["B_reused"])
        p=load_project(self.root);revised,_,_=compose(self.root,p,self.ff)
        np=np_module()
        self.assertTrue(np.array_equal(original[round(2.9*rate):round(4.4*rate)],revised[round(2.9*rate):round(4.4*rate)]))
        self.assertFalse(np.array_equal(original[round(.2*rate):round(1.2*rate)],revised[round(.2*rate):round(1.2*rate)]))


if __name__=="__main__":unittest.main()
