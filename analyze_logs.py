#!/usr/bin/env python3
"""
Analyze WebArena log files to count passes, fails, and incomplete runs.

Usage:
    python analyze_logs.py [log_directory]

Default log directory: log_files/
"""

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict


def get_task_type(task_id: int, config_dir: Path = Path('config_files')) -> str:
    """
    Get the task type (shopping, map, gitlab, etc.) from config file.

    Returns:
        Task type string (e.g., 'shopping', 'map', 'gitlab')
    """
    config_file = config_dir / f"{task_id}.json"

    if not config_file.exists():
        return 'unknown'

    try:
        with open(config_file) as f:
            data = json.load(f)
            sites = data.get('sites', [])

            if not sites:
                return 'unknown'

            # Return the first site (most tasks have one site)
            # Map common site names to readable labels
            site_map = {
                'shopping': 'shopping',
                'shopping_admin': 'shopping_admin',
                'map': 'map',
                'gitlab': 'gitlab',
                'reddit': 'reddit',
                'wikipedia': 'wikipedia',
            }

            primary_site = sites[0]
            return site_map.get(primary_site, primary_site)
    except Exception:
        return 'unknown'


def analyze_log_file(log_path: Path) -> str:
    """
    Analyze a single log file and return its status.

    Returns:
        'PASS' if task passed
        'FAIL' if task failed
        'INCOMPLETE' if no result found
    """
    try:
        content = log_path.read_text()

        if '[Result] (PASS)' in content:
            return 'PASS'
        elif '[Result] (FAIL)' in content:
            return 'FAIL'
        else:
            return 'INCOMPLETE'
    except Exception as e:
        print(f"⚠️  Error reading {log_path.name}: {e}")
        return 'ERROR'


def extract_task_id(filename: str) -> int:
    """Extract task ID from log filename."""
    match = re.match(r'task_(\d+)_', filename)
    if match:
        return int(match.group(1))
    return -1


def main():
    parser = argparse.ArgumentParser(description='Analyze WebArena log files')
    parser.add_argument(
        'log_dir',
        nargs='?',
        default='log_files',
        help='Directory containing log files (default: log_files)'
    )
    parser.add_argument(
        '--details',
        action='store_true',
        help='Show details for each task'
    )
    args = parser.parse_args()

    log_dir = Path(args.log_dir)

    if not log_dir.exists():
        print(f"❌ Directory not found: {log_dir}")
        return

    # Find all log files
    log_files = sorted(log_dir.glob('task_*.log'))

    if not log_files:
        print(f"❌ No log files found in {log_dir}")
        return

    print(f"🔍 Analyzing {len(log_files)} log files in {log_dir}/\n")

    # Analyze each file
    results = defaultdict(list)
    task_type_counts = defaultdict(lambda: defaultdict(int))

    for log_file in log_files:
        status = analyze_log_file(log_file)
        task_id = extract_task_id(log_file.name)
        task_type = get_task_type(task_id)
        results[status].append((task_id, task_type, log_file.name))

        # Track counts by task type
        task_type_counts[task_type][status] += 1

    # Print summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total = len(log_files)
    pass_count = len(results['PASS'])
    fail_count = len(results['FAIL'])
    incomplete_count = len(results['INCOMPLETE'])
    error_count = len(results['ERROR'])

    print(f"✅ PASS:       {pass_count:4d} ({pass_count/total*100:5.1f}%)")
    print(f"❌ FAIL:       {fail_count:4d} ({fail_count/total*100:5.1f}%)")
    print(f"⏳ INCOMPLETE: {incomplete_count:4d} ({incomplete_count/total*100:5.1f}%)")

    if error_count > 0:
        print(f"⚠️  ERROR:      {error_count:4d} ({error_count/total*100:5.1f}%)")

    print(f"{'─' * 30}")
    print(f"📊 TOTAL:      {total:4d}")
    print("=" * 70)

    # Calculate success rate (only from completed tasks)
    completed = pass_count + fail_count
    if completed > 0:
        success_rate = pass_count / completed * 100
        print(f"\n🎯 Success Rate (completed tasks only): {success_rate:.1f}% ({pass_count}/{completed})")

    # Show breakdown by task type
    if task_type_counts:
        print(f"\n{'=' * 70}")
        print("BREAKDOWN BY TASK TYPE")
        print("=" * 70)

        for task_type in sorted(task_type_counts.keys()):
            counts = task_type_counts[task_type]
            total_type = sum(counts.values())
            passed = counts.get('PASS', 0)
            failed = counts.get('FAIL', 0)
            incomplete = counts.get('INCOMPLETE', 0)
            completed_type = passed + failed

            success = (passed / completed_type * 100) if completed_type > 0 else 0

            print(f"\n{task_type.upper():15s}  Total: {total_type:3d}  "
                  f"Pass: {passed:2d}  Fail: {failed:2d}  Incomplete: {incomplete:2d}  "
                  f"Success: {success:5.1f}%")

    # Show details if requested
    if args.details:
        if results['PASS']:
            print(f"\n{'=' * 70}")
            print(f"✅ PASSED TASKS ({len(results['PASS'])})")
            print("=" * 70)
            for task_id, task_type, filename in sorted(results['PASS']):
                print(f"   Task {task_id:3d} [{task_type:15s}] - {filename}")

        if results['FAIL']:
            print(f"\n{'=' * 70}")
            print(f"❌ FAILED TASKS ({len(results['FAIL'])})")
            print("=" * 70)
            for task_id, task_type, filename in sorted(results['FAIL']):
                print(f"   Task {task_id:3d} [{task_type:15s}] - {filename}")

        if results['INCOMPLETE']:
            print(f"\n{'=' * 70}")
            print(f"⏳ INCOMPLETE TASKS ({len(results['INCOMPLETE'])})")
            print("=" * 70)
            for task_id, task_type, filename in sorted(results['INCOMPLETE']):
                print(f"   Task {task_id:3d} [{task_type:15s}] - {filename}")

        if results['ERROR']:
            print(f"\n{'=' * 70}")
            print(f"⚠️  ERROR READING ({len(results['ERROR'])})")
            print("=" * 70)
            for task_id, task_type, filename in sorted(results['ERROR']):
                print(f"   Task {task_id:3d} [{task_type:15s}] - {filename}")


if __name__ == '__main__':
    main()
