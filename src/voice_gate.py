"""Decide whether a segment contains speech, before it costs a decode.

**Why this exists.** The shipped ASR model invents an utterance from 252 of 253 real non-speech
segments (**V72**) and from every music segment tested, including verbatim sung lyrics (**V79**).
Five decoding configurations changed that by nothing at all (**V73**), because the model's
no-speech probability is `0.000` on non-speech — the gate Whisper has cannot arm. What does work
is not decoding the segment: a neural detector in front of the model rejects 65% of non-speech for
3% of real speech (**V82**), which is what `faster-whisper` and WhisperX have shipped all along
and structurally what the removed model did internally (**V77**).

**It is also a latency win, which is not the usual shape of a safety feature.** The detector costs
**32 ms** on CPU; a non-speech decode costs **2235 ms** (**V75**). Every rejection nets back about
two seconds, and rejected audio never enters `inference_queue`, so the 3311 ms queue dwell **V81**
measured gets shorter as well as cheaper. Same answer to **R37** and to **R9**.

**CPU on purpose.** Metal is 10 ms faster and shares the accelerator that `NPU_LOCK` exists to
serialise; a second consumer there costs more than it saves.

**It fails open, and that is the whole safety argument.** Any error — package missing, weights
absent, model refusing to load, an exception mid-inference — passes the audio through to the
decoder. A gate that fails closed would silently delete a hearing. **V64** settled the ranking that
governs this: *noise costs a line, a destroyed answer costs the record* (**R3**). A false line is
visible and survivable; a swallowed answer is neither.

**Not in `text_filters.py`.** That module's contract is that it grows no dependency, so its pure
boundary tests run anywhere. This one is nothing but a dependency.
"""
import logging
import os
import threading

logger = logging.getLogger("VoiceGate")

# Ungated, so no Hugging Face token is needed. `src/diarize.py` verified every piece of this path
# against the Hub on 2026-08-17. It is a **third-party re-host** of pyannote's weights, which is a
# supply-chain judgement rather than a free lunch -- named here so a reader meets it rather than
# inherits it (**R50**, `docs/decisions/0013`).
DEFAULT_MODEL_ID = "ivrit-ai/pyannote-segmentation-3.0"

# Seconds of detected speech a segment needs to survive. **The knee, not a guess** (**V82**): at
# 0.25 s the detector rejects 65% of non-speech for 3% of real speech, and every larger value is a
# worse bargain than the one before -- 0.40 s buys 23 more rejections for 19 destroyed utterances,
# 0.60 s buys 11 more for 31. The product's own minimum segment is 0.3 s.
DEFAULT_MIN_SPEECH_S = 0.25

TARGET_SR = 16000

_LOCK = threading.Lock()
_PIPELINE = None
_FAILED = False


def available():
    """Whether the package is importable at all. No weights are fetched."""
    try:
        import importlib.util
        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


def _load(model_id):
    """Build the pipeline once per process. Returns `None` if anything at all goes wrong.

    Loaded lazily rather than at import: the pre-flight panel and the settings screen must open
    without paying for a model (**R25**, **V19**), and nothing is loaded until Start is pressed.
    """
    global _PIPELINE, _FAILED
    with _LOCK:
        if _PIPELINE is not None or _FAILED:
            return _PIPELINE
        try:
            import torch
            from pyannote.audio import Model
            from pyannote.audio.pipelines import VoiceActivityDetection

            segmentation = Model.from_pretrained(model_id)
            pipeline = VoiceActivityDetection(segmentation=segmentation)
            pipeline.instantiate({"min_duration_on": 0.0, "min_duration_off": 0.0})
            pipeline.to(torch.device("cpu"))
            _PIPELINE = pipeline
            logger.info("[VoiceGate] %s loaded on CPU; segments below the speech floor will not "
                        "be transcribed.", model_id)
        except Exception as exc:
            _FAILED = True
            logger.warning("⚠️ [VoiceGate] unavailable (%s: %s). Every segment will be "
                           "transcribed, as it was before this gate existed.",
                           type(exc).__name__, exc)
        return _PIPELINE


def has_speech(audio, model_id="", min_speech_s=None, sample_rate=TARGET_SR):
    """Whether `audio` carries enough speech to be worth decoding. **Never raises.**

    Returns `True` on every failure path, including the gate being unavailable. The caller is the
    live capture loop and the alternative to a wrong `True` is a wrong `False`, which deletes a
    participant's sentence with no record that it happened (**R3**, **V64**).
    """
    pipeline = _load(model_id or DEFAULT_MODEL_ID)
    if pipeline is None:
        return True
    floor = DEFAULT_MIN_SPEECH_S if min_speech_s is None else min_speech_s
    try:
        import torch

        waveform = torch.as_tensor(audio, dtype=torch.float32).reshape(1, -1)
        output = pipeline({"waveform": waveform, "sample_rate": sample_rate})
        speech = sum(segment.duration for segment in output.get_timeline())
        return speech >= floor
    except Exception as exc:
        logger.warning("⚠️ [VoiceGate] segment not screened (%s: %s); transcribing it.",
                       type(exc).__name__, exc)
        return True


def settings_from(values):
    """`(enabled, model_id, min_speech_s)` from the settings mapping. Pure; no I/O.

    **Enabled unless explicitly turned off, since 2026-08-20** (`docs/decisions/0015`). This
    previously read "off unless explicitly enabled", on the **R41** reasoning that a gate which
    starts discarding audio *because a dependency appeared* would be a behaviour change nobody asked
    for. **That reasoning stands and is not what changed.** The default flipped on a deliberate,
    recorded decision after **V97** measured an hour with the gate genuinely live, and this function
    still reads the setting rather than the presence of the package -- so an appearing dependency
    still changes nothing by itself.

    The value here is what `.env` says; the shipped default lives in `bootstrap.SETTINGS_FIELDS`.
    An empty or unparseable value is off, which keeps a hand-mangled `.env` from silently enabling
    screening.
    """
    raw = (values.get("VAD_GATE") or "").strip().lower()
    enabled = raw in ("1", "true", "yes", "on")
    model_id = (values.get("VAD_MODEL") or "").strip() or DEFAULT_MODEL_ID
    try:
        floor = float((values.get("VAD_MIN_SPEECH") or "").strip())
    except ValueError:
        floor = DEFAULT_MIN_SPEECH_S
    return enabled, model_id, floor


def is_live(model_id="", sample_rate=TARGET_SR):
    """Whether the gate would actually screen anything, in this process, right now.

    **Why a probe and not a check of the parts.** The gate fails open on every path, which is the
    right ranking (**R3**, **V64**) and also means an unavailable gate is invisible: it transcribes
    every segment, and a run that transcribes every segment looks exactly like a healthy ungated
    run in every number a soak prints. That is not hypothetical — **V91**: three overnight soaks and
    the hour behind **V86** all reported *gate on* while the weights were absent from the product's
    `HF_HOME`, and nothing in their output said so.

    **The discriminator is silence.** Two seconds of digital zeros carry no speech, so a working
    pipeline returns `False`. Every failure path in `has_speech` returns `True`, so a `False` here
    cannot be produced by a gate that did not run. Checking importability instead is what the
    overnight preflight did, and `pyannote.audio` imported fine the whole time the gate was dead.

    Costs one load (about 6 s) and leaves the pipeline cached for the run that follows.
    """
    try:
        import numpy as np
    except Exception as exc:                                  # pragma: no cover - numpy is a dep
        logger.warning("⚠️ [VoiceGate] cannot probe (%s: %s).", type(exc).__name__, exc)
        return False
    silence = np.zeros(int(sample_rate * 2), dtype="float32")
    return not has_speech(silence, model_id, DEFAULT_MIN_SPEECH_S, sample_rate)
