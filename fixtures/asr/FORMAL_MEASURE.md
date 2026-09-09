# Formal ASR bake-off measurement (post–7.3)

Operator sequencing (2026-08-10): finish **7.3** / **V52** first, then run this once, then
choose under **R11**. Until then, CLI harness numbers in `STATE.md` §7.2 are indicative only.

## Must observe

| Band | What to record |
|---|---|
| Latency | Per inference call ms; median / p95 / max; end-to-end if measurable |
| Sessions | Browser count held constant (**V52**); note 0 vs ≥3 (speaker + staff + host) |
| Tracks | Single-stream now; dual-track on `NPU_LOCK` when the second source exists |
| Resources | Process RSS (MB), CPU%, and NPU/GPU/Metal activity if available; note sustained load over a multi-minute script |
| Quality | **R37** (nonspeech accepted / VAD segs), **R8** speech / code-switch on the fixture set |
| Environment | Python version, venv, package set (`mlx-whisper` / `mlx-qwen3-asr`), model id, Streamlit in/out of path, sample rate path (16 kHz vs 48 kHz resample) |

## How to run (sketch)

```bash
# Quality + latency without UI (does not replace the multi-session arm)
.venv-bakeoff/bin/python tools/asr_bakeoff.py

# Multi-session + resources: capture while the app is running with a fixed tab count.
# Prefer line-buffered logs (V52 artefact: block-buffered redirected stdout lags).
# Prefer no `\r` access-code banner (removed in 7.3).
```

Resource sampling can be as simple as periodic `ps` / `sample` / Activity Monitor notes beside
the latency table; the closing record must include both columns, not latency alone.

## Not yet closing criteria by itself

48 kHz remeasure and dual-track still required before the bake-off is fully closed — see §7.2.
Open decision **V44** still required before shipping Qwen as the product default.
