"""Query processing with LLM and fallback handling.

This module provides a unified interface for processing natural language queries,
handling LLM calls with fallback to heuristic parsing when the LLM is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

from askfind.llm.fallback import has_meaningful_filters, parse_query_fallback
from askfind.llm.mode import DEFAULT_LLM_MODE, LLMMode, decide_llm_usage
from askfind.llm.parser import parse_llm_response
from askfind.logging_config import get_logger
from askfind.search.filters import SearchFilters

if TYPE_CHECKING:
    from askfind.llm.client import LLMClient

logger = get_logger(__name__)


@dataclass
class QueryResult:
    """Result of processing a natural language query.

    Attributes:
        filters: The search filters extracted from the query
        used_fallback: Whether fallback parsing was used instead of LLM
        fallback_reason: Reason for fallback if used_fallback is True
        error_message: Error message if query was rejected
    """

    filters: SearchFilters
    used_fallback: bool = False
    fallback_reason: str | None = None
    error_message: str | None = None

    @property
    def is_rejected(self) -> bool:
        """Check if the query was rejected (too broad for the mode)."""
        return self.error_message is not None


@dataclass
class QueryProcessorStats:
    """Statistics tracking for query processor operations."""

    llm_fallback_count: int = 0
    llm_fallback_reasons: dict[str, int] = field(default_factory=dict)

    def record_fallback(self, reason: str | None) -> None:
        """Record a fallback event."""
        self.llm_fallback_count += 1
        normalized_reason = reason or "unknown"
        self.llm_fallback_reasons[normalized_reason] = (
            self.llm_fallback_reasons.get(normalized_reason, 0) + 1
        )


class QueryProcessor:
    """Process natural language queries with LLM and fallback support.

    This class encapsulates the logic for:
    1. Deciding whether to use LLM or fallback parsing
    2. Calling the LLM and handling errors
    3. Falling back to heuristic parsing when needed

    Example:
        processor = QueryProcessor(llm_mode="auto")
        result = processor.process(
            query="find recent Python files",
            client=llm_client,
            stats=stats,
        )
        if result.is_rejected:
            print(result.error_message)
        else:
            use_filters(result.filters)
    """

    def __init__(
        self,
        *,
        llm_mode: LLMMode = DEFAULT_LLM_MODE,
        offline_mode: bool = False,
    ) -> None:
        """Initialize the query processor.

        Args:
            llm_mode: LLM call policy ("always", "auto", "off")
            offline_mode: Whether to skip all network calls
        """
        self.llm_mode = "off" if offline_mode else llm_mode

    def process(
        self,
        query: str,
        *,
        client: LLMClient | None = None,
        stats: QueryProcessorStats | None = None,
    ) -> QueryResult:
        """Process a natural language query and extract search filters.

        Args:
            query: The natural language query
            client: LLM client for API calls (required if llm_mode needs it)
            stats: Optional stats tracker for fallback events

        Returns:
            QueryResult with filters or error message
        """
        fallback_filters = parse_query_fallback(query)
        llm_decision = decide_llm_usage(
            query=query,
            fallback_filters=fallback_filters,
            llm_mode=self.llm_mode,
        )
        use_llm = llm_decision.llm_called

        if not use_llm:
            return self._handle_heuristic_mode(fallback_filters, llm_decision.reason)

        # LLM mode
        return self._handle_llm_mode(
            query=query,
            client=client,
            fallback_filters=fallback_filters,
            stats=stats,
        )

    def _handle_heuristic_mode(
        self,
        fallback_filters: SearchFilters,
        decision_reason: str,
    ) -> QueryResult:
        """Handle query in heuristic (non-LLM) mode."""
        if not has_meaningful_filters(fallback_filters):
            error_msg = self._get_broad_query_error_message()
            return QueryResult(
                filters=SearchFilters(),
                error_message=error_msg,
            )

        logger.debug(
            "Heuristic mode selected (mode=%s reason=%s); skipping LLM",
            self.llm_mode,
            decision_reason,
        )
        return QueryResult(filters=fallback_filters)

    def _handle_llm_mode(
        self,
        query: str,
        client: LLMClient | None,
        fallback_filters: SearchFilters,
        stats: QueryProcessorStats | None,
    ) -> QueryResult:
        """Handle query in LLM mode with fallback support."""
        if client is None:
            # No client available, use fallback if possible
            if has_meaningful_filters(fallback_filters):
                return QueryResult(
                    filters=fallback_filters,
                    used_fallback=True,
                    fallback_reason="no_client",
                )
            return QueryResult(
                filters=SearchFilters(),
                error_message="No LLM client available and query too broad for fallback.",
            )

        try:
            logger.debug("Sending query to LLM")
            raw_response = client.extract_filters(query)
            logger.debug("Received LLM response payload")
            filters = parse_llm_response(raw_response)

            if not isinstance(filters, SearchFilters):
                filters = SearchFilters()

            if isinstance(filters, SearchFilters) and not has_meaningful_filters(filters):
                if has_meaningful_filters(fallback_filters):
                    if stats:
                        stats.record_fallback("empty_llm_filters")
                    return QueryResult(
                        filters=fallback_filters,
                        used_fallback=True,
                        fallback_reason="empty_llm_filters",
                    )

            return QueryResult(filters=filters)

        except httpx.HTTPError as exc:
            if has_meaningful_filters(fallback_filters):
                fallback_reason = f"http_{exc.__class__.__name__.lower()}"
                if stats:
                    stats.record_fallback(fallback_reason)
                return QueryResult(
                    filters=fallback_filters,
                    used_fallback=True,
                    fallback_reason=fallback_reason,
                )
            raise

        except Exception:
            # JSONDecodeError and other parsing errors
            if has_meaningful_filters(fallback_filters):
                if stats:
                    stats.record_fallback("invalid_llm_response")
                return QueryResult(
                    filters=fallback_filters,
                    used_fallback=True,
                    fallback_reason="invalid_llm_response",
                )
            raise

    def _get_broad_query_error_message(self) -> str:
        """Get appropriate error message for broad query based on mode."""
        if self.llm_mode == "off":
            return "Error: --llm-mode off query is too broad; add at least one concrete filter."
        return "Error: Query is too broad for heuristic mode; use --llm-mode always."
