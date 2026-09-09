#!/usr/bin/env python3
"""Run speaker diarization in the pinned venv, and print turns as JSON on stdout.

**Why this is a subprocess and not a function.** The product venv runs `pyannote.audio` 4.0.7,
where `SpeakerDiarization` defaults its `plda` parameter to `pyannote/speaker-diarization-community-1`
and loads it unconditionally. That repository is **gated** and answers 401 without a Hugging Face
token, so on 4.0.7 there is no token-free diarization path at all -- see **V93**. Version 3.3.2 has
no PLDA stage and runs from the three ungated pieces this repo already documents.

Pinning 3.3.2 in the product venv was rejected: the **voice gate** also imports `pyannote.audio`,
and every gate measurement from **V82** onward was taken on 4.0.7. Moving that version to fix an
optional post-meeting feature would put the live path's evidence in question. So the version lives
in `.venv-diarize`, this file is its entry point, and `src/diarize.py` calls it with `subprocess`.
One `rm -rf .venv-diarize` removes the whole thing.

**Four pins, each found by running it rather than by reading release notes**, recorded so nobody
rediscovers them:

- `pyannote.audio==3.3.2` -- the last 3.x, and the last without the gated PLDA default.
- `torch==2.8.0`, `torchaudio==2.8.0` -- 3.3.2 references `torchaudio.AudioMetaData`, removed in
  torchaudio 2.9.
- `huggingface_hub==0.25.2` -- 3.3.2 calls `hf_hub_download(use_auth_token=...)`, removed in 1.x.
- `matplotlib` -- imported unconditionally by `pyannote.audio.tasks.segmentation.mixins`.

**Two environment variables, not one.** `HF_HOME` is not enough: pyannote 3.x resolves models
through its own `PYANNOTE_CACHE` (default `~/.cache/torch/pyannote`), so with only `HF_HOME` set it
looks in an empty directory, finds nothing, and -- offline -- reports the weights as missing rather
than as misplaced. Both are set here so the caller cannot get it half right.

USAGE
    .venv-diarize/bin/python tools/diarize_runner.py <wav> [--model ID] [--max-speakers N]

Prints one JSON object on stdout: {"turns": [{"start": s, "end": s, "speaker": "SPEAKER_00"}, ...]}
or {"error": "..."}. Nothing else goes to stdout, so the caller can parse it; diagnostics go to
stderr. **The audio itself is never echoed** -- this reads the operator's meeting recordings.
"""
import argparse
import json
import os
import sys

DEFAULT_MODEL = "ivrit-ai/pyannote-speaker-diarization-3.1"


def _prepare_caches(hf_home):
    """Point both cache mechanisms at the product's weights, and forbid the network.

    Offline is deliberate rather than incidental: this runs on meeting audio, and a diarization
    pass that silently reaches the network is the thing **R15** exists to prevent. If a weight is
    missing the correct outcome is a clear failure, not a download.
    """
    os.environ["HF_HOME"] = hf_home
    os.environ["PYANNOTE_CACHE"] = os.path.join(hf_home, "hub")
    os.environ["HF_HUB_OFFLINE"] = "1"


def _allow_known_pickle_globals():
    """Allowlist the four classes 3.3.2's checkpoints carry, and nothing else.

    torch 2.6 made `weights_only=True` the default. The two documented ways past it are
    `weights_only=False`, which permits arbitrary code execution from the checkpoint, and
    allowlisting specific classes. This takes the narrow one, so any global these files do not
    already contain still raises.

    **The list was discovered by loading the pipeline repeatedly, not by reading release notes** --
    each attempt names exactly one blocked global, so four attempts enumerated the set. All four are
    plain metadata: a version string and pyannote's own task-description types. If a future weights
    update adds a fifth, the failure names it and it belongs here only after someone has looked at
    what it is.
    """
    import torch
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    torch.serialization.add_safe_globals(
        [torch.torch_version.TorchVersion, Specifications, Problem, Resolution]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--hf-home", default="")
    parser.add_argument("--min-speakers", type=int, default=1)
    parser.add_argument("--max-speakers", type=int, default=8)
    parser.add_argument("--num-speakers", type=int, default=0)
    args = parser.parse_args()

    hf_home = args.hf_home or os.environ.get("HF_HOME") or ""
    if not hf_home:
        print(json.dumps({"error": "no HF_HOME: pass --hf-home so the weights can be found"}))
        return 2
    _prepare_caches(os.path.abspath(hf_home))

    try:
        _allow_known_pickle_globals()
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(args.model)
        if pipeline is None:
            raise RuntimeError(f"{args.model} did not load; the weights are probably not cached")
        kwargs = {"min_speakers": args.min_speakers, "max_speakers": args.max_speakers}
        if args.num_speakers:
            kwargs = {"num_speakers": args.num_speakers}
        annotation = pipeline(args.wav, **kwargs)
    except Exception as exc:                      # noqa: BLE001 - the caller wants the reason
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1

    turns = [
        {"start": round(segment.start, 3), "end": round(segment.end, 3), "speaker": str(label)}
        for segment, _track, label in annotation.itertracks(yield_label=True)
    ]
    print(json.dumps({"turns": turns}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
