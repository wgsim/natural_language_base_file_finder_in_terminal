"""Tests for CLI argument parsing and entry point."""

from unittest.mock import patch, MagicMock

from askfind.cli import build_parser, main
from askfind.search.filters import SearchFilters


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
