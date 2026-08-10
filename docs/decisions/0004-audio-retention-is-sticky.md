# 0004 — Audio retention is a sticky preference, not a per-meeting decision

- **Status:** accepted
- **Decided:** 2026-08-10
- **Follows from:** R16, R27, R33, R45, R46

## Context

Retention was originally classified as a per-meeting decision: a toggle on the pre-flight panel,
default off, committed at Start and forgotten afterwards. That followed from **R27**, which puts every
per-meeting decision on one panel, and from **R33**, whose wording at the time was "persist what was
typed" — and a switch is not typed.

Reviewing what is actually lost when retention is off changed the weighting. Five capabilities exist
only while the audio does, and all five fail *retrospectively*: corroboration, re-transcribing with a
better model later, acoustic speaker attribution as the fallback for **R12**, reproducing a false
trigger after the fact, and verifying rather than merely re-flowing during cleanup. Enabling costs
disk and can be undone by deleting a file. Not enabling costs nothing today and can never be undone.
A per-meeting default of off therefore places the default on the irreversible side, and the one meeting
that later turns out to matter is the one nobody armed.

## Decision

**One switch, on the pre-flight panel, which persists its own state.** Off until the operator first
enables it; sticky on that machine thereafter, stored in `.env` beside the archive directory.

**No session-only override.** Whatever the switch reads when Start is pressed becomes the standing
preference. A single control with two meanings — sometimes remembered, sometimes not — is worse than
either behaviour on its own.

Two supporting requirements were added rather than treating this as an exception:

- **R33 was reworded**, not exempted. The real test was never typed-versus-clicked but
  *rediscoverable versus stale-prone*. A device choice goes stale because names and indices move; a
  standing preference cannot go stale and cannot be rediscovered, so it belongs in `.env` for exactly
  the reason a URL does.
- **R46** — a sticky choice is *disclosed* every session, not merely applied. Persistence removes the
  need to re-decide; it must not remove the chance to notice. The panel shows the state it is in
  before every Start, and the warning fires when the switch is turned **on**.

## Consequences

- **R27** is unharmed: the set of per-meeting decisions shrank by one, and the control still appears
  on the pre-flight panel where every capture choice is reviewed together.
- The consent argument that justified default-off survives only because of **R46**. Without the
  every-session disclosure, sticky retention would mean silently recording every later meeting, which
  is the outcome default-off existed to prevent.
- `.env` gains `ARCHIVE_AUDIO`, so `.env.example` must gain it in the same change as the code that
  reads it.
- The session record must state retention status and archive path (**R45**), or the setting's own
  history becomes unreadable after the fact.
