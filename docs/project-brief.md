# Project scope

Updated: 2026-09-15.

Analysis Workbench keeps experimental tables, images, notes, and processing results
together. Records should be easy to find by experiment date and material category.
Quantitative curve extraction and mathematical analysis are part of the product
direction; reliable support for particular instruments still needs to be established.

## Current priority

Complete the archive workflow: create a record, attach original materials, describe
the experiment, find it again, and preview or export its files. Analysis is optional
when recording an experiment. See [Archive workflow](archive-workflow.md) for the
implementation, storage choices, and limits.

The working assumption is that keeping these materials together will reduce repeated
file handling. That benefit still needs to be checked through actual use.

## Requirements

- Preserve original tables and images, including images the application cannot interpret.
- Keep experiment dates distinct from import and save times; allow unknown dates.
- Support organization, mathematical processing, and inspectable results.
- Recognize quantifiable instrument curves and spectra within a defined, tested scope.
- Keep inputs, parameters, corrections, and results associated with the same record.
- Later, consider AI assistance for management and interpretation.

Traceability supports these tasks. Tracking changes to external sources is not the
main workflow, and the project should not depend on building a large reference
library by hand unless a specific analysis task requires it.

## Analysis pilot

The [spectrum prototype](prototype.md) pairs one active CSV with one image. It uses
manual linear-axis calibration, colored-curve extraction, point correction, interval
maximum and trapezoidal area calculations. An unsupported image can still be archived.

Public samples provide early test cases without requiring private experiment data:

- Vegetable-oil FTIR/Raman workbooks provide numeric measurements and a locally
  rendered FTIR reference chart.
- Arcadia Science Raman PNG/CSV pairs test researcher-produced plots.
- UV-Vis mixture data exposes missing-value handling requirements.

See [Sample evaluation](sample-evaluation.md) for source links, reuse terms,
acquisition scripts, and measured findings. Spectroscopy is an initial evaluation
case, not a commitment to one discipline. The controlled FTIR result has not
generalized to the three tested Raman images.

## Decisions still open

- Which user and experimental task should guide the first release?
- Which table/image formats and measurement methods need full processing support?
- What image quality, calibration effort, and numerical tolerances are acceptable?
- Does actual usage justify indexed storage, a larger application framework, or collaboration?
- What code license should apply? Which research materials can be redistributed?

The current implementation uses a small loopback-only Python server and browser
modules. Keep storage, processing, and presentation responsibilities separate, and
expand the architecture when the working requirements call for it.
