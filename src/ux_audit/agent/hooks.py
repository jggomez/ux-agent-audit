"""
Agent lifecycle hooks for the UX/UI Audit Agent.

Extracted from orchestrator.py via the Extract Class refactoring.
Each hook class has a single responsibility: reacting to one specific
agent lifecycle event. Keeping them in a dedicated module means the
orchestrator no longer needs to change when hook behavior evolves.
"""

import logging
from typing import Any, Optional

from google.antigravity.hooks import hooks

logger = logging.getLogger(__name__)


class AuditToolErrorHook(hooks.OnToolErrorHook):
    """
    Intercepts browser tool errors and returns a structured recovery
    message to the agent instead of exposing a raw Python traceback.

    This keeps the audit session alive when a transient Playwright
    failure occurs (e.g., element not found, navigation timeout).
    The agent is guided to retry or skip rather than abort.
    """

    async def run(
        self,
        context: hooks.HookContext,
        data: Exception,
    ) -> Optional[str]:
        logger.warning("Browser tool error intercepted: %s", data)
        return (
            f"[TOOL ERROR] The previous browser action failed: {data}. "
            "Please retry using an alternative selector or approach, "
            "or skip this step and continue with the next audit action."
        )


class AuditCompactionHook(hooks.OnCompactionHook):
    """
    Fires when the SDK triggers context window compaction during a
    long audit session. Logs the event so operators can correlate
    compaction moments with potential report truncation.
    """

    async def run(self, context: hooks.HookContext, data: Any) -> None:
        logger.info(
            "Context compaction triggered — audit session exceeded compaction "
            "threshold. Report continuity may be affected for very long pages."
        )


import os

class AuditPostToolCallHook(hooks.PostToolCallHook):
    """
    Fires after every browser tool call completes successfully.
    Intercepts browser_screenshot calls and saves the images locally
    so the user can inspect the visual audit trail.
    """

    async def run(self, context: hooks.HookContext, data: Any) -> None:
        logger.info("Tool call completed: %s", data.name)
        
        # Check if the tool is the browser screenshot tool or the generic MCP caller
        tool_name = str(data.name).lower()
        if "screenshot" in tool_name or "call_mcp_tool" in tool_name:
            import shutil
            
            # The tool writes the screenshot to the project's .playwright-mcp folder
            project_dir = os.getcwd()
            playwright_mcp_dir = os.path.join(project_dir, ".playwright-mcp")
            if not os.path.exists(playwright_mcp_dir):
                # Fallback to path relative to this module's location (3 levels up from hooks.py)
                current_file_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(current_file_dir, "..", "..", ".."))
                playwright_mcp_dir = os.path.join(project_root, ".playwright-mcp")
                
            if os.path.isdir(playwright_mcp_dir):
                try:
                    png_files = [
                        os.path.join(playwright_mcp_dir, f)
                        for f in os.listdir(playwright_mcp_dir)
                        if f.endswith(".png")
                    ]
                    if png_files:
                        # Find the most recently modified png file
                        latest_file = max(png_files, key=os.path.getmtime)
                        
                        # Copy it to ~/ux_audit_screenshots
                        output_dir = os.path.expanduser("~/ux_audit_screenshots")
                        os.makedirs(output_dir, exist_ok=True)
                        
                        # Find unique filename
                        counter = 1
                        while True:
                            dest_file = os.path.join(output_dir, f"screenshot_{counter}.png")
                            if not os.path.exists(dest_file):
                                break
                            counter += 1
                            
                        shutil.copy2(latest_file, dest_file)
                        logger.info("Saved intercepted audit screenshot from %s to: %s", latest_file, dest_file)
                        
                        # If running inside an active Antigravity CLI conversation, also save as an artifact
                        conv_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
                        if conv_id:
                            artifact_dir = os.path.join(
                                os.path.expanduser("~"),
                                ".gemini",
                                "antigravity-cli",
                                "brain",
                                conv_id
                            )
                            os.makedirs(artifact_dir, exist_ok=True)
                            artifact_filepath = os.path.join(artifact_dir, f"screenshot_{counter}.png")
                            shutil.copy2(latest_file, artifact_filepath)
                            logger.info("Saved screenshot artifact to conversation: %s", artifact_filepath)
                except Exception as exc:
                    logger.error("Failed to copy screenshot: %s", exc)
