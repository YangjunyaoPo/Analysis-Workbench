# Spectrum Review Prototype

This local prototype reviews a single CSV and image together, with manual
calibration and correction. It is not a validated spectroscopy application.

For the current priority—multi-file archival and retrieval—use `/archive` and the
[Archive workflow](archive-workflow.md). The single-CSV/image limit here applies to
active analysis inputs, not the number of files an archive record can retain.
Archived CSVs and supported images can be selected directly in the archive page.
Changing inputs clears dependent results; the Archive link returns to the same record.

## Run and try it

Python 3.10+ runs the server using only its standard library. The browser uses native
JavaScript modules and Canvas; there is no frontend build or package installation.

```powershell
python scripts/serve_prototype.py
```

Open `http://127.0.0.1:8765/`. Keep the terminal running while using the workbench;
Ctrl+C stops it. The server binds only to loopback. Saved reviews survive restart.

1. Choose **FTIR · controlled reference**, then **Open sample**. Prepare the samples
   using [Sample Evaluation](sample-evaluation.md) if necessary. Alternatively,
   import a CSV with a header and attach an image.
2. Expand **Table columns and preview**, select X/Y columns, and inspect values.
   Units are explicit metadata; unknown units remain unknown.
3. Click **Use sample calibration** for the controlled FTIR image. For another
   image, enter four axis values, choose each **Mark** button, and click its tick.
   The two X positions and two Y positions also bound the extraction rectangle;
   include the desired curve and baseline. For keyboard placement, focus the
   canvas, use arrows (Shift for ten pixels), then Enter.
4. Choose a trace color, optionally sample it from the image, and **Extract curve**.
   Inspect the orange overlay, reference comparison, and broad-column counts.
   **Correct a point** replaces one image column; **Undo** reverses the latest edit.
5. Choose CSV or extracted values, enter an interval, and **Calculate interval**.
   Changing a numerical input or correction clears dependent results.
6. Add notes and **Save review**. The overlay-review checkbox is a user assertion;
   extraction or correction clears it. Saving does not require asserting review.
   Filter records by category, exact experiment date, or unknown date, then reopen.

**Download CSV / image** retrieves attachments; **Export curve CSV** exports the
current extracted/corrected coordinates. CSV import retains original bytes as well
as decoded text, preserving original encoding and newline bytes for download.
The controlled demo CSV is a derived reference, not the original FTIR workbook.
Preserve source attribution when sharing derivatives.

## Implementation and choices

The buildless interface and small Python server keep the workflow and algorithm
inspectable. They do not select the formal product's framework, database, or hosting.

| File | Responsibility |
| --- | --- |
| `prototype/core.mjs` | CSV parsing, coordinate transforms, extraction, integration and reference scoring; no DOM or filesystem access |
| `prototype/app.mjs` | Imports, Canvas overlay, calibration/correction, result invalidation, save/reopen |
| `prototype/index.html`, `style.css` | Labeled working surface and responsive layout |
| `scripts/serve_prototype.py` | Allowlisted routes, local samples, validation, atomic save and revision conflict detection |
| `scripts/evaluate_extraction.mjs` | Runs the same extraction module against local PNGs and numeric references |
| `tests/` | Known-answer numerical/raster tests and isolated HTTP persistence tests |

The browser decodes images into a separate source canvas. Extraction reads only
that canvas, so colored overlays never become analysis input. Four marks define
independent linear mappings:

`x = x1 + (pixelX - pixelX1) * (x2 - x1) / (pixelX2 - pixelX1)`

Y follows the same equation, including its inverted image direction. Descending
physical axes are supported. Outputs use **pixel centers**; confusing centers
with upper-left corners noticeably increases error on steep slopes.

For each image column inside the rectangle, extraction finds pixels within an
RGB-distance tolerance of the selected color and takes their median Y. Missing
columns stay missing. Columns spanning more than eight vertical pixels or containing
separated color runs are reported for inspection. This transparent baseline can
suppress narrow peaks and collapse noisy or overlapping traces.

Integration selects existing samples inside the requested interval, reverses
strictly descending X, and sums trapezoids with compensated summation. It performs
no endpoint interpolation, baseline subtraction, peak fitting, or chemical inference.
Leading/trailing blank columns lie outside the detected trace extent; internal
gaps stop calculation. Nonfinite X and duplicate/unordered coordinates also stop
calculation. Results report actual sampled bounds.

## Persistence

Reviews live in ignored `data/prototype-records/<id>.json`. Snapshots include original
attachments, decoded CSV, metadata, calibration, settings, corrected pixels, review
status, method identifiers, and results. Experiment dates have day precision or are
unknown. The separate UTC `savedAt` timestamp never substitutes for experiment date.
Reopening resets the session undo stack; saved corrected coordinates remain intact.

Writes use a temporary file and replacement under a process lock. Revision numbers
reject stale-window overwrites. This supports one local server process and small
records, not multi-user storage. Back up the record folder to preserve work;
browser storage is not the source of truth. The server checks Host/Origin and a
same-origin write header and never serves arbitrary workspace files.

The archive view uses the same records and keeps new attachments under a separate
`files/` subdirectory. Include that subdirectory in backups. Editing archive metadata
retains analysis state; saving a review with replaced inputs retains its previous
files as attachments. See the archive guide for limits and export behavior.

## Measured results

The development agent ran these checks on 2026-09-11; maintainer acceptance remains
pending. References are linearly interpolated into image space. Eligible columns
lie inside both the reference X range and calibrated Y bounds. Coverage and error
are separate; outside-reference columns are excluded from the reference score.

| Image | Eligible coverage | Median deviation | 95th percentile deviation |
| --- | ---: | ---: | ---: |
| Controlled FTIR | 100% (1187/1187) | 0.193 px | 0.439 px |
| Arcadia acetonitrile, 10,000 ms | 99.81% (516/517) | 1.107 px | 8.159 px |
| Arcadia acetonitrile, 10 ms | 100% (516/516) | 17.016 px | 47.226 px |
| Arcadia dark spectrum | 100% (516/516) | 5.755 px | 30.487 px |

Only the controlled FTIR meets the provisional two-pixel target. It uses known
renderer calibration. Browser clicks at the same marks were also exercised; that
is not a study of human calibration accuracy. Raman mappings were read manually
from ticks and extended to the plot frame. Their errors combine calibration,
potential image/table disagreement, raster information loss, and the extraction
method. Exact researcher PNG/CSV equivalence remains unproven.

The controlled CSV area is `2.3687344624601043`, matching the earlier independent
reference within 1e-10. Image-derived area is `2.3679707948753275`, over slightly
different sampled endpoints. These are raw signal integrals, not chemical accuracy
claims. In the first Raman case, the extracted maximum is about 1.375 versus 1.502
in the CSV: high visible coverage does not guarantee preserved peak height.

Verification covered five pure-function tests, three HTTP tests, actual CSV upload,
four axis clicks, extraction, calculation, correction/undo, date/category filters,
saving/reopening after server restart, and unsupported TIFF archival. Saved CSV/TIFF
bytes matched originals. Desktop (1440 px) and narrow (390 px) layouts were inspected;
the narrow layout had no horizontal overflow. The optional read-only WebMCP summary
tool accepted empty input and rejected unexpected input, using the visible UI state.

```powershell
node --test tests/core.test.mjs
node --test tests/diagnosis.test.mjs
python -m unittest discover -s tests -p "test_*.py"
node scripts/evaluate_extraction.mjs python
node scripts/diagnose_extraction.mjs python
```

The evaluation command needs prepared samples and Python with Pillow; its second
argument can be an absolute Python path. Detailed results go to ignored
`data/evaluation/extraction.json`. Use Node 22+ for the verification runner.

## Follow-up error diagnosis

The maintainer reported no obvious problems with the initial interaction steps.
This is preliminary workflow feedback, not numerical acceptance or a full code review.

The three Raman tables each contain 2,048 samples, while their plotted trace occupies
about 518 image columns. The current column median compresses several measurements
and connecting segments into one value. A numerical diagnostic projects the reference
polyline into each pixel column and computes the midpoint of its occupied vertical
range. This is an idealized diagnostic derived from the CSV, **not** a new image-only
extractor or a replacement acceptance metric.

| Case | Original p95 error | Ideal column-aggregation p95 | Residual against ideal midpoint p95 |
| --- | ---: | ---: | ---: |
| Controlled FTIR | 0.439 px | 0.015 px | 0.438 px |
| Raman, 10,000 ms | 8.159 px | 2.535 px | 5.347 px |
| Raman, 10 ms | 47.226 px | 41.396 px | 23.875 px |
| Dark spectrum | 30.487 px | 18.687 px | 19.322 px |

These quantiles are not additive and do not give percentage attribution. The
diagnostic demonstrates a substantial aggregation effect in the noisy cases.
Remaining differences still mix calibration, rasterization, thresholding, and any
image/table mismatch. Two known-answer checks verify that a straight ramp has no
midpoint bias, while a triangular peak inside one column is suppressed even with
perfect coordinates.

Under the existing calibration, 100%, 100%, and 99.02% of Raman reference vertices
fall within two pixels of matching-color image ink. This supports broad geometric
consistency; dense ink can match different series, so it does not establish exact
pair equivalence. The numerical points were used only for diagnosis and scoring.

Translating the calibration by -1, 0, or +1 pixel in each direction, without choosing
a fitted replacement, leaves Raman p95 errors in ranges 7.159–12.263, 46.368–47.810,
and 28.487–32.058 pixels. Small translation corrections alone therefore did not
resolve these cases. This does not rule out scale errors or other calibration faults.
The controlled FTIR's range is 0.439–5.303 pixels, illustrating why exact-renderer
calibration must not be generalized to ordinary manual clicks.

The diagnostic script writes `data/evaluation/extraction-diagnosis.json`; source
images, the extraction algorithm, original acceptance thresholds, and saved user
reviews are unchanged. The next proposed experiment should preserve per-column
vertical ranges and evaluate peak/trace recovery, retaining the current median as
a baseline. Do not substitute the reference CSV for image-derived answers.

## Limits and next decision

- One CSV and one image per review. The UI expects samples in rows; the wide XLSX
  discovery datasets are not yet supported by the interactive importer.
- PNG/JPEG/WebP/BMP preview depends on browser decoding. TIFF can be archived when
  preview fails. Limits: 12 MiB per attachment, 16 megapixels for extraction,
  30 MiB per serialized review. Save failures preserve the current browser state.
- Only a single colored trace on linear axes. No OCR, logarithmic axes, rotation
  correction, automatic baseline removal, or scientific AI.
- No authentication, remote access, collaboration, or product deployment.
- Maintainer review and a hands-on comparison with a spreadsheet plus
  WebPlotDigitizer remain pending. Before expanding extraction, separate image/table
  mismatch from extraction error and agree handling of narrow/noisy spectra:
  improve extraction, support explicit manual recovery, or limit quantitative use.
