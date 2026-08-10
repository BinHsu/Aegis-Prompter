# 0005 — Reset deletes only `.env`, and the storage layout is fixed beneath an operator-chosen root

- **Status:** accepted
- **Decided:** 2026-08-10
- **Follows from:** R4, R19, R22, R44, R47, R48, V46, V47

## Context

Once the application owns `.env` (**R18**, **R32**), reset becomes an action the application performs
rather than a file the operator removes. Two questions followed, and the first has an intuitive answer
that is wrong.

**Should reset also clear the weights and the recordings?** It sounds cleaner — no data left that the
form no longer references. Three reasons it is not:

- **The costs are not comparable.** `.env` is minutes to retype. Weights are a multi-gigabyte download
  and this product's premise is running offline. Recordings are irreplaceable.
- **Deleting recordings violates R4.** Retention is the file owner's decision. Destroying evidence as a
  side effect of a configuration button is precisely the application setting policy.
- **Both directories come from operator-typed strings** (**R19**, **R44**). A recursive delete against
  a path from a text field is not an operation worth offering at any warning level.

**And if reset only deletes `.env`, how does the operator get back to their data?** After reset the
form is blank, so the cache path must be re-entered. A freely-typed path re-entered slightly
differently means a complete cache becomes invisible and several gigabytes are downloaded again.

## Decision

**Reset deletes `.env`. Nothing else, ever.** No code path in the application removes transcripts,
recordings or weights (**R47**). Before deleting, reset lists the paths about to go unreferenced with
their sizes — not as a deletion offer, but because that screen is the last place the operator can read
where their data lives.

**The operator chooses one storage root, and the application owns a fixed layout beneath it**
(**R48**):

```
<storage root>/AegisPrompter/
├── models/     # HF_HOME
└── audio/      # retained WAVs, unless separately overridden
```

## Consequences

- **Re-entry is reproducible.** The same root regenerates byte-identical paths, so the existing cache
  is recognised and reused rather than refetched (**V47**). The form reports what it found under the
  root — cache size, existing recordings — before writing anything, so re-entry is confirmed rather
  than guessed at.
- **Redundant downloads are structurally impossible**, from either direction: content addressing stops
  the same weights being fetched twice, and the fixed layout stops a near-miss path from hiding a
  cache that is already there. Switching ASR models therefore costs one download each, ever — which
  settles the disk half of **V33**, though the memory half is still untested.
- **The settings form loses a field.** The archive directory is derived, not typed, so it drops to an
  optional override for the case where weights and recordings belong on different volumes. The
  retention toggle also loses its precondition: the archive path can no longer be unconfigured.
- **`.env` writes must be atomic** (**V46**), because the form is now the only writer and a torn file
  would present as a half-configured machine.
- A fixed directory name is a compatibility surface. Renaming `AegisPrompter/` later would orphan
  every existing installation exactly the way a mistyped path does, so it is effectively permanent.
