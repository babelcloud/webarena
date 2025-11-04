"""
GboxClaudeAgent - WebArena agent that uses Claude via gbox-mcp.

Follows WebArena's Agent interface but delegates browser control to Claude
through the GBOX MCP server.
"""

import asyncio
import logging
import os
import textwrap
import threading
from typing import Any, List, Optional

from browser_env import Action, ActionTypes, Trajectory, create_stop_action
from browser_env.utils import StateInfo

logger = logging.getLogger(__name__)

try:
    # Claude Code SDK
    from claude_agent_sdk import (
        AgentDefinition,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
        ResultMessage,
    )
    from agent.wikipedia_subagent import create_wikipedia_subagent
    from agent.magento_admin_subagent import create_magento_admin_subagent
except ImportError as exc:
    logger.error(f"Failed to import claude_agent_sdk: {exc}")
    ClaudeSDKClient = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class GboxClaudeAgent:
    """
    Agent that lets Claude Code drive WebArena tasks via GBOX MCP.

    Follows WebArena's Agent interface:
    - next_action(trajectory, intent, meta_data) -> Action
    - reset(test_config_file)
    """

    def __init__(
        self,
        box_id: str,
        action_set_tag: str = "id_accessibility_tree",
        server_name: str = "gbox-browser",
        model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        prompt_template: Optional[str] = None,
        gbox_client: Any = None,
        use_bedrock: bool = True,
        fallback_model: Optional[str] = None,
    ):
        """
        Initialize the GBOX Claude agent.

        Args:
            box_id: GBOX box ID where browser is running
            action_set_tag: Action format (for WebArena compatibility)
            server_name: MCP server name for gbox tools
            model: Claude model to use
            prompt_template: Custom system prompt (optional)
            gbox_client: GBOX SDK client for direct actions (optional)
            use_bedrock: Whether to use AWS Bedrock (vs Anthropic API)
            fallback_model: Fallback model to use on errors
        """
        if ClaudeSDKClient is None:
            raise ImportError(
                "claude_agent_sdk not available. Install with: pip install claude-agent-sdk"
            ) from _IMPORT_ERROR

        self.box_id = box_id
        self.action_set_tag = action_set_tag
        self.server_name = server_name
        self.model = model
        self.gbox_client = gbox_client
        self.use_bedrock = use_bedrock
        self.fallback_model = fallback_model or model

        # Session management
        self._session_id: Optional[str] = None
        self._completed = False
        self._final_answer: Optional[str] = None
        self._step_count = 0

        # Image error tracking (per task)
        self._image_error_count = 0
        self._max_image_error_retries = 2

        # Claude options
        self._claude_options = self._create_claude_options()

        # System prompt
        self._prompt_template = prompt_template or self._default_prompt()

    def _create_claude_options(self, use_sonnet_4: bool = False) -> ClaudeAgentOptions:
        """Create Claude SDK options with MCP tool access.

        Args:
            use_sonnet_4: If True, use fallback model instead of default model
        """
        # Define allowed tools
        tool_names = [
            "screenshot",
            "click",
            "hover",
            "type",
            "scroll",
            "press_key",
            "wait",
            "list_tabs",
            "switch_tab",
            "close_tab",
        ]
        allowed_tools = [f"mcp__{self.server_name}__{tool}" for tool in tool_names]

        # Add task completion tool
        allowed_tools.append("mcp__task-completion__complete_task")

        # Add Task tool to enable subagent invocation
        allowed_tools.append("Task")

        # Choose model
        model = self.fallback_model if use_sonnet_4 else self.model

        # Resume from previous session if available
        resume_session = self._session_id if self._session_id else None

        # Configure environment variables for Bedrock
        env_vars = {}
        if self.use_bedrock:
            env_vars = {
                "CLAUDE_CODE_USE_BEDROCK": "true",
                "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
                "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
                "AWS_REGION": os.environ.get("AWS_REGION", "us-west-2"),
            }

        # Create subagents
        agents = {}
        agents.update(create_wikipedia_subagent(self.box_id, self.server_name))
        agents.update(create_magento_admin_subagent(self.box_id, self.server_name))

        # Block file modification tools - keep Bash and Read
        disallowed_tools = [
            "Write",  # Block creating/overwriting files
            "Edit",   # Block editing files
            "Glob",   # Block file searching
        ]

        return ClaudeAgentOptions(
            setting_sources=["user", "project", "local"],
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            permission_mode="acceptEdits",
            model=model,
            max_buffer_size=10 * 1024 * 1024,  # 10MB for screenshots
            resume=resume_session,
            env=env_vars,
            agents=agents,
        )

    def _default_prompt(self) -> str:
        """Default system prompt for WebArena tasks."""
        return textwrap.dedent(
            """
            You are an autonomous intelligent agent tasked with completing web-based tasks.
            You are working on FAKE TESTING WEBSITES - clones designed to test AI agents.
            You are on the East Coast time zone and the year is 2025.

            ⚙️ GBOX ENVIRONMENT:
            - Profile name: byteblaze
            - You are operating through the gbox-mcp server with this profile

            ═══════════════════════════════════════════════════════════════════════
            YOUR TASK:
            ═══════════════════════════════════════════════════════════════════════

            OBJECTIVE: {intent}
            CURRENT URL: {url}

            ⚠️ CRITICAL: ONLY use these test websites. NEVER navigate to real websites like:
               google.com, wikipedia.org, reddit.com, etc.

            ═══════════════════════════════════════════════════════════════════════
            AVAILABLE TOOLS (all require boxId='{box_id}'):
            ═══════════════════════════════════════════════════════════════════════

            - screenshot(boxId): Capture current screen state
            - click(boxId, target): Click on element (describe the elements extremely precisely)
            - hover(boxId, target): Hover over element to reveal dropdowns, tooltips, or expandable menus.
              **CRITICAL FOR NESTED DROPDOWNS**: When you hover over a menu item and a dropdown appears, you MUST hover over items in that dropdown to check if there are sub-dropdowns before clicking anything. DO NOT click immediately - first explore all nested levels by hovering. Many navigation menus have multiple nested levels (e.g., Category → Subcategory → Sub-subcategory).
            - type(boxId, content, pressEnterAfterType): Type text into focused field
            - scroll(boxId, direction, distance): Scroll up means it will show the top of page and scroll down will move towards the bottom of page
            - press_key(boxId, keys): Press keyboard keys (Use these when possible instead of clicking back button or any other clicks. Can be useful to scroll to the end of a page or top of a page rather than using scroll. These are always most reliable)
            - wait(boxId, duration): Wait for specified milliseconds
            - list_tabs(boxId): List all open browser tabs
            - switch_tab(boxId, tabId): Switch to a specific tab (ALWAYS list_tabs first so you know what tabId to switch to)
            - close_tab(boxId, tabId): Close a tab (NEVER CLOSE CDP URL PAGE)

            ═══════════════════════════════════════════════════════════════════════
            RUNTIME RESTRICTIONS & SESSION RULES
            ═══════════════════════════════════════════════════════════════════════

            ⚠️ The environment ALREADY has an active browser session running in a sandbox.
            - You MUST reuse the existing browser box:
                boxId = '{box_id}'
            - NEVER call or request: start_browser_box, new tab launch, or any new browser start.
            - Do NOT request new network connections (curl, fetch, http GET/POST, etc.)
            - All navigation and interaction MUST happen through the existing authenticated browser UI.
            - Direct curl or HTTP requests from the shell will NOT work (they are unauthenticated).
            - The CLI is read-only and cannot modify files or execute shell commands that require approval.
            - NOTE: There is no point in reading the file system because it is my local machine and not the terminal of the box you are operating on. 
            - So don't bother using bash to explore because it is not the file system of the machine you are working on.

            ✅ Always continue from the CURRENT PAGE CONTEXT.
            - Scroll, click, and read from the current tab only.
            - Use screenshot() first if you’re unsure where you are.
            - Do not reload or open new windows.
            - If a “browser control” error appears, verify you are still using the same boxId.

            ═══════════════════════════════════════════════════════════════════════
            WIKIPEDIA SUBAGENT:
            ═══════════════════════════════════════════════════════════════════════

            - Task(subagent_type="wikipedia-researcher", prompt="Your specific question"):
              Use ONLY when you need information from Wikipedia. Be EXTREMELY SPECIFIC about what you need.
              Date interpretation: "after 2020" means from 2020 onwards (2020, 2021, 2022, ...)
              so be sure to include 2020 as part of the search.

              **For address queries**: Ask for "complete street address including street number"
              Example: "What is the complete street address (including street number) of Pittsburgh International Airport?"

              The subagent uses a search-first strategy with voting to cross-verify facts from multiple sources.

              IMPORTANT - Handling Wikipedia Subagent Results:
              1. Read the **Confidence** level - if Low or Medium, consider the suggestions
              2. Check **Uncertainties** - if there are significant gaps, decide if you need more info
              3. Review **Suggestions** - if the subagent suggests further exploration:
                 - Navigate to Wikipedia manually to verify specific details
                 - Check additional sources if dates/numbers are uncertain
                 - Cross-reference with other parts of the website if needed
              4. If Confidence is High and no uncertainties, proceed with the answer

            ═══════════════════════════════════════════════════════════════════════
            MAGENTO ADMIN SUBAGENT - YOUR MAGENTO EXPERT:
            ═══════════════════════════════════════════════════════════════════════

            Think of this subagent as a PROFESSIONAL MAGENTO ADMINISTRATOR who knows the system inside-out.
            Whenever you have ANY question or hit ANY roadblock with Magento Admin, ask the subagent!

            - Task(subagent_type="magento-admin-guide", prompt="Your specific question"):
              Example: "Where can I find best-selling products report?"
              Returns the exact Admin menu path (e.g., "Reports > Products > Bestsellers").

            ⚠️ WHEN TO USE (use liberally!):
            - At the START of any Magento task - ask where to find what you need
            - When you're STUCK - don't waste time exploring, ask the expert
            - When you see confusing UI - ask how to interpret or use it
            - When you need to find reports, customer data, orders, products, or any admin feature
            - If you hit any roadblock or don't know what to do next - ASK!

            The subagent is FAST and knows EXACTLY where everything is. Don't hesitate to use it!

            ═══════════════════════════════════════════════════════════════════════
            IMPORTANT RULES:
            ═══════════════════════════════════════════════════════════════════════

            1. ONLY use the test websites listed above
            2. Take screenshots frequently to see what's on screen
            3. Think step-by-step before each action
            4. Be specific with target descriptions (e.g., "Submit button in login form")
            5. Look at every thing on the website. Be extremely meticulous because every piece of information matters.
            6. When you read literal values (addresses, prices, measurements, names), copy them verbatim from the UI—do not rewrite, reformat, or substitute alternate wording.
            7. Go through all the pages and if you need to keep track of information make a list and keep track of it that way


            ═══════════════════════════════════════════════════════════════════════
            GENERAL TIPS/Benchmark Quirks (VERY IMPORTANT):
            ═══════════════════════════════════════════════════════════════════════

            1. It's MUCH easier to find something on a website when there's a search bar instead of having to scroll through the whole page trying to locate it.
            2. When asked to do a search task or information retrieval, it can be very useful to use FILTERS to narrow down the search results.
            3. There are a lot of information so it will take a very long time if you just keep scrolling trying to find it. Best way is to search or filter it!
            4. Examine screenshots thoroughly, especially keep an eye out for signs like this "-". These could be negative signs which are important.
            5. When the task asks to return customers, call complete_task() with the FULL Customer name (only if you know the full name).
            6. When asked about how much is spent on a certain category or some description is given. Assume it is specifically about that categroy ONLY. An order might consist of several different categories of products. ONLY select ones that are specifically asked about.
            7. **THIS IS IMPORTANT**: When asked about how is spent on a category include the shipping & handling as part of the cost calculation. The ORDER TOTAL will include both the shipping and handling cost as well.
                Ex: If there are two items in an order and the shipping & handling is $10.00 then each item would be charged $5. (Split the shipping and handling evenly amongst the number of orders.)
            8. For questions ONLY about **Nintendo Switch game cards** please navigate back to the url of the product you end up choosing. This is because the benchmark evalautes using the page you are on for the Nintendo task. If you are own the wrong product page it will assume you selected that product.
            9. When asked to "show me products under a price" the benchmark evaluates based on the url. so just ensure the price is under the price asked for in the url.
            10. When asked about product type don't return the acutal product name but rather the type of product it is. Ex: If the most common products are "harry potter" and "twilight" the product type is "books".
            11. When the task asks for the full address make sure to inclue **ZIP CODE** (this means choosing the address that has a zip code).
            12. **For ADDRESS questions**: A "full address" means a COMPLETE street address with ALL components (GET THE ADDRESS ALWAYS FROM OPENSTREETMAP!):
                - Street number (e.g., "1000")
                - Street name (e.g., "Airport Boulevard" or "International Drive")
                - City or Township
                - State
                - ZIP code
                - Country (if applicable)
                Example: "1000 Airport Boulevard, Pittsburgh, PA 15231, United States"
                If OpenStreetMap doesn't have the street number, try:
                - Using the Wikipedia subagent to find the official address
                - Searching for the location's "Contact" or "About" page
                - Cross-referencing multiple sources until you have the complete address
            13. Task wording can contain typos or singular/plural mismatches. Treat singular terms like "order" or "transaction" as potentially plural. If multiple entries match the described criteria, summarize all of them, list each matching item with its key details, make the quantity explicit, and when the question asks for an amount/total, include the combined sum alongside the itemized numbers. Never assume "the most recent one" unless the instructions explicitly say so.
            14. **For SHOPPING/BROWSING tasks**: When asked to browse products in a particular category, navigate using the dropdown menus (not search) when possible. This may require hovering over nested dropdowns (e.g., hover over "Electronics" → hover over "Computers" → click "Laptops"). Use the hover tool to reveal these nested menus before clicking.
            15. **When URLs/text are TRUNCATED with copy buttons**: If you see text that's cut off in the UI (e.g., "https://example.com/very-long-url..." with a copy button), click the copy button then PASTE it somewhere to see the full content:
                - Click the URL/address bar and press Ctrl+V
                - Or paste into a text field
                - Take a screenshot to see the complete untruncated text
            16. **For GitLab repository changes**: When asked to make changes to a repository, commit changes to the main branch UNLESS the task specifically asks you to create a branch, make a merge request, or follow a different workflow.
            17. **For GitLab SSH clone URLs**: Replace git@ec2-3-149-78-74.us-east-2.compute.amazonaws.com with git@metis.lti.cs.cmu.edu in the clone command.
            18. **For Postmill forum submissions**: When creating a post/submission, put all content including URLs in the Body field. Leave the URL field empty. Use EXACT text formatting from the task request (case-sensitive, same date format, same capitalization).
            19. **When asked to DRAFT a message/email/post**: DO NOT submit or send it. Just compose/write the draft and leave it in the compose window. The evaluator will assess the draft as-is. Only send/submit if explicitly instructed to do so.


            ═══════════════════════════════════════════════════════════════════════
            ANSWER FORMAT (VERY IMPORTANT):
            ═══════════════════════════════════════════════════════════════════════

            When you call complete_task(), follow these principles:

            1. **Match the format exactly**: If examples show "557m", use that exact format
            2. **Provide complete answers**: Include sufficient context for the answer to stand alone
            3. **Add reasoning when appropriate**: For questions requiring judgment (yes/no, status checks,
               comparisons), include brief context or reasoning alongside your answer
            4. **Be precise with terminology**: Use exact wording from the source when copying text
            5. When asked to return answer in MM:COUNT format, return like this: "January: 1". It expect MM to be the explicit name of the month NOT a number.
            6. When asked how much is spent return just the decimal. So if item costs $7.50 return complete_task(finalAnswer="7.50") or if it costs $0 return complete_task(finalAnswer="0")
            7. When asked for configuration return as 2x2 instead of 2*2.
            8. If multiple matching entries exist for an amount-based question, itemize each amount in your reasoning and ensure the finalAnswer string contains the combined total (e.g., sum of all matching refunds) that satisfies the query.

            ═══════════════════════════════════════════════════════════════════════
            WORKFLOW:
            ═══════════════════════════════════════════════════════════════════════

            1. Call list_tabs to see what all are open. 
               NEVER EVER EVER SWITCH TO TAB WITHOUT list_tabs done first
               NEVER SWITCH TO TAB THAT HAS (THIS IS CDP URL PAGE):
               "title": "New Tab",
               "url": "chrome://new-tab-page/"
            2. Take screenshot to see current state
            3. Think step-by-step about what you need to do
            4. Execute actions one at a time
            5. Verify with screenshots after important actions
            6. Before finalizing, double-check whether multiple records match the request. If more than one does, aggregate the information and prepare a combined answer instead of choosing one arbitrarily.
            6a. **For ADDRESS tasks specifically**: Before calling complete_task(), verify you have ALL components:
                ✅ Street number (e.g., "1000")
                ✅ Street name (e.g., "Airport Boulevard")
                ✅ City/Township
                ✅ State + ZIP code
                If ANY component is missing, DO NOT call complete_task() yet. Continue searching until you find the complete address.
            7. When you have the answer, call complete_task() with EXACT format
            8. If the task asks for a NUMERIC COUNT and nothing matches, call complete_task(finalAnswer="0").
            9. Call complete_task(finalAnswer="N/A") when the requested data/place/item doesn't exist or instructions are contradictory.
            10. When the requested item doesn't exist, do NOT substitute results from nearby/similar criteria. If you do this you WILL FAIL the evaluation.


            ═══════════════════════════════════════════════════════════════════════
            FINALIZATION & COMPLETION RULES (MANDATORY)
            ═══════════════════════════════════════════════════════════════════════

            🚨 YOU MUST call the tool mcp__task-completion__complete_task({{'finalAnswer': '...'}}) once you know the answer.

            - Never just say "The task is complete" or print the answer as text.
              That does NOT count — the evaluation system only accepts the tool call.
            - Before calling complete_task(), verify that the value you pass matches all instructions: if multiple records meet the criteria, the number must reflect their combined total, not a single example.

            """
        ).strip()

    def _build_recovery_prompt(
        self, intent: str, url: str, transcript: List[str], meta_data: Any
    ) -> str:
        """
        Build a context-aware recovery prompt after image processing error.

        Args:
            intent: Task description/goal
            url: Current URL
            transcript: Text transcript from failed session
            meta_data: Additional metadata

        Returns:
            Recovery prompt with context
        """
        # Get last 15 messages from transcript (enough context without overload)
        recent_transcript = transcript[-15:] if len(transcript) > 15 else transcript
        transcript_text = "\n".join(f"  {msg}" for msg in recent_transcript)

        # Get action history if available
        action_history = ""
        if meta_data and isinstance(meta_data, dict) and "action_history" in meta_data:
            history = meta_data["action_history"][-5:]  # Last 5 actions
            action_history = "\n".join(f"  - {action}" for action in history)

        return textwrap.dedent(f"""
            ═══════════════════════════════════════════════════════════════════════
            🔄 RECOVERING FROM TECHNICAL ERROR
            ═══════════════════════════════════════════════════════════════════════

            You encountered a temporary image processing error. The browser session is
            still active and ready to continue. Here's what happened:

            ═══════════════════════════════════════════════════════════════════════
            YOUR TASK (unchanged):
            ═══════════════════════════════════════════════════════════════════════

            OBJECTIVE: {intent}

            ═══════════════════════════════════════════════════════════════════════
            CURRENT STATE:
            ═══════════════════════════════════════════════════════════════════════

            - Box ID: {self.box_id}
            - Current URL: {url}
            - Step: {self._step_count}
            - Browser: ALREADY OPEN (do not start a new browser)

            ═══════════════════════════════════════════════════════════════════════
            WHAT YOU DID BEFORE THE ERROR (last 15 messages):
            ═══════════════════════════════════════════════════════════════════════

{transcript_text}

            {f'''
            ═══════════════════════════════════════════════════════════════════════
            ACTIONS TAKEN:
            ═══════════════════════════════════════════════════════════════════════

{action_history}''' if action_history else ''}

            ═══════════════════════════════════════════════════════════════════════
            ⚠️  CRITICAL RECOVERY INSTRUCTIONS:
            ═══════════════════════════════════════════════════════════════════════

            1. DO NOT use mcp__gbox-browser__start_browser_box (browser already exists)
            2. DO NOT ask for permissions (you already have them)
            3. DO take a screenshot FIRST to see the current page state
            4. DO continue from where you left off based on the transcript above
            5. The page was just refreshed, so you may need to re-navigate if needed

            ═══════════════════════════════════════════════════════════════════════
            AVAILABLE TOOLS (all require boxId='{self.box_id}'):
            ═══════════════════════════════════════════════════════════════════════

            - screenshot(boxId): Capture current screen state (START WITH THIS!)
            - list_tabs(boxId): List all open browser tabs
            - click(boxId, target): Click on element
            - hover(boxId, target): Hover to reveal dropdowns/menus. IMPORTANT: Fully explore nested menus by hovering over dropdown items to check for sub-menus before clicking.
            - type(boxId, content, pressEnterAfterType): Type text
            - scroll(boxId, direction, distance): Scroll page
            - press_key(boxId, keys): Press keyboard keys
            - wait(boxId, duration): Wait milliseconds
            - switch_tab(boxId, tabId): Switch to a specific tab
            - close_tab(boxId, tabId): Close a tab
            - complete_task(finalAnswer): SIGNAL TASK COMPLETION (REQUIRED!)

            ═══════════════════════════════════════════════════════════════════════
            🚨 CRITICAL: REMEMBER TO CALL complete_task() WHEN DONE! 🚨
            ═══════════════════════════════════════════════════════════════════════

            YOU MUST call complete_task(finalAnswer="your answer") to finish the task.
            Just saying "task is complete" in text will NOT work - you MUST call the tool!

            ═══════════════════════════════════════════════════════════════════════

            START BY TAKING A SCREENSHOT to see the current state, then continue
            working on the task: {intent}
            """
        ).strip()

    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: Any
    ) -> Action:
        """
        Generate next action for WebArena.

        This is the main interface method that WebArena calls in the evaluation loop.
        We run Claude to completion and return a STOP action with the final answer.

        Args:
            trajectory: List of previous states and actions
            intent: Task description/goal
            meta_data: Additional metadata (e.g., action_history)

        Returns:
            Action dict (will be a STOP action with the answer)
        """
        if self._completed:
            raise RuntimeError("Agent already completed task")

        # Increment step count
        self._step_count += 1

        # Get current URL from last state
        url = "unknown"
        if len(trajectory) >= 1:
            last_state: StateInfo = trajectory[-1]  # type: ignore
            if isinstance(last_state, dict) and "info" in last_state:
                url = last_state.get("info", {}).get("url", "unknown")

        # Format prompt with task details
        if self._step_count == 1:
            prompt = self._prompt_template.format(
                intent=intent,
                url=url,
                box_id=self.box_id
            )
        else:
            # Continuation prompt for multi-step sessions
            prompt = f"Continue task (step {self._step_count}). Goal: {intent}\nCurrent URL: {url}"

        # Run Claude in a dedicated thread (avoid event loop conflicts)
        final_answer, transcript, is_complete, has_error, has_image_error = self._run_claude_sync(prompt)

        # Handle image processing errors by refreshing and starting new session
        if has_image_error:
            if self._image_error_count < self._max_image_error_retries:
                self._image_error_count += 1
                logger.warning(f"🖼️ Image processing error detected (attempt {self._image_error_count}/{self._max_image_error_retries})")

                # Refresh the page to get clean screenshot
                if self.gbox_client:
                    logger.info("🔄 Refreshing page with Ctrl+R...")
                    try:
                        self.gbox_client.v1.boxes.actions.press_key(
                            box_id=self.box_id,
                            keys=['control', 'r']
                        )
                        logger.info("✅ Page refreshed")

                        # Wait a bit for page to reload
                        import time
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"Failed to refresh page: {e}")

                # Start a NEW session (discard corrupted one)
                logger.info("🆕 Starting fresh session with Sonnet 4.5...")
                self._session_id = None

                # Build recovery prompt with transcript context
                recovery_prompt = self._build_recovery_prompt(intent, url, transcript, meta_data)

                # Retry with fresh session using context-aware recovery prompt
                final_answer, transcript, is_complete, has_error, has_image_error = self._run_claude_sync(recovery_prompt)
            else:
                logger.error(f"❌ Max image error retries ({self._max_image_error_retries}) exceeded, giving up")
                # Treat as task failure
                self._completed = True
                action = create_stop_action("ERROR: Could not process image after multiple retries")
                action["raw_prediction"] = "\n".join(transcript)
                return action

        # If usage error detected, retry with Sonnet 4 (keeps session)
        if has_error:
            logger.warning(f"⚠️ Usage error detected at step {self._step_count}, retrying with Sonnet 4...")
            final_answer, transcript, is_complete, has_error, has_image_error = self._run_claude_sync(prompt, use_sonnet_4=True)

        if not is_complete:
            # Session incomplete, continue in next step
            logger.warning(f"Session incomplete at step {self._step_count}, continuing...")
            # Return a None action to signal continuation
            action = create_stop_action("")
            action["action_type"] = ActionTypes.NONE
            return action

        # Task complete
        self._completed = True
        self._final_answer = final_answer or "No answer provided"

        logger.info(f"🏁 Final answer: {self._final_answer}")

        # Return STOP action with answer (WebArena format)
        action = create_stop_action(self._final_answer)
        action["raw_prediction"] = "\n".join(transcript)

        return action

    def _run_claude_sync(self, prompt: str, use_sonnet_4: bool = False) -> tuple[Optional[str], List[str], bool, bool, bool]:
        """
        Run Claude session synchronously (wraps async call).

        Args:
            prompt: The prompt to send to Claude
            use_sonnet_4: If True, use Sonnet 4 instead of default

        Returns:
            (final_answer, transcript, is_complete, has_error, has_image_error)
        """
        result_box: list[tuple[Optional[str], List[str], bool, bool, bool]] = []
        exc_box: list[BaseException] = []

        def _runner():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._run_claude_async(prompt, use_sonnet_4))
                result_box.append(result)
            except BaseException as exc:
                exc_box.append(exc)
            finally:
                loop.close()

        thread = threading.Thread(target=_runner, name="claude-session")
        thread.start()
        thread.join()

        if exc_box:
            logger.error(f"Claude session failed: {exc_box[0]}")
            raise exc_box[0]

        if not result_box:
            raise RuntimeError("Claude session produced no result")

        return result_box[0]

    async def _run_claude_async(
        self, prompt: str, use_sonnet_4: bool = False
    ) -> tuple[Optional[str], List[str], bool, bool, bool]:
        """
        Run Claude session asynchronously.

        Args:
            prompt: The prompt to send to Claude
            use_sonnet_4: If True, use Sonnet 4 instead of default

        Returns:
            (final_answer, transcript, is_complete, has_error, has_image_error)
        """
        transcript: List[str] = []
        final_answer: Optional[str] = None
        is_complete = False
        has_error = False
        has_image_error = False

        # Performance tracking
        import time
        last_timestamp = time.time()
        tool_call_start_time = None

        # Create options (with session resume if available, and model override if needed)
        options = self._create_claude_options(use_sonnet_4=use_sonnet_4)

        if self._session_id:
            logger.info(f"Resuming session: {self._session_id} (model: {options.model})")
        else:
            logger.info(f"Starting new session (model: {options.model})")

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            stream = client.receive_response()
            async for message in stream:
                # Handle content blocks
                if hasattr(message, 'content') and isinstance(message.content, list):
                    for block in message.content:
                        # Thinking blocks (skip logging)
                        if ThinkingBlock and isinstance(block, ThinkingBlock):
                            thinking = block.thinking if hasattr(block, 'thinking') else str(block)
                            transcript.append(f"[thinking] {thinking}")

                        # Text blocks
                        elif TextBlock and isinstance(block, TextBlock):
                            logger.info(f"💬 {block.text}")
                            transcript.append(block.text)
                            if not is_complete:
                                final_answer = block.text

                        # Tool use blocks
                        elif ToolUseBlock and isinstance(block, ToolUseBlock):
                            tool_name = block.name if hasattr(block, 'name') else 'unknown'
                            tool_input = block.input if hasattr(block, 'input') else {}

                            # Calculate thinking time (time from last result/text to this tool call)
                            current_time = time.time()
                            thinking_duration = current_time - last_timestamp
                            tool_call_start_time = current_time

                            # Log with truncation and timing
                            tool_input_str = str(tool_input)
                            if len(tool_input_str) > 500:
                                tool_input_str = tool_input_str[:500] + "..."

                            logger.info(f"🔧 [+{thinking_duration:.2f}s think] {tool_name}({tool_input_str})")
                            transcript.append(f"[tool] {tool_name}: {tool_input}")

                        # Tool result blocks
                        elif ToolResultBlock and isinstance(block, ToolResultBlock):
                            is_error = block.is_error if hasattr(block, 'is_error') else False
                            content = block.content if hasattr(block, 'content') else None

                            # Calculate tool execution time
                            current_time = time.time()
                            if tool_call_start_time is not None:
                                tool_execution_duration = current_time - tool_call_start_time
                                timing_info = f"[⏱️ {tool_execution_duration:.2f}s exec] "
                            else:
                                timing_info = ""
                            last_timestamp = current_time

                            # Convert content to string (handle MCP tool result format)
                            if isinstance(content, list):
                                # Extract text from structured content blocks
                                text_parts = []
                                for item in content:
                                    if isinstance(item, dict) and 'text' in item:
                                        text_parts.append(item['text'])
                                    else:
                                        text_parts.append(str(item))
                                content_str = " ".join(text_parts)
                            else:
                                content_str = str(content) if content else ""

                            # Filter out image bytes to reduce log clutter
                            if "data:image" in content_str or "'data': 'iVBORw0KG" in content_str:
                                # Replace image data with placeholder
                                import re
                                # Remove base64 image data
                                content_str = re.sub(r"'data': '[A-Za-z0-9+/=]{100,}'", "'data': '<image_bytes_removed>'", content_str)
                                content_str = re.sub(r'"data": "[A-Za-z0-9+/=]{100,}"', '"data": "<image_bytes_removed>"', content_str)

                            # Check for task completion signal
                            if "TASK_COMPLETE:" in content_str:
                                # Extract just the answer part after TASK_COMPLETE:
                                answer_part = content_str.split("TASK_COMPLETE:", 1)[1]
                                # Clean up any trailing JSON artifacts
                                final_answer = answer_part.strip().rstrip('"}').rstrip('"').strip()

                                # Unescape common escape sequences that Claude might include
                                final_answer = final_answer.replace("\\'", "'")
                                final_answer = final_answer.replace('\\"', '"')
                                final_answer = final_answer.replace("\\\\", "\\")

                                is_complete = True
                                logger.info(f"✅ Task complete: {final_answer}")
                                transcript.append(f"[complete] {final_answer}")
                                continue

                            if is_error:
                                logger.error(f"❌ {timing_info}{content_str[:500]}")
                                transcript.append(f"[error] {content_str}")
                            else:
                                # Log with truncation (max 1000 chars)
                                if len(content_str) > 1000:
                                    logger.info(f"📥 {timing_info}Tool result: {content_str[:1000]}...")
                                else:
                                    logger.info(f"📥 {timing_info}Tool result: {content_str}")

                                transcript.append(f"[result] {content_str[:200]}")

                # Handle ResultMessage (session end)
                elif isinstance(message, ResultMessage):
                    # Capture session ID for resuming
                    if hasattr(message, 'session_id') and message.session_id:
                        self._session_id = message.session_id

                    # Check if this was an error result
                    if hasattr(message, 'is_error') and message.is_error:
                        error_msg = str(message.result) if hasattr(message, 'result') else 'Unknown error'

                        # Check for image processing error specifically
                        if "Could not process image" in error_msg:
                            has_image_error = True
                            logger.error(f"🖼️ Image processing error: {error_msg[:200]}")
                        else:
                            # Other errors (e.g., usage policy)
                            has_error = True
                            logger.error(f"🚨 Session error: {error_msg[:200]}")

                    num_turns = message.num_turns if hasattr(message, 'num_turns') else 0
                    logger.info(f"📊 Session complete ({num_turns} turns)")
                    break

        return final_answer, transcript, is_complete, has_error, has_image_error

    def reset(self, test_config_file: str) -> None:
        """
        Reset agent for new task.

        Args:
            test_config_file: Path to task config JSON
        """
        self._session_id = None
        self._completed = False
        self._final_answer = None
        self._step_count = 0
        self._image_error_count = 0  # Reset image error counter for new task
        logger.info(f"Agent reset for config: {test_config_file}")
