"""The gate that decides what never reaches the record.

Every test here is about one asymmetry. A wrong `True` costs a false line, which is visible in the
transcript and which **R49**'s cleanup pass removes with a person watching. A wrong `False` deletes
what somebody said, leaves nothing behind saying so, and with retention off (**R16**) nothing
recovers it. **V64** settled the ranking — *noise costs a line, a destroyed answer costs the
record* — so the gate must fail open on every path, and that is what most of these pin.
"""
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import voice_gate  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_state():
    """The pipeline is a module global, cached once per process. Without this a failure in one
    test would be inherited as `_FAILED` by every test after it."""
    voice_gate._PIPELINE = None
    voice_gate._FAILED = False
    yield
    voice_gate._PIPELINE = None
    voice_gate._FAILED = False


# ===== Configuration =====

def test_the_gate_is_off_unless_it_is_turned_on():
    """A dependency appearing must not start discarding audio. The gate changes what reaches the
    record, so it is an act the operator takes, not a state the machine drifts into (**R41**)."""
    assert voice_gate.settings_from({})[0] is False
    assert voice_gate.settings_from({"VAD_GATE": ""})[0] is False
    assert voice_gate.settings_from({"VAD_GATE": "false"})[0] is False
    assert voice_gate.settings_from({"VAD_GATE": "no"})[0] is False


@pytest.mark.parametrize("raw", ["true", "True", "1", "yes", "on", " ON "])
def test_the_ways_an_operator_might_write_yes(raw):
    """`.env` is written by the form, but a human editing it by hand is the case that produces a
    silently-off gate someone believes is on."""
    assert voice_gate.settings_from({"VAD_GATE": raw})[0] is True


def test_the_floor_falls_back_rather_than_raising_on_nonsense():
    """A malformed number must not take the capture path down. It falls back to the measured knee
    (**V82**), which is the value the field ships with anyway."""
    assert voice_gate.settings_from({"VAD_MIN_SPEECH": "abc"})[2] == voice_gate.DEFAULT_MIN_SPEECH_S
    assert voice_gate.settings_from({"VAD_MIN_SPEECH": ""})[2] == voice_gate.DEFAULT_MIN_SPEECH_S
    assert voice_gate.settings_from({"VAD_MIN_SPEECH": "0.4"})[2] == 0.4


def test_an_empty_model_id_uses_the_ungated_default():
    """The default needs no Hugging Face token. An empty field must not become an empty repo id
    that fails at load time and silently disables the gate."""
    assert voice_gate.settings_from({})[1] == voice_gate.DEFAULT_MODEL_ID
    assert voice_gate.settings_from({"VAD_MODEL": "  "})[1] == voice_gate.DEFAULT_MODEL_ID


# ===== Failing open, which is the entire safety argument =====

def test_a_missing_package_transcribes_everything(monkeypatch):
    """The package is not importable on a machine that never installed it. The gate must then be
    exactly the behaviour that existed before it, not a filter that rejects everything."""
    monkeypatch.setattr(voice_gate, "_load", lambda model_id: None)
    assert voice_gate.has_speech([0.0] * 16000) is True


def test_a_pipeline_that_raises_mid_segment_transcribes_that_segment(monkeypatch):
    """An exception inside the detector is the case where a naive `try/except: return False` would
    quietly delete a hearing. It returns the audio to the decoder and says so in the log."""
    class _Exploding:
        def __call__(self, *_args, **_kwargs):
            raise RuntimeError("model died mid-inference")

    monkeypatch.setattr(voice_gate, "_load", lambda model_id: _Exploding())
    assert voice_gate.has_speech([0.0] * 16000) is True


def test_a_load_failure_is_recorded_once_and_not_retried_per_segment(monkeypatch):
    """A failing import retried on every segment would add its cost to the live path forever.
    `_FAILED` latches, and the observable is that the second call does not attempt a load."""
    attempts = []

    def _boom(name):
        attempts.append(name)
        raise ImportError("no pyannote here")

    monkeypatch.setattr(voice_gate, "available", lambda: False)
    monkeypatch.setitem(sys.modules, "pyannote.audio", None)
    monkeypatch.setattr("builtins.__import__", _real_import_that_fails_for_pyannote(_boom))

    assert voice_gate.has_speech([0.0] * 16000) is True
    first = len(attempts)
    assert voice_gate.has_speech([0.0] * 16000) is True
    assert len(attempts) == first, "a failed load must latch, not retry once per segment"


def _real_import_that_fails_for_pyannote(on_pyannote):
    """Fail only `pyannote.*` imports; everything else imports normally."""
    import builtins

    real = builtins.__import__

    def _patched(name, *args, **kwargs):
        if name.startswith("pyannote"):
            return on_pyannote(name)
        return real(name, *args, **kwargs)

    return _patched


# ===== The decision itself, with the detector stubbed =====

def _pipeline_returning(*durations):
    """A stand-in whose timeline reports the given speech durations."""
    segments = [types.SimpleNamespace(duration=d) for d in durations]
    timeline = types.SimpleNamespace(get_timeline=lambda: segments)
    return lambda _payload: timeline


def test_speech_above_the_floor_is_transcribed(monkeypatch):
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning(0.9))
    assert voice_gate.has_speech([0.0] * 16000, min_speech_s=0.25) is True


def test_a_transient_below_the_floor_is_not(monkeypatch):
    """Measured on the corpus: with no floor the detector calls a 0.24 s chime transient speech,
    while real speech fills the window. The floor is what separates them (**V82**)."""
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning(0.24))
    assert voice_gate.has_speech([0.0] * 16000, min_speech_s=0.25) is False


def test_speech_split_across_pauses_is_summed_not_maximised(monkeypatch):
    """Three 0.1 s bursts are 0.3 s of speech. Taking the longest run instead would discard a
    hesitant sentence -- exactly the quiet, broken speech V82 shows is the expensive thing to
    lose."""
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning(0.1, 0.1, 0.1))
    assert voice_gate.has_speech([0.0] * 16000, min_speech_s=0.25) is True


def test_silence_produces_no_timeline_and_is_rejected(monkeypatch):
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning())
    assert voice_gate.has_speech([0.0] * 16000, min_speech_s=0.25) is False


# ===== The wiring, which is the code that was actually written today =====

def _run_processing_with(monkeypatch, gate, verdict):
    """Push three speech-flagged chunks through `_processing_thread` and return the queue depth.

    Exercises the real method rather than a copy of its logic: the gate's whole point is *where*
    it sits, and a test that re-implemented the loop could not tell the queue was skipped.
    """
    import queue as _queue
    import threading
    import time

    import numpy as np
    import transcriber as tr

    monkeypatch.setattr(tr, "NPU_LOCK", threading.Lock())
    monkeypatch.setattr(tr, "resolve_backend", lambda model_path: ("stub", lambda audio: ""))
    monkeypatch.setattr(voice_gate, "has_speech",
                        lambda *args, **kwargs: verdict)

    t = tr.Transcriber(device_idx=None, role="Participant", buffer_instance=object(), gate=gate)
    t.is_running = True

    # One second of "speech" then enough silence to close the segment.
    chunk = (np.zeros(t.block_size) * 32767).astype(np.int16)
    for _ in range(40):
        t.audio_queue.put((chunk, True))
    for _ in range(20):
        t.audio_queue.put((chunk, False))

    thread = threading.Thread(target=t._processing_thread, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and t.audio_queue.qsize():
        time.sleep(0.05)
    time.sleep(0.2)
    t.is_running = False
    thread.join(timeout=5.0)
    return t.inference_queue.qsize()


def test_a_rejected_segment_never_reaches_the_inference_queue(monkeypatch):
    """**Not merely "is not transcribed".** Screening inside the inference thread would save the
    decode and leave the segment queued, and V81 measured a 3311 ms dwell behind exactly that
    queue. The gate earns its place by keeping the queue short as well (**V83**, **R9**)."""
    assert _run_processing_with(monkeypatch, gate=(True, "m", 0.25), verdict=False) == 0


def test_an_accepted_segment_is_queued_as_before(monkeypatch):
    assert _run_processing_with(monkeypatch, gate=(True, "m", 0.25), verdict=True) >= 1


def test_with_the_gate_off_nothing_is_screened_even_if_it_would_reject(monkeypatch):
    """Off is off. The stubbed detector would reject every segment; the disabled gate must not
    consult it at all, which is what keeps the default behaviour byte-identical to before."""
    assert _run_processing_with(monkeypatch, gate=None, verdict=False) >= 1


# ===== Whether the gate is live at all, which is the thing nothing could see (V91) =====

def test_an_unavailable_gate_reports_itself_as_not_live(monkeypatch):
    """The failure this exists for. Three overnight soaks and V86's hour ran with the gate failed
    open and published themselves as *gate on*, because failing open is indistinguishable from a
    healthy ungated run in every number a soak prints (**V91**)."""
    monkeypatch.setattr(voice_gate, "_load", lambda model_id: None)
    assert voice_gate.is_live() is False


def test_a_gate_that_rejects_silence_is_live(monkeypatch):
    """Two seconds of zeros carry no speech, so a working pipeline rejects them. This is the whole
    discriminator: `has_speech` returns `True` on every failure path, so a `False` cannot come from
    a gate that did not run."""
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning())
    assert voice_gate.is_live() is True


def test_a_pipeline_that_calls_silence_speech_is_not_trusted_as_live(monkeypatch):
    """A detector that accepts digital zeros is not screening anything, whatever it loaded from.
    `is_live` reports the behaviour rather than the presence of an object."""
    monkeypatch.setattr(voice_gate, "_load", lambda m: _pipeline_returning(5.0))
    assert voice_gate.is_live() is False


def test_the_probe_is_two_seconds_at_the_rate_it_was_given(monkeypatch):
    """The sample count matters: a probe shorter than the floor would read as *not live* on a
    perfectly good gate. Pinned so the duration cannot drift below `DEFAULT_MIN_SPEECH_S`."""
    seen = {}

    def _capture(audio, model_id="", min_speech_s=None, sample_rate=voice_gate.TARGET_SR):
        seen["samples"] = len(audio)
        seen["rate"] = sample_rate
        seen["floor"] = min_speech_s
        return False

    monkeypatch.setattr(voice_gate, "has_speech", _capture)
    assert voice_gate.is_live(sample_rate=8000) is True
    assert seen["samples"] == 16000, "two seconds at the rate given, not a fixed sample count"
    assert seen["rate"] == 8000
    assert seen["floor"] == voice_gate.DEFAULT_MIN_SPEECH_S
    assert seen["samples"] / seen["rate"] > voice_gate.DEFAULT_MIN_SPEECH_S
