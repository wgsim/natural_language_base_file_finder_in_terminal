"""Tests for interactive session behaviors."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from askfind.interactive.session import HELP_TEXT, InteractiveSession
from askfind.output.formatter import FileResult
from rich.table import Table


def _make_session_for_actions(result: FileResult) -> InteractiveSession:
    session = InteractiveSession.__new__(InteractiveSession)
    session.config = SimpleNamespace(
        base_url="https://api.example.com",
        model="test-model",
        editor="vim",
        max_results=50,
        cache_enabled=True,
        cache_ttl_seconds=300,
        respect_ignore_files=True,
        follow_symlinks=False,
        exclude_binary_files=True,
        parallel_workers=4,
    )
    session.root = result.path.parent
    session.results = [result]
    session.cache = None
    session.client = MagicMock()
    return session


def _make_session_for_run(tmp_path) -> InteractiveSession:
    session = InteractiveSession.__new__(InteractiveSession)
    session.config = SimpleNamespace(
        base_url="https://api.example.com",
        model="test-model",
        editor="vim",
        max_results=50,
        cache_enabled=True,
        cache_ttl_seconds=300,
        respect_ignore_files=True,
        follow_symlinks=False,
        exclude_binary_files=True,
        parallel_workers=4,
    )
    session.root = tmp_path.resolve()
    session.results = []
    session.cache = None
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

    @patch("askfind.interactive.session.SearchCache")
    @patch("askfind.interactive.session.LLMClient")
    @patch("askfind.interactive.session.get_api_key", return_value="sk-test")
    def test_init_creates_client_and_cache(self, mock_get_key, mock_client_cls, mock_cache_cls, tmp_path):
        config = SimpleNamespace(
            base_url="https://api.example.com",
            model="x",
            max_results=50,
            editor="vim",
            cache_enabled=True,
            cache_ttl_seconds=123,
        )

        session = InteractiveSession(config, tmp_path)

        mock_client_cls.assert_called_once_with(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="x",
        )
        mock_cache_cls.assert_called_once_with(ttl_seconds=123)
        assert session.cache is mock_cache_cls.return_value

    @patch("askfind.interactive.session.SearchCache")
    @patch("askfind.interactive.session.LLMClient")
    @patch("askfind.interactive.session.get_api_key", return_value="sk-test")
    def test_init_normalizes_invalid_cache_settings(
        self, mock_get_key, mock_client_cls, mock_cache_cls, tmp_path
    ):
        config = SimpleNamespace(
            base_url="https://api.example.com",
            model="x",
            max_results=50,
            editor="vim",
            cache_enabled="yes",
            cache_ttl_seconds=0,
        )

        InteractiveSession(config, tmp_path)

        mock_cache_cls.assert_called_once_with(ttl_seconds=300)

    @patch("askfind.interactive.session.SearchCache")
    @patch("askfind.interactive.session.LLMClient")
    @patch("askfind.interactive.session.get_api_key", return_value="sk-test")
    def test_init_disables_cache_when_false(self, mock_get_key, mock_client_cls, mock_cache_cls, tmp_path):
        config = SimpleNamespace(
            base_url="https://api.example.com",
            model="x",
            max_results=50,
            editor="vim",
            cache_enabled=False,
            cache_ttl_seconds=123,
        )

        session = InteractiveSession(config, tmp_path)

        mock_cache_cls.assert_not_called()
        assert session.cache is None

    @patch("askfind.interactive.session.SearchCache")
    @patch("askfind.interactive.session.LLMClient")
    @patch("askfind.interactive.session.get_api_key", return_value=None)
    def test_init_offline_mode_skips_api_key_and_llm(
        self, mock_get_key, mock_client_cls, mock_cache_cls, tmp_path
    ):
        config = SimpleNamespace(
            base_url="https://api.example.com",
            model="x",
            max_results=50,
            editor="vim",
            cache_enabled=True,
            cache_ttl_seconds=123,
            offline_mode=True,
        )

        session = InteractiveSession(config, tmp_path)

        mock_get_key.assert_not_called()
        mock_client_cls.assert_not_called()
        mock_cache_cls.assert_called_once_with(ttl_seconds=123)
        assert session.client is None


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

    @patch("askfind.interactive.session.copy_content")
    def test_handle_action_copy_content(self, mock_copy_content, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)
        session = _make_session_for_actions(result)

        handled = session._handle_action("copy content 1")

        assert handled is True
        mock_copy_content.assert_called_once_with(result)

    @patch("askfind.interactive.session.preview")
    def test_handle_action_preview(self, mock_preview, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)
        session = _make_session_for_actions(result)

        handled = session._handle_action("preview 1")

        assert handled is True
        mock_preview.assert_called_once_with(result)

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

    @patch("askfind.interactive.session.console.print")
    def test_run_offline_mode_without_client_does_not_fail(self, _mock_print, tmp_path):
        session = _make_session_for_run(tmp_path)
        session.client = None
        session.offline_mode = True
        prompt = MagicMock()
        prompt.prompt.side_effect = ["exit"]

        with patch("askfind.interactive.session.PromptSession", return_value=prompt):
            session.run()


class TestInteractiveSessionSearch:
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_updates_results(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "matched.py"
        file_path.write_text("print('ok')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()
        mock_walk.return_value = [file_path]

        session._search("python files")

        assert len(session.results) == 1
        assert session.results[0].path == file_path

    @patch("askfind.interactive.session.walk_and_filter", return_value=[])
    @patch("askfind.interactive.session.parse_llm_response", return_value={})
    def test_search_normalizes_invalid_config_values(self, mock_parse, mock_walk, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url=123,
            model=456,
            editor="vim",
            max_results="many",
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files="yes",
            follow_symlinks="no",
            exclude_binary_files="no",
            parallel_workers=0,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        session._search("python files")

        assert mock_walk.call_args.kwargs["max_results"] == 50
        assert mock_walk.call_args.kwargs["respect_ignore_files"] is True
        assert mock_walk.call_args.kwargs["follow_symlinks"] is False
        assert mock_walk.call_args.kwargs["exclude_binary_files"] is True
        assert mock_walk.call_args.kwargs["traversal_workers"] == 1

    @patch("askfind.interactive.session.console.print")
    def test_search_handles_exceptions_without_raising(self, mock_print, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
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
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
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
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
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

    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response", return_value={})
    def test_search_handles_cache_read_oserror(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "live.py"
        file_path.write_text("print('live')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'
        session.cache = MagicMock()
        session.cache.get.side_effect = OSError("cache read")
        mock_walk.return_value = [file_path]

        session._search("python files")

        session.client.extract_filters.assert_called_once_with("python files")
        assert len(session.results) == 1

    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response", return_value={})
    def test_search_falls_back_when_cached_path_inaccessible(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "live.py"
        file_path.write_text("print('live')\n")
        missing = tmp_path / "missing.py"

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'
        session.cache = MagicMock()
        session.cache.get.return_value = [missing]
        mock_walk.return_value = [file_path]

        session._search("python files")

        session.client.extract_filters.assert_called_once_with("python files")
        assert len(session.results) == 1
        assert session.results[0].path == file_path

    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response", return_value={})
    def test_search_handles_cache_write_oserror(self, mock_parse, mock_walk, tmp_path):
        file_path = tmp_path / "live.py"
        file_path.write_text("print('live')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'
        session.cache = MagicMock()
        session.cache.get.return_value = None
        session.cache.set.side_effect = OSError("cache write")
        mock_walk.return_value = [file_path]

        session._search("python files")

        session.cache.set.assert_called_once()
        assert len(session.results) == 1

    @patch("askfind.interactive.session.walk_and_filter", return_value=[])
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_passes_follow_symlinks_and_binary_options(self, mock_parse, mock_walk, tmp_path):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=False,
            follow_symlinks=True,
            exclude_binary_files=False,
            parallel_workers=8,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'

        mock_parse.return_value = MagicMock()

        session._search("python files")

        assert mock_walk.call_args.kwargs["respect_ignore_files"] is False
        assert mock_walk.call_args.kwargs["follow_symlinks"] is True
        assert mock_walk.call_args.kwargs["exclude_binary_files"] is False
        assert mock_walk.call_args.kwargs["traversal_workers"] == 8

    @patch("askfind.interactive.session.compute_root_fingerprint", return_value="root-fp")
    @patch("askfind.interactive.session.build_search_cache_key", return_value="cache-key")
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_cache_hit_skips_llm_and_walk(
        self, mock_parse, mock_walk, mock_key, mock_root_fingerprint, tmp_path
    ):
        file_path = tmp_path / "cached.py"
        file_path.write_text("print('cached')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.cache = MagicMock()
        session.cache.get.return_value = [file_path]

        session._search("python files")

        assert len(session.results) == 1
        assert session.results[0].path == file_path
        session.client.extract_filters.assert_not_called()
        mock_parse.assert_not_called()
        mock_walk.assert_not_called()
        session.cache.get.assert_called_once_with(key="cache-key", root_fingerprint="root-fp")

    @patch("askfind.interactive.session.compute_root_fingerprint", return_value="root-fp")
    @patch("askfind.interactive.session.build_search_cache_key", return_value="cache-key")
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_llm_response")
    def test_search_cache_miss_writes_cache(
        self, mock_parse, mock_walk, mock_key, mock_root_fingerprint, tmp_path
    ):
        file_path = tmp_path / "live.py"
        file_path.write_text("print('live')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.client = MagicMock()
        session.client.extract_filters.return_value = '{"ext": [".py"]}'
        session.cache = MagicMock()
        session.cache.get.return_value = None
        mock_parse.return_value = MagicMock()
        mock_walk.return_value = [file_path]

        session._search("python files")

        session.client.extract_filters.assert_called_once_with("python files")
        session.cache.get.assert_called_once_with(key="cache-key", root_fingerprint="root-fp")
        session.cache.set.assert_called_once_with(
            key="cache-key",
            root_fingerprint="root-fp",
            paths=[file_path],
        )

    @patch("askfind.interactive.session.console.print")
    @patch("askfind.interactive.session.walk_and_filter")
    def test_search_uses_heuristic_fallback_when_llm_http_error(self, mock_walk, mock_print, tmp_path):
        file_path = tmp_path / "fallback.py"
        file_path.write_text("print('fallback')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
        )
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = MagicMock()
        session.client.extract_filters.side_effect = httpx.ConnectError("offline")
        mock_walk.return_value = [file_path]

        session._search("python files")

        assert len(session.results) == 1
        inferred_filters = mock_walk.call_args.args[1]
        assert inferred_filters.ext == [".py"]
        mock_print.assert_any_call("[yellow]Warning: LLM unavailable; using heuristic fallback filters.[/yellow]")

    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_query_fallback")
    def test_search_offline_mode_uses_fallback_parser_directly(self, mock_fallback, mock_walk, tmp_path):
        file_path = tmp_path / "fallback.py"
        file_path.write_text("print('fallback')\n")

        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
            offline_mode=True,
        )
        session.offline_mode = True
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = None
        mock_fallback.return_value = SimpleNamespace(
            similarity_threshold=None,
            ext=[".py"],
            not_ext=None,
            name=None,
            not_name=None,
            path=None,
            not_path=None,
            regex=None,
            fuzzy=None,
            mod=None,
            mod_after=None,
            mod_before=None,
            size=None,
            has=None,
            similar=None,
            loc=None,
            complexity=None,
            lang=None,
            not_lang=None,
            license=None,
            not_license=None,
            tag=None,
            type="file",
            depth=None,
            perm=None,
        )
        mock_walk.return_value = [file_path]

        session._search("python files")

        assert len(session.results) == 1
        mock_fallback.assert_called_once_with("python files")
        mock_walk.assert_called_once()

    @patch("askfind.interactive.session.console.print")
    @patch("askfind.interactive.session.walk_and_filter")
    @patch("askfind.interactive.session.parse_query_fallback")
    @patch("askfind.interactive.session.has_meaningful_filters", return_value=False)
    def test_search_offline_mode_rejects_broad_query(
        self, _mock_meaningful, mock_fallback, mock_walk, mock_print, tmp_path
    ):
        session = InteractiveSession.__new__(InteractiveSession)
        session.config = SimpleNamespace(
            base_url="https://api.example.com",
            model="test-model",
            editor="vim",
            max_results=50,
            cache_enabled=True,
            cache_ttl_seconds=300,
            respect_ignore_files=True,
            follow_symlinks=False,
            exclude_binary_files=True,
            parallel_workers=4,
            offline_mode=True,
        )
        session.offline_mode = True
        session.root = tmp_path.resolve()
        session.results = []
        session.cache = None
        session.client = None
        mock_fallback.return_value = SimpleNamespace()

        session._search("find files")

        mock_walk.assert_not_called()
        mock_print.assert_any_call("[red]Error: --offline query is too broad; add at least one concrete filter.[/red]")
