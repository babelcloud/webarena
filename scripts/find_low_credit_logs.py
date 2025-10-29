#!/usr/bin/env python3
"""
Scan WebArena log files for credit-balance errors.

Usage:
    python scripts/find_low_credit_logs.py
    python scripts/find_low_credit_logs.py --root /custom/path --pattern "Credit balance is too low"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find log entries mentioning credit balance issues."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("log_files"),
        help="Directory to search (default: ./log_files)",
    )
    parser.add_argument(
        "--pattern",
        default="Credit balance is too low",
        help="Substring to search for (default: 'Credit balance is too low')",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete matching log files (and related render files).",
    )
    parser.add_argument(
        "--renders-dir",
        type=Path,
        default=Path("results_full"),
        help="Directory containing render_*.html files (default: results_full).",
    )
    return parser.parse_args()


def scan_logs(root: Path, needle: str) -> list[Path]:
    hits: list[Path] = []
    if not root.exists():
        return hits

    for path in sorted(root.rglob("*.log")):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                if any(needle in line for line in handle):
                    hits.append(path)
        except OSError as exc:
            print(f"⚠️  Skipping {path}: {exc}", file=sys.stderr)
    return hits


def main() -> int:
    args = parse_args()
    matches = scan_logs(args.root, args.pattern)

    if not matches:
        print("No log files contain the pattern.")
        return 0

    print(f"Found {len(matches)} log file(s) containing the pattern:\n")
    for path in matches:
        task_id = None
        name_parts = path.stem.split("_")
        if len(name_parts) >= 2 and name_parts[0] == "task":
            candidate = name_parts[1]
            if candidate.isdigit():
                task_id = candidate

        if task_id:
            print(f"task {task_id} -> {path}")
            if args.delete:
                try:
                    path.unlink()
                    print("  ␡ removed log file")
                except OSError as exc:
                    print(f"  ⚠️ failed to remove log file: {exc}", file=sys.stderr)

                render_path = args.renders_dir / f"render_{task_id}.html"
                if render_path.exists():
                    try:
                        render_path.unlink()
                        print(f"  ␡ removed render file {render_path}")
                    except OSError as exc:
                        print(f"  ⚠️ failed to remove render file {render_path}: {exc}", file=sys.stderr)
        else:
            print(path)
            if args.delete:
                try:
                    path.unlink()
                    print("  ␡ removed log file (no task id)")
                except OSError as exc:
                    print(f"  ⚠️ failed to remove log file: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
