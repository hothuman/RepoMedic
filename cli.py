"""Headless CLI: python cli.py path [--format json|txt|html] [--output FILE]."""
from __future__ import annotations

from version import __version__

import argparse
import sys
from pathlib import Path

from diagnostics import analyze_project
from html_report import render_html_report
from report_io import atomic_save_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"RepoMedic v{__version__} — read-only local project diagnostics")
    parser.add_argument("path", type=Path, help="Local directory to scan")
    parser.add_argument("--format", choices=("txt", "json", "html"), default="txt")
    parser.add_argument("--output", type=Path, metavar="FILE", help="Write report to a file")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit 1 if errors or warnings exist")
    args = parser.parse_args(argv)

    if not args.path.is_dir():
        print(f"ERROR: not a directory: {args.path}", file=sys.stderr)
        return 2
    try:
        report = analyze_project(args.path)
        content = {"txt": report.to_text, "json": report.to_json,
                   "html": lambda: render_html_report(report)}[args.format]()
        if args.output:
            atomic_save_text(args.output, content)
            print(f"Report saved: {args.output}", file=sys.stderr)
        elif args.format == "html":
            print(content)
        else:
            print(content)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    counts = report.counts()
    return 1 if counts["ERROR"] or (args.fail_on_warning and counts["WARN"]) else 0


if __name__ == "__main__":
    sys.exit(main())
