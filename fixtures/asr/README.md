# ASR bake-off fixtures

Synthesized (or later hand-recorded) audio used to choose the live ASR model under **R11**.
Feeds float32 arrays straight into the bake-off harness — it does **not** replace dual-track
capture. The Participant / system-audio track is why **R37** exists; these clips make that
failure measurable without BlackHole or the process tap.

## Layout

```
fixtures/asr/
├── README.md          # this file (tracked)
├── MANIFEST.md        # how each clip was produced (tracked)
├── nonspeech/
│   ├── music/
│   ├── chime/
│   └── keyboard/
├── speech/
│   ├── en/
│   ├── zh/
│   └── code_switch/
└── results/           # harness output (gitignored)
```

WAVs are **gitignored**. Regenerate (product venv is enough):

```bash
.venv/bin/python tools/gen_asr_fixtures.py
```

### Bake-off runner (disposable Python ≥3.10 env)

Qwen's MLX packages need Python ≥3.10; the product `.venv` may still be 3.9. Use a
**separate, wipeable** env so measurement stays portable and does not change the product default:

```bash
# one-time host interpreter (Homebrew); optional if python3.12 already exists
brew install python@3.12

/opt/homebrew/bin/python3.12 -m venv .venv-bakeoff
.venv-bakeoff/bin/pip install numpy sounddevice mlx-whisper webrtcvad python-dotenv 'setuptools<81'
# setuptools pin: webrtcvad still imports pkg_resources (removed from newer setuptools)
# `mlx-qwen3-asr` is deliberately absent: R50 disqualifies that family (docs/decisions/0012).
# Add it by hand only to reproduce the old comparison, and pass --include-disqualified.

# uses .env storage root for HF_HOME — R48, V19
# Harness prefers Homebrew openssl@3 CA bundle when SSL_CERT_FILE is unset (corp MITM).
.venv-bakeoff/bin/python tools/asr_bakeoff.py
```


Wipe cleanly (does not touch `.venv`, weights under the storage root, or fixtures):

```bash
rm -rf .venv-bakeoff
# optional: brew uninstall python@3.12   # only if nothing else needs it
# model weights stay under the configured HF_HOME until you delete that cache yourself
```

The product venv is now enough for every candidate that is allowed to ship:

```bash
.venv/bin/python tools/asr_bakeoff.py
```

**The synthesized non-speech below is a control, not an R37 verdict.** Every model measured here
treats it as a different world from real non-speech: the model that scored 0/63 on these clips
scored 23/253 on `nonspeech_real/` (**V60**). Score both, and read the real one.

```bash
.venv/bin/python tools/probe_nonspeech_real.py      # R37 on real non-speech
.venv/bin/python tools/measure_decode_thresholds.py # can the decoder gates buy it back?
.venv/bin/python tools/measure_biasing.py           # does initial_prompt recover proper nouns?
```

## Before starting an unattended queue — read this, it cost a night

Three preconditions, each of which fails **silently and looks like success**. Checked in this
order, they take two minutes; skipped, they cost hours.

| Check | Command | Why it is not optional |
|---|---|---|
| **Permissions cover the *wrapper*** | `jq -r '.permissions.allow[]' .claude/settings.local.json \| grep caffeinate` | Every run below is wrapped in `caffeinate -dis …`, which makes it a **`caffeinate` command**. An allowlist naming only `.venv/bin/python` does not match it, so every run prompts and an unattended queue stops at the first one. On 2026-08-17 a run launched at 22:35 had done **7m44s of work by 05:00** for exactly this reason. **An agent cannot add this rule itself** — the classifier refuses to let one grant itself permissions, correctly — so it is an operator action. Added 2026-08-18 |
| **The machine is not muted** | `osascript -e "output muted of (get volume settings)"` | Only for acoustic runs. A muted run reports itself healthy and measures silence — `soak_capture.py` records a 3-minute stage that returned 38 correct Participant lines with the microphone at zero |
| **Sleep is held for the whole queue** | `pmset -g assertions \| grep -A2 caffeinate` | `pmset -g custom` says `sleep 1` here. Size `-t` to the queue and re-arm before it lapses |

**`ps etime` cannot tell you whether a run is progressing.** It excludes both sleep *and*
never-having-started, so a blocked run, a slept run and a slow run are indistinguishable from
inside. **Judge progress by the output file growing**, never by process inspection.

**Keep shell commands textually boring.** A guard in the operator's global settings matches the
*whole* command string, prose included — so a command is interrupted for what it *says*, not for
what it does. Writing a commit message that describes the guard is enough to trigger it. Put text
in a file with the file-writing tool and apply it with `git commit -F <path>`; the same reflex as
judging a run by its output file rather than by inspecting processes.

## Rules

- Never write under `history/`, `context/`, or `logs/`.
- Default sample rate is 16 kHz mono — what `transcriber.py` consumes today.
- Scoring a candidate is **measurement only** — do not treat a successful import, or a winning
  row, as adoption. Crowning a default needs **R37** on *real* non-speech, the **R11** choice made
  deliberately, and **R50** applied first, which is the one that disqualified the winner.
- [FORMAL_MEASURE.md](FORMAL_MEASURE.md) is the latency + resource checklist a closing run must
  observe; [V52_REMEASURE.md](V52_REMEASURE.md) is the live protocol, summarised with
  `tools/measure_asr_latency.py`.


## The Qwen family is disqualified, not merely unused

`mlx-qwen3-asr` and `Qwen/Qwen3-ASR-*` were the product default between 2026-08-11 and
2026-08-17 and won this bake-off on every column. **R50** removed them anyway: the weights and the
port are PRC-origin, which is a procurement constraint no measurement here can see. See
`docs/decisions/0012` for the survey and what the change cost, and `docs/decisions/0008` for the
pinned-wheel recovery path that is now **history rather than instruction**.

They stay scoreable so the comparison can be reproduced — install the package by hand and pass
`--include-disqualified`, which prints the reason. Reproducing a comparison must not require
reinstating a dependency, and must not happen by accident either.
