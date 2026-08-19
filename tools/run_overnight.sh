#!/usr/bin/env bash
# Tonight's acoustic verification, as one pasteable thing.
#
# WHY A SCRIPT AND NOT A LIST OF COMMANDS. Four things have to be true before any of these runs
# mean anything, and every one of them fails *silently and looks like success*:
#   - the machine must not be muted     (a muted run reports 38 correct Participant lines and a
#                                        microphone at zero -- soak_capture.py records that stage)
#   - sleep must be held for the whole queue, not four hours of it
#   - the wrapper must be allowlisted   (every run below is a `caffeinate` command; if that is not
#                                        allowed the queue stops at the first prompt and waits for
#                                        a human who is asleep -- this cost a night on 2026-08-17)
#   - `.env` still names the removed ASR model, so every tool needs --model
# A pasted sequence loses one of these every time. This does not.
#
# DONE / ABORT, stated up front because unattended work needs both:
#   DONE  = every selected stage wrote its summary and the final listing below prints. Per stage:
#           soak         -- all three rungs summarised, both roles non-zero, gate verified live
#           retention    -- two distinct files per rung, differing in their first five seconds
#           advisor      -- a probe summary printed, with a fabrication rate in it
#           leakage      -- all three rungs wrote a JSON with a bucketed CER
#           segmentation -- both arms printed a comparison table
#           baseline     -- both arms wrote 467 rows
#           overlap      -- the arm JSONL stopped growing and the scorer printed its table
#   ABORT = any of: a role at ZERO lines (silent room, or the stream never opened); a leakage rung
#           capturing nothing; --gate asked for while the gate is not live (V91 -- it fails open,
#           so the run would silently measure the opposite of its label); a baseline arm with the
#           wrong row count; retention producing one file, or two whose first five seconds match
#           (that is one stream written twice, which breaches R2 while looking like success); the
#           advisor probe printing no summary. The script stops, names
#           the stage and why, and does NOT climb to a longer rung on a failed short one.
#   Anything not on those two lists is a result, including an ugly one. A stage that answers its
#   question with a number nobody likes is DONE, not ABORT.
#
# THE LADDER IS 3 -> 10 -> 60 AND IS NOT OPTIONAL. Measured on 2026-08-18: queue dwell was 0 ms at
# three minutes, 3311 ms at ten, 6913 ms at sixty (V86). The short rung is not a smoke test to
# skip when confident -- it is where a wrong device, a silent room or a harness fault costs three
# minutes instead of an hour. A rung that fails is never promoted; fix and re-run the SHORT one.
#
# USAGE
#   bash tools/run_overnight.sh              # preflight, then the whole queue, in order
#   bash tools/run_overnight.sh --check      # preflight only, changes nothing, exits
#   bash tools/run_overnight.sh --only soak         # gated live hour        (needs sound)
#   bash tools/run_overnight.sh --only leakage      # speaker leak, bucketed (needs sound)
#   bash tools/run_overnight.sh --only retention    # 7.7 two files       (needs sound)
#   bash tools/run_overnight.sh --only advisor      # V94 as a rate       (silent, holds Metal)
#   bash tools/run_overnight.sh --only ragcues      # V95 regression      (silent, seconds)
#   bash tools/run_overnight.sh --only segmentation # gated vs ungated table (silent)
#   bash tools/run_overnight.sh --only baseline     # the 239-vs-252 question(silent)
#   bash tools/run_overnight.sh --only overlap      # V67 at conversational pace (silent)
#   bash tools/run_overnight.sh --only silent       # segmentation + baseline + overlap + R10
#
# THE QUEUE, AND WHY IT IS IN THIS ORDER. Roughly 8 hours end to end.
#   1. leakage      ~80 min  V87's 60-minute bucketed CER, marked "(not re-run)" in that entry,
#                            plus a third bucketed sample of the 3 and 10 rungs -- V87's own
#                            conclusion is that ONE run of this metric cannot be quoted, so
#                            repetition is the measurement, not a formality. First, and its
#                            3-minute rung is where a silent room or a wrong device shows up for
#                            three minutes instead of eight hours.
#   2. soak         ~80 min  the hour of the gate ACTUALLY live in the engine. Never once run:
#                            every previous "gate on" soak failed open (V91).
#   3. retention    ~20 min  7.7's toggle shipped 2026-08-13 and has never written a file, so R2's
#                            "never mixed" is still only an argument. Acoustic, and it follows the
#                            soak because it needs the same room, but it is deliberately NOT folded
#                            into it: continuous writes would move the latency numbers that soak
#                            exists to measure. Three and ten minutes -- two files with the right
#                            durations and different contents does not need an hour.
#   4. advisor      ~15 min  V94 found the generative advisor inventing figures and declining in
#                            prose the app then displays as advice, from one call per shape. This
#                            makes it a rate over 20 calls per shape. Starts and stops its own LLM
#                            server: mlx_lm.server holds Metal and so does Whisper, so this must
#                            never overlap an acoustic stage.
#   5. segmentation ~70 min  the same table gated and ungated. V89 found the R37 column saturated
#                            at 95-98% everywhere, so it could no longer choose a strategy; with
#                            the gate in front, what is left is the non-speech each strategy
#                            actually hands to the decoder. Two arms because a gated number with
#                            no ungated arm from the same night cannot be subtracted.
#   6. baseline     ~95 min  V92 recorded an ungated baseline of 239/253 where V72 and V84 recorded
#                            252, unexplained. Same corpus, same night, both environments: if the
#                            bake-off venv reads ~252 and the product venv ~239 it is the
#                            environment; if both read ~239 it is the day or the decode. Either
#                            answer closes it; no answer leaves every cross-run subtraction invalid.
#   7. overlap      ~70 min  V67 is the last figure still carrying the removed model. One realtime
#                            two-track arm, then the scorer. Risky: npu_lock_trial.py is close to
#                            unobservable while running and a 3-hour attempt on 2026-08-18 produced
#                            nothing, so this one is LAST and has a no-growth abort.
#
# TO STOP IT: Ctrl-C. The volume is restored by a trap on the way out, including on Ctrl-C.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

MODEL="mlx-community/whisper-large-v3-turbo"
# Dated at run time, never hardcoded. A fixed directory means the second run silently overwrites
# the first, and the first is the evidence behind whatever was already written down from it. That
# is not hypothetical: on 2026-08-19 a re-run destroyed `soak_mic_3min.log` from the night of
# 08-18, one of the four logs V91 rests on. Overridable so a deliberate continuation can still
# land beside its siblings: OUT=... bash tools/run_overnight.sh
OUT="${OUT:-fixtures/asr/results/$(date +%Y%m%d-%H%M)-overnight}"
PY=".venv/bin/python"
PYB=".venv-bakeoff/bin/python"
VOLUME=45                 # audible in a quiet room, and restored afterwards
ONLY="${2:-all}"
if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "REFUSING: $OUT already holds a run's output. Those files are gitignored, so overwriting"
  echo "them destroys the only copy of the evidence behind whatever was written from that run."
  echo "Unset OUT to get a fresh dated directory, or point OUT somewhere empty."
  exit 2
fi
mkdir -p "$OUT"

log() { printf '\n\033[1m== %s\033[0m  %s\n' "$1" "$(date '+%H:%M:%S')"; }
fail() { printf '\n\033[31mABORT: %s\033[0m\n' "$1"; exit 1; }

PREV_VOLUME=""
PREV_MUTED=""
restore() {
  [ -n "$PREV_VOLUME" ] && osascript -e "set volume output volume $PREV_VOLUME" 2>/dev/null
  # Both halves, because both were changed. Restoring the level and leaving the machine unmuted
  # would hand back a laptop that makes noise at 45 in a meeting tomorrow.
  [ "$PREV_MUTED" = "true" ] && osascript -e "set volume output muted true" 2>/dev/null
  printf '\nvolume restored to %s, muted restored to %s\n' \
    "${PREV_VOLUME:-unchanged}" "${PREV_MUTED:-unchanged}"
}
trap restore EXIT
# A signal ends the queue. Without the explicit exit, bash runs the handler and CARRIES ON: on
# 2026-08-19 a TERM restored the volume to 25 and the next acoustic stage started anyway, which
# would have produced numbers at a level no other measurement in this repo used. Reported as itself
# rather than as a clean finish, because a queue that was interrupted did not pass.
trap 'printf "\n\033[31mINTERRUPTED by a signal at %s. Stages already written are valid; nothing after this ran.\033[0m\n" "$(date "+%H:%M:%S")"; restore; exit 130' INT TERM

# ---------------------------------------------------------------- preflight
log "PREFLIGHT"

command -v caffeinate >/dev/null || fail "caffeinate missing"
[ -x "$PY" ] || fail "$PY missing -- wrong directory?"

FREE=$(df -g . | awk 'NR==2 {print $4}')
[ "$FREE" -lt 20 ] && fail "only ${FREE}GB free; the logs and fixtures need headroom"
echo "  disk free            ${FREE}GB"

# Another measurement holding the GPU makes every latency figure below meaningless, and the
# symptom is a plausible-looking table rather than an error. There is one accelerator; NPU_LOCK
# serialises callers inside a process and does nothing across processes.
# **Match the interpreter, not the command line.** The first version grepped whole command lines,
# so any process that merely *mentioned* a tool -- an editor, a grep, the very shell invoking this
# script -- read as a busy GPU and aborted the night. Seen 2026-08-19. Now: find candidate PIDs by
# command line, then keep only those whose executable is actually a Python.
BUSY_PIDS=""
for pid in $(pgrep -f "tools/(npu_lock_trial|soak_capture|probe_nonspeech_real|measure_segmentation|measure_decode_thresholds|measure_biasing)" 2>/dev/null); do
  [ "$pid" = "$$" ] && continue
  case "$(ps -p "$pid" -o comm= 2>/dev/null)" in
    *python*) BUSY_PIDS="$BUSY_PIDS $pid" ;;
  esac
done
if [ -n "${BUSY_PIDS# }" ]; then
  # shellcheck disable=SC2086
  ps -o etime=,command= -p $BUSY_PIDS | cut -c1-140
  fail "another measurement is already running (above). One GPU: its numbers and this run's
       would both be wrong, and neither would look wrong. Wait for it, or stop it with TaskStop
       and its task id -- not by matching on a process listing."
fi
echo "  gpu                  idle"

PREV_MUTED=$(osascript -e "output muted of (get volume settings)" 2>/dev/null)
PREV_VOLUME=$(osascript -e "output volume of (get volume settings)" 2>/dev/null)
echo "  output muted         $PREV_MUTED   (volume $PREV_VOLUME)"
# `--check` exits before the arming block below, so without this line it would report a muted
# machine and say nothing about it -- and the whole promise of --check is that it tells you what
# the real run will face.
if [ "$PREV_MUTED" = "true" ] && [ "$ONLY" != "silent" ]; then
  echo "  NOTE: muted now; the run will unmute, set volume $VOLUME, and restore both on exit."
fi

$PY - <<'PRE' || fail "the product path is not importable"
import sys, importlib.util as u
sys.path.insert(0, "src")
import bootstrap, model_search
m = bootstrap.FIELDS_BY_KEY["ASR_MODEL"].default
assert model_search.disqualified_reason(m) is None, m
print(f"  shipped default      {m}")
# Package importability was always True and told us nothing: V91's dead gate imported fine for
# days. The weights are the part that goes missing, and only a probe can see them.
print(f"  voice gate package   {bool(u.find_spec('pyannote.audio'))}")
bootstrap.apply_environment(bootstrap.read_settings())
bootstrap.enforce_offline()
import voice_gate
print(f"  voice gate LIVE      {voice_gate.is_live()}   (False means --gate runs will be refused)")
PRE

CONFIGURED=$($PY -c "import sys; sys.path.insert(0,'src'); import bootstrap; print((bootstrap.read_settings().get('ASR_MODEL') or '').strip())" 2>/dev/null)
echo "  .env says            ${CONFIGURED:-<empty>}"
[ "$CONFIGURED" != "$MODEL" ] && echo "  NOTE: every run below passes --model, so .env is not consulted."

if [ "${1:-}" = "--check" ]; then echo; echo "preflight only; nothing was run."; exit 0; fi

# Sized to the whole queue, not to a comfortable number. Expiring early is what cost 2026-08-17.
nohup caffeinate -dis -t 43200 >/dev/null 2>&1 &
echo "  sleep held           12h"
# **Unmute rather than refuse.** The mute check used to abort and ask a person to unmute, which
# left a human step in an unattended queue for no reason: this script already takes the volume and
# gives it back, and mute is the same kind of setting. It is still VERIFIED afterwards rather than
# assumed, because a muted acoustic run reports itself healthy and measures silence -- that failure
# cost a night on 2026-08-17 and is the one soak_capture.py has a recorded stage for.
if [ "$ONLY" != "silent" ]; then
  osascript -e "set volume output muted false" 2>/dev/null
  osascript -e "set volume output volume $VOLUME" 2>/dev/null
  NOW_MUTED=$(osascript -e "output muted of (get volume settings)" 2>/dev/null)
  NOW_VOLUME=$(osascript -e "output volume of (get volume settings)" 2>/dev/null)
  [ "$NOW_MUTED" = "true" ] && fail "the machine is still MUTED after being told not to be.
       Something else owns the audio settings; an acoustic run now would report itself healthy and
       measure silence. Nothing has been run."
  [ "${NOW_VOLUME:-0}" -lt 10 ] && fail "output volume is ${NOW_VOLUME} after being set to
       $VOLUME. An acoustic run at that level measures near-silence and reports success."
  echo "  audio armed          volume $NOW_VOLUME, muted $NOW_MUTED (both restored on exit)"
fi

# ---------------------------------------------------------------- helpers
# A rung passes only if BOTH roles produced lines. Zero for a role is the muted-room signature and
# means every later rung would measure nothing.
roles_produced_lines() {
  local f="$1" a b
  # `|| echo 0` here was a real defect, found the hard way on 2026-08-19: `grep -c` prints its
  # count AND exits 1 when the count is zero, so the fallback appended a SECOND line, the variable
  # became "0\n0", `[ -eq ]` died with "integer expression expected", and the guard that should
  # have stopped the queue was skipped. A broken guard is worse than no guard: it reads as one.
  a=$(grep -c "\[Speaker (You)\] Transcribed in" "$f" 2>/dev/null || true); a=${a:-0}
  b=$(grep -c "\[Participant\] Transcribed in" "$f" 2>/dev/null || true); b=${b:-0}
  echo "     Speaker=$a  Participant=$b"
  [ "$a" -gt 0 ] && [ "$b" -gt 0 ]
}

# ---------------------------------------------------------------- leakage (needs sound)
if [ "$ONLY" = "all" ] || [ "$ONLY" = "leakage" ]; then
  for M in 3 10 60; do
    log "LEAKAGE ${M}min  (V70, against known reference text)"
    caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/measure_speaker_leakage.py \
      --minutes "$M" --volume "$VOLUME" --model "$MODEL" \
      --out "$OUT/leakage_${M}min.json" > "$OUT/leakage_${M}min.log" 2>&1
    tail -6 "$OUT/leakage_${M}min.log"
    LINES=$(grep -c "^  \[" "$OUT/leakage_${M}min.log" 2>/dev/null || true); LINES=${LINES:-0}
    echo "     microphone lines: $LINES"
    [ "$LINES" -eq 0 ] && fail "the ${M}min leakage rung captured NOTHING.
       Either the speakers are silent or the microphone never opened. Fix, then re-run the
       3-minute rung -- never promote a rung that did not pass."
  done
fi

# ---------------------------------------------------------------- acoustic soak (needs sound)
if [ "$ONLY" = "all" ] || [ "$ONLY" = "soak" ]; then
  for M in 3 10 60; do
    log "ACOUSTIC SOAK ${M}min  (V62/V65/V69 through the microphone, gate on)"
    caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/soak_capture.py \
      --minutes "$M" --microphone --sample-every 20 --gate --model "$MODEL" \
      > "$OUT/soak_mic_${M}min.log" 2>&1
    sed -n '/=====/,$p' "$OUT/soak_mic_${M}min.log"
    roles_produced_lines "$OUT/soak_mic_${M}min.log" || fail "the ${M}min acoustic soak had a role
       at ZERO lines. That is the muted-machine signature and it reports as healthy everywhere
       else -- read the absence, not the RMS (soak_capture.py records why)."
  done
fi

# ---------------------------------------------------------------- retention (needs sound)
# 7.7 shipped the toggle on 2026-08-13 and no run has ever written a retained file, so R2's promise
# that the two tracks are never mixed has only been argued. Three and ten minutes only: proving that
# two files appear, with the right durations and different contents, does not need an hour, and the
# hour would cost the gated soak its clean conditions -- continuous writes are exactly the kind of
# confound that would move the latency numbers V86 and V88 exist to track. Kept as its own stage for
# that reason rather than folded into --gate above.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "retention" ]; then
  for M in 3 10; do
    log "RETENTION ${M}min  (7.7 / R2 -- two files, or one file twice?)"
    caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/soak_capture.py \
      --minutes "$M" --microphone --sample-every 20 --gate --retain --model "$MODEL" \
      > "$OUT/retention_${M}min.log" 2>&1
    sed -n '/===== retention/,$p' "$OUT/retention_${M}min.log" | head -12
    grep -q "distinct files: True" "$OUT/retention_${M}min.log" || fail "the ${M}min retention rung
       did not produce two distinct files. Either retention wrote nothing, or it wrote one stream
       to both paths -- and the second would breach R2 while looking like success."
    grep -q "first 5s differ: True" "$OUT/retention_${M}min.log" || fail "the ${M}min retention
       rung wrote two files whose first five seconds are identical. That is one stream written
       twice, which is precisely what R2 forbids."
  done
fi

# ---------------------------------------------------------------- advisor (silent, holds Metal)
# V94 found that the generative advisor invents figures and declines in prose that the app then
# shows as advice -- from one call per shape. This turns that into a rate. It starts and stops its
# own LLM server, because mlx_lm.server holds Metal and so does Whisper: a probe running beside a
# soak would spoil both. Never run this concurrently with an acoustic stage.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ] || [ "$ONLY" = "advisor" ]; then
  if [ ! -x ".venv-llm/bin/python" ]; then
    echo "  skipping advisor: .venv-llm not built on this machine"
  else
    log "ADVISOR  (V94 as a rate: how often does it invent a figure?)"
    caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/probe_advisor.py \
      --repeats 20 --out "$OUT/advisor_probe.jsonl" > "$OUT/advisor.log" 2>&1
    sed -n '/===== advisor probe/,$p' "$OUT/advisor.log"
    grep -q "===== advisor probe" "$OUT/advisor.log" || fail "the advisor probe printed no summary.
       Its own server may never have answered; the tail of $OUT/advisor.log says which."
  fi
fi

# ---------------------------------------------------------------- rag cues (silent, seconds)
# V95 found the retrieval slot firing 0 of 5 on paraphrases at the shipped 0.65, with the quiet
# cases correctly silent -- so the gate sits above every attainable score and the product cannot
# show that it is mute (V34/V35). Kept in the queue because it is seconds long and it is the only
# check that would notice the day an embedding-model or index change moves those scores.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ] || [ "$ONLY" = "ragcues" ]; then
  log "RAG CUES  (V95: does a cue fire on a paraphrase at all?)"
  caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/probe_rag_cues.py \
    --out "$OUT/rag_cues.jsonl" > "$OUT/rag_cues.log" 2>&1
  sed -n '/===== rag cue probe/,$p' "$OUT/rag_cues.log"
  grep -q "===== rag cue probe" "$OUT/rag_cues.log" || fail "the RAG cue probe printed no summary.
       It builds its own temporary index, so a failure here is the embedding model or the store,
       not the operator's notes -- the tail of $OUT/rag_cues.log says which."
fi

# ---------------------------------------------------------------- segmentation (silent)
# Two arms on purpose. V89 killed this table's ability to choose by finding its R37 column
# saturated at 95-98% for every strategy; gated, the column measures what each strategy hands the
# decoder rather than what the model invents regardless. A gated arm with no ungated arm from the
# same night cannot be subtracted against, so both run or neither is worth reading.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ] || [ "$ONLY" = "segmentation" ]; then
  for ARM in ungated gated; do
    GATEFLAG=""
    [ "$ARM" = "gated" ] && GATEFLAG="--gate"
    log "SEGMENTATION ${ARM}  (V66/V89 -- does the R37 column choose again?)"
    caffeinate -dis env PYTHONPATH="$PWD" $PY -u tools/measure_segmentation.py \
      --minutes 10 --model "$MODEL" --hf-home "$PWD/.hf_cache/AegisPrompter/models" $GATEFLAG \
      > "$OUT/segmentation_${ARM}.log" 2>&1
    sed -n '/segmentation comparison/,$p' "$OUT/segmentation_${ARM}.log"
    grep -q "segmentation comparison" "$OUT/segmentation_${ARM}.log" || fail "the ${ARM}
       segmentation arm printed no comparison table. Its harness raises rather than reporting
       CER 1.0, so the tail of $OUT/segmentation_${ARM}.log carries the reason."
  done
fi

# ---------------------------------------------------------------- baseline (silent)
# V92 left one number unexplained: the ungated corpus baseline read 239 of 253 in the product venv
# where V72 and V84 read 252 in the bake-off one. Two arms, same corpus, same night. If bake-off
# reads ~252 and product ~239 the difference is the environment; if both read ~239 it is the day
# or the decode. Either outcome closes it, which is what makes it worth the GPU time.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ] || [ "$ONLY" = "baseline" ]; then
  for ARM in product bakeoff; do
    if [ "$ARM" = "product" ]; then
      ARMPY="$PY"; ARMHF="$PWD/.hf_cache/AegisPrompter/models"
    else
      ARMPY="$PYB"; ARMHF="$PWD/.hf_cache-bakeoff"
    fi
    [ -x "$ARMPY" ] || { echo "  skipping $ARM: $ARMPY missing"; continue; }
    log "BASELINE ${ARM}  (V92: is 239 vs 252 the environment, or the day?)"
    caffeinate -dis env PYTHONPATH="$PWD" $ARMPY -u tools/probe_nonspeech_real.py \
      --passes 1 --skip-old --hf-home "$ARMHF" \
      --out "$OUT/baseline_${ARM}.jsonl" > "$OUT/baseline_${ARM}.log" 2>&1
    ROWS=$(wc -l < "$OUT/baseline_${ARM}.jsonl" 2>/dev/null | tr -d " ")
    grep -E "produced text on" "$OUT/baseline_${ARM}.log" | tail -4
    echo "     rows: ${ROWS:-0} (expect 467)"
    [ "${ROWS:-0}" -eq 467 ] || fail "the ${ARM} baseline arm wrote ${ROWS:-0} rows, not 467.
       A short arm cannot be compared against a full one, and the comparison is the whole point."
  done
fi

# ---------------------------------------------------------------- overlap (silent, and risky)
# V67 is the last figure still carrying the removed model. It is LAST in the queue on purpose:
# npu_lock_trial.py is close to unobservable while running and a 3-hour attempt on 2026-08-18
# produced nothing, so if it hangs it costs only itself -- everything above is already written.
# There is no early abort and that is deliberate: stopping it would mean this script terminating
# a process by PID, and the house rule is that runs are stopped by their task id, by a person or
# an agent who can see what they are stopping. The arm ends by itself when the fixture ends
# (~65 min of realtime feed); a stall shows up as a short file in the row check below.
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ] || [ "$ONLY" = "overlap" ]; then
  log "OVERLAP arm  (V67 re-run at conversational pace, ~65 min of realtime feed)"
  ARM_JSONL="$OUT/overlap_realtime.jsonl"
  caffeinate -dis env PYTHONPATH="$PWD" $PYB -u tools/npu_lock_trial.py --child \
    --model "$MODEL" --hf-home "$PWD/.hf_cache-bakeoff" --realtime \
    > "$ARM_JSONL" 2> "$OUT/overlap_arm.log"
  ARM_LINES=$(wc -l < "$ARM_JSONL" 2>/dev/null | tr -d " ")
  echo "     overlap arm finished with ${ARM_LINES:-0} lines"
  if [ "${ARM_LINES:-0}" -lt 100 ]; then
    tail -5 "$OUT/overlap_arm.log"
    fail "the overlap arm produced ${ARM_LINES:-0} lines. This is the 2026-08-18 failure
       repeating. Score nothing and conclude nothing from it; the tail of overlap_arm.log is
       above and everything earlier in the queue is already written."
  fi
  log "OVERLAP score  (solo vs contended, against V67's withdrawn 1.47x)"
  PYTHONPATH="$PWD" $PYB -u tools/measure_overlap_turns.py --events "$ARM_JSONL" \
    > "$OUT/overlap_score.log" 2>&1
  tail -25 "$OUT/overlap_score.log"
fi

# ---------------------------------------------------------------- R10 count (silent, seconds)
if [ "$ONLY" = "all" ] || [ "$ONLY" = "silent" ]; then

  log "SCRIPT MIX  (R10 quantified: how much output is Simplified?)"
  OUT_DIR="$OUT" PYTHONPATH="$PWD" $PY - <<'R10' > "$OUT/script_mix.log" 2>&1
import glob, json, os, sys
sys.path.insert(0, "src"); sys.path.insert(0, "tools")
from asr_eval import looks_traditional_chinese
rows = []
# **Score THIS run, not a fixed directory.** Until 2026-08-20 this globbed
# `20260817-model-swap/E*.jsonl` -- a hardcoded path -- so it recounted the same stored dataset every
# night and could only ever reproduce V90's 67/9. A stage that cannot produce a new number is not a
# measurement, however much its output looks like one. The current run's own outputs come first; the
# old directory is kept as a fallback so a --only silent invocation still has something to count.
patterns = [os.path.join(os.environ.get("OUT_DIR", ""), "*.jsonl"),
            "fixtures/asr/results/20260817-model-swap/E*.jsonl"]
for pattern in patterns:
    if not pattern.strip(os.sep):
        continue
    found = sorted(glob.glob(pattern))
    if found:
        print(f"counting {len(found)} file(s) from {os.path.dirname(pattern) or '.'}")
        for path in found:
            rows += [json.loads(l) for l in open(path) if l.strip()]
        break
trad = simp = 0
for r in rows:
    verdict = looks_traditional_chinese(r.get("text") or "")
    if verdict is True: trad += 1
    elif verdict is False: simp += 1
print(f"lines carrying Chinese: {trad + simp}")
print(f"  Traditional  {trad}")
print(f"  Simplified   {simp}")
print("R10 wants Traditional; V60 recorded every candidate producing Simplified against a")
print("Traditional reference, and R9 scopes the live path to the gist. This is the number.")
R10
  cat "$OUT/script_mix.log"
fi

# ---------------------------------------------------------------- summary
log "DONE"
echo "Everything written under $OUT:"
ls -1 "$OUT"
echo
echo "Nothing above is committed. Read the numbers, then record what they mean --"
echo "a measurement nobody wrote down is a measurement nobody has."
