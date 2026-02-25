# askfind

> Natural language file finder for the terminal

Find files using plain English queries instead of complex shell commands. askfind uses LLM-powered filter extraction to understand what you're looking for and searches your filesystem intelligently.

## Features

- 🗣️ **Natural Language Queries** - "python files modified this week" instead of `find . -name "*.py" -mtime -7`
- ⚡ **Optimized Search** - Cheapest-first filter application minimizes I/O operations
- 🎯 **Semantic Re-ranking** - Optional LLM re-ranking orders results by relevance
- 💻 **Interactive Mode** - REPL with action commands in tmux/zellij panes
- 🔐 **Secure Secrets** - Keychain-first API key storage (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- 📋 **Multiple Output Formats** - Plain, verbose, or JSON output for scripting

## Installation

### Prerequisites

- Python 3.12 or higher
- An OpenAI-compatible API key (OpenRouter, OpenAI, local LLM via Ollama, etc.)

### Install from Source

```bash
git clone https://github.com/yourusername/askfind.git
cd askfind
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

# Disable re-ranking for faster results
askfind "python files" --no-rerank
```

### Interactive Mode

```bash
# Launch interactive session (spawns in tmux/zellij pane)
askfind -i

# In the REPL:
askfind> python files in src
Found 15 file(s):
[1]  src/askfind/cli.py              2.1 KB  Jan 15
[2]  src/askfind/config.py           1.8 KB  Jan 15
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
askfind config set max_results 100
askfind config set editor "code"

# List available models from your provider
askfind config models
```

## How It Works

1. **Natural Language → Filters**: Your query is sent to an LLM which extracts structured search filters (file extensions, paths, size constraints, modification times, content patterns, etc.)

2. **Optimized Search**: Filters are applied in cheapest-first order:
   - Tier 0 (no I/O): type, depth, extension, name patterns
   - Tier 1 (stat call): modification time, size, permissions
   - Tier 2 (file read): content matching

3. **Optional Re-ranking**: Results can be semantically re-ranked by the LLM for better relevance

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
| `size` | `>1MB` | File size constraint |
| `has` | `["TODO"]` | File content must contain terms |
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

[interactive]
editor = "vim"
```

API keys are stored securely in your system keychain, not in the config file.

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/askfind.git
cd askfind

# Create conda environment
conda env create -f environment.yml
conda activate askfind_env

# Run tests
pytest tests/ -v
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
│   │   └── reranker.py     # Semantic re-ranking
│   ├── output/
│   │   └── formatter.py    # Output formatters (plain/verbose/JSON)
│   └── interactive/
│       ├── pane.py         # Multiplexer detection and spawning
│       ├── session.py      # REPL session
│       └── commands.py     # Action commands
├── tests/                  # Test suite (73 tests)
├── docs/                   # Documentation
└── pyproject.toml          # Project metadata and dependencies
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_filters.py -v

# Run with coverage
pytest tests/ --cov=askfind --cov-report=html
```

### Git Hooks

This repository includes shared git hooks under `.githooks/`.

```bash
# One-time setup per clone/machine
git config core.hooksPath .githooks
```

After setup, both `pre-commit` and `pre-push` run tests using:

```bash
conda run -n askfind_env sh -lc 'PYTHONPATH=src pytest -q'
```

If `askfind_env` is not available, hooks fall back to `./pytest_env/bin/pytest`.

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest tests/`)
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

- 🐛 [Report a bug](https://github.com/yourusername/askfind/issues)
- 💡 [Request a feature](https://github.com/yourusername/askfind/issues)
- 📖 [Documentation](https://github.com/yourusername/askfind/wiki)
