"""Tests for semantic re-ranking."""

from pathlib import Path
from unittest.mock import MagicMock

from askfind.output.formatter import FileResult
from askfind.search.reranker import rerank_results


class TestRerankResults:
    def test_empty_results(self):
        """Empty results list should return empty list."""
        result = rerank_results(MagicMock(), "test query", [])
        assert result == []

    def test_single_result_unchanged(self):
        """Single result should be returned unchanged."""
        results = [FileResult(path=Path("a.txt"), size=10, modified=0)]
        result = rerank_results(MagicMock(), "test query", results)
        assert result == results

    def test_successful_reranking(self):
        """Should reorder results according to LLM response."""
        results = [
            FileResult(path=Path("first.txt"), size=10, modified=0),
            FileResult(path=Path("second.txt"), size=20, modified=0),
            FileResult(path=Path("third.txt"), size=30, modified=0),
        ]

        mock_client = MagicMock()
        # LLM returns reordered filenames
        mock_client.rerank.return_value = ["third.txt", "first.txt", "second.txt"]

        reranked = rerank_results(mock_client, "test query", results)

        assert len(reranked) == 3
        assert reranked[0].path.name == "third.txt"
        assert reranked[1].path.name == "first.txt"
        assert reranked[2].path.name == "second.txt"

    def test_partial_llm_response(self):
        """Should handle LLM returning fewer filenames than input."""
        results = [
            FileResult(path=Path("a.txt"), size=10, modified=0),
            FileResult(path=Path("b.txt"), size=20, modified=0),
            FileResult(path=Path("c.txt"), size=30, modified=0),
        ]

        mock_client = MagicMock()
        # LLM only returns 2 out of 3 files
        mock_client.rerank.return_value = ["b.txt", "a.txt"]

        reranked = rerank_results(mock_client, "test query", results)

        # Should include all files but prioritize LLM-ranked ones
        assert len(reranked) == 3
        assert reranked[0].path.name == "b.txt"
        assert reranked[1].path.name == "a.txt"
        # c.txt should still be included at the end
        assert reranked[2].path.name == "c.txt"

    def test_llm_returns_unknown_filenames(self):
        """Should ignore filenames from LLM that don't exist in results."""
        results = [
            FileResult(path=Path("a.txt"), size=10, modified=0),
            FileResult(path=Path("b.txt"), size=20, modified=0),
        ]

        mock_client = MagicMock()
        # LLM returns a filename that doesn't exist
        mock_client.rerank.return_value = ["nonexistent.txt", "a.txt", "b.txt"]

        reranked = rerank_results(mock_client, "test query", results)

        assert len(reranked) == 2
        assert reranked[0].path.name == "a.txt"
        assert reranked[1].path.name == "b.txt"
