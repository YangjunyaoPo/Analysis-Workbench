"""Local archive operations; original bytes are separate from review snapshots."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import uuid
import zipfile

IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE = 25 * 1024 * 1024
MAX_RECORD_FILES = 100
MAX_RECORD_BYTES = 100 * 1024 * 1024


class ConflictError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def file_kind(name):
    extension = Path(name).suffix.lower()
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg"}:
        return "image"
    if extension in {".csv", ".tsv", ".xls", ".xlsx", ".ods"}:
        return "table"
    if extension in {".txt", ".md", ".json", ".log"}:
        return "text"
    if extension in {".pdf", ".doc", ".docx"}:
        return "document"
    return "other"


def metadata(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected record metadata.")
    result = {}
    for key, limit in (("title", 500), ("category", 100), ("notes", 20000)):
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Invalid {key}.")
        result[key] = value.strip() if key != "notes" else value
    if not result["title"]:
        raise ValueError("Give the record a title.")
    date = payload.get("date", "")
    if not isinstance(date, str):
        raise ValueError("Invalid experiment date.")
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("Use YYYY-MM-DD for the experiment date.")
        datetime.strptime(date, "%Y-%m-%d")
    result["date"] = date
    tags = payload.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 60 for t in tags):
        raise ValueError("Use at most 20 tags, each at most 60 characters.")
    result["tags"] = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    return result


class ArchiveStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.files = self.folder / "files"

    def read(self, identity):
        if not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity):
            raise ValueError("Invalid record identifier.")
        record = json.loads((self.folder / (identity + ".json")).read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("schema") != 1 or record.get("id") != identity:
            raise ValueError("Unsupported record format.")
        return record

    def write(self, record):
        self.folder.mkdir(parents=True, exist_ok=True)
        destination = self.folder / (record["id"] + ".json")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(destination)

    @staticmethod
    def check_revision(record, expected):
        if not isinstance(expected, int) or isinstance(expected, bool) or expected != record.get("revision", 0):
            raise ConflictError("This record changed in another window. Reopen it before editing.")

    @staticmethod
    def require_active(record):
        if record.get("deletedAt"):
            raise ConflictError("This record is in trash. Restore it before editing.")

    def set_trashed(self, identity, expected_revision, trashed, file_id=None):
        record = self.read(identity)
        self.check_revision(record, expected_revision)
        target = record
        if file_id is not None:
            self.require_active(record)
            item = next((m for m in self.materials(record, include_deleted=True) if m["id"] == file_id), None)
            if item is None:
                raise FileNotFoundError("Attachment not found.")
            if item.get("usedBy"):
                raise ValueError("This file is an analysis input. Detach or replace it before moving it to trash.")
            target = next(a for a in record["attachments"] if a["id"] == file_id)
        if bool(target.get("deletedAt")) == trashed:
            return self.detail(record)
        target["deletedAt"] = now() if trashed else None
        record.update(revision=record["revision"] + 1, savedAt=now())
        self.write(record)
        return self.detail(record)

    def save_metadata(self, payload, identity=None):
        values = metadata(payload)
        if identity:
            record = self.read(identity)
            self.check_revision(record, payload.get("revision"))
            self.require_active(record)
        else:
            record = {"schema": 1, "id": uuid.uuid4().hex, "revision": 0, "createdAt": now(),
                      "assets": {}, "attachments": [], "calibration": {}, "sampleCalibration": None,
                      "extraction": None, "result": None, "comparison": None, "reviewed": False,
                      "settings": {"xi": "0", "yi": "1", "xUnit": "", "yUnit": "", "color": "#1261a0",
                                   "tolerance": 80, "source": "table", "lo": "0", "hi": "1"}}
        record.update(values)
        record.update(revision=record["revision"] + 1, savedAt=now())
        self.write(record)
        return self.detail(record)

    @staticmethod
    def legacy_bytes(record, identity):
        assets = record.get("assets", {})
        def decode(value):
            if not isinstance(value, str) or ";base64," not in value:
                raise ValueError("Invalid stored attachment encoding.")
            return base64.b64decode(value.split(",", 1)[1], validate=True)
        if identity == "legacy-csv":
            if assets.get("csvData"):
                return decode(assets["csvData"])
            return assets["csvText"].encode("utf-8")
        if identity == "legacy-image":
            return decode(assets["imageData"])
        raise ValueError("Unknown legacy attachment.")

    def materials(self, record, include_deleted=False):
        materials = [dict(item) for item in record.get("attachments", []) if include_deleted or not item.get("deletedAt")]
        assets = record.get("assets", {})
        for kind, name_key, content_key in (("csv", "csvName", "csvText"), ("image", "imageName", "imageData")):
            if not assets.get(content_key):
                continue
            identity = "legacy-" + kind
            body = self.legacy_bytes(record, identity)
            name = assets.get(name_key) or ("reference.csv" if kind == "csv" else "image.png")
            digest = hashlib.sha256(body).hexdigest()
            linked = next((m for m in materials if m["id"] == assets.get(kind + "AttachmentId")
                           and m["sha256"] == digest and not m.get("deletedAt")), None)
            if linked:
                linked["usedBy"] = kind
                continue
            materials.insert(0, {"id": identity, "name": name, "size": len(body),
                                 "sha256": digest, "kind": file_kind(name), "usedBy": kind,
                                 "mediaType": mimetypes.guess_type(name)[0] or "application/octet-stream",
                                 "addedAt": None, "legacy": True,
                                 "originalBytesAvailable": kind != "csv" or bool(assets.get("csvData"))})
        return materials

    def detail(self, record):
        result = {key: record.get(key) for key in ("id", "title", "date", "category", "notes", "revision", "savedAt", "createdAt", "deletedAt")}
        result.update(tags=record.get("tags", []), materials=self.materials(record),
                      trashedMaterials=[m for m in self.materials(record, include_deleted=True) if m.get("deletedAt")],
                      hasAnalysis=bool(record.get("extraction") or record.get("result")),
                      hasReviewInputs=bool(record.get("assets", {}).get("csvText") or record.get("assets", {}).get("imageData")))
        return result

    def catalog(self, trashed=False):
        records, errors = [], []
        for path in self.folder.glob("*.json"):
            try:
                record = self.read(path.stem)
                if bool(record.get("deletedAt")) == trashed:
                    records.append(self.detail(record))
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append({"record": path.stem, "error": str(error)})
        records.sort(key=lambda r: r.get("savedAt") or "", reverse=True)
        return {"records": records, "errors": errors}

    def add_file(self, identity, expected_revision, name, body):
        if not isinstance(name, str) or not name or len(name) > 255 or name in {".", ".."} or any(c in name for c in '/\\') or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid filename.")
        if len(body) > MAX_FILE:
            raise ValueError("Each file must be at most 25 MiB.")
        record = self.read(identity)
        self.check_revision(record, expected_revision)
        self.require_active(record)
        existing = self.materials(record, include_deleted=True)
        digest = hashlib.sha256(body).hexdigest()
        duplicate = next((item for item in existing if item["sha256"] == digest and item["name"] == name), None)
        if duplicate and duplicate.get("deletedAt"):
            raise ConflictError("This identical file is in trash. Restore it from the record's trashed files.")
        if duplicate:
            return {"record": self.detail(record), "duplicate": True}
        if len(existing) >= MAX_RECORD_FILES or sum(item["size"] for item in existing) + len(body) > MAX_RECORD_BYTES:
            raise ValueError("A record can hold at most 100 files and 100 MiB of attachments.")
        attachment = self.store_file(name, body)
        record.setdefault("attachments", []).append(attachment)
        record.update(revision=record["revision"] + 1, savedAt=now())
        self.write(record)
        return {"record": self.detail(record), "duplicate": False}

    def store_file(self, name, body, original=True):
        """Write immutable bytes before the caller atomically updates its record."""
        digest = hashlib.sha256(body).hexdigest()
        self.files.mkdir(parents=True, exist_ok=True)
        path = self.files / (digest + ".bin")
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("An existing stored file failed its integrity check.")
        else:
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(body)
            temporary.replace(path)
        return {"id": uuid.uuid4().hex, "name": name, "sha256": digest, "size": len(body),
                      "kind": file_kind(name), "mediaType": mimetypes.guess_type(name)[0] or "application/octet-stream",
                      "addedAt": now(), "originalBytesAvailable": original}

    def retain_replaced_inputs(self, old, incoming):
        """An explicit analysis save may replace inputs, but must retain old files."""
        materials = self.materials(incoming, include_deleted=True)
        for item in self.materials(old):
            if not item.get("legacy") or any(m["name"] == item["name"] and m["sha256"] == item["sha256"] for m in materials):
                continue
            if len(materials) >= MAX_RECORD_FILES or sum(m["size"] for m in materials) + item["size"] > MAX_RECORD_BYTES:
                raise ValueError("Preserving the previous inputs would exceed this record's attachment limit. Save as a new record instead.")
            stored = self.store_file(item["name"], self.legacy_bytes(old, item["id"]), item["originalBytesAvailable"])
            incoming.setdefault("attachments", []).append(stored)
            materials.append(stored)

    def file_content(self, record, file_id):
        item = next((m for m in self.materials(record, include_deleted=True) if m["id"] == file_id), None)
        if item is None:
            raise FileNotFoundError("Attachment not found.")
        if item.get("legacy"):
            body = self.legacy_bytes(record, file_id)
        else:
            if not HASH.fullmatch(item["sha256"]):
                raise ValueError("Invalid stored file hash.")
            body = (self.files / (item["sha256"] + ".bin")).read_bytes()
        if len(body) != item["size"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
            raise ValueError("Attachment integrity check failed.")
        return item, body

    def export(self, identity, destination):
        record = self.read(identity)
        materials = self.materials(record, include_deleted=True)
        manifest = []
        # Preserve a complete snapshot for recovery, including old analysis inputs.
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("record.json", json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2))
            for index, item in enumerate(materials, start=1):
                _, body = self.file_content(record, item["id"])
                safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item["name"]).strip(" .") or "attachment"
                path = f"files/{index:03d}_{safe_name}"
                archive.writestr(path, body)
                manifest.append({**item, "path": path})
            archive.writestr("manifest.json", json.dumps({"schema": 1, "recordId": identity, "files": manifest}, ensure_ascii=False, indent=2))
