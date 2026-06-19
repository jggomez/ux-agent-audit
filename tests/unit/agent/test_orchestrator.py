import asyncio
import threading
import signal
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from google.antigravity.types import (
    AntigravityConnectionError,
    AntigravityValidationError,
    AntigravityExecutionError,
)
from ux_audit.core.models import AuditRequest
from ux_audit.agent.orchestrator import build_audit_prompt, _register_shutdown_handler, run_ux_audit


def test_build_audit_prompt_with_stories() -> None:
    """Test that the structured audit prompt is constructed correctly with user stories."""
    url = "https://my-app.com"
    stories = ("As a user I want to login", "As an admin I want to check logs")
    prompt = build_audit_prompt(url, stories)

    assert "https://my-app.com" in prompt
    assert "1. As a user I want to login" in prompt
    assert "2. As an admin I want to check logs" in prompt
    assert "BEGIN AUDIT" in prompt
    assert "User Stories and Acceptance Criteria to validate" in prompt


def test_build_audit_prompt_no_stories() -> None:
    """Test that the structured audit prompt is constructed correctly when no stories are provided."""
    url = "https://my-app.com"
    prompt = build_audit_prompt(url, ())

    assert "https://my-app.com" in prompt
    assert "No specific User Stories or Acceptance Criteria were provided" in prompt
    assert "Do NOT include the 'User Story Validation' section in your report" in prompt


def test_build_audit_prompt_with_hints() -> None:
    """Test that the structured audit prompt includes instructions/hints when provided."""
    url = "https://my-app.com"
    stories = ("As a user I want to login",)
    hints = "Use credentials test/test and bypass CAPTCHA."
    prompt = build_audit_prompt(url, stories, hints)

    assert "IMPORTANT AUDIT GUIDANCE & HINTS:" in prompt
    assert "Use credentials test/test and bypass CAPTCHA." in prompt
    assert "You MUST read and follow the audit guidance and hints" in prompt


def test_register_shutdown_handler_background_thread() -> None:
    """Verify signal handlers are skipped when run from a background thread."""
    shutdown_event = asyncio.Event()
    with patch("threading.current_thread") as mock_thread, \
         patch("asyncio.get_running_loop") as mock_loop:
        # Mock thread to not be main_thread
        mock_thread.return_value = MagicMock()
        mock_thread.return_value == threading.main_thread()  # Make unequal
        
        # We enforce it by mocking current_thread and main_thread unequal
        mock_main = MagicMock()
        mock_thread.return_value = mock_main
        with patch("threading.main_thread", return_value=MagicMock()):
            _register_shutdown_handler(shutdown_event)
            mock_loop.assert_not_called()


def test_register_shutdown_handler_main_thread_success() -> None:
    """Verify signal handlers are registered on the main thread loop."""
    shutdown_event = asyncio.Event()
    mock_loop = MagicMock()
    
    with patch("threading.current_thread", return_value=threading.main_thread()), \
         patch("asyncio.get_running_loop", return_value=mock_loop):
        _register_shutdown_handler(shutdown_event)
        
        # Verify add_signal_handler was called for SIGINT and SIGTERM
        assert mock_loop.add_signal_handler.call_count == 2
        
        # Invoke the registered handler callback to cover its code path
        call_args = mock_loop.add_signal_handler.call_args_list[0][0]
        handler_fn = call_args[1]
        handler_fn(signal.SIGINT)
        
        assert shutdown_event.is_set() is True


def test_register_shutdown_handler_main_thread_not_implemented() -> None:
    """Verify signal handler registration swallows NotImplementedError gracefully (e.g. on Windows)."""
    shutdown_event = asyncio.Event()
    mock_loop = MagicMock()
    mock_loop.add_signal_handler.side_effect = NotImplementedError()
    
    with patch("threading.current_thread", return_value=threading.main_thread()), \
         patch("asyncio.get_running_loop", return_value=mock_loop):
        # Should not raise NotImplementedError
        _register_shutdown_handler(shutdown_event)
        assert mock_loop.add_signal_handler.call_count == 2


# Helper Mock Classes for Run UX Audit Tests
class AsyncIterableMock:
    def __init__(self, items):
        self.items = items
        self.index = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item

class MockResponse:
    def __init__(self, thoughts, report_chunks, prompt_tokens=10, candidate_tokens=20):
        self.thoughts = AsyncIterableMock(thoughts)
        self.report_chunks = report_chunks
        self.index = 0
        
        # Usage metadata mock
        self.usage_metadata = MagicMock()
        self.usage_metadata.prompt_token_count = prompt_tokens
        self.usage_metadata.candidates_token_count = candidate_tokens
        self.usage_metadata.thoughts_token_count = 5
        self.usage_metadata.total_token_count = prompt_tokens + candidate_tokens + 5

    def __aiter__(self):
        return AsyncIterableMock(self.report_chunks)


@pytest.mark.asyncio
async def test_run_ux_audit_success() -> None:
    """Test successful run_ux_audit with mocked Agent and output stream."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    # Mock Response
    mock_thoughts = ["Thought A", " Thought B"]
    mock_report = ["Report Chunk A", " Report Chunk B"]
    mock_resp = MockResponse(mock_thoughts, mock_report)
    
    # Mock Agent instance and context manager
    mock_agent = MagicMock()
    mock_agent.chat = AsyncMock(return_value=mock_resp)
    
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    thoughts_received = []
    def on_thought_cb(t):
        thoughts_received.append(t)

    report_received = []
    def on_report_cb(c):
        report_received.append(c)

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()):  # Avoid registering signals
        
        report = await run_ux_audit(
            req,
            on_thought=on_thought_cb,
            on_report_chunk=on_report_cb,
            on_status_change=on_status_cb
        )
        
        assert report == "Report Chunk A Report Chunk B"
        assert thoughts_received == mock_thoughts
        assert report_received == mock_report
        
        # Verify status transitions
        status_keys = [update[0] for update in status_updates]
        assert "initializing" in status_keys
        assert "starting_browser" in status_keys
        assert "auditing" in status_keys
        assert "streaming" in status_keys
        assert "done" in status_keys


@pytest.mark.asyncio
async def test_run_ux_audit_early_shutdown() -> None:
    """Test run_ux_audit returns empty string if shutdown is triggered before streaming starts."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    mock_agent = MagicMock()
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    # Mock response
    mock_resp = MockResponse([], [])
    mock_agent.chat = AsyncMock(return_value=mock_resp)

    # We patch asyncio.Event to return an event that is pre-set
    mock_event = MagicMock(spec=asyncio.Event)
    mock_event.is_set.return_value = True

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()), \
         patch("asyncio.Event", return_value=mock_event):
        
        report = await run_ux_audit(req, on_status_change=on_status_cb)
        
        assert report == ""
        status_keys = [update[0] for update in status_updates]
        assert "cancelled" in status_keys


@pytest.mark.asyncio
async def test_run_ux_audit_validation_error() -> None:
    """Test run_ux_audit correctly handles and propagates AntigravityValidationError."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    mock_agent = MagicMock()
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    # Make chat raise Validation Error
    mock_agent.chat.side_effect = AntigravityValidationError("API key is invalid or expired")

    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()):
        
        with pytest.raises(AntigravityValidationError, match="API key is invalid or expired"):
            await run_ux_audit(req, on_status_change=on_status_cb)
            
        status_keys = [update[0] for update in status_updates]
        assert "failed" in status_keys
        assert any("Configuration error" in update[1] for update in status_updates)


@pytest.mark.asyncio
async def test_run_ux_audit_connection_error() -> None:
    """Test run_ux_audit correctly handles and propagates AntigravityConnectionError."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    mock_agent = MagicMock()
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    # Make chat raise Connection Error
    mock_agent.chat.side_effect = AntigravityConnectionError("Lost connection to WebSocket")

    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()):
        
        with pytest.raises(AntigravityConnectionError, match="Lost connection to WebSocket"):
            await run_ux_audit(req, on_status_change=on_status_cb)
            
        status_keys = [update[0] for update in status_updates]
        assert "failed" in status_keys
        assert any("Connection dropped" in update[1] for update in status_updates)


@pytest.mark.asyncio
async def test_run_ux_audit_execution_error() -> None:
    """Test run_ux_audit correctly handles and propagates AntigravityExecutionError."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    mock_agent = MagicMock()
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    # Make chat raise Execution Error
    mock_agent.chat.side_effect = AntigravityExecutionError("MCP server execution failed")

    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()):
        
        with pytest.raises(AntigravityExecutionError, match="MCP server execution failed"):
            await run_ux_audit(req, on_status_change=on_status_cb)
            
        status_keys = [update[0] for update in status_updates]
        assert "failed" in status_keys
        assert any("Execution failed" in update[1] for update in status_updates)


@pytest.mark.asyncio
async def test_run_ux_audit_cancelled_error() -> None:
    """Test run_ux_audit returns empty string when CancelledError is raised."""
    req = AuditRequest(target_url="https://google.com", user_stories=(), api_key="mykey")
    
    mock_agent = MagicMock()
    mock_agent_cm = MagicMock()
    mock_agent_cm.__aenter__ = AsyncMock(return_value=mock_agent)
    mock_agent_cm.__aexit__ = AsyncMock(return_value=False)
    
    # Make chat raise CancelledError
    mock_agent.chat.side_effect = asyncio.CancelledError()

    status_updates = []
    def on_status_cb(key, msg):
        status_updates.append((key, msg))

    with patch("ux_audit.agent.orchestrator.Agent", return_value=mock_agent_cm), \
         patch("threading.current_thread", return_value=MagicMock()):
        
        report = await run_ux_audit(req, on_status_change=on_status_cb)
        
        assert report == ""
        status_keys = [update[0] for update in status_updates]
        assert "cancelled" in status_keys
