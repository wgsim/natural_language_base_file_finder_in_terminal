"""Tests for CLI argument parsing and entry point."""

import json
import types
import httpx
from unittest.mock import MagicMock, patch

import pytest

from askfind.cli import _validate_base_url, build_parser, main


def _make_mock_config(default_root="."):
    mock_config = MagicMock()
    mock_config.base_url = "https://api.example.com"
    mock_config.model = "test-model"
    mock_config.default_root = str(default_root)
    mock_config.max_results = 50
    mock_config.parallel_workers = 4
    mock_config.cache_enabled = True
    mock_config.cache_ttl_seconds = 300
    mock_config.respect_ignore_files = True
    mock_config.follow_symlinks = False
    mock_config.exclude_binary_files = True
    mock_config.editor = "vim"
    return mock_config


def _setup_mock_llm_client(mock_llm_cls, raw_response='{"ext": [".py"]}', extract_side_effect=None):
    mock_client = MagicMock()
    if extract_side_effect is None:
        mock_client.extract_filters.return_value = raw_response
    else:
        mock_client.extract_filters.side_effect = extract_side_effect
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=None)
    mock_llm_cls.return_value = mock_client
    return mock_client


@pytest.fixture(autouse=True)
def _default_query_index_fallback(monkeypatch):
    monkeypatch.setattr("askfind.cli.query_index", lambda **kwargs: None, raising=False)


class TestBuildParser:
    def test_query_positional(self):
        parser = build_parser()
        args = parser.parse_args(["find python files"])
        assert args.query == "find python files"

    def test_interactive_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-i"])
        assert args.interactive is True

    def test_root_default(self):
        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.root == "."

    def test_root_override(self):
        parser = build_parser()
        args = parser.parse_args(["test", "-r", "/tmp"])
        assert args.root == "/tmp"

    def test_max_results_default(self):
        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.max_results == 0  # 0 means use config value

    def test_workers_default(self):
        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.workers == 0

    def test_workers_override(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--workers", "8"])
        assert args.workers == 8

    def test_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "-v"])
        assert args.verbose is True

    def test_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--json"])
        assert args.json_output is True

    def test_no_rerank_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--no-rerank"])
        assert args.no_rerank is True

    def test_no_cache_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--no-cache"])
        assert args.no_cache is True

    def test_cache_stats_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--cache-stats"])
        assert args.cache_stats is True

    def test_no_ignore_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--no-ignore"])
        assert args.no_ignore is True

    def test_follow_symlinks_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--follow-symlinks"])
        assert args.follow_symlinks is True

    def test_include_binary_flag(self):
        parser = build_parser()
        args = parser.parse_args(["test", "--include-binary"])
        assert args.include_binary is True


class TestValidateBaseUrl:
    def test_accepts_https_remote(self):
        is_valid, error = _validate_base_url("https://openrouter.ai/api/v1")
        assert is_valid is True
        assert error == ""

    def test_rejects_http_remote(self):
        is_valid, error = _validate_base_url("http://example.com/v1")
        assert is_valid is False
        assert "localhost" in error

    def test_accepts_http_localhost(self):
        is_valid, error = _validate_base_url("http://localhost:11434/v1")
        assert is_valid is True
        assert error == ""

    def test_rejects_invalid_scheme(self):
        is_valid, error = _validate_base_url("ftp://example.com")
        assert is_valid is False
        assert "http:// or https://" in error

    def test_handles_urlparse_exception(self):
        is_valid, error = _validate_base_url(123)  # type: ignore[arg-type]
        assert is_valid is False
        assert "Invalid URL format" in error


class TestMain:
    def test_no_args_returns_2(self):
        result = main([])
        assert result == 2

    @patch("askfind.cli.get_api_key", return_value=None)
    def test_query_without_api_key_returns_2(self, mock_get_key):
        result = main(["find python files"])
        assert result == 2  # Returns 2 when no API key

    @patch("askfind.interactive.pane.spawn_interactive_pane", return_value=False)
    @patch("askfind.interactive.session.InteractiveSession")
    def test_interactive_returns_0(self, mock_session_cls, mock_spawn):
        # Mock the InteractiveSession instance
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        result = main(["-i"])
        assert result == 0
        # Verify spawn was called and session.run() was called
        mock_spawn.assert_called_once()
        mock_session.run.assert_called_once()


class TestMainIntegration:
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_single_command_mode(self, mock_config_cls, mock_get_key, mock_llm_cls, tmp_path):
        # Setup test files
        (tmp_path / "test.py").write_text("hello")
        (tmp_path / "readme.md").write_text("# docs")

        mock_config = MagicMock()
        mock_config.base_url = "http://test"
        mock_config.model = "test-model"
        mock_config.max_results = 50
        mock_config.parallel_workers = 4
        mock_config_cls.return_value = mock_config

        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{"ext": [".py"]}'
        # Support context manager protocol for `with LLMClient(...) as client:`
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_llm_cls.return_value = mock_client

        result = main(["python files", "--root", str(tmp_path)])
        assert result == 0
        mock_client.extract_filters.assert_called_once_with("python files")

    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_uses_config_default_root_when_root_not_overridden(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_walk, tmp_path
    ):
        default_root = tmp_path / "default-root"
        default_root.mkdir()
        result_file = default_root / "matched.py"
        result_file.write_text("print('ok')\n")

        mock_config = MagicMock()
        mock_config.base_url = "http://test"
        mock_config.model = "test-model"
        mock_config.max_results = 50
        mock_config.parallel_workers = 4
        mock_config.default_root = str(default_root)
        mock_config_cls.return_value = mock_config

        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{"ext": [".py"]}'
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_llm_cls.return_value = mock_client
        mock_walk.return_value = [result_file]

        result = main(["python files"])

        assert result == 0
        assert mock_walk.call_args.args[0] == default_root.resolve()

    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_explicit_root_overrides_config_default_root(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_walk, tmp_path
    ):
        default_root = tmp_path / "default-root"
        default_root.mkdir()
        explicit_root = tmp_path / "explicit-root"
        explicit_root.mkdir()
        result_file = explicit_root / "matched.py"
        result_file.write_text("print('ok')\n")

        mock_config = MagicMock()
        mock_config.base_url = "http://test"
        mock_config.model = "test-model"
        mock_config.max_results = 50
        mock_config.parallel_workers = 4
        mock_config.default_root = str(default_root)
        mock_config_cls.return_value = mock_config

        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{"ext": [".py"]}'
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_llm_cls.return_value = mock_client
        mock_walk.return_value = [result_file]

        result = main(["python files", "--root", str(explicit_root)])

        assert result == 0
        assert mock_walk.call_args.args[0] == explicit_root.resolve()


class TestConfigSubcommand:
    @patch("askfind.cli.Config.from_file")
    def test_config_set_unknown_key_returns_2(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "unknown_key", "value"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_rejects_invalid_base_url(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "base_url", "http://example.com"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_rejects_non_integer_max_results(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "max_results", "many"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_rejects_non_integer_parallel_workers(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "parallel_workers", "many"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_max_results_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "max_results", "25"])
        assert result == 0
        assert mock_config.max_results == 25
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_parallel_workers_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "parallel_workers", "8"])
        assert result == 0
        assert mock_config.parallel_workers == 8
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_parallel_workers_must_be_positive(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "parallel_workers", "0"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_cache_ttl_seconds_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "cache_ttl_seconds", "120"])
        assert result == 0
        assert mock_config.cache_ttl_seconds == 120
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_cache_ttl_seconds_must_be_positive(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "cache_ttl_seconds", "0"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_cache_enabled_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "cache_enabled", "false"])
        assert result == 0
        assert mock_config.cache_enabled is False
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_respect_ignore_files_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "respect_ignore_files", "false"])
        assert result == 0
        assert mock_config.respect_ignore_files is False
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_respect_ignore_files_invalid_value_returns_2(self, mock_config_cls):
        mock_config_cls.return_value = MagicMock()
        result = main(["config", "set", "respect_ignore_files", "maybe"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    def test_config_set_follow_symlinks_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "follow_symlinks", "true"])
        assert result == 0
        assert mock_config.follow_symlinks is True
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    def test_config_set_exclude_binary_files_success(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main(["config", "set", "exclude_binary_files", "false"])
        assert result == 0
        assert mock_config.exclude_binary_files is False
        mock_config.save.assert_called_once()

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value=None)
    def test_config_models_without_key_returns_2(self, mock_get_key, mock_config_cls):
        mock_config = MagicMock()
        mock_config.base_url = "https://api.example.com"
        mock_config_cls.return_value = mock_config
        result = main(["config", "models"])
        assert result == 2

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("httpx.get")
    def test_config_models_http_status_error_returns_3(self, mock_get, mock_get_key, mock_config_cls):
        mock_config = MagicMock()
        mock_config.base_url = "https://api.example.com"
        mock_config_cls.return_value = mock_config

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Too many requests",
            request=MagicMock(),
            response=mock_response,
        )
        mock_get.return_value = mock_response

        result = main(["config", "models"])
        assert result == 3


class TestConfigSubcommandAdditional:
    @patch("askfind.cli.get_api_key", return_value="sk-test-1234")
    @patch("askfind.cli.Config.from_file")
    def test_config_show_returns_0(self, mock_config_cls, mock_get_key):
        mock_config_cls.return_value = _make_mock_config()

        mock_console = MagicMock()
        mock_table = MagicMock()
        console_module = types.ModuleType("rich.console")
        table_module = types.ModuleType("rich.table")
        console_module.Console = MagicMock(return_value=mock_console)
        table_module.Table = MagicMock(return_value=mock_table)

        with patch.dict(
            "sys.modules",
            {
                "rich": types.ModuleType("rich"),
                "rich.console": console_module,
                "rich.table": table_module,
            },
        ):
            result = main(["config", "show"])

        assert result == 0
        mock_table.add_row.assert_any_call("api_key", "****1234")
        mock_console.print.assert_called_once_with(mock_table)

    @patch("askfind.cli.set_api_key")
    @patch("getpass.getpass", return_value="sk-new")
    @patch("askfind.cli.Config.from_file")
    def test_config_set_key_success(self, mock_config_cls, mock_getpass, mock_set_api_key, capsys):
        mock_config_cls.return_value = _make_mock_config()

        result = main(["config", "set-key"])
        captured = capsys.readouterr()

        assert result == 0
        mock_getpass.assert_called_once()
        mock_set_api_key.assert_called_once_with("sk-new")
        assert "API key stored in system keychain." in captured.out

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("httpx.get")
    def test_config_models_success_returns_0(self, mock_get, mock_get_key, mock_config_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"id": "model-a"}, {"id": "model-b"}, {"id": "unknown-idless"}]
        }
        mock_get.return_value = mock_response

        result = main(["config", "models"])
        captured = capsys.readouterr()

        assert result == 0
        assert "model-a" in captured.out
        assert "model-b" in captured.out

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("httpx.get", side_effect=httpx.ConnectError("connection failed"))
    def test_config_models_connect_error_returns_3(self, mock_get, mock_get_key, mock_config_cls, capsys):
        mock_config = _make_mock_config()
        mock_config_cls.return_value = mock_config

        result = main(["config", "models"])
        captured = capsys.readouterr()

        assert result == 3
        assert f"Cannot connect to API server at {mock_config.base_url}" in captured.err

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("httpx.get", side_effect=httpx.TimeoutException("timed out"))
    def test_config_models_timeout_error_returns_3(self, mock_get, mock_get_key, mock_config_cls, capsys):
        mock_config = _make_mock_config()
        mock_config_cls.return_value = mock_config

        result = main(["config", "models"])
        captured = capsys.readouterr()

        assert result == 3
        assert f"Cannot connect to API server at {mock_config.base_url}" in captured.err

    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("httpx.get", side_effect=RuntimeError("boom"))
    def test_config_models_generic_exception_returns_3(self, mock_get, mock_get_key, mock_config_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()

        result = main(["config", "models"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Error: RuntimeError" in captured.err


class TestMainAdditionalBranches:
    @patch("askfind.interactive.session.InteractiveSession")
    @patch("askfind.cli.Config.from_file")
    def test_interactive_session_flag_runs_session(self, mock_config_cls, mock_session_cls, tmp_path):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config_cls.return_value = mock_config
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        result = main(["--interactive-session", "--root", str(tmp_path)])

        assert result == 0
        mock_session_cls.assert_called_once_with(mock_config, tmp_path.resolve())
        mock_session.run.assert_called_once()

    @patch("askfind.interactive.session.InteractiveSession")
    @patch("askfind.interactive.pane.spawn_interactive_pane", return_value=True)
    @patch("askfind.cli.Config.from_file")
    def test_interactive_pane_spawned_returns_0(
        self, mock_config_cls, mock_spawn, mock_session_cls, tmp_path
    ):
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)

        result = main(["-i"])

        assert result == 0
        mock_spawn.assert_called_once()
        mock_session_cls.assert_not_called()

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_api_key_flag_prints_warning(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path, capsys
    ):
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--api-key", "sk-inline", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 1
        assert "Warning: --api-key exposes your key" in captured.err
        mock_get_key.assert_called_once_with(cli_key="sk-inline")

    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_query_too_long_returns_2(self, mock_config_cls, mock_get_key, mock_llm_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()
        result = main(["x" * 1001])
        captured = capsys.readouterr()

        assert result == 2
        assert "maximum length of 1000" in captured.err
        mock_llm_cls.assert_not_called()

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_no_results_returns_1(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--root", str(tmp_path)])

        assert result == 1

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_config_respect_ignore_files_is_used_for_search(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.respect_ignore_files = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--root", str(tmp_path)])

        assert result == 1
        assert mock_walk.call_args.kwargs["respect_ignore_files"] is False

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_no_ignore_flag_overrides_config(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.respect_ignore_files = True
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--no-ignore", "--root", str(tmp_path)])

        assert result == 1
        assert mock_walk.call_args.kwargs["respect_ignore_files"] is False

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_follow_symlinks_flag_overrides_config(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.follow_symlinks = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--follow-symlinks", "--root", str(tmp_path)])

        assert result == 1
        assert mock_walk.call_args.kwargs["follow_symlinks"] is True

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_include_binary_flag_disables_binary_exclusion(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.exclude_binary_files = True
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--include-binary", "--root", str(tmp_path)])

        assert result == 1
        assert mock_walk.call_args.kwargs["exclude_binary_files"] is False

    @patch("askfind.cli.SearchCache")
    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_no_cache_flag_skips_cache_layer(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_cache_cls,
        tmp_path,
    ):
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--no-cache", "--root", str(tmp_path)])

        assert result == 1
        mock_cache_cls.assert_not_called()

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_stats_flag_prints_disabled_when_cache_off(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path, capsys
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--cache-stats", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 1
        assert "cache: disabled" in captured.err
        assert "index: hits=0 fallbacks=1" in captured.err

    @patch("askfind.cli.compute_root_fingerprint", return_value="root-fp")
    @patch("askfind.cli.build_search_cache_key", return_value="cache-key")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.SearchCache")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_stats_flag_prints_hits_misses_sets(
        self,
        mock_config_cls,
        mock_get_key,
        mock_cache_cls,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_build_key,
        mock_root_fingerprint,
        tmp_path,
        capsys,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = True
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        cache = MagicMock()
        cache.get.return_value = None
        cache.stats.return_value = {"hits": 0, "misses": 1, "sets": 1}
        mock_cache_cls.return_value = cache

        result = main(["query", "--cache-stats", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 0
        assert "cache: hits=0 misses=1 sets=1" in captured.err
        assert "index: hits=0 fallbacks=1" in captured.err

    @patch("askfind.cli.query_index")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_stats_prints_index_hit(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_query_index,
        tmp_path,
        capsys,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_query_index.return_value = [file_a]

        result = main(["query", "--cache-stats", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 0
        assert "index: hits=1 fallbacks=0 reasons=none" in captured.err
        mock_walk.assert_not_called()

    @patch("askfind.cli.query_index")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_stats_prints_index_fallback_reason(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_query_index,
        tmp_path,
        capsys,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        def fake_query_index(**kwargs):
            diagnostics = kwargs.get("diagnostics")
            if diagnostics is not None:
                diagnostics.fallback_reason = "stale_index"
            return None

        mock_query_index.side_effect = fake_query_index

        result = main(["query", "--cache-stats", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 0
        assert "index: hits=0 fallbacks=1 reasons=stale_index:1" in captured.err

    @patch("askfind.cli.compute_root_fingerprint", return_value="root-fp")
    @patch("askfind.cli.build_search_cache_key", return_value="cache-key")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response")
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.SearchCache")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_hit_skips_llm_and_walk(
        self,
        mock_config_cls,
        mock_get_key,
        mock_cache_cls,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_build_key,
        mock_root_fingerprint,
        tmp_path,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = True
        mock_config_cls.return_value = mock_config

        cache = MagicMock()
        cache.get.return_value = [file_a]
        mock_cache_cls.return_value = cache

        result = main(["query", "--root", str(tmp_path)])

        assert result == 0
        mock_llm_cls.assert_not_called()
        mock_parse.assert_not_called()
        mock_walk.assert_not_called()
        cache.get.assert_called_once_with(key="cache-key", root_fingerprint="root-fp")

    @patch("askfind.cli.query_index")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_index_hit_skips_walker(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_query_index,
        tmp_path,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_query_index.return_value = [file_a]

        result = main(["query", "--root", str(tmp_path)])

        assert result == 0
        mock_query_index.assert_called_once()
        mock_walk.assert_not_called()

    @patch("askfind.cli.query_index", return_value=None)
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_index_miss_falls_back_to_walker(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_query_index,
        tmp_path,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = False
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        result = main(["query", "--root", str(tmp_path)])

        assert result == 0
        mock_query_index.assert_called_once()
        mock_walk.assert_called_once()

    @patch("askfind.cli.compute_root_fingerprint", return_value="root-fp")
    @patch("askfind.cli.build_search_cache_key", return_value="cache-key")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.SearchCache")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_cache_miss_stores_paths(
        self,
        mock_config_cls,
        mock_get_key,
        mock_cache_cls,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_build_key,
        mock_root_fingerprint,
        tmp_path,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.cache_enabled = True
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        cache = MagicMock()
        cache.get.return_value = None
        mock_cache_cls.return_value = cache

        result = main(["query", "--root", str(tmp_path)])

        assert result == 0
        cache.get.assert_called_once_with(key="cache-key", root_fingerprint="root-fp")
        cache.set.assert_called_once_with(
            key="cache-key",
            root_fingerprint="root-fp",
            paths=[file_a],
        )

    @patch("askfind.cli.walk_and_filter", return_value=[])
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_workers_flag_overrides_config_parallel_workers(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, tmp_path
    ):
        mock_config = _make_mock_config(default_root=tmp_path)
        mock_config.parallel_workers = 2
        mock_config_cls.return_value = mock_config
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query", "--workers", "8", "--root", str(tmp_path)])

        assert result == 1
        assert mock_walk.call_args.kwargs["traversal_workers"] == 8

    @patch("askfind.cli.Config.from_file")
    def test_negative_workers_cli_returns_2(self, mock_config_cls):
        mock_config_cls.return_value = _make_mock_config()

        result = main(["query", "--workers", "-1"])

        assert result == 2

    @patch("askfind.search.reranker.rerank_results")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_no_rerank_flag_skips_reranker(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_rerank,
        tmp_path,
    ):
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text("a")
        file_b.write_text("b")
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a, file_b]

        result = main(["query", "--no-rerank", "--root", str(tmp_path)])

        assert result == 0
        mock_rerank.assert_not_called()

    @patch("askfind.cli.format_plain", return_value="plain-output")
    @patch("askfind.cli.format_verbose", return_value="verbose-output")
    @patch("askfind.cli.format_json", return_value="json-output")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_json_output_uses_json_formatter(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_format_json,
        mock_format_verbose,
        mock_format_plain,
        tmp_path,
        capsys,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        result = main(["query", "--json", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 0
        assert captured.out.strip() == "json-output"
        mock_format_json.assert_called_once()
        mock_format_verbose.assert_not_called()
        mock_format_plain.assert_not_called()

    @patch("askfind.cli.format_plain", return_value="plain-output")
    @patch("askfind.cli.format_verbose", return_value="verbose-output")
    @patch("askfind.cli.format_json", return_value="json-output")
    @patch("askfind.cli.walk_and_filter")
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_verbose_output_uses_verbose_formatter(
        self,
        mock_config_cls,
        mock_get_key,
        mock_llm_cls,
        mock_parse,
        mock_walk,
        mock_format_json,
        mock_format_verbose,
        mock_format_plain,
        tmp_path,
        capsys,
    ):
        file_a = tmp_path / "a.py"
        file_a.write_text("a")
        mock_config_cls.return_value = _make_mock_config(default_root=tmp_path)
        _setup_mock_llm_client(mock_llm_cls)
        mock_walk.return_value = [file_a]

        result = main(["query", "--verbose", "--root", str(tmp_path)])
        captured = capsys.readouterr()

        assert result == 0
        assert captured.out.strip() == "verbose-output"
        mock_format_verbose.assert_called_once()
        mock_format_json.assert_not_called()
        mock_format_plain.assert_not_called()


class TestIndexSubcommand:
    @patch("askfind.cli.build_index")
    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.get_api_key")
    def test_index_build_uses_config_root_and_prints_summary(
        self, mock_get_key, mock_config_cls, mock_build_index, tmp_path, capsys
    ):
        default_root = tmp_path / "default-root"
        default_root.mkdir()

        mock_config = _make_mock_config(default_root=default_root)
        mock_config.parallel_workers = 3
        mock_config_cls.return_value = mock_config
        mock_build_index.return_value = types.SimpleNamespace(
            root=default_root.resolve(),
            file_count=12,
        )

        result = main(["index", "build"])
        captured = capsys.readouterr()

        assert result == 0
        assert "Index built for" in captured.out
        assert "files=12" in captured.out
        mock_get_key.assert_not_called()

        kwargs = mock_build_index.call_args.kwargs
        assert kwargs["root"] == default_root.resolve()
        assert kwargs["options"].respect_ignore_files is True
        assert kwargs["options"].follow_symlinks is False
        assert kwargs["options"].exclude_binary_files is True
        assert kwargs["options"].traversal_workers == 3

    @patch("askfind.cli.build_index")
    @patch("askfind.cli.Config.from_file")
    def test_index_build_respects_traversal_flags(
        self, mock_config_cls, mock_build_index, tmp_path
    ):
        explicit_root = tmp_path / "explicit-root"
        explicit_root.mkdir()

        mock_config = _make_mock_config(default_root=tmp_path / "ignored-default")
        mock_config.respect_ignore_files = True
        mock_config.follow_symlinks = False
        mock_config.exclude_binary_files = True
        mock_config.parallel_workers = 2
        mock_config_cls.return_value = mock_config
        mock_build_index.return_value = types.SimpleNamespace(
            root=explicit_root.resolve(),
            file_count=3,
        )

        result = main(
            [
                "index",
                "build",
                "--root",
                str(explicit_root),
                "--workers",
                "8",
                "--no-ignore",
                "--follow-symlinks",
                "--include-binary",
            ]
        )

        assert result == 0
        kwargs = mock_build_index.call_args.kwargs
        assert kwargs["root"] == explicit_root.resolve()
        assert kwargs["options"].respect_ignore_files is False
        assert kwargs["options"].follow_symlinks is True
        assert kwargs["options"].exclude_binary_files is False
        assert kwargs["options"].traversal_workers == 8

    @patch("askfind.cli.Config.from_file")
    def test_index_build_negative_workers_returns_2(self, mock_config_cls):
        mock_config_cls.return_value = _make_mock_config()

        result = main(["index", "build", "--workers", "-1"])

        assert result == 2

    @patch("askfind.cli.update_index")
    @patch("askfind.cli.Config.from_file")
    def test_index_update_calls_update_handler(self, mock_config_cls, mock_update_index, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        mock_config_cls.return_value = _make_mock_config(default_root=root)
        mock_update_index.return_value = types.SimpleNamespace(root=root.resolve(), file_count=7)

        result = main(["index", "update", "--root", str(root)])

        assert result == 0
        mock_update_index.assert_called_once()

    @patch("askfind.cli.get_index_status")
    @patch("askfind.cli.Config.from_file")
    def test_index_status_prints_exists_files_and_stale(
        self, mock_config_cls, mock_get_status, tmp_path, capsys
    ):
        root = tmp_path / "root"
        root.mkdir()
        mock_config_cls.return_value = _make_mock_config(default_root=root)
        mock_get_status.return_value = types.SimpleNamespace(
            root=root.resolve(),
            exists=True,
            file_count=5,
            stale=False,
        )

        result = main(["index", "status", "--root", str(root)])
        captured = capsys.readouterr()

        assert result == 0
        assert "exists=yes" in captured.out
        assert "files=5" in captured.out
        assert "stale=no" in captured.out

    @patch("askfind.cli.clear_index")
    @patch("askfind.cli.Config.from_file")
    def test_index_clear_reports_missing_index(self, mock_config_cls, mock_clear_index, tmp_path, capsys):
        root = tmp_path / "root"
        root.mkdir()
        mock_config_cls.return_value = _make_mock_config(default_root=root)
        mock_clear_index.return_value = types.SimpleNamespace(
            root=root.resolve(),
            cleared=False,
        )

        result = main(["index", "clear", "--root", str(root)])
        captured = capsys.readouterr()

        assert result == 0
        assert "No index found for" in captured.out


class TestMainExceptionHandling:
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_keyboard_interrupt_returns_130(self, mock_config_cls, mock_get_key, mock_llm_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls, extract_side_effect=KeyboardInterrupt())

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 130
        assert "Search cancelled." in captured.err

    @patch("askfind.cli.walk_and_filter", side_effect=FileNotFoundError())
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_file_not_found_returns_3(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, capsys
    ):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls)

        missing_root = "/definitely/missing/path"
        result = main(["query", "--root", missing_root])
        captured = capsys.readouterr()

        assert result == 3
        assert missing_root in captured.err

    @patch("askfind.cli.walk_and_filter", side_effect=PermissionError())
    @patch("askfind.cli.parse_llm_response", return_value={})
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_permission_error_returns_3(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, mock_walk, capsys
    ):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Permission denied accessing search root" in captured.err

    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_http_status_error_returns_3(self, mock_config_cls, mock_get_key, mock_llm_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()
        mock_response = MagicMock()
        mock_response.status_code = 503
        error = httpx.HTTPStatusError("bad status", request=MagicMock(), response=mock_response)
        _setup_mock_llm_client(mock_llm_cls, extract_side_effect=error)

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "HTTP 503" in captured.err

    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_connect_error_returns_3(self, mock_config_cls, mock_get_key, mock_llm_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls, extract_side_effect=httpx.ConnectError("connect fail"))

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Cannot connect to API server" in captured.err

    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_timeout_exception_returns_3(self, mock_config_cls, mock_get_key, mock_llm_cls, capsys):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls, extract_side_effect=httpx.TimeoutException("timeout"))

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Cannot connect to API server" in captured.err

    @patch("askfind.cli.parse_llm_response", side_effect=json.JSONDecodeError("bad", "doc", 0))
    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_json_decode_error_returns_3(
        self, mock_config_cls, mock_get_key, mock_llm_cls, mock_parse, capsys
    ):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls)

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Invalid response from LLM API" in captured.err

    @patch("askfind.cli.LLMClient")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    @patch("askfind.cli.logger.exception")
    def test_unexpected_error_returns_3(
        self, mock_log_exception, mock_config_cls, mock_get_key, mock_llm_cls, capsys
    ):
        mock_config_cls.return_value = _make_mock_config()
        _setup_mock_llm_client(mock_llm_cls, extract_side_effect=RuntimeError("boom"))

        result = main(["query"])
        captured = capsys.readouterr()

        assert result == 3
        assert "Error: Unexpected internal error. Run with --debug for details." in captured.err
        mock_log_exception.assert_called_once()
