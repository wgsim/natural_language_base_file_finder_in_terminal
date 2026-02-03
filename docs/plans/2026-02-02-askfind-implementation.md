# askfind Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that finds files using natural language queries via LLM-powered filter extraction and filesystem search.

**Architecture:** User query → OpenAI-compatible LLM → structured JSON filters → filesystem walker with cheapest-first filter application → optional LLM re-ranking → formatted output. Two modes: single command (pipe-friendly) and interactive (tmux/zellij pane REPL).

**Tech Stack:** Python 3.12, httpx, rich, prompt-toolkit, keyring, pytest. Conda env: `dev_tool_env_askfind`.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/askfind/__init__.py`
- Create: `src/askfind/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/test_cli.py`

**Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "askfind"
version = "0.1.0"
description = "Natural language file finder for the terminal"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "rich>=13.0",
    "prompt-toolkit>=3.0",
    "keyring>=25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
askfind = "askfind.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create `src/askfind/__init__.py`**

```python
"""askfind — Natural language file finder for the terminal."""

__version__ = "0.1.0"
```

**Step 3: Create minimal `src/askfind/cli.py`**

```python
"""CLI entry point for askfind."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="askfind",
        description="Find files using natural language queries.",
    )
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive mode")
    parser.add_argument("-r", "--root", default=".", help="Search root directory")
    parser.add_argument("-m", "--max", type=int, default=50, dest="max_results", help="Max results")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.query and not args.interactive:
        parser.print_help()
        return 2

    # Placeholder — will be wired up in later tasks
    print(f"Query: {args.query}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Write the failing test**

```python
# tests/test_cli.py
"""Tests for CLI argument parsing and entry point."""

from askfind.cli import build_parser, main


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
        assert args.max_results == 50

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

    def test_query_returns_0(self):
        result = main(["find python files"])
        assert result == 0

    def test_interactive_returns_0(self):
        result = main(["-i"])
        assert result == 0
```

**Step 5: Create `tests/__init__.py`**

Empty file.

**Step 6: Install package in dev mode and run tests**

```bash
cd /Users/woogwangsim/AI_development/natural_language_base_file_finder_in_terminal
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pip install -e ".[dev]"
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_cli.py -v
```

Expected: All tests PASS.

**Step 7: Initialize git and commit**

```bash
git init
git add pyproject.toml src/ tests/
git commit -m "feat: project scaffolding with CLI argument parsing"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `src/askfind/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing tests**

```python
# tests/test_config.py
"""Tests for configuration management."""

import os
import tomllib
from pathlib import Path
from unittest.mock import patch, MagicMock

from askfind.config import Config, get_api_key, get_config_path


class TestGetConfigPath:
    def test_default_path(self):
        path = get_config_path()
        assert path == Path.home() / ".config" / "askfind" / "config.toml"


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.model == "openai/gpt-4o-mini"
        assert config.default_root == "."
        assert config.max_results == 50
        assert config.editor == "vim"

    def test_from_toml_string(self, tmp_path):
        toml_content = b'[provider]\nbase_url = "http://localhost:11434/v1"\nmodel = "llama3"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = Config.from_file(config_file)
        assert config.base_url == "http://localhost:11434/v1"
        assert config.model == "llama3"

    def test_from_missing_file_returns_defaults(self, tmp_path):
        config = Config.from_file(tmp_path / "nonexistent.toml")
        assert config.base_url == "https://openrouter.ai/api/v1"

    def test_partial_toml_merges_with_defaults(self, tmp_path):
        toml_content = b'[provider]\nmodel = "gpt-4o"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = Config.from_file(config_file)
        assert config.model == "gpt-4o"
        assert config.base_url == "https://openrouter.ai/api/v1"  # default preserved

    def test_save_and_reload(self, tmp_path):
        config = Config(model="custom-model", editor="nano")
        config_file = tmp_path / "config.toml"
        config.save(config_file)
        reloaded = Config.from_file(config_file)
        assert reloaded.model == "custom-model"
        assert reloaded.editor == "nano"


class TestGetApiKey:
    def test_cli_flag_takes_priority(self):
        key = get_api_key(cli_key="sk-cli", env_key=None)
        assert key == "sk-cli"

    @patch.dict(os.environ, {"ASKFIND_API_KEY": "sk-env"})
    def test_env_var_fallback(self):
        key = get_api_key(cli_key=None, env_key=None)
        assert key == "sk-env"

    @patch("askfind.config.keyring")
    def test_keychain_fallback(self, mock_keyring):
        mock_keyring.get_password.return_value = "sk-keychain"
        with patch.dict(os.environ, {}, clear=True):
            # Remove ASKFIND_API_KEY if present
            os.environ.pop("ASKFIND_API_KEY", None)
            key = get_api_key(cli_key=None, env_key=None)
        assert key == "sk-keychain"

    @patch("askfind.config.keyring")
    def test_no_key_returns_none(self, mock_keyring):
        mock_keyring.get_password.return_value = None
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASKFIND_API_KEY", None)
            key = get_api_key(cli_key=None, env_key=None)
        assert key is None
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_config.py -v
```

Expected: FAIL — `askfind.config` does not exist.

**Step 3: Write implementation**

```python
# src/askfind/config.py
"""Configuration management for askfind."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

import keyring


SERVICE_NAME = "askfind"
CONFIG_DIR = Path.home() / ".config" / "askfind"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def get_config_path() -> Path:
    return CONFIG_FILE


@dataclass
class Config:
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4o-mini"
    default_root: str = "."
    max_results: int = 50
    editor: str = "vim"

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        kwargs = {}
        provider = data.get("provider", {})
        search = data.get("search", {})
        interactive = data.get("interactive", {})
        field_map = {
            "base_url": provider,
            "model": provider,
            "default_root": search,
            "max_results": search,
            "editor": interactive,
        }
        for field in fields(cls):
            source = field_map.get(field.name)
            if source and field.name in source:
                kwargs[field.name] = source[field.name]
        return cls(**kwargs)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "[provider]",
            f'base_url = "{self.base_url}"',
            f'model = "{self.model}"',
            "",
            "[search]",
            f'default_root = "{self.default_root}"',
            f"max_results = {self.max_results}",
            "",
            "[interactive]",
            f'editor = "{self.editor}"',
            "",
        ]
        path.write_text("\n".join(lines))


def get_api_key(cli_key: str | None = None, env_key: str | None = None) -> str | None:
    if cli_key:
        return cli_key
    env_val = env_key or os.environ.get("ASKFIND_API_KEY")
    if env_val:
        return env_val
    return keyring.get_password(SERVICE_NAME, "api_key")
```

**Step 4: Run tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_config.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/config.py tests/test_config.py
git commit -m "feat: add configuration module with keychain-first secret storage"
```

---

### Task 3: Filter Dataclass and Matching Logic

**Files:**
- Create: `src/askfind/search/__init__.py`
- Create: `src/askfind/search/filters.py`
- Create: `tests/test_filters.py`

**Step 1: Write the failing tests**

```python
# tests/test_filters.py
"""Tests for search filter dataclass and matching logic."""

import os
import time
from pathlib import Path

from askfind.search.filters import SearchFilters, parse_size, parse_time_delta


class TestParseSize:
    def test_bytes(self):
        assert parse_size("100") == 100

    def test_kilobytes(self):
        assert parse_size("1KB") == 1024

    def test_megabytes(self):
        assert parse_size("5MB") == 5 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_size("2GB") == 2 * 1024 * 1024 * 1024

    def test_case_insensitive(self):
        assert parse_size("1kb") == 1024


class TestParseTimeDelta:
    def test_days(self):
        delta = parse_time_delta("7d")
        assert delta.days == 7

    def test_hours(self):
        delta = parse_time_delta("24h")
        assert delta.total_seconds() == 86400

    def test_minutes(self):
        delta = parse_time_delta("30m")
        assert delta.total_seconds() == 1800

    def test_weeks(self):
        delta = parse_time_delta("2w")
        assert delta.days == 14


class TestSearchFilters:
    def test_empty_filters_match_everything(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("content")
        filters = SearchFilters()
        assert filters.matches_name(f.name) is True
        assert filters.matches_path(str(f)) is True

    def test_ext_filter(self):
        filters = SearchFilters(ext=[".py"])
        assert filters.matches_name("test.py") is True
        assert filters.matches_name("test.js") is False

    def test_not_ext_filter(self):
        filters = SearchFilters(not_ext=[".pyc"])
        assert filters.matches_name("test.py") is True
        assert filters.matches_name("test.pyc") is False

    def test_name_glob(self):
        filters = SearchFilters(name="*test*")
        assert filters.matches_name("test_auth.py") is True
        assert filters.matches_name("auth.py") is False

    def test_not_name_glob(self):
        filters = SearchFilters(not_name="*cache*")
        assert filters.matches_name("file_cache.py") is False
        assert filters.matches_name("file_auth.py") is True

    def test_path_contains(self):
        filters = SearchFilters(path="src")
        assert filters.matches_path("src/auth/login.py") is True
        assert filters.matches_path("vendor/lib.py") is False

    def test_not_path_contains(self):
        filters = SearchFilters(not_path="vendor")
        assert filters.matches_path("vendor/lib.py") is False
        assert filters.matches_path("src/auth.py") is True

    def test_regex_filter(self):
        filters = SearchFilters(regex=r"test_.*\.py$")
        assert filters.matches_name("test_auth.py") is True
        assert filters.matches_name("auth_test.py") is False

    def test_size_filter(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 2000)
        stat = f.stat()
        filters = SearchFilters(size=">1KB")
        assert filters.matches_stat(stat) is True
        filters2 = SearchFilters(size=">1MB")
        assert filters2.matches_stat(stat) is False

    def test_type_file(self):
        filters = SearchFilters(type="file")
        assert filters.matches_type(is_file=True, is_dir=False, is_link=False) is True
        assert filters.matches_type(is_file=False, is_dir=True, is_link=False) is False

    def test_type_dir(self):
        filters = SearchFilters(type="dir")
        assert filters.matches_type(is_file=False, is_dir=True, is_link=False) is True

    def test_has_content(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# TODO: fix this\nimport os\n")
        filters = SearchFilters(has=["TODO"])
        assert filters.matches_content(f) is True
        filters2 = SearchFilters(has=["FIXME"])
        assert filters2.matches_content(f) is False

    def test_has_multiple_terms(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# TODO: fix this\n# FIXME: later\n")
        filters = SearchFilters(has=["TODO", "FIXME"])
        assert filters.matches_content(f) is True

    def test_depth_filter(self):
        filters = SearchFilters(depth="<3")
        assert filters.matches_depth(2) is True
        assert filters.matches_depth(3) is False
        assert filters.matches_depth(5) is False
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_filters.py -v
```

Expected: FAIL — module not found.

**Step 3: Write implementation**

```python
# src/askfind/search/__init__.py
"""Search engine for askfind."""
```

```python
# src/askfind/search/filters.py
"""Filter dataclass and matching logic for file search."""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    return int(s)


def parse_time_delta(s: str) -> timedelta:
    s = s.strip().lower()
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    for suffix, kwarg in units.items():
        if s.endswith(suffix):
            value = int(s[: -len(suffix)])
            return timedelta(**{kwarg: value})
    return timedelta(days=int(s))


def _parse_constraint(s: str) -> tuple[str, str]:
    """Parse '>7d' into ('>', '7d') or '<1MB' into ('<', '1MB')."""
    if s.startswith(">"):
        return ">", s[1:]
    if s.startswith("<"):
        return "<", s[1:]
    return "=", s


@dataclass
class SearchFilters:
    ext: list[str] | None = None
    not_ext: list[str] | None = None
    name: str | None = None
    not_name: str | None = None
    path: str | None = None
    not_path: str | None = None
    regex: str | None = None
    fuzzy: str | None = None
    mod: str | None = None
    cre: str | None = None
    acc: str | None = None
    newer: str | None = None
    size: str | None = None
    lines: str | None = None
    has: list[str] | None = None
    type: str | None = None
    cat: str | None = None
    depth: str | None = None
    perm: str | None = None
    owner: str | None = None

    def matches_name(self, filename: str) -> bool:
        if self.ext is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() not in [e.lower() for e in self.ext]:
                return False
        if self.not_ext is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() in [e.lower() for e in self.not_ext]:
                return False
        if self.name and not fnmatch.fnmatch(filename, self.name):
            return False
        if self.not_name and fnmatch.fnmatch(filename, self.not_name):
            return False
        if self.regex and not re.search(self.regex, filename):
            return False
        if self.fuzzy:
            if not _fuzzy_match(self.fuzzy.lower(), filename.lower()):
                return False
        return True

    def matches_path(self, filepath: str) -> bool:
        if self.path and self.path not in filepath:
            return False
        if self.not_path and self.not_path in filepath:
            return False
        return True

    def matches_type(self, is_file: bool, is_dir: bool, is_link: bool) -> bool:
        if self.type is None:
            return True
        if self.type == "file":
            return is_file
        if self.type == "dir":
            return is_dir
        if self.type == "link":
            return is_link
        return True

    def matches_depth(self, depth: int) -> bool:
        if self.depth is None:
            return True
        op, val = _parse_constraint(self.depth)
        limit = int(val)
        if op == "<":
            return depth < limit
        if op == ">":
            return depth > limit
        return depth == limit

    def matches_stat(self, stat: os.stat_result) -> bool:
        if self.size:
            op, val = _parse_constraint(self.size)
            size_bytes = parse_size(val)
            if op == ">" and stat.st_size <= size_bytes:
                return False
            if op == "<" and stat.st_size >= size_bytes:
                return False
        if self.mod:
            op, val = _parse_constraint(self.mod)
            delta = parse_time_delta(val)
            cutoff = datetime.now(timezone.utc) - delta
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if op == ">" and mtime < cutoff:
                return False
            if op == "<" and mtime > cutoff:
                return False
        if self.perm:
            mode = stat.st_mode
            if "x" in self.perm and not (mode & 0o111):
                return False
            if "w" in self.perm and not (mode & 0o222):
                return False
            if "r" in self.perm and not (mode & 0o444):
                return False
        return True

    def matches_content(self, filepath: Path) -> bool:
        if not self.has:
            return True
        try:
            text = filepath.read_text(errors="ignore")
            return all(term in text for term in self.has)
        except (OSError, UnicodeDecodeError):
            return False


def _fuzzy_match(pattern: str, text: str) -> bool:
    """Simple subsequence fuzzy match."""
    p_idx = 0
    for char in text:
        if p_idx < len(pattern) and char == pattern[p_idx]:
            p_idx += 1
    return p_idx == len(pattern)
```

**Step 4: Run tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_filters.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/search/ tests/test_filters.py
git commit -m "feat: add search filter dataclass with matching logic"
```

---

### Task 4: Filesystem Walker

**Files:**
- Create: `src/askfind/search/walker.py`
- Create: `tests/test_walker.py`

**Step 1: Write the failing tests**

```python
# tests/test_walker.py
"""Tests for filesystem walker."""

from pathlib import Path

from askfind.search.filters import SearchFilters
from askfind.search.walker import walk_and_filter


def _make_tree(tmp_path: Path) -> None:
    """Create a test file tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "src" / "auth" / "login.py").write_text("def login(): pass")
    (tmp_path / "src" / "auth" / "logout.py").write_text("def logout(): pass")
    (tmp_path / "src" / "config.toml").write_text('[db]\nhost = "localhost"')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("# TODO: add tests\nimport pytest")
    (tmp_path / "readme.md").write_text("# Project")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("gitconfig")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module")


class TestWalkAndFilter:
    def test_no_filters_returns_all_files(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        paths = [r.name for r in results]
        assert "login.py" in paths
        assert "readme.md" in paths

    def test_skips_git_directory(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        paths = [str(r) for r in results]
        assert not any(".git" in p for p in paths)

    def test_skips_node_modules(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        paths = [str(r) for r in results]
        assert not any("node_modules" in p for p in paths)

    def test_ext_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(ext=[".py"])
        results = list(walk_and_filter(tmp_path, filters))
        assert all(r.suffix == ".py" for r in results)
        assert len(results) == 3  # login.py, logout.py, test_auth.py

    def test_name_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(name="*login*")
        results = list(walk_and_filter(tmp_path, filters))
        assert len(results) == 1
        assert results[0].name == "login.py"

    def test_has_content_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(has=["TODO"])
        results = list(walk_and_filter(tmp_path, filters))
        assert len(results) == 1
        assert results[0].name == "test_auth.py"

    def test_path_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(path="auth")
        results = list(walk_and_filter(tmp_path, filters))
        names = [r.name for r in results]
        assert "login.py" in names
        assert "logout.py" in names
        assert "readme.md" not in names

    def test_type_dir(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(type="dir")
        results = list(walk_and_filter(tmp_path, filters))
        names = [r.name for r in results]
        assert "src" in names
        assert "auth" in names
        assert "tests" in names

    def test_max_results(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters, max_results=2))
        assert len(results) == 2
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_walker.py -v
```

Expected: FAIL — `walk_and_filter` not found.

**Step 3: Write implementation**

```python
# src/askfind/search/walker.py
"""Filesystem walker with filter-during-traversal."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from askfind.search.filters import SearchFilters

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hg", ".svn"}


def walk_and_filter(
    root: Path,
    filters: SearchFilters,
    max_results: int = 0,
) -> Generator[Path, None, None]:
    """Walk filesystem from root, yielding paths that match filters.

    Filters are applied during traversal in cheapest-first order.
    """
    count = 0
    for path in _scan_recursive(root, filters, depth=0):
        yield path
        count += 1
        if max_results and count >= max_results:
            return


def _scan_recursive(
    directory: Path,
    filters: SearchFilters,
    depth: int,
) -> Generator[Path, None, None]:
    try:
        entries = os.scandir(directory)
    except PermissionError:
        return

    dirs_to_recurse: list[tuple[Path, int]] = []

    with entries:
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue

            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            is_link = entry.is_symlink()
            entry_path = Path(entry.path)

            # Tier 0: type and depth (no I/O)
            if not filters.matches_type(is_file=is_file, is_dir=is_dir, is_link=is_link):
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_depth(depth):
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 1: name and path checks (no I/O)
            if not filters.matches_name(entry.name):
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_path(str(entry_path)):
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 2: stat-based checks
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_stat(stat):
                if is_dir:
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 3: content checks (most expensive, files only)
            if is_file and not filters.matches_content(entry_path):
                continue

            yield entry_path

            if is_dir:
                dirs_to_recurse.append((entry_path, depth + 1))

    # Recurse into subdirectories
    for dir_path, next_depth in dirs_to_recurse:
        yield from _scan_recursive(dir_path, filters, next_depth)
```

**Step 4: Run tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_walker.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/search/walker.py tests/test_walker.py
git commit -m "feat: add filesystem walker with cheapest-first filter application"
```

---

### Task 5: LLM Client and Prompt

**Files:**
- Create: `src/askfind/llm/__init__.py`
- Create: `src/askfind/llm/client.py`
- Create: `src/askfind/llm/prompt.py`
- Create: `src/askfind/llm/parser.py`
- Create: `tests/test_llm_parser.py`

**Step 1: Write the failing tests**

```python
# tests/test_llm_parser.py
"""Tests for LLM response parsing."""

from askfind.llm.parser import parse_llm_response
from askfind.search.filters import SearchFilters


class TestParseLlmResponse:
    def test_simple_ext_filter(self):
        raw = '{"ext": [".py"]}'
        filters = parse_llm_response(raw)
        assert isinstance(filters, SearchFilters)
        assert filters.ext == [".py"]

    def test_multiple_filters(self):
        raw = '{"ext": [".py"], "name": "*test*", "mod": ">7d"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]
        assert filters.name == "*test*"
        assert filters.mod == ">7d"

    def test_empty_json(self):
        raw = "{}"
        filters = parse_llm_response(raw)
        assert filters.ext is None
        assert filters.name is None

    def test_ignores_unknown_keys(self):
        raw = '{"ext": [".py"], "unknown_key": "value"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_handles_markdown_wrapped_json(self):
        raw = '```json\n{"ext": [".py"]}\n```'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_handles_plain_text_wrapped_json(self):
        raw = 'Here are the filters:\n{"ext": [".py"]}\nLet me know if you need more.'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_invalid_json_returns_empty_filters(self):
        raw = "not json at all"
        filters = parse_llm_response(raw)
        assert filters == SearchFilters()

    def test_has_as_single_string_converted_to_list(self):
        raw = '{"has": "TODO"}'
        filters = parse_llm_response(raw)
        assert filters.has == ["TODO"]

    def test_has_as_list(self):
        raw = '{"has": ["TODO", "FIXME"]}'
        filters = parse_llm_response(raw)
        assert filters.has == ["TODO", "FIXME"]

    def test_ext_as_single_string_converted_to_list(self):
        raw = '{"ext": ".py"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_llm_parser.py -v
```

Expected: FAIL — module not found.

**Step 3: Write implementation — parser**

```python
# src/askfind/llm/__init__.py
"""LLM integration for askfind."""
```

```python
# src/askfind/llm/parser.py
"""Parse LLM responses into SearchFilters."""

from __future__ import annotations

import json
import re
from dataclasses import fields

from askfind.search.filters import SearchFilters

_LIST_FIELDS = {"ext", "not_ext", "has"}


def parse_llm_response(raw: str) -> SearchFilters:
    """Parse a raw LLM response string into SearchFilters.

    Handles JSON wrapped in markdown code blocks or surrounding text.
    Returns empty SearchFilters on parse failure.
    """
    json_str = _extract_json(raw)
    if json_str is None:
        return SearchFilters()
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return SearchFilters()
    if not isinstance(data, dict):
        return SearchFilters()
    valid_names = {f.name for f in fields(SearchFilters)}
    kwargs = {}
    for key, value in data.items():
        if key not in valid_names:
            continue
        if key in _LIST_FIELDS and isinstance(value, str):
            value = [value]
        kwargs[key] = value
    return SearchFilters(**kwargs)


def _extract_json(raw: str) -> str | None:
    """Extract JSON object from raw text."""
    raw = raw.strip()
    # Try markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if md_match:
        return md_match.group(1).strip()
    # Try to find JSON object directly
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if brace_match:
        return brace_match.group(0)
    return None
```

**Step 4: Write implementation — prompt**

```python
# src/askfind/llm/prompt.py
"""System prompt and schema for LLM filter extraction."""

from __future__ import annotations

from datetime import datetime, timezone

FILTER_SCHEMA = """\
{
  "ext": [".py"],        // file extensions to include
  "not_ext": [".pyc"],   // file extensions to exclude
  "name": "*test*",      // glob on filename
  "not_name": "*cache*", // glob to exclude
  "path": "src",         // path must contain
  "not_path": "vendor",  // path must not contain
  "regex": "pattern",    // regex on filename
  "fuzzy": "confg",      // fuzzy match on filename
  "mod": ">7d",          // modified within (d=days, h=hours, m=minutes, w=weeks)
  "cre": ">1d",          // created within
  "acc": ">3d",          // accessed within
  "newer": "file.py",    // newer than reference file
  "size": ">1MB",        // size (KB, MB, GB)
  "lines": ">100",       // line count
  "has": ["TODO"],       // file content contains all terms
  "type": "file",        // file, dir, link
  "cat": "python",       // category: python, javascript, image, binary, text...
  "depth": "<5",         // directory depth
  "perm": "x",           // permissions: r, w, x
  "owner": "root"        // file owner
}\
"""


def build_system_prompt() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""\
You are a file search assistant. Given a natural language query about finding files, \
extract structured search filters as a JSON object.

Current date/time: {now}

Return ONLY a JSON object with relevant keys. Omit keys that are not needed. \
Use the shortest representation possible.

Available keys:
{FILTER_SCHEMA}

Rules:
- Return ONLY the JSON object, no explanation, no markdown.
- Use relative time: "7d" not "2026-01-26".
- For "this week" use ">7d". For "today" use ">1d". For "this month" use ">30d".
- ext values must include the dot: ".py" not "py".
- has accepts a list of strings that must ALL appear in the file content.
- Only include keys relevant to the query.\
"""
```

**Step 5: Write implementation — client**

```python
# src/askfind/llm/client.py
"""OpenAI-compatible LLM HTTP client."""

from __future__ import annotations

import httpx

from askfind.llm.prompt import build_system_prompt


class LLMClient:
    """Client for OpenAI-compatible chat completion APIs."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def extract_filters(self, query: str) -> str:
        """Send query to LLM and return raw response text."""
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def rerank(self, query: str, file_list: list[str]) -> list[str]:
        """Send file list to LLM for semantic re-ranking. Returns ordered list."""
        file_text = "\n".join(file_list)
        prompt = (
            f"Given the query: \"{query}\"\n\n"
            f"Rank these files by relevance (most relevant first). "
            f"Return ONLY the file paths, one per line, no numbering:\n\n{file_text}"
        )
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        ranked = [line.strip() for line in content.splitlines() if line.strip()]
        # Only return paths that were in the original list
        valid = set(file_list)
        return [p for p in ranked if p in valid]

    def close(self) -> None:
        self._http.close()
```

**Step 6: Run parser tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_llm_parser.py -v
```

Expected: All tests PASS.

**Step 7: Commit**

```bash
git add src/askfind/llm/ tests/test_llm_parser.py
git commit -m "feat: add LLM client, prompt, and response parser"
```

---

### Task 6: Output Formatter

**Files:**
- Create: `src/askfind/output/__init__.py`
- Create: `src/askfind/output/formatter.py`
- Create: `tests/test_formatter.py`

**Step 1: Write the failing tests**

```python
# tests/test_formatter.py
"""Tests for output formatting."""

import json
from pathlib import Path

from askfind.output.formatter import format_plain, format_verbose, format_json, FileResult


class TestFileResult:
    def test_from_path(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello\nworld\n")
        result = FileResult.from_path(f)
        assert result.path == f
        assert result.size > 0
        assert result.modified is not None


class TestFormatPlain:
    def test_single_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_plain(results)
        assert str(f) in output

    def test_multiple_files(self, tmp_path):
        files = []
        for name in ["a.py", "b.py", "c.py"]:
            f = tmp_path / name
            f.write_text("x")
            files.append(FileResult.from_path(f))
        output = format_plain(files)
        lines = output.strip().splitlines()
        assert len(lines) == 3

    def test_empty_results(self):
        output = format_plain([])
        assert output == ""


class TestFormatJson:
    def test_valid_json(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_json(results)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "path" in data[0]
        assert "size" in data[0]
        assert "modified" in data[0]


class TestFormatVerbose:
    def test_includes_metadata(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_verbose(results)
        assert "test.py" in output
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_formatter.py -v
```

Expected: FAIL — module not found.

**Step 3: Write implementation**

```python
# src/askfind/output/__init__.py
"""Output formatting for askfind."""
```

```python
# src/askfind/output/formatter.py
"""Format search results for terminal output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileResult:
    path: Path
    size: int
    modified: datetime

    @classmethod
    def from_path(cls, path: Path) -> FileResult:
        stat = path.stat()
        return cls(
            path=path,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )


def format_plain(results: list[FileResult]) -> str:
    if not results:
        return ""
    return "\n".join(str(r.path) for r in results)


def format_verbose(results: list[FileResult]) -> str:
    if not results:
        return ""
    lines = []
    for r in results:
        size_str = _human_size(r.size)
        date_str = r.modified.strftime("%b %d")
        lines.append(f"{r.path}  {size_str}  {date_str}")
    return "\n".join(lines)


def format_json(results: list[FileResult]) -> str:
    data = [
        {
            "path": str(r.path),
            "size": r.size,
            "modified": r.modified.strftime("%Y-%m-%d"),
        }
        for r in results
    ]
    return json.dumps(data, indent=2)


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024:
            if unit == "B":
                return f"{nbytes} {unit}"
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"
```

**Step 4: Run tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_formatter.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/output/ tests/test_formatter.py
git commit -m "feat: add output formatters (plain, verbose, JSON)"
```

---

### Task 7: Wire Up Single Command Mode

**Files:**
- Modify: `src/askfind/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
from unittest.mock import patch, MagicMock
from askfind.search.filters import SearchFilters


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
```

**Step 2: Run test to verify it fails**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_cli.py::TestMainIntegration -v
```

Expected: FAIL — imports or logic missing.

**Step 3: Update `src/askfind/cli.py`**

```python
"""CLI entry point for askfind."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from askfind.config import Config, get_api_key, get_config_path
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
from askfind.output.formatter import FileResult, format_json, format_plain, format_verbose
from askfind.search.walker import walk_and_filter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="askfind",
        description="Find files using natural language queries.",
    )
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive mode")
    parser.add_argument("-r", "--root", default=".", help="Search root directory")
    parser.add_argument("-m", "--max", type=int, default=0, dest="max_results", help="Max results (0=use config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.query and not args.interactive:
        parser.print_help()
        return 2

    config = Config.from_file(get_config_path())

    if args.interactive:
        # Will be implemented in Task 9
        print("Interactive mode not yet implemented.", file=sys.stderr)
        return 0

    # Single command mode
    api_key = get_api_key(cli_key=args.api_key)
    if not api_key:
        print("Error: No API key configured. Run `askfind config set-key`.", file=sys.stderr)
        return 2

    model = args.model or config.model
    max_results = args.max_results or config.max_results

    client = LLMClient(base_url=config.base_url, api_key=api_key, model=model)
    try:
        raw_response = client.extract_filters(args.query)
        filters = parse_llm_response(raw_response)
        root = Path(args.root).resolve()
        paths = list(walk_and_filter(root, filters, max_results=max_results))
        results = [FileResult.from_path(p) for p in paths]

        if not results:
            return 1

        if args.json_output:
            print(format_json(results))
        elif args.verbose:
            print(format_verbose(results))
        else:
            print(format_plain(results))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run all tests**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/cli.py tests/test_cli.py
git commit -m "feat: wire up single command mode end-to-end"
```

---

### Task 8: Config Subcommand

**Files:**
- Modify: `src/askfind/cli.py`
- Modify: `src/askfind/config.py`

**Step 1: Add config subcommand handling to CLI**

Add a `config` subcommand group to `build_parser()`. Support:
- `askfind config show`
- `askfind config set <key> <value>`
- `askfind config set-key`
- `askfind config models`

Update `build_parser()` to use subparsers:

```python
# Add to build_parser() — replace the existing function
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="askfind",
        description="Find files using natural language queries.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Config subcommand
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_sub = config_parser.add_subparsers(dest="config_action")

    config_sub.add_parser("show", help="Show current configuration")

    set_parser = config_sub.add_parser("set", help="Set a config value")
    set_parser.add_argument("key", help="Config key")
    set_parser.add_argument("value", help="Config value")

    config_sub.add_parser("set-key", help="Store API key in system keychain")

    models_parser = config_sub.add_parser("models", help="List available models")
    models_parser.add_argument("--provider", help="Filter by provider")

    # Main query arguments (when no subcommand)
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive mode")
    parser.add_argument("-r", "--root", default=".", help="Search root directory")
    parser.add_argument("-m", "--max", type=int, default=0, dest="max_results", help="Max results (0=use config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
    return parser
```

Add `set_api_key()` to `src/askfind/config.py`:

```python
def set_api_key(key: str) -> None:
    keyring.set_password(SERVICE_NAME, "api_key", key)
```

Add config command handler to `main()`:

```python
    if args.command == "config":
        return _handle_config(args)
```

```python
def _handle_config(args) -> int:
    config = Config.from_file(get_config_path())
    if args.config_action == "show":
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="askfind configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("base_url", config.base_url)
        table.add_row("model", config.model)
        table.add_row("default_root", config.default_root)
        table.add_row("max_results", str(config.max_results))
        table.add_row("editor", config.editor)
        api_key = get_api_key()
        table.add_row("api_key", "****" + api_key[-4:] if api_key else "[not set]")
        console.print(table)
        return 0
    if args.config_action == "set":
        setattr(config, args.key, args.value)
        config.save(get_config_path())
        print(f"Set {args.key} = {args.value}")
        return 0
    if args.config_action == "set-key":
        from getpass import getpass
        from askfind.config import set_api_key
        key = getpass("Enter API key: ")
        set_api_key(key)
        print("API key stored in system keychain.")
        return 0
    if args.config_action == "models":
        api_key = get_api_key()
        if not api_key:
            print("Error: No API key configured.", file=sys.stderr)
            return 2
        try:
            import httpx
            resp = httpx.get(
                f"{config.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            models = resp.json().get("data", [])
            for m in models:
                print(m.get("id", "unknown"))
        except Exception as e:
            print(f"Error fetching models: {e}", file=sys.stderr)
            return 3
        return 0
    return 2
```

**Step 2: Run all tests**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/ -v
```

Expected: All tests PASS (existing tests may need minor adjustments due to subparser changes).

**Step 3: Commit**

```bash
git add src/askfind/cli.py src/askfind/config.py
git commit -m "feat: add config subcommand (show, set, set-key, models)"
```

---

### Task 9: Interactive Mode — Pane Spawning

**Files:**
- Create: `src/askfind/interactive/__init__.py`
- Create: `src/askfind/interactive/pane.py`
- Create: `tests/test_pane.py`

**Step 1: Write the failing tests**

```python
# tests/test_pane.py
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
```

**Step 2: Run tests to verify they fail**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_pane.py -v
```

Expected: FAIL — module not found.

**Step 3: Write implementation**

```python
# src/askfind/interactive/__init__.py
"""Interactive mode for askfind."""
```

```python
# src/askfind/interactive/pane.py
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
```

**Step 4: Run tests to verify they pass**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/test_pane.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/interactive/ tests/test_pane.py
git commit -m "feat: add multiplexer detection and pane spawning"
```

---

### Task 10: Interactive Mode — REPL Session

**Files:**
- Create: `src/askfind/interactive/session.py`
- Create: `src/askfind/interactive/commands.py`

**Step 1: Write implementation — commands**

```python
# src/askfind/interactive/commands.py
"""Action commands for interactive mode."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax

from askfind.output.formatter import FileResult

console = Console()


def copy_path(result: FileResult) -> None:
    path_str = str(result.path)
    _copy_to_clipboard(path_str)
    console.print(f"[green]Copied: {path_str}[/green]")


def copy_content(result: FileResult) -> None:
    try:
        content = result.path.read_text()
        _copy_to_clipboard(content)
        console.print(f"[green]Copied content of: {result.path.name}[/green]")
    except OSError as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def preview(result: FileResult) -> None:
    try:
        content = result.path.read_text(errors="replace")
        # Show first 50 lines
        lines = content.splitlines()[:50]
        text = "\n".join(lines)
        suffix = result.path.suffix.lstrip(".")
        syntax = Syntax(text, suffix or "text", theme="monokai", line_numbers=True)
        console.print(f"[bold]── {result.path} ──[/bold]")
        console.print(syntax)
        if len(content.splitlines()) > 50:
            console.print(f"[dim]... ({len(content.splitlines()) - 50} more lines)[/dim]")
    except OSError as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def open_in_editor(result: FileResult, editor: str = "vim") -> None:
    try:
        subprocess.run([editor, str(result.path)])
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")


def _copy_to_clipboard(text: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    elif sys.platform == "linux":
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        except FileNotFoundError:
            subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
    else:
        # Windows
        subprocess.run(["clip"], input=text.encode(), check=True)
```

**Step 2: Write implementation — session**

```python
# src/askfind/interactive/session.py
"""Interactive REPL session for askfind."""

from __future__ import annotations

import re
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.table import Table

from askfind.config import Config, get_api_key
from askfind.interactive.commands import copy_content, copy_path, open_in_editor, preview
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
from askfind.output.formatter import FileResult
from askfind.search.walker import walk_and_filter

console = Console()

HELP_TEXT = """\
[bold]Available commands:[/bold]
  [cyan]<natural language query>[/cyan]  Search for files
  [cyan]copy path <n>[/cyan]             Copy file path to clipboard
  [cyan]copy content <n>[/cyan]          Copy file contents to clipboard
  [cyan]preview <n>[/cyan]               Preview file contents
  [cyan]open <n>[/cyan]                  Open file in editor
  [cyan]help[/cyan]                      Show this message
  [cyan]exit[/cyan] / [cyan]quit[/cyan]               Exit askfind
"""


class InteractiveSession:
    def __init__(self, config: Config, root: Path) -> None:
        self.config = config
        self.root = root.resolve()
        self.results: list[FileResult] = []
        self.conversation: list[dict[str, str]] = []

        api_key = get_api_key()
        if not api_key:
            console.print("[red]No API key configured. Run `askfind config set-key`.[/red]")
            raise SystemExit(2)

        self.client = LLMClient(
            base_url=config.base_url,
            api_key=api_key,
            model=config.model,
        )

    def run(self) -> None:
        session: PromptSession[str] = PromptSession()
        console.print("[bold blue]askfind[/bold blue] [dim]interactive mode[/dim]")
        console.print("[dim]Type 'help' for commands, 'exit' to quit.[/dim]\n")

        try:
            while True:
                try:
                    user_input = session.prompt(HTML("<ansiblue><b>askfind&gt;</b></ansiblue> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not user_input:
                    continue
                if user_input in ("exit", "quit"):
                    break
                if user_input == "help":
                    console.print(HELP_TEXT)
                    continue

                # Check for action commands
                if self._handle_action(user_input):
                    continue

                # Natural language query
                self._search(user_input)
        finally:
            self.client.close()

    def _handle_action(self, text: str) -> bool:
        """Handle action commands. Returns True if handled."""
        match = re.match(r"^(copy path|copy content|preview|open)\s+(\d+)$", text, re.IGNORECASE)
        if not match:
            return False

        action = match.group(1).lower()
        idx = int(match.group(2)) - 1  # 1-indexed to 0-indexed

        if idx < 0 or idx >= len(self.results):
            console.print(f"[red]Invalid index. Have {len(self.results)} results.[/red]")
            return True

        result = self.results[idx]
        if action == "copy path":
            copy_path(result)
        elif action == "copy content":
            copy_content(result)
        elif action == "preview":
            preview(result)
        elif action == "open":
            open_in_editor(result, self.config.editor)
        return True

    def _search(self, query: str) -> None:
        try:
            raw = self.client.extract_filters(query)
            filters = parse_llm_response(raw)
            paths = list(walk_and_filter(self.root, filters, max_results=self.config.max_results))
            self.results = [FileResult.from_path(p) for p in paths]

            if not self.results:
                console.print("[dim]No files found.[/dim]")
                return

            console.print(f"[dim]Found {len(self.results)} file(s):[/dim]")
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("idx", style="yellow bold", width=5)
            table.add_column("path", style="blue")
            table.add_column("size", style="dim", justify="right", width=10)
            table.add_column("date", style="dim", width=8)

            for i, r in enumerate(self.results, 1):
                size_str = _human_size(r.size)
                date_str = r.modified.strftime("%b %d")
                table.add_row(f"[{i}]", str(r.path), size_str, date_str)

            console.print(table)
            console.print()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            if unit == "B":
                return f"{nbytes} {unit}"
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"
```

**Step 3: Wire interactive mode into `cli.py`**

Update the interactive branch in `main()`:

```python
    if args.interactive:
        from askfind.interactive.pane import spawn_interactive_pane
        if spawn_interactive_pane():
            return 0  # Pane was spawned, exit this process
        # Fallback: run inline
        from askfind.interactive.session import InteractiveSession
        session = InteractiveSession(config, Path(args.root))
        session.run()
        return 0
```

Add a hidden `--interactive-session` flag for pane-spawned processes:

```python
    parser.add_argument("--interactive-session", action="store_true", help=argparse.SUPPRESS)
```

And handle it in `main()`:

```python
    if args.interactive_session:
        from askfind.interactive.session import InteractiveSession
        session = InteractiveSession(config, Path(args.root))
        session.run()
        return 0
```

**Step 4: Run all tests**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/askfind/interactive/ src/askfind/cli.py
git commit -m "feat: add interactive mode with REPL session and action commands"
```

---

### Task 11: Re-ranker

**Files:**
- Create: `src/askfind/search/reranker.py`

**Step 1: Write implementation**

```python
# src/askfind/search/reranker.py
"""Optional LLM-based semantic re-ranking of search results."""

from __future__ import annotations

from askfind.llm.client import LLMClient
from askfind.output.formatter import FileResult


def rerank_results(
    client: LLMClient,
    query: str,
    results: list[FileResult],
) -> list[FileResult]:
    """Re-rank results using LLM semantic understanding.

    Returns results in relevance order.
    """
    if len(results) <= 1:
        return results

    path_list = [str(r.path) for r in results]
    ranked_paths = client.rerank(query, path_list)

    path_to_result = {str(r.path): r for r in results}
    ranked = [path_to_result[p] for p in ranked_paths if p in path_to_result]

    # Append any results not returned by LLM (safety net)
    ranked_set = {str(r.path) for r in ranked}
    for r in results:
        if str(r.path) not in ranked_set:
            ranked.append(r)

    return ranked
```

**Step 2: Wire re-ranking into `cli.py`**

In the single command mode section of `main()`, after getting results and before formatting, add:

```python
        if not args.no_rerank and len(results) > 1:
            from askfind.search.reranker import rerank_results
            results = rerank_results(client, args.query, results)
```

**Step 3: Run all tests**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/ -v
```

Expected: All tests PASS.

**Step 4: Commit**

```bash
git add src/askfind/search/reranker.py src/askfind/cli.py
git commit -m "feat: add optional LLM semantic re-ranking"
```

---

### Task 12: End-to-End Smoke Test

**Step 1: Run full test suite**

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/pytest tests/ -v --tb=short
```

Expected: All tests PASS.

**Step 2: Manual smoke test (requires API key)**

```bash
# Set up API key
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/python -m askfind config set-key

# Test single command mode
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/python -m askfind "python files" --root /Users/woogwangsim/AI_development/natural_language_base_file_finder_in_terminal

# Test verbose output
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/python -m askfind "python files" -v --root /Users/woogwangsim/AI_development/natural_language_base_file_finder_in_terminal

# Test JSON output
/opt/homebrew/Caskroom/miniconda/base/envs/dev_tool_env_askfind/bin/python -m askfind "python files" --json --root /Users/woogwangsim/AI_development/natural_language_base_file_finder_in_terminal
```

**Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: askfind v0.1.0 — natural language file finder"
```

---

## Task Summary

| Task | Component | Test File |
|------|-----------|-----------|
| 1 | Project scaffolding + CLI parser | `test_cli.py` |
| 2 | Configuration module | `test_config.py` |
| 3 | Filter dataclass + matching | `test_filters.py` |
| 4 | Filesystem walker | `test_walker.py` |
| 5 | LLM client + prompt + parser | `test_llm_parser.py` |
| 6 | Output formatter | `test_formatter.py` |
| 7 | Wire up single command mode | `test_cli.py` |
| 8 | Config subcommand | `test_cli.py` |
| 9 | Pane spawning | `test_pane.py` |
| 10 | Interactive REPL session | — |
| 11 | Re-ranker | — |
| 12 | End-to-end smoke test | — |

**Build order:** Tasks 1→2→3→4→5→6 can be done sequentially (each builds on the previous). Task 7 wires them together. Tasks 8, 9, 10 can be done after 7. Task 11 extends 7. Task 12 is final validation.
