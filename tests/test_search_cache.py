"""Tests for filesystem search cache."""

from pathlib import Path

from askfind.search.cache import (
    SearchCache,
    build_search_cache_key,
    compute_root_fingerprint,
)


def test_cache_set_and_get_hit(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache = SearchCache(cache_path=cache_file, ttl_seconds=60, max_entries=16)
    key = "k1"
    root_fp = "root-fp"
    file_a = tmp_path / "a.py"
    file_a.write_text("print('a')\n")

    cache.set(key=key, root_fingerprint=root_fp, paths=[file_a])
    hit = cache.get(key=key, root_fingerprint=root_fp)

    assert hit == [file_a]


def test_cache_miss_on_root_fingerprint_change(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json", ttl_seconds=60, max_entries=16)
    file_a = tmp_path / "a.py"
    file_a.write_text("print('a')\n")
    cache.set(key="k1", root_fingerprint="fp-old", paths=[file_a])

    miss = cache.get(key="k1", root_fingerprint="fp-new")
    assert miss is None


def test_cache_entry_expires_by_ttl(tmp_path, monkeypatch):
    cache = SearchCache(cache_path=tmp_path / "cache.json", ttl_seconds=10, max_entries=16)
    file_a = tmp_path / "a.py"
    file_a.write_text("print('a')\n")

    monkeypatch.setattr("askfind.search.cache.time.time", lambda: 1000.0)
    cache.set(key="k1", root_fingerprint="fp", paths=[file_a])

    monkeypatch.setattr("askfind.search.cache.time.time", lambda: 1015.0)
    miss = cache.get(key="k1", root_fingerprint="fp")
    assert miss is None


def test_build_search_cache_key_changes_with_options(tmp_path):
    root = Path(tmp_path)
    key_a = build_search_cache_key(
        query="python files",
        root=root,
        model="m1",
        base_url="https://api.example.com/v1",
        max_results=10,
        no_rerank=False,
        respect_ignore_files=True,
        follow_symlinks=False,
        exclude_binary_files=True,
        traversal_workers=1,
    )
    key_b = build_search_cache_key(
        query="python files",
        root=root,
        model="m1",
        base_url="https://api.example.com/v1",
        max_results=10,
        no_rerank=False,
        respect_ignore_files=True,
        follow_symlinks=False,
        exclude_binary_files=True,
        traversal_workers=8,
    )

    assert key_a != key_b


def test_compute_root_fingerprint_changes_after_top_level_mutation(tmp_path):
    before = compute_root_fingerprint(tmp_path)
    (tmp_path / "new_file.py").write_text("x = 1\n")
    after = compute_root_fingerprint(tmp_path)

    assert before != after


def test_cache_stats_track_hits_misses_and_sets(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json", ttl_seconds=60, max_entries=16)
    file_a = tmp_path / "a.py"
    file_a.write_text("print('a')\n")

    assert cache.stats() == {"hits": 0, "misses": 0, "sets": 0}

    cache.get(key="missing", root_fingerprint="fp")
    cache.set(key="k1", root_fingerprint="fp", paths=[file_a])
    cache.get(key="k1", root_fingerprint="fp")

    assert cache.stats() == {"hits": 1, "misses": 1, "sets": 1}
