"""Fetch a pinned public archive and inspect three researcher-produced CSV/PNG pairs.

External analysis code is saved for reading only, never imported or executed.
Requires numpy and Pillow; all acquired materials remain in ignored data/.
"""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image

from inspect_samples import fetch


COMMIT = "05975ad9eb95ba868a61ceb90058d3fedf2eb035"
BASE = f"https://raw.githubusercontent.com/Arcadia-Science/2025-diyraman-bio/{COMMIT}/"
OUTPUT = Path(__file__).resolve().parents[1] / "data/initial-samples/arcadia"
FILES = {
    "README.md": "b1f25406ddb4af4610abdab7c4d9cb95f2cba810fda12efd8fd79b431369213c",
    "LICENSE": "e693da7b953434d5f2b2306fdef8e8aae861a02a934e2d5987449e84cfc85c72",
    "scripts/apply_calibration.py": "558b82b04340eba90d59cfd479a2c52c113391ee5c30ba0bf47c71ad726a030a",
    "data/processed.zip": "9132eb64087f9de83bb4d25eebbfd4d3f3c724e3aa5a7ec6ebbf07f63e0354f1",
}
SAMPLES = (
    "2024-10-11_acetonitrileinquartzcuvette_n_n_n_solid_10000_0_5",
    "2024-10-11_acetonitrileinquartzcuvette_n_n_n_solid_10_0_5",
    "2024-10-11_darkspectrum_n_n_n_solid_10000_0_5",
)
X_COLUMN = "Raman shift (cm-1) adjusted"
Y_COLUMN = "Intensity (a.u.)"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": COMMIT,
        "source_repository": "https://github.com/Arcadia-Science/2025-diyraman-bio",
        "license_scope": "Repository LICENSE is MIT; README describes it as code license. Separate dataset/image terms not confirmed.",
        "files": [], "samples": [],
    }
    for name, expected in FILES.items():
        path = OUTPUT / Path(name).name
        cached = path.exists()
        body = path.read_bytes() if cached else fetch(BASE + name)[0]
        digest = hashlib.sha256(body).hexdigest()
        if digest != expected:
            raise ValueError(f"SHA-256 differs from inspected revision: {name}")
        if not cached:
            path.write_bytes(body)
        manifest["files"].append({"url": BASE + name, "bytes": len(body), "sha256": digest})
    with zipfile.ZipFile(OUTPUT / "processed.zip") as archive:
        names = {n for n in archive.namelist() if not n.startswith("__MACOSX/")}
        pairs = sorted(n for n in names if n.endswith(".png") and n[:-4] + ".csv" in names)
        manifest["same_stem_png_csv_pairs"] = len(pairs)
        selected = OUTPUT / "selected"
        selected.mkdir(exist_ok=True)
        for stem in SAMPLES:
            member = f"processed/processed_data/2024-10-11/{stem}"
            hashes = {}
            for suffix in (".csv", ".png"):
                body = archive.read(member + suffix)
                (selected / (stem + suffix)).write_bytes(body)
                hashes[suffix] = hashlib.sha256(body).hexdigest()
            body = archive.read(member + ".csv")
            reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
            rows = list(reader)
            x = np.array([float(r[X_COLUMN]) for r in rows])
            y = np.array([float(r[Y_COLUMN]) for r in rows])
            with Image.open(selected / (stem + ".png")) as picture:
                dimensions = picture.size
                picture.verify()
            mask = (x >= 2800) & (x <= 3100)
            bx, by = x[mask], y[mask]
            index = int(np.argmax(by))
            manifest["samples"].append({
                "archive_stem": member, "hashes": hashes, "rows": len(rows),
                "columns": reader.fieldnames, "image_size": dimensions,
                "x_column": X_COLUMN, "y_column": Y_COLUMN,
                "pairing_basis": "Same archive stem; plotting columns identified from source script. Pixelwise agreement not yet evaluated.",
                "x_range": [float(x.min()), float(x.max())],
                "y_range": [float(y.min()), float(y.max())],
                "nonfinite_xy_values": int((~np.isfinite(x)).sum() + (~np.isfinite(y)).sum()),
                "date_from_filename": "2024-10-11", "date_precision": "day",
                "reference_band": {
                    "requested_bounds": [2800, 3100], "sampled_bounds": [float(bx[0]), float(bx[-1])],
                    "sample_count": len(bx), "maximum_coordinate": float(bx[index]),
                    "maximum_value": float(by[index]), "raw_trapezoidal_area": float(np.trapezoid(by, bx)),
                    "note": "Raw intensity area; not baseline-corrected peak area or concentration.",
                },
            })
    (OUTPUT / "inspection.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
