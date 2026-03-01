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
_PATH_PATTERN = re.compile(r"\b(?:in|under|inside)\s+([A-Za-z0-9_./-]+)", re.IGNORECASE)
_NAME_PATTERN = re.compile(r"\bnamed\s+([A-Za-z0-9*._-]+)", re.IGNORECASE)
_QUOTED_TERM_PATTERN = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_HAS_MARKERS = ("todo", "fixme", "hack", "bug", "xxx", "note")
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
    ("go", (".go",)),
    ("rust", (".rs",)),
    ("java", (".java",)),
    ("html", (".html", ".htm")),
    ("css", (".css",)),
    ("xml", (".xml",)),
    ("sql", (".sql",)),
)


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
    name = _infer_name(stripped)

    entry_type: str | None = None
    if re.search(r"\b(?:directories|directory|folders|folder)\b", lowered):
        entry_type = "dir"
    elif re.search(r"\b(?:symlink|symlinks|link|links)\b", lowered):
        entry_type = "link"
    elif ext or has_terms or path or name:
        entry_type = "file"

    candidate = SearchFilters(
        ext=ext or None,
        has=has_terms or None,
        path=path,
        name=name,
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

    return found


def _infer_has_terms(query: str) -> list[str]:
    clause_match = _HAS_CLAUSE_PATTERN.search(query)
    if clause_match is None:
        return []

    tail = clause_match.group("tail")
    tail = re.split(r"\b(?:in|under|inside)\b\s+[A-Za-z0-9_./-]+", tail, maxsplit=1, flags=re.IGNORECASE)[0]
    terms: list[str] = []

    for quoted_a, quoted_b in _QUOTED_TERM_PATTERN.findall(tail):
        candidate = (quoted_a or quoted_b).strip()
        if candidate:
            _append_unique(terms, candidate[:200])

    if terms:
        return terms

    lowered_tail = tail.lower()
    for marker in _HAS_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", lowered_tail):
            _append_unique(terms, marker.upper())
    return terms


def _infer_path(query: str) -> str | None:
    path_match = _PATH_PATTERN.search(query)
    if path_match is None:
        return None

    candidate = path_match.group(1).strip().strip(".,;:)")
    if candidate in {"", ".", "./"}:
        return None
    if candidate.startswith(("/", "~")):
        return None
    if any(part == ".." for part in candidate.split("/")):
        return None
    if candidate.lower() in {"files", "file", "directories", "directory", "folders", "folder"}:
        return None
    return candidate


def _infer_name(query: str) -> str | None:
    name_match = _NAME_PATTERN.search(query)
    if name_match is None:
        return None
    candidate = name_match.group(1).strip().strip(".,;:)")
    if not candidate:
        return None
    return candidate


def _append_unique(values: list[str], candidate: str) -> None:
    if candidate not in values:
        values.append(candidate)
