"""Tiny local-only benchmark for developers (does not run analyzed code)."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
import sys

# Support direct execution: python scripts/benchmark_scan.py .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from diagnostics import analyze_project


def main():
    parser = argparse.ArgumentParser(description="Measure RepoMedic static scanning time")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if not args.directory.is_dir() or not 1 <= args.runs <= 25:
        parser.error("Choose an existing directory and 1 to 25 runs")
    timings = []
    for _ in range(args.runs):
        start = time.perf_counter()
        analyze_project(args.directory)
        timings.append(round((time.perf_counter() - start) * 1000, 2))
    print(json.dumps({"runs": len(timings), "median_ms": statistics.median(timings),
                      "max_ms": max(timings), "times_ms": timings}, indent=2))


if __name__ == "__main__":
    main()
