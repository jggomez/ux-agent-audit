import os
import shutil
import pytest
from unittest.mock import MagicMock, patch

from ux_audit.agent.hooks import AuditToolErrorHook, AuditCompactionHook, AuditPostToolCallHook


@pytest.mark.asyncio
async def test_audit_tool_error_hook_returns_recovery_message() -> None:
    """Test that the tool error hook returns a recovery guidance message for the agent."""
    hook = AuditToolErrorHook()
    mock_context = MagicMock()
    test_exception = Exception("Playwright element click timeout")

    recovery_message = await hook.run(mock_context, test_exception)

    assert recovery_message is not None
    assert "[TOOL ERROR]" in recovery_message
    assert "Playwright element click timeout" in recovery_message
    assert "Please retry using an alternative selector" in recovery_message


@pytest.mark.asyncio
async def test_audit_compaction_hook() -> None:
    """Test that compaction hook executes without raising errors."""
    hook = AuditCompactionHook()
    mock_context = MagicMock()
    
    with patch("ux_audit.agent.hooks.logger.info") as mock_info:
        await hook.run(mock_context, "compaction data")
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_post_tool_call_hook_ignored_tool() -> None:
    """Test that non-screenshot/mcp tools are ignored by PostToolCallHook."""
    hook = AuditPostToolCallHook()
    mock_context = MagicMock()
    mock_data = MagicMock()
    mock_data.name = "browser_click"  # Ignored tool name

    with patch("os.getcwd") as mock_getcwd:
        await hook.run(mock_context, mock_data)
        mock_getcwd.assert_not_called()


@pytest.mark.asyncio
async def test_post_tool_call_hook_screenshot_mcp_folder_not_exists() -> None:
    """Test that hook handles missing playwright-mcp folder gracefully."""
    hook = AuditPostToolCallHook()
    mock_context = MagicMock()
    mock_data = MagicMock()
    mock_data.name = "browser_screenshot"

    with patch("os.getcwd", return_value="/dummy/project"), \
         patch("os.path.isdir", return_value=False), \
         patch("os.listdir") as mock_listdir:
        await hook.run(mock_context, mock_data)
        # Should check project folder and fallback absolute folder, but never listdir since both are False
        mock_listdir.assert_not_called()


@pytest.mark.asyncio
async def test_post_tool_call_hook_screenshot_success() -> None:
    """Test successful copying of a screenshot to local folder."""
    hook = AuditPostToolCallHook()
    mock_context = MagicMock()
    mock_data = MagicMock()
    mock_data.name = "call_mcp_tool"

    dummy_mcp_dir = "/dummy/project/.playwright-mcp"
    dummy_files = ["shot1.png", "other_file.txt"]

    def isdir_side_effect(path):
        return path in (dummy_mcp_dir, os.path.expanduser("~/ux_audit_screenshots"))

    def exists_side_effect(path):
        if ".playwright-mcp" in path:
            return True
        if "screenshot_1.png" in path:
            return True
        return False

    with patch("os.getcwd", return_value="/dummy/project"), \
         patch("os.path.isdir", side_effect=isdir_side_effect), \
         patch("os.listdir", return_value=dummy_files), \
         patch("os.path.getmtime", return_value=12345.6), \
         patch("os.path.exists", side_effect=exists_side_effect), \
         patch("os.makedirs") as mock_makedirs, \
         patch("shutil.copy2") as mock_copy, \
         patch.dict(os.environ, {}, clear=True):
         
        await hook.run(mock_context, mock_data)
        
        # Verify mkdirs called on dest folder
        mock_makedirs.assert_any_call(os.path.expanduser("~/ux_audit_screenshots"), exist_ok=True)
        # Verify copied shot1.png to screenshot_2.png
        mock_copy.assert_called_once_with(
            os.path.join(dummy_mcp_dir, "shot1.png"),
            os.path.join(os.path.expanduser("~/ux_audit_screenshots"), "screenshot_2.png")
        )


@pytest.mark.asyncio
async def test_post_tool_call_hook_screenshot_artifact_success() -> None:
    """Test screenshot copying including conversation artifact directory when ANTIGRAVITY_CONVERSATION_ID is set."""
    hook = AuditPostToolCallHook()
    mock_context = MagicMock()
    mock_data = MagicMock()
    mock_data.name = "browser_screenshot"

    dummy_mcp_dir = "/dummy/project/.playwright-mcp"
    dummy_files = ["shot_latest.png"]

    def exists_side_effect(path):
        if ".playwright-mcp" in path:
            return True
        return False

    with patch("os.getcwd", return_value="/dummy/project"), \
         patch("os.path.isdir", return_value=True), \
         patch("os.listdir", return_value=dummy_files), \
         patch("os.path.getmtime", return_value=100.0), \
         patch("os.path.exists", side_effect=exists_side_effect), \
         patch("os.makedirs") as mock_makedirs, \
         patch("shutil.copy2") as mock_copy, \
         patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": "mock_conv_999"}, clear=True):
         
        await hook.run(mock_context, mock_data)
        
        # Check both copies: one for user, one for gemini artifact
        assert mock_copy.call_count == 2
        mock_copy.assert_any_call(
            os.path.join(dummy_mcp_dir, "shot_latest.png"),
            os.path.join(os.path.expanduser("~/ux_audit_screenshots"), "screenshot_1.png")
        )
        
        expected_artifact_dest = os.path.join(
            os.path.expanduser("~"),
            ".gemini",
            "antigravity-cli",
            "brain",
            "mock_conv_999",
            "screenshot_1.png"
        )
        mock_copy.assert_any_call(
            os.path.join(dummy_mcp_dir, "shot_latest.png"),
            expected_artifact_dest
        )



@pytest.mark.asyncio
async def test_post_tool_call_hook_screenshot_copy_exception_handling() -> None:
    """Test that exception raised during shutil.copy2 is caught and does not crash the hook."""
    hook = AuditPostToolCallHook()
    mock_context = MagicMock()
    mock_data = MagicMock()
    mock_data.name = "browser_screenshot"

    with patch("os.getcwd", return_value="/dummy/project"), \
         patch("os.path.isdir", return_value=True), \
         patch("os.listdir", return_value=["img.png"]), \
         patch("os.path.getmtime", return_value=1.0), \
         patch("os.path.exists", return_value=False), \
         patch("os.makedirs"), \
         patch("shutil.copy2", side_effect=IOError("Mock permission error")), \
         patch("ux_audit.agent.hooks.logger.error") as mock_log_err:
         
        # This call should complete without throwing IOError
        await hook.run(mock_context, mock_data)
        mock_log_err.assert_called_once()
