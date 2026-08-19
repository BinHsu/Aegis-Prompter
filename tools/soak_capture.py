"""Run capture for an hour through the real device path, and report whether it degrades.

This is the mechanical half of "prove it in a real meeting" (**R7**). A meeting settles two things
at once — does the machinery hold up, and is the transcript usable from a podium — and only the
second needs a person. This measures the first, so that a real meeting is spent on judgement rather
than on discovering that the tap dies at minute forty.

**What makes this different from the NPU_LOCK trial**, which also ran an hour: that fed WAVs
straight to the transcriber and never opened a device. Here the Participant track goes through the
whole real path — audio played to the system output, captured by the Core Audio tap, read back
through PortAudio — which is the part that has only ever been exercised for seconds at a time.

**Two modes, and they soak different devices.** The default is the original one; `--microphone`
closes the hole the original left open, and is the second of the two fixtures 7.5 still needs.

    default (--mute safe, silent):
      Participant  track_A.wav -> afplay -> system output -> tap -> PortAudio -> transcriber
      Speaker      track_B.wav -> AEGIS_V52_FEED -> the transcriber's queue directly

    --microphone (audible by necessity):
      Participant  track_A.wav -> afplay -> system output -> tap -> PortAudio -> transcriber
      Speaker      the room    -> built-in microphone -> sd.InputStream -> transcriber

**Why the default leaves a hole.** Feeding the Speaker track from a WAV keeps both tracks
contending for the NPU — which is what makes it a two-track soak — but the microphone is then never
opened. **V65** ran the hour that way, so the tap has an hour behind it and the microphone has
seconds (**V62**). `--microphone` unsets the lab feed, which is all it takes: `start_recording`
opens a real `sd.InputStream` whenever `AEGIS_V52_FEED` is absent.

**`--microphone` refuses `--mute`, and the reason is not symmetry.** Muting does not affect the tap
— measured 2026-08-12, peak 0.2558 at volume 0, identical to volume 50, because the tap reads the
mix before device volume is applied — which is what lets the default run silently. The microphone
has no such shortcut: it hears the room or it hears nothing, so a muted run would soak an open
stream carrying silence and report success. That is this codebase's characteristic failure, not a
measurement.

**It also refuses a machine that was *already* muted, and that hole cost a stage.** The original
guard blocked the flag and never asked the machine's state. A 3-minute stage on 2026-08-12 came back
looking healthy — 38 Participant lines with correct code-switched text, `mic_rms` moving across every
sample, zero warnings, zero exceptions — while `output muted` was `true` the whole time, so the
speakers emitted nothing and the microphone logged **0 transcribed lines**. Nothing in the summary
said "muted"; the tap looked perfect precisely because it reads the mix before device volume. The
pre-flight now exits instead. **A guard against an argument is not a guard against a state.**

**Expect a poor transcript on the Speaker track, and do not treat that as the result.** Room
acoustics plus the leakage **V62** measured mean the microphone hears an attenuated copy of what
the speakers are playing, and the model invents short fluent utterances from exactly that kind of
input (**V60**). The question here is device durability over an hour, which a poor transcript
answers as well as a good one. What *would* be a finding is the microphone going quiet: the report
below tracks `last_rms` across samples, because a stream that stops delivering callbacks stays
`active` and produces no error.

**Escalate 3 -> 10 -> 60 minutes; do not start at 60.** Stated by the operator 2026-08-12: *do not
let a broken thing run for an hour.* `--minutes` already takes the value, so staging costs nothing
and each stage answers a different question, with its own reason to stop:

| Stage | The question | Stop here if |
|---|---|---|
| **3 min** | does this path work at all today? | either stream failed to open and be named in the log (mic `[N] MacBook Pro Microphone`, Participant `[N] Aegis System Audio`), or **either role emits zero transcribed lines**. The tap needing two attempts to appear is normal (**V61**), not a failure |

**Judge stage 1 on per-role line counts, not on `mic_rms`.** Measured 2026-08-12, back to back: the
muted stage read `mic_rms` 0.0031–0.0070 and the audible re-run read 0.0033–0.0046. **The audible run
is not the higher one.** RMS is dominated by whatever the room is doing between utterances, so
"moving across every sample" is satisfied by ambient noise alone and cannot distinguish a live room
from a dead one. What separates them is unambiguous: 0 Speaker lines muted, 18 audible in the same
three minutes. The report prints per-role counts and omits a role at zero — read the *absence* of a
row as the finding it is.
| **10 min** | does it start degrading immediately? | latency medians drift against the 3-minute run, `mic_rms` stops moving, the line rate falls, `Audio queue full` appears, or `peak_mlx_mb` climbs **above 3578 MB** -- that figure is the two-track plateau (**V58**, **V67**), not a climb, because the second `Transcriber` shares weights and adds only ~371 MB |
| **60 min** | does the microphone device survive an hour? | `mic_rms` reaches zero or callbacks stall -- **that moment is the answer; stop, do not run out the hour** |

Only the last stage needs the full hour, and only because "an hour" is the question rather than an
inherited fixture length. Fix and re-run the *short* stage after any failure; never promote a stage
that did not pass.

**`Audio queue full` has always been visible on *this* path**, and an earlier draft of the table said
it was newly visible. It is not: `global_state.py` calls `logging.basicConfig` with a
`StreamHandler` and a `FileHandler` at import, and this tool imports `GlobalState`, so warnings have
always reached `logs/`. The swallowed-warning fix (`ccab813`) was to `npu_lock_trial.py`'s child,
which is a separate entry point that never calls `basicConfig`. Worth keeping straight, because
believing the warnings are new invites distrusting older soak logs that were in fact complete.

**Hold sleep off, and do not confuse the two kinds.** On battery this machine idles to sleep after
**1 minute** (`pmset -g custom`), and the assertions that happen to be up -- an agent session's
renewing `caffeinate`, `coreaudiod` holding the mic open -- expire without warning. Wrap the run:
`caffeinate -i` prevents *idle* sleep and nothing else. It does **not** prevent **clamshell** sleep,
which is what cost **V67** 80 minutes of its hour, so the lid stays open. Afterwards, confirm rather
than assume: `pmset -g log | grep -E "Clamshell|Wake from"`.

Run:  PYTHONPATH="$PWD" .venv/bin/python tools/soak_capture.py [--minutes 60] [--mute]
      caffeinate -i env PYTHONPATH="$PWD" .venv/bin/python tools/soak_capture.py \
          --microphone --minutes 3 --sample-every 20      # then 10, then 60
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

FIXTURES = os.path.join(REPO, "fixtures", "asr", "conversation")
TRACK_PARTICIPANT = os.path.join(FIXTURES, "track_A.wav")
TRACK_SPEAKER = os.path.join(FIXTURES, "track_B.wav")

LOG_LINE = re.compile(
    r"^(?P<time>[\d\-]+ [\d:,]+) .*\[(?P<role>[^\]]+)\] Transcribed in (?P<ms>\d+)ms: (?P<text>.*)$"
)

# `queue` is the dwell in `inference_queue`, instrumented 2026-08-12. It is stamped at completion,
# so a line at t having queued q and inferred i occupied [t-i, t] on the accelerator and waited in
# [t-i-q, t-i] before that. Dwell can only be non-zero while another segment holds the worker, so
# the figure worth reporting is its distribution split by whether a *different role* was mid-
# inference -- V67's contention definition, applied to a real device path instead of a fed WAV.
SEGMENT_LINE = re.compile(
    r"^(?P<time>[\d\-]+ [\d:]+),(?P<msec>\d+) .*\[(?P<role>[^\]]+)\] "
    r"Segment (?P<seg>[\d.]+)s: queue (?P<queue>\d+)ms, inference (?P<inf>\d+)ms"
)


def newest_log():
    logs = sorted((os.path.join(REPO, "logs", f) for f in os.listdir(os.path.join(REPO, "logs"))
                   if f.endswith(".log")), key=os.path.getmtime)
    return logs[-1] if logs else None


def parse_segments(lines):
    """Every `Segment ...` line as a window pair: when inference held the accelerator, and the
    dwell before it. Split out of the report so the arithmetic is testable without an hour of
    audio -- the previous version was only exercised by the run whose result it summarises."""
    segments = []
    for line in lines:
        m = SEGMENT_LINE.match(line.strip())
        if not m:
            continue
        end = time.mktime(time.strptime(m.group("time"), "%Y-%m-%d %H:%M:%S"))
        end += int(m.group("msec")) / 1000.0
        inf, queue = int(m.group("inf")), int(m.group("queue"))
        # `seg` is kept because inference scales with segment length (**V66**: 715 / 1076 / 1790 ms
        # for 3.03 / 6.76 / 15.0 s), which makes it the control for a real confound: labelling a
        # segment "contended" requires its window to intersect another role's, and a longer window is
        # mechanically likelier to intersect one. Any contended-vs-solo comparison must be made
        # within comparable durations or it is measuring length.
        segments.append({"role": m.group("role"), "queue": queue, "inf": inf, "end": end,
                         "seg": float(m.group("seg")), "inf_start": end - inf / 1000.0})
    return segments


def mark_contended(segments):
    """Flag segments whose inference window intersects one on a *different* role -- V67's
    definition. Same-role overlap is not contention: one worker per role means its own segments
    cannot be mid-inference simultaneously, so an apparent overlap there is a clock artefact."""
    for s in segments:
        s["contended"] = any(
            o is not s and o["role"] != s["role"]
            and s["inf_start"] < o["end"] and o["inf_start"] < s["end"]
            for o in segments
        )
    return segments


def sample_memory():
    """Peak MLX memory in MB. `ps` under-reports this by gigabytes -- see the bake-off notes."""
    try:
        import mlx.core as mx
        return round(mx.get_peak_memory() / (1024 * 1024), 1)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=60.0)
    parser.add_argument(
        "--model", default="",
        help="Override ASR_MODEL for this run only. **Not a convenience.** `.env` is written by "
             "the app and never by hand (R18, R32), and it survives a version change -- so an "
             "operator whose stored id was removed on provenance grounds (R50) cannot soak the "
             "*new* model until they re-save the settings form. Measuring must not require "
             "editing their configuration, and must not silently paper over the fact that the "
             "product will refuse to start until they do.")
    parser.add_argument("--gate", action="store_true",
                        help="Enable the voice-activity gate for this soak. It gets its own flag "
                             "rather than reading `.env` for the same reason `--model` does: the "
                             "gate is new code (docs/decisions/0013), and an hour is the only "
                             "thing that answers whether it leaks or degrades.")
    parser.add_argument("--gate-min-speech", type=float, default=0.25)
    parser.add_argument("--retain", action="store_true",
                        help="Arm dual-track audio retention for this soak and check what lands "
                             "on disk. 7.7 shipped the toggle in 2026-08-13 and **no run has ever "
                             "written a retained file**, so R2's promise that the two tracks are "
                             "never mixed has only been argued, never observed as two files. "
                             "Writes under the configured archive directory, which is the "
                             "operator's storage root -- the check below reports sizes and "
                             "durations and never the contents.")
    parser.add_argument("--sample-every", type=float, default=30.0)
    parser.add_argument("--mute", action="store_true", help="silence the output for the duration")
    parser.add_argument("--microphone", action="store_true",
                        help="soak the built-in microphone too: open the real input device instead "
                             "of feeding the Speaker track from a WAV, and let it hear the room")
    args = parser.parse_args()

    if args.microphone and args.mute:
        # Not a symmetry check. The tap is unaffected by output volume (measured), so the default
        # mode may run silent; the microphone has no such path and would soak an open stream
        # carrying nothing while reporting success.
        sys.exit("--microphone cannot be combined with --mute: a muted room gives the microphone "
                 "nothing to hear, and the run would report a successful hour of silence.")

    if args.microphone:
        # The guard above refuses to mute the machine; it never asked what state the machine was
        # already in. A run started on a muted system produced a clean-looking 3 minutes on
        # 2026-08-12 -- 38 Participant lines, correct code-switched text, RMS moving, zero
        # warnings -- and 0 lines on the microphone, because the tap reads the mix before device
        # volume while the speakers emitted nothing. Refusing here rather than reporting it in the
        # summary, since the summary is what looked fine.
        muted = subprocess.run(["osascript", "-e", "output muted of (get volume settings)"],
                               capture_output=True, text=True).stdout.strip()
        level = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                               capture_output=True, text=True).stdout.strip()
        if muted == "true" or level in ("0", "missing value"):
            sys.exit(f"--microphone needs the speakers audible: output muted={muted} volume={level}. "
                     "The tap would still transcribe perfectly (it reads the mix before device "
                     "volume), so this failure does not announce itself -- the microphone simply "
                     "soaks an open stream carrying room noise and the run reports success.\n"
                     "  osascript -e 'set volume output volume 35' -e 'set volume without output muted'")

    for path in (TRACK_PARTICIPANT, TRACK_SPEAKER):
        if not os.path.exists(path):
            sys.exit(f"missing fixture: {path}\n  build it with tools/build_conversation_fixture.py")

    import bootstrap
    settings = bootstrap.read_settings()
    if not bootstrap.is_configured(settings):
        sys.exit("no storage root configured")
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    # Feeding the Speaker track from a WAV is the existing lab hook; it also tells `start_recording`
    # not to open the microphone. Absent, a real `sd.InputStream` opens -- which is the whole of
    # what `--microphone` does.
    if args.microphone:
        os.environ.pop("AEGIS_V52_FEED", None)
    else:
        os.environ["AEGIS_V52_FEED"] = TRACK_SPEAKER

    import audio_devices
    import system_audio
    from global_state import GlobalState

    volume = None
    if args.mute:
        volume = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                                capture_output=True, text=True).stdout.strip()
        subprocess.run(["osascript", "-e", "set volume output volume 0"], check=False)

    state = GlobalState()
    print(f"backend: {system_audio.available_backend()}", flush=True)
    configured = (settings.get("ASR_MODEL") or "").strip()
    asr_model = args.model.strip() or configured or None
    if args.model.strip() and configured and args.model.strip() != configured:
        print(f"NOTE: soaking {asr_model!r}; `.env` still says {configured!r}. The product will "
              f"refuse to start until that is changed from the settings page.", flush=True)
    gate = (True, "", args.gate_min_speech) if args.gate else None
    if args.gate:
        # V91: this used to print "gate: ON" and mean nothing. The gate fails open, so an
        # unavailable one transcribes every segment and every number below still looks healthy --
        # three overnight soaks and V86's hour were published as gate-on that way. Probe it, and
        # refuse rather than mislabel: a measurement that silently measures the opposite of its
        # label is worse than one that did not run.
        import voice_gate
        if not voice_gate.is_live():
            sys.exit("REFUSING: --gate was asked for and the gate is not live. It failed open, so "
                     "this run would transcribe every segment and report itself as gated (V91). "
                     "The weights are ivrit-ai/pyannote-segmentation-3.0 under the product's "
                     "HF_HOME; the log above says why the load failed. Fix that, or drop --gate "
                     "and label the run ungated.")
        print(f"gate: ON and verified live, floor {args.gate_min_speech}s", flush=True)
    state.warm_up(asr_model=asr_model,
                  mic_device=(settings.get("MIC_DEVICE") or "").strip(),
                  gate=gate)
    log_path = newest_log()
    print(f"warm — participant {state.other_name!r}; log {log_path}", flush=True)

    scratch = os.environ.get("CLAUDE_JOB_DIR", "/tmp")
    scratch = os.path.join(scratch, "tmp") if os.path.isdir(os.path.join(scratch, "tmp")) else scratch
    samples_path = os.path.join(scratch, "soak_samples.jsonl")

    recording_kwargs = {}
    if args.retain:
        archive_dir = bootstrap.resolve_archive_dir(settings)
        recording_kwargs = {"archive_audio": True, "archive_dir": archive_dir}
        print(f"retention: ARMED -> {archive_dir}", flush=True)
    started = time.monotonic()
    player = None
    try:
        state.start_recording(enable_rag=False, **recording_kwargs)
        print(f"capture live — backend {state.audio_backend}", flush=True)
        if args.microphone:
            me = state.transcriber_me
            opened = getattr(me, "device_name", None) if me else None
            idx = getattr(me, "device_idx", None) if me else None
            print(f"microphone — name={opened!r} idx={idx} "
                  f"stream={'open' if getattr(me, 'stream', None) is not None else 'MISSING'}",
                  flush=True)
            if me is None or getattr(me, "stream", None) is None:
                # Nothing downstream would notice: the soak would run its hour and report a
                # microphone that produced no lines, which looks like a quiet room.
                raise RuntimeError("--microphone asked for a real input stream and none opened")
        player = subprocess.Popen(["afplay", TRACK_PARTICIPANT],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        deadline = started + args.minutes * 60
        with open(samples_path, "w", encoding="utf-8") as samples:
            while time.monotonic() < deadline:
                time.sleep(args.sample_every)
                elapsed = time.monotonic() - started
                me = state.transcriber_me
                stream = getattr(me, "stream", None) if me else None
                entry = {
                    "elapsed_s": round(elapsed, 1),
                    "peak_mlx_mb": sample_memory(),
                    # Saturates at 15 and stays there: `DialogueBuffer(max_history=15)` is a rolling
                    # window for the view, not a counter. It plateaus a couple of minutes into every
                    # run and that is not a stall -- judge line rate from the per-role log counts in
                    # the report, never from this field.
                    "buffer_lines": len(state.buffer.get_full_dialogue()),
                    "tap_alive": state._tap is not None and state._tap.process is not None,
                    "player_alive": player.poll() is None,
                    # A stream that stops delivering callbacks stays `active` and raises nothing,
                    # so aliveness is `last_rms` moving -- not the flag beside it.
                    "mic_stream_active": bool(getattr(stream, "active", False)),
                    "mic_rms": round(float(getattr(me, "last_rms", 0.0) or 0.0), 8) if me else None,
                }
                samples.write(json.dumps(entry) + "\n")
                samples.flush()
                if int(elapsed) % 300 < args.sample_every:
                    print(f"  {elapsed/60:.0f} min — {entry['buffer_lines']} lines, "
                          f"{entry['peak_mlx_mb']} MB, tap={entry['tap_alive']}", flush=True)
    finally:
        if player and player.poll() is None:
            player.terminate()
        print("stopping...", flush=True)
        state.stop_recording()
        if volume:
            subprocess.run(["osascript", "-e", f"set volume output volume {volume}"], check=False)

    # ---- Retention: what actually landed on disk ----------------------------------------
    # R2 says the two tracks are never mixed, and until this ran that was a statement about the
    # code rather than about two files. Sizes, durations and RMS only -- the audio is the
    # operator's and is never read back into a log.
    if args.retain:
        import wave
        import audio_archive
        print("\n===== retention =====", flush=True)
        session_id = getattr(state.buffer, "session_id", None) or ""
        expected = args.minutes * 60
        seen = {}
        for track in (audio_archive.TRACK_MIC, audio_archive.TRACK_SYSTEM):
            path = audio_archive.track_path(archive_dir, session_id, track)
            if not os.path.exists(path):
                print(f"  {track:<7} MISSING at {os.path.basename(path)}")
                continue
            with wave.open(path, "rb") as wav:
                frames, rate, width, channels = (wav.getnframes(), wav.getframerate(),
                                                 wav.getsampwidth(), wav.getnchannels())
                wav.setpos(0)
                raw = wav.readframes(min(frames, rate * 5))
            seconds = frames / rate if rate else 0.0
            seen[track] = {"path": path, "seconds": seconds, "bytes": os.path.getsize(path),
                           "rate": rate, "head": hashlib.sha256(raw).hexdigest()[:16]}
            drift = seconds - expected
            print(f"  {track:<7} {seconds:7.1f}s ({drift:+.1f}s vs the soak)  "
                  f"{os.path.getsize(path):>12,} bytes  {rate} Hz  {channels}ch {width * 8}-bit")
        if len(seen) == 2:
            a, b = seen[audio_archive.TRACK_MIC], seen[audio_archive.TRACK_SYSTEM]
            print(f"  distinct files: {a['path'] != b['path']}")
            print(f"  first 5s differ: {a['head'] != b['head']}   "
                  f"(identical heads would mean one stream was written to both -- R2)")
        else:
            print("  ONE OR BOTH TRACKS ABSENT -- retention did not deliver two files")

    # ---- Report -------------------------------------------------------------------------
    print("\n===== soak result =====", flush=True)
    rows = [json.loads(line) for line in open(samples_path, encoding="utf-8")]
    if rows:
        print(f"  duration          {rows[-1]['elapsed_s']/60:.1f} min")
        print(f"  peak MLX memory   {rows[0]['peak_mlx_mb']} MB -> {rows[-1]['peak_mlx_mb']} MB")
        print(f"  tap alive at end  {rows[-1]['tap_alive']}")
        dropped = [r for r in rows if not r["tap_alive"]]
        if dropped:
            print(f"  ❌ tap died at {dropped[0]['elapsed_s']/60:.1f} min")

    if args.microphone and rows:
        # The failure to catch is not an exception -- it is the stream going quiet while every flag
        # still reads healthy. `last_rms` is reassigned on every callback from real audio, so an
        # identical value across consecutive samples means no callback arrived between them.
        print(f"\n  microphone stream active at end  {rows[-1]['mic_stream_active']}")
        values = [r.get("mic_rms") for r in rows]
        silent = sum(1 for v in values if not v)
        longest = current = 1
        for prev, nxt in zip(values, values[1:]):
            current = current + 1 if prev == nxt else 1
            longest = max(longest, current)
        print(f"  mic RMS  first {values[0]}  last {values[-1]}  distinct {len(set(values))}"
              f"/{len(values)}")
        if silent:
            print(f"  ⚠️  {silent}/{len(values)} samples had zero RMS — the input heard nothing")
        if longest > 2:
            print(f"  ❌ RMS frozen across {longest} consecutive samples "
                  f"(~{longest * args.sample_every / 60:.1f} min) — callbacks stopped")
        elif not silent:
            print("  ✅ RMS moved between every sample — callbacks arrived for the whole run")
        inactive = [r for r in rows if not r["mic_stream_active"]]
        if inactive:
            print(f"  ❌ stream went inactive at {inactive[0]['elapsed_s']/60:.1f} min")

    # Latency by fifth of the run: the question is drift, which a median over the whole hour hides.
    entries = []
    if log_path:
        for line in open(log_path, encoding="utf-8", errors="replace"):
            m = LOG_LINE.match(line.strip())
            if m:
                entries.append((m.group("role"), int(m.group("ms"))))
    by_role = {}
    for role, ms in entries:
        by_role.setdefault(role, []).append(ms)
    print(f"\n  transcribed lines: " + ", ".join(f"{r}={len(v)}" for r, v in by_role.items()))
    for role, values in by_role.items():
        fifth = max(1, len(values) // 5)
        chunks = [values[i:i + fifth] for i in range(0, len(values), fifth)][:5]
        medians = [sorted(c)[len(c) // 2] for c in chunks if c]
        print(f"  {role} median ms by fifth: {medians}")
        if len(medians) >= 2 and medians[-1] > medians[0] * 1.5:
            print(f"    ⚠️  last fifth is {medians[-1]/medians[0]:.1f}x the first — drift")

    if args.microphone and "Speaker (You)" not in by_role:
        # A role at zero used to be invisible here: `by_role` simply had no key for it, and a report
        # listing only the Participant read as a quiet room. It is the signature of a muted machine,
        # which the pre-flight now refuses -- so reaching this means something else took the mic.
        print("  ❌ the microphone produced ZERO transcribed lines — this is not a soak of it")

    # Queue dwell, split by observed contention. Reported here rather than left to a scratch script
    # because a bare median of 0 ms is compatible with a long tail, and the tail is what R9 feels.
    segments = []
    if log_path:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            segments = mark_contended(parse_segments(handle))
    if segments:
        allq = sorted(s["queue"] for s in segments)
        contended = [s for s in segments if s["contended"]]
        print(f"\n  queue dwell over {len(segments)} segments: median {allq[len(allq)//2]} ms, "
              f"max {allq[-1]} ms, non-zero {sum(1 for q in allq if q > 0)}/{len(allq)}")
        print(f"  contended segments (another role mid-inference): "
              f"{len(contended)}/{len(segments)} = {100*len(contended)/len(segments):.0f}%")
        if contended:
            cq = sorted(s["queue"] for s in contended)
            print(f"    of those: queue median {cq[len(cq)//2]} ms, max {cq[-1]} ms, "
                  f"non-zero {sum(1 for q in cq if q > 0)}/{len(cq)}")
        else:
            # Zero dwell with no collisions is not evidence about dwell under collision.
            print("    ⚠️  no overlapping inference windows in this run — the dwell figure above "
                  "says nothing about contention, only that a lone worker never waits")

    if log_path:
        text = open(log_path, encoding="utf-8", errors="replace").read()
        print(f"\n  'Audio queue full' warnings: {text.count('Audio queue full')}")
        print(f"  inference-thread exceptions:  {text.count('Exception in inference thread')}")
        print(f"  network requests:             {text.count('huggingface.co')}")

    leftover = any(d["name"] == system_audio.TAP_DEVICE_NAME
                   for d in audio_devices.list_input_devices())
    print(f"  tap device left behind:       {leftover}")
    print(f"\n  samples: {samples_path}\n  log:     {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
