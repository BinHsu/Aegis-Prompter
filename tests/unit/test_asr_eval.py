"""Unit tests for ASR bake-off helpers (tmp_path only — no real fixtures/asr audio)."""

import pytest

from src.asr_eval import (
    TARGET_SR,
    assert_fixture_path_allowed,
    iter_fixture_wavs,
    load_wav_mono_float32,
    looks_traditional_chinese,
    score_nonspeech_texts,
    write_wav_mono_int16,
)


def test_write_load_roundtrip(tmp_path):
    path = tmp_path / "tone.wav"
    samples = [0.0, 0.5, -0.5, 0.25]
    # pad to something longer
    samples = samples + [0.0] * (TARGET_SR // 10)
    write_wav_mono_int16(str(path), samples, sample_rate=TARGET_SR)
    loaded, rate = load_wav_mono_float32(str(path), target_sr=TARGET_SR)
    assert rate == TARGET_SR
    assert len(loaded) == len(samples)
    assert abs(loaded[1] - 0.5) < 0.02
    assert abs(loaded[2] + 0.5) < 0.02


def test_resample_halves_length(tmp_path):
    path = tmp_path / "hi.wav"
    sr = 32000
    samples = [0.1] * sr  # 1 second at 32 kHz
    write_wav_mono_int16(str(path), samples, sample_rate=sr)
    loaded, rate = load_wav_mono_float32(str(path), target_sr=TARGET_SR)
    assert rate == TARGET_SR
    assert abs(len(loaded) - TARGET_SR) <= 1


def test_refuse_private_trees(tmp_path):
    for name in ("history", "context", "logs"):
        bad = tmp_path / name / "clip.wav"
        bad.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="private tree"):
            assert_fixture_path_allowed(str(bad))


def test_iter_fixture_wavs(tmp_path):
    root = tmp_path / "asr"
    (root / "nonspeech" / "music").mkdir(parents=True)
    (root / "nonspeech" / "music" / "a.wav").write_bytes(b"RIFF")
    (root / "nonspeech" / "music" / "b.txt").write_text("nope")
    (root / "nonspeech" / "chime").mkdir(parents=True)
    (root / "nonspeech" / "chime" / "c.WAV").write_bytes(b"RIFF")
    found = iter_fixture_wavs(str(root), "nonspeech")
    assert len(found) == 2
    assert all(p.lower().endswith(".wav") for p in found)


def test_score_nonspeech_texts_separates_model_from_filter():
    """Raw counts what the model said; accepted counts what survives the filter.

    The two columns exist because conflating them credited a model with a defence fitted to a
    rival's failures. With the blacklist now empty (docs/decisions/0009 and the module docstring)
    the columns agree — which is the point, not a reason to drop one. If they ever diverge again,
    something is filtering, and the report will show it.
    """
    scored = score_nonspeech_texts(["", "OK", "營收成長"])
    assert scored["calls"] == 3
    assert scored["raw"] == 2, "raw counts every non-empty string the model produced"
    assert scored["accepted"] == 2, "nothing is filtered while the list is empty"
    assert scored["filtered_out"] == 0
    assert "OK" in scored["accepted_texts"]


def test_looks_traditional_chinese():
    assert looks_traditional_chinese("本季營收成長") is True  # 國 not needed; 營/長 markers
    assert looks_traditional_chinese("本季营收成长") is False
    assert looks_traditional_chinese("hello only") is None
