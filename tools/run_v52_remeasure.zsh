#!/usr/bin/env zsh
# Run both V52 arms (0sess then 3sess) or only summarise.
#
# Usage:
#   ./tools/run_v52_remeasure.zsh              # interactive: 0sess, then 3sess, then table
#   ./tools/run_v52_remeasure.zsh --summarise-only

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
ARM_SCRIPT="$REPO/tools/run_v52_arm.zsh"
VENV_PY="$REPO/.venv/bin/python"
OUT_MD="$REPO/fixtures/asr/results/v52_summary.md"

if [[ "${1:-}" == "--summarise-only" ]]; then
  "$VENV_PY" tools/measure_asr_latency.py \
    --label "0sess=$REPO/fixtures/asr/results/v52_0sess.log" \
    --label "3sess=$REPO/fixtures/asr/results/v52_3sess.log" \
    --threshold-ms 2000 \
    --write-md "$OUT_MD"
  print "Wrote $OUT_MD"
  exit 0
fi

print "This will run arm 0sess, then arm 3sess (each needs you to press Start / Stop)."
print "WAV is 3 passes (~213s, ~30 ASR lines). On Staff tab confirm exactly ONE Start capture."
print "Press Enter to begin 0sess, or Ctrl+C to abort."
read -r

# Fresh logs for this closing round (previous indicative arms stay as *.prev if present).
mkdir -p "$REPO/fixtures/asr/results"
for arm in 0sess 3sess; do
  f="$REPO/fixtures/asr/results/v52_${arm}.log"
  if [[ -f "$f" ]]; then
    mv -f "$f" "$REPO/fixtures/asr/results/v52_${arm}.prev.log"
  fi
done

zsh "$ARM_SCRIPT" 0sess

print ""
print "Press Enter to begin 3sess (1× staff + 2× speaker tabs)."
print "Again: Staff tab → exactly one ▶️ Start capture."
read -r

zsh "$ARM_SCRIPT" 3sess

print ""
print "Summarising…"
zsh "$0" --summarise-only
print "Done. Paste fixtures/asr/results/v52_summary.md (or the table) back to close 7.3."
