import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import numpy as np
import numpy.typing as npt
from beartype import beartype
from beartype.door import is_bearable
from gymnasium import Env
from gymnasium.spaces import Box, Text
from playwright.sync_api import (
    CDPSession,
    Page,
    Playwright,
    ViewportSize,
    expect,
    sync_playwright,
)

from .actions import Action, execute_action, get_action_space
from .processors import ObservationHandler, ObservationMetadata
from .utils import (
    AccessibilityTree,
    DetachedPage,
    Observation,
    png_bytes_to_numpy,
)


@dataclass
class PlaywrightScript:
    function: str  # goto, get_by_role
    destination: str  # https://www.google.com/, combobox
    name: str | None = None  # Search, Avatar 2009
    operation: str | None = None  # click, fill, press
    value: str | None = None  # avatar movie, Enter


def parse_action(action: str) -> PlaywrightScript:
    splitted = action.strip().split(" ")
    assert len(splitted) >= 2
    match splitted[:2]:
        case ["goto", url]:
            assert len(splitted) == 2
            return PlaywrightScript("goto", url)
        case ["get_by_role", destination]:
            assert len(splitted) >= 4
            match splitted[2:]:
                case [name, operation]:
                    return PlaywrightScript(
                        "get_by_role", destination, name, operation
                    )
                case [name, operation, value]:
                    return PlaywrightScript(
                        "get_by_role", destination, name, operation, value
                    )
                case _:
                    raise ValueError("Invalid action")
        case _:
            raise ValueError(f"Invalid action {action}")


class ScriptBrowserEnv(Env[dict[str, Observation], Action]):
    """
    The goal of this environment is to produce a prototype of a browser environment.
    In the end, we want to support a fully configurable browser environment with wide
    range of action spaces and observation spaces, both structured and unstructured.
    But in this prototype, we just support action space specified by Playwright script,
    and observation space is the html content of the page.
    """

    @beartype
    def __init__(
        self,
        max_page_length: int = 8192,
        headless: bool = True,
        slow_mo: int = 0,
        observation_type: str = "html",
        current_viewport_only: bool = False,
        viewport_size: ViewportSize = {"width": 1280, "height": 720},
        save_trace_enabled: bool = False,
        sleep_after_execution: float = 0.0,
        cdp_url: str | None = None,
        skip_observation_extraction: bool = False,
    ):
        # TODO: make Space[Action] = ActionSpace
        self.action_space = get_action_space()  # type: ignore[assignment]
        self.headless = headless
        self.slow_mo = slow_mo
        self.current_viewport_only = current_viewport_only
        self.reset_finished = False
        self.viewport_size = viewport_size
        self.save_trace_enabled = save_trace_enabled
        self.sleep_after_execution = sleep_after_execution
        self.cdp_url = cdp_url
        self.skip_observation_extraction = skip_observation_extraction

        match observation_type:
            case "html" | "accessibility_tree":
                self.text_observation_type = observation_type
                self.image_observation_type = ""
                self.main_observation_type = "text"
            case "image":
                self.image_observation_type = observation_type
                self.text_observation_type = ""  # type: ignore[assignment]
                self.main_observation_type = "image"
            case _:
                raise ValueError(
                    f"Unsupported observation type: {observation_type}"
                )

        self.observation_handler = ObservationHandler(
            self.main_observation_type,
            self.text_observation_type,
            self.image_observation_type,
            self.current_viewport_only,
            self.viewport_size,
        )

        self.observation_space = (
            self.observation_handler.get_observation_space()
        )

    @beartype
    def setup(self, config_file: Path | None = None) -> None:
        print(f"[SETUP] Starting setup, config_file={config_file}")
        self.context_manager = sync_playwright()
        self.playwright = self.context_manager.__enter__()
        print(f"[SETUP] Playwright initialized")

        if self.cdp_url:
            print(f"[SETUP] Connecting to browser via CDP: {self.cdp_url}")
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            print(f"[SETUP] ✅ Connected to browser successfully")
        else:
            print(f"[SETUP] Launching browser with headless={self.headless}, slow_mo={self.slow_mo}")
            launch_args = {
                "headless": self.headless,
                "slow_mo": self.slow_mo,
            }
            if not self.headless:
                launch_args["args"] = ["--start-maximized"]
                print(f"[SETUP] Added --start-maximized flag, launching visible browser")
            self.browser = self.playwright.chromium.launch(**launch_args)
            print(f"[SETUP] ✅ Browser launched successfully")

        print(f"[SETUP] Reading config file...")
        if config_file:
            with open(config_file, "r") as f:
                instance_config = json.load(f)
        else:
            instance_config = {}

        storage_state = instance_config.get("storage_state", None)
        start_url = instance_config.get("start_url", None)
        geolocation = instance_config.get("geolocation", None)
        print(f"[SETUP] Config loaded: start_url={start_url}, has_storage={bool(storage_state)}")

        print(f"[SETUP] Creating browser context...")
        self.context = self.browser.new_context(
            viewport=self.viewport_size,
            storage_state=storage_state,
            geolocation=geolocation,
            device_scale_factor=1,
        )
        print(f"[SETUP] ✅ Browser context created")
        if self.save_trace_enabled:
            print(f"[SETUP] Starting trace...")
            self.context.tracing.start(screenshots=True, snapshots=True)

        if start_url:
            start_urls = start_url.split(" |AND| ")
            print(f"[SETUP] Will navigate to {len(start_urls)} URL(s)")
            for i, url in enumerate(start_urls, 1):
                print(f"[SETUP] [{i}/{len(start_urls)}] Creating new page...")
                page = self.context.new_page()
                print(f"[SETUP] [{i}/{len(start_urls)}] ✅ Page created")

                print(f"[SETUP] [{i}/{len(start_urls)}] Creating CDP session...")
                client = page.context.new_cdp_session(page)
                print(f"[SETUP] [{i}/{len(start_urls)}] ✅ CDP session created")

                if self.text_observation_type == "accessibility_tree":
                    print(f"[SETUP] [{i}/{len(start_urls)}] Enabling accessibility...")
                    client.send("Accessibility.enable")
                    print(f"[SETUP] [{i}/{len(start_urls)}] ✅ Accessibility enabled")

                page.client = client  # type: ignore

                print(f"[SETUP] [{i}/{len(start_urls)}] 🌐 Navigating to: {url}")
                import time
                nav_start = time.time()
                try:
                    page.goto(url, timeout=10000, wait_until='domcontentloaded')
                    nav_time = time.time() - nav_start
                    print(f"[SETUP] [{i}/{len(start_urls)}] ✅ Navigation complete ({nav_time:.1f}s)")
                except Exception as e:
                    nav_time = time.time() - nav_start
                    print(f"[SETUP] [{i}/{len(start_urls)}] ❌ Navigation failed ({nav_time:.1f}s): {e}")

            # set the first page as the current page
            print(f"[SETUP] Setting first page as active...")
            self.page = self.context.pages[0]
            self.page.bring_to_front()
            print(f"[SETUP] ✅ Page activated")
        else:
            print(f"[SETUP] No start URL, creating blank page...")
            self.page = self.context.new_page()
            client = self.page.context.new_cdp_session(self.page)
            if self.text_observation_type == "accessibility_tree":
                client.send("Accessibility.enable")
            self.page.client = client  # type: ignore
            self.page.goto("about:blank", timeout=5000)
            print(f"[SETUP] ✅ Blank page created")

        print(f"[SETUP] ✅✅✅ Setup complete!")

    def get_page_client(self, page: Page) -> CDPSession:
        return page.client  # type: ignore

    def _get_obs(self) -> dict[str, Observation]:
        if self.skip_observation_extraction:
            print(f"[OBS] ⚡ Skipping observation extraction (visual agent mode)")
            # Return minimal placeholder for visual agents using GBOX
            return {
                "text": "[Observation skipped - using visual GBOX agent]",
                "image": np.zeros((self.viewport_size["height"], self.viewport_size["width"], 3), dtype=np.uint8),
            }

        print(f"[OBS] Getting observation from page...")
        import time
        obs_start = time.time()
        obs = self.observation_handler.get_observation(
            self.page, self.get_page_client(self.page)
        )
        obs_time = time.time() - obs_start
        print(f"[OBS] ✅ Observation received ({obs_time:.1f}s)")
        return obs

    def _get_obs_metadata(self) -> dict[str, ObservationMetadata]:
        if self.skip_observation_extraction:
            print(f"[OBS] ⚡ Skipping observation metadata (visual agent mode)")
            # Return minimal placeholder metadata
            return {
                "text": {"obs_nodes_info": {}},
            }

        print(f"[OBS] Getting observation metadata...")
        import time
        meta_start = time.time()
        metadata = self.observation_handler.get_observation_metadata()
        meta_time = time.time() - meta_start
        print(f"[OBS] ✅ Metadata received ({meta_time:.1f}s)")
        return metadata

    @beartype
    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, str] | None = None,
    ) -> tuple[dict[str, Observation], dict[str, Any]]:
        """
        Reset the environment.
        :param options: options for the environment. The current supported options are:
            - "storage_state": the storage state of the browser. It is a file path to a json file.
        """
        print(f"[RESET] Starting reset...")
        super().reset(seed=seed, options=options)

        if self.reset_finished:
            print(f"[RESET] Cleaning up previous context...")
            self.context_manager.__exit__()

        if options is not None and "config_file" in options:
            config_file = Path(options["config_file"])
            if config_file.exists():
                print(f"[RESET] Calling setup with config...")
                self.setup(config_file=config_file)
                print(f"[RESET] ✅ Setup returned")
            else:
                raise ValueError(f"Config file {config_file} does not exist.")
        else:
            print(f"[RESET] Calling setup without config...")
            self.setup()
            print(f"[RESET] ✅ Setup returned")

        self.reset_finished = True

        if self.sleep_after_execution > 0:
            print(f"[RESET] Sleeping {self.sleep_after_execution}s...")
            time.sleep(self.sleep_after_execution)

        print(f"[RESET] Getting observation...")
        observation = self._get_obs()
        print(f"[RESET] ✅ Observation received")

        print(f"[RESET] Getting observation metadata...")
        observation_metadata = self._get_obs_metadata()
        print(f"[RESET] ✅ Metadata received")

        info = {
            "page": DetachedPage(self.page.url, ""),
            "fail_error": "",
            "observation_metadata": observation_metadata,
        }

        print(f"[RESET] ✅✅✅ Reset complete! Returning observation...")
        return (observation, info)

    def save_trace(self, trace_path: str | Path) -> None:
        if self.save_trace_enabled:
            self.context.tracing.stop(path=trace_path)

    def close(self) -> None:
        if self.reset_finished:
            self.context_manager.__exit__()

    def step(
        self, action: Action
    ) -> tuple[dict[str, Observation], float, bool, bool, dict[str, Any]]:
        if not self.reset_finished:
            raise RuntimeError("Call reset first before calling step.")

        success = False
        fail_error = ""
        try:
            self.page = execute_action(
                action,
                self.page,
                self.context,
                self.observation_handler.action_processor,
            )
            success = True
        except Exception as e:
            fail_error = str(e)

        # hard sleep TODO[shuyanzh] suboptimal, may need to check network
        if self.sleep_after_execution > 0:
            time.sleep(self.sleep_after_execution)

        observation = self._get_obs()
        observation_metadata = self._get_obs_metadata()

        info = {
            "page": DetachedPage(self.page.url, self.page.content()),
            "fail_error": fail_error,
            "observation_metadata": observation_metadata,
        }
        msg = (
            observation,
            float(success),  # reward
            False,  # terminated
            False,  # truncated
            info,
        )
        return msg
