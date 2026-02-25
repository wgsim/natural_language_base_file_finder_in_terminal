"""Tests for logging configuration utilities."""

from unittest.mock import MagicMock, patch

from askfind.logging_config import get_logger, setup_logging


class TestSetupLogging:
    @patch("askfind.logging_config.logging.basicConfig")
    @patch("askfind.logging_config.logging.getLogger")
    def test_default_configuration_uses_warning_level(self, mock_get_logger, mock_basic_config):
        httpx_logger = MagicMock()
        httpcore_logger = MagicMock()
        mock_get_logger.side_effect = [httpx_logger, httpcore_logger]

        setup_logging()

        kwargs = mock_basic_config.call_args.kwargs
        assert kwargs["level"] == 30  # logging.WARNING
        assert kwargs["format"] == "%(levelname)s: %(message)s"
        httpx_logger.setLevel.assert_called_once_with(30)  # logging.WARNING
        httpcore_logger.setLevel.assert_called_once_with(30)  # logging.WARNING

    @patch("askfind.logging_config.logging.basicConfig")
    @patch("askfind.logging_config.logging.getLogger")
    def test_verbose_configuration_uses_info_level(self, mock_get_logger, mock_basic_config):
        httpx_logger = MagicMock()
        httpcore_logger = MagicMock()
        mock_get_logger.side_effect = [httpx_logger, httpcore_logger]

        setup_logging(verbose=True)

        kwargs = mock_basic_config.call_args.kwargs
        assert kwargs["level"] == 20  # logging.INFO
        assert kwargs["format"] == "%(levelname)s: %(message)s"
        httpx_logger.setLevel.assert_called_once_with(30)
        httpcore_logger.setLevel.assert_called_once_with(30)

    @patch("askfind.logging_config.logging.basicConfig")
    @patch("askfind.logging_config.logging.getLogger")
    def test_debug_configuration_overrides_verbose_and_uses_debug_format(
        self, mock_get_logger, mock_basic_config
    ):
        httpx_logger = MagicMock()
        httpcore_logger = MagicMock()
        mock_get_logger.side_effect = [httpx_logger, httpcore_logger]

        setup_logging(verbose=True, debug=True)

        kwargs = mock_basic_config.call_args.kwargs
        assert kwargs["level"] == 10  # logging.DEBUG
        assert kwargs["format"] == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        httpx_logger.setLevel.assert_called_once_with(30)
        httpcore_logger.setLevel.assert_called_once_with(30)


class TestGetLogger:
    @patch("askfind.logging_config.logging.getLogger")
    def test_get_logger_delegates_to_logging_module(self, mock_get_logger):
        expected_logger = MagicMock()
        mock_get_logger.return_value = expected_logger

        logger = get_logger("askfind.test")

        assert logger is expected_logger
        mock_get_logger.assert_called_once_with("askfind.test")
