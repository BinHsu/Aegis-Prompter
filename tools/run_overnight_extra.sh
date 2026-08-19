#!/usr/bin/env bash
# The follow-on queue: experiments that need nothing from the operator, and could not be in the
# main queue because they consume what the main queue produces.
#
# WHY A SECOND FILE AND NOT MORE STAGES IN THE FIRST. The main queue was already running when these
# were asked for, and **bash reads a script incrementally from disk while executing it** -- editing
# a running script can make it execute garbage halfway through. A separate file is not tidiness, it
# is the only safe way to add work to a night already in progress.
#
# DONE / ABORT:
#   DONE  = every stage below printed its summary and the final listing appears.
#   ABORT = the retention audio this depends on does not exist (the main queue's retention stage
#           aborted or never ran), or a diarization run produced no turns at all. Both mean the
#           question cannot be answered, not that the answer is bad.
#
# USAGE
#   bash tools/run_overnight_extra.sh              # find last night's audio automatically
#   bash tools/run_overnight_extra.sh --check      # report what it would use, change nothing
#   AUDIO_DIR=/path/to/audio bash tools/run_overnight_extra.sh

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

PY=".venv/bin/python"
PYD=".venv-diarize/bin/python"
OUT="${OUT:-fixtures/asr/results/$(date +%Y%m%d-%H%M)-extra}"

log() { printf '\n\033[1m== %s\033[0m  %s\n' "$1" "$(date '+%H:%M:%S')"; }
fail() { printf '\n\033[31mABORT: %s\033[0m\n' "$1"; exit 1; }

[ -x "$PY" ] || fail "$PY missing -- wrong directory?"

log "PREFLIGHT"

# The retained audio lives under the operator's storage root, which only the app knows. Ask the
# app rather than guessing a path.
AUDIO_DIR="${AUDIO_DIR:-$($PY -c "
import sys; sys.path.insert(0, 'src')
import bootstrap
print(bootstrap.resolve_archive_dir(bootstrap.read_settings()))
" 2>/dev/null)}"
echo "  archive dir          ${AUDIO_DIR:-<unknown>}"
[ -n "$AUDIO_DIR" ] && [ -d "$AUDIO_DIR" ] || fail "no archive directory at '${AUDIO_DIR}'.
       The retention stage of the main queue writes it; if that stage aborted or never ran, there
       is nothing here to diarize. Run: bash tools/run_overnight.sh --only retention"

# Newest first, so a re-run picks up the most recent session rather than the oldest.
# **No `mapfile`**: macOS ships bash 3.2, where `mapfile` and `readarray` do not exist -- with
# `set -u` the array then reads as an unbound variable and the script dies in its own preflight.
# Found by running it, 2026-08-20. A newline-separated list plus a `while read` loop works on both.
WAVS=""
while IFS= read -r line; do
  [ -n "$line" ] && WAVS="$WAVS$line
"
done <<EOF
$(find "$AUDIO_DIR" -name '*.wav' -type f 2>/dev/null | xargs -I{} ls -t "{}" 2>/dev/null | head -4)
EOF
WAV_COUNT=$(printf '%s' "$WAVS" | grep -c . || true); WAV_COUNT=${WAV_COUNT:-0}
echo "  retained files       ${WAV_COUNT} found (newest first, up to 4)"
[ "$WAV_COUNT" -gt 0 ] || fail "the archive directory exists but holds no .wav.
       Retention arms a preference and writes on Stop; an empty directory means no session with
       retention armed has completed. This is exactly what 7.7 had never verified."

[ -x "$PYD" ] || echo "  NOTE: $PYD missing -- the diarization stage will be skipped (V93)"

if [ "${1:-}" = "--check" ]; then
  echo
  echo "preflight only; nothing was run. Files that would be diarized:"
  printf '%s' "$WAVS" | while IFS= read -r w; do [ -n "$w" ] && echo "    $w"; done
  exit 0
fi

if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  fail "$OUT already holds output. Overwriting destroys the evidence behind whatever was written
       from it. Unset OUT for a fresh dated directory."
fi
mkdir -p "$OUT"

nohup caffeinate -dis -t 7200 >/dev/null 2>&1 &
echo "  sleep held           2h"

# ---------------------------------------------------------------- diarization on real retained audio
# 7.10 was built 2026-08-17 and has never run on anything but a fixture clip. V93 made it possible
# without a Hugging Face token; this is the first time it meets audio the product itself recorded,
# through the microphone, with the room's acoustics in it. Roughly half real time on CPU.
if [ -x "$PYD" ]; then
  printf '%s' "$WAVS" | while IFS= read -r wav; do
    [ -n "$wav" ] || continue
    name=$(basename "$wav" .wav)
    log "DIARIZE $name  (7.10 on audio the product recorded, not a fixture)"
    caffeinate -dis env PYTHONPATH="$PWD" $PYD tools/diarize_runner.py "$wav" \
      --hf-home "$PWD/.hf_cache/AegisPrompter/models" --max-speakers 4 \
      > "$OUT/diarize_${name}.json" 2> "$OUT/diarize_${name}.log"
    $PY - "$OUT/diarize_${name}.json" <<'SUMMARY'
import collections, json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print(f"  unreadable output: {type(exc).__name__}"); raise SystemExit(0)
if "error" in data:
    print(f"  ERROR: {data['error'][:200]}"); raise SystemExit(0)
turns = data.get("turns", [])
counts = collections.Counter(t["speaker"] for t in turns)
speech = sum(t["end"] - t["start"] for t in turns)
print(f"  turns {len(turns)}  speakers {dict(counts)}  speech {speech:.0f}s")
if turns:
    print(f"  covers {turns[0]['start']:.1f}s -> {turns[-1]['end']:.1f}s")
    shortest = min(t["end"] - t["start"] for t in turns)
    print(f"  shortest turn {shortest:.2f}s  (a floor of exactly 0 would mean empty segments)")
SUMMARY
  done
else
  echo "  skipped diarization: no $PYD"
fi

# ---------------------------------------------------------------- summary
log "DONE"
echo "Everything written under $OUT:"
ls -1 "$OUT"
echo
echo "Nothing above is committed. The point of this queue is 7.10 meeting real recorded audio for"
echo "the first time -- read the speaker counts against how many people were actually in the room."
