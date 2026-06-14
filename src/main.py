import os
import sys
import logging
import asyncio
import argparse
from dotenv import load_dotenv

from ux_audit.ui.gui_runner import start_gui, set_startup_params
from ux_audit.core.env import setup_environment

def configure_logging() -> None:
    """Configures the root logger for the application."""
    log_file = os.path.expanduser("~/ux_audit.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, mode="a", encoding="utf-8")
        ],
    )

def run_cli(args: argparse.Namespace) -> None:
    """Executes the UX/UI audit in pure CLI mode."""
    # Load environment variables
    setup_environment()
    load_dotenv()
    configure_logging()

    # Load API Key
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set. Use --api-key to provide it.", file=sys.stderr)
        sys.exit(1)

    # Get target url
    url = args.url
    if not url:
        from ux_audit.core.constants import DEFAULT_AUDIT_URL
        url = DEFAULT_AUDIT_URL
        print(f"No target URL specified. Using default: {url}")

    # Get user stories
    user_stories = tuple(args.stories) if args.stories else ()

    from ux_audit.core.models import AuditRequest
    request = AuditRequest(
        target_url=url,
        user_stories=user_stories,
        api_key=api_key
    )

    print(f"\nStarting UX/UI Audit CLI...")
    print(f"Target URL: {url}")
    print(f"User Stories: {len(user_stories)} loaded")
    print(f"Output File: {args.output}")
    print("-" * 60)

    from ux_audit.agent.orchestrator import run_ux_audit

    def cli_on_status_change(status_key: str, message: str) -> None:
        print(f"\n>>> [STATUS: {status_key.upper()}] {message}")

    try:
        report_text = asyncio.run(
            run_ux_audit(
                request,
                on_status_change=cli_on_status_change
            )
        )

        if report_text:
            output_path = os.path.abspath(args.output)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            print(f"\n" + "=" * 60)
            print(f"AUDIT COMPLETED SUCCESSFULLY!")
            print(f"Report saved to: {output_path}")
            print("=" * 60 + "\n")
        else:
            print("\nAudit completed, but no report text was generated.")
            sys.exit(1)

    except Exception as exc:
        print(f"\n[CLI ERROR] Audit failed: {exc}", file=sys.stderr)
        sys.exit(1)

def main() -> None:
    """Entry point parsing arguments and launching either CLI or GUI mode."""
    # Prevent macOS Finder launching from root directory (/)
    # which makes the SDK mount / as the workspace and crash on permissions.
    if os.getcwd() == "/":
        os.chdir(os.path.expanduser("~"))

    parser = argparse.ArgumentParser(description="UX/UI Audit Agent — Senior Auditor")
    parser.add_argument("--cli", action="store_true", help="Run in terminal CLI mode instead of GUI")
    parser.add_argument("--url", type=str, help="Target URL to audit")
    parser.add_argument("--stories", type=str, nargs="*", help="User stories to validate")
    parser.add_argument("--api-key", type=str, help="Gemini API key override")
    parser.add_argument("--output", type=str, default="audit_report.md", help="Output Markdown report path (CLI only)")

    args = parser.parse_args()

    if args.cli:
        run_cli(args)
    else:
        # Load environment first for GUI subprocesses
        setup_environment()
        load_dotenv()
        configure_logging()
        
        # Seed startup params if specified
        set_startup_params(args.url, args.stories, args.api_key)
        start_gui()

if __name__ == "__main__":
    main()
