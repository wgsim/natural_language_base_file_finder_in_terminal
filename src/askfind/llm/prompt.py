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
  "mod_after": "2026-01-01",   // modified on/after absolute date (YYYY-MM-DD or ISO datetime)
  "mod_before": "2026-01-15",  // modified before absolute date boundary (YYYY-MM-DD or ISO datetime)
  "size": ">1MB",        // size (KB, MB, GB)
  "has": ["TODO"],       // file content contains all terms
  "type": "file",        // file, dir, link
  "depth": "<5",         // directory depth
  "perm": "x"            // permissions: r, w, x
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
- Use `mod` for relative time queries (e.g., "last 7 days").
- Use `mod_after`/`mod_before` for explicit absolute dates or date ranges.
- For "between Jan 1 and Jan 15", set both keys with `YYYY-MM-DD`.
- For "this week" use ">7d". For "today" use ">1d". For "this month" use ">30d".
- ext values must include the dot: ".py" not "py".
- has accepts a list of strings that must ALL appear in the file content.
- Only include keys relevant to the query.\
"""
