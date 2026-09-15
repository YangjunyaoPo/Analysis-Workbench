"""Validate a workbench ZIP before publishing a new local record.

ZIP member names are lookup keys only; no member is extracted to a filesystem path.
Original files are written by verified content hash, then one atomic record write
makes the imported copy visible. Existing records are never overwritten.
"""
import hashlib
import json
from pathlib import PurePosixPath
import stat
import uuid
import zipfile

if __package__:
    from .archive_store import HASH, IDENTIFIER, MAX_FILE, MAX_RECORD_BYTES, MAX_RECORD_FILES, metadata, now
else:
    from archive_store import HASH, IDENTIFIER, MAX_FILE, MAX_RECORD_BYTES, MAX_RECORD_FILES, metadata, now

MAX_PACKAGE = 150 * 1024 * 1024
MAX_SNAPSHOT = 30 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property in archive package.")
        result[key] = value
    return result


def load_json(body):
    def reject(value):
        raise ValueError("Nonfinite JSON values are not supported.")
    try:
        return json.loads(body, object_pairs_hook=object_pairs, parse_constant=reject)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Invalid JSON in archive package.") from error


def validate_snapshot(record):
    if not isinstance(record, dict) or type(record.get("schema")) is not int or record["schema"] != 1:
        raise ValueError("Unsupported record format.")
    if not isinstance(record.get("id"), str) or not IDENTIFIER.fullmatch(record["id"]):
        raise ValueError("Invalid source record identifier.")
    record.update(metadata(record))
    if type(record.get("revision")) is not int or record["revision"] < 1:
        raise ValueError("Invalid source revision.")
    for key in ("assets", "settings", "calibration"):
        if not isinstance(record.get(key, {}), dict):
            raise ValueError(f"Invalid {key} in record snapshot.")
        record.setdefault(key, {})
    for key in ("extraction", "result", "comparison", "sampleCalibration"):
        if record.get(key) is not None and not isinstance(record[key], dict):
            raise ValueError(f"Invalid {key} in record snapshot.")
    for key, value in record["assets"].items():
        if not isinstance(value, str):
            raise ValueError("Analysis asset fields must be text.")
        if key in {"csvData", "imageData"} and value and not value.startswith("data:"):
            raise ValueError("Analysis inputs must be embedded original bytes.")
    attachments = record.setdefault("attachments", [])
    if not isinstance(attachments, list) or len(attachments) > MAX_RECORD_FILES:
        raise ValueError("Invalid attachment list.")
    for item in attachments:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not IDENTIFIER.fullmatch(item["id"]):
            raise ValueError("Invalid attachment identifier.")
        if item.get("legacy"):
            raise ValueError("Stored attachments cannot impersonate inline inputs.")
    # Default only fields absent from older review snapshots.
    defaults = {"xi": "0", "yi": "1", "xUnit": "", "yUnit": "", "color": "#1261a0",
                "tolerance": 80, "source": "table", "lo": "0", "hi": "1"}
    for key, value in defaults.items():
        record["settings"].setdefault(key, value)


def import_package(store, source):
    """Import one exported record as an independent copy after complete validation."""
    try:
        return _import_package(store, source)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid or unsupported archive package.") from error


def _import_package(store, source):
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > MAX_RECORD_FILES + 2 or len(names) != len(set(names)):
            raise ValueError("Too many or duplicate ZIP entries.")
        if sum(item.file_size for item in entries) > MAX_RECORD_BYTES + MAX_SNAPSHOT + MAX_MANIFEST:
            raise ValueError("Archive expands beyond the supported size.")
        for item in entries:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename or ":" in item.filename
                    or item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1
                    or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                raise ValueError("Unsupported ZIP entry or path.")
            limit = MAX_SNAPSHOT if item.filename == "record.json" else MAX_MANIFEST if item.filename == "manifest.json" else MAX_FILE
            if item.file_size > limit:
                raise ValueError("An archive entry exceeds its size limit.")
        if not {"record.json", "manifest.json"}.issubset(names):
            raise ValueError("Expected a workbench ZIP with record.json and manifest.json.")
        record = load_json(archive.read("record.json"))
        manifest = load_json(archive.read("manifest.json"))
        validate_snapshot(record)
        if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("recordId") != record["id"]:
            raise ValueError("Manifest and record do not match.")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > MAX_RECORD_FILES:
            raise ValueError("Invalid manifest files.")
        expected = store.materials(record, include_deleted=True)
        by_id = {item["id"]: item for item in expected}
        if len(by_id) != len(expected) or len(files) != len(expected):
            raise ValueError("Attachment identities do not match the manifest.")
        payloads, seen_ids, used_paths = [], set(), {"record.json", "manifest.json"}
        for item in files:
            if not isinstance(item, dict) or item.get("id") not in by_id or item["id"] in seen_ids:
                raise ValueError("Unknown or duplicate manifest attachment.")
            descriptor = by_id[item["id"]]
            for key in ("name", "size", "sha256", "originalBytesAvailable", "deletedAt"):
                if item.get(key) != descriptor.get(key):
                    raise ValueError("Attachment metadata differs from its manifest.")
            name, size, digest = item["name"], item["size"], item["sha256"]
            if not isinstance(name, str) or not name or len(name) > 255 or any(c in name for c in '/\\') or any(ord(c) < 32 for c in name):
                raise ValueError("Invalid original filename.")
            if type(size) is not int or not 0 <= size <= MAX_FILE or not isinstance(digest, str) or not HASH.fullmatch(digest):
                raise ValueError("Invalid attachment size or hash.")
            path = item.get("path")
            if not isinstance(path, str) or not path.startswith("files/") or path in used_paths or path not in names:
                raise ValueError("Invalid attachment path in manifest.")
            if archive.getinfo(path).file_size != size:
                raise ValueError("Attachment size does not match its manifest.")
            body = archive.read(path)
            if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
                raise ValueError("Attachment integrity check failed.")
            if descriptor.get("legacy") and body != store.legacy_bytes(record, item["id"]):
                raise ValueError("Inline analysis input differs from the exported original.")
            payloads.append((descriptor, body))
            seen_ids.add(item["id"])
            used_paths.add(path)
        if used_paths != set(names) or sum(len(body) for _, body in payloads) > MAX_RECORD_BYTES:
            raise ValueError("Unexpected ZIP contents or total attachment size.")

    imported_at = now()
    record["importedFrom"] = {key: record.get(key) for key in ("id", "revision", "createdAt", "savedAt", "deletedAt")}
    record["importedFrom"]["importedAt"] = imported_at
    record.update(id=uuid.uuid4().hex, revision=1, createdAt=imported_at, savedAt=imported_at, deletedAt=None)
    # All structure, identities, and bytes are checked before any persistent write.
    for descriptor, body in payloads:
        if not descriptor.get("legacy"):
            store.store_file(descriptor["name"], body, descriptor.get("originalBytesAvailable", True))
    store.write(record)
    return store.detail(record)
