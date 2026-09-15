# Initial Sample Evaluation

Checked: 2026-09-11. This is discovery evidence and a proposed pilot, not an
implemented product or a claim of scientific validation. Downloads, parsing,
calculations, and visual inspection were performed by the development agent;
maintainer review and user workflow validation remain outstanding.

Subsequent work: the local prototype is now implemented.
This page preserves the initial discovery findings; see [Prototype](prototype.md)
for extraction measurements, implemented behavior, and current limits.

## Recommendation

Start with **reviewing one experimental spectrum and preserving the review**:
import a CSV and PNG, inspect columns and units, calibrate the image axes manually,
extract and correct a curve, calculate an interval maximum and trapezoidal area,
then save and retrieve the record by experiment date and material category.

Use researcher-produced Raman plots as realistic candidates, a locally rendered
FTIR curve as a controlled numeric reference, and UV-Vis data for missing-value
handling. These sources do not restrict the eventual product to spectroscopy.
Raw interval area describes the chosen signal; it is not automatically a
baseline-corrected peak area, concentration, or substance identification.

## Acquired materials

| Source | Verified local contents | Evaluation role |
| --- | --- | --- |
| [Arcadia Science DIY Raman](https://github.com/Arcadia-Science/2025-diyraman-bio/tree/05975ad9eb95ba868a61ceb90058d3fedf2eb035) | 33,260,840-byte ZIP; 294 same-stem PNG/CSV pairs; three pairs parsed and images visually inspected | Researcher-produced plots, metadata, signal/background cases |
| [Vegetable-oil FTIR/Raman](https://zenodo.org/records/14651816) | 37,701,525-byte RAR containing four XLSX workbooks | Wide-table import and controlled curve reference |
| [UV-Vis chemical mixtures](https://zenodo.org/records/19324549) | 1,347,250-byte CSV; 846 rows, nine metadata columns and 221 signal columns | Missing values and unknown units |

Both Zenodo downloads matched the depositor's byte count and MD5 checksum.
SHA-256 hashes are recorded locally for all downloaded datasets. Arcadia downloads
are pinned to a Git commit and checked against the hashes observed in this inspection.

### Raman images and tables

Three selected pairs are from 2024-10-11: acetonitrile at 10,000 ms and 10 ms
exposure, plus a dark spectrum at 10,000 ms. Each CSV has 2,048 rows and seven
columns; each PNG is 720 x 432 pixels. The filename metadata is documented by the
source. Preserve date precision as a day; do not invent a time or timezone.

The source plotting script uses `Raman shift (cm-1) adjusted` and
`Intensity (a.u.)`, even though baseline-corrected and filtered columns also exist.
The script was read, not executed. Same-stem pairing and documented plotting columns
provide an evaluation candidate, not proof that every archived image matches the
current table exactly. Pixelwise correspondence remains to be checked.

Images show narrow peaks, background noise, and limited raster resolution. Recovering
all original 2,048 samples from a plot narrower than 2,048 pixels is not a sensible
accuracy requirement. Evaluate the visible curve in image space first, then assess
the uncertainty in derived numerical results.

### Table findings

| Workbook | Spectrum rows | Coordinates per row | Repeated identifiers beyond first occurrence |
| --- | ---: | ---: | ---: |
| FTIR classification | 438 | 7,157 | 4 |
| FTIR quantification | 81 | 7,157 | 1 |
| Raman classification | 144 | 3,001 | 1 |
| Raman quantification | 30 | 3,001 | 0 |

The oil-data page describes CSV files, but the downloaded archive contains XLSX.
FTIR coordinates run approximately 550.095154–4000.122040; Raman coordinates run
200–3200. The associated paper's instrumentation section supplies the cm^-1 unit;
the workbook headers do not explicitly label signal units. There are negative FTIR
values and repeated sample identifiers. Preserve both, and identify records using
source file, sheet, and row rather than deduplicating by sample name.

The UV-Vis signal block contains 4,231 literal `NaN` entries, affecting all 846 rows
and six coordinate columns. No blank cells does **not** mean complete data.
Automatically dropping every affected row would remove the entire dataset.
Coordinates span 200–750 in steps of 2.5, but their units need source confirmation.
Neither Zenodo table set provides an explicit experiment-date field. Publication
and import dates must remain separate from unknown experiment dates.

## Numeric reference already checked

FTIR classification, sheet row 2, sample `AVE1AVC121`, requested interval
1600–1800 cm^-1: 415 points, actually spanning 1600.145260–1799.741561.

- Largest sampled value: 0.0842665 at 1745.262377 cm^-1.
- Trapezoidal area: 2.368734462460104 in raw signal times cm^-1.
- NumPy integration and a separate scalar sum differ by 4.44e-16.

This verifies arithmetic on the selected samples, not the underlying instrument,
chemical interpretation, or image extraction. Endpoints are selected existing
samples; there is no interpolation to exactly 1600 and 1800, baseline correction,
or fitted peak position. The generated PNG is explicitly labeled as a local plot
of published numeric measurements, not an instrument export.

## Proposed acceptance checks

These are provisional engineering targets to agree before implementation, not
measured results or discipline-wide accuracy standards.

1. **Import integrity:** preserve originals and all rows; keep missing values,
   negative signals, duplicate names, and unknown units visible. Record source and
   selected columns. Never silently replace nonfinite values with zero.
2. **Numeric reference:** reproduce the FTIR maximum and area above; absolute area
   error at most 1e-10 on the identical selected input and endpoint convention.
   Missing samples inside an integration interval must require an explicit policy.
3. **Controlled image:** after manual linear-axis calibration, recover at least
   95% of eligible plot columns; 95th-percentile vertical deviation at most two
   pixels against the projected reference curve. Define eligible columns, plot
   bounds, interpolation, and handling of gaps before scoring. Report calibration
   error separately. A narrow peak may need a stricter downstream criterion.
4. **Research images:** first verify each PNG/CSV relationship and axis mapping.
   Report coverage and errors for each selected image, including noisy examples.
   Do not extend controlled-chart results to arbitrary spectra or scientific use.
5. **Review and persistence:** show an extraction overlay and allow corrections;
   save calibration, selected interval, method, parameters, and notes. Reopening
   must preserve the result. Unsupported images stay attached with a clear status.
   Retrieve by category and known experiment date, with a visible unknown-date group.

The first usability comparison should use a spreadsheet plus
[WebPlotDigitizer](https://www.automeris.io/docs/digitize/). Its documented calibration
and extraction workflow is an existing baseline; no hands-on comparison or product
advantage has yet been demonstrated. Evaluate whether keeping files, corrections,
analysis settings, and records together reduces repeated work.

## Provenance and reuse

- Zenodo depositors declare CC BY 4.0 for both datasets. Retain creator, source,
  license link, and modifications with any redistributed derivatives. The FTIR
  fixture JSON records these fields.
- Arcadia's repository LICENSE is MIT, while its README describes that license as
  applying to code. The [associated publication](https://thestacks.org/publications/resource-diy-raman-bio)
  displays CC BY 4.0. Separate coverage for the repository's data and PNG files has
  not been established here; they remain local evaluation inputs rather than
  bundled project assets.
- The [oil study manuscript](https://pure.qub.ac.uk/en/publications/chemometric-classification-and-quantification-of-olive-oil-in-ble/)
  has different reuse terms from its dataset. Direct manuscript downloads returned
  HTTP 403; no local manuscript images were acquired.
- [OMLC PhotochemCAD](https://omlc.org/spectra/PhotochemCAD/html/001.html) remains a
  secondary candidate. Its original and transformed numeric exports differ;
  redistribution terms and a usable static spectral image remain unverified.

## Reproduction

From the repository root, in an analysis environment with Python, NumPy, openpyxl,
ReportLab, pypdfium2, Pillow, and a `tar` supporting RAR reads:

```powershell
python scripts/inspect_samples.py
python scripts/analyze_sample_tables.py
python scripts/inspect_arcadia_samples.py
```

Verified library versions: NumPy 2.3.5, openpyxl 3.1.5, ReportLab 4.4.9,
pypdfium2 5.13.0. This is an exploratory environment, not an application dependency
lock. Network access is required for downloads; existing verified files are reused.
The table-analysis script can run offline after the Zenodo acquisition step.

Outputs live under ignored `data/initial-samples/`: source metadata and checksums,
`table-analysis.json`, `controlled-fixtures/ftir-reference.{json,png}`, and
`arcadia/inspection.json` with three selected PNG/CSV pairs. Original spreadsheets
are read without modification. At this initial discovery checkpoint, no application
or extraction implementation existed. The subsequent prototype and its measurements
are documented in [Prototype](prototype.md); user acceptance and deployment remain open.
