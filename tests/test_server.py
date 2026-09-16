"""Real HTTP persistence checks against an isolated temporary record directory."""
import json
import io
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile

from scripts import serve_prototype as server_module


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.previous_records = server_module.RECORDS
        server_module.RECORDS = Path(self.folder.name)
        self.server = server_module.ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.folder.cleanup()
        server_module.RECORDS = self.previous_records

    def request(self, path, payload=None, origin=None):
        headers = {"Content-Type": "application/json", "X-Workbench-Request": "1"}
        if origin:
            headers["Origin"] = origin
        body = json.dumps(payload).encode() if payload is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=body, headers=headers)) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_saved_originals_reopen_and_stale_writes_fail(self):
        record = {"schema": 1, "title": "Fixture", "date": "", "category": "FTIR", "notes": "checked",
                  "assets": {"csvText": "x,y\n0,-1\n1,NaN", "imageData": "data:image/png;base64,test"},
                  "calibration": {"x1": 10}, "extraction": {"pixels": [{"px": 1.5, "py": 2.5, "corrected": True}]}}
        status, saved = self.request("/api/records", record)
        self.assertEqual(status, 200)
        status, loaded = self.request("/api/records/" + saved["id"])
        for key in ("assets", "calibration", "extraction", "notes", "date"):
            self.assertEqual(record[key], loaded[key])
        self.assertEqual(len(list(server_module.RECORDS.glob("*.json"))), 1)
        status, updated = self.request("/api/records", loaded)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(self.request("/api/records", loaded)[0], 409)

    def test_invalid_date_and_foreign_origin_do_not_save(self):
        record = {"schema": 1, "title": "Fixture", "date": "2026-02-30", "category": "", "notes": ""}
        self.assertEqual(self.request("/api/records", record)[0], 400)
        self.assertEqual(self.request("/api/records", record, "https://example.org")[0], 403)
        self.assertEqual(list(server_module.RECORDS.glob("*.json")), [])

    def test_unlisted_files_are_not_served(self):
        for path in ("/AGENTS.md", "/.git/config", "/api/records/../../README.md"):
            self.assertEqual(self.request(path)[0], 404)

    def binary_request(self, path, body=None, revision=1, origin=None):
        headers = {"Content-Type": "application/octet-stream", "X-Workbench-Request": "1",
                   "X-Record-Revision": str(revision)}
        if origin:
            headers["Origin"] = origin
        try:
            response = urllib.request.urlopen(urllib.request.Request(self.base + path, data=body, headers=headers))
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_archive_upload_preview_download_export_and_conflicts(self):
        status, record = self.request("/api/archive", {"title": "Multi-file sample", "tags": ["test"]})
        self.assertEqual(status, 200)
        path = "/api/archive/" + record["id"]
        body = b'\xef\xbb\xbfx,y\r\n1,2\r\n'
        status, _, saved = self.binary_request(path + "/files?name=sample.csv", body)
        self.assertEqual(status, 200)
        record = json.loads(saved)["record"]
        file_path = path + "/files/" + record["materials"][0]["id"]
        self.assertEqual(self.binary_request(file_path)[2], body)
        status, preview = self.request(file_path + "?preview=1")
        self.assertEqual((status, preview["text"]), (200, "x,y\r\n1,2\r\n"))
        self.assertEqual(self.binary_request(path + "/files?name=stale.bin", b"x", 1)[0], 409)
        self.assertEqual(self.binary_request(path + "/files?name=x.bin", b"x", 2, "https://example.org")[0], 403)
        self.assertEqual(self.request(path, {"title": "Stale", "revision": 1})[0], 409)
        status, _, saved = self.binary_request(path + "/files?name=image.tiff", b"original tiff fixture", 2)
        self.assertEqual(status, 200)
        record = json.loads(saved)["record"]
        tiff_path = path + "/files/" + record["materials"][-1]["id"]
        self.assertEqual(self.request(tiff_path + "?preview=1")[0], 415)
        self.assertEqual(self.binary_request(tiff_path)[2], b"original tiff fixture")
        status, headers, output = self.binary_request(path + "/export")
        self.assertEqual((status, headers["Content-Type"]), (200, "application/zip"))
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            files = json.loads(archive.read("manifest.json"))["files"]
            self.assertEqual(archive.read(files[0]["path"]), body)
            self.assertEqual(archive.read(files[1]["path"]), b"original tiff fixture")
        self.assertEqual(len(self.request("/api/archive")[1]["records"]), 1)

    def test_analysis_saves_preserve_archive_materials_and_tags(self):
        _, saved = self.request("/api/records", {"schema": 1, "title": "Review", "date": "", "category": "", "notes": "",
                                               "assets": {"csvText": "x,y\n1,2", "csvName": "old.csv"}, "result": {"area": 2}})
        path = "/api/archive/" + saved["id"]
        _, edited = self.request(path, {"title": "Edited", "revision": 1, "tags": ["retained"]})
        self.binary_request(path + "/files?name=notes.txt", b"lab notes", edited["revision"])
        _, loaded = self.request("/api/records/" + saved["id"])
        for key in ("tags", "attachments", "createdAt"):
            loaded.pop(key, None)
        loaded["assets"] = {"csvText": "x,y\n1,3", "csvName": "new.csv"}
        self.assertEqual(self.request("/api/records", loaded)[0], 200)
        _, archived = self.request(path)
        self.assertEqual(archived["tags"], ["retained"])
        self.assertEqual({m["name"] for m in archived["materials"]}, {"old.csv", "new.csv", "notes.txt"})

    def test_archive_entrypoint_and_assets_are_served(self):
        for path, content_type in (("/archive", "text/html"), ("/archive.mjs", "text/javascript"),
                                   ("/archive-filters.mjs", "text/javascript"), ("/archive.css", "text/css")):
            status, headers, body = self.binary_request(path)
            self.assertEqual(status, 200)
            self.assertIn(content_type, headers["Content-Type"])
            self.assertTrue(body)

    def test_trash_routes_preserve_bytes_and_block_stale_analysis_saves(self):
        _, record = self.request("/api/archive", {"title": "Trash test"})
        identity = record["id"]
        path = "/api/archive/" + identity
        _, _, saved = self.binary_request(path + "/files?name=notes.txt", b"keep")
        file_id = json.loads(saved)["record"]["materials"][0]["id"]
        self.assertEqual(self.request(path + "/files/" + file_id + "/trash", {"revision": 2})[0], 200)
        self.assertEqual(self.binary_request(path + "/files/" + file_id)[2], b"keep")
        self.assertEqual(self.request(path + "/files/" + file_id + "/restore", {"revision": 3})[0], 200)
        self.assertEqual(self.request(path + "/trash", {"revision": 4})[0], 200)
        self.assertEqual(self.request("/api/archive")[1]["records"], [])
        self.assertEqual(self.request("/api/records")[1], [])
        self.assertEqual(self.request("/api/archive?view=trash")[1]["records"][0]["id"], identity)
        _, current = self.request("/api/records/" + identity)
        self.assertEqual(self.request("/api/records", current)[0], 409)
        self.assertEqual(self.request(path + "/restore", {"revision": 4})[0], 409)
        self.assertEqual(self.request(path + "/restore", {"revision": 5})[0], 200)
        self.assertEqual(self.request("/api/records")[1][0]["id"], identity)

    def test_import_roundtrip_through_http_creates_a_copy(self):
        _, source = self.request("/api/archive", {"title": "Export and import"})
        path = "/api/archive/" + source["id"]
        self.binary_request(path + "/files?name=original.bin", b"original bytes")
        package = self.binary_request(path + "/export")[2]
        status, _, body = self.binary_request("/api/archive/import", package)
        self.assertEqual(status, 200)
        imported = json.loads(body)
        self.assertNotEqual(imported["id"], source["id"])
        imported_file = f'/api/archive/{imported["id"]}/files/{imported["materials"][0]["id"]}'
        self.assertEqual(self.binary_request(imported_file)[2], b"original bytes")
        self.assertEqual(self.binary_request("/api/archive/import", b"invalid zip")[0], 400)
        self.assertEqual(self.binary_request("/api/archive/import", package, origin="https://example.org")[0], 403)
        self.assertEqual(len(self.request("/api/archive")[1]["records"]), 2)

    def test_archived_csv_can_be_selected_saved_and_detached(self):
        _, record = self.request("/api/archive", {"title": "Archive analysis"})
        path = "/api/archive/" + record["id"]
        _, _, upload = self.binary_request(path + "/files?name=triangle.csv", b"x,y\n0,0\n1,2\n2,0")
        file_id = json.loads(upload)["record"]["materials"][0]["id"]
        self.assertEqual(self.request(path + "/inputs", {"revision": 2, "kind": "csv", "fileId": file_id})[0], 200)
        _, analysis = self.request("/api/records/" + record["id"])
        self.assertEqual(analysis["assets"]["csvText"], "x,y\n0,0\n1,2\n2,0")
        analysis["result"] = {"area": 2}
        self.assertEqual(self.request("/api/records", analysis)[0], 200)
        self.assertEqual(self.request(path)[1]["materials"][0]["usedBy"], "csv")
        self.assertEqual(self.request(path + "/files/" + file_id + "/trash", {"revision": 4})[0], 400)
        self.assertEqual(self.request(path + "/inputs", {"revision": 4, "kind": "csv", "fileId": None})[0], 200)
        self.assertEqual(self.request(path + "/files/" + file_id + "/trash", {"revision": 5})[0], 200)


if __name__ == "__main__":
    unittest.main()
