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
    def test_query_returns_0(self, mock_get_key):
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

    @patch("httpx.get")
    @patch("askfind.cli.get_api_key", return_value="sk-test")
    @patch("askfind.cli.Config.from_file")
    def test_config_models_filters_by_provider(self, mock_config_cls, mock_get_key, mock_get, capsys):
        mock_config = MagicMock()
        mock_config.base_url = "http://test"
        mock_config.model = "test-model"
        mock_config.max_results = 50
        mock_config_cls.return_value = mock_config

        mock_get.return_value.json.return_value = {
            "data": [
                {"id": "openai/gpt-4o"},
                {"id": "anthropic/claude-3.5"},
            ]
        }
        mock_get.return_value.raise_for_status.return_value = None

        result = main(["config", "models", "--provider", "openai"])
        assert result == 0
        out = capsys.readouterr().out
        assert "openai/gpt-4o" in out
        assert "anthropic/claude-3.5" not in out


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
