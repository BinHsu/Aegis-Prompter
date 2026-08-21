"""Unit tests for tools/measure_asr_latency.py helpers (tmp_path only)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import measure_asr_latency as mal  # noqa: E402


def test_extract_and_summarise(tmp_path):
    text = """
2026-08-10 12:00:00 [INFO] Transcriber: [Speaker] Transcribed in 1376ms: hello
2026-08-10 12:00:02 [INFO] Transcriber: [Speaker] Transcribed in 1409ms: world
2026-08-10 12:00:04 [INFO] Transcriber: [Speaker] Transcribed in 4983ms: slow
"""
    path = tmp_path / "arm.log"
    path.write_text(text, encoding="utf-8")
    samples = mal.extract_latencies_ms(path.read_text(encoding="utf-8"))
    assert samples == [1376.0, 1409.0, 4983.0]
    stats = mal.summarise(samples, threshold_ms=2000)
    assert stats["n"] == 3
    assert stats["median"] == 1409.0
    assert stats["max"] == 4983.0
    assert stats["over_threshold"] == 1
    assert stats["over_pct"] == pytest.approx(100 / 3)


def test_cli_writes_md(tmp_path):
    import subprocess

    log = tmp_path / "a.log"
    log.write_text("Transcribed in 100ms: x\nTranscribed in 200ms: y\n", encoding="utf-8")
    out = tmp_path / "sum.md"
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(REPO, "tools", "measure_asr_latency.py"),
            f"--label=t={log}",
            f"--write-md={out}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    body = out.read_text(encoding="utf-8")
    assert "median" in body
    assert "| t |" in body
