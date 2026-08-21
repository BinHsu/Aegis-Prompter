#!/usr/bin/env zsh
# One arm of the V52 / 7.3 remeasure (zsh).
#
# Usage:
#   ./tools/run_v52_arm.zsh 0sess
#   ./tools/run_v52_arm.zsh 3sess
#   ./tools/run_v52_arm.zsh 5sess
#
# Audio is injected in-process via AEGIS_V52_FEED (no speaker→mic). You should NOT expect
# to hear the prompt on speakers. You SHOULD see transcript lines appear in the browser.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

ARM="${1:-}"
case "$ARM" in
  0sess) TABS=1 ;;
  3sess) TABS=3 ;;
  5sess) TABS=5 ;;
  *)
    print -u2 "Usage: $0 0sess|3sess|5sess"
    exit 2
    ;;
esac

VENV_PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/fixtures/asr/results"
LOG="$LOG_DIR/v52_${ARM}.log"
WAV="$REPO/fixtures/asr/speech/en/v52_ten_line_en.wav"
URL="http://localhost:8501"
PID_FILE="$LOG_DIR/v52_${ARM}.pid"

mkdir -p "$LOG_DIR"

if [[ ! -x "$VENV_PY" ]]; then
  print -u2 "Missing $VENV_PY — run setup_mac.sh first."
  exit 2
fi

if [[ ! -f "$WAV" ]]; then
  print "Building prompt WAV…"
  "$VENV_PY" tools/gen_v52_prompt_audio.py --force
fi

# Free port 8501 if a leftover Streamlit is listening (best-effort).
if command -v lsof >/dev/null 2>&1; then
  busy=("${(@f)$(lsof -tiTCP:8501 -sTCP:LISTEN 2>/dev/null || true)}")
  # Drop empties (zsh can yield a single empty element).
  busy=("${(@)busy:#}")
  if (( ${#busy} )); then
    print "Port 8501 busy (pids: ${busy[*]}). Stopping…"
    kill "${busy[@]}" 2>/dev/null || true
    sleep 1
  fi
fi

: >"$LOG"
print "=== Arm $ARM  tabs=$TABS  log=$LOG ==="
print "Starting Streamlit with in-process WAV feed (AEGIS_V52_FEED)…"
print "You will NOT hear speakers — watch the transcript pane instead."

export AEGIS_V52_FEED="$WAV"
PYTHONUNBUFFERED=1 "$VENV_PY" -u -m streamlit run src/app.py \
  --server.headless true \
  --browser.gatherUsageStats false \
  >>"$LOG" 2>&1 &
ST_PID=$!
print "$ST_PID" >"$PID_FILE"
print "Streamlit pid=$ST_PID"
print "AEGIS_V52_FEED=$AEGIS_V52_FEED"

print -n "Waiting for $URL"
for i in {1..90}; do
  if curl -sf -o /dev/null "$URL"; then
    print " ready."
    break
  fi
  if ! kill -0 "$ST_PID" 2>/dev/null; then
    print -u2 "\nStreamlit exited early — see $LOG"
    exit 1
  fi
  print -n "."
  sleep 1
  if (( i == 90 )); then
    print -u2 "\nTimed out waiting for Streamlit."
    exit 1
  fi
done

print "Opening $TABS browser tab(s)…"
print "  tab 1: Staff (control — press Start capture here)"
# Use ?role= (not /?role=) and a fresh URL each time so macOS `open` does not reuse a
# Speaker tab whose session_state still had selected_role=speaker.
open "${URL}?role=staff&v52=${ARM}-staff"
sleep 0.5
for ((n = 2; n <= TABS; n++)); do
  print "  tab $n: Speaker (teleprompter — no Start; waits/follows)"
  open "${URL}?role=speaker&v52=${ARM}-spk${n}"
  sleep 0.4
done

print ""
print "────────────────────────────────────────"
print "UI (R34: machine controls are local-only; use the Staff tab on this Mac):"
print "  1) Staff tab: hard-refresh once (Cmd+R) → 🚦 Pre-flight → ✅ Models warmed"
print "  2) VERIFY Start capture: exactly ONE ▶️ Start capture on Staff; NONE on Speaker tabs"
print "  3) Staff: press that single ▶️ Start capture"
print "  4) Speaker tabs: teleprompter / follow only — no Start"
print "  5) Feed is in-process (no speaker sound). Watch transcript (~3 passes / ~30 lines), then Enter."
print "────────────────────────────────────────"
print -n "After verifying ONE Start on Staff (and Start capture pressed), press Enter: "
read -r

WAV_S="$("$VENV_PY" -c "import wave; w=wave.open(r'''$WAV'''); print(w.getnframes()/float(w.getframerate()))")"
# Feed is realtime; inference trails it. Wait for marker + headroom.
TIMEOUT_S=$(( ${WAV_S%.*} + 180 ))
if grep -q "V52 feed complete" "$LOG" 2>/dev/null; then
  print "Feed already complete in $LOG — skipping wait."
else
  print "Waiting for 'V52 feed complete' in log (timeout ${TIMEOUT_S}s; wav≈${WAV_S}s)…"
  START_WAIT="$SECONDS"
  while (( SECONDS - START_WAIT < TIMEOUT_S )); do
    if grep -q "V52 feed complete" "$LOG" 2>/dev/null; then
      print "Feed complete."
      break
    fi
    if ! kill -0 "$ST_PID" 2>/dev/null; then
      print -u2 "Streamlit exited during feed — see $LOG"
      exit 1
    fi
    # Progress: how many ASR lines so far.
    # Do not use `grep -c … || print 0` — grep exits 1 on zero matches after printing 0,
    # so `||` appends a second 0 and later zsh math blows up ("operator expected at 0").
    n="$(grep -c 'Transcribed in' "$LOG" 2>/dev/null || true)"
    n="${n//[^0-9]/}"
    [[ -n "$n" ]] || n=0
    print -n "\r  … still feeding/transcribing (Transcribed lines so far: $n)   "
    sleep 2
  done
  print ""
  if ! grep -q "V52 feed complete" "$LOG" 2>/dev/null; then
    print -u2 "WARNING: did not see V52 feed complete within timeout. Check Start was pressed and $LOG"
  fi
fi

# Inference usually finishes alongside the feed for this fixture; short drain only.
print "Short drain (10s) for any trailing inference…"
sleep 10

print ""
print "────────────────────────────────────────"
print "In the running view press ⏹️ Stop capture, wait for the page to settle,"
print "then Enter here. We SIGINT Streamlit — do not force-quit (Metal mutex abort)."
print "────────────────────────────────────────"
read -r

_graceful_stop() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 0
  kill -INT "$pid" 2>/dev/null || true
  for _ in {1..40}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.5
  done
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.5
  done
  print -u2 "WARNING: pid $pid still alive after INT/TERM; leaving it (avoid SIGKILL on MLX)."
}

if kill -0 "$ST_PID" 2>/dev/null; then
  _graceful_stop "$ST_PID"
  wait "$ST_PID" 2>/dev/null || true
fi
rm -f "$PID_FILE"

COUNT="$("$VENV_PY" -c "
import re, pathlib
t = pathlib.Path(r'''$LOG''').read_text(encoding='utf-8', errors='replace')
print(len(re.findall(r'Transcribed in\\s+\\d+', t, re.I)))
")"

print ""
print "Arm $ARM finished."
print "  log: $LOG"
print "  Transcribed lines found: $COUNT  (want ≥20–30)"
print ""
print "Next: ./tools/run_v52_arm.zsh 3sess   or   ./tools/run_v52_remeasure.zsh --summarise-only"
