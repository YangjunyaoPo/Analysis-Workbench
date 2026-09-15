"""Round-trip and malformed-package checks against isolated storage."""
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.archive_store import ArchiveStore
from scripts.archive_transfer import import_package


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.source_folder = tempfile.TemporaryDirectory()
        self.destination_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_folder.cleanup)
        self.addCleanup(self.destination_folder.cleanup)
        self.source = ArchiveStore(self.source_folder.name)
        self.destination = ArchiveStore(self.destination_folder.name)
        saved = self.source.save_metadata({"title": "Experiment", "tags": ["oil"], "date": ""})
        self.identity = saved["id"]
        self.source.add_file(self.identity, 1, "same.txt", b"first")
        self.source.add_file(self.identity, 2, "same.txt", b"second")
        record = self.source.read(self.identity)
        record.update(assets={"csvName": "old.csv", "csvText": "x,y\n1,2"},
                      result={"area": 2}, extraction={"pixels": [{"px": 1.5, "py": 2.5}]})
        self.source.write(record)
        self.source.set_trashed(self.identity, 3, True, record["attachments"][0]["id"])
        output = io.BytesIO()
        self.source.export(self.identity, output)
        self.package = output.getvalue()

    def repack(self, change):
        with zipfile.ZipFile(io.BytesIO(self.package)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        change(entries)
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, body in entries.items():
                archive.writestr(name, body)
        result.seek(0)
        return result

    def assert_no_records(self):
        self.assertEqual(list(self.destination.folder.glob("*.json")), [])

    def test_roundtrip_preserves_analysis_originals_and_trash(self):
        imported = import_package(self.destination, io.BytesIO(self.package))
        record = self.destination.read(imported["id"])
        source = self.source.read(self.identity)
        self.assertNotEqual(imported["id"], self.identity)
        self.assertEqual(record["revision"], 1)
        for key in ("title", "date", "tags", "assets", "extraction", "result"):
            self.assertEqual(record[key], source[key])
        self.assertEqual(record["importedFrom"]["id"], self.identity)
        self.assertEqual(len(imported["trashedMaterials"]), 1)
        self.assertFalse(next(m for m in imported["materials"] if m["id"] == "legacy-csv")["originalBytesAvailable"])
        for item in self.source.materials(source, include_deleted=True):
            self.assertEqual(self.destination.file_content(record, item["id"])[1], self.source.file_content(source, item["id"])[1])
        reexport = io.BytesIO()
        self.destination.export(imported["id"], reexport)
        again = import_package(self.source, reexport)
        self.assertEqual(self.source.read(again["id"])["result"], source["result"])
        self.assertEqual(self.source.read(self.identity), source)

    def test_repeat_import_creates_copies_without_overwriting(self):
        original = self.source.read(self.identity)
        first = import_package(self.source, io.BytesIO(self.package))
        second = import_package(self.source, io.BytesIO(self.package))
        self.assertEqual(len({first["id"], second["id"], self.identity}), 3)
        self.assertEqual(self.source.read(self.identity), original)

    def test_corrupt_bytes_fail_before_any_original_is_written(self):
        def corrupt(entries):
            path = next(name for name in entries if name.startswith("files/"))
            entries[path] = b"x" * len(entries[path])
        with self.assertRaisesRegex(ValueError, "integrity"):
            import_package(self.destination, self.repack(corrupt))
        self.assert_no_records()
        self.assertFalse(self.destination.files.exists())

    def test_traversal_and_unlisted_files_are_rejected(self):
        for extra in ("../outside.txt", "/absolute.txt", "files/unlisted.txt", "C:\\file.txt"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                import_package(self.destination, self.repack(lambda entries: entries.update({extra: b"bad"})))
        self.assert_no_records()
        self.assertFalse(self.destination.files.exists())

    def test_manifest_mismatch_and_missing_file_are_rejected(self):
        def change_manifest(entries):
            manifest = json.loads(entries["manifest.json"])
            manifest["files"][0]["name"] = "different.csv"
            entries["manifest.json"] = json.dumps(manifest).encode()
        with self.assertRaises(ValueError):
            import_package(self.destination, self.repack(change_manifest))
        def remove_file(entries):
            entries.pop(next(name for name in entries if name.startswith("files/")))
        with self.assertRaises(ValueError):
            import_package(self.destination, self.repack(remove_file))
        self.assert_no_records()

    def test_entry_limits_and_duplicate_zip_members_are_rejected(self):
        with patch("scripts.archive_transfer.MAX_FILE", 1), self.assertRaisesRegex(ValueError, "size limit"):
            import_package(self.destination, io.BytesIO(self.package))
        duplicate = io.BytesIO(self.package)
        with zipfile.ZipFile(duplicate, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr("record.json", "{}")
        duplicate.seek(0)
        with self.assertRaisesRegex(ValueError, "duplicate ZIP"):
            import_package(self.destination, duplicate)
        self.assert_no_records()

    def test_invalid_json_and_record_shape_are_rejected(self):
        for body in (b'{"schema":1,"schema":2}', b'{"schema":NaN}', b'[]', b'{"schema":1,"id":false}', b'{"schema":999}'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                import_package(self.destination, self.repack(lambda entries: entries.update({"record.json": body})))
        with self.assertRaises(ValueError):
            import_package(self.destination, io.BytesIO(b"not a zip"))
        self.assert_no_records()

    def test_failed_publish_leaves_no_visible_partial_record_and_can_retry(self):
        with patch.object(self.destination, "write", side_effect=OSError("Disk failure")), self.assertRaises(OSError):
            import_package(self.destination, io.BytesIO(self.package))
        self.assert_no_records()
        imported = import_package(self.destination, io.BytesIO(self.package))
        self.assertEqual(imported["title"], "Experiment")


if __name__ == "__main__":
    unittest.main()
