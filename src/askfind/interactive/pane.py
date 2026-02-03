"""Multiplexer detection and pane spawning."""

from __future__ import annotations

import os
import shlex
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
    # Build command as list to handle paths with spaces
    askfind_args = [sys.executable, "-m", "askfind", "--interactive-session"]

    if mux == Multiplexer.TMUX:
        # tmux split-window expects a shell command string, so use shlex.join
        subprocess.run(
            ["tmux", "split-window", "-h", shlex.join(askfind_args)],
            check=True,
        )
        return True

    if mux == Multiplexer.ZELLIJ:
        # Zellij accepts proper argument list after --
        subprocess.run(
            ["zellij", "run", "--direction", "right", "--", *askfind_args],
            check=True,
        )
        return True

    # No multiplexer — try opening a new terminal window
    if sys.platform == "darwin":
        # macOS Terminal.app - use AppleScript for proper handling
        script = f'tell application "Terminal" to do script "{shlex.join(askfind_args)}"'
        subprocess.Popen(
            ["osascript", "-e", script],
        )
        return True

    # Fallback: run inline
    return False
