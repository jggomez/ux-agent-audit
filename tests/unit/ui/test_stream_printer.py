import asyncio
import pytest
from unittest.mock import MagicMock, patch
from ux_audit.ui.stream_printer import AuditStreamPrinter
from ux_audit.core.constants import SECTION_REASONING, SECTION_REPORT

class AsyncIterableMock:
    """A helper to mock async iterables for response thoughts and chunks."""
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
    """Mock for agent response offering thoughts and self-iteration."""
    def __init__(self, thoughts_list, chunk_list):
        self.thoughts = AsyncIterableMock(thoughts_list)
        self.chunks = chunk_list
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.chunks):
            raise StopAsyncIteration
        chunk = self.chunks[self.index]
        self.index += 1
        return chunk

@pytest.mark.asyncio
async def test_stream_reasoning_trace_success() -> None:
    printer = AuditStreamPrinter()
    thoughts = ["Thinking...", " Analyzing structure...", " Done."]
    response = MockResponse(thoughts_list=thoughts, chunk_list=[])
    shutdown_event = asyncio.Event()
    
    received_thoughts = []
    def on_thought_cb(t: str) -> None:
        received_thoughts.append(t)

    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush") as mock_flush:
        await printer.stream_reasoning_trace(response, shutdown_event, on_thought=on_thought_cb)
        
        # Verify thoughts were accumulated and printed
        assert received_thoughts == thoughts
        written_strings = [call[0][0] for call in mock_write.call_args_list]
        for t in thoughts:
            assert t in written_strings
        assert mock_flush.call_count >= len(thoughts)

@pytest.mark.asyncio
async def test_stream_reasoning_trace_shutdown() -> None:
    printer = AuditStreamPrinter()
    thoughts = ["Step 1", "Step 2", "Step 3"]
    response = MockResponse(thoughts_list=thoughts, chunk_list=[])
    shutdown_event = asyncio.Event()
    
    received_thoughts = []
    def on_thought_cb(t: str) -> None:
        received_thoughts.append(t)
        if t == "Step 2":
            shutdown_event.set()

    with patch("sys.stdout.write") as mock_write:
        await printer.stream_reasoning_trace(response, shutdown_event, on_thought=on_thought_cb)
        
        # Should stop after Step 2 because shutdown_event was set
        assert "Step 1" in received_thoughts
        assert "Step 2" in received_thoughts
        assert "Step 3" not in received_thoughts

@pytest.mark.asyncio
async def test_stream_reasoning_trace_callback_exception() -> None:
    printer = AuditStreamPrinter()
    thoughts = ["Step 1"]
    response = MockResponse(thoughts_list=thoughts, chunk_list=[])
    shutdown_event = asyncio.Event()
    
    def buggy_cb(t: str) -> None:
        raise ValueError("Oops callback error")

    with patch("ux_audit.ui.stream_printer.logger.error") as mock_log_err:
        await printer.stream_reasoning_trace(response, shutdown_event, on_thought=buggy_cb)
        # Should catch callback errors internally and log them, not raise
        mock_log_err.assert_called_once()

@pytest.mark.asyncio
async def test_stream_final_report_success() -> None:
    printer = AuditStreamPrinter()
    chunks = ["# Report", "\n## Section 1", "\nText"]
    response = MockResponse(thoughts_list=[], chunk_list=chunks)
    shutdown_event = asyncio.Event()
    
    received_chunks = []
    def on_report_cb(c: str) -> None:
        received_chunks.append(c)

    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush") as mock_flush:
        report_text = await printer.stream_final_report(response, shutdown_event, on_report_chunk=on_report_cb)
        
        assert report_text == "# Report\n## Section 1\nText"
        assert received_chunks == chunks
        written_strings = [call[0][0] for call in mock_write.call_args_list]
        for c in chunks:
            assert c in written_strings

@pytest.mark.asyncio
async def test_stream_final_report_shutdown() -> None:
    printer = AuditStreamPrinter()
    chunks = ["Chunk A", "Chunk B", "Chunk C"]
    response = MockResponse(thoughts_list=[], chunk_list=chunks)
    shutdown_event = asyncio.Event()
    
    received_chunks = []
    def on_report_cb(c: str) -> None:
        received_chunks.append(c)
        if c == "Chunk B":
            shutdown_event.set()

    report_text = await printer.stream_final_report(response, shutdown_event, on_report_chunk=on_report_cb)
    
    assert "Chunk A" in received_chunks
    assert "Chunk B" in received_chunks
    assert "Chunk C" not in received_chunks
    assert report_text == "Chunk AChunk B"

@pytest.mark.asyncio
async def test_stream_final_report_callback_exception() -> None:
    printer = AuditStreamPrinter()
    chunks = ["Chunk A"]
    response = MockResponse(thoughts_list=[], chunk_list=chunks)
    shutdown_event = asyncio.Event()
    
    def buggy_cb(c: str) -> None:
        raise ValueError("Oops callback error")

    with patch("ux_audit.ui.stream_printer.logger.error") as mock_log_err:
        await printer.stream_final_report(response, shutdown_event, on_report_chunk=buggy_cb)
        mock_log_err.assert_called_once()

class ExceptionAsyncIterable:
    def __aiter__(self):
        return self
    async def __anext__(self):
        raise RuntimeError("Mock stream read error")

class MockExceptionResponse:
    def __init__(self, thoughts_fail=False):
        if thoughts_fail:
            self.thoughts = ExceptionAsyncIterable()
        else:
            self.thoughts = AsyncIterableMock([])

    def __aiter__(self):
        return ExceptionAsyncIterable()

@pytest.mark.asyncio
async def test_stream_reasoning_trace_exception() -> None:
    printer = AuditStreamPrinter()
    response = MockExceptionResponse(thoughts_fail=True)
    shutdown_event = asyncio.Event()
    
    with pytest.raises(RuntimeError, match="Mock stream read error"):
        await printer.stream_reasoning_trace(response, shutdown_event)

@pytest.mark.asyncio
async def test_stream_final_report_exception() -> None:
    printer = AuditStreamPrinter()
    response = MockExceptionResponse(thoughts_fail=False)
    shutdown_event = asyncio.Event()
    
    with pytest.raises(RuntimeError, match="Mock stream read error"):
        await printer.stream_final_report(response, shutdown_event)

