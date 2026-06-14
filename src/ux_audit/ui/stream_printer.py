"""
Console output renderer for the UX/UI Audit Agent.

Extracted from orchestrator.py via the Extract Class refactoring.
All stdout I/O lives here — the orchestrator never calls print() or
sys.stdout.write() directly. This separation means output format can
be changed (e.g., write to a file, emit JSON lines) without touching
any business logic.
"""

import asyncio
import logging
import sys
from typing import Callable, Optional

from ux_audit.core.constants import DIVIDER_CHAR, DIVIDER_WIDTH, SECTION_REASONING, SECTION_REPORT

logger = logging.getLogger(__name__)

_DIVIDER: str = DIVIDER_CHAR * DIVIDER_WIDTH


class AuditStreamPrinter:
    """
    Renders the two concurrent audit output streams to stdout:
    the agent's reasoning trace and the final Markdown report.
    Supports optional dispatch callbacks for UI integration.
    """

    async def stream_reasoning_trace(
        self,
        response: object,
        shutdown_event: asyncio.Event,
        on_thought: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Streams the agent's internal reasoning thoughts to stdout
        and forwards them to an optional callback.
        """
        self._print_section_header(SECTION_REASONING)
        try:
            async for thought in response.thoughts:  # type: ignore[union-attr]
                if shutdown_event.is_set():
                    break
                sys.stdout.write(thought)
                sys.stdout.flush()
                if on_thought:
                    try:
                        on_thought(thought)
                    except Exception as err:
                        logger.error("Error dispatching thought callback: %s", err)
        except Exception as exc:
            logger.exception("Reasoning trace stream failed")
            raise
        self._print_section_footer()

    async def stream_final_report(
        self,
        response: object,
        shutdown_event: asyncio.Event,
        on_report_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Streams the final audit report tokens to stdout, accumulates them,
        and forwards them to an optional callback.
        """
        self._print_section_header(SECTION_REPORT)
        report_chunks: list[str] = []
        try:
            async for token in response:  # type: ignore[union-attr]
                if shutdown_event.is_set():
                    break
                sys.stdout.write(token)
                sys.stdout.flush()
                report_chunks.append(token)
                if on_report_chunk:
                    try:
                        on_report_chunk(token)
                    except Exception as err:
                        logger.error("Error dispatching report chunk callback: %s", err)
        except Exception as exc:
            logger.exception("Report stream failed")
            raise
        self._print_section_footer()
        return "".join(report_chunks)

    @staticmethod
    def _print_section_header(title: str) -> None:
        """Prints a consistent section boundary with a centered title."""
        print(f"\n{_DIVIDER}")
        print(title)
        print(_DIVIDER)

    @staticmethod
    def _print_section_footer() -> None:
        """Prints the closing boundary of a section."""
        print(f"\n{_DIVIDER}\n")
