# Decision records

Append-only provenance. One file per **topic decision** — never one per conversation.

Topics recur across sessions. A file per session therefore produces several documents that each
claim to be a complete picture and disagree with each other, leaving the reader to work out which
one is current for which topic. That is the failure mode ADR practice is known for, and it arrives
faster here, because a session produces a record every time.

## Rules

- **Never rewrite a record.** A decision that is later reversed gets a *new* record whose
  `Supersedes:` line names the old one. The old record gains a `Superseded by:` line and nothing
  else about it changes.
- **Every record cites at least one `R*` or `V*`** from [`REQUIREMENTS.md`](../../REQUIREMENTS.md).
  A decision that cannot name the requirement or the measurement it follows from is not yet a
  decision. `tools/check_state.py` enforces this.
- **A record is provenance, not current truth.** What must be true *now* lives in
  `REQUIREMENTS.md`; what happens next lives in [`STATE.md`](../../STATE.md). Read a record to
  learn *why*, never to learn *what*.
- **Open questions do not belong here.** They stay in `STATE.md` as open decisions until they are
  answered, and only then does a record appear.
- **Do not cite plan numbers** (`7.1`, `7.4`, …). They are renumbered whenever execution order
  changes. Name the work in prose instead.

Numbering is sequential; gaps are left in place rather than closed up.
