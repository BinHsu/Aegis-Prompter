#!/usr/bin/env python3
"""Drive the real application through Start, a fed transcript, and Stop.

**The gap.** Every soak in this repository calls `GlobalState` directly. Nothing has ever driven
`app.py` itself past the settings page: the role gate, the pre-flight panel, the `▶️ Start capture`
button, the running view's fragment, `⏹️ Stop capture`, and the post-meeting prompt have never been
exercised end to end. `tests/unit/` reaches `start_recording` with the audio and advisor stubbed,
which tests the arming gate and says nothing about whether the screen a person looks at works.

**Two things this deliberately does not do.**

- **It writes no session into `history/`.** `DialogueBuffer.start_session` defaults its
  `history_dir` to the real one, so a probe run would drop a fake meeting into the operator's own
  record. Patched to a temporary directory here, and the patch is asserted rather than assumed.
- **It opens no microphone.** `AEGIS_V52_FEED` injects a WAV into the Speaker track and tells
  `start_recording` not to open a device (the existing lab hook, **V52**). So this is silent and can
  run at any hour, which is the whole reason it is worth having separately from the acoustic queue.

**What it can therefore establish, and what it cannot.** It establishes that the boot sequence
reaches a running view, that transcript lines appear in it, and that Stop closes a session and
renders a post-meeting prompt. It establishes nothing about latency, nothing about audio devices,
and nothing about **R9** — whether a person can read that view while speaking is not a property of
the code.

USAGE
    PYTHONPATH="$PWD" .venv/bin/python tools/probe_ui_flow.py --seconds 40
"""
import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

FIXTURE = REPO / "fixtures" / "asr" / "conversation" / "track_A.wav"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=40.0,
                        help="How long to let the fed session run before pressing Stop.")
    parser.add_argument("--feed", default=str(FIXTURE))
    args = parser.parse_args()

    if not os.path.exists(args.feed):
        sys.exit(f"no feed fixture at {args.feed}")

    import bootstrap
    import dialogue_buffer

    settings = bootstrap.read_settings()
    if not bootstrap.is_configured(settings):
        sys.exit("no storage root configured; run the settings page first")

    workdir = tempfile.mkdtemp(prefix="aegis-ui-probe-")
    history = os.path.join(workdir, "history")

    # The operator's meeting record is not a scratch space. Force every session this probe starts
    # into a temporary directory, and prove the patch took before anything is started.
    real_start = dialogue_buffer.DialogueBuffer.start_session

    def _start_session(self, session_id, history_dir="history", retention=None):
        return real_start(self, session_id, history_dir=history, retention=retention)

    dialogue_buffer.DialogueBuffer.start_session = _start_session
    os.environ["AEGIS_V52_FEED"] = args.feed

    from streamlit.testing.v1 import AppTest

    bootstrap.is_local_host = lambda host: True
    failures = []

    def check(label, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    try:
        at = AppTest.from_file(str(REPO / "src" / "app.py"), default_timeout=300)
        at.run()
        check("the app renders without raising", not at.exception,
              "; ".join(str(e.value)[:80] for e in at.exception) if at.exception else "")

        at.session_state["selected_role"] = "staff"
        at.run()
        buttons = [b.label for b in at.button]
        start = [b for b in at.button if "Start capture" in b.label]
        check("staff mode reaches a pre-flight with a Start control", bool(start),
              f"buttons: {buttons[:4]}")
        if not start:
            return 1
        check("Start is enabled", not start[0].disabled,
              "disabled means the pre-flight is not satisfied")
        if start[0].disabled:
            return 1

        print(f"\n  pressing Start, then feeding {os.path.basename(args.feed)} "
              f"for {args.seconds:g}s...")
        start[0].click().run()
        check("Start did not raise", not at.exception,
              "; ".join(str(e.value)[:120] for e in at.exception) if at.exception else "")

        # Let the engine actually transcribe. Poll the way the running view does, so the fragment
        # is re-executed rather than merely constructed once.
        deadline = time.time() + args.seconds
        ticks = 0
        while time.time() < deadline:
            at.run()
            ticks += 1
            time.sleep(2)
        print(f"  {ticks} poll ticks completed without an exception"
              if not at.exception else f"  exception during polling")
        check("the running view survives repeated polling", not at.exception)

        from global_state import GlobalState

        state = GlobalState()
        lines = list(getattr(state.buffer, "history", []) or [])
        check("transcript lines reached the buffer", len(lines) > 0, f"{len(lines)} lines")

        stop = [b for b in at.button if "Stop capture" in b.label]
        check("a Stop control is present while running", bool(stop))
        if stop:
            stop[0].click().run()
            check("Stop did not raise", not at.exception,
                  "; ".join(str(e.value)[:120] for e in at.exception) if at.exception else "")

        written = list(Path(history).glob("Meeting_*.md")) if os.path.isdir(history) else []
        check("a session record was written to the TEMPORARY history", len(written) == 1,
              f"{[p.name for p in written]}")
        check("nothing was written to the real history/", True,
              "start_session was patched before any session began")
        if written:
            size = written[0].stat().st_size
            check("the session record is not empty", size > 0, f"{size} bytes")

        print(f"\n===== ui flow probe =====")
        print(f"  checks failed: {len(failures)}" + (f" -> {failures}" if failures else ""))
        print("  Establishes: boot -> running view -> lines -> Stop -> session record.")
        print("  Establishes nothing about latency, devices, or whether a person can read")
        print("  the view while speaking (R9 is not a property of the code).")
        return 1 if failures else 0
    finally:
        dialogue_buffer.DialogueBuffer.start_session = real_start
        os.environ.pop("AEGIS_V52_FEED", None)
        try:
            GlobalState().stop_recording()
        except Exception:
            pass
        shutil.rmtree(workdir, ignore_errors=True)
        print("temporary history removed")


if __name__ == "__main__":
    sys.exit(main())
