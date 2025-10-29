#!/usr/bin/env python3
"""
Human evaluation mode for WebArena tasks.

This script lets you manually complete a task in the browser, then evaluates
your work using the same evaluation pipeline as the agent.

Usage:
    python human_eval.py 662
"""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_env import create_stop_action, StateInfo, Trajectory
from browser_env.auto_login import get_site_comb_from_filepath
from evaluation_harness import evaluator_router


def human_eval(task_id: int):
    config_file = Path(f"config_files/{task_id}.json")

    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return

    with open(config_file) as f:
        config = json.load(f)

    print("=" * 80)
    print(f"HUMAN EVALUATION MODE - TASK {task_id}")
    print("=" * 80)
    print(f"\n📋 INTENT:")
    print(f"   {config['intent']}")
    print(f"\n🌐 START URL:")
    print(f"   {config['start_url']}")
    print(f"\n🔐 REQUIRES LOGIN: {config['require_login']}")

    # Show evaluation criteria
    eval_config = config['eval']
    eval_types = eval_config.get('eval_types', [])

    print("\n" + "=" * 80)
    print("EVALUATION CRITERIA:")
    print("=" * 80)

    if 'url_match' in eval_types:
        print(f"\n✅ URL CHECK:")
        print(f"   Final URL must contain: {eval_config['reference_url']}")
        print(f"   Rule: {eval_config.get('url_note', 'GOLD in PRED')}")

    if 'program_html' in eval_types:
        print(f"\n✅ HTML CHECKS:")
        for i, check in enumerate(eval_config['program_html'], 1):
            print(f"\n   Check {i}:")
            print(f"   - URL: {check['url']}")
            print(f"   - Selector: {check['locator'][:80]}...")
            if 'exact_match' in check['required_contents']:
                print(f"   - Must exactly match: {check['required_contents']['exact_match']}")
            elif 'must_include' in check['required_contents']:
                print(f"   - Must include: {check['required_contents']['must_include']}")

    if 'string_match' in eval_types:
        print(f"\n✅ ANSWER CHECK:")
        ref_answers = eval_config.get('reference_answers', {})
        for match_type, value in ref_answers.items():
            print(f"   - {match_type}: {value}")

    print("\n" + "=" * 80)
    print("🎮 INSTRUCTIONS:")
    print("=" * 80)
    print("1. Browser will open with authentication loaded")
    print("2. Complete the task manually in the browser")
    print("3. When done, press ENTER in this terminal")
    print("4. Provide the final textual answer if the task requires one")
    print("5. Evaluator will check your work and show the score")
    print("=" * 80)
    input("\nPress ENTER to open browser and start...")

    # Handle authentication
    temp_dir = None
    if config.get('storage_state'):
        cookie_file_name = Path(config['storage_state']).name
        comb = get_site_comb_from_filepath(cookie_file_name)
        temp_dir = tempfile.mkdtemp()
        subprocess.run(
            ["python", "browser_env/auto_login.py", "--auth_folder", temp_dir, "--site_list", *comb],
            check=True
        )
        config['storage_state'] = f"{temp_dir}/{cookie_file_name}"

    # Open browser
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )

        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "no_viewport": True,
        }

        if config.get('storage_state') and Path(config['storage_state']).exists():
            context_args['storage_state'] = config['storage_state']
            print(f"✅ Loaded authentication from {config['storage_state']}")

        if config.get('geolocation'):
            context_args['geolocation'] = config['geolocation']

        context = browser.new_context(**context_args)
        page = context.new_page()

        # Enable CDP session for accessibility tree (if needed)
        client = page.context.new_cdp_session(page)
        client.send("Accessibility.enable")

        # Navigate to start URL
        print(f"\n🌐 Navigating to: {config['start_url']}")
        page.goto(config['start_url'])

        print("\n" + "=" * 80)
        print("✨ Browser is open! Complete the task manually.")
        print("=" * 80)
        print("\nWhen you're done:")
        print("  1. Leave the browser on the final page")
        print("  2. Press ENTER in this terminal")
        print("=" * 80)

        # Wait for human to complete task
        input("\n⏸️  Press ENTER when you've completed the task...")

        # Capture final state
        # Refresh page reference to use the active tab (handles new-tab navigation)
        if context.pages:
            page = context.pages[-1]
            # Recreate CDP session for the active page to keep evaluator happy
            client = page.context.new_cdp_session(page)
            client.send("Accessibility.enable")
        # Evaluate location directly from the browser to avoid cached value
        final_url = page.evaluate("() => window.location.href")
        print(f"\n📍 FINAL URL: {final_url}")

        # Create minimal trajectory for evaluation
        # Trajectory format: [StateInfo, Action, StateInfo, Action, ..., Action (STOP)]
        # For evaluation, we just need the final state and a STOP action

        # Create dummy initial state
        initial_state: StateInfo = {
            "observation": {"text": "", "image": None},
            "info": {
                "page": type('obj', (object,), {'url': config['start_url'], 'content': lambda: ''})(),
                "fail_error": "",
                "observation_metadata": {"text": {"obs_nodes_info": {}}},
            }
        }

        # Ask user for final answer (for string_match evaluations)
        user_answer = input(
            "\n📝 If the task expects a textual answer, type it now (press ENTER to skip): "
        )
        final_answer = user_answer.strip()

        # Create STOP action with provided answer (fallback keeps legacy behaviour)
        stop_action = create_stop_action(
            final_answer if final_answer else "Task completed by human"
        )

        # Create final state
        final_state: StateInfo = {
            "observation": {"text": "", "image": None},
            "info": {
                "page": type('obj', (object,), {'url': final_url, 'content': lambda: page.content()})(),
                "fail_error": "",
                "observation_metadata": {"text": {"obs_nodes_info": {}}},
            }
        }

        # Build trajectory
        trajectory: Trajectory = [initial_state, stop_action]

        print("\n" + "=" * 80)
        print("🔍 EVALUATING YOUR WORK...")
        print("=" * 80)

        # Run evaluation
        try:
            evaluator = evaluator_router(str(config_file))
            score = evaluator(
                trajectory=trajectory,
                config_file=str(config_file),
                page=page,
                client=client,
            )

            print("\n" + "=" * 80)
            if score == 1.0:
                print("✅ RESULT: PASS")
            else:
                print(f"❌ RESULT: FAIL (score: {score})")
            print("=" * 80)

        except Exception as e:
            print(f"\n❌ Evaluation error: {e}")
            import traceback
            traceback.print_exc()

        print("\n📊 Final URL:", final_url)

        if 'url_match' in eval_types:
            ref_url = eval_config['reference_url']
            if ref_url in final_url:
                print(f"   ✅ URL CHECK: Reference URL '{ref_url}' found in final URL")
            else:
                print(f"   ❌ URL CHECK: Reference URL '{ref_url}' NOT found in '{final_url}'")

        input("\n\nPress ENTER to close browser...")
        browser.close()

    print("\n✅ Done!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Human evaluation for WebArena tasks")
    parser.add_argument("task_id", type=int, help="Task ID to test (e.g., 662)")
    args = parser.parse_args()

    human_eval(args.task_id)
