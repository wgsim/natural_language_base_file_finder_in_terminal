# Contributing to askfind

Thank you for considering contributing to askfind! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful and constructive. We're all here to build something useful together.

## How Can I Contribute?

### Reporting Bugs

Before creating a bug report:
1. Check the [existing issues](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/issues)
2. Try the latest version to see if it's already fixed
3. Collect information about your environment

When filing a bug report, include:
- **Clear title and description**
- **Steps to reproduce** the behavior
- **Expected behavior** vs actual behavior
- **Environment details** (OS, Python version, askfind version)
- **Relevant logs or error messages**

### Suggesting Features

Feature suggestions are welcome! Please:
1. Check the [Future Development Plan](docs/FUTURE_DEVELOPMENT.md)
2. Search existing feature requests
3. Describe the problem and your proposed solution
4. Explain why this would be useful to most users

### Pull Requests

#### Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/wgsim/natural_language_base_file_finder_in_terminal.git
   cd natural_language_base_file_finder_in_terminal
   ```

3. Create a feature branch:
   ```bash
   git checkout -b feature/amazing-feature
   ```

4. Set up development environment:
   ```bash
   conda env create -f environment.yml
   conda activate askfind_env
   git config core.hooksPath .githooks
   ```

#### Development Workflow

1. **Write Tests First** (TDD approach)
   ```bash
   # Write failing tests in tests/
   conda run -n askfind_env pytest tests/test_your_feature.py -v
   ```

2. **Implement Feature**
   - Keep changes focused and minimal
   - Follow existing code style
   - Add docstrings to public functions
   - Update type hints

3. **Run Tests**
   ```bash
   # Run all tests
   conda run -n askfind_env pytest tests/ -v

   # Run with coverage
   conda run -n askfind_env pytest tests/ --cov=askfind --cov-report=html
   ```

   If conda is unavailable locally, replace `conda run -n askfind_env pytest` with
   `./pytest_env/bin/pytest`.

4. **Check Code Quality**
   ```bash
   conda run -n askfind_env python scripts/ci/check_dev_tool_pins.py
   conda run -n askfind_env ruff check src tests scripts
   conda run -n askfind_env python -m mypy src
   ```

5. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add amazing feature"
   ```

#### Commit Message Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Maintenance tasks

**Examples:**
```bash
feat: add fuzzy search support
fix: handle empty query in interactive mode
docs: update installation instructions
test: add tests for filter matching
refactor: simplify walker logic
```

#### Pull Request Process

1. **Update Documentation**
   - Update README.md if adding user-facing features
   - Add docstrings to new functions/classes
   - Update FUTURE_DEVELOPMENT.md if implementing roadmap items

2. **Ensure Tests Pass**
   ```bash
   conda run -n askfind_env pytest tests/ -v
   ```
   All tests must pass before merging.

3. **Create Pull Request**
   - Use a clear, descriptive title
   - Reference related issues (`Fixes #123`)
   - Describe what changed and why
   - Add screenshots for UI changes

4. **Code Review**
   - Address reviewer feedback
   - Keep discussions constructive
   - Update PR based on comments

5. **Merge**
   - Squash commits if requested
   - Maintainer will merge when approved

#### Release Tags

Tagging `v*` (for example `v0.1.3`) triggers `.github/workflows/release.yml`:
- Build sdist/wheel via `python -m build`
- Validate artifacts via `twine check`
- Upload `dist/*` as workflow artifacts

## Development Guidelines

### Code Style

- **Python Version**: 3.12+
- **Style**: Follow PEP 8 generally, but prioritize readability
- **Line Length**: ~100 characters (not strict)
- **Type Hints**: Use type hints for function signatures
- **Docstrings**: Use for public functions and classes

### Testing

- **Philosophy**: Test-Driven Development (TDD)
- **Coverage**: CI gate is >=95%
- **Test Types**: Unit tests for all modules
- **Test Naming**: `test_<what>_<condition>_<expected>`

Example:
```python
def test_filter_matches_name_with_glob_pattern():
    filters = SearchFilters(name="*test*")
    assert filters.matches_name("test_auth.py") is True
    assert filters.matches_name("auth.py") is False
```

### Project Structure

```
askfind/
├── src/askfind/         # Source code
│   ├── cli.py           # CLI entry point
│   ├── config.py        # Configuration
│   ├── llm/             # LLM integration
│   ├── search/          # Search engine
│   ├── output/          # Output formatting
│   └── interactive/     # Interactive mode
├── tests/               # Test suite
├── docs/                # Documentation
└── pyproject.toml       # Project config
```

### Adding New Features

#### 1. New Filter Type

Add to `src/askfind/search/filters.py`:

```python
@dataclass
class SearchFilters:
    # ... existing filters ...
    your_filter: str | None = None

    def matches_your_criteria(self, path: Path) -> bool:
        if not self.your_filter:
            return True
        # Your logic here
        return True
```

Update `src/askfind/llm/prompt.py` to include your filter in the schema.

Write tests in `tests/test_filters.py`.

#### 2. New Action Command

Add to `src/askfind/interactive/commands.py`:

```python
def your_action(result: FileResult) -> None:
    # Your action implementation
    console.print("[green]Action completed[/green]")
```

Update `src/askfind/interactive/session.py` to handle the command.

#### 3. New Output Format

Add to `src/askfind/output/formatter.py`:

```python
def format_your_format(results: list[FileResult]) -> str:
    # Your formatting logic
    return formatted_output
```

Wire into `src/askfind/cli.py`.

Write tests in `tests/test_formatter.py`.

## Architecture Decisions

### Key Principles

1. **TDD**: Write tests before implementation
2. **Minimal Dependencies**: Only add dependencies when necessary
3. **Simplicity**: Prefer simple solutions over clever ones
4. **Performance**: Optimize for common cases
5. **Extensibility**: Design for future plugins

### Important Patterns

- **Cheapest-First Filtering**: Apply filters in order of cost (no I/O → stat → file read)
- **Lazy Evaluation**: Use generators to avoid loading all results in memory
- **Separation of Concerns**: CLI, LLM, search, and output are independent modules
- **Secure by Default**: API keys in keychain, not environment variables

## Getting Help

- 💬 [GitHub Discussions](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/discussions) - Ask questions
- 🐛 [Issues](https://github.com/wgsim/natural_language_base_file_finder_in_terminal/issues) - Report bugs
- 📖 [Documentation](README.md) - Read the docs

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in commits (`Co-Authored-By:`)

Significant contributions may earn you:
- Collaborator access
- Decision-making input on roadmap
- Your name in the hall of fame

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

Don't hesitate to ask! Open a discussion or issue, and we'll help you get started.

Happy coding! 🚀
