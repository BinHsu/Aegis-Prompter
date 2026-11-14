"""The command that re-listens to a file this application never captured.

The recogniser stays stubbed. These tests check the conversion into the one WAV shape
`relisten.read_wav_mono_int16` accepts, and that the command hands that WAV to `relisten.run`
with the operator's vocabulary and without asking for speaker separation. They build their own
fixtures and never read settings from disk.
"""
import os
import shutil
import subprocess
import sys
import wave

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "tools"))

import relisten  # noqa: E402
import relisten_file  # noqa: E402


def _require_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")
    return ffmpeg


def _pcm(path, channels, rate, frames):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


def _pretend_ffmpeg(monkeypatch):
    """The hand-off tests do not decode anything. The conversion tests use the real binary."""
    monkeypatch.setattr(relisten_file.shutil, "which", lambda name: f"/usr/bin/{name}")


def _settings(monkeypatch, root, weights=True):
    """Keep `main` off the real settings file and off the network."""
    import bootstrap

    order = []
    settings = {"STORAGE_ROOT": str(root), "ASR_MODEL": "", "HF_TOKEN": "", "DIARIZE_MODEL": ""}

    monkeypatch.setattr(bootstrap, "read_settings", lambda path=None: settings)
    monkeypatch.setattr(bootstrap, "apply_environment",
                        lambda _settings: order.append("env") or {"models": str(root)})
    monkeypatch.setattr(bootstrap, "enforce_offline", lambda: order.append("offline") or [])
    monkeypatch.setattr(bootstrap, "weights_present", lambda repo: order.append(repo) or weights)
    return settings, order


def test_an_unknown_stream_count_is_refused_before_settings_are_read(tmp_path, monkeypatch):
    """A missing count is not permission to keep whichever stream ffmpeg would have picked."""
    import bootstrap

    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffmpeg, path: None)

    def boom(path=None):
        raise AssertionError("settings were read when the stream list could not be read")

    monkeypatch.setattr(bootstrap, "read_settings", boom)
    assert relisten_file.main([str(source)]) == 2


def test_a_missing_file_is_refused_before_any_settings_are_read(tmp_path, monkeypatch):
    import bootstrap

    def boom(path=None):
        raise AssertionError("settings were read for a path that is not a file")

    monkeypatch.setattr(bootstrap, "read_settings", boom)
    code = relisten_file.main([str(tmp_path / "no-such-file.mov")])
    assert code == 2


def test_a_stereo_file_is_downmixed_to_the_wav_relisten_reads(tmp_path):
    ffmpeg = _require_ffmpeg()
    stereo = tmp_path / "stereo.wav"
    # One second, 44.1 kHz, left channel a tone and the right channel silence.
    left = (8000).to_bytes(2, "little", signed=True)
    right = (0).to_bytes(2, "little", signed=True)
    _pcm(stereo, 2, 44100, (left + right) * 44100)
    wav = tmp_path / "out.wav"

    assert relisten_file.convert(ffmpeg, str(stereo), str(wav)) == ""
    samples, rate = relisten.read_wav_mono_int16(str(wav))

    assert rate == 16000
    assert samples is not None and len(samples) > 16000 * 0.9
    assert int(abs(samples).mean()) > 100
    assert relisten_file.audio_stream_count(ffmpeg, str(stereo)) == 1


def test_say_aiff_converts_to_the_wav_relisten_reads(tmp_path):
    """A synthetic voice, not a recording of anyone. `say` is the same fixture V74 used."""
    ffmpeg = _require_ffmpeg()
    say = shutil.which("say")
    if not say:
        pytest.skip("say is not installed")
    aiff = tmp_path / "fixture.aiff"
    subprocess.run([say, "-o", str(aiff), "Datadog JSON pipeline"], check=True)
    wav = tmp_path / "fixture.wav"

    assert relisten_file.convert(ffmpeg, str(aiff), str(wav)) == ""
    samples, rate = relisten.read_wav_mono_int16(str(wav))
    assert rate == 16000
    assert samples is not None and len(samples) > 0


def test_two_audio_streams_reach_relisten_as_two_tracks(tmp_path, monkeypatch):
    """A screen recording can keep the microphone and the system audio as two streams.
    Each one is a track, in stream order, and the samples that arrive are that stream's."""
    ffmpeg = _require_ffmpeg()
    left = tmp_path / "left.wav"
    right = tmp_path / "right.wav"
    _pcm(left, 1, 16000, (4000).to_bytes(2, "little", signed=True) * 1600)
    _pcm(right, 1, 16000, (12000).to_bytes(2, "little", signed=True) * 1600)
    dual = tmp_path / "dual.mkv"
    muxed = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(left), "-i", str(right),
         "-map", "0:a:0", "-map", "1:a:0", "-c:a", "pcm_s16le", str(dual)],
        capture_output=True, text=True)
    assert muxed.returncode == 0, muxed.stderr

    _settings(monkeypatch, tmp_path)
    seen = {}

    def fake_run(transcript_path, tracks, **kwargs):
        seen["tracks"] = list(tracks)
        seen["kwargs"] = kwargs
        seen["means"] = []
        for label in kwargs["track_order"]:
            samples, _rate = relisten.read_wav_mono_int16(tracks[label])
            seen["means"].append(int(samples.mean()))
        return {"output": kwargs["out_path"], "error": "", "segments": 0,
                "vocabulary": "", "diarize_error": ""}

    monkeypatch.setattr(relisten, "run", fake_run)
    out = tmp_path / "notes"
    out.mkdir()
    assert relisten_file.main([str(dual), "--out", str(out), "--diarize"]) == 0
    assert seen["tracks"] == ["Stream 1", "Stream 2"]
    assert seen["kwargs"]["track_order"] == ["Stream 1", "Stream 2"]
    assert seen["kwargs"]["same_container"] is True
    assert seen["kwargs"]["diarize"] is False
    assert abs(seen["means"][0] - 4000) < 50
    assert abs(seen["means"][1] - 12000) < 50

    assert relisten_file.main(
        [str(dual), "--out", str(out), "--labels", "Them,Me"]) == 0
    assert seen["tracks"] == ["Them", "Me"]
    assert seen["kwargs"]["track_order"] == ["Them", "Me"]
    assert abs(seen["means"][0] - 4000) < 50
    assert abs(seen["means"][1] - 12000) < 50


def test_labels_must_name_each_stream(tmp_path, monkeypatch):
    import bootstrap

    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffmpeg, path: 2)

    def boom(path=None):
        raise AssertionError("settings were read for a label list that does not match")

    monkeypatch.setattr(bootstrap, "read_settings", boom)
    assert relisten_file.main([str(source), "--labels", "OnlyMe"]) == 2


def test_a_backtick_in_the_vocabulary_is_refused_before_settings_are_read(tmp_path, monkeypatch):
    import bootstrap

    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffmpeg, path: 1)

    def boom(path=None):
        raise AssertionError("settings were read for a vocabulary the header cannot print")

    monkeypatch.setattr(bootstrap, "read_settings", boom)
    assert relisten_file.main([str(source), "--vocab", "Da`tag,JSON"]) == 2


def test_diarize_help_does_not_claim_the_command_installs_it(capsys):
    with pytest.raises(SystemExit) as caught:
        relisten_file.parse_args(["--help"])
    assert caught.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "does not install" in text
    assert "installed on demand" not in text


def test_the_command_hands_the_vocabulary_to_relisten_and_does_not_diarize(tmp_path, monkeypatch,
                                                                          capsys):
    source = tmp_path / "call.mov"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 1600)
    _pretend_ffmpeg(monkeypatch)
    _settings_ignored, order = _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffprobe, path: 1)

    def convert(ffmpeg, src, wav):
        with open(wav, "wb") as handle:
            handle.write(b"R")
        return ""

    monkeypatch.setattr(relisten_file, "convert", convert)

    seen = {}

    def fake_run(transcript_path, tracks, **kwargs):
        order.append("run")
        seen["transcript"] = transcript_path
        seen["tracks"] = tracks
        seen["kwargs"] = kwargs
        return {"output": kwargs["out_path"], "error": "", "segments": 3,
                "vocabulary": "Datadog, JSON", "diarize_error": ""}

    monkeypatch.setattr(relisten, "run", fake_run)
    out = tmp_path / "notes"
    out.mkdir()
    code = relisten_file.main([
        str(source), "--vocab", "Datadog, JSON", "--out", str(out),
        "--model", "mlx-community/whisper-large-v3-turbo",
    ])
    printed = capsys.readouterr().out

    assert code == 0
    assert seen["transcript"] is None
    assert seen["kwargs"]["vocabulary"] == "Datadog, JSON"
    assert seen["kwargs"]["diarize"] is False
    assert seen["kwargs"]["model_path"] == "mlx-community/whisper-large-v3-turbo"
    assert seen["kwargs"]["source"] == os.path.abspath(source)
    assert seen["kwargs"]["speaker_track"] == "Recording"
    assert list(seen["tracks"]) == ["Recording"]
    assert order[:2] == ["env", "offline"]
    assert order.index("offline") < order.index("run")
    assert "call_relistened.md" in seen["kwargs"]["out_path"]
    assert "vocabulary: Datadog, JSON" in printed
    # A second run must not overwrite the first reading.
    os.makedirs(out, exist_ok=True)
    with open(seen["kwargs"]["out_path"], "w", encoding="utf-8") as handle:
        handle.write("")
    relisten_file.main([str(source), "--vocab", "JSON", "--out", str(out), "--model", "m"])
    assert seen["kwargs"]["out_path"].endswith("call_relistened-2.md")


def test_diarize_when_asked_targets_the_only_track(tmp_path, monkeypatch):
    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    settings, _order = _settings(monkeypatch, tmp_path)
    settings["HF_TOKEN"] = "not-a-real-token"
    settings["DIARIZE_MODEL"] = "example/diarizer"
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffprobe, path: 1)
    monkeypatch.setattr(relisten_file, "convert", lambda ffmpeg, src, wav: "")
    seen = {}

    def fake_run(transcript_path, tracks, **kwargs):
        seen.update(kwargs)
        return {"output": kwargs["out_path"], "error": "", "segments": 0,
                "vocabulary": "", "diarize_error": ""}

    monkeypatch.setattr(relisten, "run", fake_run)
    assert relisten_file.main([str(source), "--diarize", "--label", "Call"]) == 0
    assert seen["diarize"] is True
    assert seen["speaker_track"] == "Call"
    assert seen["hf_token"] == "not-a-real-token"
    assert seen["diarize_model"] == "example/diarizer"


def test_a_missing_model_does_not_convert_or_download(tmp_path, monkeypatch):
    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    _settings(monkeypatch, tmp_path, weights=False)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffprobe, path: 1)

    def convert(ffmpeg, src, wav):
        raise AssertionError("conversion ran before the weights were known to be local")

    monkeypatch.setattr(relisten_file, "convert", convert)
    code = relisten_file.main([str(source), "--model", "missing/model"])
    assert code == 2


def test_an_unconfigured_machine_stops_before_offline_or_conversion(tmp_path, monkeypatch):
    import bootstrap

    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffprobe, path: 1)
    monkeypatch.setattr(bootstrap, "read_settings", lambda path=None: {})

    def offline():
        raise AssertionError("offline mode was entered with no storage root")

    monkeypatch.setattr(bootstrap, "enforce_offline", offline)
    assert relisten_file.main([str(source)]) == 2


def _stub_one_stream(monkeypatch, tmp_path):
    """A one-stream file whose recognition is replaced, so `--out` can be asserted exactly."""
    source = tmp_path / "call.wav"
    _pcm(source, 1, 16000, (1000).to_bytes(2, "little", signed=True) * 800)
    _pretend_ffmpeg(monkeypatch)
    _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(relisten_file, "audio_stream_count", lambda ffmpeg, path: 1)
    monkeypatch.setattr(relisten_file, "convert", lambda ffmpeg, src, wav: "")
    seen = {}

    def fake_run(transcript_path, tracks, **kwargs):
        seen["kwargs"] = kwargs
        return {"output": kwargs["out_path"], "error": "", "segments": 1,
                "vocabulary": "", "diarize_error": ""}

    monkeypatch.setattr(relisten, "run", fake_run)
    return source, seen


@pytest.mark.parametrize("name", ["name.transcript.txt", "name.md"])
def test_out_naming_a_file_writes_that_file(tmp_path, monkeypatch, capsys, name):
    """A path that does not exist yet is the file, not a directory created to hold another name."""
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    target = tmp_path / name

    assert relisten_file.main([str(source), "--out", str(target)]) == 0

    expected = os.path.abspath(target)
    assert seen["kwargs"]["out_path"] == expected
    assert not os.path.isdir(expected)
    assert expected in capsys.readouterr().out
    assert not expected.endswith(f"{os.sep}call_relistened.md")


def test_out_that_is_already_a_directory_names_the_file_inside_it(tmp_path, monkeypatch, capsys):
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    out = tmp_path / "notes"
    out.mkdir()

    assert relisten_file.main([str(source), "--out", str(out)]) == 0

    expected = os.path.join(os.path.abspath(out), "call_relistened.md")
    assert seen["kwargs"]["out_path"] == expected
    assert expected in capsys.readouterr().out


def test_out_ending_in_a_slash_is_a_directory_even_when_it_does_not_exist(tmp_path, monkeypatch,
                                                                        capsys):
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    out = tmp_path / "fresh"
    assert not out.exists()

    assert relisten_file.main([str(source), "--out", str(out) + "/"]) == 0

    assert out.is_dir()
    expected = os.path.join(os.path.abspath(out), "call_relistened.md")
    assert seen["kwargs"]["out_path"] == expected
    assert expected in capsys.readouterr().out


def test_out_file_creates_a_missing_parent_and_does_not_become_a_directory(tmp_path, monkeypatch,
                                                                         capsys):
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    target = tmp_path / "missing" / "deeper" / "name.transcript.txt"
    assert not target.parent.exists()

    assert relisten_file.main([str(source), "--out", str(target)]) == 0

    expected = os.path.abspath(target)
    assert seen["kwargs"]["out_path"] == expected
    assert target.parent.is_dir()
    assert not os.path.isdir(expected)
    assert expected in capsys.readouterr().out


def test_out_naming_an_existing_file_keeps_it_and_writes_a_numbered_one(tmp_path, monkeypatch,
                                                                         capsys):
    """A re-run must not erase the earlier reading, in the file form as in the directory form."""
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    target = tmp_path / "name.transcript.txt"
    target.write_text("earlier reading", encoding="utf-8")
    (tmp_path / "name.transcript-2.txt").write_text("second reading", encoding="utf-8")

    assert relisten_file.main([str(source), "--out", str(target)]) == 0

    expected = os.path.abspath(tmp_path / "name.transcript-3.txt")
    assert seen["kwargs"]["out_path"] == expected
    assert target.read_text(encoding="utf-8") == "earlier reading"
    assert expected in capsys.readouterr().out


def test_out_naming_a_fresh_file_is_used_unnumbered(tmp_path):
    """The boundary below the one above: nothing there yet, so no -2."""
    source = tmp_path / "call.wav"
    source.write_bytes(b"x")
    path, error = relisten_file.destination(str(source), str(tmp_path / "name.transcript.txt"))
    assert error == ""
    assert path == os.path.abspath(tmp_path / "name.transcript.txt")


@pytest.mark.parametrize("spelling", ["same", "relative", "symlink"])
def test_out_naming_the_input_is_refused_and_the_recording_is_untouched(tmp_path, monkeypatch,
                                                                       capsys, spelling):
    source, seen = _stub_one_stream(monkeypatch, tmp_path)
    before = source.read_bytes()
    if spelling == "same":
        out = str(source)
    elif spelling == "relative":
        monkeypatch.chdir(tmp_path)
        out = os.path.join(".", source.name)
    else:
        link = tmp_path / "alias.wav"
        link.symlink_to(source)
        out = str(link)

    assert relisten_file.main([str(source), "--out", out]) == 2

    assert "kwargs" not in seen
    assert source.read_bytes() == before
    assert "input file" in capsys.readouterr().err
