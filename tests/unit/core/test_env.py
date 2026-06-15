import os
import subprocess
from unittest.mock import patch, MagicMock
from ux_audit.core.env import setup_environment, _ensure_fallback_paths

def test_ensure_fallback_paths() -> None:
    # Mock exists, isdir, listdir to simulate node/nvm presence
    def mock_exists_side_effect(path):
        return "/opt/homebrew/bin" in path or "/usr/local/bin" in path or ".nvm" in path

    with patch("os.path.exists", side_effect=mock_exists_side_effect), \
         patch("os.path.isdir", return_value=True), \
         patch("os.listdir", return_value=["v23.8.0"]), \
         patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
        _ensure_fallback_paths()
        path = os.environ["PATH"]
        assert "/opt/homebrew/bin" in path
        assert "/usr/local/bin" in path
        assert ".nvm/versions/node/v23.8.0/bin" in path

def test_ensure_fallback_paths_nvm_scan_exception() -> None:
    # Simulates listdir failing for NVM directory to cover exception block
    with patch("os.path.exists", return_value=True), \
         patch("os.path.isdir", return_value=True), \
         patch("os.listdir", side_effect=OSError("Permission denied")), \
         patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True), \
         patch("ux_audit.core.env.logger.debug") as mock_debug:
        _ensure_fallback_paths()
        mock_debug.assert_called_once()

def test_setup_environment_non_darwin() -> None:
    with patch("sys.platform", "linux"), \
         patch("subprocess.run") as mock_run:
        setup_environment()
        mock_run.assert_not_called()

def test_setup_environment_darwin_standard_path() -> None:
    # Standard path containing npx and > 5 segments
    test_path = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:npx"
    with patch("sys.platform", "darwin"), \
         patch("subprocess.run") as mock_run, \
         patch.dict(os.environ, {"PATH": test_path}, clear=True):
        setup_environment()
        mock_run.assert_not_called()

def test_setup_environment_darwin_restricted_path_success() -> None:
    # Restricted path (<= 5 segments, no npx)
    test_path = "/usr/bin:/bin"
    mock_stdout = "PATH=/captured/brew/bin:/captured/nvm/bin\nGEMINI_API_KEY=captured_key\nNVM_DIR=/captured/nvm\nINVALID_LINE\n"
    completed_process = MagicMock(spec=subprocess.CompletedProcess)
    completed_process.stdout = mock_stdout

    with patch("sys.platform", "darwin"), \
         patch("subprocess.run", return_value=completed_process) as mock_run, \
         patch.dict(os.environ, {"PATH": test_path}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("os.path.isdir", return_value=False):
        setup_environment()
        mock_run.assert_called_once()
        
        # Verify env keys were merged correctly
        assert "GEMINI_API_KEY" in os.environ
        assert os.environ["GEMINI_API_KEY"] == "captured_key"
        assert os.environ["NVM_DIR"] == "/captured/nvm"
        
        # Verify PATH merged new paths with old paths
        path = os.environ["PATH"]
        assert "/captured/brew/bin" in path
        assert "/captured/nvm/bin" in path
        assert "/usr/bin" in path
        assert "/bin" in path

def test_setup_environment_darwin_restricted_path_failure() -> None:
    # Restricted path, but subprocess runs fails/raises error
    test_path = "/usr/bin"
    with patch("sys.platform", "darwin"), \
         patch("subprocess.run", side_effect=subprocess.SubprocessError("timeout")) as mock_run, \
         patch.dict(os.environ, {"PATH": test_path}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("os.path.isdir", return_value=False):
        # Should catch exception and not crash
        setup_environment()
        mock_run.assert_called_once()
