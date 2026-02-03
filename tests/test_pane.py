"""Tests for pane detection and spawning."""

import os
from unittest.mock import patch

from askfind.interactive.pane import detect_multiplexer, Multiplexer


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
