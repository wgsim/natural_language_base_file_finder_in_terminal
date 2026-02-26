"""Tests for interactive session behaviors."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from askfind.interactive.session import HELP_TEXT, InteractiveSession
from askfind.output.formatter import FileResult
from rich.table import Table


def _make_session_for_actions(result: FileResult) -> InteractiveSession:
    session = InteractiveSession.__new__(InteractiveSession)
    session.config = SimpleNamespace(
        editor="vim",
        max_results=50,
        follow_symlinks=False,
        exclude_binary_files=True,
    )
    session.root = result.path.parent
    session.results = [result]
    session.client = MagicMock()
    return session


def _make_session_for_run(tmp_path) -> InteractiveSession:
    session = InteractiveSession.__new__(InteractiveSession)
    session.config = SimpleNamespace(
        editor="vim",
        max_results=50,
        follow_symlinks=False,
        exclude_binary_files=True,
    )
    session.root = tmp_path.resolve()
    session.results = []
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

    @patch("askfind.interactive.session.console.print")
    def test_handle_action_invalid_index_prints_error(self, mock_print, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        session = _make_session_for_actions(FileResult.from_path(file_path))

        handled = session._handle_action("preview 2")

        assert handled is True
        mock_print.assert_called_once_with("[red]Invalid index. Have 1 results.[/red]")


class TestInteractiveSessionRun:
    @patch("askfind.interactive.session.console.print")
    def test_run_help_command_then_exit(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = ["help", "exit"]

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action", return_value=False) as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_not_called()
        mock_search.assert_not_called()
        _mock_print.assert_any_call(HELP_TEXT)
        session.client.close.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    def test_run_skips_empty_input_then_quit(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = ["   ", "quit"]

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action", return_value=False) as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_not_called()
        mock_search.assert_not_called()
        session.client.close.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    def test_run_continues_when_action_is_handled(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = ["copy path 1", "exit"]

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action", return_value=True) as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_called_once_with("copy path 1")
        mock_search.assert_not_called()
        session.client.close.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    def test_run_calls_search_for_query(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = ["python files", "quit"]

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action", return_value=False) as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_called_once_with("python files")
        mock_search.assert_called_once_with("python files")
        session.client.close.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    def test_run_handles_eoferror_and_closes_client(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = EOFError

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action") as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_not_called()
        mock_search.assert_not_called()
        session.client.close.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    def test_run_handles_keyboardinterrupt_and_closes_client(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        prompt = MagicMock()
        prompt.prompt.side_effect = KeyboardInterrupt

        with (
            patch("askfind.interactive.session.PromptSession", return_value=prompt),
            patch.object(session, "_handle_action") as mock_handle_action,
            patch.object(session, "_search") as mock_search,
        ):
            session.run()

        mock_handle_action.assert_not_called()
        mock_search.assert_not_called()
        session.client.close.assert_called_once()


class TestInteractiveSessionSearch:
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_updates_results(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "matched.py"
        file_path.write_text("print('ok')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            editor="vim",
            max_results=50,
            follow_symlinks=False,
            exclude_binary_files=True,
        )
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
        session.config = SimpleNamespace(
            editor="vim",
            max_results=50,
            follow_symlinks=False,
            exclude_binary_files=True,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.side_effect = RuntimeError("boom")

        session._search("python files")

        assert session.results == []
        mock_print.assert_called()

    @patch("askfind.interactive.session.walk_and_filter", return_value=[])
    @patch("askfind.interactive.session.parse_llm_response")
    @patch("askfind.interactive.session.console.print")
    def test_search_prints_no_results_message(self, mock_print, mock_parse, _mock_walk, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            editor="vim",
            max_results=50,
            follow_symlinks=False,
            exclude_binary_files=True,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()

        session._search("python files")

        assert session.results == []
        mock_print.assert_any_call("[dim]No files found.[/dim]")

    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    @patch("askfind.interactive.session.console.print")
    def test_search_prints_table_for_results(self, mock_print, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "matched.py"
        file_path.write_text("print('ok')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            editor="vim",
            max_results=50,
            follow_symlinks=False,
            exclude_binary_files=True,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()
        mock_walk.return_value = [file_path]

        session._search("python files")

        mock_print.assert_any_call("[dim]Found 1 file(s):[/dim]")
        table_calls = [call_ for call_ in mock_print.call_args_list if call_.args and isinstance(call_.args[0], Table)]
        assert len(table_calls) == 1
        assert table_calls[0].args[0].row_count == 1
        assert any(call_.args == () for call_ in mock_print.call_args_list)

    @patch("askfind.interactive.session.walk_and_filter", return_value=[])
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_passes_follow_symlinks_and_binary_options(self, mock_parse, mock_walk, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            editor="vim",
            max_results=50,
            follow_symlinks=True,
            exclude_binary_files=False,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()

        session._search("python files")

        assert mock_walk.call_args.kwargs["follow_symlinks"] is True
        assert mock_walk.call_args.kwargs["exclude_binary_files"] is False
