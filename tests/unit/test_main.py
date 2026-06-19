import pytest
import argparse
from unittest.mock import patch, mock_open
from main import main, run_cli

def test_main_gui_routing() -> None:
    # Test that without --cli, main calls setup_environment and start_gui
    with patch("sys.argv", ["main.py"]), \
         patch("main.setup_environment") as mock_setup_env, \
         patch("main.start_gui") as mock_start_gui, \
         patch("main.set_startup_params") as mock_set_params, \
         patch("main.load_dotenv"), \
         patch("main.configure_logging"):
        main()
        mock_setup_env.assert_called_once()
        mock_start_gui.assert_called_once()
        mock_set_params.assert_called_once_with(None, None, None, "")

def test_main_cli_routing() -> None:
    # Test that with --cli, main calls run_cli
    with patch("sys.argv", ["main.py", "--cli", "--url", "https://test.com", "--api-key", "my-key"]), \
         patch("main.run_cli") as mock_run_cli:
        main()
        mock_run_cli.assert_called_once()
        args = mock_run_cli.call_args[0][0]
        assert args.cli is True
        assert args.url == "https://test.com"
        assert args.api_key == "my-key"
        assert args.hints == ""

def test_run_cli_no_api_key() -> None:
    args = argparse.Namespace(cli=True, url="https://test.com", api_key=None, stories=[], output="report.md")
    with patch.dict("os.environ", {}, clear=True), \
         patch("main.setup_environment"), \
         patch("main.load_dotenv"), \
         patch("main.configure_logging"), \
         pytest.raises(SystemExit) as excinfo:
        run_cli(args)
    assert excinfo.value.code == 1

def test_run_cli_success() -> None:
    args = argparse.Namespace(cli=True, url="https://test.com", api_key="my-key", stories=["Story 1"], output="report.md")
    mock_report = "Mock Report Text"
    
    with patch("main.setup_environment"), \
         patch("main.load_dotenv"), \
         patch("main.configure_logging"), \
         patch("ux_audit.agent.orchestrator.run_ux_audit", return_value=mock_report) as mock_run, \
         patch("builtins.open", mock_open()) as mock_file:
        run_cli(args)
        mock_run.assert_called_once()
        mock_file.assert_called_once()

def test_run_cli_failure() -> None:
    args = argparse.Namespace(cli=True, url="https://test.com", api_key="my-key", stories=[], output="report.md")
    with patch("main.setup_environment"), \
         patch("main.load_dotenv"), \
         patch("main.configure_logging"), \
         patch("ux_audit.agent.orchestrator.run_ux_audit", side_effect=Exception("API Error")), \
         pytest.raises(SystemExit) as excinfo:
        run_cli(args)
    assert excinfo.value.code == 1

