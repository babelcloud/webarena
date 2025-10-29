"""Run WebArena evaluation using Claude via gbox-mcp"""
import argparse
import glob
import json
import logging
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path

from gbox_sdk import GboxSDK

from agent.gbox_claude_agent import GboxClaudeAgent
from browser_env import (
    ActionTypes,
    ScriptBrowserEnv,
    StateInfo,
    Trajectory,
    create_stop_action,
)
from browser_env.actions import is_equivalent
from browser_env.auto_login import get_site_comb_from_filepath
from browser_env.helper_functions import RenderHelper
from evaluation_harness import evaluator_router

# Configuration
DEFAULT_BOX_ID = "4e8e5ce1-fcb0-4e6b-963f-57492bfe99f1"

# Provider-specific model mappings
PROVIDER_MODELS = {
    "anthropic": {
        "primary": "claude-sonnet-4-5-20250929",
        "fallback": "claude-sonnet-4-20250514",
    },
    "bedrock": {
        "primary": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "fallback": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    }
}

SERVER_NAME = "gbox-browser"
ACTION_SET_TAG = "id_accessibility_tree"
OBSERVATION_TYPE = "accessibility_tree"
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 980
BOX_RESOLUTION_WIDTH = 1920
BOX_RESOLUTION_HEIGHT = 1080
MAX_STEPS = 30
HEADLESS = False
SAVE_TRACE = True
RENDER_SCREENSHOT = True
PARSING_FAILURE_TH = 3
REPEATING_ACTION_TH = 3

LOG_FOLDER = "log_files"
Path(LOG_FOLDER).mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("logger")
logger.setLevel(logging.DEBUG)

# Also set GboxClaudeAgent logger to DEBUG
agent_logger = logging.getLogger("agent.gbox_claude_agent")
agent_logger.setLevel(logging.DEBUG)

# Console handler (shared across all tasks)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

logger.addHandler(console_handler)
agent_logger.addHandler(console_handler)


def early_stop(trajectory, max_steps, thresholds):
    num_steps = (len(trajectory) - 1) / 2
    if num_steps >= max_steps:
        return True, f"Reach max steps {max_steps}"

    k = thresholds["parsing_failure"]
    last_k_actions = trajectory[1::2][-k:]
    if len(last_k_actions) >= k:
        if all([action["action_type"] == ActionTypes.NONE for action in last_k_actions]):
            return True, f"Failed to parse actions for {k} times"

    k = thresholds["repeating_action"]
    last_k_actions = trajectory[1::2][-k:]
    action_seq = trajectory[1::2]

    if len(action_seq) == 0:
        return False, ""

    last_action = action_seq[-1]

    if last_action["action_type"] != ActionTypes.TYPE:
        if len(last_k_actions) >= k:
            if all([is_equivalent(action, last_action) for action in last_k_actions]):
                return True, f"Same action for {k} times"
    else:
        if sum([is_equivalent(action, last_action) for action in action_seq]) >= k:
            return True, f"Same typing action for {k} times"

    return False, ""


def test(agent, config_file_list, box_id, gbox_client, result_dir):
    """Run tasks with fresh browser session per task."""
    scores = []
    early_stop_thresholds = {
        "parsing_failure": PARSING_FAILURE_TH,
        "repeating_action": REPEATING_ACTION_TH,
    }

    for config_file in config_file_list:
        env = None
        cdp_url = None
        task_file_handler = None
        try:
            # 0. SETUP PER-TASK LOG FILE
            # Extract task_id from config file path (e.g., "config_files/9.json" -> "9")
            task_id = os.path.basename(config_file).replace('.json', '')
            task_log_file = f"{LOG_FOLDER}/task_{task_id}_{time.strftime('%Y%m%d_%H%M%S')}.log"

            # Create file handler for this task
            task_file_handler = logging.FileHandler(task_log_file)
            task_file_handler.setLevel(logging.DEBUG)
            task_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

            # Add handler to both loggers
            logger.addHandler(task_file_handler)
            agent_logger.addHandler(task_file_handler)

            logger.info(f"📝 Logging to: {task_log_file}")

            # 1. OPEN BROWSER FOR THIS TASK
            logger.info(f"Opening browser for task {config_file}")
            open_result = gbox_client.v1.boxes.browser.open(
                box_id=box_id,
                show_controls=False  # Hide browser UI - visual agent doesn't need address bar
            )
            cdp_url = open_result.cdp_url
            logger.info(f"Browser opened with fresh CDP URL")

            # 2. CREATE FRESH ENV FOR THIS TASK
            env = ScriptBrowserEnv(
                headless=HEADLESS,
                slow_mo=0,
                observation_type=OBSERVATION_TYPE,
                current_viewport_only=True,
                viewport_size={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                save_trace_enabled=SAVE_TRACE,
                sleep_after_execution=0.0,
                cdp_url=cdp_url,
                skip_observation_extraction=True,  # Visual GBOX agent doesn't need DOM extraction
            )

            render_helper = RenderHelper(config_file, result_dir, ACTION_SET_TAG)

            with open(config_file) as f:
                _c = json.load(f)
                intent = _c["intent"]
                task_id = _c["task_id"]

                if _c["storage_state"]:
                    cookie_file_name = os.path.basename(_c["storage_state"])
                    comb = get_site_comb_from_filepath(cookie_file_name)
                    temp_dir = tempfile.mkdtemp()
                    subprocess.run(
                        ["python", "browser_env/auto_login.py", "--auth_folder", temp_dir, "--site_list", *comb]
                    )
                    _c["storage_state"] = f"{temp_dir}/{cookie_file_name}"
                    assert os.path.exists(_c["storage_state"])
                    config_file = f"{temp_dir}/{os.path.basename(config_file)}"
                    with open(config_file, "w") as f:
                        json.dump(_c, f)

            logger.info(f"[Config file]: {config_file}")
            logger.info(f"[Intent]: {intent}")

            agent.reset(config_file)
            trajectory: Trajectory = []
            obs, info = env.reset(options={"config_file": config_file})
            state_info: StateInfo = {"observation": obs, "info": info}
            trajectory.append(state_info)

            meta_data = {"action_history": ["None"]}
            while True:
                early_stop_flag, stop_info = early_stop(trajectory, MAX_STEPS, early_stop_thresholds)

                if early_stop_flag:
                    action = create_stop_action(f"Early stop: {stop_info}")
                else:
                    try:
                        action = agent.next_action(trajectory, intent, meta_data=meta_data)
                    except ValueError as e:
                        action = create_stop_action(f"ERROR: {str(e)}")

                trajectory.append(action)

                action_str = f"{action['action_type']}: {action.get('answer', '')}"
                render_helper.render(action, state_info, meta_data, RENDER_SCREENSHOT)
                meta_data["action_history"].append(action_str)

                if action["action_type"] == ActionTypes.STOP:
                    break

                if action["action_type"] == ActionTypes.NONE:
                    continue

                obs, _, terminated, _, info = env.step(action)
                state_info = {"observation": obs, "info": info}
                trajectory.append(state_info)

                if terminated:
                    trajectory.append(create_stop_action(""))
                    break

            # Ensure env.page references the active tab (handles new-tab navigation)
            try:
                if getattr(env, "context", None) and env.context.pages:
                    env.page = env.context.pages[-1]
                    env.page.bring_to_front()
                    env.page.client = env.page.context.new_cdp_session(env.page)  # type: ignore[attr-defined]
                    env.page.client.send("Accessibility.enable")  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug(f"Unable to refresh active page reference: {e}")

            evaluator = evaluator_router(config_file)
            score = evaluator(
                trajectory=trajectory,
                config_file=config_file,
                page=env.page,
                client=env.get_page_client(env.page),
            )

            scores.append(score)

            if score == 1:
                logger.info(f"[Result] (PASS) {config_file}")
            else:
                logger.info(f"[Result] (FAIL) {config_file}")

            if SAVE_TRACE:
                env.save_trace(Path(result_dir) / "traces" / f"{task_id}.zip")

        except Exception as e:
            logger.info(f"[Unhandled Error] {repr(e)}")
            import traceback
            with open(Path(result_dir) / "error.txt", "a") as f:
                f.write(f"[Config file]: {config_file}\n")
                f.write(f"[Unhandled Error] {repr(e)}\n")
                f.write(traceback.format_exc())

        finally:
            # 3. ALWAYS CLOSE BROWSER AND ENV (box stays alive)
            if env:
                try:
                    env.close()
                    logger.info(f"Closed environment for task")
                except Exception as e:
                    logger.warning(f"Failed to close environment: {e}")

            try:
                gbox_client.v1.boxes.browser.close(box_id=box_id)
                logger.info(f"Closed browser for task")
            except Exception as e:
                logger.warning(f"Failed to close browser: {e}")

            # 4. REMOVE TASK-SPECIFIC LOG HANDLER
            if task_file_handler:
                logger.removeHandler(task_file_handler)
                agent_logger.removeHandler(task_file_handler)
                task_file_handler.close()

        render_helper.close()

    # All tasks complete
    if scores:
        logger.info(f"Average score: {sum(scores) / len(scores)}")


def get_unfinished(config_files, result_dir):
    result_files = glob.glob(f"{result_dir}/*.html")
    task_ids = [os.path.basename(f).split(".")[0].split("_")[1] for f in result_files]
    unfinished_configs = []
    for config_file in config_files:
        task_id = os.path.basename(config_file).split(".")[0]
        if task_id not in task_ids:
            unfinished_configs.append(config_file)
    return unfinished_configs


def prepare(args: argparse.Namespace) -> None:
    """Prepare result directory (following run.py pattern)"""
    result_dir = args.result_dir
    if not result_dir:
        result_dir = f"cache/gbox_results_{time.strftime('%Y%m%d%H%M%S', time.localtime())}"

    if not Path(result_dir).exists():
        Path(result_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created result dir: {result_dir}")

    # Always set args.result_dir
    args.result_dir = result_dir

    if not (Path(result_dir) / "traces").exists():
        (Path(result_dir) / "traces").mkdir(parents=True)

    # Note: Individual task log files are created per-task in log_files/ directory
    # No need to track a single global log file anymore


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Run WebArena evaluation with Claude via GBOX",
        epilog="""
Examples:
  # Run tasks 0-10 on default box
  python gbox_run.py --start 0 --end 10

  # Run tasks in parallel on multiple boxes (same result dir)
  Terminal 1: python gbox_run.py --start 0 --end 5 --box_id <box1> --result_dir results_run1
  Terminal 2: python gbox_run.py --start 5 --end 10 --box_id <box2> --result_dir results_run1
  Terminal 3: python gbox_run.py --start 10 --end 15 --box_id <box3> --result_dir results_run1
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start task index (default: 0)"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=1,
        help="End task index (exclusive, default: 1)"
    )
    parser.add_argument(
        "--box_id",
        type=str,
        default=DEFAULT_BOX_ID,
        help=f"GBOX box ID to use (default: {DEFAULT_BOX_ID})"
    )
    parser.add_argument(
        "--result_dir",
        type=str,
        default="",
        help="Result directory - use SAME dir for parallel runs (default: auto-generated timestamp)"
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["anthropic", "bedrock"],
        default="bedrock",
        help="AI provider to use: anthropic (direct API) or bedrock (AWS) (default: bedrock)"
    )
    args = parser.parse_args()

    # Prepare result directory
    prepare(args)

    TEST_START_IDX = args.start
    TEST_END_IDX = args.end
    BOX_ID = args.box_id
    RESULT_DIR = args.result_dir
    PROVIDER = args.provider

    # Get models for selected provider
    MODEL = PROVIDER_MODELS[PROVIDER]["primary"]
    FALLBACK_MODEL = PROVIDER_MODELS[PROVIDER]["fallback"]
    USE_BEDROCK = (PROVIDER == "bedrock")

    logger.info(f"╔══════════════════════════════════════════════════════════════════════╗")
    logger.info(f"║  WebArena Parallel Runner                                            ║")
    logger.info(f"╠══════════════════════════════════════════════════════════════════════╣")
    box_display = BOX_ID if len(BOX_ID) <= 40 else f"{BOX_ID[:37]}..."
    logger.info(f"║  Box ID:      {box_display:<40}           ║")
    logger.info(f"║  Provider:    {PROVIDER:<40}           ║")
    model_display = MODEL if len(MODEL) <= 38 else f"{MODEL[:35]}..."
    logger.info(f"║  Model:       {model_display:<40}           ║")
    logger.info(f"║  Tasks:       {TEST_START_IDX} to {TEST_END_IDX-1:<44}           ║")
    result_display = RESULT_DIR if len(RESULT_DIR) <= 40 else f"{RESULT_DIR[:37]}..."
    logger.info(f"║  Result Dir:  {result_display:<40}           ║")
    logger.info(f"╚══════════════════════════════════════════════════════════════════════╝")

    gbox = GboxSDK()
    box = gbox.get(BOX_ID)

    logger.info(f"Setting box resolution to {BOX_RESOLUTION_WIDTH}x{BOX_RESOLUTION_HEIGHT}")
    box.resolution.set(width=BOX_RESOLUTION_WIDTH, height=BOX_RESOLUTION_HEIGHT)

    logger.info("Box ready - will open/close browser per task")

    agent = GboxClaudeAgent(
        box_id=BOX_ID,
        action_set_tag=ACTION_SET_TAG,
        server_name=SERVER_NAME,
        model=MODEL,
        gbox_client=gbox.client,
        use_bedrock=USE_BEDROCK,
        fallback_model=FALLBACK_MODEL,
    )

    config_files = []
    for i in range(TEST_START_IDX, TEST_END_IDX):
        config_file = f"config_files/{i}.json"
        if Path(config_file).exists():
            config_files.append(config_file)

    if not config_files:
        logger.error(f"No config files found in range {TEST_START_IDX} to {TEST_END_IDX}!")
        return

    logger.info(f"Running tasks {TEST_START_IDX} to {TEST_END_IDX-1} ({len(config_files)} tasks)")

    test_file_list = get_unfinished(config_files, RESULT_DIR)

    if len(test_file_list) == 0:
        logger.info("No task left to run")
    else:
        logger.info(f"Running {len(test_file_list)} tasks (fresh browser per task)")
        test(agent, test_file_list, BOX_ID, gbox.client, RESULT_DIR)

    logger.info("✅ All tasks complete! Box remains alive.")


if __name__ == "__main__":
    main()
