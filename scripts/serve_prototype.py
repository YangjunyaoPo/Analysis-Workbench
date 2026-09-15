"""Loopback-only prototype server. Saves review snapshots under ignored data/.

No external packages, external requests, or arbitrary filesystem browsing.
Run: python scripts/serve_prototype.py [--port 8765]
"""

import argparse
import base64
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import threading
import tempfile
from urllib.parse import urlsplit, parse_qs, quote
import uuid

if __package__:
    from .archive_store import ArchiveStore, ConflictError, MAX_FILE
else:
    from archive_store import ArchiveStore, ConflictError, MAX_FILE

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "prototype"
SAMPLES = ROOT / "data/initial-samples"
RECORDS = ROOT / "data/prototype-records"
LOCK = threading.Lock()
LIMIT = 30 * 1024 * 1024
ID = re.compile(r"^[0-9a-f]{32}$")
STATIC = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css",
          "/app.mjs": "app.mjs", "/core.mjs": "core.mjs", "/archive": "archive.html",
          "/archive.html": "archive.html", "/archive.mjs": "archive.mjs",
          "/archive.css": "archive.css", "/archive-filters.mjs": "archive-filters.mjs"}
STEMS = {
    "raman": "2024-10-11_acetonitrileinquartzcuvette_n_n_n_solid_10000_0_5",
    "weak": "2024-10-11_acetonitrileinquartzcuvette_n_n_n_solid_10_0_5",
    "dark": "2024-10-11_darkspectrum_n_n_n_solid_10000_0_5",
}


def sample(name):
    if name == "ftir":
        folder = SAMPLES / "controlled-fixtures"
        reference = json.loads((folder / "ftir-reference.json").read_text())
        csv_text = "Wavenumber,Signal\n" + "\n".join(f"{x},{y}" for x, y in reference["points"])
        image = folder / "ftir-reference.png"
        return {"title": "FTIR reference — AVE1AVC121", "date": "", "category": "FTIR",
                "csvName": "ftir-reference.csv", "csvText": csv_text,
                "csvData": "data:text/csv;base64," + base64.b64encode(csv_text.encode()).decode("ascii"),
                "imageName": image.name, "imageData": data_url(image),
                "xUnit": "cm^-1", "yUnit": "Unknown signal unit", "xi": 0, "yi": 1,
                "interval": [1600, 1800], "color": "#1261a0",
                "calibration": {"px1": 150, "px2": 1340, "py1": 750, "py2": 140,
                                "x1": 1600, "x2": 1800, "y1": 0, "y2": .1},
                "provenance": "Locally rendered from Jimenez-Carvelo, Zenodo 14651816, CC BY 4.0. First sample cropped to 1600–1800 cm^-1. Experiment date unknown.",
                "source": "https://zenodo.org/records/14651816"}
    if name not in STEMS:
        raise ValueError("Unknown sample.")
    stem = STEMS[name]
    folder = SAMPLES / "arcadia/selected"
    return {"title": stem, "date": "2024-10-11", "category": "Raman",
            "csvName": stem + ".csv", "csvText": (folder / (stem + ".csv")).read_text(),
            "csvData": data_url(folder / (stem + ".csv"), "text/csv"),
            "imageName": stem + ".png", "imageData": data_url(folder / (stem + ".png")),
            "xUnit": "cm^-1", "yUnit": "a.u.", "xi": 4, "yi": 1,
            "interval": [2800, 3100], "color": "#0000ff", "calibration": None,
            "provenance": "Arcadia Science · researcher-produced plot and same-stem CSV · 2024-10-11. Exact image/table agreement requires checking. Local evaluation only; separate image reuse terms unconfirmed.",
            "source": "https://github.com/Arcadia-Science/2025-diyraman-bio/tree/05975ad9eb95ba868a61ceb90058d3fedf2eb035"}


def data_url(path, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def validate_record(payload):
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Unsupported review format.")
    for key, maximum in (("title", 500), ("category", 100), ("notes", 20000)):
        if not isinstance(payload.get(key), str) or len(payload[key]) > maximum:
            raise ValueError(f"Invalid {key}.")
    if not payload["title"].strip():
        raise ValueError("Give the review a title.")
    date = payload.get("date", "")
    if not isinstance(date, str):
        raise ValueError("Invalid experiment date.")
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("Use YYYY-MM-DD for experiment date.")
        datetime.strptime(date, "%Y-%m-%d")
    return payload


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type="application/json", extra_headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def permitted(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        return host in allowed and self.headers.get("Origin", f"http://{host}") == f"http://{host}"

    def do_GET(self):
        if not self.permitted():
            return self.reply(403, {"error": "Use the local workbench origin."})
        path = urlsplit(self.path).path
        try:
            if path == "/api/archive" or path.startswith("/api/archive/"):
                return self.archive_get()
            if path in STATIC:
                file = ASSETS / STATIC[path]
                mime = "text/javascript" if file.suffix == ".mjs" else mimetypes.guess_type(file.name)[0]
                return self.reply(200, file.read_bytes(), mime + "; charset=utf-8")
            if path == "/api/records":
                records = []
                with LOCK:
                    for file in RECORDS.glob("*.json"):
                        r = json.loads(file.read_text(encoding="utf-8"))
                        records.append({k: r.get(k) for k in ("id", "title", "date", "category", "savedAt", "revision")})
                return self.reply(200, sorted(records, key=lambda r: r["savedAt"], reverse=True))
            if path.startswith("/api/records/") and ID.fullmatch(path.rsplit("/", 1)[-1]):
                return self.reply(200, (RECORDS / (path.rsplit("/", 1)[-1] + ".json")).read_bytes())
            if path.startswith("/api/samples/"):
                return self.reply(200, sample(path.rsplit("/", 1)[-1]))
            return self.reply(404, {"error": "Not found."})
        except FileNotFoundError:
            self.reply(404, {"error": "Sample or record unavailable. Run the sample preparation scripts, or import local files."})
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.reply(400, {"error": str(error)})

    def archive_get(self):
        store = ArchiveStore(RECORDS)
        url = urlsplit(self.path)
        parts = url.path.strip("/").split("/")
        if len(parts) == 2:
            return self.reply(200, store.catalog())
        record = store.read(parts[2])
        if len(parts) == 3:
            return self.reply(200, store.detail(record))
        if len(parts) == 4 and parts[3] == "export":
            with tempfile.TemporaryFile() as output:
                store.export(parts[2], output)
                size = output.tell()
                output.seek(0)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f'attachment; filename="record-{parts[2]}.zip"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                while chunk := output.read(64 * 1024):
                    self.wfile.write(chunk)
            return
        if len(parts) == 5 and parts[3] == "files":
            item, body = store.file_content(record, parts[4])
            if parse_qs(url.query).get("preview") == ["1"]:
                extension = Path(item["name"]).suffix.lower()
                image_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
                if extension in image_types:
                    return self.reply(200, body, image_types[extension])
                if extension in {".csv", ".tsv", ".txt", ".md", ".json", ".log"}:
                    encoding = "utf-16" if body.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
                    return self.reply(200, {"text": body[:65536].decode(encoding, errors="replace"), "truncated": len(body) > 65536})
                return self.reply(415, {"error": "Preview is unavailable for this format. Download the original to open it in another application."})
            headers = {"Content-Disposition": "attachment; filename=attachment; filename*=UTF-8''" + quote(item["name"], safe="")}
            return self.reply(200, body, "application/octet-stream", headers)
        self.reply(404, {"error": "Not found."})

    def archive_post(self):
        store = ArchiveStore(RECORDS)
        url = urlsplit(self.path)
        parts = url.path.strip("/").split("/")
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if len(parts) == 4 and parts[3] == "files":
                if not 0 <= size <= MAX_FILE:
                    return self.reply(413, {"error": "Each file must be at most 25 MiB."})
                name = parse_qs(url.query).get("name", [""])[0]
                revision = int(self.headers.get("X-Record-Revision", "-1"))
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError("Incomplete upload.")
                with LOCK:
                    result = store.add_file(parts[2], revision, name, body)
                return self.reply(200, result)
            if len(parts) not in {2, 3}:
                return self.reply(404, {"error": "Not found."})
            if not 0 < size <= 100000 or self.headers.get("Content-Type") != "application/json":
                return self.reply(400, {"error": "Expected a bounded JSON metadata request."})
            payload = json.loads(self.rfile.read(size))
            with LOCK:
                result = store.save_metadata(payload, parts[2] if len(parts) == 3 else None)
            return self.reply(200, result)
        except ConflictError as error:
            self.reply(409, {"error": str(error)})
        except FileNotFoundError:
            self.reply(404, {"error": "Record not found."})
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.reply(400, {"error": str(error)})

    def do_POST(self):
        if not self.permitted() or self.headers.get("X-Workbench-Request") != "1":
            return self.reply(403, {"error": "Save from the local workbench."})
        if self.path == "/api/archive" or self.path.startswith("/api/archive/"):
            return self.archive_post()
        if self.path != "/api/records":
            return self.reply(404, {"error": "Not found."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= LIMIT:
                return self.reply(413, {"error": "Review exceeds the 30 MiB save limit."})
            if self.headers.get("Content-Type") != "application/json":
                return self.reply(415, {"error": "Expected JSON."})
            def reject_constant(value):
                raise ValueError(f"Nonfinite JSON value: {value}")
            record = validate_record(json.loads(self.rfile.read(size), parse_constant=reject_constant))
            identity = record.get("id") or uuid.uuid4().hex
            if not isinstance(identity, str) or not ID.fullmatch(identity):
                raise ValueError("Invalid review identifier.")
            with LOCK:
                RECORDS.mkdir(parents=True, exist_ok=True)
                target = RECORDS / (identity + ".json")
                old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
                if record.get("revision", 0) != (old["revision"] if old else 0):
                    return self.reply(409, {"error": "This review changed in another window. Reopen it before saving."})
                # Archive metadata belongs to the shared record, even when this
                # older analysis UI does not include it in its save payload.
                if old:
                    for key in ("attachments", "tags", "createdAt"):
                        if key in old:
                            record[key] = old[key]
                    ArchiveStore(RECORDS).retain_replaced_inputs(old, record)
                record.update(id=identity, revision=(old["revision"] if old else 0) + 1,
                              savedAt=datetime.now(timezone.utc).isoformat())
                temp = target.with_suffix(".tmp")
                temp.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                temp.replace(target)
            self.reply(200, {k: record[k] for k in ("id", "revision", "savedAt")})
        except (ValueError, TypeError, OSError) as error:
            self.reply(400, {"error": str(error)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Analysis Workbench: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
