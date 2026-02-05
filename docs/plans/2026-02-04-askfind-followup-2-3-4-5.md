# Askfind Follow-up (Items 2–5) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve provider list output, preview error handling, LLM parse error reporting, and default root resolution.

**Architecture:** Keep changes localized to `cli.py`, `commands.py`, `llm/parser.py`, and `config.py`. Add tests for each new behavior with minimal surface changes.

**Tech Stack:** Python 3.12, pytest, rich.

### Task 1: Improve provider list output format

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("httpx.get")
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("askfind.cli.Config.from_file")
def test_config_models_provider_list_sorted(mock_config_cls, mock_get_key, mock_get, capsys):
    mock_config = MagicMock()
    mock_config.base_url = "http://test"
    mock_config.model = "test-model"
    mock_config.max_results = 50
    mock_config_cls.return_value = mock_config
    mock_get.return_value.json.return_value = {
        "data": [{"id": "zeta/a"}, {"id": "alpha/b"}]
    }
    mock_get.return_value.raise_for_status.return_value = None
    result = main(["config", "models", "--provider", "list"])
    assert result == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["alpha", "zeta"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_config_models_provider_list_sorted -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# cli.py
# ensure providers list is sorted and printed one per line
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_config_models_provider_list_sorted -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: sort provider list output"
```

### Task 2: Preview error handling (binary=unknown on read failure)

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_preview_binary_unknown_on_read_error(tmp_path, capsys, monkeypatch):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    monkeypatch.setattr(result.path, "read_bytes", lambda: (_ for _ in ()).throw(OSError("boom")))
    preview(result)
    out = capsys.readouterr().out
    assert "Binary: unknown" in out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_preview_binary_unknown_on_read_error -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# commands.py
# in _is_binary, return None on OSError; in preview, display Binary: unknown
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_preview_binary_unknown_on_read_error -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: show binary unknown on read error"
```

### Task 3: LLM parse error reporting option

**Files:**
- Modify: `src/askfind/llm/parser.py`
- Modify: `src/askfind/cli.py`
- Test: `tests/test_llm_parser.py`

**Step 1: Write the failing test**

```python
def test_parse_llm_response_with_errors():
    raw = "not json"
    filters, errors = parse_llm_response(raw, return_errors=True)
    assert filters is not None
    assert errors
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_parser.py::TestParseLlmResponse::test_parse_llm_response_with_errors -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# parser.py
# add return_errors flag returning (filters, errors)
# keep backward-compatible default behavior
```

**Step 4: Wire to CLI**

```python
# cli.py
# if env var ASKFIND_DEBUG=1, print parse errors to stderr
```

**Step 5: Run tests**

Run: `pytest tests/test_llm_parser.py::TestParseLlmResponse::test_parse_llm_response_with_errors -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_llm_parser.py src/askfind/llm/parser.py src/askfind/cli.py
git commit -m "feat: report LLM parse errors in debug"
```

### Task 4: default_root respected when --root not provided

**Files:**
- Modify: `src/askfind/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
@patch("askfind.cli.get_api_key", return_value="sk-test")
@patch("askfind.cli.Config.from_file")
@patch("askfind.cli.LLMClient")
def test_default_root_used_when_root_missing(mock_llm, mock_cfg, mock_key, tmp_path):
    mock_cfg.return_value = MagicMock(base_url="http://test", model="m", max_results=50, default_root=str(tmp_path))
    mock_llm.return_value.__enter__.return_value = mock_llm.return_value
    mock_llm.return_value.extract_filters.return_value = "{}"
    result = main(["query"])
    assert result == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_default_root_used_when_root_missing -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# cli.py
# when args.root is default '.', use config.default_root instead
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_default_root_used_when_root_missing -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_cli.py src/askfind/cli.py
git commit -m "feat: honor default_root" 
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-followup-2-3-4-5.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
