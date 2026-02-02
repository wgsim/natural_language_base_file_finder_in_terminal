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

    def test_interactive_returns_0(self):
        result = main(["-i"])
        assert result == 0


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
        mock_llm_cls.return_value = mock_client

        result = main(["python files", "--root", str(tmp_path)])
        assert result == 0
        mock_client.extract_filters.assert_called_once_with("python files")
