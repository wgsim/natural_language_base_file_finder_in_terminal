"""Parse LLM responses into SearchFilters."""

from __future__ import annotations

import json
import re
from dataclasses import fields

from askfind.search.filters import SearchFilters

_LIST_FIELDS = {"ext", "not_ext", "has"}


def parse_llm_response(raw: str) -> SearchFilters:
    """Parse a raw LLM response string into SearchFilters.

    Handles JSON wrapped in markdown code blocks or surrounding text.
    Returns empty SearchFilters on parse failure.
    """
    json_str = _extract_json(raw)
    if json_str is None:
        return SearchFilters()
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return SearchFilters()
    if not isinstance(data, dict):
        return SearchFilters()
    valid_names = {f.name for f in fields(SearchFilters)}
    kwargs = {}
    for key, value in data.items():
        if key not in valid_names:
            continue
        if key in _LIST_FIELDS and isinstance(value, str):
            value = [value]
        kwargs[key] = value
    return SearchFilters(**kwargs)


def _extract_json(raw: str) -> str | None:
    """Extract JSON object from raw text."""
    raw = raw.strip()
    # Try markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if md_match:
        return md_match.group(1).strip()
    # Try to find JSON object directly
    brace_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if brace_match:
        return brace_match.group(0)
    return None
