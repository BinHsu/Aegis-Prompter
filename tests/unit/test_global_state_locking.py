"""Warm-up must not hold the lock that singleton construction needs.

`global_state` is imported **inside** the test bodies, not at module scope. Importing it pulls
`mlx_whisper`, `webrtcvad` and `sounddevice`, and `tests/unit/test_app_screens.py` asserts that
those are absent from `sys.modules` -- pytest imports every test module during collection, before
running anything, so a module-scope import here would make that assertion pass vacuously.
"""
import os
import sys
import threading
import time

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


class SlowTranscriber:
    """Stands in for the real one, whose constructor loads a model into the NPU."""

    entered = threading.Event()
    release = threading.Event()

    def __init__(self, *args, **kwargs):
        SlowTranscriber.entered.set()
        SlowTranscriber.release.wait(10)

    @staticmethod
    def find_device_index(keywords, fallback_to_default=True):
        return (0, "fake input") if fallback_to_default else (None, "Not Found")

    @staticmethod
    def resolve_input_device(name):
        # The Speaker track resolves its microphone by name now (R26). Kept as a stub for the
        # same reason as the constructor: this test is about lock behaviour, and touching a real
        # device table would make it depend on the machine it runs on.
        return 0, "fake input"


@pytest.fixture
def fresh_singleton(monkeypatch):
    # Deliberately NOT `importorskip`. `global_state` pulls the whole audio stack, and if that
    # cannot be imported the product cannot run at all — a skip would report the suite green over
    # a machine where nothing works. That is exactly what happened on the Python 3.12 rebuild:
    # `webrtcvad` failed on a removed `pkg_resources` and these three tests silently vanished.
    import global_state as gs
    monkeypatch.setattr(gs, "Transcriber", SlowTranscriber)
    SlowTranscriber.entered.clear()
    SlowTranscriber.release.clear()
    monkeypatch.setattr(gs.GlobalState, "_instance", None)
    yield gs
    SlowTranscriber.release.set()
    gs.GlobalState._instance = None


def test_warm_up_does_not_block_singleton_construction(fresh_singleton):
    """Warm-up runs for minutes on a real model (V33). If it holds the class-level `_lock` that
    `__new__` takes, the Streamlit script thread blocks on `get_global_state()` for that whole
    window -- freezing the UI precisely while download and warm-up progress is the only thing
    worth showing (R23, R39)."""
    gs = fresh_singleton
    state = gs.GlobalState()

    warming = threading.Thread(target=state.warm_up, daemon=True)
    warming.start()
    assert SlowTranscriber.entered.wait(5), "warm-up never reached the model load"

    # Warm-up is now inside its critical section. Constructing the singleton must still return.
    started = time.time()
    again = gs.GlobalState()
    elapsed = time.time() - started

    assert again is state
    assert elapsed < 1.0, (
        f"GlobalState() blocked for {elapsed:.1f}s while warm-up held the lock — on a real model "
        "that wait is minutes, not seconds"
    )

    SlowTranscriber.release.set()
    warming.join(timeout=10)
    assert state.is_warm is True


def test_the_construction_lock_and_the_state_lock_are_different_objects(fresh_singleton):
    gs = fresh_singleton
    state = gs.GlobalState()
    assert state._state_lock is not gs.GlobalState._lock


def test_start_recording_refuses_before_warm_up(fresh_singleton):
    """R24/R25: Start is only reachable once warm-up is confirmed complete, and the engine says so
    rather than opening a stream against transcribers that do not exist."""
    gs = fresh_singleton
    state = gs.GlobalState()
    with pytest.raises(RuntimeError, match="warm_up"):
        state.start_recording()
    assert state.is_running is False
