"""Filter dataclass and matching logic for file search."""

from __future__ import annotations

import fnmatch
import os
import plistlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

# Maximum file size for content scanning (10 MB)
MAX_CONTENT_SCAN_BYTES = 10 * 1024 * 1024
CONTENT_SCAN_CHUNK_BYTES = 64 * 1024
MACOS_TAG_XATTR = "com.apple.metadata:_kMDItemUserTags"
SHEBANG_PROBE_BYTES = 512
LICENSE_SCAN_BYTES = 128 * 1024
CODE_METRICS_SCAN_BYTES = 512 * 1024
SIMILARITY_SCAN_BYTES = 512 * 1024
DEFAULT_SIMILARITY_THRESHOLD = 0.55
SIMILARITY_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
COMPLEXITY_TOKEN_PATTERN = re.compile(
    r"\b(if|elif|for|while|except|case|catch|and|or)\b|&&|\|\|",
    re.IGNORECASE,
)

_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".xml": "xml",
}

_LANGUAGE_ALIASES = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "ts": "typescript",
    "bash": "shell",
    "sh": "shell",
    "zsh": "shell",
    "c#": "csharp",
    "cs": "csharp",
    "objc": "objective-c",
    "objectivec": "objective-c",
    "md": "markdown",
}

_LICENSE_ALIASES = {
    "mit": "mit",
    "apache": "apache-2.0",
    "apache2": "apache-2.0",
    "apache-2.0": "apache-2.0",
    "apache 2.0": "apache-2.0",
    "gpl": "gpl-3.0",
    "gplv3": "gpl-3.0",
    "gpl-3.0": "gpl-3.0",
    "gpl3": "gpl-3.0",
    "gplv2": "gpl-2.0",
    "gpl-2.0": "gpl-2.0",
    "gpl2": "gpl-2.0",
    "bsd-3-clause": "bsd-3-clause",
    "bsd3": "bsd-3-clause",
    "bsd-2-clause": "bsd-2-clause",
    "bsd2": "bsd-2-clause",
    "mpl-2.0": "mpl-2.0",
    "mpl2": "mpl-2.0",
    "isc": "isc",
    "unlicense": "unlicense",
}

_SPDX_LICENSE_PATTERN = re.compile(
    r"SPDX-License-Identifier:\s*([A-Za-z0-9\.\-\+]+)",
    re.IGNORECASE,
)


def parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    # Handle both integer and decimal bytes (e.g., "100" or "1.5")
    return int(float(s))


def parse_time_delta(s: str) -> timedelta:
    s = s.strip().lower()
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    for suffix, kwarg in units.items():
        if s.endswith(suffix):
            value = int(s[: -len(suffix)])
            return timedelta(**{kwarg: value})
    return timedelta(days=int(s))


def parse_mod_datetime(s: str, *, upper_bound: bool = False) -> datetime:
    """Parse absolute date/datetime filter values into UTC datetime.

    Supported formats:
    - YYYY-MM-DD
    - YYYY-MM-DDTHH:MM[:SS][Z|+HH:MM]
    - YYYY-MM-DD HH:MM[:SS][Z|+HH:MM]
    """
    raw = s.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)

    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    # Date-only values represent whole-day boundaries.
    if len(s.strip()) == 10:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        if upper_bound:
            dt += timedelta(days=1)
    return dt


def _parse_constraint(s: str) -> tuple[str, str]:
    """Parse '>7d' into ('>', '7d') or '<1MB' into ('<', '1MB')."""
    if s.startswith(">"):
        return ">", s[1:]
    if s.startswith("<"):
        return "<", s[1:]
    return "=", s


def _file_contains_all_terms(filepath: Path, terms: list[str]) -> bool:
    """Scan file in chunks and return True when all terms are found."""
    pending_terms = set(terms)
    max_term_len = max(len(term) for term in pending_terms)
    overlap = max(0, max_term_len - 1)
    tail = ""

    with filepath.open("rb") as handle:
        while True:
            chunk = handle.read(CONTENT_SCAN_CHUNK_BYTES)
            if not chunk:
                break

            text = tail + chunk.decode("utf-8", errors="ignore")
            matched = {term for term in pending_terms if term in text}
            pending_terms -= matched
            if not pending_terms:
                return True

            tail = text[-overlap:] if overlap else ""

    return False


def _normalize_tag_name(tag: str) -> str:
    # Finder tags may include a color suffix like "ProjectX\n6".
    normalized = tag.split("\n", 1)[0].strip()
    return normalized.casefold()


def _decode_macos_tags(payload: bytes) -> set[str]:
    try:
        decoded = plistlib.loads(payload)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        return set()
    if not isinstance(decoded, list):
        return set()
    tags: set[str] = set()
    for item in decoded:
        if not isinstance(item, str):
            continue
        normalized = _normalize_tag_name(item)
        if normalized:
            tags.add(normalized)
    return tags


def _read_user_tags_xattr(filepath: Path, *, follow_symlinks: bool) -> set[str]:
    if not hasattr(os, "getxattr"):
        return set()
    try:
        raw = os.getxattr(
            str(filepath),
            MACOS_TAG_XATTR,
            follow_symlinks=follow_symlinks,
        )
    except OSError:
        return set()
    if not isinstance(raw, bytes):
        return set()
    return _decode_macos_tags(raw)


def _normalize_language_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        return ""
    return _LANGUAGE_ALIASES.get(normalized, normalized)


def _normalize_license_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        return ""
    return _LICENSE_ALIASES.get(normalized, normalized)


def _detect_language_from_shebang(filepath: Path) -> str | None:
    try:
        with filepath.open("rb") as handle:
            first_line = handle.read(SHEBANG_PROBE_BYTES).splitlines()[0:1]
    except (OSError, IndexError):
        return None
    if not first_line:
        return None
    shebang = first_line[0].decode("utf-8", errors="ignore").casefold()
    if not shebang.startswith("#!"):
        return None
    if "python" in shebang:
        return "python"
    if "node" in shebang or "deno" in shebang:
        return "javascript"
    if "bash" in shebang or "sh" in shebang or "zsh" in shebang:
        return "shell"
    if "ruby" in shebang:
        return "ruby"
    if "perl" in shebang:
        return "perl"
    if "php" in shebang:
        return "php"
    return None


def _detect_language(filepath: Path) -> str | None:
    language_by_ext = _LANGUAGE_BY_EXTENSION.get(filepath.suffix.casefold())
    if language_by_ext is not None:
        return language_by_ext
    return _detect_language_from_shebang(filepath)


def _read_text_sample(filepath: Path, *, max_bytes: int) -> str | None:
    try:
        with filepath.open("rb") as handle:
            payload = handle.read(max_bytes)
    except OSError:
        return None
    if not payload:
        return None
    return payload.decode("utf-8", errors="ignore")


def _detect_license(filepath: Path) -> str | None:
    sample = _read_text_sample(filepath, max_bytes=LICENSE_SCAN_BYTES)
    if not sample:
        return None
    spdx_match = _SPDX_LICENSE_PATTERN.search(sample)
    if spdx_match:
        return _normalize_license_name(spdx_match.group(1))

    lowered = sample.casefold()
    if "permission is hereby granted, free of charge" in lowered:
        return "mit"
    if "apache license" in lowered and "version 2.0" in lowered:
        return "apache-2.0"
    if "gnu general public license" in lowered and "version 3" in lowered:
        return "gpl-3.0"
    if "gnu general public license" in lowered and "version 2" in lowered:
        return "gpl-2.0"
    if "mozilla public license" in lowered and "2.0" in lowered:
        return "mpl-2.0"
    if "the unlicense" in lowered:
        return "unlicense"
    if (
        "permission to use, copy, modify, and/or distribute this software for any purpose"
        in lowered
    ):
        return "isc"
    if "redistribution and use in source and binary forms" in lowered:
        if "neither the name" in lowered:
            return "bsd-3-clause"
        return "bsd-2-clause"
    return None


def _parse_int_constraint(value: str) -> tuple[str, int] | None:
    op, raw = _parse_constraint(value)
    try:
        parsed = int(raw)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return (op, parsed)


def _matches_numeric_constraint(value: int, constraint: str) -> bool:
    parsed = _parse_int_constraint(constraint)
    if parsed is None:
        return True
    op, expected = parsed
    if op == ">":
        return value > expected
    if op == "<":
        return value < expected
    return value == expected


def _estimate_code_complexity(text: str) -> int:
    hits = COMPLEXITY_TOKEN_PATTERN.findall(text)
    # Baseline complexity is 1 for linear flow.
    return 1 + len(hits)


def _count_lines_of_code(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _tokenize_for_similarity(text: str) -> set[str]:
    tokens = {match.group(0).casefold() for match in SIMILARITY_TOKEN_PATTERN.finditer(text)}
    if tokens:
        return tokens
    # Fallback to line chunks for non-code/text-light files.
    return {line.strip().casefold() for line in text.splitlines() if line.strip()}


def _compute_similarity_score(left: str, right: str) -> float:
    left_tokens = _tokenize_for_similarity(left)
    right_tokens = _tokenize_for_similarity(right)
    if left_tokens and right_tokens:
        union = left_tokens | right_tokens
        if union:
            overlap = left_tokens & right_tokens
            return len(overlap) / len(union)
    # Fallback to sequence similarity when tokenization is sparse.
    return SequenceMatcher(None, left, right).ratio()


@dataclass
class SearchFilters:
    """Search filters extracted from natural language queries.

    Implemented filters:
    - ext, not_ext: File extension filtering
    - name, not_name: Glob pattern matching on filename
    - path, not_path: Path substring matching
    - regex: Regex matching on filename
    - fuzzy: Fuzzy subsequence matching on filename
    - mod: Modification time constraints
    - mod_after, mod_before: Absolute modification date range constraints
    - size: File size constraints
    - has: Content matching (all terms must be present)
    - similar: Similarity matching against a reference file
    - similarity_threshold: Similarity cutoff in [0.0, 1.0]
    - loc: Lines-of-code constraint
    - complexity: Approximate complexity constraint
    - lang, not_lang: Programming language filtering
    - license, not_license: License identifier filtering
    - tag: macOS Finder tags attached to files (all tags must be present)
    - type: File type (file, dir, link)
    - depth: Directory depth constraints
    - perm: Permission checks (r, w, x)

    Future/unimplemented filters (removed to avoid confusion):
    - cre: Creation time (not portable across filesystems)
    - acc: Access time (often disabled for performance)
    - newer: Newer than reference file
    - lines: Line count
    - cat: File category detection
    - owner: File owner matching
    """
    ext: list[str] | None = None
    not_ext: list[str] | None = None
    name: str | None = None
    not_name: str | None = None
    path: str | None = None
    not_path: str | None = None
    regex: str | None = None
    fuzzy: str | None = None
    mod: str | None = None
    mod_after: str | None = None
    mod_before: str | None = None
    size: str | None = None
    has: list[str] | None = None
    similar: str | None = None
    similarity_threshold: float | None = None
    loc: str | None = None
    complexity: str | None = None
    lang: list[str] | None = None
    not_lang: list[str] | None = None
    license: list[str] | None = None
    not_license: list[str] | None = None
    tag: list[str] | None = None
    type: str | None = None
    depth: str | None = None
    perm: str | None = None
    _compiled_regex: re.Pattern[str] | None = field(default=None, init=False, repr=False)
    _ext_lower: frozenset[str] | None = field(default=None, init=False, repr=False)
    _not_ext_lower: frozenset[str] | None = field(default=None, init=False, repr=False)
    _lang_normalized: frozenset[str] | None = field(default=None, init=False, repr=False)
    _not_lang_normalized: frozenset[str] | None = field(default=None, init=False, repr=False)
    _license_normalized: frozenset[str] | None = field(default=None, init=False, repr=False)
    _not_license_normalized: frozenset[str] | None = field(default=None, init=False, repr=False)
    _similar_text_cache: str | None = field(default=None, init=False, repr=False)
    _similar_reference_path_cache: Path | None = field(default=None, init=False, repr=False)
    _similar_resolved_failure: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Pre-compile regex and normalize extension sets for performance and safety."""
        # Pre-compile regex pattern with error handling to prevent ReDoS
        if self.regex:
            try:
                self._compiled_regex = re.compile(self.regex)
            except re.error:
                # Invalid regex from LLM - treat as no regex filter
                self._compiled_regex = None
                self.regex = None

        # Pre-compute lowercase extension sets for performance
        if self.ext:
            self._ext_lower = frozenset(e.lower() for e in self.ext)
        if self.not_ext:
            self._not_ext_lower = frozenset(e.lower() for e in self.not_ext)
        if self.lang:
            self._lang_normalized = frozenset(
                normalized for value in self.lang if (normalized := _normalize_language_name(value))
            )
        if self.not_lang:
            self._not_lang_normalized = frozenset(
                normalized
                for value in self.not_lang
                if (normalized := _normalize_language_name(value))
            )
        if self.license:
            self._license_normalized = frozenset(
                normalized for value in self.license if (normalized := _normalize_license_name(value))
            )
        if self.not_license:
            self._not_license_normalized = frozenset(
                normalized
                for value in self.not_license
                if (normalized := _normalize_license_name(value))
            )

    def _resolve_similar_reference_path(self, *, root: Path) -> Path | None:
        if self.similar is None:
            return None
        if self._similar_resolved_failure:
            return None
        if self._similar_reference_path_cache is not None:
            return self._similar_reference_path_cache

        requested = self.similar.strip()
        if not requested:
            self._similar_resolved_failure = True
            return None

        try:
            resolved_root = root.resolve(strict=False)
        except OSError:
            self._similar_resolved_failure = True
            return None

        def is_within_root(path: Path) -> bool:
            return path == resolved_root or resolved_root in path.parents

        candidate = Path(requested)
        if candidate.is_absolute():
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                self._similar_resolved_failure = True
                return None
            if not is_within_root(resolved):
                self._similar_resolved_failure = True
                return None
            self._similar_reference_path_cache = resolved
            return resolved

        root_candidate = (resolved_root / candidate).resolve(strict=False)
        if not is_within_root(root_candidate):
            self._similar_resolved_failure = True
            return None
        if root_candidate.is_file():
            self._similar_reference_path_cache = root_candidate
            return root_candidate

        target_name = candidate.name
        try:
            for path in resolved_root.rglob(target_name):
                if path.is_file():
                    resolved_path = path.resolve(strict=False)
                    if is_within_root(resolved_path):
                        self._similar_reference_path_cache = resolved_path
                        return self._similar_reference_path_cache
        except OSError:
            self._similar_resolved_failure = True
            return None

        self._similar_resolved_failure = True
        return None

    def _resolve_similar_reference_text(self, *, root: Path) -> str | None:
        if self.similar is None:
            return None
        if self._similar_text_cache is not None:
            return self._similar_text_cache
        reference_path = self._resolve_similar_reference_path(root=root)
        if reference_path is None:
            return None
        text = _read_text_sample(reference_path, max_bytes=SIMILARITY_SCAN_BYTES)
        if text is None:
            self._similar_resolved_failure = True
            return None
        self._similar_text_cache = text
        return text

    def matches_name(self, filename: str) -> bool:
        # Use pre-computed extension sets for better performance
        if self._ext_lower is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() not in self._ext_lower:
                return False
        if self._not_ext_lower is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() in self._not_ext_lower:
                return False
        if self.name and not fnmatch.fnmatch(filename, self.name):
            return False
        if self.not_name and fnmatch.fnmatch(filename, self.not_name):
            return False
        # Use pre-compiled regex to prevent ReDoS and handle invalid patterns
        if self._compiled_regex is not None:
            if not self._compiled_regex.search(filename):
                return False
        if self.fuzzy:
            if not _fuzzy_match(self.fuzzy.lower(), filename.lower()):
                return False
        return True

    def matches_path(self, filepath: str) -> bool:
        if self.path and self.path not in filepath:
            return False
        if self.not_path and self.not_path in filepath:
            return False
        return True

    def matches_type(self, is_file: bool, is_dir: bool, is_link: bool) -> bool:
        if self.type is None:
            return True
        if self.type == "file":
            return is_file
        if self.type == "dir":
            return is_dir
        if self.type == "link":
            return is_link
        return True

    def matches_depth(self, depth: int) -> bool:
        if self.depth is None:
            return True
        op, val = _parse_constraint(self.depth)
        limit = int(val)
        if op == "<":
            return depth < limit
        if op == ">":
            return depth > limit
        return depth == limit

    def matches_stat(self, stat: os.stat_result) -> bool:
        mtime: datetime | None = None

        def get_mtime() -> datetime:
            nonlocal mtime
            if mtime is None:
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            return mtime

        if self.size:
            op, val = _parse_constraint(self.size)
            try:
                size_bytes = parse_size(val)
            except (ValueError, OverflowError):
                size_bytes = None
            if size_bytes is not None:
                if op == ">" and stat.st_size <= size_bytes:
                    return False
                if op == "<" and stat.st_size >= size_bytes:
                    return False
        if self.mod:
            op, val = _parse_constraint(self.mod)
            try:
                delta = parse_time_delta(val)
            except (ValueError, OverflowError):
                delta = None
            if delta is not None:
                cutoff = datetime.now(UTC) - delta
                if op == ">" and get_mtime() < cutoff:
                    return False
                if op == "<" and get_mtime() > cutoff:
                    return False
        if self.mod_after:
            try:
                lower_bound = parse_mod_datetime(self.mod_after, upper_bound=False)
            except (ValueError, OverflowError):
                lower_bound = None
            if lower_bound is not None and get_mtime() < lower_bound:
                return False
        if self.mod_before:
            try:
                upper_bound = parse_mod_datetime(self.mod_before, upper_bound=True)
            except (ValueError, OverflowError):
                upper_bound = None
            if upper_bound is not None and get_mtime() >= upper_bound:
                return False
        if self.perm:
            mode = stat.st_mode
            if "x" in self.perm and not (mode & 0o111):
                return False
            if "w" in self.perm and not (mode & 0o222):
                return False
            if "r" in self.perm and not (mode & 0o444):
                return False
        return True

    def matches_content(self, filepath: Path, *, follow_symlinks: bool = False) -> bool:
        if not self.has:
            return True
        try:
            # Skip symlinks by default to prevent reading files outside search root.
            if filepath.is_symlink() and not follow_symlinks:
                return False
            # Check file size to prevent OOM on large files
            file_size = filepath.stat().st_size
            if file_size > MAX_CONTENT_SCAN_BYTES:
                return False
            return _file_contains_all_terms(filepath, self.has)
        except (OSError, UnicodeDecodeError):
            return False

    def matches_similarity(
        self,
        filepath: Path,
        *,
        root: Path,
        follow_symlinks: bool = False,
    ) -> bool:
        if self.similar is None:
            return True
        reference_text = self._resolve_similar_reference_text(root=root)
        reference_path = self._resolve_similar_reference_path(root=root)
        if reference_text is None or reference_path is None:
            return False
        try:
            candidate_path = filepath.resolve(strict=False)
        except OSError:
            return False
        if candidate_path == reference_path:
            return False
        try:
            if filepath.is_symlink() and not follow_symlinks:
                return False
        except OSError:
            return False
        candidate_text = _read_text_sample(filepath, max_bytes=SIMILARITY_SCAN_BYTES)
        if candidate_text is None:
            return False
        score = _compute_similarity_score(reference_text, candidate_text)
        threshold = (
            self.similarity_threshold
            if self.similarity_threshold is not None
            else DEFAULT_SIMILARITY_THRESHOLD
        )
        return score >= threshold

    def matches_tags(self, filepath: Path, *, follow_symlinks: bool = False) -> bool:
        if not self.tag:
            return True
        requested = {_normalize_tag_name(tag) for tag in self.tag if tag.strip()}
        if not requested:
            return True
        present_tags = _read_user_tags_xattr(
            filepath,
            follow_symlinks=follow_symlinks,
        )
        if not present_tags:
            return False
        return requested.issubset(present_tags)

    def matches_code_metrics(self, filepath: Path, *, follow_symlinks: bool = False) -> bool:
        if self.loc is None and self.complexity is None:
            return True
        try:
            if filepath.is_symlink() and not follow_symlinks:
                return False
            stat = filepath.stat()
        except OSError:
            return False
        if stat.st_size > CODE_METRICS_SCAN_BYTES:
            return False
        text = _read_text_sample(filepath, max_bytes=CODE_METRICS_SCAN_BYTES)
        if text is None:
            return False
        if self.loc is not None:
            loc_value = _count_lines_of_code(text)
            if not _matches_numeric_constraint(loc_value, self.loc):
                return False
        if self.complexity is not None:
            complexity_value = _estimate_code_complexity(text)
            if not _matches_numeric_constraint(complexity_value, self.complexity):
                return False
        return True

    def matches_language(self, filepath: Path, *, follow_symlinks: bool = False) -> bool:
        if self._lang_normalized is None and self._not_lang_normalized is None:
            return True
        try:
            if filepath.is_symlink() and not follow_symlinks:
                return False if self._lang_normalized is not None else True
        except OSError:
            return False if self._lang_normalized is not None else True

        detected = _detect_language(filepath)
        if self._lang_normalized is not None:
            if detected is None or detected not in self._lang_normalized:
                return False
        if self._not_lang_normalized is not None and detected in self._not_lang_normalized:
            return False
        return True

    def matches_license(self, filepath: Path, *, follow_symlinks: bool = False) -> bool:
        if self._license_normalized is None and self._not_license_normalized is None:
            return True
        try:
            if filepath.is_symlink() and not follow_symlinks:
                return False if self._license_normalized is not None else True
        except OSError:
            return False if self._license_normalized is not None else True

        detected = _detect_license(filepath)
        if self._license_normalized is not None:
            if detected is None or detected not in self._license_normalized:
                return False
        if self._not_license_normalized is not None and detected in self._not_license_normalized:
            return False
        return True


def _fuzzy_match(pattern: str, text: str) -> bool:
    """Simple subsequence fuzzy match."""
    p_idx = 0
    for char in text:
        if p_idx < len(pattern) and char == pattern[p_idx]:
            p_idx += 1
    return p_idx == len(pattern)
