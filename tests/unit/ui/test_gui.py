import pytest
from unittest.mock import MagicMock, patch, mock_open
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QListWidgetItem
from ux_audit.ui.gui_runner import MainWindow


@pytest.fixture(scope="session")
def q_app():
    """Initializes the QApplication singleton for testing Qt widgets."""
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_mainwindow_init(q_app) -> None:
    """Verifies that the MainWindow initializes with the correct title, views, and initial state."""
    window = MainWindow()
    assert window.windowTitle() == "UX/UI Audit Agent — Senior Auditor"
    assert window.wizard_stack.count() == 3
    assert window.wizard_stack.currentIndex() == 0  # Starts on configuration view
    assert window.url_input.text() != ""
    assert window.stories_list.count() == 0
    
    # Check new components
    assert window.results_tabs is not None
    assert window.results_tabs.count() == 2
    assert window.results_tabs.tabText(0) == "Executive Audit Report"
    assert window.results_tabs.tabText(1) == "Agent Thinking Process"
    assert window.thoughts_browser is not None
    assert window.report_text == ""
    assert window.thoughts_text == ""


def test_mainwindow_add_user_story(q_app) -> None:
    window = MainWindow()
    initial_count = window.stories_list.count()
    
    window.story_input.setText("Test user story description")
    window.criteria_input.setPlainText("- Criteria A\n- Criteria B")
    
    window._add_user_story()
    
    assert window.stories_list.count() == initial_count + 1
    added_item = window.stories_list.item(initial_count)
    assert "Test user story description" in added_item.text()
    assert "Criteria A" in added_item.text()
    
    # Inputs should be cleared
    assert window.story_input.text() == ""
    assert window.criteria_input.toPlainText() == ""


def test_mainwindow_add_user_story_validation_error(q_app) -> None:
    window = MainWindow()
    window.story_input.setText("")  # Invalid empty story
    
    with patch.object(QMessageBox, "warning") as mock_warning:
        window._add_user_story()
        mock_warning.assert_called_once()


def test_mainwindow_remove_selected_story(q_app) -> None:
    window = MainWindow()
    window.stories_list.clear()
    window.stories_list.addItem(QListWidgetItem("Mock Story 1"))
    window.stories_list.addItem(QListWidgetItem("Mock Story 2"))
    assert window.stories_list.count() == 2
    
    # Select first item
    window.stories_list.setCurrentRow(0)
    window._remove_selected_story()
    
    assert window.stories_list.count() == 1
    assert window.stories_list.item(0).text() == "Mock Story 2"


def test_mainwindow_remove_selected_story_empty_selection(q_app) -> None:
    window = MainWindow()
    window.stories_list.clear()
    window.stories_list.addItem(QListWidgetItem("Mock Story 1"))
    window.stories_list.clearSelection()
    
    with patch.object(QMessageBox, "information") as mock_info:
        window._remove_selected_story()
        mock_info.assert_called_once()
        assert window.stories_list.count() == 1


def test_mainwindow_reset_wizard(q_app) -> None:
    window = MainWindow()
    window.report_text = "Some report text"
    window.thoughts_text = "Some thoughts text"
    window.wizard_stack.setCurrentIndex(2)
    
    window._reset_wizard()
    
    assert window.report_text == ""
    assert window.thoughts_text == ""
    assert window.wizard_stack.currentIndex() == 0


def test_mainwindow_export_to_markdown_no_report(q_app) -> None:
    window = MainWindow()
    window.report_text = ""
    
    with patch.object(QMessageBox, "warning") as mock_warning:
        window._export_to_markdown()
        mock_warning.assert_called_once()


def test_mainwindow_export_to_markdown_success(q_app) -> None:
    window = MainWindow()
    window.report_text = "# Test Report Markdown"
    
    m_open = mock_open()
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/report.md", "Markdown Files (*.md)")), \
         patch("builtins.open", m_open), \
         patch.object(QMessageBox, "information") as mock_info:
        window._export_to_markdown()
        
        m_open.assert_called_once_with("/dummy/report.md", "w", encoding="utf-8")
        m_open().write.assert_called_once_with("# Test Report Markdown")
        mock_info.assert_called_once()


def test_mainwindow_export_to_markdown_failure(q_app) -> None:
    window = MainWindow()
    window.report_text = "# Test Report Markdown"
    
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/report.md", "Markdown Files (*.md)")), \
         patch("builtins.open", side_effect=IOError("Permission denied")), \
         patch.object(QMessageBox, "critical") as mock_critical:
        window._export_to_markdown()
        mock_critical.assert_called_once()


def test_mainwindow_export_to_pdf_no_report(q_app) -> None:
    window = MainWindow()
    window.report_text = ""
    
    with patch.object(QMessageBox, "warning") as mock_warning:
        window._export_to_pdf()
        mock_warning.assert_called_once()


def test_mainwindow_export_to_pdf_success(q_app) -> None:
    window = MainWindow()
    window.report_text = "# Styled PDF Report"
    
    mock_pdf_writer = MagicMock()
    mock_doc = MagicMock()
    
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/report.pdf", "PDF Files (*.pdf)")), \
         patch("ux_audit.ui.gui_runner.QPdfWriter", return_value=mock_pdf_writer), \
         patch("ux_audit.ui.gui_runner.QTextDocument", return_value=mock_doc), \
         patch.object(QMessageBox, "information") as mock_info:
        window._export_to_pdf()
        
        mock_doc.setHtml.assert_called_once()
        mock_doc.print_.assert_called_once_with(mock_pdf_writer)
        mock_info.assert_called_once()


def test_mainwindow_export_to_pdf_failure(q_app) -> None:
    window = MainWindow()
    window.report_text = "# Styled PDF Report"
    
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/report.pdf", "PDF Files (*.pdf)")), \
         patch("ux_audit.ui.gui_runner.QPdfWriter", side_effect=Exception("Failed to construct writer")), \
         patch.object(QMessageBox, "critical") as mock_critical:
        window._export_to_pdf()
        mock_critical.assert_called_once()


def test_mainwindow_export_thoughts_no_thoughts(q_app) -> None:
    window = MainWindow()
    window.thoughts_text = ""
    
    with patch.object(QMessageBox, "warning") as mock_warning:
        window._export_thoughts()
        mock_warning.assert_called_once()


def test_mainwindow_export_thoughts_success(q_app) -> None:
    window = MainWindow()
    window.thoughts_text = "Some reasoning thoughts"
    
    m_open = mock_open()
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/thoughts.txt", "Text Files (*.txt)")), \
         patch("builtins.open", m_open), \
         patch.object(QMessageBox, "information") as mock_info:
        window._export_thoughts()
        
        m_open.assert_called_once_with("/dummy/thoughts.txt", "w", encoding="utf-8")
        m_open().write.assert_called_once_with("Some reasoning thoughts")
        mock_info.assert_called_once()


def test_mainwindow_export_thoughts_failure(q_app) -> None:
    window = MainWindow()
    window.thoughts_text = "Some reasoning thoughts"
    
    with patch.object(QFileDialog, "getSaveFileName", return_value=("/dummy/thoughts.txt", "Text Files (*.txt)")), \
         patch("builtins.open", side_effect=IOError("Disk Full")), \
         patch.object(QMessageBox, "critical") as mock_critical:
        window._export_thoughts()
        mock_critical.assert_called_once()


def test_mainwindow_handle_thought_and_chunk(q_app) -> None:
    window = MainWindow()
    window._handle_thought("Thought chunk 1")
    assert window.thoughts_text == "Thought chunk 1"
    
    window._handle_chunk("Chunk 1")
    assert window.report_text == "Chunk 1"


def test_mainwindow_handle_audit_finished(q_app) -> None:
    window = MainWindow()
    window.thoughts_text = "Thinking about design..."
    
    with patch("os.path.isdir", return_value=False), \
         patch("os.listdir", return_value=[]):
        window._handle_audit_finished("# Audit Report\n[CRITICAL] Contrast issue\n[MAJOR] Flow error\n[MINOR] Alignment")
        
        # Verify stack moved to report page (index 2)
        assert window.wizard_stack.currentIndex() == 2
        assert window.status_bar_label.text() == "Audit successfully completed!"
        assert "LOW (MINOR)" in window.report_browser.toHtml()


def test_mainwindow_handle_audit_error(q_app) -> None:
    window = MainWindow()
    
    with patch("ux_audit.ui.gui_runner.QMessageBox.exec") as mock_exec:
        window._handle_audit_error("API key validation failed", "Traceback here...")
        mock_exec.assert_called_once()
        # Verify it reverted back to config page
        assert window.wizard_stack.currentIndex() == 0


def test_mainwindow_start_audit_validation_no_api_key(q_app) -> None:
    window = MainWindow()
    window.url_input.setText("https://test.com")
    window.api_key_input.clear()
    
    with patch.object(QMessageBox, "warning") as mock_warning:
        window._start_audit_wizard()
        mock_warning.assert_called_once()
        assert window.wizard_stack.currentIndex() == 0


def test_mainwindow_start_audit_saves_api_key(q_app) -> None:
    mock_settings = MagicMock()
    with patch("ux_audit.ui.gui_runner.QSettings", return_value=mock_settings), \
         patch("ux_audit.ui.gui_runner.AuditWorker") as mock_worker:
        window = MainWindow()
        window.url_input.setText("https://test.com")
        window.api_key_input.setText("mock-persisted-api-key")
        window._start_audit_wizard()
        
        # Verify settings saved the key
        mock_settings.setValue.assert_called_with("api_key", "mock-persisted-api-key")
        # Verify stack transitioned to progress screen (index 1)
        assert window.wizard_stack.currentIndex() == 1


