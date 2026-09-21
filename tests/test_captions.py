import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from caption_align import align
from redub_core import RedubError


class CaptionTests(unittest.TestCase):
    def test_pause_is_preserved_not_distributed_by_characters(self):
        r=align(["我。","我们。"],[{"word":"我","start":.1,"end":.4},{"word":"我们","start":1.9,"end":2.3}],3)
        self.assertEqual(r["captions"][1]["start"],1.9)
    def test_mismatch_does_not_produce_false_precision(self):
        r=align(["完全不相干"],[{"word":"hello","start":0,"end":1}],1)
        self.assertEqual(r["captions"],[])
    def test_cannot_split_inside_asr_word(self):
        r=align(["我","们"],[{"word":"我们","start":0,"end":1}],1)
        self.assertEqual(r["captions"],[])
    def test_explicit_pronunciation_alias(self):
        r=align(["Claude。"],[{"word":"克劳德","start":.1,"end":1}],1,{"Claude":"克劳德"})
        self.assertEqual(r["coverage"],1)
    def test_reject_negative_word_time(self):
        with self.assertRaises(RedubError):align(["a"],[{"word":"a","start":-1,"end":1}],1)


if __name__=="__main__":unittest.main()
