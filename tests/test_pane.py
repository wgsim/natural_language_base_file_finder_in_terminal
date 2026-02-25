"""Tests for pane detection and spawning."""

import os
from unittest.mock import patch

from askfind.interactive.pane import detect_multiplexer, Multiplexer, spawn_interactive_pane


class TestDetectMultiplexer:
    @patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"})
    def test_detects_tmux(self):
        assert detect_multiplexer() == Multiplexer.TMUX

    @patch.dict(os.environ, {"ZELLIJ_SESSION_NAME": "mysession"})
    def test_detects_zellij(self):
        assert detect_multiplexer() == Multiplexer.ZELLIJ

    @patch.dict(os.environ, {}, clear=True)
    def test_detects_none(self):
        os.environ.pop("TMUX", None)
        os.environ.pop("ZELLIJ_SESSION_NAME", None)
        assert detect_multiplexer() == Multiplexer.NONE


class TestSpawnInteractivePane:
    @patch("askfind.interactive.pane.subprocess.run")
    @patch("askfind.interactive.pane.detect_multiplexer", return_value=Multiplexer.TMUX)
    def test_spawns_tmux_pane(self, mock_detect, mock_run):
        result = spawn_interactive_pane()
        assert result is True
        cmd = mock_run.call_args.args[0]
        assert cmd[:3] == ["tmux", "split-window", "-h"]

    @patch("askfind.interactive.pane.subprocess.run")
    @patch("askfind.interactive.pane.detect_multiplexer", return_value=Multiplexer.ZELLIJ)
    def test_spawns_zellij_pane(self, mock_detect, mock_run):
        result = spawn_interactive_pane()
        assert result is True
        cmd = mock_run.call_args.args[0]
        assert cmd[:4] == ["zellij", "run", "--direction", "right"]

    @patch("askfind.interactive.pane.subprocess.Popen")
    @patch("askfind.interactive.pane.detect_multiplexer", return_value=Multiplexer.NONE)
    @patch("askfind.interactive.pane.sys.platform", "darwin")
    def test_spawns_terminal_on_darwin(self, mock_detect, mock_popen):
        result = spawn_interactive_pane()
        assert result is True
        mock_popen.assert_called_once()

    @patch("askfind.interactive.pane.detect_multiplexer", return_value=Multiplexer.NONE)
    @patch("askfind.interactive.pane.sys.platform", "linux")
    def test_returns_false_without_mux_or_darwin(self, mock_detect):
        assert spawn_interactive_pane() is False
