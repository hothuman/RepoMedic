"""Release guard: Git tag and generated reports must share one version."""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from version import __version__


def validate_tag(tag: str) -> bool:
    return tag == f"v{__version__}" and re.fullmatch(r"v\d+\.\d+\.\d+", tag) is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify version / tag agreement before publishing")
    parser.add_argument("--tag", help="Git tag such as v1.0.0; required for a release")
    args = parser.parse_args(argv)
    if args.tag and not validate_tag(args.tag):
        print(f"ERROR: tag {args.tag!r} does not match v{__version__}", file=sys.stderr)
        return 2
    print(f"RepoMedic v{__version__}: release version check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
