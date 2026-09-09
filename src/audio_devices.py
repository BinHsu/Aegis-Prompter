"""Input-device enumeration. Nothing here loads a model or opens a stream.

Split out of `transcriber.py` for the same reason as `text_filters.py`: importing `transcriber`
pulls `mlx_whisper`, `webrtcvad` and `sounddevice`, and the pre-flight panel needs the device list
while the model may still be downloading. Dragging the ASR stack in to populate a dropdown would
import `huggingface_hub` earlier than the boot sequence intends, which is the shape of the bug
V19 describes.

`sounddevice` (PortAudio) is the only dependency and it is imported lazily, so this module is
importable on a machine where the audio stack is absent -- the caller sees the failure at the call,
where it can be reported, rather than at import, where it takes the whole page down.

Nothing here may grow a dependency. If it needs one, it belongs in `transcriber.py` instead.
"""

SYSTEM_DEFAULT_INPUT = ""
"""The stored value meaning "follow whatever macOS currently calls the default input".

Stored rather than resolved so the preference survives the default changing -- an operator who
never expressed a choice should keep getting the system's answer, not a snapshot of it (R26).
Empty is therefore a meaningful value, not an unset one.
"""


def list_input_devices():
    """Every device that can be recorded from, as `[{"index": int, "name": str}, ...]`.

    Enumeration only. `sd.query_devices()` reads PortAudio's device table and opens nothing, so
    this is safe to call before Start (R25). Duplicate names are kept -- two identical entries
    mean two real devices, and hiding one would make the other unselectable.

    Caveat worth knowing before trusting a stale list: PortAudio snapshots the device table when
    it initialises, so a headset paired *after* this process started may not appear until the
    process restarts. Not worked around here; the dropdown re-reads on every full script run,
    which is as fresh as the library allows.
    """
    import sounddevice as sd
    return [{"index": i, "name": dev["name"]}
            for i, dev in enumerate(sd.query_devices())
            if dev["max_input_channels"] > 0]


def default_input_name():
    """The name macOS currently reports as the default input, or `""` if there is none."""
    import sounddevice as sd
    try:
        idx = sd.default.device[0]
        if idx is not None and idx >= 0:
            return sd.query_devices(idx)["name"]
    except Exception:
        pass
    return ""


def resolve_input_device(name):
    """Turn a stored device *name* into `(index, name)` for this run, or `(None, "")`.

    Names, not indices, are what gets stored anywhere that outlives a run: PortAudio's indices
    shift between runs and between machines, so a persisted index eventually points at a
    different microphone with no error to notice (AGENTS.md). Substring match, because a device
    can gain or lose a suffix across OS versions.

    `SYSTEM_DEFAULT_INPUT` means "ask the OS now", which is what every operator gets until they
    override it (R26).

    An unmatched name resolves to nothing rather than to the default. Falling back would leave
    the panel naming a headset while the built-in microphone recorded the room, and the operator
    would have no way to notice -- silent substitution is worse than a visible gap.
    """
    name = (name or "").strip()
    if not name:
        name = default_input_name()
        if not name:
            return None, ""
    devices = list_input_devices()
    for dev in devices:                                  # exact first: one device's name can be
        if dev["name"] == name:                          # a substring of another's
            return dev["index"], dev["name"]
    lowered = name.lower()
    for dev in devices:
        if lowered in dev["name"].lower() or dev["name"].lower() in lowered:
            return dev["index"], dev["name"]
    return None, ""
