# Askfind Follow-up Top3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend interactive preview UX, document depth semantics, and implement provider filtering for `config models`.

**Architecture:** Keep changes localized to interactive commands, documentation, and CLI config handling. Use TDD for each behavior change.

**Tech Stack:** Python 3.12, pytest, rich.

### Task 1: Preview messaging improvements (binary + limit)

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_preview_skips_binary(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff")
    result = FileResult.from_path(f)
    preview(result)
    captured = capsys.readouterr()
    assert "Skipping binary file" in captured.out


def test_preview_reports_line_limit(tmp_path, capsys):
    f = tmp_path / "many.txt"
    f.write_text("\n".join(["x"] * 60))
    result = FileResult.from_path(f)
    preview(result)
    captured = capsys.readouterr()
    assert "more lines" in captured.out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_preview_skips_binary -v`
Expected: FAIL (no binary message)

**Step 3: Write minimal implementation**

```python
# commands.py
# reuse _is_binary for preview
# ensure "... (N more lines)" remains after limiting to 50 lines
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_preview_skips_binary tests/test_commands.py::test_preview_reports_line_limit -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: improve preview messaging"
```

### Task 2: Depth semantics documentation + tests

**Files:**
- Modify: `README.md`
- Test: `tests/test_walker.py`

**Step 1: Write the failing test**

```python
def test_depth_zero_matches_root_only(self, tmp_path):
    _make_tree(tmp_path)
    filters = SearchFilters(depth="=0")
    results = list(walk_and_filter(tmp_path, filters))
    names = {p.name for p in results}
    assert "readme.md" in names
    assert "src" in names
    assert "login.py" not in names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_depth_zero_matches_root_only -v`
Expected: FAIL (deep files included)

**Step 3: Write minimal implementation**

No code change expected if current depth pruning works; adjust test if needed to match semantics.

**Step 4: Update README**

Add a short note in Filter Schema section describing depth semantics (root depth 0, directories are pruned when depth limit exceeded).

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_depth_zero_matches_root_only -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_walker.py README.md
git commit -m "docs: clarify depth semantics"
```

### Task 3: Provider filter for `config models`

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("askfind.cli.httpx.get")
def test_config_models_filters_by_provider(mock_get, mock_key, capsys):
    mock_get.return_value.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o"},
            {"id": "anthropic/claude-3.5"},
        ]
    }
    mock_get.return_value.raise_for_status.return_value = None
    result = main(["config", "models", "--provider", "openai"])
    assert result == 0
    out = capsys.readouterr().out
    assert "openai/gpt-4o" in out
    assert "anthropic/claude-3.5" not in out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestMain::test_config_models_filters_by_provider -v`
Expected: FAIL (no filtering)

**Step 3: Write minimal implementation**

```python
# cli.py _handle_config models
# if args.provider: filter model id prefix before printing
# provider prefix = id.split("/", 1)[0]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::TestMain::test_config_models_filters_by_provider -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: filter models by provider"
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-followup-top3.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
