#!/usr/bin/env python3
"""Parse ASR inference latencies from a captured log and summarise for V52 / 7.3.

Expects lines containing: Transcribed in <ms>ms
(from transcriber.py). Does not read history/, context/, or logs/ unless you
explicitly pass such a path — prefer tee/copy into fixtures/asr/results/.

Examples:
  .venv/bin/python tools/measure_asr_latency.py fixtures/asr/results/v52_0sess.log
  .venv/bin/python tools/measure_asr_latency.py \\
      --label 0sess fixtures/asr/results/v52_0sess.log \\
      --label 3sess fixtures/asr/results/v52_3sess.log \\
      --threshold-ms 2000
"""

from __future__ import annotations

import argparse
import math
import os
import re
import statistics
import sys
import time

TRANSCRIBED_RE = re.compile(
    r"Transcribed in\s+(?P<ms>\d+(?:\.\d+)?)\s*ms",
    re.IGNORECASE,
)


def extract_latencies_ms(text: str) -> list[float]:
    return [float(m.group("ms")) for m in TRANSCRIBED_RE.finditer(text)]


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    # Nearest-rank style on [0, 100]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_vals[lo]
    frac = k - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def summarise(samples: list[float], threshold_ms: float) -> dict:
    if not samples:
        return {
            "n": 0,
            "median": None,
            "p95": None,
            "max": None,
            "mean": None,
            "over_threshold": 0,
            "over_pct": None,
        }
    ordered = sorted(samples)
    over = sum(1 for s in samples if s > threshold_ms)
    return {
        "n": len(samples),
        "median": statistics.median(ordered),
        "p95": percentile(ordered, 95),
        "max": ordered[-1],
        "mean": statistics.fmean(samples),
        "over_threshold": over,
        "over_pct": 100.0 * over / len(samples),
    }


def format_row(label: str, stats: dict, threshold_ms: float) -> str:
    if stats["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | 0 (—) |"
    return (
        f"| {label} | {stats['n']} | {stats['median']:.0f} | {stats['p95']:.0f} | "
        f"{stats['max']:.0f} | {stats['mean']:.0f} | "
        f"{stats['over_threshold']} ({stats['over_pct']:.0f}%) |"
    )


def load_path(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def watch_resources(pid: int, out_path: str, interval_s: float, duration_s: float) -> None:
    """Sample RSS/CPU via ps until duration elapses. Portable enough for macOS/Linux."""
    deadline = time.time() + duration_s
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("unix_s,rss_kb,pcpu\n")
        while time.time() < deadline:
            # ps -o rss= -o pcpu= -p PID
            import subprocess

            try:
                raw = subprocess.check_output(
                    ["ps", "-o", "rss=", "-o", "pcpu=", "-p", str(pid)],
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                handle.write(f"{time.time():.3f},,\n")
                handle.flush()
                break
            parts = raw.split()
            rss = parts[0] if parts else ""
            pcpu = parts[1] if len(parts) > 1 else ""
            handle.write(f"{time.time():.3f},{rss},{pcpu}\n")
            handle.flush()
            time.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logs",
        nargs="*",
        help="Log file(s) to parse (prefer fixtures/asr/results/*.log)",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="NAME=PATH or NAME path-paired",
        help="Named arm: either NAME=PATH, or pass --label NAME before each path",
    )
    parser.add_argument(
        "--threshold-ms",
        type=float,
        default=2000.0,
        help="Tail threshold matching V52 (default 2000)",
    )
    parser.add_argument(
        "--watch-pid",
        type=int,
        default=0,
        help="If set with --watch-out, sample RSS/CPU for this PID then exit",
    )
    parser.add_argument("--watch-out", default="", help="CSV path for --watch-pid samples")
    parser.add_argument(
        "--watch-seconds", type=float, default=120.0, help="Duration for --watch-pid",
    )
    parser.add_argument(
        "--watch-interval", type=float, default=1.0, help="Sample interval for --watch-pid",
    )
    parser.add_argument(
        "--write-md",
        default="",
        help="Optional markdown summary path (e.g. fixtures/asr/results/v52_summary.md)",
    )
    args = parser.parse_args()

    if args.watch_pid:
        if not args.watch_out:
            print("--watch-pid requires --watch-out", file=sys.stderr)
            return 2
        print(
            f"Sampling pid={args.watch_pid} every {args.watch_interval}s "
            f"for {args.watch_seconds}s → {args.watch_out}"
        )
        watch_resources(args.watch_pid, args.watch_out, args.watch_interval, args.watch_seconds)
        return 0

    arms: list[tuple[str, str]] = []
    # Parse --label NAME=PATH
    for item in args.label:
        if "=" in item:
            name, path = item.split("=", 1)
            arms.append((name, path))
        else:
            # NAME alone: consume next positional later — handled below
            arms.append((item, ""))

    # Pair bare labels with positionals
    bare_labels = [i for i, (n, p) in enumerate(arms) if not p]
    pos = list(args.logs)
    if bare_labels and len(pos) < len(bare_labels):
        print("Not enough log paths for --label names", file=sys.stderr)
        return 2
    for idx in bare_labels:
        arms[idx] = (arms[idx][0], pos.pop(0))
    for path in pos:
        arms.append((os.path.basename(path), path))

    if not arms:
        parser.print_help()
        return 2

    rows = []
    details = []
    header = (
        f"| Arm | n | median (ms) | p95 (ms) | max (ms) | mean (ms) | "
        f"> {args.threshold_ms:.0f} ms |"
    )
    sep = "|---|---|---|---|---|---|---|"
    table = [header, sep]

    for label, path in arms:
        if not os.path.isfile(path):
            print(f"missing: {path}", file=sys.stderr)
            return 2
        samples = extract_latencies_ms(load_path(path))
        stats = summarise(samples, args.threshold_ms)
        table.append(format_row(label, stats, args.threshold_ms))
        rows.append((label, path, stats, samples))
        details.append(f"### {label} (`{path}`)")
        details.append(f"- samples: {stats['n']}")
        if samples:
            details.append(
                f"- all ms: {', '.join(f'{s:.0f}' for s in samples)}"
            )

    body = "\n".join(table) + "\n\n" + "\n".join(details) + "\n"
    print(body)

    # Closing hint for 7.3
    if len(rows) >= 2 and all(r[2]["n"] for r in rows):
        control = rows[0][2]
        multi = rows[-1][2]
        print("## 7.3 glance")
        print(
            f"- control max {control['max']:.0f} ms vs multi max {multi['max']:.0f} ms"
        )
        print(
            f"- control >{args.threshold_ms:.0f}ms "
            f"{control['over_pct']:.0f}% vs multi {multi['over_pct']:.0f}%"
        )
        if multi["n"] < 30 or control["n"] < 30:
            print(
                f"- WARNING: want n≥30 per arm for closing 7.3 "
                f"(have control={control['n']}, multi={multi['n']})"
            )
        # Heuristic pass: multi over% within 5pp of control and max < 2× control max
        if (
            multi["over_pct"] is not None
            and control["over_pct"] is not None
            and (multi["over_pct"] - control["over_pct"]) <= 5.0
            and multi["max"] <= max(control["max"] * 2.0, control["max"] + 500.0)
        ):
            print("- heuristic: multi-session tail looks controlled (still record in STATE)")
        else:
            print("- heuristic: multi-session tail still elevated — tune poll or dig further")

    if args.write_md:
        os.makedirs(os.path.dirname(os.path.abspath(args.write_md)) or ".", exist_ok=True)
        with open(args.write_md, "w", encoding="utf-8") as handle:
            handle.write("# ASR latency summary (V52 / 7.3)\n\n")
            handle.write(body)
        print(f"Wrote {args.write_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
