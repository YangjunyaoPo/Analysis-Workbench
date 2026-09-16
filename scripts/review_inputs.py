"""Choose archived originals as active review inputs and invalidate dependents."""
import base64
import copy
import csv
import io
import json
from pathlib import Path

if __package__:
    from .archive_store import now
else:
    from archive_store import now

REVIEW_FILE_LIMIT = 12 * 1024 * 1024
REVIEW_SNAPSHOT_LIMIT = 30 * 1024 * 1024
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".bmp": "image/bmp"}


def csv_text(body):
    encoding = "utf-16" if body.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        text = body.decode(encoding)
        rows = csv.reader(io.StringIO(text), strict=True)
        header = next(rows, [])
        if len(header) < 2:
            raise ValueError("The analysis CSV needs a header with at least two columns.")
        for row in rows:
            if row and len(row) != len(header):
                raise ValueError("CSV rows must have the same number of columns as the header.")
        return text
    except (UnicodeError, csv.Error) as error:
        raise ValueError("Use a valid UTF-8 CSV or BOM-marked UTF-16 CSV for analysis. The original remains archived.") from error


def choose_input(store, identity, revision, kind, file_id):
    if kind not in {"csv", "image"}:
        raise ValueError("Choose a CSV or image analysis input.")
    if file_id is not None and not isinstance(file_id, str):
        raise ValueError("Invalid attachment identifier.")
    old = store.read(identity)
    store.check_revision(old, revision)
    store.require_active(old)
    materials = store.materials(old)
    current = next((item for item in materials if item.get("usedBy") == kind), None)
    if (current["id"] if current else None) == file_id:
        return store.detail(old)
    selected = None
    if file_id is not None:
        selected = next((item for item in materials if item["id"] == file_id), None)
        if selected is None:
            raise ValueError("Choose an active file from this record. Restore trashed files first.")
        if selected["size"] > REVIEW_FILE_LIMIT:
            raise ValueError("Analysis inputs must be at most 12 MiB. The original remains archived.")
        extension = Path(selected["name"]).suffix.lower()
        if (kind == "csv" and extension != ".csv") or (kind == "image" and extension not in IMAGE_TYPES):
            raise ValueError("Analysis supports CSV and PNG/JPEG/WebP/BMP images. Other formats remain archived.")
        _, body = store.file_content(old, file_id)
        text = csv_text(body) if kind == "csv" else None

    record = copy.deepcopy(old)
    assets = record.setdefault("assets", {})
    for key in (kind + "Name", kind + "Data", kind + "AttachmentId"):
        assets.pop(key, None)
    if kind == "csv":
        assets.pop("csvText", None)
    if selected:
        media_type = "text/csv" if kind == "csv" else IMAGE_TYPES[extension]
        assets.update({kind + "Name": selected["name"], kind + "AttachmentId": file_id,
                       kind + "Data": f"data:{media_type};base64," + base64.b64encode(body).decode("ascii")})
        if kind == "csv":
            assets["csvText"] = text
    assets["provenance"] = "Inputs selected from archived materials. Check file pairing, units, and experimental context."
    assets.pop("source", None)
    settings = record.setdefault("settings", {})
    record.update(result=None, comparison=None, reviewed=False)
    if kind == "csv":
        settings.update(xi="0", yi="1", xUnit="", yUnit="")
    else:
        record.update(calibration={}, sampleCalibration=None, extraction=None)
    store.retain_replaced_inputs(old, record)
    record.update(revision=record["revision"] + 1, savedAt=now())
    if len(json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")) > REVIEW_SNAPSHOT_LIMIT:
        raise ValueError("These inputs exceed the 30 MiB review snapshot limit. Choose smaller analysis inputs.")
    store.write(record)
    return store.detail(record)
