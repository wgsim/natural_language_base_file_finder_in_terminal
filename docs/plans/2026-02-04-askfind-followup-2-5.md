# Askfind Follow-up (Items 2–5) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add preview options, provider list output, .askfindignore support, tolerant parsing improvements, and clearer root errors.

**Architecture:** Isolate new CLI flags in `cli.py`, add small helpers in `commands.py` and `walker.py`, and extend parser/filters with strict but user-friendly validation. Tests cover each new behavior.

**Tech Stack:** Python 3.12, pytest, rich.

### Task 1: Add preview options (file size + binary indicator)

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_preview_includes_size_and_binary_flag(tmp_path, capsys):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    preview(result)
    out = capsys.readouterr().out
    assert "Size:" in out
    assert "Binary:" in out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_preview_includes_size_and_binary_flag -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# commands.py
# Print a short metadata line before preview:
# Size: <human_size> | Binary: yes/no
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_preview_includes_size_and_binary_flag -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: include preview metadata"
```

### Task 2: Add provider list output for `config models`

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("httpx.get")
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("askfind.cli.Config.from_file")
def test_config_models_provider_list(mock_config_cls, mock_get_key, mock_get, capsys):
    mock_config = MagicMock()
    mock_config.base_url = "http://test"
    mock_config.model = "test-model"
    mock_config.max_results = 50
    mock_config_cls.return_value = mock_config
    mock_get.return_value.json.return_value = {
        "data": [{"id": "openai/gpt-4o"}, {"id": "anthropic/claude-3.5"}]
    }
    mock_get.return_value.raise_for_status.return_value = None
    result = main(["config", "models", "--provider", "list"])
    assert result == 0
    out = capsys.readouterr().out
    assert "openai" in out and "anthropic" in out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_config_models_provider_list -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# cli.py
# if args.provider == "list": print unique provider prefixes
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_config_models_provider_list -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: list providers for config models"
```

### Task 3: Support `.askfindignore`

**Files:**
- Modify: `src/askfind/search/walker.py`
- Test: `tests/test_walker.py`

**Step 1: Write the failing test**

```python
def test_askfindignore_skips_paths(self, tmp_path):
    _make_tree(tmp_path)
    (tmp_path / ".askfindignore").write_text("tests\n")
    filters = SearchFilters()
    results = list(walk_and_filter(tmp_path, filters))
    names = {p.name for p in results}
    assert "test_auth.py" not in names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_askfindignore_skips_paths -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# walker.py
# read .askfindignore at root once
# add ignored directory names to SKIP_DIRS
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_askfindignore_skips_paths -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_walker.py src/askfind/search/walker.py
git commit -m "feat: support .askfindignore"
```

### Task 4: Tolerant parsing improvements (size/mod)

**Files:**
- Modify: `src/askfind/search/filters.py`
- Test: `tests/test_filters.py`

**Step 1: Write the failing test**

```python
def test_size_parsing_allows_spaces_and_case(self):
    assert parse_size(" 1 mb ") == 1024 * 1024


def test_time_parsing_allows_spaces(self):
    assert parse_time_delta(" 7 d ").days == 7
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_filters.py::TestParseSize::test_size_parsing_allows_spaces_and_case -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# filters.py
# normalize by removing spaces before unit parsing
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_filters.py::TestParseSize::test_size_parsing_allows_spaces_and_case tests/test_filters.py::TestParseTimeDelta::test_time_parsing_allows_spaces -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_filters.py src/askfind/search/filters.py
git commit -m "feat: allow spaced size/time inputs"
```

### Task 5: Clearer error when --root is a file

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("askfind.cli.Config.from_file")
@patch("askfind.cli.LLMClient")
def test_root_file_error_message(mock_llm, mock_cfg, mock_key, tmp_path, capsys):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    mock_cfg.return_value = MagicMock(base_url="http://test", model="m", max_results=50)
    mock_llm.return_value.__enter__.return_value = mock_llm.return_value
    mock_llm.return_value.extract_filters.return_value = "{}"
    result = main(["query", "--root", str(file_path)])
    assert result == 3
    err = capsys.readouterr().err
    assert "Search root is a file" in err
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_root_file_error_message -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# cli.py
# after root = Path(args.root).resolve(), check root.is_file() and error
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_root_file_error_message -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: improve root file error"
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-followup-2-5.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
