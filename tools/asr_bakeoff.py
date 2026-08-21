#!/usr/bin/env python3
"""CLI ASR bake-off harness for R37 / R8 / R10 / latency (STATE 7.2).

Loads gitignored fixtures under fixtures/asr/, feeds float32 arrays into each
candidate, and prints a markdown table. Uses bootstrap so HF_HOME lands under
the configured storage root (R48, V19). No Streamlit (V52).

Does not change the product default ASR_MODEL.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import threading
import subprocess
import time
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SRC)


def _prefer_homebrew_ssl_bundle():
    """Homebrew CPython uses OpenSSL + certifi; corp MITM CAs often live in openssl@3's PEM.

    System /usr/bin/python3 (LibreSSL) already trusts the macOS keychain, so product `.venv`
    downloads can succeed while `.venv-bakeoff` fails with CERTIFICATE_VERIFY_FAILED. Prefer the
    brew openssl bundle when present and the caller has not set SSL_CERT_FILE.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    for candidate in (
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ):
        if os.path.isfile(candidate):
            os.environ["SSL_CERT_FILE"] = candidate
            os.environ.setdefault("REQUESTS_CA_BUNDLE", candidate)
            os.environ.setdefault("CURL_CA_BUNDLE", candidate)
            return


_prefer_homebrew_ssl_bundle()

# Bootstrap before huggingface_hub / mlx_whisper (V19).
import bootstrap  # noqa: E402
import model_search  # noqa: E402
from asr_eval import (  # noqa: E402
    TARGET_SR,
    assert_fixture_path_allowed,
    iter_fixture_wavs,
    load_wav_mono_float32,
    looks_traditional_chinese,
    score_nonspeech_texts,
)

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
V51_BASELINE_MS = 1380.0  # ~1.38 s incumbent call (REQUIREMENTS V51)

WHISPER_CANDIDATES = (
    ("distil-v3 (baseline)", "mlx-community/distil-whisper-large-v3", "whisper"),
    ("whisper-large-v3-turbo", "mlx-community/whisper-large-v3-turbo", "whisper"),
)

# Disqualified on provenance by **R50** (`docs/decisions/0012`), not on measurement -- these won
# the 2026-08-11 comparison and the numbers still stand. They are kept runnable, behind an
# explicit flag, for one reason: a comparison nobody can reproduce is a claim. Running them needs
# `mlx-qwen3-asr` installed by hand; it is no longer in `requirements.txt`.
QWEN_CANDIDATES = (
    ("Qwen3-ASR-1.7B", "Qwen/Qwen3-ASR-1.7B", "qwen"),
    ("Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-0.6B", "qwen"),
)
DISQUALIFIED_REASON = ("R50 — PRC-origin weights and PRC-origin loader package; "
                       "see docs/decisions/0012")


def _boot_hf_home(hf_home_override="", offline=True):
    """Point the run at a weight cache and, by default, forbid the network.

    `offline` is on by default because it is a **measurement** decision, not a convenience:
    `mlx_whisper.transcribe(path_or_hf_repo=...)` re-resolves the repo on every call, and
    `huggingface_hub` 1.27 turns that into an HTTPS round trip per inference. Observed
    2026-08-11: the same model measured 2542 ms/call online and ~600 ms offline, so a latency
    table taken with the network in the loop is measuring the link, not the model.

    `hf_home_override` lets a bake-off keep its weights outside the product's storage root, so the
    whole experiment stays deletable in one command.
    """
    settings = bootstrap.read_settings()
    if hf_home_override:
        models = os.path.abspath(os.path.expanduser(hf_home_override))
        os.makedirs(models, exist_ok=True)
        os.environ["HF_HOME"] = models
        if offline:
            bootstrap.enforce_offline()
        print(f"HF_HOME={models}  (override)")
        print(f"HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE', '0')}")
        return settings
    if not bootstrap.is_configured(settings):
        print(
            "No configured storage root. Open the app Configure screen once, "
            "or write STORAGE_ROOT into .env, so HF_HOME derives under R48.",
            file=sys.stderr,
        )
        sys.exit(2)
    paths = bootstrap.apply_environment(settings)
    if offline:
        bootstrap.enforce_offline()
    print(f"HF_HOME={os.environ.get('HF_HOME')}")
    print(f"storage models dir={paths.get('models')}")
    print(f"HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE', '0')}")
    return settings


def vad_speech_segments(samples, sample_rate=TARGET_SR, aggressiveness=3):
    """Mirror Transcriber VAD grouping: 30 ms frames, 0.4 s silence flush, 15 s max, 0.3 s min."""
    import numpy as np
    import webrtcvad

    if sample_rate != 16000:
        raise ValueError("webrtcvad path requires 16 kHz")
    vad = webrtcvad.Vad(aggressiveness)
    block = int(sample_rate * 0.03)
    silence_flush_limit = int(0.4 / 0.03)
    max_speech_chunks = int(15.0 / 0.03)
    min_samples = int(sample_rate * 0.3)

    audio = np.asarray(samples, dtype=np.float32)
    # Pad to whole frames
    pad = (-len(audio)) % block
    if pad:
        audio = np.concatenate([audio, np.zeros(pad, dtype=np.float32)])

    speech_buffer = []
    silence_frames = 0
    segments = []

    for i in range(0, len(audio), block):
        frame = audio[i : i + block]
        pcm = (frame * 32767.0).astype(np.int16)
        try:
            is_speech = vad.is_speech(pcm.tobytes(), sample_rate)
        except Exception:
            is_speech = False
        if is_speech:
            speech_buffer.append(pcm)
            silence_frames = 0
        else:
            silence_frames += 1
        if (
            (silence_frames >= silence_flush_limit or len(speech_buffer) >= max_speech_chunks)
            and speech_buffer
        ):
            packed = np.concatenate(speech_buffer).astype(np.float32) / 32767.0
            speech_buffer = []
            silence_frames = 0
            if len(packed) >= min_samples:
                segments.append(packed)

    if speech_buffer:
        packed = np.concatenate(speech_buffer).astype(np.float32) / 32767.0
        if len(packed) >= min_samples:
            segments.append(packed)
    return segments


def backend_kind_for(model_id):
    """Which backend scores this id — **including families the product refuses to dispatch to**.

    `model_search.family_for` answers a product question and `transcriber.resolve_backend` now
    refuses disqualified ids outright (**R50**). A measurement harness needs the opposite: it must
    still be able to load the model that was removed, or the comparison that justified removing it
    cannot be reproduced. This is the one place that difference is allowed to exist, and it is
    deliberately in `tools/` rather than in `src/`.
    """
    head = (model_id or "").split("/", 1)[0].lower()
    if head.startswith("qwen"):
        return "qwen"
    return model_search.family_for(model_id)["id"]


def resolve_qwen_backend():
    """Return (kind, module_or_none). kind is mlx_qwen3_asr | qwen3_asr_mlx | missing."""
    for name in ("mlx_qwen3_asr", "qwen3_asr_mlx"):
        try:
            mod = importlib.import_module(name)
            return name, mod
        except ImportError:
            continue
    return "missing", None


def make_transcribe_fn(kind, model_id, qwen_backend):
    """Return callable(audio_float32_np) -> text, holding NPU_LOCK like the product."""
    import numpy as np
    import mlx_whisper
    from transcriber import NPU_LOCK

    if kind == "whisper":
        # Warm once
        with NPU_LOCK:
            mlx_whisper.transcribe(
                np.zeros(16000, dtype=np.float32), path_or_hf_repo=model_id,
            )

        def _run(audio):
            arr = np.asarray(audio, dtype=np.float32)
            with NPU_LOCK:
                result = mlx_whisper.transcribe(
                    arr,
                    path_or_hf_repo=model_id,
                    fp16=True,
                    no_speech_threshold=0.6,
                    condition_on_previous_text=False,
                )
            return (result.get("text") or "").strip()

        return _run

    if kind == "qwen":
        backend_name, mod = qwen_backend
        if mod is None:
            raise RuntimeError("Qwen backend not importable")

        if backend_name == "mlx_qwen3_asr":
            # Warm / load by one short call
            with NPU_LOCK:
                mod.transcribe(np.zeros(16000, dtype=np.float32), model=model_id)

            def _run(audio):
                arr = np.asarray(audio, dtype=np.float32)
                with NPU_LOCK:
                    result = mod.transcribe(arr, model=model_id)
                text = getattr(result, "text", None)
                if text is None and isinstance(result, dict):
                    text = result.get("text", "")
                return (text or "").strip()

            return _run

        # qwen3_asr_mlx: class API
        model = mod.Qwen3ASR.from_pretrained(model_id)

        def _run(audio):
            arr = np.asarray(audio, dtype=np.float32)
            with NPU_LOCK:
                result = model.transcribe(arr)
            return (getattr(result, "text", None) or "").strip()

        return _run

    raise ValueError(f"unknown kind {kind}")



class ResourceSampler:
    """Poll this process's RSS and CPU while a candidate runs (FORMAL_MEASURE 'Resources').

    Deliberately shells out to `ps` rather than adding `psutil`: the measurement environment is
    meant to stay wipeable, and a dependency added for a bake-off outlives the bake-off.

    **RSS is only per-candidate when the candidate is the only one in the process.** Models are
    not unloaded between candidates, so a run scoring several inherits the earlier allocations.
    Run one candidate per invocation for figures that mean what they look like.
    """

    def __init__(self, interval=0.5):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.rss_start_mb = 0.0
        self.rss_peak_mb = 0.0
        self.cpu_samples = []

    @staticmethod
    def _sample():
        try:
            out = subprocess.run(
                ["ps", "-o", "rss=,%cpu=", "-p", str(os.getpid())],
                capture_output=True, text=True, timeout=5,
            ).stdout.split()
            return float(out[0]) / 1024.0, float(out[1])
        except Exception:
            return 0.0, 0.0

    def _loop(self):
        while not self._stop.is_set():
            rss, cpu = self._sample()
            self.rss_peak_mb = max(self.rss_peak_mb, rss)
            if cpu:
                self.cpu_samples.append(cpu)
            self._stop.wait(self.interval)

    def __enter__(self):
        self._mlx_reset_peak()
        self.rss_start_mb, _ = self._sample()
        self.rss_peak_mb = self.rss_start_mb
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return False

    @staticmethod
    def _mlx_peak_mb():
        """Peak MLX allocation in MB, or 0 if MLX is not loaded.

        This is the figure a resource claim should rest on. Sampling `ps` measures resident pages
        of memory-mapped weights, which is why it reported a 1.7B model at 317 MB and a 0.6B one at
        1808 MB -- an ordering that cannot be true and reproduced across workloads (V55).
        """
        try:
            import mlx.core as mx
        except Exception:
            return 0.0
        try:
            return mx.get_peak_memory() / (1024.0 * 1024.0)
        except Exception:
            return 0.0

    @staticmethod
    def _mlx_reset_peak():
        try:
            import mlx.core as mx
            mx.reset_peak_memory()
        except Exception:
            pass

    def summary(self):
        cpu = max(self.cpu_samples) if self.cpu_samples else 0.0
        return {
            "rss_start_mb": self.rss_start_mb,
            "rss_peak_mb": self.rss_peak_mb,
            "rss_delta_mb": max(0.0, self.rss_peak_mb - self.rss_start_mb),
            "cpu_peak_pct": cpu,
            "mlx_peak_mb": self._mlx_peak_mb(),
        }


def codeswitch_through_vad(transcribe, fixture_root):
    """Score R8 the way production actually runs: VAD segments, one call each.

    The whole-clip pass elsewhere in this harness feeds a concatenated EN+ZH file to the model in
    one go, which the product never does -- `_processing_thread` flushes a segment after 0.4 s of
    silence and each segment is its own call with no language argument. A model that picks one
    language for a long mixed clip may still handle both when they arrive separately, so a whole-
    clip result must not be read as an **R8** verdict.
    """
    import re as _re

    path = os.path.join(fixture_root, "speech/code_switch/en_zh_interleaved.wav")
    if not os.path.exists(path):
        return None
    samples, _sr = load_wav_mono_float32(path)
    texts = []
    for chunk in vad_speech_segments(samples):
        try:
            texts.append(transcribe(chunk))
        except Exception:
            texts.append("")
    joined = " ".join(t for t in texts if t)
    has_cjk = bool(_re.search(r"[\u4e00-\u9fff]", joined))
    has_latin = bool(_re.search(r"[A-Za-z]{3,}", joined))
    return {
        "segments": len(texts),
        "has_cjk": has_cjk,
        "has_latin": has_latin,
        "both": has_cjk and has_latin,
        "texts": [t for t in texts if t],
    }


def evaluate_candidate(label, model_id, kind, qwen_backend, fixture_root, use_vad, repeat=1):
    row = {
        "candidate": label,
        "model": model_id,
        "status": "ok",
        "note": "",
        "nonspeech_segments": 0,
        "nonspeech_accepted": 0,
        "nonspeech_raw": 0,
        "speech_calls": 0,
        "speech_accepted": 0,
        "latencies_ms": [],
        "zh_traditional": None,
        "speech_texts": [],
    }
    try:
        transcribe = make_transcribe_fn(kind, model_id, qwen_backend)
    except Exception as exc:
        row["status"] = "error"
        row["note"] = f"init failed: {exc}"
        return row

    # --- R37 nonspeech ---
    # Repeated because the filtered count is a random variable (V54): the decoder falls back to
    # sampling on non-speech, so which ghost string appears -- and therefore whether the blacklist
    # catches it -- differs run to run. The raw count does not move.
    row["filtered_runs"] = []
    sampler = ResourceSampler()
    sampler.__enter__()
    nonspeech_texts = []
    for _pass in range(max(1, repeat)):
      nonspeech_texts = []
      row["nonspeech_segments"] = 0
      for path in iter_fixture_wavs(fixture_root, "nonspeech"):
          samples, _sr = load_wav_mono_float32(path)
          if use_vad:
              chunks = vad_speech_segments(samples)
          else:
              chunks = [samples] if len(samples) >= int(TARGET_SR * 0.3) else []
          row["nonspeech_segments"] += len(chunks)
          for chunk in chunks:
              t0 = time.perf_counter()
              try:
                  text = transcribe(chunk)
              except Exception as exc:
                  row["note"] = (row["note"] + f" nonspeech err: {exc}").strip()
                  text = ""
              row["latencies_ms"].append((time.perf_counter() - t0) * 1000.0)
              nonspeech_texts.append(text)
      scored = score_nonspeech_texts(nonspeech_texts)
      row["filtered_runs"].append(scored["accepted"])
      row["nonspeech_accepted"] = scored["accepted"]
      row["nonspeech_raw"] = scored["raw"]
    if scored["accepted_texts"]:
        preview = "; ".join(scored["accepted_texts"][:3])
        row["note"] = (row["note"] + f" R37 samples: {preview}").strip()

    # --- R8 / R10 speech ---
    for path in iter_fixture_wavs(fixture_root, "speech"):
        samples, _sr = load_wav_mono_float32(path)
        # Whole-clip for language / script observation (VAD would chop code-switch).
        if len(samples) < int(TARGET_SR * 0.3):
            continue
        t0 = time.perf_counter()
        try:
            text = transcribe(samples)
        except Exception as exc:
            row["note"] = (row["note"] + f" speech err: {exc}").strip()
            text = ""
        ms = (time.perf_counter() - t0) * 1000.0
        row["latencies_ms"].append(ms)
        row["speech_calls"] += 1
        try:
            from text_filters import is_acceptable
        except ImportError:
            from src.text_filters import is_acceptable
        if text and is_acceptable(text):
            row["speech_accepted"] += 1
            row["speech_texts"].append((os.path.relpath(path, fixture_root), text))
            trad = looks_traditional_chinese(text)
            if trad is not None:
                row["zh_traditional"] = trad if row["zh_traditional"] is None else (
                    row["zh_traditional"] or trad
                )

    # R8 through the production path: VAD segments, one call each (not the whole-clip pass above).
    try:
        row["codeswitch_vad"] = codeswitch_through_vad(transcribe, fixture_root)
    except Exception as exc:
        row["note"] = (row["note"] + f" cs-vad err: {exc}").strip()
        row["codeswitch_vad"] = None

    sampler.__exit__(None, None, None)
    row["resources"] = sampler.summary()
    return row


def _cs_str(cs):
    """R8 verdict from the VAD path. `both` is the only passing value — R8 says one meeting may
    contain both languages and **both must be transcribed**."""
    if not cs:
        return "—"
    if cs["both"]:
        return f"**yes** ({cs['segments']} segs)"
    got = "zh only" if cs["has_cjk"] else ("en only" if cs["has_latin"] else "neither")
    return f"NO — {got} ({cs['segments']} segs)"


def _range_str(values):
    """`n` for one observation, `min-max (n runs)` for several -- never a bare mean (V54)."""
    if not values:
        return "—"
    if len(values) == 1:
        return str(values[0])
    return f"{min(values)}-{max(values)} ({len(values)} runs)"


def format_table(rows):
    lines = [
        "| Candidate | Status | R37 raw (model) | R37 after filter | VAD segs | "
        "R8 both langs (VAD path) | Latency median (ms) | Peak MLX (MB) | Peak RSS (MB) | Peak CPU% | "
        "ZH Traditional? | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lats = sorted(row["latencies_ms"])
        if lats:
            mid = lats[len(lats) // 2]
            lat_s = f"{mid:.0f}"
        else:
            lat_s = "—"
        zh = row["zh_traditional"]
        zh_s = "—" if zh is None else ("yes" if zh else "simplified-leaning")
        note = (row.get("note") or "").replace("|", "/")
        if len(note) > 80:
            note = note[:77] + "..."
        lines.append(
            f"| {row['candidate']} | {row['status']} | "
            f"{row.get('nonspeech_raw', 0)} | "
            f"{_range_str(row.get('filtered_runs') or [row['nonspeech_accepted']])} | "
            f"{row['nonspeech_segments']} | "
            f"{_cs_str(row.get('codeswitch_vad'))} | "
            f"{lat_s} | "
            f"{(row.get('resources') or {}).get('mlx_peak_mb', 0):.0f} | "
            f"{(row.get('resources') or {}).get('rss_peak_mb', 0):.0f} | "
            f"{(row.get('resources') or {}).get('cpu_peak_pct', 0):.0f} | "
            f"{zh_s} | {note} |"
        )
    return "\n".join(lines)


def write_results(md_body, fixture_root):
    out_dir = os.path.join(fixture_root, "results")
    assert_fixture_path_allowed(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"{stamp}.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(md_body)
        handle.write("\n")
    return path



def toolchain_fingerprint():
    """Interpreter and package versions for this run (V53).

    A candidate can be made to look better or worse than a rival purely by the interpreter it ran
    under -- turbo moved 13/63 -> 1/63 and distil 32/63 -> 45/63 on the same fixtures across two
    toolchains. A result without this block cannot be compared with any other result.
    """
    import importlib.metadata as md
    import platform

    lines = [
        f"Python {platform.python_version()} ({sys.executable})",
        f"platform {platform.platform()}",
    ]
    for pkg in ("mlx", "mlx-metal", "mlx-whisper", "mlx-qwen3-asr", "huggingface_hub",
                "numpy", "webrtcvad", "webrtcvad-wheels"):
        try:
            lines.append(f"{pkg} {md.version(pkg)}")
        except Exception:
            continue
    return lines


def fixture_fingerprint(fixture_root):
    """(relative path, sha256, bytes) for every fixture WAV, sorted.

    The generator is seeded, but the speech clips come from macOS `say`, whose voices differ by
    OS build. Recording the digests is what lets a later run say whether it scored the same audio
    rather than assuming it did.
    """
    import hashlib

    out = []
    for path in iter_fixture_wavs(fixture_root, ""):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        out.append((os.path.relpath(path, fixture_root), digest.hexdigest(),
                    os.path.getsize(path)))
    return sorted(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-vad", action="store_true",
        help="Transcribe whole nonspeech files (debug); default mirrors product VAD path",
    )
    parser.add_argument(
        "--include-disqualified", action="store_true",
        help="Also score the candidates R50 rules out on provenance (docs/decisions/0012). Off "
             "by default: they win on measurement, so a run that quietly includes them produces "
             "a table whose top row cannot be adopted",
    )
    parser.add_argument(
        "--only", default="",
        help="Comma substring filter on candidate labels (e.g. distil,turbo)",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Run the nonspeech pass N times per candidate and report the filtered count as a "
             "range. Single runs are uninterpretable: the same command varied 30-60 of 63 (V54)",
    )
    parser.add_argument(
        "--hf-home", default="",
        help="Weight cache for this run (e.g. .hf_cache-bakeoff), keeping experiment downloads "
             "out of the product storage root",
    )
    parser.add_argument(
        "--allow-download", action="store_true",
        help="Permit network access. Off by default: a per-call Hub round trip inflated one "
             "model's latency from ~600 ms to 2542 ms (V53)",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Print only; do not write fixtures/asr/results/*.md",
    )
    args = parser.parse_args()

    _boot_hf_home(args.hf_home, offline=not args.allow_download)

    qwen_backend = resolve_qwen_backend()
    print(f"Qwen import: {qwen_backend[0]}")

    candidates = list(WHISPER_CANDIDATES)
    if args.include_disqualified:
        print(f"Including disqualified candidates: {DISQUALIFIED_REASON}")
        candidates.extend(QWEN_CANDIDATES)

    only = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    if only:
        candidates = [
            c for c in candidates if any(tok in c[0].lower() or tok in c[1].lower() for tok in only)
        ]

    nonspeech = iter_fixture_wavs(FIXTURE_ROOT, "nonspeech")
    speech = iter_fixture_wavs(FIXTURE_ROOT, "speech")
    if not nonspeech and not speech:
        print(
            f"No WAV fixtures under {FIXTURE_ROOT}. Run tools/gen_asr_fixtures.py first.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"Fixtures: {len(nonspeech)} nonspeech, {len(speech)} speech")

    rows = []
    for label, model_id, kind in candidates:
        if kind == "qwen" and qwen_backend[1] is None:
            rows.append({
                "candidate": label,
                "model": model_id,
                "status": "skipped",
                "note": "package not installed (V44 — do not auto-adopt)",
                "nonspeech_segments": 0,
                "nonspeech_accepted": 0,
                "nonspeech_raw": 0,
                "speech_calls": 0,
                "speech_accepted": 0,
                "latencies_ms": [],
                "zh_traditional": None,
                "speech_texts": [],
            })
            print(f"== {label}: skipped (no Qwen MLX package) ==")
            continue
        print(f"== {label} ({model_id}) ==")
        row = evaluate_candidate(
            label, model_id, kind, qwen_backend, FIXTURE_ROOT, use_vad=not args.no_vad,
            repeat=args.repeat,
        )
        rows.append(row)
        print(
            f"   R37 raw {row.get('nonspeech_raw', 0)} / filtered {_range_str(row.get('filtered_runs') or [])}"
            f" of {row['nonspeech_segments']} segs "
            f"speech {row['speech_accepted']}/{row['speech_calls']} "
            f"status={row['status']}"
        )
        for rel, text in row.get("speech_texts") or []:
            print(f"   [{rel}] {text[:120]}")

    table = format_table(rows)
    header = [
        "# ASR bake-off results",
        "",
        f"- When (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- Fixture root: `{FIXTURE_ROOT}`",
        f"- Nonspeech path: {'whole-file' if args.no_vad else 'VAD + 0.3s min + is_acceptable (product)'}",
        f"- Qwen backend: `{qwen_backend[0]}`",
        f"- Network: {'ALLOWED (latency includes Hub round trips)' if args.allow_download else 'offline (HF_HUB_OFFLINE=1)'}",
        "- R37 is reported twice: **raw** is what the model produced from a VAD segment;"
        " **after filter** additionally applies the whole-utterance blacklist. Compare models on"
        " raw (**R11**); the filtered column describes the pipeline, and the blacklist was fitted"
        " to Whisper ghosts on these same fixtures.",
        "- Latency baselines are toolchain-specific (**V51**, **V53**): ~1380 ms/call on"
        " Python 3.9 + mlx 0.29, ~600 ms/call on Python 3.12 + mlx 0.32. Do not compare a median"
        " here against a number measured under a different block below.",
        "",
        "## Toolchain (V53)",
        "",
        "```",
        *toolchain_fingerprint(),
        "```",
        "",
        "## Fixture digests",
        "",
        "```",
        *[f"{sha[:16]}  {size:>9}  {rel}" for rel, sha, size in fixture_fingerprint(FIXTURE_ROOT)],
        "```",
        "",
        "- Closing the bake-off still needs 48 kHz remeasure and open decision on **V44**.",
        "- Default `ASR_MODEL` was **not** changed by this run.",
        "",
        table,
        "",
        "- Resources: **Peak MLX** is the figure to use — `mlx.core.get_peak_memory()`, reset per"
        " candidate. Peak RSS is retained only as a cross-check and is known to misreport"
        " memory-mapped weights (**V55**). Both are per-candidate only when the run scored one"
        " candidate; models are not unloaded between candidates.",
        "",
        "## R8 through the VAD path (what production does)",
        "",
        *[line for row in rows for line in (
            [f"### {row['candidate']}"] + (
                [f"- {ln}" for ln in ((row.get('codeswitch_vad') or {}).get('texts') or ["_none_"])]
            ))],
        "",
        "## Speech transcripts (whole-clip — NOT the production path)",
    ]
    for row in rows:
        header.append(f"### {row['candidate']}")
        if not row.get("speech_texts"):
            header.append("_none_")
            continue
        for rel, text in row["speech_texts"]:
            header.append(f"- `{rel}`: {text}")
    body = "\n".join(header)
    print()
    print(table)
    if not args.no_write:
        path = write_results(body, FIXTURE_ROOT)
        print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
