"""Download and inspect two fixed research candidates, without modifying source data.

Uses only Python's standard library. Downloads and metadata stay under ignored data/.
This is a discovery utility, not a commitment to the application's technology stack.
"""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "initial-samples"
RECORDS = ("19324549", "14651816")
MAX_BYTES = 50_000_000


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Analysis-Workbench-sample-evaluation/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError(f"Download exceeds {MAX_BYTES} bytes: {url}")
        return body, response.status, response.geturl()


def inspect_csv(body):
    text = body.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    widths = sorted(set(map(len, rows)))
    return {
        "row_count_including_header": len(rows),
        "row_widths": widths,
        "first_rows_first_columns": [row[:16] for row in rows[:5]],
        "first_row_last_columns": rows[0][-10:] if rows else [],
        "blank_cells": sum(value.strip() == "" for row in rows for value in row),
        "identical_rows_beyond_first_occurrence": len(rows) - len(set(map(tuple, rows))),
        "note": "Structural inspection only; no missing-value replacement or unit inference.",
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for record_id in RECORDS:
        folder = OUTPUT / record_id
        folder.mkdir(exist_ok=True)
        metadata_url = f"https://zenodo.org/api/records/{record_id}"
        metadata_bytes, status, resolved_url = fetch(metadata_url)
        metadata = json.loads(metadata_bytes)
        (folder / "record.json").write_bytes(metadata_bytes)
        result = {
            "record_id": record_id,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata_url": metadata_url,
            "metadata_http_status": status,
            "resolved_metadata_url": resolved_url,
            "title": metadata["metadata"]["title"],
            "creators": metadata["metadata"].get("creators"),
            "license_as_declared_by_depositor": metadata["metadata"].get("license"),
            "description": metadata["metadata"].get("description"),
            "files": [],
        }
        for entry in metadata["files"]:
            name = entry["key"]
            if "/" in name or "\\" in name or name in (".", ".."):
                raise ValueError(f"Unexpected filename: {name}")
            if entry["size"] > MAX_BYTES:
                raise ValueError(f"File too large for this evaluation: {name}")
            target = folder / name
            algorithm, expected_hash = entry["checksum"].split(":", 1)
            if algorithm != "md5":
                raise ValueError(f"Unexpected checksum algorithm: {algorithm}")
            cached = target.exists()
            if cached:
                body = target.read_bytes()
                download_status = None
                resolved_download = None
            else:
                print(f"Downloading {record_id}/{name} ({entry['size']} bytes)", flush=True)
                body, download_status, resolved_download = fetch(entry["links"]["self"])
            digest = hashlib.md5(body).hexdigest()
            if digest != expected_hash or len(body) != entry["size"]:
                raise ValueError(f"Published size/checksum mismatch: {name}")
            if not cached:
                target.write_bytes(body)
            item = {
                "name": name,
                "download_url": entry["links"]["self"],
                "download_http_status": download_status,
                "resolved_download_url": resolved_download,
                "cached": cached,
                "bytes": len(body),
                "md5": digest,
                "published_checksum_matches": True,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            if name.lower().endswith(".csv"):
                item["csv"] = inspect_csv(body)
            elif name.lower().endswith(".rar"):
                completed = subprocess.run(
                    ["tar", "-tf", str(target)], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30, check=True,
                )
                members = completed.stdout.splitlines()
                (folder / "archive-members.json").write_text(json.dumps(members, indent=2), encoding="utf-8")
                item["archive_member_count"] = len(members)
                item["archive_first_members"] = members[:15]
                item["archive_extensions"] = sorted(set(Path(n).suffix.lower() for n in members))
            result["files"].append(item)
        (folder / "inspection.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(result)
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    (OUTPUT / "inspection.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
