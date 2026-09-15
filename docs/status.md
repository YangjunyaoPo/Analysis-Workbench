# Development status

Updated: 2026-09-15.

## Working locally

- **Archive:** multiple files per record, metadata and tags, keyword/date/category/
  file-kind filtering, previews, original downloads, and ZIP export.
- **Spectrum review:** CSV/image import, column and unit selection, manual calibration,
  curve extraction, correction/undo, interval calculations, and saved results.
- **Storage:** original-byte attachments, atomic record replacement, stale-write
  rejection, and preservation of previous files when analysis inputs change.
- **Recovery:** reversible record and attachment trash, with active-analysis input
  protection and no automatic permanent deletion. See the
  [maintainer's retention decision](decisions/001-record-lifecycle.md).

Run instructions are in the [README](../README.md). Storage limits and formats are
in [Archive workflow](archive-workflow.md); numerical methods and measured errors
are in [Spectrum review](prototype.md).

## Verification

The development agent ran **16 Python tests** after adding trash and recovery on
2026-09-15; all passed. The **10 JavaScript tests** passed earlier that day.
They cover storage integrity and failure cases, HTTP
persistence, filtering, known-answer calculations, and extraction diagnostics.

Earlier agent browser checks on 2026-09-11 covered the spectrum workflow,
save/reopen after restart, original-byte downloads, and narrow-screen layout.
Agent archive checks also covered creation, multiple-file upload, trash/restore,
cancelled confirmation, and read-only trashed records in an isolated directory. The maintainer's
initial spectrum-page feedback reported no obvious interaction problems;
numerical acceptance and detailed implementation review remain pending.

The controlled FTIR chart had 100% eligible coverage and p95 vertical error of
0.439 pixels. The three researcher Raman plots had p95 errors of 8.159, 47.226,
and 30.487 pixels and are not accepted for reliable quantitative extraction.
Follow-up diagnostics indicate that reducing each image column to one median
loses narrow peaks and rapid variation. This has not yet been fixed.

## Next

1. Walk through creating, editing, finding, and exporting multi-file records.
2. Review original-byte storage, revision conflicts, and backup/export behavior.
3. Complete ZIP import and selection of archived files as analysis inputs, then
   review the complete workflow. Permanent deletion is intentionally out of scope.

Further extraction experiments are paused while archival and retrieval take priority.
There is no deployment, collaboration support, AI product feature, or independent
scientific validation at this stage.
