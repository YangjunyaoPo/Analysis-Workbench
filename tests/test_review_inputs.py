"""Selecting archived inputs preserves originals and invalidates only dependents."""
import base64
import tempfile
import unittest
from unittest.mock import patch

from scripts.archive_store import ArchiveStore, ConflictError
from scripts.review_inputs import choose_input


class ReviewInputTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = ArchiveStore(self.folder.name)
        self.identity = self.store.save_metadata({"title": "Inputs"})["id"]

    def attach(self, name, body):
        record = self.store.read(self.identity)
        return self.store.add_file(self.identity, record["revision"], name, body)["record"]["materials"][-1]

    def choose(self, kind, file_id):
        return choose_input(self.store, self.identity, self.store.read(self.identity)["revision"], kind, file_id)

    def test_csv_selection_keeps_bytes_and_invalidates_results(self):
        body = 'x,y\r\n0,0\r\n1,2\r\n2,0\r\n'.encode('utf-16')
        item = self.attach("triangle.csv", body)
        record = self.store.read(self.identity)
        record.update(extraction={"pixels": [{"px": 1.5, "py": 2}]}, result={"area": 99},
                      comparison={"p95": 1}, reviewed=True)
        record["settings"].update(xUnit="old unit", yi="7")
        record["assets"].update(provenance="Previous demo pair", source="https://example.org/old-pair")
        self.store.write(record)
        detail = self.choose("csv", item["id"])
        saved = self.store.read(self.identity)
        self.assertEqual(len(detail["materials"]), 1)
        self.assertEqual(detail["materials"][0]["usedBy"], "csv")
        self.assertEqual(base64.b64decode(saved["assets"]["csvData"].split(",")[1]), body)
        self.assertEqual(saved["assets"]["csvText"], "x,y\r\n0,0\r\n1,2\r\n2,0\r\n")
        self.assertEqual(saved["extraction"], record["extraction"])
        for key in ("result", "comparison"):
            self.assertIsNone(saved[key])
        self.assertFalse(saved["reviewed"])
        self.assertNotIn("source", saved["assets"])
        self.assertNotEqual(saved["assets"]["provenance"], "Previous demo pair")
        self.assertEqual((saved["settings"]["xi"], saved["settings"]["yi"], saved["settings"]["xUnit"]), ("0", "1", ""))
        self.assertEqual(self.choose("csv", item["id"])["revision"], saved["revision"])
        with self.assertRaisesRegex(ValueError, "analysis input"):
            self.store.set_trashed(self.identity, saved["revision"], True, item["id"])

    def test_image_replacement_clears_geometry_and_keeps_previous_material(self):
        item = self.attach("new.png", b"new image bytes")
        old = self.store.read(self.identity)
        old.update(assets={"imageName": "old.png", "imageData": "data:image/png;base64," + base64.b64encode(b"old").decode()},
                   calibration={"x1": 10}, extraction={"pixels": []}, sampleCalibration={"x1": 10}, result={"area": 4}, reviewed=True)
        self.store.write(old)
        detail = self.choose("image", item["id"])
        saved = self.store.read(self.identity)
        self.assertEqual({m["name"] for m in detail["materials"]}, {"old.png", "new.png"})
        self.assertEqual(saved["calibration"], {})
        for key in ("extraction", "sampleCalibration", "result"):
            self.assertIsNone(saved[key])
        old_file = next(m for m in detail["materials"] if m["name"] == "old.png")
        self.assertEqual(self.store.file_content(saved, old_file["id"])[1], b"old")

    def test_detaching_legacy_csv_keeps_its_encoding_disclosure_and_allows_trash(self):
        old = self.store.read(self.identity)
        old["assets"] = {"csvText": "x,y\n1,2", "csvName": "legacy.csv"}
        self.store.write(old)
        detail = self.choose("csv", None)
        item = detail["materials"][0]
        self.assertFalse(item["originalBytesAvailable"])
        self.assertFalse(detail["hasReviewInputs"])
        self.assertNotIn("csvText", self.store.read(self.identity)["assets"])
        self.store.set_trashed(self.identity, detail["revision"], True, item["id"])
        with self.assertRaises(ValueError):
            self.choose("csv", item["id"])

    def test_invalid_csv_wrong_format_and_stale_selection_do_not_change_record(self):
        for name, body in (("bad.csv", b"x,y\n1,2,3"), ("one.csv", b"header\n1"),
                           ("encoding.csv", b"\xff\x00"), ("table.xlsx", b"xlsx")):
            item = self.attach(name, body)
            before = self.store.read(self.identity)
            with self.assertRaises(ValueError):
                self.choose("csv", item["id"])
            self.assertEqual(self.store.read(self.identity), before)
        with self.assertRaises(ConflictError):
            choose_input(self.store, self.identity, 1, "csv", item["id"])

    def test_analysis_limits_do_not_remove_large_archived_files(self):
        item = self.attach("large.csv", b"x,y\n0,0\n1,1")
        before = self.store.read(self.identity)
        with patch("scripts.review_inputs.REVIEW_FILE_LIMIT", 1), self.assertRaises(ValueError):
            self.choose("csv", item["id"])
        with patch("scripts.review_inputs.REVIEW_SNAPSHOT_LIMIT", 1), self.assertRaises(ValueError):
            self.choose("csv", item["id"])
        self.assertEqual(self.store.read(self.identity), before)
        self.assertEqual(self.store.file_content(before, item["id"])[1], b"x,y\n0,0\n1,1")


if __name__ == "__main__":
    unittest.main()
