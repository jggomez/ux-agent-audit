"""
Orchestration runtime for the UX/UI Audit Agent.

Manages the Agent session lifecycle, builds the audit prompt,
streams thoughts + tokens concurrently, and handles clean shutdown.
"""

import asyncio
import logging
import signal
import threading
from typing import Callable, Optional

from google.antigravity import Agent
from google.antigravity.types import (
    AntigravityConnectionError,
    AntigravityValidationError,
    AntigravityExecutionError,
)

from ux_audit.core.models import AuditRequest
from ux_audit.ui.stream_printer import AuditStreamPrinter
from ux_audit.agent.config import get_agent_config

logger = logging.getLogger(__name__)


# ─── Prompt Builder ───────────────────────────────────────────────────────────

def build_audit_prompt(url: str, user_stories: tuple[str, ...], hints: str = "") -> str:
    """
    Constructs the structured audit instruction prompt for the agent.

    Args:
        url: The target URL to audit.
        user_stories: Tuple of user story strings to validate against.
        hints: Optional hints or guidance for the agent.

    Returns:
        A formatted multi-line prompt string.
    """
    if user_stories:
        stories_list_str = "\n".join(f"  {i+1}. {story}" for i, story in enumerate(user_stories))
        stories_block = (
            f"User Stories and Acceptance Criteria to validate:\n{stories_list_str}\n\n"
            "CRITICAL PRIORITY: Your primary task is to follow the user flows described in these User Stories. "
            "Navigate, click, type, and verify if each user story and its acceptance criteria can be completed. "
            "In your final report, you must include the 'User Story Validation' section showing the status of each story."
        )
    else:
        stories_block = (
            "No specific User Stories or Acceptance Criteria were provided. "
            "Please perform a comprehensive, general usability, accessibility, and visual audit of the target URL, "
            "analyzing the layout, navigation, contrast, responsiveness, and interaction elements across easily navigable paths. "
            "Do NOT include the 'User Story Validation' section in your report, and proceed directly to findings."
        )

    hints_block = ""
    if hints.strip():
        hints_block = (
            f"IMPORTANT AUDIT GUIDANCE & HINTS:\n"
            f"{hints.strip()}\n\n"
            f"You MUST read and follow the audit guidance and hints provided above during your exploration and validation. "
            f"Use any provided credentials or navigate through the specific paths suggested.\n\n"
        )

    return (
        f"BEGIN AUDIT\n\n"
        f"Target URL: {url}\n\n"
        f"{hints_block}"
        f"{stories_block}\n\n"
        f"Navigate to the target URL now using your browser tools and perform "
        f"the complete UX/UI and accessibility audit. "
        f"You must generate a formal, highly detailed, and complete audit report in English. "
        f"The report must strictly contain:\n"
        f"1. Executive Summary: What was audited, target URL, and scope of validation.\n"
        f"2. Visual Execution Tree / Steps: List of all pages visited, actions taken, and visual validation of screenshots.\n"
        f"3. User Story Validation (CONDITIONAL): If User Stories were provided, list each story, status ([MET]/[PARTIALLY MET]/[NOT MET]), and detailed UX validation details.\n"
        f"4. Detailed Findings categorized by severity ([CRITICAL], [MAJOR], [MINOR]). For each finding, structure it with Heuristic & WCAG criteria, Target Element, detailed 'UX & Design Analysis', 'Technical & DOM Analysis', and specific 'Implementation & Code Recommendation'.\n"
        f"5. Page-Specific UX Recommendations: Tailored visual design, system hierarchy, typography, and flow improvements for this page.\n"
        f"6. Summary Table showing counts of findings by severity.\n\n"
        f"Proceed with the browser audit now."
    )


# ─── Shutdown Handler ─────────────────────────────────────────────────────────

def _register_shutdown_handler(shutdown_event: asyncio.Event) -> None:
    """
    Registers SIGINT and SIGTERM handlers that set a shared asyncio.Event,
    allowing the audit coroutine to detect shutdown and exit cleanly.

    Args:
        shutdown_event: The shared event to set on signal receipt.
    """
    if threading.current_thread() is not threading.main_thread():
        logger.info("Running on a background thread — skipping signal handler registration.")
        return

    loop = asyncio.get_running_loop()

    def _handle_signal(sig: signal.Signals) -> None:
        logger.warning("Received signal %s — initiating graceful shutdown...", sig.name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig)
        except NotImplementedError:
            # Fallback for platforms without signal handler support in asyncio
            pass


# ─── Main Audit Runner ────────────────────────────────────────────────────────

async def run_ux_audit(
    request: AuditRequest,
    on_thought: Optional[Callable[[str], None]] = None,
    on_report_chunk: Optional[Callable[[str], None]] = None,
    on_status_change: Optional[Callable[[str, str], None]] = None,
) -> str:
    """
    Executes the full autonomous UX/UI audit lifecycle:

    1. Registers OS signal handlers for graceful shutdown.
    2. Builds the structured audit prompt.
    3. Opens an Agent session with Playwright MCP + lifecycle hooks.
    4. Concurrently streams thoughts and final report tokens.
    5. Returns the complete report text for artifact generation.

    Args:
        request: The validated AuditRequest parameter object.
        on_thought: Optional callback invoked with each streamed thought chunk.
        on_report_chunk: Optional callback invoked with each streamed markdown token.
        on_status_change: Optional callback invoked with status key and display message.

    Returns:
        The full audit report as a Markdown string.

    Raises:
        AntigravityValidationError: On invalid configuration or API key.
        AntigravityConnectionError: On SDK/WebSocket connectivity issues.
        AntigravityExecutionError: On agent-side execution failures.
    """
    shutdown_event = asyncio.Event()
    _register_shutdown_handler(shutdown_event)

    if on_status_change:
        on_status_change("initializing", "Initializing Auditor Agent configuration...")

    prompt = build_audit_prompt(request.target_url, request.user_stories, request.hints)
    agent_config = get_agent_config(api_key=request.api_key)

    logger.info("Initializing Senior Usability & Accessibility Auditor agent...")
    logger.info("Target: %s", request.target_url)
    logger.info("User Stories: %d story/stories loaded", len(request.user_stories))

    if on_status_change:
        on_status_change("starting_browser", "Launching browser viewport via Playwright...")

    try:
        async with Agent(config=agent_config) as agent:
            logger.info(
                "Agent session active — Playwright MCP server starting via npx..."
            )
            logger.info("Sending audit request to agent...")

            if on_status_change:
                on_status_change("auditing", "Executing UX/UI and accessibility audit steps on browser...")

            response = await agent.chat(prompt)

            if shutdown_event.is_set():
                logger.warning("Shutdown requested before streaming — aborting.")
                if on_status_change:
                    on_status_change("cancelled", "Audit cancelled by user.")
                return ""

            if on_status_change:
                on_status_change("streaming", "Analyzing findings and streaming report...")

            # Use the extracted AuditStreamPrinter for presentation concerns
            printer = AuditStreamPrinter()

            # Stream thoughts and report text concurrently
            _, report_text = await asyncio.gather(
                printer.stream_reasoning_trace(response, shutdown_event, on_thought=on_thought),
                printer.stream_final_report(response, shutdown_event, on_report_chunk=on_report_chunk),
            )

            usage = response.usage_metadata
            if usage:
                logger.info(
                    "Token usage — prompt: %s | output: %s | thoughts: %s | total: %s",
                    usage.prompt_token_count,
                    usage.candidates_token_count,
                    usage.thoughts_token_count,
                    usage.total_token_count,
                )

            if on_status_change:
                on_status_change("done", "Audit completed successfully!")

            return report_text

    except AntigravityValidationError as exc:
        logger.error("Configuration error: %s", exc)
        if on_status_change:
            on_status_change("failed", f"Configuration error: {exc}")
        raise
    except AntigravityConnectionError as exc:
        logger.error("SDK connection dropped: %s", exc)
        if on_status_change:
            on_status_change("failed", f"Connection dropped: {exc}")
        raise
    except AntigravityExecutionError as exc:
        logger.error("Agent execution failed: %s", exc)
        if on_status_change:
            on_status_change("failed", f"Execution failed: {exc}")
        raise
    except asyncio.CancelledError:
        logger.warning("Audit cancelled via shutdown signal.")
        if on_status_change:
            on_status_change("cancelled", "Audit cancelled.")
        return ""
