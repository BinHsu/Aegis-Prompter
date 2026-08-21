"""Microphone selection (R26): resolve by name, override the default, never reload the model.

No audio device is opened here. `list_input_devices` and `default_input_name` are the only two
places the real hardware is consulted, so both are replaced and everything else is exercised for
real -- which is the point: the logic that decides *which* microphone must be testable on a
machine that has none of them.
"""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import audio_devices as ad  # noqa: E402
import transcriber as tr  # noqa: E402
from src import bootstrap  # noqa: E402

DEVICES = [
    {"index": 0, "name": "MacBook Pro Microphone"},
    {"index": 3, "name": "AirPods Pro"},
    {"index": 7, "name": "Scarlett Solo USB"},
]


@pytest.fixture
def devices(monkeypatch):
    """Present a fixed device table, and a system default that is *not* the first entry.

    Deliberately not index 0: a resolver that quietly returns the first input would pass an
    identity-ordered fixture and fail on the machine.

    Patched on `audio_devices`, which is where the resolver looks them up. Patching the names
    re-exported by `transcriber` would silently miss -- the function closes over its own module
    globals -- and every assertion below would then be measuring this machine's real devices.
    """
    monkeypatch.setattr(ad, "list_input_devices", lambda: list(DEVICES))
    monkeypatch.setattr(ad, "default_input_name", lambda: "AirPods Pro")
    return DEVICES


# ===== Resolution =====

def test_empty_preference_follows_the_system_default(devices):
    assert tr.Transcriber.resolve_input_device("") == (3, "AirPods Pro")
    assert tr.Transcriber.resolve_input_device(None) == (3, "AirPods Pro")


def test_exact_name_wins_over_substring(devices, monkeypatch):
    # "AirPods" is a substring of "AirPods Pro Max", so a substring-first resolver would return
    # the wrong device for an operator who owns both.
    monkeypatch.setattr(ad, "list_input_devices", lambda: [
        {"index": 1, "name": "AirPods Pro Max"},
        {"index": 2, "name": "AirPods"},
    ])
    assert tr.Transcriber.resolve_input_device("AirPods") == (2, "AirPods")


def test_substring_match_survives_a_renamed_device(devices):
    # macOS has renamed built-in inputs across releases; a stored name from an older run must
    # still find its device rather than silently falling back.
    assert tr.Transcriber.resolve_input_device("MacBook Pro Microphone (Built-in)")[0] == 0
    assert tr.Transcriber.resolve_input_device("Scarlett")[0] == 7


def test_unmatched_preference_resolves_to_nothing_not_to_the_default(devices):
    """The failure that matters: a disconnected headset must not silently become the built-in.

    Returning the default here would record the room while the panel names a headset -- the
    operator has no way to notice, which is the whole objection.
    """
    assert tr.Transcriber.resolve_input_device("Yeti Nano") == (None, "")


def test_no_devices_and_no_default_is_reported_not_guessed(monkeypatch):
    monkeypatch.setattr(ad, "list_input_devices", lambda: [])
    monkeypatch.setattr(ad, "default_input_name", lambda: "")
    assert tr.Transcriber.resolve_input_device("") == (None, "")


# ===== Changing device without reloading the model =====

class _FakeTranscriber:
    """`Transcriber` with `__init__` bypassed, so no model is loaded to test device switching."""

    def __init__(self, device_name):
        self.device_name = device_name
        self.device_idx = None
        self.is_running = False

    set_device = tr.Transcriber.set_device
    resolve_input_device = staticmethod(tr.Transcriber.resolve_input_device)


def test_set_device_changes_only_the_device_fields(devices):
    t = _FakeTranscriber("MacBook Pro Microphone")
    t.device_idx = 0
    before = set(vars(t))

    idx, name = t.set_device("Scarlett Solo USB")

    assert (idx, name) == (7, "Scarlett Solo USB")
    assert t.device_idx == 7 and t.device_name == "Scarlett Solo USB"
    # V33: constructing a Transcriber preloads the model. Switching must not add or replace any
    # other state -- if this ever grows a `self.model = ...`, a dropdown change costs minutes.
    assert set(vars(t)) == before


def test_set_device_refuses_while_running(devices):
    t = _FakeTranscriber("MacBook Pro Microphone")
    t.is_running = True
    with pytest.raises(RuntimeError, match="running"):
        t.set_device("AirPods Pro")
    assert t.device_name == "MacBook Pro Microphone"


def test_set_device_to_a_missing_device_reports_it(devices):
    t = _FakeTranscriber("")
    idx, name = t.set_device("Yeti Nano")
    assert (idx, name) == (None, "")
    # The preference is still recorded: the operator chose it, and it may reappear at Start.
    assert t.device_name == "Yeti Nano"


# ===== Persistence =====

def test_mic_device_is_sticky_and_round_trips(tmp_path):
    env = tmp_path / ".env"
    bootstrap.write_settings({"STORAGE_ROOT": str(tmp_path), "MIC_DEVICE": "Scarlett Solo USB"},
                             path=str(env))
    assert bootstrap.read_settings(path=str(env))["MIC_DEVICE"] == "Scarlett Solo USB"


def test_mic_device_does_not_force_a_restart():
    """Changing the microphone must not demand a process restart.

    `fingerprint` is what `needs_restart` compares, and it exists for settings baked into the
    process at import (V19). The device is read when a stream opens, so including it here would
    make every dropdown change look like a configuration change requiring a relaunch -- which is
    exactly the reconstruct-vs-reload confusion this item had to avoid.
    """
    base = {"STORAGE_ROOT": "/x", "ASR_MODEL": "mlx-community/whisper-large-v3-turbo",
            "MIC_DEVICE": ""}
    changed = dict(base, MIC_DEVICE="AirPods Pro")
    assert bootstrap.fingerprint(base) == bootstrap.fingerprint(changed)


def test_mic_device_is_absent_from_a_fresh_env_as_empty_not_missing(tmp_path):
    env = tmp_path / ".env"
    bootstrap.write_settings({"STORAGE_ROOT": str(tmp_path)}, path=str(env))
    # R32: absent configuration renders as a blank, and blank is meaningful here -- it is the
    # default, "follow macOS", not an unset error.
    assert bootstrap.read_settings(path=str(env))["MIC_DEVICE"] == ""
