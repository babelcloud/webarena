#!/usr/bin/env python3
"""
Real-time log monitor for WebArena tasks.

Shows live statistics as tasks complete in the background.

Usage:
    python monitor_logs.py [log_directory]

Press Ctrl+C to exit.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def get_task_type(task_id: int, config_dir: Path = Path('config_files')) -> str:
    """Get the task type from config file."""
    config_file = config_dir / f"{task_id}.json"

    if not config_file.exists():
        return 'unknown'

    try:
        with open(config_file) as f:
            data = json.load(f)
            sites = data.get('sites', [])

            if not sites:
                return 'unknown'

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


def analyze_log_file(log_path: Path) -> tuple[str, datetime]:
    """
    Analyze a single log file and return its status and last modified time.

    Returns:
        Tuple of (status, last_modified_time)
    """
    try:
        content = log_path.read_text()
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime)

        if '[Result] (PASS)' in content:
            return 'PASS', mtime
        elif '[Result] (FAIL)' in content:
            return 'FAIL', mtime
        else:
            return 'INCOMPLETE', mtime
    except Exception:
        return 'ERROR', datetime.now()


def extract_task_id(filename: str) -> int:
    """Extract task ID from log filename."""
    match = re.match(r'task_(\d+)_', filename)
    if match:
        return int(match.group(1))
    return -1


def clear_screen():
    """Clear the terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


def format_time_ago(dt: datetime) -> str:
    """Format time difference as human-readable string."""
    now = datetime.now()
    diff = (now - dt).total_seconds()

    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff / 60)}m ago"
    else:
        return f"{int(diff / 3600)}h ago"


def monitor_logs(log_dir: Path, refresh_interval: float = 2.0):
    """
    Monitor logs in real-time with live updates.

    Args:
        log_dir: Directory containing log files
        refresh_interval: Seconds between refreshes
    """
    print(f"🔍 Starting real-time monitor for {log_dir}/")
    print(f"⏱️  Refreshing every {refresh_interval}s")
    print(f"Press Ctrl+C to exit\n")
    time.sleep(2)

    last_completed_count = 0
    last_file_count = 0

    try:
        while True:
            clear_screen()

            # Find all log files
            log_files = sorted(log_dir.glob('task_*.log'))

            if not log_files:
                print(f"⏳ Waiting for log files in {log_dir}/...")
                time.sleep(refresh_interval)
                continue

            # Analyze each file
            results = defaultdict(list)
            task_type_counts = defaultdict(lambda: defaultdict(int))
            recent_completions = []

            for log_file in log_files:
                status, mtime = analyze_log_file(log_file)
                task_id = extract_task_id(log_file.name)
                task_type = get_task_type(task_id)
                results[status].append((task_id, task_type, log_file.name, mtime))

                # Track counts by task type
                task_type_counts[task_type][status] += 1

                # Track recent completions
                if status in ['PASS', 'FAIL']:
                    recent_completions.append((task_id, task_type, status, mtime))

            # Sort recent completions by time
            recent_completions.sort(key=lambda x: x[3], reverse=True)

            # Calculate stats
            total = len(log_files)
            pass_count = len(results['PASS'])
            fail_count = len(results['FAIL'])
            incomplete_count = len(results['INCOMPLETE'])
            completed = pass_count + fail_count

            # Print header
            print("=" * 80)
            print(f"{'WebArena Real-Time Monitor':^80}")
            print(f"{'Updated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^80}")
            print("=" * 80)

            # Overall stats
            print(f"\n{'OVERALL PROGRESS':^80}")
            print("─" * 80)

            # Progress bar
            if total > 0:
                pass_pct = pass_count / total
                fail_pct = fail_count / total
                incomplete_pct = incomplete_count / total

                bar_width = 60
                pass_bar = int(pass_pct * bar_width)
                fail_bar = int(fail_pct * bar_width)
                incomplete_bar = int(incomplete_pct * bar_width)

                print(f"  [{'█' * pass_bar}{'▓' * fail_bar}{'░' * incomplete_bar}{' ' * (bar_width - pass_bar - fail_bar - incomplete_bar)}]")
                print(f"  {'✅ Pass':15} {'❌ Fail':15} {'⏳ Running':15} {'📊 Total':15}")
                print(f"  {pass_count:3d} ({pass_pct*100:5.1f}%)    {fail_count:3d} ({fail_pct*100:5.1f}%)    {incomplete_count:3d} ({incomplete_pct*100:5.1f}%)    {total:3d}")

            if completed > 0:
                success_rate = pass_count / completed * 100
                print(f"\n  🎯 Success Rate (completed): {success_rate:.1f}% ({pass_count}/{completed})")

            # Show new completions indicator
            if completed != last_completed_count:
                new_completions = completed - last_completed_count
                if new_completions > 0:
                    print(f"  🆕 {new_completions} new completion(s) since last refresh")
                last_completed_count = completed

            if len(log_files) != last_file_count:
                new_files = len(log_files) - last_file_count
                if new_files > 0:
                    print(f"  📝 {new_files} new task(s) started")
                last_file_count = len(log_files)

            # Breakdown by task type
            print(f"\n{'BREAKDOWN BY TASK TYPE':^80}")
            print("─" * 80)
            print(f"  {'Type':<15} {'Total':>6} {'Pass':>6} {'Fail':>6} {'Running':>8} {'Success':>8}")
            print("  " + "─" * 70)

            for task_type in sorted(task_type_counts.keys()):
                counts = task_type_counts[task_type]
                total_type = sum(counts.values())
                passed = counts.get('PASS', 0)
                failed = counts.get('FAIL', 0)
                incomplete = counts.get('INCOMPLETE', 0)
                completed_type = passed + failed

                success = (passed / completed_type * 100) if completed_type > 0 else 0

                # Emoji based on performance
                if success >= 70:
                    emoji = "🌟"
                elif success >= 50:
                    emoji = "✅"
                elif success >= 30:
                    emoji = "⚠️"
                else:
                    emoji = "❌"

                print(f"  {emoji} {task_type:<13} {total_type:>6} {passed:>6} {failed:>6} {incomplete:>8} {success:>7.1f}%")

            # Recent completions
            print(f"\n{'RECENT COMPLETIONS (Last 10)':^80}")
            print("─" * 80)

            if recent_completions:
                for i, (task_id, task_type, status, mtime) in enumerate(recent_completions[:10]):
                    status_emoji = "✅" if status == "PASS" else "❌"
                    time_str = format_time_ago(mtime)
                    print(f"  {status_emoji} Task {task_id:3d} [{task_type:15s}] - {time_str:>8}")
            else:
                print("  No completed tasks yet...")

            # Currently running tasks
            running_tasks = [(tid, ttype) for tid, ttype, _, _ in results['INCOMPLETE']]
            if running_tasks:
                print(f"\n{'CURRENTLY RUNNING (' + str(len(running_tasks)) + ')':^80}")
                print("─" * 80)
                # Show up to 10 running tasks
                for task_id, task_type in sorted(running_tasks[:10]):
                    print(f"  ⏳ Task {task_id:3d} [{task_type:15s}]")
                if len(running_tasks) > 10:
                    print(f"  ... and {len(running_tasks) - 10} more")

            print("\n" + "=" * 80)
            print(f"  Refreshing in {refresh_interval}s... (Press Ctrl+C to exit)")
            print("=" * 80)

            time.sleep(refresh_interval)

    except KeyboardInterrupt:
        clear_screen()
        print("\n👋 Monitoring stopped. Final stats:\n")

        # Print final summary
        total = len(log_files)
        pass_count = len(results['PASS'])
        fail_count = len(results['FAIL'])
        incomplete_count = len(results['INCOMPLETE'])
        completed = pass_count + fail_count

        print(f"  ✅ PASS:       {pass_count:4d} ({pass_count/total*100:5.1f}%)")
        print(f"  ❌ FAIL:       {fail_count:4d} ({fail_count/total*100:5.1f}%)")
        print(f"  ⏳ INCOMPLETE: {incomplete_count:4d} ({incomplete_count/total*100:5.1f}%)")
        print(f"  📊 TOTAL:      {total:4d}")

        if completed > 0:
            success_rate = pass_count / completed * 100
            print(f"\n  🎯 Success Rate: {success_rate:.1f}% ({pass_count}/{completed})")

        print("\n✨ Done!\n")
        sys.exit(0)


def print_task_summary(log_dir: Path):
    """
    Print a detailed summary of all tasks with their status.

    Args:
        log_dir: Directory containing log files
    """
    log_files = sorted(log_dir.glob('task_*.log'))

    if not log_files:
        print("No log files found.")
        return

    results = {'FAIL': [], 'INCOMPLETE': [], 'PASS': []}

    for log_file in log_files:
        status, _ = analyze_log_file(log_file)
        task_id = extract_task_id(log_file.name)
        task_type = get_task_type(task_id)

        if status == 'PASS':
            results['PASS'].append((task_id, task_type))
        elif status == 'FAIL':
            results['FAIL'].append((task_id, task_type))
        else:
            results['INCOMPLETE'].append((task_id, task_type))

    # Calculate stats
    total = len(log_files)
    pass_count = len(results['PASS'])
    fail_count = len(results['FAIL'])
    incomplete_count = len(results['INCOMPLETE'])
    completed = pass_count + fail_count

    # Print success rate
    if completed > 0:
        success_rate = pass_count / completed * 100
        print(f"Success Rate: {success_rate:.1f}% ({pass_count}/{completed})\n")

    # Print header
    print(f"{'Task #':<8} {'Site':<20} {'Status':<12}")
    print("-" * 40)

    # Print in order: FAIL, INCOMPLETE, PASS
    for task_id, site in sorted(results['FAIL']):
        print(f"{task_id:<8} {site:<20} Fail")

    for task_id, site in sorted(results['INCOMPLETE']):
        print(f"{task_id:<8} {site:<20} Incomplete")

    for task_id, site in sorted(results['PASS']):
        print(f"{task_id:<8} {site:<20} Success")


def main():
    parser = argparse.ArgumentParser(description='Real-time WebArena log monitor')
    parser.add_argument(
        'log_dir',
        nargs='?',
        default='log_files',
        help='Directory containing log files (default: log_files)'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Refresh interval in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print task summary and exit (no live monitoring)'
    )
    args = parser.parse_args()

    log_dir = Path(args.log_dir)

    if not log_dir.exists():
        print(f"❌ Directory not found: {log_dir}")
        print(f"Creating directory: {log_dir}")
        log_dir.mkdir(parents=True, exist_ok=True)

    if args.summary:
        print_task_summary(log_dir)
    else:
        monitor_logs(log_dir, args.interval)


if __name__ == '__main__':
    main()
