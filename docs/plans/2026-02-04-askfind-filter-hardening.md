# Askfind Filter Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve `depth` handling (current semantics), harden `size/mod` parsing, and stabilize interactive clipboard operations.

**Architecture:** Keep current “directory depth” semantics for `depth` while pruning recursion earlier. Add defensive parsing in LLM filter handling so invalid constraints do not crash search. Make clipboard actions robust to encoding and missing tools without changing user-facing behavior beyond error messages.

**Tech Stack:** Python 3.12, pytest, prompt-toolkit, rich.

### Task 1: Define and enforce `depth` recursion pruning (current semantics)

**Files:**
- Modify: `src/askfind/search/walker.py`
- Test: `tests/test_walker.py`

**Step 1: Write the failing test**

```python
def test_depth_prunes_recursion(self, tmp_path):
    _make_tree(tmp_path)
    filters = SearchFilters(depth="<1")
    results = list(walk_and_filter(tmp_path, filters))
    # root depth is 0; with <1, only root entries should be considered
    names = {p.name for p in results}
    assert "src" in names  # directory at depth 0
    assert "readme.md" in names  # file at depth 0
    assert "login.py" not in names  # deeper file should be pruned
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_depth_prunes_recursion -v`
Expected: FAIL (deeper entries still appear)

**Step 3: Write minimal implementation**

```python
# walker.py
# After computing entry_path and depth, decide whether to recurse
# If depth filter fails for this directory, skip recursing into it
if is_dir and not filters.matches_depth(depth + 1):
    continue
```

(Keep `matches_depth(depth)` for current entry evaluation to preserve existing semantics.)

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_walker.py::TestWalkAndFilter::test_depth_prunes_recursion -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_walker.py src/askfind/search/walker.py
git commit -m "fix: prune recursion with depth filter"
```

### Task 2: Harden `size/mod` parsing to avoid crashes

**Files:**
- Modify: `src/askfind/search/filters.py`
- Test: `tests/test_filters.py`

**Step 1: Write the failing test**

```python
def test_invalid_size_does_not_raise(self, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    stat = f.stat()
    filters = SearchFilters(size=">not-a-size")
    assert filters.matches_stat(stat) is True  # invalid constraint should be ignored

def test_invalid_mod_does_not_raise(self, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    stat = f.stat()
    filters = SearchFilters(mod=">not-a-time")
    assert filters.matches_stat(stat) is True  # invalid constraint should be ignored
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_size_does_not_raise -v`
Expected: FAIL (ValueError)

**Step 3: Write minimal implementation**

```python
# filters.py in matches_stat
if self.size:
    try:
        op, val = _parse_constraint(self.size)
        size_bytes = parse_size(val)
    except ValueError:
        pass  # ignore invalid size constraint
    else:
        if op == ">" and stat.st_size <= size_bytes:
            return False
        if op == "<" and stat.st_size >= size_bytes:
            return False

if self.mod:
    try:
        op, val = _parse_constraint(self.mod)
        delta = parse_time_delta(val)
    except ValueError:
        pass  # ignore invalid mod constraint
    else:
        cutoff = datetime.now(timezone.utc) - delta
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if op == ">" and mtime < cutoff:
            return False
        if op == "<" and mtime > cutoff:
            return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_filters.py::TestSearchFilters::test_invalid_size_does_not_raise -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_filters.py src/askfind/search/filters.py
git commit -m "fix: ignore invalid size/mod constraints"
```

### Task 3: Stabilize interactive clipboard/content operations

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_pane.py` (add new unit tests here if feasible) or create `tests/test_commands.py`

**Step 1: Write the failing test**

```python
# new test file: tests/test_commands.py
from pathlib import Path
from unittest.mock import patch
from askfind.output.formatter import FileResult
from askfind.interactive.commands import copy_content


def test_copy_content_handles_decode_error(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\xff\xfe\xfd")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands._copy_to_clipboard") as _:
        copy_content(result)  # should not raise
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_copy_content_handles_decode_error -v`
Expected: FAIL (UnicodeDecodeError)

**Step 3: Write minimal implementation**

```python
# commands.py in copy_content
try:
    content = result.path.read_text(errors="replace")
    _copy_to_clipboard(content)
    console.print(f"[green]Copied content of: {result.path.name}[/green]")
except (OSError, UnicodeDecodeError) as e:
    console.print(f"[red]Error reading file: {e}[/red]")
```

Also harden `_copy_to_clipboard` for missing tools:

```python
# commands.py
elif sys.platform == "linux":
    try:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
    except FileNotFoundError:
        try:
            subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
        except FileNotFoundError:
            console.print("[red]Clipboard tool not found (xclip/xsel).[/red]")
            return
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_copy_content_handles_decode_error -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "fix: harden interactive clipboard operations"
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-filter-hardening.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
