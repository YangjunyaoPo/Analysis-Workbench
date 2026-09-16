# Archive and Retrieval Workflow

Archive experimental materials independently of analysis, then make them easy to
retrieve. The existing local server is sufficient for this workflow; larger storage
or framework changes should follow actual usage needs.

## First slice

Create and save a record with title, optional experiment date, category, tags and notes →
attach multiple original files → search/filter records → reopen
and preview or download materials. Analysis remains an optional activity.

- Experiment date may be unknown. File-added and saved timestamps are distinct.
- Preserve same-named files with different bytes; identify file content by SHA-256.
- Store new original files separately from record metadata and analysis snapshots.
- Read existing spectrum reviews without migrating or rewriting them automatically.
- Metadata edits must preserve existing analysis settings, corrections, and results.
- Images and bounded text previews are supported; other formats remain downloadable.
- Search title, notes, category, tags and filenames; filter by date range and file kind.
- Reject stale edits rather than overwriting changes from another window.

## Acceptance

Verify multi-file upload, original-byte downloads, repeated names, search/filtering,
unknown dates, metadata updates, reopening, and existing-review compatibility.
File or record write failures must not claim success or discard previously saved work.
Provide a record export containing originals and metadata, with a manifest of hashes.

## Use the local archive

Run `python scripts/serve_prototype.py` and open `http://127.0.0.1:8765/archive`.
Choose **New record**, enter a title, and **Save record**. An unknown experiment date
can stay blank. **Add files** accepts multiple files and saves them sequentially.
If an upload fails, earlier successful files stay saved; the message identifies the
failure and stops the remaining uploads. Repeating an identical same-name file is
a no-op. Different bytes with the same filename remain separate attachments.

Search matches all entered words across title, category, notes, tags, and filenames;
it does not search file contents or run OCR. Combine it with category, file kind,
inclusive experiment-date ranges, or unknown dates. Sort by experiment date, last
save time, or title. Select a record to edit metadata, preview, download, or export.
Archive metadata changes retain analysis results. Choose **Use as CSV input** or
**Use as image input** on a supported attachment, then **Open spectrum review**.
Changing an input requires confirmation and invalidates dependent results. Changing
the CSV resets its column/unit selection, comparison and calculated result, while
retaining image extraction. Changing the image also resets calibration and extracted
points. Originals remain archived. **Detach from analysis** clears the active input
and allows that attachment to be trashed. Returning from spectrum review opens the
same record in the archive.

Analysis inputs retain the existing 12 MiB per-file and 30 MiB review-snapshot limits.
The CSV must have at least two columns, consistent row widths, and UTF-8 or BOM-marked
UTF-16 encoding. Image inputs accept PNG, JPEG, WebP and BMP; actual decoding and
the 16-megapixel extraction limit are checked in the browser. Unsupported or larger
files remain archival materials. Choosing a new input clears the old pair's source
label; verify source context and pairing in the record notes before analysis.

PNG, JPEG, WebP, GIF and BMP use browser image previews. CSV, TSV, TXT, Markdown,
JSON and LOG show at most the first 64 KiB as plain text (UTF-8 or BOM-marked UTF-16).
Other encodings may display replacement characters; original downloads are unchanged.
TIFF, SVG, XLSX, PDF and other formats are retained for download without an embedded
preview. Files are classified by extension; this is not content recognition.

Uploads are bounded to **25 MiB per file, 100 files and 100 MiB per record**.
Records and attachments can be moved to trash and restored. Trash does not free
disk space and is never automatically cleared. The [retention decision](decisions/001-record-lifecycle.md)
records the maintainer's choice and its tradeoff. Analysis inputs must be detached
or replaced before the corresponding file can be trashed. Trashed records are
read-only until restored, and both interfaces reject saves to them.

There is no permanent deletion, background sync, or cloud storage in this slice.
ZIP export includes a full `record.json`, retained files (including trash),
and `manifest.json` with paths, lengths and SHA-256 hashes. It is an inspectable
portable export. **Import record ZIP** validates the package and creates a new
record; it never overwrites an existing record, even on repeated import. Source
identity and timestamps are retained in `importedFrom`. A copied record is active;
individual attachment trash states are preserved. Saved analysis is retained,
not recalculated or scientifically certified by import.

Import accepts workbench ZIPs up to 150 MiB, with at most 100 original files and
100 MiB of original bytes, a 30 MiB record snapshot and a 1 MiB manifest. Entry
paths, identities, sizes and hashes must agree. Duplicate entries, unlisted files,
encrypted entries, symlinks and unsupported compression are rejected. ZIP member
names are never used as filesystem extraction paths. Validation completes before
writing content-addressed files and atomically publishing the new record.

## Implementation and tradeoffs

| Component | Responsibility |
| --- | --- |
| `prototype/archive.html`, `archive.css` | Record list, metadata form, materials and preview surface |
| `prototype/archive.mjs` | Explicit save/upload state, request handling, previews and navigation |
| `prototype/archive-filters.mjs` | Pure metadata/filename filtering and sorting |
| `scripts/archive_store.py` | Metadata validation, original-byte storage, compatibility and ZIP export |
| `scripts/archive_transfer.py` | Bounded ZIP validation and import as an independent record |
| `scripts/review_inputs.py` | Select/detach archived analysis inputs and invalidate dependent state |
| `scripts/serve_prototype.py` | Local HTTP routes, limits, same-origin checks and write locking |

Metadata and analysis snapshots share `data/prototype-records/<id>.json`. New files
are stored by content hash under `data/prototype-records/files/<sha256>.bin`;
descriptors preserve original filenames. Both are Git-ignored. Back up the **whole
record directory including `files/`**. Copying JSON alone loses new attachments.

An upload verifies or writes immutable bytes before replacing the record JSON.
If the record write fails, the old record remains readable; an unreferenced blob
can remain and be reused on retry. There is no automatic garbage collection.
The process lock serializes writes, and revisions reject stale saves from either
interface. Run one local server against a record directory. This is not a database
transaction system or a multi-user service.

Old inline inputs are exposed as virtual attachments without rewriting stored
records on read. If an explicit analysis save replaces an input, its previous bytes
are retained as an attachment. Some early CSV records kept decoded text only:
the interface and export manifest disclose that original encoding bytes are unavailable.
Malformed catalog records produce a visible warning and remain untouched.

Listing currently reads all records and hashes legacy inline inputs; downloads
verify file length and SHA-256. This favors small local archives and inspectable
behavior. Pagination, indexed search and a database should follow measured needs.

## Verification and pending review

The development agent ran 31 Python tests and 10 JavaScript tests on 2026-09-15.
The browser modules also pass syntax checks.
The archive additions cover original bytes, duplicates, old records, preservation of
analysis, injected write failure, corrupt blobs, export manifests, limits, HTTP
conflicts and origin rejection, date boundaries, unknown dates, and combined search.
Tests use isolated temporary directories; they do not insert fixtures into working
records. Existing numerical tests also pass; extraction behavior was not changed.

```powershell
python -m unittest discover -s tests -p "test_*.py"
node --test tests/core.test.mjs tests/diagnosis.test.mjs tests/archive-filters.test.mjs
```

Agent browser checks on an isolated record directory covered record creation,
multiple-file upload, file trash/restore, cancellation, record trash/restore, and
read-only metadata while a record is trashed, and importing an exported record
as a separate copy. Further checks selected a CSV from the archive, calculated its
known triangle area of 2, saved the result, and returned to the same record. Combined
keyword/file-kind filtering and text preview worked. At 390 px, the checked page had
no horizontal overflow. These agent checks are separate from user acceptance.

For an isolated walkthrough, start the server with
`python scripts/serve_prototype.py --port 8766 --records-dir data/browser-checks`.
This keeps verification records separate from working experiments.
