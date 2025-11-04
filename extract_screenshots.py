#!/usr/bin/env python3
"""
Extract all screenshots from a Claude Code session JSONL file.

This script can work in two modes:
1. Direct JSONL file path: python extract_screenshots.py path/to/file.jsonl
2. Task number lookup: python extract_screenshots.py 174

For task number mode, it:
- Finds the log file (e.g., log_files/task_174_*.log)
- Extracts first and last timestamps from the log
- Finds the matching JSONL file in ~/.claude/projects/-Users-skshibu-webarena/
  that was created/modified around those timestamps
- Extracts screenshots from that JSONL file
"""

import json
import base64
import os
import re
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple


def parse_log_timestamps(log_path: str) -> Tuple[datetime, datetime]:
    """
    Extract first and last timestamps from a log file.

    Args:
        log_path: Path to the log file

    Returns:
        (first_timestamp, last_timestamp) as datetime objects
    """
    first_ts = None
    last_ts = None

    # Pattern to match log timestamps: 2025-10-26 09:33:12,269
    ts_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+')

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = ts_pattern.match(line)
            if match:
                ts_str = match.group(1)
                ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')

                if first_ts is None:
                    first_ts = ts
                last_ts = ts  # Keep updating to get the last one

    if first_ts is None or last_ts is None:
        raise ValueError(f"Could not find valid timestamps in {log_path}")

    return first_ts, last_ts


def find_jsonl_by_timestamps(
    first_ts: datetime,
    last_ts: datetime,
    search_dir: str = "~/.claude/projects/-Users-skshibu-webarena"
) -> Optional[str]:
    """
    Find JSONL file that matches the timestamp range.

    Args:
        first_ts: Expected creation time
        last_ts: Expected modification time
        search_dir: Directory to search for JSONL files

    Returns:
        Path to matching JSONL file, or None if not found
    """
    search_path = Path(search_dir).expanduser()

    if not search_path.exists():
        print(f"⚠️  Warning: Directory not found: {search_path}")
        return None

    # Find all JSONL files
    jsonl_files = list(search_path.glob("*.jsonl"))

    if not jsonl_files:
        print(f"⚠️  Warning: No JSONL files found in {search_path}")
        return None

    print(f"🔍 Searching {len(jsonl_files)} JSONL files for matching timestamps...")
    print(f"   Looking for: created ~{first_ts}, modified ~{last_ts}")

    best_match = None
    best_score = float('inf')

    # Allow 5 minute tolerance for timestamp matching
    tolerance_seconds = 300

    for jsonl_file in jsonl_files:
        stat = jsonl_file.stat()
        created = datetime.fromtimestamp(stat.st_birthtime if hasattr(stat, 'st_birthtime') else stat.st_ctime)
        modified = datetime.fromtimestamp(stat.st_mtime)

        # Calculate how close this file's timestamps are to our target
        created_diff = abs((created - first_ts).total_seconds())
        modified_diff = abs((modified - last_ts).total_seconds())

        total_diff = created_diff + modified_diff

        # Check if within tolerance
        if created_diff <= tolerance_seconds and modified_diff <= tolerance_seconds:
            if total_diff < best_score:
                best_score = total_diff
                best_match = jsonl_file
                print(f"   ✓ Match found: {jsonl_file.name}")
                print(f"     Created: {created}, Modified: {modified}")
                print(f"     Score: {total_diff:.1f}s difference")

    if best_match:
        print(f"✅ Best match: {best_match}")
        return str(best_match)
    else:
        print(f"❌ No JSONL file found matching timestamps")
        return None


def find_log_file_for_task(task_num: int, log_dir: str = "log_files") -> Optional[str]:
    """
    Find the log file for a given task number.

    Args:
        task_num: Task number (e.g., 174)
        log_dir: Directory containing log files

    Returns:
        Path to log file, or None if not found
    """
    log_path = Path(log_dir)

    if not log_path.exists():
        print(f"❌ Error: Log directory not found: {log_dir}")
        return None

    # Pattern: task_174_20251026_093312.log
    pattern = f"task_{task_num}_*.log"
    matches = list(log_path.glob(pattern))

    if not matches:
        print(f"❌ Error: No log file found for task {task_num} in {log_dir}/")
        return None

    if len(matches) > 1:
        # Sort by modification time, take the most recent
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        print(f"⚠️  Found {len(matches)} log files, using most recent")

    log_file = matches[0]
    print(f"📋 Found log file: {log_file}")
    return str(log_file)


def extract_screenshots(jsonl_path: str, output_dir: str = "trace") -> int:
    """
    Extract all screenshots from JSONL file into output directory.

    Args:
        jsonl_path: Path to the .jsonl file
        output_dir: Directory to save screenshots (default: "trace")

    Returns:
        Number of screenshots extracted
    """
    # Create output directory (remove old one if exists)
    output_path = Path(output_dir)

    # Clear existing screenshots if directory exists
    if output_path.exists():
        print(f"🗑️  Clearing existing screenshots in {output_dir}/")
        for file in output_path.glob("screenshot_*.png"):
            file.unlink()
        for file in output_path.glob("screenshot_*.jpg"):
            file.unlink()
    else:
        output_path.mkdir(exist_ok=True)

    screenshot_count = 0

    print(f"📖 Reading {jsonl_path}...")
    print(f"💾 Saving screenshots to {output_dir}/")

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                # Parse JSON line
                data = json.loads(line.strip())

                # Look for tool results with images
                if data.get('type') == 'user' and 'message' in data:
                    message = data['message']

                    # Check if this is a tool result
                    if message.get('role') == 'user' and 'content' in message:
                        content = message['content']

                        # Content can be a list of tool results
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'tool_result':
                                    # Check tool result content for images
                                    tool_content = item.get('content', [])
                                    if isinstance(tool_content, list):
                                        for tool_item in tool_content:
                                            if isinstance(tool_item, dict) and tool_item.get('type') == 'image':
                                                # Extract base64 image data
                                                source = tool_item.get('source', {})
                                                image_data = source.get('data', '')
                                                media_type = source.get('media_type', 'image/png')

                                                if image_data:
                                                    screenshot_count += 1

                                                    # Determine file extension
                                                    ext = 'png'
                                                    if 'jpeg' in media_type or 'jpg' in media_type:
                                                        ext = 'jpg'

                                                    # Save image
                                                    filename = f"screenshot_{screenshot_count:04d}.{ext}"
                                                    filepath = output_path / filename

                                                    try:
                                                        # Decode and save
                                                        image_bytes = base64.b64decode(image_data)
                                                        with open(filepath, 'wb') as img_file:
                                                            img_file.write(image_bytes)

                                                        print(f"✅ Extracted: {filename} ({len(image_bytes):,} bytes)")
                                                    except Exception as e:
                                                        print(f"⚠️  Failed to decode image {screenshot_count}: {e}")

            except json.JSONDecodeError as e:
                print(f"⚠️  Skipping line {line_num}: Invalid JSON - {e}")
            except Exception as e:
                print(f"⚠️  Error processing line {line_num}: {e}")

    print(f"\n🎉 Done! Extracted {screenshot_count} screenshots to {output_dir}/")
    return screenshot_count


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract screenshots from Claude Code session JSONL file',
        epilog="""
Examples:
  # Extract from direct JSONL file path
  python extract_screenshots.py session.jsonl

  # Extract from task number (auto-finds log and JSONL)
  python extract_screenshots.py 174

  # Specify output directory
  python extract_screenshots.py 174 -o my_screenshots
        """
    )
    parser.add_argument(
        'input',
        help='Task number (e.g., 174) or path to .jsonl file'
    )
    parser.add_argument(
        '-o', '--output',
        default='trace',
        help='Output directory for screenshots (default: trace)'
    )
    parser.add_argument(
        '--log-dir',
        default='log_files',
        help='Directory containing log files (default: log_files)'
    )

    args = parser.parse_args()

    # Determine if input is a task number or file path
    if args.input.isdigit():
        # Task number mode
        task_num = int(args.input)
        print(f"🔢 Task number mode: {task_num}")
        print("=" * 70)

        # Step 1: Find log file
        log_file = find_log_file_for_task(task_num, args.log_dir)
        if not log_file:
            return 1

        # Step 2: Extract timestamps from log
        print(f"⏰ Extracting timestamps from log...")
        try:
            first_ts, last_ts = parse_log_timestamps(log_file)
            print(f"   First: {first_ts}")
            print(f"   Last:  {last_ts}")
            print(f"   Duration: {(last_ts - first_ts).total_seconds():.1f} seconds")
        except Exception as e:
            print(f"❌ Error parsing timestamps: {e}")
            return 1

        # Step 3: Find matching JSONL file
        jsonl_file = find_jsonl_by_timestamps(first_ts, last_ts)
        if not jsonl_file:
            print("\n💡 Tip: Make sure the task was run with Claude Code")
            print("   and the session logs are in ~/.claude/projects/")
            return 1

        print("=" * 70)

    else:
        # Direct file path mode
        jsonl_file = args.input
        if not os.path.exists(jsonl_file):
            print(f"❌ Error: File not found: {jsonl_file}")
            return 1

    # Extract screenshots
    count = extract_screenshots(jsonl_file, args.output)

    return 0 if count > 0 else 1


if __name__ == '__main__':
    exit(main())
