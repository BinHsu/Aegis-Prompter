"""Pure helpers for ASR bake-off fixtures and scoring.

No heavy imports at module scope — WAV I/O uses the standard library only so unit tests
run without `webrtcvad` / `mlx_whisper`. The bake-off harness imports this module and adds
VAD + model calls itself.
"""

import math
import os
import struct
import wave

TARGET_SR = 16000

# Forbidden output roots — same private trees AGENTS.md forbids reading or fabricating.
FORBIDDEN_PATH_PARTS = ("history", "context", "logs")


def assert_fixture_path_allowed(path):
    """Refuse to write under history/, context/, or logs/."""
    normalized = os.path.normpath(os.path.abspath(path))
    parts = set(normalized.split(os.sep))
    hit = parts.intersection(FORBIDDEN_PATH_PARTS)
    if hit:
        raise ValueError(f"refusing path under private tree {sorted(hit)}: {path}")


def write_wav_mono_int16(path, samples, sample_rate=TARGET_SR):
    """Write mono float samples in [-1, 1] as 16-bit PCM WAV."""
    assert_fixture_path_allowed(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    clamped = [max(-1.0, min(1.0, float(s))) for s in samples]
    frames = b"".join(struct.pack("<h", int(s * 32767.0)) for s in clamped)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(frames)


def load_wav_mono_float32(path, target_sr=TARGET_SR):
    """Load a WAV as mono float32, resampling with linear interpolation when needed.

    Returns (samples_list, sample_rate_used). sample_rate_used equals target_sr after resample.
    """
    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        nframes = handle.getnframes()
        raw = handle.readframes(nframes)

    if width != 2:
        raise ValueError(f"only 16-bit PCM supported, got sampwidth={width} in {path}")

    count = len(raw) // 2
    ints = struct.unpack("<" + "h" * count, raw)
    if channels == 1:
        mono = [i / 32767.0 for i in ints]
    elif channels == 2:
        mono = [(ints[i] + ints[i + 1]) / 2.0 / 32767.0 for i in range(0, len(ints) - 1, 2)]
    else:
        raise ValueError(f"unsupported channel count {channels} in {path}")

    if rate == target_sr:
        return mono, target_sr

    if rate <= 0:
        raise ValueError(f"invalid sample rate {rate} in {path}")

    duration = len(mono) / float(rate)
    out_len = max(1, int(round(duration * target_sr)))
    if len(mono) == 1:
        return mono * out_len, target_sr

    resampled = []
    for i in range(out_len):
        src = i * (len(mono) - 1) / float(out_len - 1)
        lo = int(math.floor(src))
        hi = min(lo + 1, len(mono) - 1)
        frac = src - lo
        resampled.append(mono[lo] * (1.0 - frac) + mono[hi] * frac)
    return resampled, target_sr


def iter_fixture_wavs(root, relative_dir):
    """Yield absolute paths to *.wav under root/relative_dir, sorted."""
    base = os.path.join(root, relative_dir)
    if not os.path.isdir(base):
        return []
    found = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in sorted(filenames):
            if name.lower().endswith(".wav"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def score_nonspeech_texts(texts):
    """How many ASR strings would become buffer lines (R37 false triggers).

    Reports **two** counts, and the distinction decides what a bake-off can conclude:

    - `raw` — every non-empty string the model produced from a segment VAD called speech. This is
      the **model's** behaviour on non-speech.
    - `accepted` — what survives the whole-utterance blacklist as well. This is the **pipeline's**
      behaviour.

    They must not be conflated. The blacklist was extended with ghosts harvested from Whisper on
    these same fixtures, so scoring a rival through it credits one model with a defence fitted to
    another's failures — and `STATE.md` already requires that defence to be rebuilt for whichever
    model wins. **R11** asks for a deliberate choice about the model, which is the `raw` column.
    """
    try:
        from text_filters import is_acceptable
    except ImportError:
        from src.text_filters import is_acceptable

    produced = [t for t in texts if t and t.strip()]
    accepted = [t for t in produced if is_acceptable(t)]
    return {
        "calls": len(texts),
        "raw": len(produced),
        "raw_texts": produced,
        "accepted": len(accepted),
        "accepted_texts": accepted,
        "filtered_out": len(produced) - len(accepted),
    }


def looks_traditional_chinese(text):
    """Heuristic: True if text contains common Traditional-only codepoints.

    Observational for R10 — not a converter. Simplified-only markers tip the other way.
    """
    traditional_markers = set("國語臺灣過體門東車紅學長馬鳥魚")
    simplified_markers = set("国语台湾过体门东车红学长马鸟鱼")
    chars = set(text)
    trad_hits = len(chars & traditional_markers)
    simp_hits = len(chars & simplified_markers)
    if trad_hits == 0 and simp_hits == 0:
        return None
    return trad_hits >= simp_hits
