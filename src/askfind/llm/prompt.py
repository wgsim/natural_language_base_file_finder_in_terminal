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
  "lang": ["python"],    // language to include (e.g., python, javascript)
  "not_lang": ["javascript"], // language to exclude
  "license": ["mit"],    // license id(s) to include (e.g., mit, apache-2.0)
  "not_license": ["gpl-3.0"], // license id(s) to exclude
  "tag": ["ProjectX"],   // macOS Finder tags (all tags must be present)
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
- lang/not_lang accept language names (e.g., python, javascript, typescript, shell).
- license/not_license accept normalized license ids (e.g., mit, apache-2.0, gpl-3.0).
- tag accepts a list of macOS Finder tag names that must ALL be present.
- Only include keys relevant to the query.\
"""
