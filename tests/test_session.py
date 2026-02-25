"""Tests for interactive session behaviors."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from askfind.interactive.session import InteractiveSession
from askfind.output.formatter import FileResult


def _make_session_for_actions(result: FileResult) -> InteractiveSession:
    session = InteractiveSession.__new__(InteractiveSession)
    session.config = SimpleNamespace(editor="vim", max_results=50)
    session.root = result.path.parent
    session.results = [result]
    session.client = MagicMock()
    return session


class TestInteractiveSessionInit:
    @patch("askfind.interactive.session.get_api_key", return_value=None)
    @patch("askfind.interactive.session.console.print")
    def test_init_raises_when_no_api_key(self, mock_print, mock_get_key, tmp_path):
        config = SimpleNamespace(base_url="https://api.example.com", model="x", max_results=50, editor="vim")
        with patch("askfind.interactive.session.LLMClient") as mock_client:
            try:
                InteractiveSession(config, tmp_path)
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("Expected SystemExit when API key is missing")
            mock_client.assert_not_called()
            mock_print.assert_called_once()


class TestInteractiveSessionActions:
    @patch("askfind.interactive.session.copy_path")
    def test_handle_action_copy_path(self, mock_copy_path, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)
        session = _make_session_for_actions(result)

        handled = session._handle_action("copy path 1")

        assert handled is True
        mock_copy_path.assert_called_once_with(result)

    @patch("askfind.interactive.session.open_in_editor")
    def test_handle_action_open_uses_config_editor(self, mock_open, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)
        session = _make_session_for_actions(result)
        session.config.editor = "nano"

        handled = session._handle_action("open 1")

        assert handled is True
        mock_open.assert_called_once_with(result, "nano")

    def test_handle_action_returns_false_for_non_action_text(self, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        session = _make_session_for_actions(FileResult.from_path(file_path))

        assert session._handle_action("find python files") is False


class TestInteractiveSessionSearch:
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_updates_results(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "matched.py"
        file_path.write_text("print('ok')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(editor="vim", max_results=50)
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()
        mock_walk.return_value = [file_path]

        session._search("python files")

        assert len(session.results) == 1
        assert session.results[0].path == file_path

    @patch("askfind.interactive.session.console.print")
    def test_search_handles_exceptions_without_raising(self, mock_print, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(editor="vim", max_results=50)
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.side_effect = RuntimeError("boom")

        session._search("python files")

        assert session.results == []
        mock_print.assert_called()
