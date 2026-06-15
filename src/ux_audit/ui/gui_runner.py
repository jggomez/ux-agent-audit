"""
Native PySide6 Desktop GUI runner for the UX/UI Audit Agent.

Implements a step-by-step wizard interface:
1. Configuration (Target URL, User Stories + Acceptance Criteria, API Key)
2. Live Execution (Pulsing step indicators and a real-time thought console)
3. Report & Export (Rich markdown rendering and modern styled PDF printing)
"""

import sys
import os
import asyncio
import logging
import traceback
from typing import Sequence, Dict

import markdown
from PySide6.QtCore import QThread, Signal, Qt, QSize, QUrl, QMarginsF, QSettings
from PySide6.QtGui import (
    QTextDocument,
    QPdfWriter,
    QPageLayout,
    QPageSize,
    QIcon,
    QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QFrame,
    QTextBrowser,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QTabWidget,
)

from ux_audit.core.models import AuditRequest
from ux_audit.agent.orchestrator import run_ux_audit
from ux_audit.core.constants import DEFAULT_AUDIT_URL

logger = logging.getLogger(__name__)

# Global startup parameters (to pre-populate inputs from main.py args)
_startup_url: str | None = None
_startup_stories: Sequence[str] | None = None
_startup_api_key: str | None = None


def set_startup_params(
    url: str | None,
    stories: Sequence[str] | None,
    api_key: str | None,
) -> None:
    """Sets initial parameters parsed from launcher args to seed the GUI."""
    global _startup_url, _startup_stories, _startup_api_key
    _startup_url = url
    _startup_stories = stories
    _startup_api_key = api_key


# ─── Worker Thread for Async Orchestrator ─────────────────────────────────────

class AuditWorker(QThread):
    """
    Background worker that runs the asynchronous orchestrator.
    Emits thread-safe signals to update the PySide6 UI.
    """
    thought_signal = Signal(str)
    chunk_signal = Signal(str)
    status_signal = Signal(str, str)  # status_key, message
    finished_signal = Signal(str)     # final_report_text
    error_signal = Signal(str, str)   # error_message, traceback_text

    def __init__(self, request: AuditRequest) -> None:
        super().__init__()
        self.request = request
        self.loop = None

    def run(self) -> None:
        """Background thread entry point."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            # Execute orchestrator using callbacks that trigger thread-safe Qt Signal emits
            report_text = self.loop.run_until_complete(
                run_ux_audit(
                    self.request,
                    on_thought=lambda thought: self.thought_signal.emit(thought),
                    on_report_chunk=lambda chunk: self.chunk_signal.emit(chunk),
                    on_status_change=lambda status, msg: self.status_signal.emit(status, msg),
                )
            )
            self.finished_signal.emit(report_text)
        except Exception as exc:
            logger.exception("Audit run failed on background thread")
            tb = traceback.format_exc()
            self.error_signal.emit(str(exc) or type(exc).__name__, tb)
        finally:
            self.loop.close()


# ─── Main Window Class ────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    The main desktop GUI application window.
    Implements the wizard steps and styling.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UX/UI Audit Agent — Senior Auditor")
        self.setMinimumSize(QSize(1100, 750))
        self.report_text = ""
        self.thoughts_text = ""
        self.worker = None

        # Base structure
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Wizard multi-step container
        self.wizard_stack = QStackedWidget(self)
        self.main_layout.addWidget(self.wizard_stack)

        # Build individual step views
        self._build_config_view()
        self._build_wizard_view()
        self._build_report_view()

        # Apply dark mode stylesheet (QSS)
        self._apply_theme()

        # Load startup seeds if provided
        self._load_seeds()

    def _apply_theme(self) -> None:
        """Applies a premium dark mode stylesheet (QSS) with purple accents."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f0f12;
            }
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #e4e4e7;
                font-weight: 500;
            }
            QLineEdit, QPlainTextEdit {
                background-color: #16161a;
                border: 1px solid #2d2d34;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f4f4f5;
            }
            QLineEdit:focus, QPlainTextEdit:focus {
                border: 1px solid #9b5de5;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border: 1px solid #52525b;
            }
            QPushButton:pressed {
                background-color: #18181b;
            }
            QListWidget {
                background-color: #16161a;
                border: 1px solid #2d2d34;
                border-radius: 6px;
                padding: 4px;
                color: #e4e4e7;
            }
            QListWidget::item {
                border-bottom: 1px solid #27272a;
                padding: 10px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #27272a;
            }
            QListWidget::item:selected {
                background-color: rgba(155, 93, 229, 0.15);
                color: #d8b4fe;
            }
            QTextBrowser {
                background-color: #16161a;
                border: 1px solid #2d2d34;
                border-radius: 8px;
                padding: 20px;
                color: #e4e4e7;
                line-height: 1.5;
            }
            QCheckBox {
                color: #e4e4e7;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                background: #16161a;
            }
            QCheckBox::indicator:checked {
                background: #9b5de5;
                border: 1px solid #a78bfa;
            }
            QScrollBar:vertical {
                border: none;
                background: #16161a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3f3f46;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #52525b;
            }
        """)

    def _load_seeds(self) -> None:
        """Pre-populates fields using seed variables from command line arguments and settings."""
        if _startup_url:
            self.url_input.setText(_startup_url)
        else:
            self.url_input.setText(DEFAULT_AUDIT_URL)

        # Clear default mock items
        self.stories_list.clear()

        if _startup_stories:
            for story in _startup_stories:
                # Add stories directly
                item = QListWidgetItem(story)
                self.stories_list.addItem(item)

        # Load API Key from QSettings, startup params, or env fallback
        self.settings = QSettings("UXAuditAgent", "UXAuditAgent")
        saved_api_key = self.settings.value("api_key", "")
        if _startup_api_key:
            self.api_key_input.setText(_startup_api_key)
        elif saved_api_key:
            self.api_key_input.setText(str(saved_api_key))
        else:
            env_key = os.environ.get("GEMINI_API_KEY", "")
            if env_key:
                self.api_key_input.setText(env_key)

    # ─── VIEW 1: Configuration View ───────────────────────────────────────────

    def _build_config_view(self) -> None:
        """Creates the initial configuration panel (URL, stories manager, key)."""
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Header Block
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        title_label = QLabel("Senior Usability & Accessibility Auditor", widget)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        subtitle_label = QLabel(
            "Configure audit targets, load User Stories with acceptance criteria, and launch the autonomous agent.",
            widget
        )
        subtitle_label.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        layout.addLayout(header_layout)

        # Descriptive Info Card (What it does & expected results)
        info_frame = QFrame(widget)
        info_frame.setStyleSheet("background-color: #16161a; border-radius: 8px; border: 1px solid #2d2d34;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(15, 12, 15, 12)
        info_layout.setSpacing(8)

        what_label = QLabel(
            "<span style='color: #d8b4fe;'><b>What the Agent Does:</b></span> "
            "Runs an autonomous web browser simulation to navigate, scroll, click UI components, and analyze "
            "layouts at multiple resolutions (including a 390px mobile viewport) against Nielsen Heuristics and WCAG 2.2 standards.",
            info_frame
        )
        what_label.setStyleSheet("color: #e4e4e7; font-size: 13px; border: none; background: transparent;")
        what_label.setWordWrap(True)

        results_label = QLabel(
            "<span style='color: #d8b4fe;'><b>Expected Outputs:</b></span> "
            "Generates an Executive Report with visual severity levels, code remediation snippets, User Story validation logs, "
            "and a sidebar screenshot gallery. You can export results to styled PDFs, raw Markdown, or raw agent log files.",
            info_frame
        )
        results_label.setStyleSheet("color: #e4e4e7; font-size: 13px; border: none; background: transparent;")
        results_label.setWordWrap(True)

        info_layout.addWidget(what_label)
        info_layout.addWidget(results_label)
        layout.addWidget(info_frame)

        # Grid form for Inputs
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        # Target URL
        url_box = QVBoxLayout()
        url_box.setSpacing(6)
        url_title = QLabel("Target Web Application URL", widget)
        url_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #d8b4fe;")
        self.url_input = QLineEdit(widget)
        self.url_input.setPlaceholderText("https://staging.clientapp.com")
        self.url_input.setFixedHeight(38)
        url_box.addWidget(url_title)
        url_box.addWidget(self.url_input)
        form_layout.addLayout(url_box)

        # User Stories Manager (Horizontal Layout)
        stories_box = QVBoxLayout()
        stories_box.setSpacing(6)
        stories_title = QLabel("User Stories & Acceptance Criteria (Optional)", widget)
        stories_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #d8b4fe;")
        stories_title.setToolTip(
            "Optional: Enter specific user stories and acceptance criteria to validate. "
            "If left empty, the auditor agent will perform a comprehensive, general review of the entire UI."
        )
        stories_box.addWidget(stories_title)

        manager_layout = QHBoxLayout()
        manager_layout.setSpacing(15)

        # Left Column: Inputs to Add
        input_col = QVBoxLayout()
        input_col.setSpacing(10)

        self.story_input = QLineEdit(widget)
        self.story_input.setPlaceholderText("User Story: As a customer, I want to filter products...")
        self.story_input.setFixedHeight(34)
        
        self.criteria_input = QPlainTextEdit(widget)
        self.criteria_input.setPlaceholderText(
            "Acceptance Criteria:\n1. Filter dropdown is keyboard-navigable.\n2. Screen reader announces filter changes."
        )
        self.criteria_input.setMaximumHeight(100)

        add_btn = QPushButton("Add User Story", widget)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b5cf6;
                border: none;
                color: white;
                font-weight: bold;
                height: 32px;
            }
            QPushButton:hover {
                background-color: #7c3aed;
            }
        """)
        add_btn.clicked.connect(self._add_user_story)

        input_col.addWidget(self.story_input)
        input_col.addWidget(self.criteria_input)
        input_col.addWidget(add_btn)
        manager_layout.addLayout(input_col, 5)

        # Right Column: List of Stories
        list_col = QVBoxLayout()
        list_col.setSpacing(6)
        self.stories_list = QListWidget(widget)
        self.stories_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        remove_btn = QPushButton("Remove Selected", widget)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f1f23;
                border: 1px solid #ef4444;
                color: #f87171;
                font-weight: 500;
                height: 28px;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        remove_btn.clicked.connect(self._remove_selected_story)

        list_col.addWidget(self.stories_list)
        list_col.addWidget(remove_btn)
        manager_layout.addLayout(list_col, 5)

        stories_box.addLayout(manager_layout)
        form_layout.addLayout(stories_box)

        # API Key Required Field
        api_box = QVBoxLayout()
        api_box.setSpacing(8)
        api_label = QLabel("Google Gemini API Key (Required):", widget)
        api_label.setStyleSheet("font-weight: bold; color: #f4f4f5;")
        self.api_key_input = QLineEdit(widget)
        self.api_key_input.setPlaceholderText("Enter your Google Gemini API Key (saved locally for future sessions)")
        self.api_key_input.setToolTip("Your Google Gemini API Key will be saved locally in application preferences.")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setFixedHeight(34)

        api_box.addWidget(api_label)
        api_box.addWidget(self.api_key_input)
        form_layout.addLayout(api_box)

        layout.addLayout(form_layout)

        # Bottom Launch Button
        launch_btn = QPushButton("Start Audit Wizard", widget)
        launch_btn.setObjectName("start_btn")
        launch_btn.setFixedHeight(46)
        launch_btn.clicked.connect(self._start_audit_wizard)
        layout.addWidget(launch_btn)

        self.wizard_stack.addWidget(widget)

    def _add_user_story(self) -> None:
        """Assembles the user story + criteria inputs and pushes to list widget."""
        story_text = self.story_input.text().strip()
        criteria_text = self.criteria_input.toPlainText().strip()

        if not story_text:
            QMessageBox.warning(self, "Validation Error", "User Story description cannot be empty.")
            return

        # Format combined string
        formatted_entry = f"Story: {story_text}"
        if criteria_text:
            formatted_entry += f"\nAcceptance Criteria:\n{criteria_text}"

        item = QListWidgetItem(formatted_entry)
        self.stories_list.addItem(item)

        # Clear inputs
        self.story_input.clear()
        self.criteria_input.clear()

    def _remove_selected_story(self) -> None:
        """Removes the selected story from list widget."""
        selected_items = self.stories_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Tip", "Select a story from the list to remove it.")
            return

        for item in selected_items:
            self.stories_list.takeItem(self.stories_list.row(item))

    # ─── VIEW 2: Wizard Execution View ────────────────────────────────────────

    def _build_wizard_view(self) -> None:
        """Creates the active auditor progress wizard and terminal stream console."""
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # Title block
        title_label = QLabel("Auditor Agent Progress Wizard", widget)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_label)

        # Steppers Layout (Horizontal)
        stepper_widget = QWidget(widget)
        stepper_layout = QHBoxLayout(stepper_widget)
        stepper_layout.setContentsMargins(0, 10, 0, 10)
        stepper_layout.setSpacing(10)

        # Initialize steps dict
        self.steps: Dict[str, Dict] = {}
        step_definitions = [
            ("initializing", "1", "Initializing"),
            ("starting_browser", "2", "Starting Browser"),
            ("auditing", "3", "Auditing Pages"),
            ("streaming", "4", "Finalizing Report"),
        ]

        for key, num, desc in step_definitions:
            step_frame = QFrame(stepper_widget)
            step_frame.setStyleSheet("background-color: #16161a; border-radius: 8px; border: 1px solid #2d2d34;")
            step_frame_layout = QHBoxLayout(step_frame)
            step_frame_layout.setContentsMargins(10, 8, 10, 8)
            step_frame_layout.setSpacing(10)

            # Circular number label
            num_label = QLabel(num, step_frame)
            num_label.setFixedSize(24, 24)
            num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Description label
            desc_label = QLabel(desc, step_frame)
            desc_label.setStyleSheet("color: #71717a; font-weight: bold;")

            step_frame_layout.addWidget(num_label)
            step_frame_layout.addWidget(desc_label)
            stepper_layout.addWidget(step_frame)

            # Track elements for style updates
            self.steps[key] = {
                "frame": step_frame,
                "circle": num_label,
                "text": desc_label,
                "title": desc
            }

            # Set initial pending style
            self._set_step_ui_status(key, "pending")

        layout.addWidget(stepper_widget)

        # Live Status Label
        self.status_bar_label = QLabel("Preparing environment...", widget)
        self.status_bar_label.setStyleSheet("font-weight: bold; color: #9b5de5; font-size: 14px;")
        layout.addWidget(self.status_bar_label)

        # Monospace Terminal Console Log
        console_title = QLabel("Agent Thought & Execution Log", widget)
        console_title.setStyleSheet("font-weight: bold; color: #a1a1aa;")
        layout.addWidget(console_title)

        self.thought_console = QPlainTextEdit(widget)
        self.thought_console.setReadOnly(True)
        self.thought_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #08080a;
                border: 1px solid #2d2d34;
                color: #22d3ee;
                font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Monaco, Courier, monospace;
                font-size: 12px;
                padding: 12px;
                line-height: 1.4;
            }
        """)
        layout.addWidget(self.thought_console)

        self.wizard_stack.addWidget(widget)

    def _set_step_ui_status(self, key: str, status: str) -> None:
        """Sets QSS stylesheet on stepper circles/texts depending on execution states."""
        step = self.steps[key]
        circle = step["circle"]
        text = step["text"]

        if status == "pending":
            circle.setStyleSheet("""
                border-radius: 12px;
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #a1a1aa;
                font-weight: bold;
            """)
            text.setStyleSheet("color: #71717a; font-weight: 500;")
        elif status == "active":
            circle.setStyleSheet("""
                border-radius: 12px;
                background-color: rgba(155, 93, 229, 0.2);
                border: 2px solid #9b5de5;
                color: #d8b4fe;
                font-weight: bold;
            """)
            text.setStyleSheet("color: #e9d5ff; font-weight: bold;")
        elif status == "completed":
            circle.setStyleSheet("""
                border-radius: 12px;
                background-color: rgba(6, 214, 160, 0.2);
                border: 2px solid #06d6a0;
                color: #34d399;
                font-weight: bold;
            """)
            text.setStyleSheet("color: #a7f3d0; font-weight: 500;")
        elif status == "failed":
            circle.setStyleSheet("""
                border-radius: 12px;
                background-color: rgba(239, 68, 68, 0.2);
                border: 2px solid #ef4444;
                color: #fca5a5;
                font-weight: bold;
            """)
            text.setStyleSheet("color: #fca5a5; font-weight: bold;")

    def _update_wizard_status(self, status_key: str, message: str) -> None:
        """Maps orchestrator status callbacks to Wizard step highlighting and prints message."""
        self.status_bar_label.setText(message)
        self.thought_console.appendPlainText(f"[STATUS] {message}")

        # Update step highlights
        if status_key == "initializing":
            self._set_step_ui_status("initializing", "active")
        elif status_key == "starting_browser":
            self._set_step_ui_status("initializing", "completed")
            self._set_step_ui_status("starting_browser", "active")
        elif status_key == "auditing":
            self._set_step_ui_status("initializing", "completed")
            self._set_step_ui_status("starting_browser", "completed")
            self._set_step_ui_status("auditing", "active")
        elif status_key == "streaming":
            self._set_step_ui_status("initializing", "completed")
            self._set_step_ui_status("starting_browser", "completed")
            self._set_step_ui_status("auditing", "completed")
            self._set_step_ui_status("streaming", "active")
        elif status_key == "done":
            self._set_step_ui_status("initializing", "completed")
            self._set_step_ui_status("starting_browser", "completed")
            self._set_step_ui_status("auditing", "completed")
            self._set_step_ui_status("streaming", "completed")
        elif status_key == "failed":
            self.status_bar_label.setStyleSheet("color: #fca5a5;")
            self.status_bar_label.setText(f"Audit failed: {message}")

    # ─── VIEW 3: Results & Export View ────────────────────────────────────────

    def _build_report_view(self) -> None:
        """Creates the final results panel displaying markdown results and export actions."""
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        title_label = QLabel("Executive UX/UI Audit Report", widget)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_label)

        # Tabbed container for Report and Thoughts
        self.results_tabs = QTabWidget(widget)
        self.results_tabs.setStyleSheet("""
            QTabWidget::panel {
                border: 1px solid #2d2d34;
                background-color: #16161a;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #1f1f23;
                color: #a1a1aa;
                border: 1px solid #2d2d34;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 4px;
            }
            QTabBar::tab:hover {
                background-color: #27272a;
                color: #e4e4e7;
            }
            QTabBar::tab:selected {
                background-color: #16161a;
                color: #c084fc;
                border-color: #2d2d34;
                border-bottom: 2px solid #9b5de5;
            }
        """)

        # Tab 1: Executive Report
        self.report_browser = QTextBrowser(self.results_tabs)
        self.report_browser.setOpenExternalLinks(True)
        self.report_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #16161a;
                border: none;
                padding: 24px;
                color: #e4e4e7;
            }
        """)
        self.results_tabs.addTab(self.report_browser, "Executive Audit Report")

        # Tab 2: Thinking Process
        self.thoughts_browser = QTextBrowser(self.results_tabs)
        self.thoughts_browser.setOpenExternalLinks(True)
        self.thoughts_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #0c0c0e;
                border: none;
                padding: 24px;
                color: #22d3ee;
            }
        """)
        self.results_tabs.addTab(self.thoughts_browser, "Agent Thinking Process")

        layout.addWidget(self.results_tabs)

        # Visual Audit Trail (Screenshots captured by Agent)
        self.screenshots_container = QWidget(widget)
        screenshots_layout = QVBoxLayout(self.screenshots_container)
        screenshots_layout.setContentsMargins(0, 10, 0, 5)
        screenshots_layout.setSpacing(6)
        
        self.screenshots_label = QLabel("Visual Audit Trail (Click on a screenshot to open in system viewer):", self.screenshots_container)
        self.screenshots_label.setStyleSheet("font-weight: bold; color: #d8b4fe; font-size: 13px;")
        
        self.screenshots_scroll = QScrollArea(self.screenshots_container)
        self.screenshots_scroll.setFixedHeight(120)
        self.screenshots_scroll.setWidgetResizable(True)
        self.screenshots_scroll.setStyleSheet("background-color: #16161a; border: 1px solid #2d2d34; border-radius: 6px;")
        
        self.screenshots_scroll_widget = QWidget(self.screenshots_scroll)
        self.screenshots_scroll_widget.setStyleSheet("background-color: transparent;")
        self.screenshots_list_layout = QHBoxLayout(self.screenshots_scroll_widget)
        self.screenshots_list_layout.setContentsMargins(8, 8, 8, 8)
        self.screenshots_list_layout.setSpacing(12)
        self.screenshots_list_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.screenshots_scroll.setWidget(self.screenshots_scroll_widget)
        screenshots_layout.addWidget(self.screenshots_label)
        screenshots_layout.addWidget(self.screenshots_scroll)
        
        # Hide initially
        self.screenshots_container.setVisible(False)
        layout.addWidget(self.screenshots_container)

        # Export row buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        pdf_btn = QPushButton("Export PDF Report", widget)
        pdf_btn.setObjectName("pdf_btn")
        pdf_btn.setFixedHeight(40)
        pdf_btn.setToolTip("Export the executive summary and findings as a styled PDF")
        pdf_btn.clicked.connect(self._export_to_pdf)

        md_btn = QPushButton("Export Markdown Report", widget)
        md_btn.setFixedHeight(40)
        md_btn.setToolTip("Export the report as a Markdown file")
        md_btn.clicked.connect(self._export_to_markdown)

        thoughts_btn = QPushButton("Export Thinking Process", widget)
        thoughts_btn.setFixedHeight(40)
        thoughts_btn.setToolTip("Export the agent's full thinking process and tool executions")
        thoughts_btn.clicked.connect(self._export_thoughts)

        folder_btn = QPushButton("Open Screenshots", widget)
        folder_btn.setFixedHeight(40)
        folder_btn.setToolTip("Open the local folder containing captured screen viewports")
        folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expanduser("~/ux_audit_screenshots")))
        )

        new_audit_btn = QPushButton("New Audit", widget)
        new_audit_btn.setFixedHeight(40)
        new_audit_btn.setToolTip("Start a new UX/UI audit session")
        new_audit_btn.clicked.connect(self._reset_wizard)

        buttons_layout.addWidget(pdf_btn)
        buttons_layout.addWidget(md_btn)
        buttons_layout.addWidget(thoughts_btn)
        buttons_layout.addWidget(folder_btn)
        buttons_layout.addWidget(new_audit_btn)
        layout.addLayout(buttons_layout)

        self.wizard_stack.addWidget(widget)

    # ─── EVENT HANDLERS & LOGIC ───────────────────────────────────────────────

    def _start_audit_wizard(self) -> None:
        """Collects, validates configs, switches stack to wizard, and launches thread."""
        # Clear previous screenshots
        import shutil
        output_dir = os.path.expanduser("~/ux_audit_screenshots")
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                filepath = os.path.join(output_dir, filename)
                try:
                    if os.path.isfile(filepath) or os.path.islink(filepath):
                        os.unlink(filepath)
                    elif os.path.isdir(filepath):
                        shutil.rmtree(filepath)
                except Exception as exc:
                    logger.error("Failed to delete old screenshot %s: %s", filepath, exc)

        url = self.url_input.text().strip()
        
        # Read list items
        stories = []
        for i in range(self.stories_list.count()):
            stories.append(self.stories_list.item(i).text())

        if not url:
            QMessageBox.warning(self, "Validation Error", "Target URL is required.")
            return

        # Empty user stories list is allowed for general UI/UX audits

        # Resolve and validate API key
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Validation Error", "Google Gemini API Key is required.")
            return

        # Save to QSettings
        self.settings.setValue("api_key", api_key)
        self.settings.sync()

        try:
            # Build parameter request object (fail fast validation check)
            request = AuditRequest.from_primitives(
                target_url=url,
                user_stories=stories,
                api_key=api_key
            )
        except ValueError as err:
            QMessageBox.critical(self, "Validation Error", f"Invalid parameters:\n{err}")
            return

        # Switch to wizard view (index 1)
        self.wizard_stack.setCurrentIndex(1)
        
        # Reset step visual states and clear logs
        self.report_text = ""
        self.thoughts_text = ""
        self.thought_console.clear()
        self.status_bar_label.setStyleSheet("color: #9b5de5; font-size: 14px; font-weight: bold;")
        self.status_bar_label.setText("Preparing environment...")
        
        for k in self.steps:
            self._set_step_ui_status(k, "pending")

        # Launch Thread
        self.worker = AuditWorker(request)
        self.worker.thought_signal.connect(self._handle_thought)
        self.worker.chunk_signal.connect(self._handle_chunk)
        self.worker.status_signal.connect(self._update_wizard_status)
        self.worker.finished_signal.connect(self._handle_audit_finished)
        self.worker.error_signal.connect(self._handle_audit_error)

        self.worker.start()

    def _handle_thought(self, thought: str) -> None:
        """Appends thought text chunks to the scrollable thought console."""
        self.thoughts_text += thought
        self.thought_console.appendPlainText(thought)
        self.thought_console.verticalScrollBar().setValue(
            self.thought_console.verticalScrollBar().maximum()
        )

    def _handle_chunk(self, chunk: str) -> None:
        """Appends markdown chunk tokens to report preview (raw logs during stream)."""
        self.report_text += chunk

    def _handle_audit_finished(self, final_report: str) -> None:
        """Auditor finished: sets markdown, switches to view 3."""
        self.report_text = final_report
        
        # Convert final report markdown to HTML and apply premium dark styling
        report_html = markdown.markdown(final_report, extensions=['tables', 'fenced_code'])
        styled_report_html = f"""
        <html>
        <head>
        <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #e4e4e7;
            background-color: #16161a;
            line-height: 1.6;
            font-size: 14px;
        }}
        h1 {{
            color: #c084fc;
            font-size: 22px;
            border-bottom: 2px solid #3f3f46;
            padding-bottom: 8px;
            margin-top: 24px;
            margin-bottom: 12px;
        }}
        h2 {{
            color: #d8b4fe;
            font-size: 18px;
            border-bottom: 1px solid #2d2d34;
            padding-bottom: 6px;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        h3 {{
            color: #e9d5ff;
            font-size: 15px;
            margin-top: 16px;
            margin-bottom: 8px;
        }}
        p, li {{
            margin-top: 6px;
            margin-bottom: 12px;
            color: #d4d4d8;
        }}
        ul, ol {{
            margin-top: 4px;
            margin-bottom: 12px;
            padding-left: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            margin-bottom: 15px;
        }}
        th {{
            background-color: #27272a;
            color: #f4f4f5;
            font-weight: bold;
            border: 1px solid #3f3f46;
            padding: 8px 12px;
            text-align: left;
        }}
        td {{
            border: 1px solid #2d2d34;
            padding: 8px 12px;
            background-color: #18181b;
        }}
        tr:nth-child(even) td {{
            background-color: #202024;
        }}
        code {{
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            background-color: #27272a;
            color: #f4f4f5;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
        }}
        pre {{
            background-color: #09090b;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #2d2d34;
            margin-top: 10px;
            margin-bottom: 10px;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        </style>
        </head>
        <body>
        {report_html}
        </body>
        </html>
        """
        # Replace severity badges with styled HTML spans
        styled_report_html = styled_report_html.replace(
            "[CRITICAL]",
            '<span style="background-color: #7f1d1d; color: #fecaca; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; border: 1px solid #991b1b;">CRITICAL</span>'
        ).replace(
            "[MAJOR]",
            '<span style="background-color: #7c2d12; color: #ffedd5; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; border: 1px solid #9a3412;">MEDIUM (MAJOR)</span>'
        ).replace(
            "[MINOR]",
            '<span style="background-color: #1e3a8a; color: #dbeafe; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; border: 1px solid #1e40af;">LOW (MINOR)</span>'
        )
        self.report_browser.setHtml(styled_report_html)

        # Convert thoughts markdown to HTML and apply styled dark monospace look
        thoughts_html = markdown.markdown(self.thoughts_text, extensions=['tables', 'fenced_code'])
        styled_thoughts_html = f"""
        <html>
        <head>
        <style>
        body {{
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Monaco, Courier, monospace;
            color: #22d3ee;
            background-color: #0c0c0e;
            line-height: 1.6;
            font-size: 13px;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #d8b4fe;
            font-weight: bold;
            margin-top: 15px;
            margin-bottom: 8px;
        }}
        p, li {{
            margin-top: 4px;
            margin-bottom: 8px;
        }}
        strong {{
            color: #a78bfa;
        }}
        a {{
            color: #38bdf8;
            text-decoration: underline;
        }}
        </style>
        </head>
        <body>
        {thoughts_html}
        </body>
        </html>
        """
        self.thoughts_browser.setHtml(styled_thoughts_html)

        # Ensure the first tab (Executive Report) is selected by default
        self.results_tabs.setCurrentIndex(0)
        
        # Mark all steps completed
        for k in self.steps:
            self._set_step_ui_status(k, "completed")
        self.status_bar_label.setStyleSheet("color: #06d6a0;")
        self.status_bar_label.setText("Audit successfully completed!")

        # Scan and populate screenshots
        # 1. Clear previous thumbnails in layout
        while self.screenshots_list_layout.count() > 0:
            item = self.screenshots_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # 2. Find files in ~/ux_audit_screenshots/
        output_dir = os.path.expanduser("~/ux_audit_screenshots")
        if os.path.exists(output_dir):
            screenshots = sorted([
                f for f in os.listdir(output_dir) 
                if f.startswith("screenshot_") and f.endswith(".png")
            ], key=lambda x: int(x.split("_")[1].split(".")[0]))
            
            if screenshots:
                self.screenshots_container.setVisible(True)
                for sc in screenshots:
                    filepath = os.path.join(output_dir, sc)
                    
                    # Create a button acting as a clickable thumbnail
                    thumb_btn = QPushButton(self.screenshots_scroll_widget)
                    thumb_btn.setFixedSize(140, 85)
                    thumb_btn.setIcon(QIcon(filepath))
                    thumb_btn.setIconSize(QSize(130, 75))
                    thumb_btn.setToolTip(f"Open screenshot: {sc}\nClick to view full size")
                    
                    # Style the button thumbnail
                    thumb_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #0f0f12;
                            border: 1px solid #3f3f46;
                            border-radius: 4px;
                            padding: 2px;
                        }
                        QPushButton:hover {
                            border: 2px solid #9b5de5;
                        }
                    """)
                    
                    # Connect click handler to open image in system preview
                    thumb_btn.clicked.connect(lambda checked=False, path=filepath: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
                    self.screenshots_list_layout.addWidget(thumb_btn)
            else:
                self.screenshots_container.setVisible(False)
        else:
            self.screenshots_container.setVisible(False)

        # Move to report view (index 2)
        self.wizard_stack.setCurrentIndex(2)

    def _handle_audit_error(self, err_msg: str, traceback_text: str) -> None:
        """Handles background exceptions by showing a detailed QMessageBox."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Execution Failure")
        msg_box.setText(
            f"The auditor agent encountered an unexpected error:\n\n"
            f"Error: {err_msg}"
        )
        msg_box.setDetailedText(traceback_text)
        
        # Style the QMessageBox details panel and text to match our dark theme
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #16161a;
            }
            QLabel {
                color: #e4e4e7;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #f4f4f5;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
            QTextEdit {
                background-color: #08080a;
                color: #fca5a5;
                font-family: monospace;
            }
        """)
        msg_box.exec()
        self.wizard_stack.setCurrentIndex(0)

    def _reset_wizard(self) -> None:
        """Returns wizard view back to setup config stage."""
        self.report_text = ""
        self.thoughts_text = ""
        self.report_browser.clear()
        self.thoughts_browser.clear()
        self.wizard_stack.setCurrentIndex(0)

    # ─── PDF & MARKDOWN EXPORTERS ─────────────────────────────────────────────

    def _export_to_markdown(self) -> None:
        """Saves raw markdown report text using file dialog."""
        if not self.report_text:
            QMessageBox.warning(self, "No Report", "No report content is available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown Report",
            os.path.expanduser("~/UX_Audit_Report.md"),
            "Markdown Files (*.md)",
            options=QFileDialog.Option.DontUseNativeDialog
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.report_text)
            QMessageBox.information(self, "Success", "Markdown report exported successfully!")
        except Exception as exc:
            QMessageBox.critical(self, "File Error", f"Failed to save Markdown file:\n{exc}")

    def _export_to_pdf(self) -> None:
        """Converts markdown report text to stylized HTML and exports to PDF."""
        if not self.report_text:
            QMessageBox.warning(self, "No Report", "No report content is available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Report",
            os.path.expanduser("~/UX_Audit_Report.pdf"),
            "PDF Files (*.pdf)",
            options=QFileDialog.Option.DontUseNativeDialog
        )

        if not file_path:
            return

        try:
            # 1. Convert markdown to HTML body
            html_body = markdown.markdown(self.report_text, extensions=['tables', 'fenced_code'])

            # 2. Package inside fully-styled HTML template using robust inline styling rules
            # suitable for QTextDocument's HTML layout parser.
            styled_html = f"""
            <html>
            <head>
            <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                color: #27272a;
                line-height: 1.5;
                font-size: 11pt;
            }}
            h1 {{
                color: #4f46e5;
                font-size: 20pt;
                border-bottom: 2px solid #e2e8f0;
                padding-bottom: 6px;
                margin-top: 18pt;
                margin-bottom: 8pt;
            }}
            h2 {{
                color: #1e1b4b;
                font-size: 14pt;
                border-bottom: 1px solid #e2e8f0;
                padding-bottom: 4px;
                margin-top: 16pt;
                margin-bottom: 6pt;
            }}
            h3 {{
                color: #312e81;
                font-size: 11pt;
                margin-top: 12pt;
                margin-bottom: 4pt;
            }}
            p {{
                margin-top: 4pt;
                margin-bottom: 8pt;
                color: #4b5563;
            }}
            li {{
                color: #4b5563;
                margin-bottom: 3pt;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10pt;
                margin-bottom: 10pt;
            }}
            th {{
                background-color: #f3f4f6;
                color: #111827;
                font-weight: bold;
                border: 1px solid #e5e7eb;
                padding: 6px 8px;
                text-align: left;
                font-size: 10pt;
            }}
            td {{
                border: 1px solid #e5e7eb;
                padding: 6px 8px;
                font-size: 9.5pt;
            }}
            tr:nth-child(even) {{
                background-color: #f9fafb;
            }}
            code {{
                font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
                background-color: #f3f4f6;
                color: #111827;
                padding: 2px 4px;
                border-radius: 3px;
                font-size: 9.5pt;
            }}
            pre {{
                background-color: #f9fafb;
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #e5e7eb;
                margin-top: 6pt;
                margin-bottom: 6pt;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
            }}
            </style>
            </head>
            <body>
            {html_body}
            </body>
            </html>
            """

            # 3. Add modern color pills for severity levels
            styled_html = styled_html.replace(
                "[CRITICAL]",
                '<span style="background-color: #fecaca; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 9pt; border: 1px solid #fee2e2;">CRITICAL</span>'
            )
            styled_html = styled_html.replace(
                "[MAJOR]",
                '<span style="background-color: #ffedd5; color: #9a3412; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 9pt; border: 1px solid #ffedd5;">MEDIUM (MAJOR)</span>'
            )
            styled_html = styled_html.replace(
                "[MINOR]",
                '<span style="background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 9pt; border: 1px solid #dbeafe;">LOW (MINOR)</span>'
            )

            # 4. Save via QPdfWriter
            pdf_writer = QPdfWriter(file_path)
            pdf_writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            pdf_writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)

            doc = QTextDocument()
            doc.setHtml(styled_html)
            doc.print_(pdf_writer)
            
            # Flush and release the PDF writer to complete file creation
            del pdf_writer

            QMessageBox.information(
                self,
                "Success",
                "Styled PDF report generated successfully!"
            )
        except Exception as exc:
            logger.exception("PDF conversion failed")
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to generate PDF document:\n{exc}"
            )

    def _export_thoughts(self) -> None:
        """Saves the agent's reasoning thoughts using file dialog."""
        if not self.thoughts_text:
            QMessageBox.warning(self, "No Thoughts", "No thinking process trace is available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Thinking Process Log",
            os.path.expanduser("~/UX_Audit_Thoughts.txt"),
            "Text Files (*.txt);;Markdown Files (*.md)",
            options=QFileDialog.Option.DontUseNativeDialog
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.thoughts_text)
            QMessageBox.information(self, "Success", "Thinking process log exported successfully!")
        except Exception as exc:
            QMessageBox.critical(self, "File Error", f"Failed to save thinking process log:\n{exc}")


# ─── Launcher GUI Entry Point ────────────────────────────────────────────────

def start_gui() -> None:
    """Initializes the QApplication loop, registers resources, and launches window."""
    from ux_audit.core.env import setup_environment
    setup_environment()
    logger.info("Initializing PySide6 Application Window...")
    
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    
    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "icon.png"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.showMaximized()
    
    sys.exit(app.exec())
