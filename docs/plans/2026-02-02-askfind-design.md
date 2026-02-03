# askfind — Design Document

> Natural language file finder for the terminal.

## 1. Project Overview

**askfind** — a CLI tool that finds files using natural language queries.

**Core flow:**

```
User query → LLM (structured filters) → Filesystem search → Optional LLM re-rank → Results
```

**Two modes:**

- **Single command:** `askfind "python test files modified this week"` — prints results to stdout, pipe-friendly.
- **Interactive:** `askfind -i` — opens a chat session in a new multiplexer pane (tmux/zellij auto-detected) or new terminal window as fallback. Conversational, supports query refinement, acts on results.

**Read-only actions (interactive mode):**

- Copy path to clipboard
- Open in editor
- Preview file contents
- Copy file contents to clipboard

**Search scope:**

- Current directory by default
- `--root <path>` to override

**Tech stack:**

- Python 3.12+
- `prompt_toolkit` for interactive input
- `rich` for styled output
- `keyring` for secret storage
- `httpx` for LLM API calls
- `tomllib` (stdlib) for config parsing
- `textual` reserved for future full-screen mode only

---

## 2. LLM Integration

### Provider Architecture

- Single generic client with configurable `(base_url, api_key, model)`
- OpenAI-compatible API format only for initial release
- Any provider supporting this format works: OpenRouter, OpenAI, z.ai GLM, Groq, Together, Mistral, etc.

### Query Processing (Two-Stage)

**Stage 1 — Structured filter extraction:**

```
User: "large python files modified this week"
       ↓ LLM
JSON: {
  "ext": [".py"],
  "size": ">1MB",
  "mod": ">7d"
}
       ↓ Filesystem search
Results: [list of matching files]
```

**Stage 2 — Semantic re-ranking (optional):**

- For vague queries like "files related to authentication"
- Send filenames + metadata back to LLM
- LLM ranks by relevance
- Skipped when filters are specific enough

### Prompt Design

- System prompt defines the structured JSON schema
- Instructs the LLM to extract filters from natural language
- Includes current date for relative time expressions ("this week", "yesterday")

---

## 3. Configuration & Security

### Config File

Location: `~/.config/askfind/config.toml`

```toml
[provider]
base_url = "https://openrouter.ai/api/v1"
model = "openai/gpt-4o-mini"

[search]
default_root = "."
max_results = 50

[interactive]
editor = "vim"
```

- **Never stores secrets** — no API keys in this file
- TOML format, parsed with `tomllib` (stdlib)

### Secret Storage Priority (highest wins)

```
CLI flag         →  askfind --api-key <key> "query"  (one-off use)
Environment var  →  ASKFIND_API_KEY                  (CI/scripts fallback)
System keychain  →  keyring library                  (default, recommended)
```

### Keychain via `keyring`

- `askfind config set-key` — prompts for API key, stores in OS keychain
- macOS → Keychain, Linux → Secret Service, Windows → Credential Manager
- Encrypted at rest by the OS
- Same code, all platforms

### Config Management Commands

```
askfind config set model openai/gpt-4o-mini
askfind config set base_url https://openrouter.ai/api/v1
askfind config set-key          # prompts securely, stores in keychain
askfind config show             # displays current config (key masked)
askfind config models           # list available models from provider
askfind config models --provider openai  # list from specific provider
```

### Env Var Fallback Warning

- If keychain is unavailable (headless Linux, Docker, WSL without secret service), env vars are used
- Tool logs a one-time warning suggesting keychain setup

---

## 4. Interactive Mode Architecture

### Launch Behavior — `askfind -i`

```
Detect environment
    ├─ In tmux?    → open new tmux pane (split)
    ├─ In zellij?  → open new zellij pane
    └─ Neither?    → open new terminal window (OS-dependent)
```

### Auto-Detection

- tmux: check `$TMUX` env var
- zellij: check `$ZELLIJ_SESSION_NAME` env var
- Fallback: spawn new terminal window via `open` (macOS), `xdg-open`/`xterm` (Linux), `start` (Windows)

### Session Behavior

- Chat-style REPL with `prompt_toolkit` for input
- `rich` for styled result output
- LLM retains conversation context for query refinement
- Numbered results for reference in follow-up commands

### Example Session

```
askfind> find python test files
  [1] src/tests/test_auth.py      2.4KB  Jan 28
  [2] src/tests/test_api.py       1.8KB  Jan 25
  [3] tests/conftest.py           0.9KB  Jan 20

askfind> only modified this week
  [1] src/tests/test_auth.py      2.4KB  Jan 28

askfind> preview 1
── src/tests/test_auth.py ──
import pytest
from app.auth import login
...

askfind> copy path 1
Copied: src/tests/test_auth.py

askfind> exit
```

### Available Commands in Interactive Mode

- Natural language queries (default)
- `copy path <n>` — copy file path to clipboard
- `copy content <n>` — copy file contents to clipboard
- `preview <n>` — display file contents
- `open <n>` — open in configured editor
- `help` — show available commands
- `exit` / `quit` / `Ctrl+D` — close session

### UI Mockup

See `docs/mockup_interactive_mode.png` for visual reference of the tmux split-pane layout.

---

## 5. Single Command Mode

### Usage

```
askfind "python test files modified this week"
askfind "large log files" --root /var/log
askfind "config files containing database" --max 20
```

### Output Formats

**Plain (default, pipe-friendly):**

```
src/tests/test_auth.py
src/tests/test_api.py
tests/conftest.py
```

**Verbose (`-v`):**

```
src/tests/test_auth.py      2.4 KB  Jan 28  Python
src/tests/test_api.py       1.8 KB  Jan 25  Python
tests/conftest.py           0.9 KB  Jan 20  Python
```

**JSON (`--json`):**

```json
[
  {"path": "src/tests/test_auth.py", "size": 2457, "modified": "2026-01-28", "type": "python"}
]
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `"query"` | Natural language query (positional) |
| `-i` / `--interactive` | Launch interactive mode |
| `-r` / `--root <path>` | Search root directory |
| `-m` / `--max <n>` | Max results (default: 50) |
| `-v` / `--verbose` | Show metadata alongside paths |
| `--json` | JSON output |
| `--model <name>` | Override LLM model |
| `--api-key <key>` | One-off API key |
| `--no-rerank` | Skip semantic re-ranking |
| `config` | Subcommand for configuration |

### Exit Codes

- `0` — results found
- `1` — no results found
- `2` — configuration error (no API key, etc.)
- `3` — LLM API error

### Pipe Integration

```bash
askfind "python test files" | xargs wc -l
askfind "config files" | head -5
vim $(askfind "main entry point")
```

---

## 6. Filesystem Search Engine

### LLM Input/Output — Compact Schema

Prompt instructs LLM to return a single JSON object. No explanations, no wrapping.

```json
{"ext": [".py"], "name": "*test*", "path": "config", "mod": ">7d", "size": ">1MB", "has": "database", "type": "file"}
```

Short keys, relative time expressions (`>7d` = modified within 7 days), human-readable size strings. The LLM produces fewer tokens, our parser normalizes them.

### V1 Filter Keys (20 total)

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `ext` | `[str]` | File extensions to include | `[".py", ".pyi"]` |
| `not_ext` | `[str]` | File extensions to exclude | `[".pyc"]` |
| `name` | `str` | Glob pattern on filename | `"*test*"` |
| `not_name` | `str` | Glob pattern to exclude | `"*cache*"` |
| `path` | `str` | Path must contain | `"src"` |
| `not_path` | `str` | Path must not contain | `"vendor"` |
| `regex` | `str` | Regex pattern on filename | `"test_.*\\.py$"` |
| `fuzzy` | `str` | Fuzzy match on filename | `"confg"` |
| `mod` | `str` | Modified within | `">7d"` |
| `cre` | `str` | Created within | `">1d"` |
| `acc` | `str` | Accessed within | `">3d"` |
| `newer` | `str` | Newer than reference file | `"src/main.py"` |
| `size` | `str` | Size constraint | `">1MB"` |
| `lines` | `str` | Line count constraint | `">100"` |
| `has` | `[str]` | Content must contain | `["TODO", "FIXME"]` |
| `type` | `str` | Entry type | `"file"`, `"dir"`, `"link"` |
| `cat` | `str` | File category | `"python"`, `"image"`, `"binary"` |
| `depth` | `str` | Max/min depth | `"<5"` |
| `perm` | `str` | Permission filter | `"x"` (executable) |
| `owner` | `str` | File owner | `"root"` |

All keys optional — LLM only includes what the query needs.

### Filter Application Order (cheapest first)

1. `type` → `depth` → `ext`/`not_ext` → `name`/`not_name` → `path`/`not_path` → `regex` → `fuzzy` → `cat` (no I/O)
2. `mod` → `cre` → `acc` → `newer` → `size` → `perm` → `owner` (stat call)
3. `lines` → `has` (content read — most expensive)

### Walker

- `os.scandir()` with filters applied during traversal
- Respects `.gitignore` by default (`--no-gitignore` to opt out)
- Skips `.git`, `.venv`, `node_modules`, `__pycache__` by default
- Streams results as found

---

## 7. Project Structure

```
askfind/
├── pyproject.toml
├── README.md
├── src/
│   └── askfind/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point, argument parsing
│       ├── config.py           # Config file + env var + keychain management
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py       # OpenAI-compatible HTTP client
│       │   ├── prompt.py       # System prompt + filter schema definition
│       │   └── parser.py       # Parse LLM JSON response into filter objects
│       ├── search/
│       │   ├── __init__.py
│       │   ├── filters.py      # Filter dataclass + matching logic
│       │   ├── walker.py       # Filesystem traversal with os.scandir()
│       │   └── reranker.py     # Optional LLM re-ranking of results
│       ├── interactive/
│       │   ├── __init__.py
│       │   ├── session.py      # REPL loop with conversation context
│       │   ├── commands.py     # Action commands (copy, preview, open)
│       │   └── pane.py         # tmux/zellij pane spawning logic
│       └── output/
│           ├── __init__.py
│           └── formatter.py    # Plain, verbose, JSON output formatting
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_llm_parser.py
│   ├── test_filters.py
│   ├── test_walker.py
│   └── test_formatter.py
└── docs/
    └── plans/
```

### Dependencies (`pyproject.toml`)

```toml
[project]
name = "askfind"
requires-python = ">=3.12"
dependencies = [
    "httpx",
    "rich",
    "prompt-toolkit",
    "keyring",
]

[project.scripts]
askfind = "askfind.cli:main"
```

---

## 8. Future Development

All deferred decisions and enhancements, in priority order.

### Phase 2 — Local LLM Support

- Ollama backend (same prompt, `localhost:11434` endpoint)
- Offline operation after model download
- No API key required

### Phase 3 — Additional LLM Backends

- Native Anthropic API format (`/v1/messages`)
- Native Google Gemini API format
- OAuth authentication (Claude Code-style, Codex-style, Gemini CLI-style) for subscription accounts

### Phase 4 — Advanced Search

- Deferred filter keys: `links`, `hidden`, `follow`, `compressed`
- Embedding-based search (vector index of filenames + contents for semantic matching)
- Pre-indexing for large codebases

### Phase 5 — Interactive Mode Enhancements

- Full-screen TUI mode via `textual` (`askfind -i --fullscreen`)
- Result history and session persistence across runs

### Phase 6 — MCP Integration

- Expose askfind as an MCP server so AI agents (Claude Code, Cursor, etc.) can use natural language file search as a tool
- Differentiator over existing filesystem MCP servers: NLP query layer, not just glob/pattern matching

### Phase 7 — Cross-Language Rewrites

- Rust or Go rewrite of the filesystem walker for performance
- Python remains for LLM interaction layer
- Hybrid architecture: Rust/Go binary for search, Python for orchestration

### Phase 8 — Distribution

- `pip install askfind`
- `brew install askfind`
- Standalone binary via PyInstaller or Nuitka

### Phase 9 — Multilingual Support

- Verify LLM filter extraction accuracy across major languages (Korean, Japanese, Chinese, Spanish, German, etc.)
- If accuracy drops for specific languages, add a lightweight translation pre-processing step
- Localize CLI output: help text, error messages, interactive mode commands
- i18n framework (e.g., `gettext` or `babel`)
- User-configurable language in config: `language = "ko"`

---

## Environment

- **Conda environment:** `dev_tool_env_askfind`
- **Python:** 3.12
- **Tool name:** `askfind`
- **CLI entry point:** `askfind`
