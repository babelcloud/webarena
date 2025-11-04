# From Vision to Action — Towards General-Purpose GUI Agents

## Introduction

<img width="1779" height="980" alt="output (1)" src="https://github.com/user-attachments/assets/11f33f8e-c5e0-443b-8c71-d22e0fbece2b" />



<br></br>

At GBOX, we've demonstrated how the right tools can significantly enhance the reliability of autonomous web agents. By integrating Claude Code with the GBOX MCP, our system achieved a 67.98% task success rate on WebArena, a comprehensive benchmark comprising 812 diverse web automation tasks across various websites and applications. This benchmark serves as a rigorous validation environment, and these results showcase how GBOX enables agents to move beyond brittle, rule-based automation toward robust, production-ready systems capable of handling the complexity of modern web applications.


## Why Claude Code + GBOX Made the Difference
### GBOX MCP

Traditional web automation often relies on selector-based interactions using element IDs extracted from the DOM tree (e.g., click(bid='237'), where 'bid' stands for browser ID). This approach fundamentally does not scale to complex, real-world websites. Modern web applications contain hundreds or thousands of interactive elements, resulting in massive DOM trees that overwhelm agents with token limits. Element IDs like 'a12' or '237' provide no information about what they represent or where they appear on the page, forcing agents to reconstruct the entire UI from a flat list of meaningless numbers. [GBOX](https://docs.gbox.ai/api-reference/box/create-linux-box) supports both coordinate-based input and semantic, natural-language control, giving developers flexibility to choose the modality best suited to the task.

The GBOX MCP provides a semantic, natural-language interface that allows AI agents to describe what they want to interact with using vision-based targeting. Instead of parsing through hundreds of element IDs, agents simply describe the target in natural language and the system uses visual recognition to locate it. This approach scales to complex websites, remains robust across layout changes, and produces human-readable automation code.

The MCP exposes a wide range of control primitives:
```
mcp__gbox-browser__screenshot
mcp__gbox-browser__wait
mcp__gbox-browser__click
mcp__gbox-browser__type
mcp__gbox-browser__long_press
mcp__gbox-browser__drag
mcp__gbox-browser__scroll
mcp__gbox-browser__hover
mcp__gbox-browser__press_key
mcp__gbox-browser__list_tabs
mcp__gbox-browser__switch_tab
mcp__gbox-browser__close_tab
```

Each action is issued in natural, grounded language that reflects real-world user behavior:
```python
click(target="SAVE button at bottom of form")
type(content="5 orders placed")
scroll(direction="up", distance="medium")
```

In contrast, traditional Playwright-based automation requires agents to parse massive DOM trees and work with element IDs that tell you nothing:
```python
click(bid='237')  # What is this? Where is it?
fill(bid='a12', value="example text")  # No context
select_option(bid='c48', ["red", "green"])  # Just a number
```

On complex websites with hundreds of elements, this approach breaks down as agents struggle to map IDs to actual UI components while staying within token limits.
### Vision-Based Targeting

GBOX MCP uses vision-based element detection instead of relying on DOM structure or accessibility trees. When an agent issues a command like `click(target="SAVE button at bottom of form")`, the system uses visual recognition to locate the target on screen, similar to how a human user would find it.

This approach provides several advantages:
- Works across different browsers and screen resolutions without modification
- Continues to function when websites update their HTML structure
- No need to parse or maintain mappings of hundreds of element IDs
- Automation code remains human-readable and easy to understand 

### Claude Code

We used Claude Code not just as a coding assistant, but as a fully capable reasoning agent with strong tool-use abilities. Claude's ability to interpret natural language, plan multi-step actions, and adapt on the fly made it an excellent companion for GBOX MCP.

Claude Code handled complete workflows through GBOX's interface: navigating websites, entering text, clicking elements, scrolling, taking screenshots, and reasoning about visual feedback to accomplish complex web automation tasks.

With GBOX MCP providing vision-based control and Claude Code supplying the reasoning and planning, AI agents can now perform multi-step web automation that's robust, adaptable, and easy to understand.

## Prompt
<pre>
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
</pre>

## Error Handling and Benchmark Limitations

### Model Fallback Strategy
For the benchmark, we used Sonnet 4.5 as our primary model. However, some tasks triggered usage policy issues. To handle this, we implemented an automatic fallback to Sonnet 4, which has more relaxed guardrails. The session persists during the switch, allowing Sonnet 4 to continue the task without losing context, ensuring smooth task execution even when content restrictions are encountered.

### Benchmark Limitations
While WebArena provides a comprehensive testing environment, we identified several limitations in the benchmark's evaluation methodology:

1. **URL-Based Validation**: The benchmark often relies on exact URL matching for validation, which can be problematic. For example, a task might ask to filter women's shoes by price ($0-25), but different navigation paths to the same filtered results can produce different URLs. This leads to false negatives when the task is completed correctly but through a different navigation flow. A more robust approach would be to validate against the actual DOM state or rendered content rather than just the URL, as this would better reflect whether the user's intent was satisfied regardless of the specific navigation path taken.

2. **Vague Task Descriptions**: Some tasks contain ambiguous or vague instructions that don't clearly specify the expected outcome. These unclear requirements test the agent's ability to interpret instructions rather than its web navigation or GUI interaction capabilities.

3. **Inconsistent Validation**: There are several tasks which do a fuzzy match or exact string match. This results in tasks failing because an agent might respond with "7 minutes" which doesn't match the validator's answer of "7 min". The inconsistent handling of formats causes unnecessary task failures.

Despite these limitations, our approach with GBOX MCP demonstrates robust performance by handling these challenges through careful prompt engineering and adaptive behavior strategies.

## How to Run WebArena Benchmark with GBOX MCP

1. Go to [GBOX.ai](https://gbox.ai/) and create a Linux box.
2. Set up the [GBOX Browser MCP server](https://www.npmjs.com/package/@gbox.ai/mcp-server).
3. Set up the task completion server using the included [task_completion_mcp.py](https://github.com/babelcloud/webarena/blob/main/task_completion_mcp.py) to register the local MCP tool. This enables Claude to signal the benchmark when a task is completed.

4. Run the scaling script to optimize screenshots for Claude's image processing:
   ```bash
   python scale.py
   ```
   This sets the browser to 80% scaling to ensure screenshots stay within Claude's image dimension limits.

5. Run the benchmark using the provided parallel execution script:
   ```bash
   ./gbox_parallel.sh START_INDEX END_INDEX RESULTS_DIR
   ```
   Example:
   ```bash
   ./gbox_parallel.sh 0 100 results_run1
   ```
   The script will automatically distribute tasks across 4 pre-configured GBOX instances. You can monitor progress using:
   ```bash
   tmux attach -t webarena_gbox
   ```


