"""System prompt and schema for LLM filter extraction."""

from __future__ import annotations

from datetime import datetime, timezone

FILTER_SCHEMA = """\
{
  "ext": [".py"],        // file extensions to include
  "not_ext": [".pyc"],   // file extensions to exclude
  "name": "*test*",      // glob on filename
  "not_name": "*cache*", // glob to exclude
  "path": "src",         // path must contain
  "not_path": "vendor",  // path must not contain
  "regex": "pattern",    // regex on filename
  "fuzzy": "confg",      // fuzzy match on filename
  "mod": ">7d",          // modified within (d=days, h=hours, m=minutes, w=weeks)
  "cre": ">1d",          // created within
  "acc": ">3d",          // accessed within
  "newer": "file.py",    // newer than reference file
  "size": ">1MB",        // size (KB, MB, GB)
  "lines": ">100",       // line count
  "has": ["TODO"],       // file content contains all terms
  "type": "file",        // file, dir, link
  "cat": "python",       // category: python, javascript, image, binary, text...
  "depth": "<5",         // directory depth
  "perm": "x",           // permissions: r, w, x
  "owner": "root"        // file owner
}\
"""


def build_system_prompt() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""\
You are a file search assistant. Given a natural language query about finding files, \
extract structured search filters as a JSON object.

Current date/time: {now}

Return ONLY a JSON object with relevant keys. Omit keys that are not needed. \
Use the shortest representation possible.

Available keys:
{FILTER_SCHEMA}

Rules:
- Return ONLY the JSON object, no explanation, no markdown.
- Use relative time: "7d" not "2026-01-26".
- For "this week" use ">7d". For "today" use ">1d". For "this month" use ">30d".
- ext values must include the dot: ".py" not "py".
- has accepts a list of strings that must ALL appear in the file content.
- Only include keys relevant to the query.\
"""
