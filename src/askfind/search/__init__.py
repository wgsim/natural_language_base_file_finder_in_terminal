"""Search engine for askfind."""

from askfind.search.filters import SearchFilters
from askfind.search.walker import walk_and_filter
from askfind.search.reranker import rerank_results
from askfind.search.cache import SearchCache, build_search_cache_key, compute_root_fingerprint
from askfind.search.index import (
    IndexBuildResult,
    IndexClearResult,
    IndexOptions,
    IndexStatusResult,
    build_index,
    clear_index,
    get_index_status,
    update_index,
)

__all__ = [
    "SearchFilters",
    "walk_and_filter",
    "rerank_results",
    "SearchCache",
    "build_search_cache_key",
    "compute_root_fingerprint",
    "IndexOptions",
    "IndexBuildResult",
    "IndexStatusResult",
    "IndexClearResult",
    "build_index",
    "update_index",
    "get_index_status",
    "clear_index",
]
