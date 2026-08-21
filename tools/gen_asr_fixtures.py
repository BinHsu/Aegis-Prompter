#!/usr/bin/env python3
"""Synthesize ASR bake-off fixtures under fixtures/asr/ (gitignored WAVs).

Non-speech is programmatic. Speech uses macOS `say` when available, with a
programmatic fallback so the layout still regenerates on a headless clone.

Never writes under history/, context/, or logs/.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from asr_eval import TARGET_SR, assert_fixture_path_allowed, write_wav_mono_int16  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")


def _sine(freq, duration_s, sr=TARGET_SR, amp=0.25, phase=0.0):
    n = int(duration_s * sr)
    return [amp * math.sin(2 * math.pi * freq * (i / sr) + phase) for i in range(n)]


def _silence(duration_s, sr=TARGET_SR):
    return [0.0] * int(duration_s * sr)


def _mix(*tracks):
    length = max(len(t) for t in tracks)
    out = [0.0] * length
    for track in tracks:
        for i, sample in enumerate(track):
            out[i] += sample
    peak = max((abs(s) for s in out), default=1.0) or 1.0
    if peak > 0.95:
        out = [s * (0.95 / peak) for s in out]
    return out


def _noise(duration_s, sr=TARGET_SR, amp=0.15, seed=1):
    rng = random.Random(seed)
    return [amp * (rng.random() * 2 - 1) for _ in range(int(duration_s * sr))]


def gen_layered_tones(duration_s=90.0):
    parts = []
    t = 0.0
    while t < duration_s:
        chunk = min(5.0, duration_s - t)
        parts.append(
            _mix(
                _sine(220 + (t % 7) * 12, chunk, amp=0.18),
                _sine(330 + (t % 5) * 9, chunk, amp=0.12, phase=0.3),
                _sine(440, chunk, amp=0.08 * (0.5 + 0.5 * math.sin(t))),
            )
        )
        t += chunk
    flat = []
    for p in parts:
        flat.extend(p)
    return flat


def gen_noise_bed(duration_s=60.0):
    raw = _noise(duration_s, amp=0.35, seed=7)
    # Crude one-pole low-pass → pink-ish bed
    out = []
    state = 0.0
    for sample in raw:
        state = 0.95 * state + 0.05 * sample
        out.append(state * 2.2)
    peak = max((abs(s) for s in out), default=1.0) or 1.0
    return [s * (0.4 / peak) for s in out]


def gen_single_chimes(duration_s=45.0):
    out = []
    t = 0.0
    freqs = (880, 988, 1175, 1319)
    i = 0
    while t < duration_s:
        burst = _sine(freqs[i % len(freqs)], 0.35, amp=0.45)
        # exponential-ish decay
        burst = [s * math.exp(-3.5 * (j / TARGET_SR)) for j, s in enumerate(burst)]
        gap = _silence(1.4)
        out.extend(burst)
        out.extend(gap)
        t += 0.35 + 1.4
        i += 1
    return out[: int(duration_s * TARGET_SR)]


def gen_glass_cascade(duration_s=30.0):
    out = []
    t = 0.0
    base = 1200.0
    while t < duration_s:
        cluster = _mix(
            _sine(base, 0.2, amp=0.3),
            _sine(base * 1.25, 0.2, amp=0.22),
            _sine(base * 1.5, 0.2, amp=0.15),
        )
        cluster = [s * math.exp(-5.0 * (j / TARGET_SR)) for j, s in enumerate(cluster)]
        out.extend(cluster)
        out.extend(_silence(0.55))
        base = 900 + ((base - 900 + 40) % 500)
        t += 0.2 + 0.55
    return out[: int(duration_s * TARGET_SR)]


def gen_click_burst(duration_s=60.0, interval=0.18, seed=3):
    rng = random.Random(seed)
    n = int(duration_s * TARGET_SR)
    out = [0.0] * n
    pos = 0
    while pos < n:
        click_len = int(0.008 * TARGET_SR)
        for j in range(click_len):
            if pos + j < n:
                out[pos + j] = (rng.random() * 2 - 1) * 0.55 * math.exp(-j / 40.0)
        step = int((interval + rng.uniform(-0.05, 0.08)) * TARGET_SR)
        pos += max(step, click_len + 1)
    return out


def gen_typing_run(duration_s=60.0):
    return gen_click_burst(duration_s=duration_s, interval=0.07, seed=11)


def _pick_zh_voice():
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (result.stdout or "").splitlines()
    # Prefer Taiwan / Traditional voices when present.
    preferred = ("Mei-Jia", "Meijia", "Ting-Ting", "Tingting", "Sin-ji")
    available = {}
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        available[name.lower()] = name
    for want in preferred:
        if want.lower() in available:
            return available[want.lower()]
    for line in lines:
        if "zh_" in line or "zh-CN" in line or "zh-TW" in line or "Chinese" in line:
            return line.split()[0]
    return None


def _say_to_wav(text, voice, dest_wav):
    """Render text with macOS say into dest_wav at TARGET_SR. Returns True on success."""
    assert_fixture_path_allowed(dest_wav)
    if shutil.which("say") is None or shutil.which("afconvert") is None:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        aiff = os.path.join(tmp, "clip.aiff")
        cmd = ["say", "-o", aiff]
        if voice:
            cmd.extend(["-v", voice])
        cmd.append(text)
        try:
            subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            subprocess.run(
                [
                    "afconvert", "-f", "WAVE", "-d", f"LEI16@{TARGET_SR}",
                    aiff, dest_wav,
                ],
                check=True, timeout=60, capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False
    return os.path.isfile(dest_wav) and os.path.getsize(dest_wav) > 1000


def _tts_fallback_tone_speech(text, dest_wav):
    """When say is unavailable: mark the slot with a short beep pattern (still a WAV)."""
    # Not linguistic — only keeps the path present. Bake-off speech rows will note synthesis mode.
    samples = _mix(_sine(300, 0.4, amp=0.2), _sine(450, 0.4, amp=0.15))
    samples.extend(_silence(0.2))
    samples.extend(_sine(350, min(2.0, 0.08 * max(len(text), 1)), amp=0.12))
    write_wav_mono_int16(dest_wav, samples)
    return False


def write_speech_clip(path, text, voice):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if _say_to_wav(text, voice, path):
        return "say"
    _tts_fallback_tone_speech(text, path)
    return "fallback-tone"


def maybe_skip(path, force):
    return (not force) and os.path.isfile(path) and os.path.getsize(path) > 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate even when a WAV already exists",
    )
    args = parser.parse_args()

    assert_fixture_path_allowed(FIXTURE_ROOT)
    jobs = [
        ("nonspeech/music/layered_tones.wav", gen_layered_tones),
        ("nonspeech/music/noise_bed.wav", gen_noise_bed),
        ("nonspeech/chime/single_chimes.wav", gen_single_chimes),
        ("nonspeech/chime/glass_cascade.wav", gen_glass_cascade),
        ("nonspeech/keyboard/click_burst.wav", gen_click_burst),
        ("nonspeech/keyboard/typing_run.wav", gen_typing_run),
    ]

    print(f"Fixture root: {FIXTURE_ROOT}")
    for rel, factory in jobs:
        path = os.path.join(FIXTURE_ROOT, rel)
        if maybe_skip(path, args.force):
            print(f"  skip {rel}")
            continue
        print(f"  write {rel}")
        write_wav_mono_int16(path, factory())

    zh_voice = _pick_zh_voice()
    en_voice = "Samantha"
    print(f"TTS voices: en={en_voice!r} zh={zh_voice!r}")

    speech_jobs = [
        (
            "speech/en/briefing_en.wav",
            "Good morning. The quarterly revenue grew twelve percent year over year. "
            "We will take questions after the prepared remarks.",
            en_voice,
        ),
        (
            "speech/zh/briefing_zh.wav",
            "各位先進大家好。本季營收較去年同期成長百分之十二。準備稿結束後再開放提問。",
            zh_voice,
        ),
    ]

    for rel, text, voice in speech_jobs:
        path = os.path.join(FIXTURE_ROOT, rel)
        if maybe_skip(path, args.force):
            print(f"  skip {rel}")
            continue
        mode = write_speech_clip(path, text, voice)
        print(f"  write {rel} ({mode})")

    # Code-switch: concatenate EN and ZH WAVs if both exist; else synthesize one clip.
    cs_path = os.path.join(FIXTURE_ROOT, "speech/code_switch/en_zh_interleaved.wav")
    en_path = os.path.join(FIXTURE_ROOT, "speech/en/briefing_en.wav")
    zh_path = os.path.join(FIXTURE_ROOT, "speech/zh/briefing_zh.wav")
    if maybe_skip(cs_path, args.force):
        print("  skip speech/code_switch/en_zh_interleaved.wav")
    else:
        from asr_eval import load_wav_mono_float32

        os.makedirs(os.path.dirname(cs_path), exist_ok=True)
        if os.path.isfile(en_path) and os.path.isfile(zh_path):
            en_s, _ = load_wav_mono_float32(en_path)
            zh_s, _ = load_wav_mono_float32(zh_path)
            gap = _silence(0.6)
            # Interleave: first sentence-worth of each by simple halves
            mid_en = len(en_s) // 2
            mid_zh = len(zh_s) // 2
            combined = en_s[:mid_en] + gap + zh_s[:mid_zh] + gap + en_s[mid_en:] + gap + zh_s[mid_zh:]
            write_wav_mono_int16(cs_path, combined)
            print("  write speech/code_switch/en_zh_interleaved.wav (concat)")
        else:
            mode = write_speech_clip(
                cs_path,
                "Revenue grew twelve percent. 營收成長百分之十二.",
                en_voice,
            )
            print(f"  write speech/code_switch/en_zh_interleaved.wav ({mode})")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
