# Record and attachment retention

Status: accepted by the maintainer on 2026-09-15.

## Decision

Deleting a record or attachment moves it to a recoverable trash view. This stage
does not automatically empty trash or provide permanent deletion.

The maintainer chose this approach over adding immediate permanent removal or
postponing deletion entirely. The tradeoff presented was fewer accidental losses
of experimental originals, at the cost of retaining disk usage.

## Consequences

- Original bytes remain in content-addressed storage while items are in trash.
- Normal searches exclude trashed records; a separate view supports restoration.
- Trashed records cannot be edited until restored. Revisions still reject stale writes.
- Attachments used by a saved analysis must first be detached or replaced before
  they can be moved to trash, so saved results keep their inputs.
- Exports include retained materials and their trash state. Import creates a new
  record instead of silently replacing an existing record with the same identifier.

The input-dependency and import-copy rules are implementation choices supporting
this retention policy; they are not separate maintainer decisions. Disk reclamation
can be considered later with an explicit retention policy and recovery requirements.
