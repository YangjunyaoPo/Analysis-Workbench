# Analysis Workbench

A local workbench for keeping experimental files, notes, and analysis together.
The current focus is archiving materials and finding them again by date, category,
tags, or filename.

A local archive supports multiple original files per record, editable metadata,
search and date/category filters, previews, original downloads, record ZIP export/import,
and recoverable trash for records and attachments.
The spectrum-review prototype supports CSV/image import, manual calibration,
colored-curve extraction and correction, interval calculations, and saved reviews.
The controlled reference passes the provisional extraction target; the three
researcher-produced Raman examples do not. This is not a scientifically validated tool.

## Run locally

Requires Python 3.10+ and a modern browser. No package installation or frontend
build is needed to run the app.

```powershell
python scripts/serve_prototype.py
```

Open [Experimental records](http://127.0.0.1:8765/archive) to archive and retrieve
materials, or [Spectrum review](http://127.0.0.1:8765/) for the analysis pilot.
The server uses Python's standard library. Import local files or prepare public
samples using the linked evaluation instructions.

Records are stored in `data/prototype-records/`, including original attachments in
its `files/` subdirectory. Back up the whole directory. Research downloads and
saved experimental records are excluded from Git.

## Tests

Python's standard library and Node.js 22+ are sufficient for the automated tests;
they use temporary records and synthetic fixtures, with no research downloads.

```powershell
python -m unittest discover -s tests -p "test_*.py"
node --test tests/core.test.mjs tests/diagnosis.test.mjs tests/archive-filters.test.mjs
```

[GitHub Actions](https://github.com/YangjunyaoPo/Analysis-Workbench/actions/workflows/tests.yml)
runs these checks on Linux and Windows for pushes and pull requests, using Python
3.10 and Node.js 22. Browser module syntax is checked separately. CI does not run
interactive browser tests or download the research datasets.

## Design and current limits

- [Project direction and proposed workflow](docs/project-brief.md)
- [Archive workflow, storage, and verification](docs/archive-workflow.md)
- [Prototype guide, implementation, and measured limits](docs/prototype.md)
- [Sample evaluation, reference calculations, and reproduction](docs/sample-evaluation.md)
- [Current status and verification limits](docs/status.md)
- [Implementation tour and reproducible walkthrough](docs/development.md)

## Development

Changes are committed as working, reviewable increments, with relevant tests and
documentation. This first prototype was developed locally before its initial
code publication; the Git history does not reconstruct those earlier sessions.

AI tools have contributed to research, core implementation, tests, and documentation.
The maintainer sets priorities and acceptance criteria. Recorded agent checks are
separate from maintainer review and user acceptance; pending reviews are listed in
the status document. The application itself has no AI features yet.
