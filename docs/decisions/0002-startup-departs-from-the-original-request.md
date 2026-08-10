# 0002 — Two departures from what was asked for in configuration and startup

- **Status:** accepted
- **Decided:** 2026-08-07 · **Recorded:** 2026-08-10
- **Follows from:** R18, R21, R24, R25, V19, V33

## Context

The configuration-and-startup work was requested in one session, and two parts of it were then
planned differently from how they were asked for. Both departures were reasoned, and neither was
written down — which is how a deliberate departure decays into a quiet reinterpretation that the
next reader mistakes for the original intent.

## Decision

Keep both departures, and record them here so the reasoning is auditable.

### 1. Warm-up does not wait for Start

**Asked for:** nothing heavy happens until the operator presses Start — model warm-up included.

**Planned instead:** warm-up begins as soon as configuration exists; only *opening the audio
streams* waits for Start.

**Why:** **V33.** Warm-up is fused into `Transcriber.__init__` and runs under `NPU_LOCK`, so the two
instances warm *sequentially* — minutes for a multilingual model, possibly preceded by a download.
Deferring that to Start places the entire wait at the worst possible moment: after the operator has
already committed to starting a meeting. The half of the request that carries the actual guarantee
survives intact — no capture before authentication and an explicit Start (**R24**, **R25**) —
because the control that opens the streams is what is gated, not the model load.

### 2. `setup_mac.sh` keeps its current scope

**Asked for:** the web page runs `setup_mac.sh` once the operator has chosen a cache directory.

**Planned instead:** `setup_mac.sh` keeps doing Homebrew dependencies, `.venv` and `pip install`;
only the **model download** moves behind the UI.

**Why:** by the time the settings form is on screen, Streamlit is already running *inside* the
`.venv` that script builds, so it cannot rebuild that `.venv` from within, and Homebrew installs
need a shell the application does not own. The stated goal is unaffected — nothing must be
downloaded before the first cold start (**R21**) — because the model weights were the only large
part. The operator still never edits `.env` by hand (**R18**).

## Consequences

- If **V33** stops holding — a model small enough or a warm-up fast enough that the wait is
  negligible — the first departure loses its justification and the plan should return to what was
  asked for, rather than the request being treated as superseded.
- The second departure means the readiness state machine must distinguish "dependencies missing"
  (fix by running `setup_mac.sh` in a terminal) from "weights missing" (fix in the UI). Those are
  different failures with different remedies, and **V19** is why the second one cannot be assumed
  to have worked before.
