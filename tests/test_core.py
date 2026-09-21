import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from redub_core import *


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="redub-中文-")
        self.root=Path(self.temp.name)
        self.p=init_project(self.root,"https://example.invalid/video?x=1&y=2","讽刺虚构行业")
        f=self.root/"input.wav";f.write_bytes(b"a test immutable reference")
        self.aid=import_asset(self.root,self.p,f,"reference","Synthetic fixture")
        self.p["source"]={"asset":self.aid,"duration":12}
        self.p["scene"]={"keep":[{"start":1,"end":5},{"start":8,"end":12}],
                         "evidence":{"opening":"inspected","ending":"inspected","completeness":"compared"}}
        self.p["speakers"]={"A":{"label":"Actor A","timbre_asset":self.aid},"B":{"label":"Actor B","timbre_asset":self.aid}}
        self.t={"id":"t1","speaker":"A","start":2,"end":4,"source_text":"旧句",
                "text":"完整的新句。","action":"generate","performance_asset":self.aid,
                "cast_evidence":"Speaker begins before the reaction shot","captions":[]}
        self.p["turns"]=[self.t]
        self.backend={"name":"test","version":"1","params":{"seed":117}}
    def tearDown(self):self.temp.cleanup()
    def codes(self,stage="script"):
        return {v["code"] for v in validate(self.root,self.p,stage)["errors"]}
    def take(self):
        f=asset_path(self.root,self.p,self.aid)
        rec=register_take(self.root,self.p,"t1",f,self.backend,{"duration":2},"fixture")
        self.t["selected_take"]=rec["id"]
        return rec
    def test_valid_script(self):self.assertEqual(self.codes(),set())
    def test_edit_map_after_removed_scene(self):self.assertEqual(map_interval(self.p["scene"]["keep"],9,10),(5,6))
    def test_mid_utterance_cut_rejected(self):
        self.t["end"]=9
        self.assertIn("CUT_CROSSES_TURN",self.codes())
    def test_duplicate_and_swapped_turn_detection(self):
        other=copy.deepcopy(self.t);self.p["turns"].append(other)
        self.assertTrue({"TURN_ID","OVERLAPPING_TURNS"}.issubset(self.codes()))
    def test_reaction_shot_requires_cast_evidence(self):
        del self.t["cast_evidence"]
        self.assertIn("CAST_EVIDENCE",self.codes())
    def test_unsafe_asset_path(self):
        self.p["assets"][self.aid]["path"]="../private.wav"
        self.assertIn("UNSAFE_PATH",self.codes())
    def test_changed_bytes_same_filename_detected(self):
        asset_path(self.root,self.p,self.aid).write_bytes(b"changed")
        self.assertIn("ASSET_CORRUPT",self.codes())
    def test_missing_reference_is_not_silently_defaulted(self):
        self.t["performance_asset"]="absent"
        self.assertIn("REFERENCE_REQUIRED",self.codes("generate"))
    def test_unknown_claim(self):
        self.t["claim_ids"]=["notfound"]
        self.assertIn("UNKNOWN_CLAIM",self.codes())
    def test_verified_claim_needs_citation(self):
        self.p["claims"]=[{"id":"c","status":"verified","text":"alleged thing"}]
        self.assertIn("CLAIM_SOURCE",self.codes())
    def test_rumor_allowed_without_official_confirmation(self):
        self.p["claims"]=[{"id":"c","status":"rumor","text":"Unverified forum rumor","framing":"听说"}]
        self.t["claim_ids"]=["c"]
        self.assertEqual(self.codes(),set())
    def test_unchanged_take_valid(self):
        rec=self.take();self.assertEqual(selected_receipt(self.root,self.p,self.t)["id"],rec["id"])
    def test_text_change_invalidates_take(self):
        self.take();self.t["text"]="一句新的话"
        with self.assertRaisesRegex(RedubError,"changed"):selected_receipt(self.root,self.p,self.t)
    def test_cast_change_invalidates_take(self):
        self.take();self.t["speaker"]="B"
        with self.assertRaises(RedubError) as caught:selected_receipt(self.root,self.p,self.t)
        self.assertEqual(caught.exception.code,"CAST_MISMATCH")
    def test_reference_change_invalidates_take(self):
        self.take();f=self.root/"new.wav";f.write_bytes(b"different acting")
        self.t["performance_asset"]=import_asset(self.root,self.p,f,"reference","new")
        with self.assertRaises(RedubError) as caught:selected_receipt(self.root,self.p,self.t)
        self.assertEqual(caught.exception.code,"STALE_TAKE")
    def test_timing_and_seed_affect_cache(self):
        old=take_fingerprint(self.p,self.t,self.backend)
        self.t["end"]=4.1
        self.assertNotEqual(old,take_fingerprint(self.p,self.t,self.backend))
        self.t["end"]=4;self.backend["params"]["seed"]=118
        self.assertNotEqual(old,take_fingerprint(self.p,self.t,self.backend))
    def test_unrelated_turn_edit_does_not_invalidate_take(self):
        self.take();other=copy.deepcopy(self.t);other.update(id="t2",start=8,end=10,text="another")
        self.p["turns"].append(other)
        selected_receipt(self.root,self.p,self.t)
    def test_review_becomes_stale(self):
        review(self.root,self.p,"script","user","实际用户接受了剧本","message 1")
        self.assertTrue(review_current(self.p,"script"));self.t["text"]="Changed"
        self.assertFalse(review_current(self.p,"script"))
    def test_review_without_evidence_rejected(self):
        with self.assertRaises(RedubError):review(self.root,self.p,"pilot","user","approved","")
    def test_lock_blocks_second_writer(self):
        with writer_lock(self.root):
            with self.assertRaises(RedubError):
                with writer_lock(self.root):pass
        self.assertFalse((self.root/".redub.lock").exists())
    def test_interrupted_writer_not_auto_unlocked(self):
        atomic_json(self.root/".redub.lock",{"pid":99999999,"host":"other-host","token":"unknown"})
        with self.assertRaises(RedubError):
            with writer_lock(self.root):pass
        self.assertTrue((self.root/".redub.lock").exists())
    def test_captions_must_not_overlap(self):
        self.t["captions"]=[{"start":0,"end":1.5,"text":"one"},{"start":1,"end":2,"text":"two"}]
        self.assertIn("CAPTION_TIME",self.codes())
    def test_nonfinite_and_boolean_times_rejected(self):
        for bad in (float("nan"),True,-1):
            self.t["start"]=bad
            self.assertIn("TURN_TIME",self.codes())
    def test_locked_original_cannot_be_overwritten(self):
        self.p["mix"]["preserve_regions"]=[{"start":3,"end":3.5}]
        self.assertIn("PRESERVE_CONFLICT",self.codes())
    def test_idempotent_register(self):
        a=self.take();b=self.take();self.assertEqual(a["id"],b["id"])
        self.assertEqual(len(list((self.root/"takes/t1").glob("*.json"))),1)
    def test_schema_rejects_future_version(self):
        self.p["schema_version"]=99;atomic_json(self.root/"project.json",self.p)
        with self.assertRaises(RedubError):load_project(self.root)
    def test_cannot_change_subtitles_while_retaining_old_words(self):
        self.t["action"]="retain"
        self.assertIn("RETAINED_TEXT_CHANGED",self.codes())
        self.t["text"]=self.t["source_text"]+"！"
        self.assertNotIn("RETAINED_TEXT_CHANGED",self.codes())
    def test_duplicate_claim_ids_rejected(self):
        self.p["claims"]=[{"id":"one","status":"fiction"},{"id":"one","status":"rumor"}]
        self.assertIn("CLAIM_ID",self.codes())
    def test_invalid_audio_settings_rejected(self):
        self.p["settings"]["fade_ms"]=-10;self.t["gain_db"]=float("inf")
        self.assertTrue({"FADE_RANGE","GAIN_RANGE"}.issubset(self.codes()))


if __name__=="__main__":unittest.main()
