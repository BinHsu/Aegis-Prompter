# 0003 — The interface is English; only content carries the meeting's language

- **Status:** accepted
- **Decided:** 2026-08-10
- **Follows from:** R3, R38

## Context

The operator works in a Taiwan hearing room, reads cues aloud in Chinese, and the knowledge base is
written in Chinese. The obvious inference — that the interface should therefore be Traditional
Chinese — was drafted as **R38** earlier the same day and **rejected on review**.

It also had to be settled explicitly because `AGENTS.md` forbids Chinese in the codebase but lists
identifiers, comments, log output and test assertions — not displayed strings. That left displayed
strings genuinely undefined, and the plan had already acquired a Chinese example string, so the
ambiguity was producing facts on the ground.

## Decision

**Interface text is English. Content keeps the language it arrived in.**

- **Interface** — labels, buttons, warnings, status lines, error messages, empty states. English.
- **Content** — transcript lines, retrieved cues, generated advice, staff broadcasts. Whatever
  language was spoken or written. Nothing translates or normalises it; doing so would discard part of
  what was captured (**R3**).

## Consequences

- `AGENTS.md`'s English-only rule needs no exception clause, so there is no boundary to argue about
  during review. One rule instead of two.
- Log lines and the interface they describe use the same vocabulary, which is what makes a support
  question answerable from `logs/` alone.
- The bilingual load sits where it belongs: the transcript pane renders mixed English and Chinese
  because the meeting was mixed, and the pane must not assume a single script for layout, font
  fallback, or line breaking.
- Anyone who later proposes translating the interface should read this record first — the Chinese
  interface is not an oversight and was not skipped for effort.
