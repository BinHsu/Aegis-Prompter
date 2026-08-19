# V52 / 7.3 remeasure protocol

Closes **7.3** when multi-session ASR **tails** no longer look like the old V52 failure
(5 browsers → max ~5 s, ~29% of calls > 2000 ms) while the median stays near **V51**.

Do this on the machine that runs capture. Unit tests cannot close this item.

## Prompt audio (TTS preferred)

V52 measures **UI contention vs inference latency**, not WER — so a reusable TTS fixture is
enough. Natural reading is optional.

```bash
# Build once (macOS say, 10 lines × 2 passes, 4 s gaps) → gitignored WAV
.venv/bin/python tools/gen_v52_prompt_audio.py --force

# Optional: teleprompter + mic record instead of TTS
.venv/bin/python tools/gen_v52_prompt_audio.py --teleprompter --force
```

During each arm, with capture **Started**, play into a path the mic can hear (speakers, or a
loopback device):

```bash
.venv/bin/python tools/gen_v52_prompt_audio.py --play
# or: afplay fixtures/asr/speech/en/v52_ten_line_en.wav
```

Keep the **same** `ASR_MODEL` as the V52 baseline unless you are deliberately changing it
(default distil is fine for an apples-to-apples remeasure).

## Arms

| Arm | Browsers | Notes |
|---|---|---|
| `0sess` | 0 extra (capturing UI only, or minimize other tabs) | Control |
| `3sess` | speaker + staff + host (≥3) | Production hearing |
| `5sess` (optional) | 5 tabs | Matches the published V52 table |

Warm up once before the first arm. New log file (or clear marker) per arm.

## One-shot (zsh)

```zsh
cd /Users/bin.hsu/Documents/Aegis-Prompter
./tools/run_v52_remeasure.zsh          # 0sess → 3sess → summary table
# or one arm:
./tools/run_v52_arm.zsh 0sess
./tools/run_v52_arm.zsh 3sess
./tools/run_v52_remeasure.zsh --summarise-only
```

Each arm opens the browser. On this Mac the real sequence is:

1. Role (if needed): **Speaker Mode** or **Staff Mode** — either is fine for V52  
2. **Configure** only if unset → Save → wait download / NPU warm  
3. **🚦 Pre-flight** — wait for **✅ Models warmed**; button is **▶️ Start capture**  
   (disabled until warm-up finishes — there is no separate bare “Start”)  
4. Feed runs via `AEGIS_V52_FEED` (no speaker sound); watch the left transcript  
5. **⏹️ Stop capture** on the running view, then finish the shell prompts  

Logs: `fixtures/asr/results/v52_*.log` (gitignored).

## Capture logs without the old artefacts

**V52 artefacts to avoid:** block-buffered redirected stdout; `\r` access-code banner (already
removed). The zsh helpers use `PYTHONUNBUFFERED=1` and redirect into `fixtures/asr/results/`.

Manual equivalent:

```zsh
mkdir -p fixtures/asr/results
PYTHONUNBUFFERED=1 .venv/bin/python -u -m streamlit run src/app.py 2>&1 \
  | tee fixtures/asr/results/v52_0sess.log
```

After Start + reading the script for arm `0sess`, stop capture / stop the app.
Copy or rename the tee file, then repeat for `3sess` with three browsers open **before** Start:

```bash
mv fixtures/asr/results/v52_0sess_tee.log fixtures/asr/results/v52_0sess.log
# reopen streamlit, open 3 tabs, Start, read script twice
PYTHONUNBUFFERED=1 .venv/bin/python -u -m streamlit run src/app.py 2>&1 \
  | tee fixtures/asr/results/v52_3sess.log
```

Optional resource sample while an arm runs (RSS KB + `%cpu` via `ps`):

```bash
# In another terminal — PID of the streamlit/python process
.venv/bin/python tools/measure_asr_latency.py \
  --watch-pid <PID> \
  --watch-out fixtures/asr/results/v52_3sess_resources.csv \
  --watch-seconds 180
```

## Summarise

```bash
.venv/bin/python tools/measure_asr_latency.py \
  --label 0sess=fixtures/asr/results/v52_0sess.log \
  --label 3sess=fixtures/asr/results/v52_3sess.log \
  --threshold-ms 2000 \
  --write-md fixtures/asr/results/v52_summary.md
```

Aim for **n ≥ 30** per arm. The default WAV is ten lines × **three** passes (~30 segments).

## Pass bar (record in STATE.md §7.3)

- Multi-session **median** stays near the 0-session arm (contention shape, not thermal).
- Multi-session **max** and **%>2000 ms** are no longer in the old V52 ballpark (~5 s / ~30%).
- Paste the markdown table into `STATE.md` and note whether 0.5 s `run_every` stays or changes.

Then 7.3 can be marked done; the **formal ASR bake-off** (latency + resources across models)
is a separate step — see [FORMAL_MEASURE.md](FORMAL_MEASURE.md).
