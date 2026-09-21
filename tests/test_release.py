from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from package_release import package,ROOT_FILES
from redub_core import RedubError


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/"skill";self.root.mkdir()
        for name in ROOT_FILES:(self.root/name).write_text("Synthetic release fixture\n",encoding="utf-8")
    def tearDown(self):self.temp.cleanup()
    def test_deterministic_zip_and_relative_manifest(self):
        one=package(self.root,self.base/"one.zip");two=package(self.root,self.base/"two.zip")
        self.assertEqual(one["sha256"],two["sha256"])
        self.assertEqual(one["zip"],"one.zip")
        with zipfile.ZipFile(self.base/"one.zip") as archive:
            self.assertIn("scene-redub/release_manifest.json",archive.namelist())
    def test_private_path_rejected(self):
        # Build the sensitive fixture without embedding a private path in the package itself.
        (self.root/"README.md").write_text("C:"+"/Users/"+"someone/secret.txt",encoding="utf-8")
        with self.assertRaises(RedubError) as caught:package(self.root,self.base/"bad.zip")
        self.assertEqual(caught.exception.code,"PRIVATE_DATA_PATTERN")
    def test_media_never_bundled(self):
        (self.root/"movie.mp4").write_bytes(b"fake-media")
        with self.assertRaises(RedubError) as caught:package(self.root,self.base/"bad.zip")
        self.assertEqual(caught.exception.code,"UNEXPECTED_RELEASE_FILE")
    def test_non_utf8_file_rejected(self):
        (self.root/"README.md").write_bytes(bytes([255,254,128]))
        with self.assertRaises(RedubError) as caught:package(self.root,self.base/"bad.zip")
        self.assertEqual(caught.exception.code,"NON_UTF8_FILE")
    def test_existing_release_never_overwritten(self):
        dest=self.base/"one.zip";package(self.root,dest)
        with self.assertRaises(RedubError) as caught:package(self.root,dest)
        self.assertEqual(caught.exception.code,"RELEASE_EXISTS")
    def test_repack_extracted_release_is_reproducible(self):
        first=package(self.root,self.base/"one.zip")
        extracted=self.base/"extracted"
        with zipfile.ZipFile(self.base/"one.zip") as archive:archive.extractall(extracted)
        second=package(extracted/"scene-redub",self.base/"two.zip")
        self.assertEqual(first["sha256"],second["sha256"])
    def test_git_metadata_not_shipped(self):
        first=package(self.root,self.base/"plain.zip")
        git=self.root/".git";git.mkdir();(git/"config").write_text("synthetic repository config",encoding="utf-8")
        second=package(self.root,self.base/"checkout.zip")
        self.assertEqual(first["sha256"],second["sha256"])
        with zipfile.ZipFile(self.base/"checkout.zip") as archive:
            self.assertFalse(any(".git/" in p for p in archive.namelist()))
    def test_installed_runtime_locator_is_never_published(self):
        first=package(self.root,self.base/"before.zip")
        (self.root/"runtime.json").write_text('{"root":"C:'+"/Users/"+'private/engine"}',encoding="utf-8")
        second=package(self.root,self.base/"after.zip")
        self.assertEqual(first["sha256"],second["sha256"])


if __name__=="__main__":unittest.main()
