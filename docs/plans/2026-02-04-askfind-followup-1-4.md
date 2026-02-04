# Askfind Follow-up (Items 1-4) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden parsing with warnings, unify preview/copy messaging, guard invalid perm/depth values, and improve `config models` errors.

**Architecture:** Keep changes localized in `filters.py`, `commands.py`, and `cli.py`. Warnings are printed to stderr to avoid disrupting normal output.

**Tech Stack:** Python 3.12, pytest, rich.

### Task 1: Warn and ignore invalid size/mod values (including negatives/spaces/units)

**Files:**
- Modify: `src/askfind/search/filters.py`
- Test: `tests/test_filters.py`

**Step 1: Write the failing test**

```python
def test_invalid_size_emits_warning(self, tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("x")
    stat = f.stat()
    filters = SearchFilters(size=">-1MB")
    assert filters.matches_stat(stat) is True
    err = capsys.readouterr().err
    assert "Invalid size" in err


def test_invalid_mod_emits_warning(self, tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("x")
    stat = f.stat()
    filters = SearchFilters(mod="> 7 days")
    assert filters.matches_stat(stat) is True
    err = capsys.readouterr().err
    assert "Invalid mod" in err
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_size_emits_warning -v`
Expected: FAIL (no stderr warning)

**Step 3: Write minimal implementation**

```python
# filters.py
# on ValueError for size/mod, print warning to stderr and ignore constraint
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_size_emits_warning tests/test_filters.py::TestSearchFilters::test_invalid_mod_emits_warning -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_filters.py src/askfind/search/filters.py
git commit -m "feat: warn and ignore invalid size/mod"
```

### Task 2: Unify preview/copy warning messages

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_copy_and_preview_binary_message_consistent(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff")
    result = FileResult.from_path(f)
    copy_content(result)
    preview(result)
    out = capsys.readouterr().out
    assert out.count("Skipping binary file") == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_copy_and_preview_binary_message_consistent -v`
Expected: FAIL (messages inconsistent)

**Step 3: Write minimal implementation**

```python
# commands.py
# use a shared helper to format binary skip message
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_copy_and_preview_binary_message_consistent -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: unify binary skip messaging"
```

### Task 3: Guard invalid perm/depth values

**Files:**
- Modify: `src/askfind/search/filters.py`
- Test: `tests/test_filters.py`

**Step 1: Write the failing test**

```python
def test_invalid_perm_emits_warning(self, tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("x")
    stat = f.stat()
    filters = SearchFilters(perm="z")
    assert filters.matches_stat(stat) is True
    err = capsys.readouterr().err
    assert "Invalid perm" in err


def test_invalid_depth_emits_warning(self, capsys):
    filters = SearchFilters(depth="=x")
    assert filters.matches_depth(0) is True
    err = capsys.readouterr().err
    assert "Invalid depth" in err
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_perm_emits_warning -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# filters.py
# validate perm only contains r/w/x; warn+ignore otherwise
# validate depth is int; warn+ignore otherwise
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_perm_emits_warning tests/test_filters.py::TestSearchFilters::test_invalid_depth_emits_warning -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_filters.py src/askfind/search/filters.py
git commit -m "feat: warn on invalid perm/depth"
```

### Task 4: Improve `config models` error messaging

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("httpx.get")
def test_config_models_provider_no_match(mock_get, mock_key, capsys):
    mock_get.return_value.json.return_value = {"data": [{"id": "openai/gpt-4o"}]}
    mock_get.return_value.raise_for_status.return_value = None
    result = main(["config", "models", "--provider", "anthropic"])
    assert result == 0
    err = capsys.readouterr().err
    assert "No models found" in err
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestMain::test_config_models_provider_no_match -v`
Expected: FAIL (no stderr message)

**Step 3: Write minimal implementation**

```python
# cli.py
# track printed count, if provider set and zero results, print stderr warning
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::TestMain::test_config_models_provider_no_match -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: warn when provider has no models"
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-followup-1-4.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
