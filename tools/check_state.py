#!/usr/bin/env python3
"""Checks that the requirement documents still hold together.

REQUIREMENTS.md and STATE.md were split apart because they fail in opposite ways:
a requirement fails by being quietly rewritten to match a plan, a plan fails by
going stale. The split only helps if the boundary is actually maintained -- and a
whole-file rephrase has already silently dropped a session's conclusions once.
This turns "did the rewrite lose something?" from vigilance into a failing test.

Uses only the standard library, so it runs without the project venv.

    python tools/check_state.py        # exit 1 on any violation
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(REPO_ROOT, "REQUIREMENTS.md")
STATE = os.path.join(REPO_ROOT, "STATE.md")
DECISIONS_DIR = os.path.join(REPO_ROOT, "docs", "decisions")

# A definition is a list item opening with the bolded ID followed by a dash. Both
# bold styles occur in the file -- "- **V1** — text" and "- **V12 — text**" -- so
# the closing asterisks are optional. A bare "**R8**" mid-sentence is a citation,
# not a definition, which is why the dash is part of the pattern.
DEFINITION = re.compile(r"^- \*\*(R\d+|V\d+)\*{0,2}\s*(?:—|--)", re.M)
CITATION = re.compile(r"\b([RV]\d+)\b")
# Plan sections are 7.1 through 7.7. The guards keep prose decimals out: a
# measured "CER 7.71" must not read as a citation of section 7.7.
PLAN_NUMBER = re.compile(r"(?<!\d)7\.\d(?![\d.])")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def decision_records():
    """Yields (filename, text) for every decision record, skipping the README."""
    if not os.path.isdir(DECISIONS_DIR):
        return
    for name in sorted(os.listdir(DECISIONS_DIR)):
        if name.endswith(".md") and name != "README.md":
            yield name, read(os.path.join(DECISIONS_DIR, name))


def main():
    requirements = read(REQUIREMENTS)
    state = read(STATE)
    failures = []

    defined = set(DEFINITION.findall(requirements))
    if not defined:
        failures.append("REQUIREMENTS.md defines no R*/V* at all -- has the format changed?")

    # 1. Every ID in each sequence exists. A gap means an entry was deleted rather
    #    than superseded, which is the exact failure the split exists to catch.
    for prefix in ("R", "V"):
        numbers = sorted(int(i[1:]) for i in defined if i.startswith(prefix))
        if not numbers:
            continue
        missing = [f"{prefix}{n}" for n in range(1, max(numbers) + 1) if f"{prefix}{n}" not in defined]
        if missing:
            failures.append(f"gap in the {prefix}* sequence: {', '.join(missing)}")

    # 2. Definitions belong in REQUIREMENTS.md only.
    stray = sorted(set(DEFINITION.findall(state)))
    if stray:
        failures.append(f"STATE.md defines {', '.join(stray)} -- definitions live in REQUIREMENTS.md")

    # 3. Nothing cites an ID that does not exist.
    sources = [("REQUIREMENTS.md", requirements), ("STATE.md", state)]
    sources.extend((os.path.join("docs", "decisions", n), t) for n, t in decision_records())
    for label, text in sources:
        dangling = sorted(set(CITATION.findall(text)) - defined)
        if dangling:
            failures.append(f"{label} cites undefined {', '.join(dangling)}")

    # 4. Reference direction is one-way. Plan numbers are renumbered whenever
    #    execution order changes, so a durable document must never depend on one.
    for label, text in [("REQUIREMENTS.md", requirements)] + [
        (os.path.join("docs", "decisions", n), t) for n, t in decision_records()
    ]:
        cited = sorted(set(PLAN_NUMBER.findall(text)))
        if cited:
            failures.append(f"{label} cites plan number(s) {', '.join(cited)} -- name the work in prose")

    # 5. Every requirement is either planned or explicitly refused. An R that is
    #    neither is a requirement nobody has decided anything about.
    plan_and_issues = state.split("# 🗺️", 1)[-1]
    closed = requirements.split("# ✅", 1)[-1]
    covered = set(CITATION.findall(plan_and_issues)) | set(CITATION.findall(closed))
    orphans = sorted(
        (r for r in defined if r.startswith("R") and r not in covered),
        key=lambda r: int(r[1:]),
    )
    if orphans:
        failures.append(
            f"no plan item or closed decision covers {', '.join(orphans)}"
        )

    # 6. A decision record that cannot name what it follows from is not a decision.
    for name, text in decision_records():
        if not CITATION.search(text):
            failures.append(f"docs/decisions/{name} cites no R*/V*")
        if "**Status:**" not in text:
            failures.append(f"docs/decisions/{name} has no Status line")

    if failures:
        print("FAIL: requirement documents are inconsistent")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    counts = (
        sum(1 for i in defined if i.startswith("R")),
        sum(1 for i in defined if i.startswith("V")),
        len(list(decision_records())),
    )
    print(
        "OK: {0} requirements, {1} constraints, {2} decision records -- "
        "no gaps, no dangling citations, no requirement uncovered".format(*counts)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
