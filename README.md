# askfind

> Natural language file finder for the terminal

Find files using plain English queries instead of complex shell commands. askfind uses LLM-powered filter extraction to understand what you're looking for and searches your filesystem intelligently.

## Features

- 🗣️ **Natural Language Queries** - "python files modified this week" instead of `find . -name "*.py" -mtime -7`
- ⚡ **Optimized Search** - Cheapest-first filter application minimizes I/O operations
- 🎯 **Semantic Re-ranking** - Optional LLM re-ranking orders results by relevance
- 🙈 **Ignore-Aware Traversal** - Respects `.gitignore` and `.askfindignore` by default
- 🔗 **Safe Symlink Traversal** - Optional `--follow-symlinks` follows links only inside search root
- 🧪 **Binary File Exclusion** - Binary files are excluded by default (override with `--include-binary`)
- 📦 **Archive-Aware Matching** - Optional archive entry path/name and content (`has`) matching for `.zip` / `.tar.gz`
- 💾 **Search Cache** - Reuses recent query results (disable per run with `--no-cache`, inspect cache/index runtime counters with `--cache-stats`)
- 🗂️ **Index Management** - Build/update/status/clear optional per-root file indexes
- 🧠 **LLM Filter Memoization** - Reuses repeated filter-extraction calls (in-memory + disk cache)
- 🛟 **LLM Outage Fallback** - If filter extraction fails, askfind falls back to heuristic query parsing for core filters
- 🔌 **Explicit Offline Mode** - `--offline` skips API key/LLM and uses local heuristic parsing directly
- 💻 **Interactive Mode** - REPL with action commands in tmux/zellij panes
- 🔐 **Secure Secrets** - Keychain-first API key storage (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- 📋 **Multiple Output Formats** - Plain, verbose, or JSON output for scripting

## Installation

### Prerequisites

- Python 3.12 or higher
- An OpenAI-compatible API key for online mode (OpenRouter, OpenAI, local LLM via Ollama, etc.)
  - API key is not required when using `--offline`

### Install from Source

```bash
git clone https://github.com/wgsim/natural_language_base_file_finder_in_terminal.git
cd natural_language_base_file_finder_in_terminal
pip install -e ".[dev]"
```

### Quick Setup

```bash
# Store your API key securely
askfind config set-key

# Configure LLM provider (optional - defaults to OpenRouter)
askfind config set base_url "https://api.openai.com/v1"
askfind config set model "gpt-4o-mini"

# Test it out
askfind "python files in src"
```

## Usage

### Single Command Mode

```bash
# Basic search
askfind "python files"

# Complex queries
askfind "large javascript files modified this week"
askfind "markdown files containing TODO"
askfind "configuration files in src excluding tests"

# Output options
askfind "python files" --verbose    # Show size and date
askfind "python files" --json       # JSON output for scripting
askfind "python files" --max 10     # Limit results
askfind "python files" --workers 8  # Parallel traversal workers

# Disable re-ranking for faster results
askfind "python files" --no-rerank

# Disable cache for one command
askfind "python files" --no-cache

# Force local-only parsing (no API key / no LLM call)
askfind "python files in src" --offline

# Auto mode: simple queries use local parser, ambiguous queries call LLM
askfind "python files in src" --llm-mode auto --no-rerank

# Print cache/index counters for the command
askfind "python files" --cache-stats

# Optional index lifecycle commands
askfind index build --root .
askfind index update --root .
askfind index status --root .
askfind index clear --root .

# Search everything (ignore files disabled)
askfind "python files" --no-ignore

# Follow symlinks within root
askfind "python files" --follow-symlinks

# Include binary files in results
askfind "files in build output" --include-binary

# Search inside archive entries by path/name and content (`has`) (.zip, .tar.gz)
askfind "python files in archives" --search-archives
```

### Interactive Mode

```bash
# Launch interactive session (spawns in tmux/zellij pane)
askfind -i

# Launch interactive session in offline mode (no API key / no LLM call)
askfind -i --offline

# In the REPL:
askfind> python files in src
Found 15 file(s):
[1]  src/askfind/cli.py              2.1 KB  Jan 15 2026
[2]  src/askfind/config.py           1.8 KB  Jan 15 2026
...

# Action commands
askfind> copy path 1        # Copy file path to clipboard
askfind> copy content 2     # Copy file contents
askfind> preview 3          # Show syntax-highlighted preview
askfind> open 4             # Open in editor
askfind> help               # Show all commands
askfind> exit               # Quit
```

### Configuration

```bash
# View current configuration
askfind config show

# Set configuration values
askfind config set model "gpt-4o"
askfind config set llm_mode "auto"   # always | auto | off
askfind config set max_results 100
askfind config set parallel_workers 1
askfind config set cache_enabled true
askfind config set cache_ttl_seconds 300
askfind config set respect_ignore_files false
askfind config set follow_symlinks true
askfind config set exclude_binary_files false
askfind config set similarity_threshold 0.65
askfind config set editor "code"

# List available models from your provider
askfind config models
```

## How It Works

1. **Natural Language → Filters**:
   - Default mode sends your query to an LLM which extracts structured search filters (file extensions, paths, size constraints, modification times, content patterns, etc.).
   - `--llm-mode auto` uses local fallback parsing for simple queries and calls the LLM only for ambiguous queries.
   - `--llm-mode off` disables all LLM calls (same extraction behavior as heuristic mode).
   - `--offline` skips the LLM and directly applies heuristic query parsing for core filters (`ext`, `path`, `not_path`, `has`, `size`, `mod`).
   - If fallback parsing yields no meaningful filters in `--offline` mode, askfind exits with a non-zero status and a concise guidance message instead of running a broad search.

2. **Optimized Search**: Filters are applied in cheapest-first order:
   - Tier 0 (no I/O): type, depth, extension, name patterns
   - Tier 1 (stat call): modification time, size, permissions
   - Tier 2 (file read): content matching

   By default, traversal respects root `.gitignore` and `.askfindignore`. Use `--no-ignore` to disable this behavior.
   Binary files are excluded by default to reduce noisy results. Use `--include-binary` when needed.
   Symlinks are not followed unless `--follow-symlinks` is set.
   Archive entry path/name and `has` content matching are available with `--search-archives`.
   Search results are cached by default. Use `--no-cache` to bypass cache for one command, or `--cache-stats` to print cache hit/miss/set counters, index hit/fallback reasons, and LLM fallback usage stats.

3. **Optional Re-ranking**: Results can be semantically re-ranked by the LLM for better relevance (automatically skipped when heuristic fallback is used)

4. **Optional Index Management**: Use `askfind index` commands to precompute and manage
   per-root file path indexes for large repositories. When present and fresh, search
   execution attempts index query first, then falls back to live traversal if needed.

## Filter Schema

askfind understands these filter types:

| Filter | Example | Description |
|--------|---------|-------------|
| `ext` | `.py`, `.js` | File extensions to include |
| `not_ext` | `.pyc`, `.log` | File extensions to exclude |
| `name` | `*test*` | Glob pattern on filename |
| `path` | `src` | Path must contain string |
| `not_path` | `vendor` | Path must not contain string |
| `regex` | `test_.*\.py` | Regex pattern on filename |
| `fuzzy` | `confg` | Fuzzy match on filename |
| `mod` | `>7d` | Modified within timeframe |
| `mod_after` | `2026-01-01` | Modified on/after absolute date (UTC) |
| `mod_before` | `2026-01-15` | Modified up to absolute date (inclusive for date-only) |
| `size` | `>1MB` | File size constraint |
| `has` | `["TODO"]` | File content must contain terms |
| `similar` | `auth.py` | Files with content similar to the reference file |
| `loc` | `>200` | Non-empty line count constraint |
| `complexity` | `>15` | Approximate complexity constraint |
| `lang` | `["python"]` | Programming language(s) to include |
| `not_lang` | `["javascript"]` | Programming language(s) to exclude |
| `license` | `["mit"]` | License identifier(s) to include |
| `not_license` | `["gpl-3.0"]` | License identifier(s) to exclude |
| `tag` | `["ProjectX"]` | macOS Finder tags that must all be present |
| `type` | `file`, `dir` | Entry type |
| `depth` | `<5` | Directory depth limit |

Time units: `m` (minutes), `h` (hours), `d` (days), `w` (weeks)
Size units: `KB`, `MB`, `GB`, `TB`

## Examples

```bash
# Find Python files modified in the last week
askfind "python files modified in the last 7 days"

# Find large files
askfind "files larger than 10MB"

# Find files containing specific text
askfind "files containing TODO or FIXME"

# Find recent config files
askfind "config files modified today"

# Find test files
askfind "test files in src excluding vendor"

# Combine multiple criteria
askfind "small python files in src modified this week containing async"

# Tighten similarity matching for one command
askfind "files similar to auth.py" --similarity-threshold 0.8
```

## Configuration File

Config is stored in `~/.config/askfind/config.toml`:

```toml
[provider]
base_url = "https://openrouter.ai/api/v1"
model = "openai/gpt-4o-mini"

[search]
default_root = "."
max_results = 50
parallel_workers = 1
cache_enabled = true
cache_ttl_seconds = 300
respect_ignore_files = true
follow_symlinks = false
exclude_binary_files = true
search_archives = false
similarity_threshold = 0.55

[interactive]
editor = "vim"
```

API keys are stored securely in your system keychain, not in the config file.

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/wgsim/natural_language_base_file_finder_in_terminal.git
cd natural_language_base_file_finder_in_terminal

# Create conda environment
conda env create -f environment.yml
conda activate askfind_env

# Run tests
conda run -n askfind_env pytest tests/ -v
```

### Project Structure

```
askfind/
├── src/askfind/
│   ├── cli.py              # CLI entry point and argument parsing
│   ├── config.py           # Configuration and API key management
│   ├── llm/
│   │   ├── client.py       # OpenAI-compatible HTTP client
│   │   ├── prompt.py       # System prompt and filter schema
│   │   └── parser.py       # JSON response parsing
│   ├── search/
│   │   ├── filters.py      # Filter dataclass and matching logic
│   │   ├── walker.py       # Filesystem traversal
│   │   ├── index.py        # Persistent per-root index management
│   │   └── reranker.py     # Semantic re-ranking
│   ├── output/
│   │   └── formatter.py    # Output formatters (plain/verbose/JSON)
│   └── interactive/
│       ├── pane.py         # Multiplexer detection and spawning
│       ├── session.py      # REPL session
│       └── commands.py     # Action commands
├── tests/                  # Test suite
├── docs/                   # Documentation
└── pyproject.toml          # Project metadata and dependencies
```

### Running Tests

```bash
# Run all tests
conda run -n askfind_env pytest tests/ -v

# Fallback if conda is unavailable
./pytest_env/bin/pytest tests/ -v

# Run specific test file
conda run -n askfind_env pytest tests/test_filters.py -v

# Run with coverage
conda run -n askfind_env pytest tests/ --cov=askfind --cov-report=html
```

CI enforces a minimum coverage gate of 95%.
CI also runs a traversal performance regression gate via
`scripts/ci/benchmark_regression_gate.py`.
CI additionally validates index-query performance parity via
`scripts/ci/index_query_regression_gate.py`.

### Benchmark Traversal

```bash
# Traversal baseline (no LLM calls)
PYTHONPATH=src python scripts/bench/benchmark_walk.py --root . --repeats 5 --workers 4

# Persist benchmark artifacts for later comparison
PYTHONPATH=src python scripts/bench/benchmark_walk.py --root . --repeats 5 --workers 4 --output-json /tmp/askfind-bench.json --output-csv /tmp/askfind-bench.csv

# Compare baseline and candidate benchmark outputs
python scripts/bench/compare_benchmark_results.py --baseline /tmp/bench-baseline.json --candidate /tmp/bench-candidate.json --metric median_s --ratio-threshold 1.35

# CI-style performance regression check (parallel vs sequential median ratio)
PYTHONPATH=src python scripts/ci/benchmark_regression_gate.py --root .

# CI-style index-query regression check (index-query vs walk median ratio)
PYTHONPATH=src python scripts/ci/index_query_regression_gate.py --root .

# Optional: use a local index directory for sandboxed/dev runs
PYTHONPATH=src python scripts/ci/index_query_regression_gate.py --root . --index-dir /tmp/askfind-indexes
```

For reproducible multi-repo benchmark plans, see:
`docs/BENCHMARK_SCENARIOS.md`

Latest captured baseline:
`docs/benchmark-baseline-2026-02-28.md`

Release process checklist:
`docs/RELEASE_CHECKLIST.md`

### Git Hooks

This repository includes shared git hooks under `.githooks/`.

```bash
# One-time setup per clone/machine
git config core.hooksPath .githooks
```

After setup, both `pre-commit` and `pre-push` run lint+tests using:

```bash
conda run -n askfind_env sh -lc 'python scripts/ci/check_dev_tool_pins.py && ruff check src tests scripts && PYTHONPATH=src pytest -q'
```

If `askfind_env` is not available, hooks fall back to `./pytest_env/bin/ruff` and
`./pytest_env/bin/pytest`.

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`conda run -n askfind_env pytest tests/ -v`)
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Troubleshooting

### "No API key configured"

```bash
# Store your API key
askfind config set-key
# Enter your key when prompted
```

### "ModuleNotFoundError"

Make sure you've installed the package:

```bash
pip install -e .
```

### Interactive mode not spawning pane

askfind will fall back to inline mode if:
- You're not in tmux or zellij
- The multiplexer binary isn't in PATH

### Slow searches

Try disabling re-ranking for faster results:

```bash
askfind "your query" --no-rerank
```

## FAQ

**Q: What LLM providers are supported?**
A: Any OpenAI-compatible API (OpenRouter, OpenAI, Azure OpenAI, local Ollama, etc.)

**Q: Does askfind send my file contents to the LLM?**
A: No. Only your query and file paths are sent. File contents stay local unless you use re-ranking (which sends paths only).

**Q: Can I use this with local LLMs?**
A: Yes! Point it to your local LLM server:
```bash
askfind config set base_url "http://localhost:11434/v1"
askfind config set model "llama3"
```

**Q: How much does it cost?**
A: Typical query uses ~500 tokens ($0.001-0.01 depending on model). Re-ranking adds another small request.

**Q: Is my API key secure?**
A: Yes. Keys are stored in your system's keychain (macOS Keychain, Linux Secret Service, Windows Credential Manager), not in plaintext config files.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

Built with:
- [httpx](https://www.python-httpx.org/) - HTTP client
- [rich](https://rich.readthedocs.io/) - Terminal formatting
- [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/) - Interactive REPL
- [keyring](https://pypi.org/project/keyring/) - Secure credential storage
- [pytest](https://pytest.org/) - Testing framework

## Support

- 🐛 [Report a bug](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/issues)
- 💡 [Request a feature](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/issues)
- 📖 [Documentation](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/tree/main/docs)
