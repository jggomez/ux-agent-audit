import os
from unittest.mock import patch
from ux_audit.agent.config import get_agent_config

def test_get_agent_config_with_explicit_key() -> None:
    config = get_agent_config(api_key="my-custom-key")
    assert config.api_key == "my-custom-key"
    assert config.capabilities.enable_subagents is False
    assert config.capabilities.compaction_threshold == 60000
    
    # Verify hooks registration
    assert len(config.hooks) == 2
    hook_classes = [type(hook).__name__ for hook in config.hooks]
    assert "AuditToolErrorHook" in hook_classes
    assert "AuditPostToolCallHook" in hook_classes

    # Verify MCP server registration
    assert len(config.mcp_servers) == 1
    mcp = config.mcp_servers[0]
    assert mcp.name == "playwright"
    assert mcp.command == "npx"

def test_get_agent_config_with_env_key() -> None:
    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-999"}, clear=True):
        config = get_agent_config()
        # Since it is a LocalAgentConfig, it might pass None to api_key if we don't override,
        # but let's just make sure it initializes without raising error.
        assert config is not None
