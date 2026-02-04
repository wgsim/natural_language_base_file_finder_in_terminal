# Askfind Interactive Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve interactive clipboard UX by adding clearer guidance, binary detection, and stronger tool detection.

**Architecture:** Keep changes localized to interactive command helpers. Add small helper functions for binary detection and clipboard tool selection to minimize behavioral changes. Tests cover new behaviors at unit level.

**Tech Stack:** Python 3.12, pytest, rich.

### Task 1: Improve clipboard-missing guidance messages

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_copy_content_reports_missing_clipboard_tool(tmp_path, capsys):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands.sys.platform", "linux"):
        with patch("askfind.interactive.commands.subprocess.run", side_effect=FileNotFoundError()):
            copy_content(result)
    captured = capsys.readouterr()
    assert "Clipboard tool not found" in captured.out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_copy_content_reports_missing_clipboard_tool -v`
Expected: FAIL (no message or unhandled error)

**Step 3: Write minimal implementation**

```python
# commands.py
# when clipboard tool is missing, print a clear message with hints
console.print("[red]Clipboard tool not found (xclip/xsel). Install one of them to enable copy.[/red]")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_copy_content_reports_missing_clipboard_tool -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: improve clipboard missing guidance"
```

### Task 2: Add binary detection for copy/preview

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_copy_content_skips_binary(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff\x00\xff")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands._copy_to_clipboard") as mocked:
        copy_content(result)
        mocked.assert_not_called()
    captured = capsys.readouterr()
    assert "binary" in captured.out.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_copy_content_skips_binary -v`
Expected: FAIL (attempts to read/copy content)

**Step 3: Write minimal implementation**

```python
# commands.py
# add helper

def _is_binary(path: Path) -> bool:
    try:
        data = path.read_bytes()[:1024]
    except OSError:
        return False
    return b"\x00" in data

# in copy_content/preview
if _is_binary(result.path):
    console.print(f"[yellow]Skipping binary file: {result.path}[/yellow]")
    return
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_copy_content_skips_binary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: detect and skip binary files"
```

### Task 3: Strengthen clipboard tool detection (Wayland + Windows guidance)

**Files:**
- Modify: `src/askfind/interactive/commands.py`
- Test: `tests/test_commands.py`

**Step 1: Write the failing test**

```python
def test_copy_content_uses_wl_copy_when_available(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands.sys.platform", "linux"):
        with patch("askfind.interactive.commands.shutil.which", return_value="/usr/bin/wl-copy"):
            with patch("askfind.interactive.commands.subprocess.run") as mocked:
                copy_content(result)
                mocked.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_commands.py::test_copy_content_uses_wl_copy_when_available -v`
Expected: FAIL (wl-copy not used)

**Step 3: Write minimal implementation**

```python
# commands.py
# prefer wl-copy on Wayland if available
if sys.platform == "linux":
    wl_copy = shutil.which("wl-copy")
    if wl_copy:
        subprocess.run([wl_copy], input=text.encode(), check=True)
        return
    # fallback to xclip/xsel as before
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_commands.py::test_copy_content_uses_wl_copy_when_available -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_commands.py src/askfind/interactive/commands.py
git commit -m "feat: support wl-copy clipboard tool"
```

---

**Plan complete and saved to `docs/plans/2026-02-04-askfind-interactive-enhancements.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
