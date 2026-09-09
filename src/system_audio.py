"""Lifecycle of the system-audio capture helper, and which backend a machine can use.

Two backends produce the Participant track, and the choice is a **capability, not a preference**
(R7): the Core Audio process tap where the OS and the built helper allow it, BlackHole where they
do not. Nothing here is configurable, because there is nothing for an operator to decide -- a
machine either can run a tap or cannot.

Deliberately no ASR imports, for the same reason as `audio_devices`: the pre-flight panel reports
which backend is available before anything heavy has loaded.

**The tap is started at Start and never before.** Creating a tap *is* capture (R25), so nothing
here may be called from an import, a page load, or warm-up. `SystemAudioTap.start()` is reachable
only from `GlobalState.start_recording`.
"""

import json
import logging
import os
import platform
import signal
import subprocess
import time

logger = logging.getLogger("SystemAudio")

TAP_DEVICE_NAME = "Aegis System Audio"
"""The input device the helper publishes. Matched by name like every other device (AGENTS.md)."""

BLACKHOLE_KEYWORDS = ["BlackHole 2ch", "BlackHole"]

HELPER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native", "aegis_tap")

TAP_MIN_MACOS = (14, 2)
"""14.2, read from `AudioHardwareTapping.h` (V6). Not 14.4, and not 26.0 -- declining per-app
capture (R5) is what keeps the floor this low (V8)."""

BACKEND_TAP = "tap"
BACKEND_BLACKHOLE = "blackhole"
BACKEND_NONE = "none"


def _macos_version():
    try:
        parts = platform.mac_ver()[0].split(".")
        return tuple(int(p) for p in parts[:2]) if parts and parts[0] else (0, 0)
    except ValueError:
        return (0, 0)


def tap_capability():
    """Can this machine run the tap? Returns `(bool, reason)`; the reason is shown to the operator.

    **Capability, not enumeration.** The obvious check -- look for the device -- is circular: the
    tap's aggregate device exists only while the helper runs (V9), and the helper must not run
    before Start (R25), yet the pre-flight panel has to report the backend *before* Start. So this
    asks what could work, not what is present, and a helper that then fails at Start is handled as
    a runtime failure with a visible message (R39) rather than as a wrong prediction.
    """
    if platform.system() != "Darwin":
        return False, "not macOS"
    version = _macos_version()
    if version < TAP_MIN_MACOS:
        return False, f"macOS {version[0]}.{version[1]} is below {TAP_MIN_MACOS[0]}.{TAP_MIN_MACOS[1]}"
    if not os.path.exists(HELPER_PATH):
        return False, "capture helper not built (run setup_mac.sh)"
    if not os.access(HELPER_PATH, os.X_OK):
        return False, "capture helper is not executable"
    return True, ""


def blackhole_device():
    """`(index, name)` of a BlackHole input, or `(None, "")`. Present only if the operator installed it."""
    from audio_devices import list_input_devices
    try:
        devices = list_input_devices()
    except Exception:
        return None, ""
    for keyword in BLACKHOLE_KEYWORDS:
        for device in devices:
            if keyword.lower() in device["name"].lower():
                return device["index"], device["name"]
    return None, ""


def available_backend():
    """Which backend this machine would use, decided without opening anything.

    Returns `(backend, detail)`. The tap wins where it is possible: it needs no driver install,
    leaves the operator's output device alone (V10, R6), and is the route new hardware takes.
    BlackHole is kept for machines that cannot run a tap, not as a competing option.
    """
    ok, reason = tap_capability()
    if ok:
        return BACKEND_TAP, "Core Audio process tap"
    index, name = blackhole_device()
    if index is not None:
        return BACKEND_BLACKHOLE, f"{name} (tap unavailable: {reason})"
    return BACKEND_NONE, reason or "no system-audio source"


def reinitialize_portaudio():
    """Make PortAudio re-read the device table.

    PortAudio snapshots devices when it initialises, and this process always starts before the
    helper does -- so without this the tap's device is invisible however correct everything else
    is (V61).

    Destroys any open stream, so it must happen **before** the capture streams are opened, never
    between them.
    """
    import sounddevice as sd
    sd._terminate()
    sd._initialize()


def wait_for_device(name, timeout=3.0, interval=0.05):
    """Re-initialise PortAudio until `name` appears, or give up. Returns True if it appeared.

    **A single re-initialisation is not enough, and the failure is not intermittent -- it is
    reliably wrong.** Measured 2026-08-12, five trials out of five: re-initialising immediately
    after the helper reports the device published never sees it, and one more attempt 50 ms later
    always does. Publishing an aggregate device and other processes' HAL clients learning about it
    are not the same event.

    That combination is the worst kind to ship. It is not flaky enough to catch in testing and not
    reliable enough to work: it would have produced sessions where the Participant track is
    silently empty, with every log line saying the tap started successfully.

    Polling rather than subscribing to a device-list notification because this runs once, at Start,
    with a hard deadline -- a listener would need a run loop this process does not have.
    """
    from audio_devices import list_input_devices
    deadline = time.monotonic() + timeout
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        try:
            if any(device["name"] == name for device in list_input_devices()):
                if attempts > 1:
                    logger.info("🎧 [Audio] '%s' appeared after %d attempts", name, attempts)
                return True
        except Exception as exc:
            logger.debug("device enumeration during wait: %s", exc)
        time.sleep(interval)
        reinitialize_portaudio()
    return False


class SystemAudioTap:
    """The helper subprocess. Owns the tap and its aggregate device for exactly its own lifetime.

    A crash tears both down with it, which is the property that matters: a half-dead tap would
    leave an input device on the operator's Mac that plays nothing and survives until a reboot.
    """

    def __init__(self, helper_path=HELPER_PATH):
        self.helper_path = helper_path
        self.process = None
        self.info = None

    def start(self, timeout=10.0):
        """Launch the helper and wait for it to publish. Returns its JSON info, or raises.

        Raising rather than returning a flag: the caller has to choose a fallback, and a silent
        `None` here would produce a session that captures the operator and nothing else -- the
        failure being silent is the whole objection.
        """
        if self.process is not None:
            raise RuntimeError("system-audio helper already running")
        self.process = subprocess.Popen(
            [self.helper_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        line = self.process.stdout.readline()
        if not line:
            code = self.process.poll()
            self.stop()
            raise RuntimeError(f"capture helper exited before publishing (code {code})")
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            self.stop()
            raise RuntimeError(f"capture helper emitted no JSON: {line.strip()!r}")
        if not info.get("ok"):
            self.stop()
            raise RuntimeError(
                f"capture helper failed at {info.get('stage')}: {info.get('detail') or info}"
            )
        self.info = info
        reinitialize_portaudio()
        name = info.get("device_name") or TAP_DEVICE_NAME
        if not wait_for_device(name):
            self.stop()
            raise RuntimeError(
                f"capture helper published '{name}' but PortAudio never saw it. The tap is alive "
                f"and unreachable, which would look like a working session with a silent "
                f"Participant track."
            )
        logger.info("🎧 [Audio] System-audio tap published as '%s' (%s Hz)",
                    name, info.get("sample_rate"))
        return info

    def stop(self):
        """SIGTERM, then wait. The helper destroys the aggregate device before the tap."""
        if self.process is None:
            return
        try:
            self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ [Audio] Capture helper ignored SIGTERM; killing it.")
            self.process.kill()
            self.process.wait(timeout=5)
        except Exception as exc:
            logger.warning("⚠️ [Audio] Capture helper teardown: %s", exc)
        finally:
            self.process = None
            self.info = None
            # Symmetrical with `start`, and for a sharper reason. PortAudio's table still lists
            # the destroyed device, so the next Start would find it immediately, treat the wait as
            # satisfied, and open a stream on an index that no longer refers to anything -- a
            # session that reports a working tap and captures nothing. Measured 2026-08-12: the
            # first end-to-end run saw the device still listed after teardown.
            try:
                reinitialize_portaudio()
            except Exception as exc:
                logger.debug("PortAudio re-init after teardown: %s", exc)
