"""Tests for QueryProcessor and related classes."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from askfind.query_processor import QueryProcessor, QueryProcessorStats, QueryResult
from askfind.search.filters import SearchFilters


class TestQueryResult:
    """Tests for QueryResult dataclass."""

    def test_is_rejected_false_when_no_error(self) -> None:
        result = QueryResult(filters=SearchFilters(name="test"))
        assert result.is_rejected is False

    def test_is_rejected_true_when_error_message(self) -> None:
        result = QueryResult(
            filters=SearchFilters(),
            error_message="Query too broad",
        )
        assert result.is_rejected is True

    def test_defaults(self) -> None:
        result = QueryResult(filters=SearchFilters())
        assert result.used_fallback is False
        assert result.fallback_reason is None
        assert result.error_message is None


class TestQueryProcessorStats:
    """Tests for QueryProcessorStats."""

    def test_record_fallback_increments_count(self) -> None:
        stats = QueryProcessorStats()
        stats.record_fallback("http_error")
        assert stats.llm_fallback_count == 1

    def test_record_fallback_tracks_reasons(self) -> None:
        stats = QueryProcessorStats()
        stats.record_fallback("http_error")
        stats.record_fallback("http_error")
        stats.record_fallback("invalid_json")

        assert stats.llm_fallback_reasons == {
            "http_error": 2,
            "invalid_json": 1,
        }

    def test_record_fallback_normalizes_none_reason(self) -> None:
        stats = QueryProcessorStats()
        stats.record_fallback(None)
        assert stats.llm_fallback_reasons == {"unknown": 1}


class TestQueryProcessor:
    """Tests for QueryProcessor class."""

    def test_offline_mode_forces_off(self) -> None:
        processor = QueryProcessor(llm_mode="always", offline_mode=True)
        assert processor.llm_mode == "off"

    def test_process_with_llm_mode_off_and_broad_query(self) -> None:
        processor = QueryProcessor(llm_mode="off")
        result = processor.process("find files")  # Too broad

        assert result.is_rejected is True
        assert "too broad" in result.error_message.lower()

    def test_process_with_llm_mode_off_and_specific_query(self) -> None:
        processor = QueryProcessor(llm_mode="off")
        result = processor.process("find Python files")

        assert result.is_rejected is False
        assert result.filters.ext == [".py"]

    def test_process_with_llm_mode_always(self) -> None:
        processor = QueryProcessor(llm_mode="always")

        # Mock client that returns valid filters
        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{"name": "test.txt"}'

        result = processor.process("find test.txt", client=mock_client)

        assert result.is_rejected is False
        assert result.filters.name == "test.txt"
        mock_client.extract_filters.assert_called_once_with("find test.txt")

    def test_process_with_llm_returns_empty_filters_falls_back(self) -> None:
        processor = QueryProcessor(llm_mode="always")
        stats = QueryProcessorStats()

        # Mock client that returns empty filters
        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{}'

        result = processor.process(
            "find Python files",  # Has meaningful fallback
            client=mock_client,
            stats=stats,
        )

        assert result.used_fallback is True
        assert result.fallback_reason == "empty_llm_filters"
        assert stats.llm_fallback_count == 1

    def test_process_with_http_error_falls_back(self) -> None:
        processor = QueryProcessor(llm_mode="always")
        stats = QueryProcessorStats()

        # Mock client that raises HTTP error
        mock_client = MagicMock()
        mock_client.extract_filters.side_effect = httpx.HTTPError("Connection failed")

        result = processor.process(
            "find Python files",  # Has meaningful fallback
            client=mock_client,
            stats=stats,
        )

        assert result.used_fallback is True
        assert "http_" in result.fallback_reason  # type: ignore[operator]
        assert stats.llm_fallback_count == 1

    def test_process_with_http_error_no_fallback_raises(self) -> None:
        processor = QueryProcessor(llm_mode="always")

        # Mock client that raises HTTP error
        mock_client = MagicMock()
        mock_client.extract_filters.side_effect = httpx.HTTPError("Connection failed")

        # Query without meaningful fallback should raise
        with pytest.raises(httpx.HTTPError):
            processor.process("find files", client=mock_client)

    def test_process_with_no_client_uses_heuristic_in_auto_mode(self) -> None:
        processor = QueryProcessor(llm_mode="auto")

        result = processor.process(
            "find Python files",  # Has meaningful fallback
            client=None,
        )

        assert result.used_fallback is False
        assert result.fallback_reason is None

    def test_process_with_no_client_no_fallback_rejects(self) -> None:
        processor = QueryProcessor(llm_mode="always")

        result = processor.process(
            "find files",  # Too broad, no fallback
            client=None,
        )

        assert result.is_rejected is True

    def test_auto_mode_simple_query_uses_fallback(self) -> None:
        processor = QueryProcessor(llm_mode="auto")

        # Simple, specific query should use fallback
        result = processor.process("find Python files with name test")

        assert result.used_fallback is False
        assert result.filters.ext == [".py"]

    def test_auto_mode_ambiguous_query_uses_llm(self) -> None:
        processor = QueryProcessor(llm_mode="auto")

        # Ambiguous query should use LLM
        mock_client = MagicMock()
        mock_client.extract_filters.return_value = '{"name": "important"}'

        result = processor.process(
            "find files related to important project",
            client=mock_client,
        )

        assert result.used_fallback is False
        mock_client.extract_filters.assert_called_once()


class TestQueryProcessorErrorMessages:
    """Tests for error message generation."""

    def test_offline_mode_error_message(self) -> None:
        processor = QueryProcessor(llm_mode="off")
        result = processor.process("find files")

        assert "--offline" in result.error_message or "--llm-mode off" in result.error_message

    def test_heuristic_mode_error_message(self) -> None:
        processor = QueryProcessor(llm_mode="auto")
        result = processor.process("find files")  # Too broad for auto mode without LLM

        # Auto mode without LLM client should suggest --llm-mode always
        assert result.error_message is not None
