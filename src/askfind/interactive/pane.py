"""Multiplexer detection and pane spawning."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from enum import Enum


class Multiplexer(Enum):
    TMUX = "tmux"
    ZELLIJ = "zellij"
    NONE = "none"


def detect_multiplexer() -> Multiplexer:
    if os.environ.get("TMUX"):
        return Multiplexer.TMUX
    if os.environ.get("ZELLIJ_SESSION_NAME"):
        return Multiplexer.ZELLIJ
    return Multiplexer.NONE


def spawn_interactive_pane() -> bool:
    """Spawn askfind interactive session in a new pane.

    Returns True if pane was spawned (caller should exit).
    Returns False if running inline (caller should start REPL directly).
    """
    mux = detect_multiplexer()
    askfind_cmd = f"{sys.executable} -m askfind --interactive-session"

    if mux == Multiplexer.TMUX:
        subprocess.run(
            ["tmux", "split-window", "-h", askfind_cmd],
            check=True,
        )
        return True

    if mux == Multiplexer.ZELLIJ:
        subprocess.run(
            ["zellij", "run", "--direction", "right", "--", *askfind_cmd.split()],
            check=True,
        )
        return True

    # No multiplexer — try opening a new terminal window
    if sys.platform == "darwin":
        subprocess.Popen(
            ["open", "-a", "Terminal", "--args", askfind_cmd],
        )
        return True

    # Fallback: run inline
    return False
