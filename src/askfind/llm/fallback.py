"""Heuristic query parser used when LLM extraction is unavailable."""

from __future__ import annotations

import re

from askfind.search.filters import SearchFilters

_MEANINGFUL_FILTER_FIELDS = (
    "ext",
    "not_ext",
    "name",
    "not_name",
    "path",
    "not_path",
    "regex",
    "fuzzy",
    "mod",
    "mod_after",
    "mod_before",
    "size",
    "has",
    "similar",
    "loc",
    "complexity",
    "lang",
    "not_lang",
    "license",
    "not_license",
    "tag",
    "depth",
    "perm",
)
_EXTENSION_PATTERN = re.compile(r"(?<!\w)\.([a-z0-9]{1,12})\b")
_HAS_CLAUSE_PATTERN = re.compile(r"\b(?:contain|contains|containing|with|has)\b(?P<tail>.+)", re.IGNORECASE)
_PATH_PATTERN = re.compile(
    r"\b(?:in|under|inside)\s+(?:(?:the|a|an|this|that|these|those|my|your|our)\s+)?([A-Za-z0-9_./-]+)",
    re.IGNORECASE,
)
_NOT_PATH_PATTERN = re.compile(
    r"\b(?:excluding|exclude|without|except|not in)\s+"
    r"(?:(?:the|a|an|this|that|these|those|my|your|our)\s+)?([A-Za-z0-9_./-]+)",
    re.IGNORECASE,
)
_NAME_PATTERN = re.compile(r"\bnamed\s+([A-Za-z0-9*._-]+)", re.IGNORECASE)
_QUOTED_TERM_PATTERN = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_HAS_MARKERS = ("todo", "fixme", "hack", "bug", "xxx", "note")
_SIZE_LITERAL_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:kb|mb|gb|tb|b)?\Z", re.IGNORECASE)
_SIZE_GREATER_PATTERN = re.compile(
    r"\b(?:larger than|bigger than|greater than|more than|over|above)\s+"
    r"(\d+(?:\.\d+)?)\s*(kb|mb|gb|tb|b)?\b",
    re.IGNORECASE,
)
_SIZE_LESS_PATTERN = re.compile(
    r"\b(?:smaller than|less than|under|below)\s+(\d+(?:\.\d+)?)\s*(kb|mb|gb|tb|b)?\b",
    re.IGNORECASE,
)
_MOD_LAST_WINDOW_PATTERN = re.compile(
    r"\b(?:last|past)\s+(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks|month|months)\b",
    re.IGNORECASE,
)
_PATH_STOPWORDS = {
    "a",
    "an",
    "all",
    "any",
    "last",
    "past",
    "the",
    "this",
    "that",
    "these",
    "those",
    "today",
    "yesterday",
    "week",
    "month",
    "day",
    "hour",
    "days",
    "weeks",
    "months",
    "hours",
    "minutes",
    "minute",
    "my",
    "our",
    "your",
}
_PATH_ENTITY_WORDS = {"files", "file", "directories", "directory", "folders", "folder"}
_PATH_GENERIC_SCOPE_WORDS = {"codebase", "project", "repo", "repository", "workspace"}
_LANGUAGE_EXTENSION_HINTS = (
    ("python", (".py",)),
    ("javascript", (".js",)),
    ("typescript", (".ts", ".tsx")),
    ("markdown", (".md",)),
    ("json", (".json",)),
    ("yaml", (".yaml", ".yml")),
    ("yml", (".yml",)),
    ("toml", (".toml",)),
    ("shell", (".sh",)),
    ("bash", (".sh",)),
    ("zsh", (".zsh", ".sh")),
    ("golang", (".go",)),
    ("rust", (".rs",)),
    ("java", (".java",)),
    ("html", (".html", ".htm")),
    ("css", (".css",)),
    ("xml", (".xml",)),
    ("sql", (".sql",)),
)
_GO_LANGUAGE_PATTERN = re.compile(r"\b(?:golang|go\s+(?:files?|code|source)|(?:files?|code|source)\s+in\s+go)\b")


def has_meaningful_filters(filters: SearchFilters) -> bool:
    """Return True when filters include at least one constraint beyond entry type."""
    return any(getattr(filters, field_name) is not None for field_name in _MEANINGFUL_FILTER_FIELDS)


def parse_query_fallback(query: str) -> SearchFilters:
    """Infer a minimal SearchFilters object from plain-text query heuristics."""
    stripped = query.strip()
    if not stripped:
        return SearchFilters()

    lowered = stripped.lower()
    ext = _infer_extensions(lowered)
    has_terms = _infer_has_terms(stripped)
    path = _infer_path(stripped)
    not_path = _infer_not_path(stripped)
    name = _infer_name(stripped)
    size = _infer_size(stripped)
    mod = _infer_mod(stripped)

    entry_type: str | None = None
    if re.search(r"\b(?:directories|directory|folders|folder)\b", lowered):
        entry_type = "dir"
    elif re.search(r"\b(?:symlink|symlinks|link|links)\b", lowered):
        entry_type = "link"
    elif ext or has_terms or path or not_path or name or size or mod:
        entry_type = "file"

    candidate = SearchFilters(
        ext=ext or None,
        has=has_terms or None,
        path=path,
        not_path=not_path,
        name=name,
        size=size,
        mod=mod,
        type=entry_type,
    )
    if not has_meaningful_filters(candidate):
        return SearchFilters()
    return candidate


def _infer_extensions(lowered_query: str) -> list[str]:
    found: list[str] = []

    for raw_ext in _EXTENSION_PATTERN.findall(lowered_query):
        _append_unique(found, f".{raw_ext}")

    for keyword, extensions in _LANGUAGE_EXTENSION_HINTS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered_query):
            for extension in extensions:
                _append_unique(found, extension)

    if _GO_LANGUAGE_PATTERN.search(lowered_query):
        _append_unique(found, ".go")

    return found


def _infer_has_terms(query: str) -> list[str]:
    clause_match = _HAS_CLAUSE_PATTERN.search(query)
    if clause_match is None:
        return []

    tail = clause_match.group("tail")
    terms: list[str] = []

    for quoted_a, quoted_b in _QUOTED_TERM_PATTERN.findall(tail):
        candidate = (quoted_a or quoted_b).strip()
        if candidate:
            _append_unique(terms, candidate[:200])

    if terms:
        return terms

    tail = re.split(r"\b(?:in|under|inside)\b\s+[A-Za-z0-9_./-]+", tail, maxsplit=1, flags=re.IGNORECASE)[0]
    lowered_tail = tail.lower()
    for marker in _HAS_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", lowered_tail):
            _append_unique(terms, marker.upper())
    return terms


def _infer_path(query: str) -> str | None:
    query_without_quotes = _QUOTED_TERM_PATTERN.sub(" ", query)
    lowered = query_without_quotes.lower()

    for match in _PATH_PATTERN.finditer(query_without_quotes):
        # Avoid interpreting "not in <x>" as an inclusion path.
        prefix = lowered[max(0, match.start() - 5) : match.start()]
        if re.search(r"\bnot\s*$", prefix):
            continue
        candidate = _normalize_path_candidate(match.group(1))
        if candidate is not None:
            return candidate
    return None


def _infer_not_path(query: str) -> str | None:
    query_without_quotes = _QUOTED_TERM_PATTERN.sub(" ", query)
    for match in _NOT_PATH_PATTERN.finditer(query_without_quotes):
        candidate = _normalize_path_candidate(match.group(1))
        if candidate is not None:
            return candidate
    return None


def _infer_name(query: str) -> str | None:
    name_match = _NAME_PATTERN.search(query)
    if name_match is None:
        return None
    candidate = name_match.group(1).strip().strip(".,;:)")
    if not candidate:
        return None
    return candidate


def _infer_size(query: str) -> str | None:
    greater = _SIZE_GREATER_PATTERN.search(query)
    if greater is not None:
        return _build_size_constraint(">", greater.group(1), greater.group(2))
    lower = _SIZE_LESS_PATTERN.search(query)
    if lower is not None:
        return _build_size_constraint("<", lower.group(1), lower.group(2))
    return None


def _infer_mod(query: str) -> str | None:
    lowered = query.lower()
    explicit = _MOD_LAST_WINDOW_PATTERN.search(lowered)
    if explicit is not None:
        count = explicit.group(1)
        unit = explicit.group(2)
        if unit.startswith("minute"):
            return f">{count}m"
        if unit.startswith("hour"):
            return f">{count}h"
        if unit.startswith("day"):
            return f">{count}d"
        if unit.startswith("week"):
            return f">{count}w"
        if unit.startswith("month"):
            return f">{int(count) * 30}d"

    if "today" in lowered:
        return ">1d"
    if "this week" in lowered:
        return ">7d"
    if "this month" in lowered:
        return ">30d"
    return None


def _build_size_constraint(operator: str, raw_amount: str, raw_unit: str | None) -> str:
    amount = float(raw_amount)
    if amount.is_integer():
        amount_str = str(int(amount))
    else:
        amount_str = str(amount).rstrip("0").rstrip(".")

    if raw_unit is None or raw_unit.lower() == "b":
        return f"{operator}{amount_str}"
    return f"{operator}{amount_str}{raw_unit.upper()}"


def _normalize_path_candidate(raw_candidate: str) -> str | None:
    candidate = raw_candidate.strip().strip(".,;:)")
    if candidate in {"", ".", "./"}:
        return None
    if candidate.startswith(("/", "~")):
        return None
    if any(part == ".." for part in candidate.split("/")):
        return None

    lowered = candidate.lower()
    if lowered in _PATH_STOPWORDS:
        return None
    if lowered in _PATH_ENTITY_WORDS:
        return None
    if lowered in _PATH_GENERIC_SCOPE_WORDS:
        return None
    if _SIZE_LITERAL_PATTERN.fullmatch(candidate):
        return None
    return candidate


def _append_unique(values: list[str], candidate: str) -> None:
    if candidate not in values:
        values.append(candidate)
