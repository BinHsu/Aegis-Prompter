"""Participant-track backend selection and helper lifecycle (R1, R5, R6, R7, R25, R39).

No real tap is created here: the helper is replaced by a script that prints whatever this test
wants it to print. That is the point -- the branches worth testing are the ones a working machine
never takes, and a test that needs a working tap could only ever confirm the happy path.
"""

import json
import os
import stat
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import audio_devices as ad  # noqa: E402
import system_audio as sa  # noqa: E402


@pytest.fixture(autouse=True)
def never_touch_portaudio(monkeypatch):
    """Re-initialising PortAudio for real would destroy any stream the suite has open, and the
    fake helper publishes no device, so waiting for one would always time out."""
    monkeypatch.setattr(sa, "reinitialize_portaudio", lambda: None)
    monkeypatch.setattr(sa, "wait_for_device", lambda name, **kwargs: True)


def fake_helper(tmp_path, stdout, exit_code=0, name="aegis_tap"):
    """A stand-in helper that prints `stdout` and then blocks, the way the real one does."""
    path = tmp_path / name
    lines = ["#!/bin/sh"]
    if stdout:
        # `printf '%s\n'` with no argument still emits a newline, which reads as a non-empty line
        # and sends the caller down the wrong branch. Emit nothing when nothing was asked for.
        lines.append("printf '%s\\n' '%s'" % ("%s", stdout.replace("'", "'\\''")))
    lines.append("exit %d" % exit_code if exit_code or not stdout
                 else "while true; do sleep 1; done")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


OK_LINE = json.dumps({"ok": True, "device_name": "Aegis System Audio",
                      "sample_rate": 48000, "channels": 1})

# Captured before the autouse fixture replaces the module attribute, so the two tests that are
# *about* the wait loop can call the real one.
REAL_WAIT_FOR_DEVICE = sa.wait_for_device


# ===== Capability, not enumeration =====

def test_capability_is_decided_without_looking_for_the_device(monkeypatch, tmp_path):
    """The circularity that shapes this: the tap's device exists only while the helper runs, and
    the helper must not run before Start (R25) -- yet the panel reports the backend before Start.
    So capability must not consult the device list at all."""
    monkeypatch.setattr(sa, "HELPER_PATH", fake_helper(tmp_path, OK_LINE))
    monkeypatch.setattr(sa, "blackhole_device",
                        lambda: pytest.fail("capability must not enumerate devices"))
    ok, reason = sa.tap_capability()
    assert (ok, reason) == (True, "")


def test_a_missing_helper_is_a_reason_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "HELPER_PATH", str(tmp_path / "does-not-exist"))
    ok, reason = sa.tap_capability()
    assert ok is False
    assert "setup_mac.sh" in reason, "the reason must say how to fix it (R39)"


def test_a_helper_that_is_not_executable_is_reported_distinctly(monkeypatch, tmp_path):
    path = tmp_path / "aegis_tap"
    path.write_text("#!/bin/sh\n")
    path.chmod(0o644)
    monkeypatch.setattr(sa, "HELPER_PATH", str(path))
    ok, reason = sa.tap_capability()
    assert ok is False and "executable" in reason


def test_an_old_macos_names_the_floor(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "HELPER_PATH", fake_helper(tmp_path, OK_LINE))
    monkeypatch.setattr(sa, "_macos_version", lambda: (13, 6))
    ok, reason = sa.tap_capability()
    # 14.2 is the real floor (V6), and declining per-app capture is what keeps it there (V8).
    assert ok is False and "14.2" in reason


# ===== Which backend, and in what order =====

def test_the_tap_wins_where_it_is_possible(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "HELPER_PATH", fake_helper(tmp_path, OK_LINE))
    monkeypatch.setattr(sa, "blackhole_device", lambda: (9, "BlackHole 2ch"))
    assert sa.available_backend()[0] == sa.BACKEND_TAP


def test_blackhole_is_the_fallback_and_says_why(monkeypatch, tmp_path):
    monkeypatch.setattr(sa, "HELPER_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(sa, "blackhole_device", lambda: (9, "BlackHole 2ch"))
    backend, detail = sa.available_backend()
    assert backend == sa.BACKEND_BLACKHOLE
    assert "BlackHole 2ch" in detail and "tap unavailable" in detail


def test_no_backend_at_all_is_a_reported_state(monkeypatch, tmp_path):
    """The provisioning stance leaves BlackHole uninstalled on machines that can run the tap, so
    'neither is available' is reachable and must not look like success."""
    monkeypatch.setattr(sa, "HELPER_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(sa, "blackhole_device", lambda: (None, ""))
    backend, detail = sa.available_backend()
    assert backend == sa.BACKEND_NONE and detail


def test_blackhole_lookup_survives_an_unavailable_audio_stack(monkeypatch):
    def boom():
        raise OSError("PortAudio not initialised")
    monkeypatch.setattr(ad, "list_input_devices", boom)
    assert sa.blackhole_device() == (None, "")


# ===== Helper lifecycle =====

def test_start_returns_what_the_helper_published(monkeypatch, tmp_path):
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, OK_LINE))
    try:
        info = tap.start()
        assert info["device_name"] == "Aegis System Audio"
        assert info["sample_rate"] == 48000
    finally:
        tap.stop()


def test_a_helper_that_reports_failure_raises_rather_than_returning_none(monkeypatch, tmp_path):
    """Returning a flag here would produce a session that captures the operator and nothing else,
    with nothing said about it. The caller has to choose a fallback, so it has to be told."""
    line = json.dumps({"ok": False, "stage": "create-tap", "status": -1, "detail": "permission"})
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, line, exit_code=1))
    with pytest.raises(RuntimeError, match="create-tap"):
        tap.start()
    assert tap.process is None, "a failed start must not leave the subprocess behind"


def test_a_helper_that_dies_silently_raises(monkeypatch, tmp_path):
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, "", exit_code=3))
    with pytest.raises(RuntimeError, match="exited before publishing"):
        tap.start()


def test_a_helper_that_emits_garbage_raises(monkeypatch, tmp_path):
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, "not json at all", exit_code=1))
    with pytest.raises(RuntimeError, match="no JSON"):
        tap.start()


def test_stop_is_idempotent_and_safe_when_nothing_ran(tmp_path):
    tap = sa.SystemAudioTap(helper_path=str(tmp_path / "missing"))
    tap.stop()
    tap.stop()


def test_starting_twice_is_refused(tmp_path):
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, OK_LINE))
    try:
        tap.start()
        with pytest.raises(RuntimeError, match="already running"):
            tap.start()
    finally:
        tap.stop()


def test_a_published_device_that_never_appears_is_a_failure_not_a_silent_session(monkeypatch,
                                                                                 tmp_path):
    """The failure the wait loop exists for, and the reason it is not merely a retry.

    Publishing an aggregate device and other processes' HAL clients learning about it are separate
    events: measured 2026-08-12, an immediate re-initialisation saw the device 0 times out of 5,
    and one attempt 50 ms later saw it 5 times out of 5. Reliably wrong is worse than flaky --
    without the wait, every session would log a successful tap over an empty Participant track.
    If the device never turns up, that has to end the attempt so the caller can fall back.
    """
    monkeypatch.setattr(sa, "wait_for_device", lambda name, **kwargs: False)
    tap = sa.SystemAudioTap(helper_path=fake_helper(tmp_path, OK_LINE))
    with pytest.raises(RuntimeError, match="never saw it"):
        tap.start()
    assert tap.process is None, "the helper must not be left running behind a failed start"


def test_wait_for_device_gives_up_rather_than_hanging_start(monkeypatch):
    """A bounded wait, because this runs inside Start with an operator watching."""
    monkeypatch.setattr(sa, "reinitialize_portaudio", lambda: None)
    monkeypatch.setattr("audio_devices.list_input_devices", lambda: [{"index": 0, "name": "other"}])
    assert REAL_WAIT_FOR_DEVICE("Aegis System Audio", timeout=0.15, interval=0.01) is False


def test_wait_for_device_tolerates_enumeration_failing_mid_wait(monkeypatch):
    """PortAudio is being torn down and rebuilt in this loop; a query landing mid-cycle raises,
    and that is a reason to try again rather than to abandon the tap."""
    monkeypatch.setattr(sa, "reinitialize_portaudio", lambda: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("PortAudio not initialised")
        return [{"index": 0, "name": "Aegis System Audio"}]

    monkeypatch.setattr("audio_devices.list_input_devices", flaky)
    assert REAL_WAIT_FOR_DEVICE("Aegis System Audio", timeout=2.0, interval=0.01) is True
