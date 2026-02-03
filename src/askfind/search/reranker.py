"""Optional LLM-based semantic re-ranking of search results."""

from __future__ import annotations

from askfind.llm.client import LLMClient
from askfind.output.formatter import FileResult


def rerank_results(
    client: LLMClient,
    query: str,
    results: list[FileResult],
) -> list[FileResult]:
    """Re-rank results using LLM semantic understanding.

    Returns results in relevance order.
    """
    if len(results) <= 1:
        return results

    path_list = [str(r.path) for r in results]
    ranked_paths = client.rerank(query, path_list)

    path_to_result = {str(r.path): r for r in results}
    ranked = [path_to_result[p] for p in ranked_paths if p in path_to_result]

    # Append any results not returned by LLM (safety net)
    ranked_set = {str(r.path) for r in ranked}
    for r in results:
        if str(r.path) not in ranked_set:
            ranked.append(r)

    return ranked
