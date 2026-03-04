"""Configuration reader and runtime configuration management.

This module centralizes config value reading with type validation,
eliminating duplicated getattr + validation patterns across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from askfind.config import Config
from askfind.llm.mode import DEFAULT_LLM_MODE, LLMMode, normalize_llm_mode
from askfind.search.filters import DEFAULT_SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from askfind.search.index import IndexOptions


class ConfigReader:
    """Type-safe configuration reader with validation.

    Wraps a Config object and provides validated accessors for all config fields.
    This eliminates the repeated pattern of getattr + type checking throughout the codebase.

    Example:
        reader = ConfigReader(config)
        respect_ignore = reader.get_bool("respect_ignore_files", default=True)
        workers = reader.get_positive_int("parallel_workers", default=1)
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def get_bool(self, key: str, *, default: bool) -> bool:
        """Get a boolean config value with validation."""
        value = getattr(self._config, key, default)
        if isinstance(value, bool):
            return value
        return default

    def get_positive_int(self, key: str, *, default: int) -> int:
        """Get a positive integer config value (>= 1)."""
        value = getattr(self._config, key, default)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            return value
        return default

    def get_non_negative_int(self, key: str, *, default: int) -> int:
        """Get a non-negative integer config value (>= 0)."""
        value = getattr(self._config, key, default)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return default

    def get_similarity_threshold(self, key: str = "similarity_threshold", *, default: float) -> float:
        """Get a similarity threshold value (0.0 to 1.0)."""
        value = getattr(self._config, key, default)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized = float(value)
            if 0.0 <= normalized <= 1.0:
                return normalized
        return default

    def get_llm_mode(self, key: str = "llm_mode", *, default: LLMMode) -> LLMMode:
        """Get and normalize an LLM mode value."""
        value = getattr(self._config, key, default)
        return normalize_llm_mode(value, default=default)

    def get_str(self, key: str, *, default: str) -> str:
        """Get a string config value with validation."""
        value = getattr(self._config, key, default)
        if isinstance(value, str):
            return value
        return default


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable runtime configuration derived from Config + CLI arguments.

    This dataclass captures all the runtime settings needed for search execution,
    combining config file values with CLI overrides. Using a frozen dataclass
    ensures immutability and makes the configuration explicit.

    Attributes:
        root: Resolved search root directory path
        respect_ignore_files: Whether to respect .gitignore/.askfindignore
        follow_symlinks: Whether to follow symbolic links
        exclude_binary_files: Whether to exclude binary files from results
        search_archives: Whether to search inside archive files
        parallel_workers: Number of parallel traversal workers
        max_results: Maximum number of results (0 = unlimited)
        similarity_threshold: Threshold for similarity matching (0.0-1.0)
        cache_enabled: Whether search caching is enabled
        cache_ttl_seconds: Cache time-to-live in seconds
        llm_mode: LLM call policy ("always", "auto", "off")
        offline_mode: Whether to skip all network calls
        model: LLM model identifier
        base_url: LLM API base URL
    """

    root: Path
    respect_ignore_files: bool = True
    follow_symlinks: bool = False
    exclude_binary_files: bool = True
    search_archives: bool = False
    parallel_workers: int = 1
    max_results: int = 50
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    llm_mode: LLMMode = DEFAULT_LLM_MODE
    offline_mode: bool = False
    model: str = ""
    base_url: str = ""

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        root: Path,
        no_ignore: bool = False,
        follow_symlinks: bool = False,
        include_binary: bool = False,
        search_archives: bool = False,
        workers: int = 0,
        max_results: int = 0,
        similarity_threshold: float | None = None,
        no_cache: bool = False,
        llm_mode: LLMMode | None = None,
        offline: bool = False,
        model: str | None = None,
    ) -> RuntimeConfig:
        """Build RuntimeConfig from Config with CLI argument overrides.

        Args:
            config: Base configuration from file
            root: Resolved search root path
            no_ignore: CLI flag to ignore .gitignore rules
            follow_symlinks: CLI flag to follow symlinks
            include_binary: CLI flag to include binary files
            search_archives: CLI flag to search archives
            workers: CLI override for parallel workers (0 = use config)
            max_results: CLI override for max results (0 = use config)
            similarity_threshold: CLI override for similarity threshold
            no_cache: CLI flag to disable cache
            llm_mode: CLI override for LLM mode
            offline: CLI flag for offline mode
            model: CLI override for model

        Returns:
            Fully resolved RuntimeConfig instance
        """
        reader = ConfigReader(config)

        # Compute final values with CLI overrides
        final_respect_ignore = reader.get_bool("respect_ignore_files", default=True) and not no_ignore
        final_follow_symlinks = reader.get_bool("follow_symlinks", default=False) or follow_symlinks
        final_exclude_binary = reader.get_bool("exclude_binary_files", default=True) and not include_binary
        final_search_archives = reader.get_bool("search_archives", default=False) or search_archives
        final_workers = workers if workers > 0 else reader.get_positive_int("parallel_workers", default=1)
        final_max_results = max_results if max_results > 0 else reader.get_non_negative_int("max_results", default=50)
        final_similarity = similarity_threshold if similarity_threshold is not None else reader.get_similarity_threshold(default=DEFAULT_SIMILARITY_THRESHOLD)
        final_cache_enabled = reader.get_bool("cache_enabled", default=True) and not no_cache
        final_cache_ttl = reader.get_positive_int("cache_ttl_seconds", default=300)

        # LLM mode resolution
        config_llm_mode = reader.get_llm_mode(default=DEFAULT_LLM_MODE)
        final_llm_mode = normalize_llm_mode(llm_mode, default=config_llm_mode)
        if offline:
            final_llm_mode = "off"

        final_model = model if model else reader.get_str("model", default="")
        final_base_url = reader.get_str("base_url", default="")

        return cls(
            root=root,
            respect_ignore_files=final_respect_ignore,
            follow_symlinks=final_follow_symlinks,
            exclude_binary_files=final_exclude_binary,
            search_archives=final_search_archives,
            parallel_workers=final_workers,
            max_results=final_max_results,
            similarity_threshold=final_similarity,
            cache_enabled=final_cache_enabled,
            cache_ttl_seconds=final_cache_ttl,
            llm_mode=final_llm_mode,
            offline_mode=offline,
            model=final_model,
            base_url=final_base_url,
        )

    def apply_to_config(self, config: Config) -> None:
        """Apply runtime config values back to a Config object.

        This is used for interactive session setup where the Config object
        needs to be mutated to reflect runtime settings.

        Args:
            config: Config object to mutate
        """
        config.respect_ignore_files = self.respect_ignore_files
        config.follow_symlinks = self.follow_symlinks
        config.exclude_binary_files = self.exclude_binary_files
        config.search_archives = self.search_archives
        config.similarity_threshold = self.similarity_threshold
        config.parallel_workers = self.parallel_workers
        config.cache_enabled = self.cache_enabled
        config.cache_ttl_seconds = self.cache_ttl_seconds
        config.offline_mode = self.offline_mode
        config.llm_mode = self.llm_mode

    def to_index_options(self) -> IndexOptions:
        """Create IndexOptions from this runtime configuration.

        This provides a convenient way to get the IndexOptions needed for
        index building and querying operations.

        Returns:
            IndexOptions instance populated from runtime config
        """
        # Import here to avoid circular dependency
        from askfind.search.index import IndexOptions

        return IndexOptions(
            respect_ignore_files=self.respect_ignore_files,
            follow_symlinks=self.follow_symlinks,
            exclude_binary_files=self.exclude_binary_files,
            search_archives=self.search_archives,
            traversal_workers=self.parallel_workers,
        )
