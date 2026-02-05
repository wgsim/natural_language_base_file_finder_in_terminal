"""Parse LLM responses into SearchFilters."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path

from askfind.search.filters import SearchFilters

_LIST_FIELDS = {"ext", "not_ext", "has"}
_MAX_LIST_LENGTH = 20  # Maximum items in list fields
_MAX_TERM_LENGTH = 200  # Maximum length of individual terms


def _validate_and_sanitize_value(key: str, value: any) -> any | None:
    """Validate and sanitize field values from LLM response.

    Returns sanitized value or None if invalid.
    """
    # Validate list fields
    if key in _LIST_FIELDS:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return None
        # Limit list length and term length
        value = value[:_MAX_LIST_LENGTH]
        value = [str(v)[:_MAX_TERM_LENGTH] for v in value if v]
        if not value:
            return None
        return value

    # Sanitize path fields to prevent directory traversal
    if key in ("path", "not_path"):
        if not isinstance(value, str):
            return None
        value = str(value)[:_MAX_TERM_LENGTH]
        # Convert to relative path and normalize
        try:
            p = Path(value)
            # Reject absolute paths
            if p.is_absolute():
                return None
            # Reject paths with parent directory references that escape root
            normalized = p.as_posix()
            if normalized.startswith("../") or "/../" in normalized:
                return None
            return value
        except (ValueError, OSError):
            return None

    # Validate string fields
    if key in ("name", "not_name", "regex", "fuzzy", "mod", "size", "depth",
               "type", "perm"):
        if not isinstance(value, str):
            return None
        return str(value)[:_MAX_TERM_LENGTH]

    # Unknown field type - reject
    return None


def parse_llm_response(raw: str, return_errors: bool = False) -> SearchFilters | tuple[SearchFilters, list[str]]:
    """Parse a raw LLM response string into SearchFilters.

    Handles JSON wrapped in markdown code blocks or surrounding text.
    Returns empty SearchFilters on parse failure.
    """
    errors: list[str] = []
    json_str = _extract_json(raw)
    if json_str is None:
        errors.append("No JSON object found in LLM response.")
        filters = SearchFilters()
        return (filters, errors) if return_errors else filters
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON: {exc}")
        filters = SearchFilters()
        return (filters, errors) if return_errors else filters
    if not isinstance(data, dict):
        errors.append("JSON root must be an object.")
        filters = SearchFilters()
        return (filters, errors) if return_errors else filters
    valid_names = {f.name for f in fields(SearchFilters)}
    kwargs = {}
    for key, value in data.items():
        if key not in valid_names:
            continue
        # Validate and sanitize value
        sanitized = _validate_and_sanitize_value(key, value)
        if sanitized is not None:
            kwargs[key] = sanitized
    filters = SearchFilters(**kwargs)
    return (filters, errors) if return_errors else filters


def _extract_json(raw: str) -> str | None:
    """Extract JSON object from raw text using balanced brace matching.

    Handles nested JSON objects correctly by counting brace depth.
    """
    raw = raw.strip()
    # Try markdown code block first
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if md_match:
        return md_match.group(1).strip()

    # Find first opening brace and match with balanced closing brace
    start = raw.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(raw[start:], start):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]

    return None
