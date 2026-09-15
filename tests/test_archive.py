"""Archive integrity and failure checks, without touching working records."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.archive_store import ArchiveStore, ConflictError


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = ArchiveStore(self.folder.name)
        self.record = self.store.save_metadata({"title": "Sample", "date": "", "tags": ["oil", "oil"]})

    def test_originals_duplicate_names_and_reopening(self):
        body = b'\xff\xfex\x00,\x00y\x00\r\x00\n\x00'
        saved = self.store.add_file(self.record["id"], 1, "测量.csv", body)
        record = saved["record"]
        self.assertEqual(record["tags"], ["oil"])
        self.assertEqual(record["date"], "")
        duplicate = self.store.add_file(record["id"], 2, "测量.csv", body)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["record"]["revision"], 2)
        changed = self.store.add_file(record["id"], 2, "测量.csv", b"different bytes")["record"]
        self.assertEqual(len(changed["materials"]), 2)
        reopened = ArchiveStore(self.folder.name)
        _, actual = reopened.file_content(reopened.read(record["id"]), record["materials"][0]["id"])
        self.assertEqual(actual, body)
        with self.assertRaises(ConflictError):
            self.store.add_file(record["id"], 1, "stale.png", b"stale")

    def legacy(self):
        record = self.store.read(self.record["id"])
        record.update(assets={"csvText": "x,y\n1,2", "csvName": "old.csv"}, result={"area": 2},
                      calibration={"x1": 1}, extraction={"pixels": [{"corrected": True}]})
        self.store.write(record)
        return record

    def test_legacy_reads_do_not_migrate_and_metadata_keeps_analysis(self):
        legacy = self.legacy()
        path = Path(self.folder.name) / (legacy["id"] + ".json")
        before = path.read_bytes()
        catalog = self.store.catalog()
        self.assertFalse(catalog["records"][0]["materials"][0]["originalBytesAvailable"])
        self.assertEqual(path.read_bytes(), before)
        self.store.save_metadata({"title": "Changed", "revision": 1, "date": "2026-09-11"}, legacy["id"])
        edited = self.store.read(legacy["id"])
        for key in ("assets", "calibration", "extraction", "result"):
            self.assertEqual(edited[key], legacy[key])
        with self.assertRaises(ConflictError):
            self.store.save_metadata({"title": "Stale", "revision": 1}, legacy["id"])

    def test_replaced_review_inputs_remain_archived(self):
        old = self.legacy()
        incoming = json.loads(json.dumps(old))
        incoming["assets"] = {"csvName": "old.csv", "csvText": "x,y\n1,3",
                              "csvData": "data:text/csv;base64," + base64.b64encode(b"x,y\n1,3").decode()}
        self.store.retain_replaced_inputs(old, incoming)
        self.store.write(incoming)
        files = self.store.materials(incoming)
        self.assertEqual(len(files), 2)
        archived = next(item for item in files if not item.get("legacy"))
        self.assertFalse(archived["originalBytesAvailable"])
        self.assertEqual(self.store.file_content(incoming, archived["id"])[1], b"x,y\n1,2")
        self.store.retain_replaced_inputs(old, incoming)
        self.assertEqual(len(incoming["attachments"]), 1)

    def test_export_contains_originals_and_verifiable_manifest(self):
        identity = self.record["id"]
        for revision, body in enumerate((b"first", b"second"), start=1):
            self.store.add_file(identity, revision, "same.tiff", body)
        output = io.BytesIO()
        self.store.export(identity, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(json.loads(archive.read("record.json"))["id"], identity)
            files = json.loads(archive.read("manifest.json"))["files"]
            self.assertEqual(len({item["path"] for item in files}), 2)
            self.assertEqual([archive.read(item["path"]) for item in files], [b"first", b"second"])
            for item in files:
                self.assertEqual(hashlib.sha256(archive.read(item["path"])).hexdigest(), item["sha256"])

    def test_failed_record_write_preserves_previous_record_and_retry(self):
        identity = self.record["id"]
        before = self.store.read(identity)
        with patch.object(self.store, "write", side_effect=OSError("Disk failure")):
            with self.assertRaises(OSError):
                self.store.add_file(identity, 1, "sample.bin", b"original")
        self.assertEqual(self.store.read(identity), before)
        saved = self.store.add_file(identity, 1, "sample.bin", b"original")
        self.assertEqual(saved["record"]["revision"], 2)
        path = self.store.files / (saved["record"]["materials"][0]["sha256"] + ".bin")
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.store.file_content(self.store.read(identity), saved["record"]["materials"][0]["id"])

    def test_invalid_inputs_and_record_limits(self):
        for name in ("../escape", "folder/file", "folder\\file", "bad\nname"):
            with self.assertRaises(ValueError):
                self.store.add_file(self.record["id"], 1, name, b"")
        with self.assertRaises(ValueError):
            self.store.save_metadata({"title": "Bad date", "date": "2026-02-30"})
        with patch("scripts.archive_store.MAX_RECORD_FILES", 0):
            with self.assertRaises(ValueError):
                self.store.add_file(self.record["id"], 1, "a.bin", b"a")
        with patch("scripts.archive_store.MAX_RECORD_BYTES", 1):
            with self.assertRaises(ValueError):
                self.store.add_file(self.record["id"], 1, "a.bin", b"ab")
        with patch("scripts.archive_store.MAX_FILE", 1):
            with self.assertRaises(ValueError):
                self.store.add_file(self.record["id"], 1, "a.bin", b"ab")
        (Path(self.folder.name) / ("a" * 32 + ".json")).write_text("invalid", encoding="utf-8")
        self.assertEqual(len(self.store.catalog()["errors"]), 1)
        self.assertEqual(len(self.store.catalog()["records"]), 1)

    def test_record_trash_is_reversible_and_blocks_mutation(self):
        legacy = self.legacy()
        identity = legacy["id"]
        trashed = self.store.set_trashed(identity, 1, True)
        self.assertTrue(trashed["deletedAt"])
        self.assertEqual(self.store.catalog()["records"], [])
        self.assertEqual(self.store.catalog(trashed=True)["records"][0]["id"], identity)
        with self.assertRaises(ConflictError):
            self.store.save_metadata({"title": "Edit", "revision": 2}, identity)
        with self.assertRaises(ConflictError):
            self.store.add_file(identity, 2, "file.txt", b"new")
        with self.assertRaises(ConflictError):
            self.store.set_trashed(identity, 1, False)
        restored = self.store.set_trashed(identity, 2, False)
        self.assertFalse(restored["deletedAt"])
        self.assertEqual(self.store.read(identity)["result"], legacy["result"])
        self.assertEqual(self.store.file_content(self.store.read(identity), "legacy-csv")[1], b"x,y\n1,2")

    def test_file_trash_keeps_shared_bytes_export_and_limits(self):
        identity = self.record["id"]
        saved = self.store.add_file(identity, 1, "one.txt", b"shared")["record"]
        attachment = saved["materials"][0]
        other = self.store.save_metadata({"title": "Other"})
        self.store.add_file(other["id"], 1, "two.txt", b"shared")
        trashed = self.store.set_trashed(identity, 2, True, attachment["id"])
        self.assertEqual(trashed["materials"], [])
        self.assertEqual(len(trashed["trashedMaterials"]), 1)
        self.assertEqual(len(list(self.store.files.glob("*.bin"))), 1)
        self.assertEqual(self.store.file_content(self.store.read(identity), attachment["id"])[1], b"shared")
        with self.assertRaises(ConflictError):
            self.store.add_file(identity, 3, "one.txt", b"shared")
        with patch("scripts.archive_store.MAX_RECORD_FILES", 1):
            with self.assertRaises(ValueError):
                self.store.add_file(identity, 3, "new.txt", b"new")
        output = io.BytesIO()
        self.store.export(identity, output)
        with zipfile.ZipFile(output) as archive:
            files = json.loads(archive.read("manifest.json"))["files"]
            self.assertTrue(files[0]["deletedAt"])
            self.assertEqual(archive.read(files[0]["path"]), b"shared")
        restored = self.store.set_trashed(identity, 3, False, attachment["id"])
        self.assertEqual(restored["materials"][0]["sha256"], attachment["sha256"])

    def test_active_analysis_inputs_cannot_be_trashed(self):
        legacy = self.legacy()
        with self.assertRaisesRegex(ValueError, "analysis input"):
            self.store.set_trashed(legacy["id"], 1, True, "legacy-csv")
        self.assertEqual(self.store.read(legacy["id"]), legacy)


if __name__ == "__main__":
    unittest.main()
