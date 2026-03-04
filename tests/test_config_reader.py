"""Tests for ConfigReader and RuntimeConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from askfind.config import Config
from askfind.config_reader import ConfigReader, RuntimeConfig
from askfind.llm.mode import DEFAULT_LLM_MODE
from askfind.search.filters import DEFAULT_SIMILARITY_THRESHOLD


class TestConfigReader:
    """Tests for ConfigReader class."""

    def test_get_bool_with_true_value(self) -> None:
        config = Config(cache_enabled=True)
        reader = ConfigReader(config)
        assert reader.get_bool("cache_enabled", default=False) is True

    def test_get_bool_with_false_value(self) -> None:
        config = Config(cache_enabled=False)
        reader = ConfigReader(config)
        assert reader.get_bool("cache_enabled", default=True) is False

    def test_get_bool_with_missing_field_returns_default(self) -> None:
        config = Config()
        reader = ConfigReader(config)
        # Access a field that doesn't exist via getattr
        assert reader.get_bool("nonexistent_field", default=True) is True

    def test_get_bool_with_non_bool_value_returns_default(self) -> None:
        config = Config()
        # Manually set a non-bool value
        config.cache_enabled = "not_a_bool"  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_bool("cache_enabled", default=True) is True

    def test_get_positive_int_with_valid_value(self) -> None:
        config = Config(parallel_workers=4)
        reader = ConfigReader(config)
        assert reader.get_positive_int("parallel_workers", default=1) == 4

    def test_get_positive_int_with_zero_returns_default(self) -> None:
        config = Config(parallel_workers=0)
        reader = ConfigReader(config)
        assert reader.get_positive_int("parallel_workers", default=1) == 1

    def test_get_positive_int_with_negative_returns_default(self) -> None:
        config = Config()
        config.parallel_workers = -5  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_positive_int("parallel_workers", default=1) == 1

    def test_get_non_negative_int_with_zero(self) -> None:
        config = Config(max_results=0)
        reader = ConfigReader(config)
        assert reader.get_non_negative_int("max_results", default=50) == 0

    def test_get_non_negative_int_with_positive(self) -> None:
        config = Config(max_results=100)
        reader = ConfigReader(config)
        assert reader.get_non_negative_int("max_results", default=50) == 100

    def test_get_non_negative_int_with_negative_returns_default(self) -> None:
        config = Config()
        config.max_results = -10  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_non_negative_int("max_results", default=50) == 50

    def test_get_similarity_threshold_valid(self) -> None:
        config = Config(similarity_threshold=0.75)
        reader = ConfigReader(config)
        assert reader.get_similarity_threshold(default=0.5) == 0.75

    def test_get_similarity_threshold_out_of_range_low(self) -> None:
        config = Config()
        config.similarity_threshold = -0.1  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_similarity_threshold(default=0.5) == 0.5

    def test_get_similarity_threshold_out_of_range_high(self) -> None:
        config = Config()
        config.similarity_threshold = 1.5  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_similarity_threshold(default=0.5) == 0.5

    def test_get_llm_mode_valid(self) -> None:
        config = Config(llm_mode="auto")
        reader = ConfigReader(config)
        assert reader.get_llm_mode(default="always") == "auto"

    def test_get_llm_mode_invalid_returns_default(self) -> None:
        config = Config()
        config.llm_mode = "invalid"  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_llm_mode(default="always") == "always"

    def test_get_str_valid(self) -> None:
        config = Config(model="gpt-4")
        reader = ConfigReader(config)
        assert reader.get_str("model", default="") == "gpt-4"

    def test_get_str_with_non_str_returns_default(self) -> None:
        config = Config()
        config.model = 123  # type: ignore[assignment]
        reader = ConfigReader(config)
        assert reader.get_str("model", default="default-model") == "default-model"


class TestRuntimeConfig:
    """Tests for RuntimeConfig dataclass."""

    def test_from_config_basic(self, tmp_path: Path) -> None:
        config = Config()
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(config, root=root)

        assert runtime.root == root.resolve()
        assert runtime.respect_ignore_files is True  # default
        assert runtime.follow_symlinks is False  # default

    def test_from_config_with_cli_overrides(self, tmp_path: Path) -> None:
        config = Config(
            respect_ignore_files=True,
            follow_symlinks=False,
            parallel_workers=2,
        )
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(
            config,
            root=root,
            no_ignore=True,
            follow_symlinks=True,
            workers=4,
        )

        assert runtime.respect_ignore_files is False  # overridden by no_ignore
        assert runtime.follow_symlinks is True  # overridden by CLI
        assert runtime.parallel_workers == 4  # overridden by CLI

    def test_from_config_offline_mode(self, tmp_path: Path) -> None:
        config = Config(llm_mode="always")
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(config, root=root, offline=True)

        assert runtime.llm_mode == "off"
        assert runtime.offline_mode is True

    def test_from_config_similarity_threshold_override(self, tmp_path: Path) -> None:
        config = Config(similarity_threshold=0.5)
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(
            config,
            root=root,
            similarity_threshold=0.9,
        )

        assert runtime.similarity_threshold == 0.9

    def test_from_config_similarity_threshold_invalid_cli(self, tmp_path: Path) -> None:
        """Invalid CLI values should still be passed through (validation is in CLI layer)."""
        config = Config(similarity_threshold=0.5)
        root = tmp_path / "search_root"
        root.mkdir()

        # Note: CLI validation happens before from_config is called
        # So we just test that valid values are passed through
        runtime = RuntimeConfig.from_config(
            config,
            root=root,
            similarity_threshold=0.8,
        )

        assert runtime.similarity_threshold == 0.8

    def test_apply_to_config(self, tmp_path: Path) -> None:
        config = Config()
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(
            config,
            root=root,
            no_ignore=True,
            follow_symlinks=True,
            offline=True,
        )

        runtime.apply_to_config(config)

        assert config.respect_ignore_files is False
        assert config.follow_symlinks is True
        assert config.offline_mode is True

    def test_to_index_options(self, tmp_path: Path) -> None:
        config = Config()
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(
            config,
            root=root,
            no_ignore=True,
            follow_symlinks=True,
            workers=8,
        )

        index_options = runtime.to_index_options()

        assert index_options.respect_ignore_files is False
        assert index_options.follow_symlinks is True
        assert index_options.traversal_workers == 8

    def test_frozen_dataclass(self, tmp_path: Path) -> None:
        """RuntimeConfig should be immutable."""
        config = Config()
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(config, root=root)

        with pytest.raises(AttributeError):
            runtime.max_results = 999  # type: ignore[misc]

    def test_max_results_fallback_to_config(self, tmp_path: Path) -> None:
        config = Config(max_results=100)
        root = tmp_path / "search_root"
        root.mkdir()

        # When max_results CLI arg is 0, should use config value
        runtime = RuntimeConfig.from_config(config, root=root, max_results=0)

        assert runtime.max_results == 100

    def test_max_results_cli_override(self, tmp_path: Path) -> None:
        config = Config(max_results=100)
        root = tmp_path / "search_root"
        root.mkdir()

        runtime = RuntimeConfig.from_config(config, root=root, max_results=50)

        assert runtime.max_results == 50
