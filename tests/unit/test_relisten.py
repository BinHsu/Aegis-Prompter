"""Re-listening: segmentation, the timebase, the vocabulary, and what the output declares.

Real WAVs written by the retention writer and read back by this module, so the two halves of the
round trip are exercised against each other rather than against an assumption. The recogniser
itself is stubbed — this pass is defined by *how it cuts the audio and how it merges two tracks*,
and neither of those is a property of the model.
"""
import datetime
import os
import sys
import types

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import audio_archive  # noqa: E402
import relisten  # noqa: E402

RATE = 16000
FRAME = 480


class _Vad:
    """Speech wherever the block is loud. The real VAD needs real speech; this needs a boundary."""

    def is_speech(self, buf, rate):
        return int(np.abs(np.frombuffer(buf, dtype=np.int16)).mean()) > 500


def _tone(seconds, level=6000):
    return np.full(int(RATE * seconds), level, dtype=np.int16)


def _silence(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.int16)


def _write(path, samples):
    writer = audio_archive.TrackWriter(str(path), RATE)
    assert writer.open() == ""
    writer.write(samples)
    writer.close()
    return str(path)


# ===== The round trip with the retention writer =====

def test_what_retention_wrote_is_what_this_reads_back(tmp_path):
    """The two halves are only useful together, so they are tested against each other rather
    than against a guess about the format."""
    block = _tone(0.5)
    path = _write(tmp_path / "Meeting_S1_mic.wav", block)

    samples, rate = relisten.read_wav_mono_int16(path)
    assert rate == RATE
    assert np.array_equal(samples, block)


def test_a_file_that_is_not_mono_sixteen_bit_is_refused_rather_than_converted(tmp_path):
    """It reads back exactly what the writer writes. Anything else is a fault to report, not
    something to quietly reinterpret."""
    import wave

    path = str(tmp_path / "stereo.wav")
    with wave.open(path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(_tone(0.2).tobytes())

    samples, rate = relisten.read_wav_mono_int16(path)
    assert samples is None and rate == 0


def test_a_missing_file_is_reported_rather_than_raising(tmp_path):
    assert relisten.read_wav_mono_int16(str(tmp_path / "nope.wav")) == (None, 0)


# ===== Segmentation: the whole difference from the live path =====

def test_a_pause_shorter_than_the_flush_no_longer_splits_a_sentence():
    """The live path closes after 0.4 s because the speaker is waiting for it (V66). Nobody is
    waiting here, so a sentence spoken with a breath in the middle arrives as one line — which
    is most of what "fill in what was dropped" means."""
    audio = np.concatenate([_tone(1.0), _silence(0.8), _tone(1.0)])
    segments = list(relisten.segment(audio, RATE, _Vad()))

    assert len(segments) == 1, "0.8 s is under the 1.2 s flush and must not cut"


def test_a_real_gap_still_separates_two_utterances():
    audio = np.concatenate([_tone(1.0), _silence(2.0), _tone(1.0)])
    segments = list(relisten.segment(audio, RATE, _Vad()))

    assert len(segments) == 2
    assert segments[0][0] == pytest.approx(0.0, abs=0.05)
    assert segments[1][0] > 2.5


def test_unbroken_speech_is_capped_rather_than_growing_without_bound():
    """A cut on a clock is worse than a cut at silence, so the cap exists only as a backstop."""
    segments = list(relisten.segment(_tone(50.0), RATE, _Vad()))

    assert len(segments) > 1
    for _second, block in segments:
        assert len(block) / RATE <= relisten.MAX_SEGMENT_S + 0.1


def test_noise_shorter_than_the_floor_is_not_an_utterance():
    audio = np.concatenate([_silence(0.5), _tone(0.1), _silence(2.0)])
    assert list(relisten.segment(audio, RATE, _Vad())) == []


def test_a_segment_reports_where_in_the_track_it_started():
    """Without that there is no timebase, and without a timebase two tracks cannot be merged."""
    audio = np.concatenate([_silence(3.0), _tone(1.0)])
    (second, _block), = list(relisten.segment(audio, RATE, _Vad()))
    assert second == pytest.approx(3.0, abs=0.1)


# ===== The timebase the streaming branch assumed and never established =====

TRANSCRIPT = """# 🛡️ Staff Officer Meeting Log

- **Session ID**: S1

---

## 📝 Transcript & Tactical Cues

**[10:15:01] Participant**: 台北市政府 said the ACME Corporation figure was wrong

---

## 🎧 Audio archive

- **Speaker (You)** — `/vault/Meeting_S1_mic.wav`
  - started 2026-08-14T10:15:00.100, 3600.0 s, 115.0 MB
- **Participant** — `/vault/Meeting_S1_system.wav`
  - started 2026-08-14T10:15:02.600, 3599.0 s, 114.0 MB
"""


def test_each_track_start_is_read_back_so_the_merge_is_not_a_guess(tmp_path):
    """`docs/decisions/0006`: the branch's offline merge assumed a shared `t=0` that nothing
    established. Retention records each track's own first frame precisely so it need not."""
    path = tmp_path / "Meeting_S1.md"
    path.write_text(TRANSCRIPT, encoding="utf-8")

    starts = relisten.track_starts(str(path))
    assert set(starts) == {"Speaker (You)", "Participant"}
    offset = (starts["Participant"] - starts["Speaker (You)"]).total_seconds()
    assert offset == pytest.approx(2.5, abs=0.01)


def test_a_transcript_without_an_audio_section_yields_no_starts(tmp_path):
    path = tmp_path / "Meeting_S2.md"
    path.write_text("# log\n\n## 📝 Transcript & Tactical Cues\n\nnothing else\n", encoding="utf-8")
    assert relisten.track_starts(str(path)) == {}


# ===== Vocabulary, scoped to this meeting =====

def test_the_vocabulary_comes_from_this_meeting_not_the_knowledge_base(tmp_path):
    """V59 recovers rare proper nouns, and the terms the live pass already got right are the best
    available guess at what the ones it got wrong sound like."""
    path = tmp_path / "Meeting_S1.md"
    path.write_text(TRANSCRIPT, encoding="utf-8")

    vocabulary = relisten.vocabulary_from(str(path))
    assert "台北市政府" in vocabulary
    assert "ACME" in vocabulary


def test_the_vocabulary_excludes_the_post_meeting_prompt(tmp_path):
    """Otherwise every transcript would bias recognition toward the words of our own instruction,
    which appear in every file and belong to none of the meetings."""
    import postmeeting

    path = tmp_path / "Meeting_S1.md"
    path.write_text(TRANSCRIPT + postmeeting.render_block(session_id="S1"), encoding="utf-8")

    vocabulary = relisten.vocabulary_from(str(path))
    assert "Proofread" not in vocabulary
    assert "台北市政府" in vocabulary


def test_an_unreadable_transcript_yields_no_vocabulary_rather_than_raising(tmp_path):
    assert relisten.vocabulary_from(str(tmp_path / "nope.md")) == ""


# ===== The output declares what it is and what it is not =====

@pytest.fixture
def stub_asr(monkeypatch):
    # A plain `list` takes no attributes, so the segment lengths and the prompts each backend was
    # built with need one object that can carry both.
    class _Calls(list):
        prompts = ()

    calls = _Calls()
    calls.prompts = []

    def resolve_backend(model_path, initial_prompt=None):
        # Recorded, not ignored. Biasing moved from a per-call `context=` argument to a backend
        # built around `initial_prompt` when the ASR model was replaced (`docs/decisions/0012`),
        # and a stub that swallowed the keyword would let the pass stop biasing without a single
        # test turning red.
        calls.prompts.append(initial_prompt)

        def _transcribe(audio):
            calls.append(len(audio))
            return "a recognised line"
        return "stub", _transcribe

    import transcriber as tr
    import webrtcvad
    monkeypatch.setattr(tr, "resolve_backend", resolve_backend)
    monkeypatch.setattr(tr, "NPU_LOCK", __import__("threading").Lock())
    monkeypatch.setattr(relisten, "vocabulary_from", lambda path, limit=40: "")
    # `run()` builds its own `webrtcvad.Vad(3)`, and a constant tone is not speech to the real
    # one — it wants formants. These tests are about merging, alignment and what the output
    # declares, none of which is a property of voice detection, so the boundary is stubbed and
    # `test_a_pause_shorter_than_the_flush...` above covers the segmentation rule itself.
    monkeypatch.setattr(webrtcvad, "Vad", lambda severity=3: _Vad())
    return calls


def test_a_run_writes_a_new_file_and_leaves_the_live_transcript_alone(tmp_path, stub_asr):
    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    before = transcript.read_text(encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav",
                 np.concatenate([_tone(1.0), _silence(2.0), _tone(1.0)]))

    result = relisten.run(str(transcript), {"Speaker (You)": mic})

    assert result["error"] == ""
    assert result["output"] == relisten.relistened_path(str(transcript))
    assert transcript.read_text(encoding="utf-8") == before
    assert result["segments"] == 2


def test_the_harvested_vocabulary_is_handed_to_the_decoder_as_its_prompt(tmp_path, stub_asr,
                                                                        monkeypatch):
    """**V59** measured biasing recovering 9 of 11 rare proper nouns, on an argument that no
    longer exists: the previous backend took a `context=` vocabulary list per call, and Whisper
    takes an `initial_prompt` bound into the backend. The observable that fails if the wiring is
    lost is the prompt reaching `resolve_backend` — the transcript would still be written, and
    would silently be the unbiased one."""
    monkeypatch.setattr(relisten, "vocabulary_from", lambda path, limit=40: "Aegis, Hualien")
    transcript = tmp_path / "Meeting_S9.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S9_mic.wav", _tone(1.0))

    relisten.run(str(transcript), {"Speaker (You)": mic})

    assert stub_asr.prompts == ["Aegis, Hualien"]


def test_biasing_can_be_declined_and_then_nothing_is_prepended(tmp_path, stub_asr, monkeypatch):
    """`use_context=False` must reach the decoder as no prompt at all, not as an empty string:
    a prompt is text the model may copy out, so "off" has to mean absent."""
    monkeypatch.setattr(relisten, "vocabulary_from", lambda path, limit=40: "Aegis, Hualien")
    transcript = tmp_path / "Meeting_S10.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S10_mic.wav", _tone(1.0))

    relisten.run(str(transcript), {"Speaker (You)": mic}, use_context=False)

    assert stub_asr.prompts == [None]


def test_the_output_says_when_the_tracks_could_not_be_aligned(tmp_path, stub_asr):
    """The branch aligned them anyway and said nothing. Stating it is the whole correction."""
    transcript = tmp_path / "Meeting_S2.md"
    transcript.write_text("# log\n\n## 📝 Transcript & Tactical Cues\n\n", encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S2_mic.wav", _tone(1.0))

    result = relisten.run(str(transcript), {"Speaker (You)": mic})
    written = open(result["output"], encoding="utf-8").read()

    assert result["aligned"] is False
    assert "aligned as if they began together" in written
    assert "**They did not.**" in written


def test_two_tracks_are_merged_on_their_own_recorded_starts(tmp_path, stub_asr):
    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav", _tone(1.0))
    system = _write(tmp_path / "Meeting_S1_system.wav", _tone(1.0))

    result = relisten.run(str(transcript),
                          {"Speaker (You)": mic, "Participant": system})
    written = open(result["output"], encoding="utf-8").read()

    assert result["aligned"] is True
    assert "both tracks aligned on their own recorded first-frame instants" in written
    # Only the transcript section: the header carries a per-track summary line whose label would
    # otherwise be matched instead.
    body = written.split("## 📝 Transcript", 1)[1]
    # The Participant track started 2.5 s later, so its line must land after the microphone's.
    assert body.index("Speaker (You)**:") < body.index("Participant**:")


def test_the_output_declares_that_speakers_were_not_separated(tmp_path, stub_asr):
    """R12 is not satisfied by this pass, and a transcript that looks authoritative must say so
    rather than letting one label be read as one person."""
    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav", _tone(1.0))

    result = relisten.run(str(transcript), {"Speaker (You)": mic})
    written = open(result["output"], encoding="utf-8").read()

    assert "Speaker attribution**: not performed" in written
    assert "however many people spoke" in written


def test_the_output_carries_the_same_post_meeting_prompt(tmp_path, stub_asr):
    """It is a transcript too, so it needs the same review — and its own defects differ, which
    the header states."""
    import postmeeting

    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav", _tone(1.0))

    result = relisten.run(str(transcript), {"Speaker (You)": mic})
    assert postmeeting.MARKER in open(result["output"], encoding="utf-8").read()


def test_a_session_with_no_audio_is_refused_with_a_reason(tmp_path):
    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")

    result = relisten.run(str(transcript), {})
    assert "no retained audio" in result["error"]
    assert result["output"] == ""


def test_an_unreadable_track_is_reported_per_track_and_does_not_abort_the_rest(tmp_path,
                                                                              stub_asr):
    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav", _tone(1.0))
    broken = str(tmp_path / "Meeting_S1_system.wav")
    open(broken, "wb").write(b"not a wav")

    result = relisten.run(str(transcript),
                          {"Speaker (You)": mic, "Participant": broken})

    assert result["segments"] >= 1, "the readable track still produced lines"
    assert "unreadable" in result["tracks"]["Participant"]["error"]
    assert "❌ **Participant**" in open(result["output"], encoding="utf-8").read()


def test_the_appended_prompt_describes_the_relistened_file_not_the_live_one(tmp_path, stub_asr):
    """The bug this replaced: `render_block()` was called with no arguments, so a file whose own
    header said "segments closed after 1.2 s" carried a prompt saying 0.4 s."""
    import postmeeting

    transcript = tmp_path / "Meeting_S1.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    mic = _write(tmp_path / "Meeting_S1_mic.wav", _tone(1.0))

    result = relisten.run(str(transcript), {"Speaker (You)": mic})
    written = open(result["output"], encoding="utf-8").read()
    prompt = postmeeting.extract(written)

    assert f"{relisten.SILENCE_FLUSH_S} s of" in prompt
    assert "0.4 s of silence" not in prompt
    assert "Staff override" not in prompt
    assert "offset from the start of the recording" in prompt
    # And the header and the prompt agree about the flush, which is what failed.
    assert f"closed after {relisten.SILENCE_FLUSH_S} s of silence" in written
