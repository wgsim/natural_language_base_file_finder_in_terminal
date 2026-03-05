"""Parse LLM responses into SearchFilters."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeAlias

from askfind.search.filters import SearchFilters, parse_mod_datetime, parse_size, parse_time_delta

# Type aliases for JSON values from LLM responses
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list['JSONValue'] | dict[str, 'JSONValue']
JSONDict: TypeAlias = dict[str, JSONValue]

_LIST_FIELDS = {"ext", "not_ext", "has", "tag", "lang", "not_lang", "license", "not_license"}
_MAX_LIST_LENGTH = 20  # Maximum items in list fields
_MAX_TERM_LENGTH = 200  # Maximum length of individual terms
_VALID_TYPE_VALUES = {"file", "dir", "link"}
_VALID_PERM_VALUES = {"r", "w", "x"}
_MAX_DEPTH = 1024
_MAX_SIZE_FILTER_BYTES = 1024**5  # 1 PB
_MAX_MOD_DELTA = timedelta(days=36500)  # ~100 years
_MIN_MOD_YEAR = 1970
_MAX_FUTURE_YEARS = 10
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_METRIC_LIMIT = 1_000_000


def _split_constraint(value: str) -> tuple[str, str]:
    if value.startswith((">", "<")):
        return value[0], value[1:]
    return "", value


def _validate_depth_value(value: str) -> str | None:
    op, raw = _split_constraint(value.strip())
    if not raw:
        return None
    try:
        depth = int(raw)
    except ValueError:
        return None
    if depth < 0 or depth > _MAX_DEPTH:
        return None
    return f"{op}{depth}" if op else str(depth)


def _validate_metric_constraint_value(value: str) -> str | None:
    op, raw = _split_constraint(value.strip())
    if not raw:
        return None
    try:
        metric = int(raw)
    except ValueError:
        return None
    if metric < 0 or metric > _MAX_METRIC_LIMIT:
        return None
    return f"{op}{metric}" if op else str(metric)


def _validate_size_value(value: str) -> str | None:
    op, raw = _split_constraint(value.strip().upper())
    if not raw:
        return None
    try:
        size = parse_size(raw)
    except (ValueError, OverflowError):
        return None
    if size < 0 or size > _MAX_SIZE_FILTER_BYTES:
        return None
    return f"{op}{raw}" if op else raw


def _validate_mod_value(value: str) -> str | None:
    op, raw = _split_constraint(value.strip().lower())
    if not raw:
        return None
    try:
        delta = parse_time_delta(raw)
    except (ValueError, OverflowError):
        return None
    if delta <= timedelta(0) or delta > _MAX_MOD_DELTA:
        return None
    return f"{op}{raw}" if op else raw


def _validate_mod_absolute_value(value: str) -> str | None:
    raw = value.strip()[:_MAX_TERM_LENGTH]
    if not raw:
        return None
    try:
        parsed = parse_mod_datetime(raw, upper_bound=False)
    except (ValueError, OverflowError):
        return None

    max_year = datetime.now(UTC).year + _MAX_FUTURE_YEARS
    if parsed.year < _MIN_MOD_YEAR or parsed.year > max_year:
        return None

    if _DATE_ONLY_PATTERN.match(raw):
        return parsed.date().isoformat()
    return parsed.isoformat(timespec="seconds")


def _sanitize_relative_path_reference(value: JSONValue) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()[:_MAX_TERM_LENGTH]
    try:
        path = Path(normalized)
    except (ValueError, OSError):
        return None
    if path.is_absolute() or normalized.startswith("~") or "\x00" in normalized:
        return None
    if any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


# Validated value types that can be assigned to SearchFilters fields
ValidatedValue: TypeAlias = (
    str | list[str]  # Most fields are string or list of strings
)


def _validate_and_sanitize_value(key: str, value: JSONValue) -> ValidatedValue | None:
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
        value = [str(v).strip()[:_MAX_TERM_LENGTH] for v in value if v]
        value = [v for v in value if v]
        if not value:
            return None
        return value

    # Sanitize path fields to prevent directory traversal
    if key in ("path", "not_path", "similar"):
        return _sanitize_relative_path_reference(value)

    # Validate string fields
    if key in ("name", "not_name", "regex", "fuzzy"):
        if not isinstance(value, str):
            return None
        return str(value).strip()[:_MAX_TERM_LENGTH]

    if key == "type":
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if normalized not in _VALID_TYPE_VALUES:
            return None
        return normalized

    if key == "perm":
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if not normalized or any(ch not in _VALID_PERM_VALUES for ch in normalized):
            return None
        # Preserve canonical order and de-duplicate
        return "".join(ch for ch in "rwx" if ch in normalized)

    if key == "depth":
        if not isinstance(value, str):
            return None
        return _validate_depth_value(value)

    if key in {"loc", "complexity"}:
        if not isinstance(value, str):
            return None
        return _validate_metric_constraint_value(value)

    if key == "size":
        if not isinstance(value, str):
            return None
        return _validate_size_value(value)

    if key == "mod":
        if not isinstance(value, str):
            return None
        return _validate_mod_value(value)

    if key in {"mod_after", "mod_before"}:
        if not isinstance(value, str):
            return None
        return _validate_mod_absolute_value(value)

    # Unknown field type - reject
    return None


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
        # Validate and sanitize value
        sanitized = _validate_and_sanitize_value(key, value)
        if sanitized is not None:
            kwargs[key] = sanitized
    return SearchFilters(**kwargs)


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
