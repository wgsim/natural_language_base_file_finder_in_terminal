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
        search_archives=False,
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
        search_archives=True,
        traversal_workers=8,
    )

    assert key_a != key_b


def test_build_search_cache_key_changes_with_archive_option(tmp_path):
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
        search_archives=False,
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
        search_archives=True,
        traversal_workers=1,
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


def test_compute_root_fingerprint_missing_root_returns_digest():
    missing_root = Path("/definitely/missing/askfind-root")
    digest = compute_root_fingerprint(missing_root)

    assert isinstance(digest, str)
    assert len(digest) == 64


def test_compute_root_fingerprint_scandir_error_returns_digest(tmp_path):
    regular_file = tmp_path / "not_a_directory.txt"
    regular_file.write_text("x")

    digest = compute_root_fingerprint(regular_file)

    assert isinstance(digest, str)
    assert len(digest) == 64


def test_load_entries_rejects_non_dict_payload(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('["not-a-dict"]', encoding="utf-8")

    cache = SearchCache(cache_path=cache_file)

    assert cache._load_entries() == {}


def test_load_entries_rejects_wrong_version(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"version": 999, "entries": {}}', encoding="utf-8")

    cache = SearchCache(cache_path=cache_file)

    assert cache._load_entries() == {}


def test_load_entries_rejects_non_dict_entries(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    cache = SearchCache(cache_path=cache_file)

    assert cache._load_entries() == {}


def test_load_entries_skips_non_dict_entry_value(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"version": 1, "entries": {"k1": []}}', encoding="utf-8")

    cache = SearchCache(cache_path=cache_file)

    assert cache._load_entries() == {}


def test_get_miss_on_invalid_paths_shape_increments_miss(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json")
    cache._load_entries = lambda: {"k1": {"created_at": 1.0, "root_fingerprint": "fp", "paths": "bad"}}  # type: ignore[method-assign]
    cache._prune = lambda entries, now: True  # type: ignore[method-assign]
    save_calls: list[dict[str, object]] = []
    cache._save_entries = lambda entries: save_calls.append(dict(entries))  # type: ignore[method-assign]

    assert cache.get(key="k1", root_fingerprint="fp") is None
    assert cache.stats()["misses"] == 1
    assert len(save_calls) == 1


def test_get_miss_on_fingerprint_mismatch_saves_when_pruned(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json")
    cache._load_entries = lambda: {"k1": {"created_at": 1.0, "root_fingerprint": "old", "paths": []}}  # type: ignore[method-assign]
    cache._prune = lambda entries, now: True  # type: ignore[method-assign]
    saved = {"count": 0}
    cache._save_entries = lambda entries: saved.__setitem__("count", saved["count"] + 1)  # type: ignore[method-assign]

    assert cache.get(key="k1", root_fingerprint="new") is None
    assert saved["count"] == 1


def test_get_hit_saves_when_pruned(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json")
    file_a = tmp_path / "a.py"
    file_a.write_text("x")
    cache._load_entries = lambda: {  # type: ignore[method-assign]
        "k1": {"created_at": 1.0, "root_fingerprint": "fp", "paths": [str(file_a)]}
    }
    cache._prune = lambda entries, now: True  # type: ignore[method-assign]
    saved = {"count": 0}
    cache._save_entries = lambda entries: saved.__setitem__("count", saved["count"] + 1)  # type: ignore[method-assign]

    assert cache.get(key="k1", root_fingerprint="fp") == [file_a]
    assert saved["count"] == 1


def test_prune_drops_invalid_created_at_and_enforces_max_entries(tmp_path):
    cache = SearchCache(cache_path=tmp_path / "cache.json", ttl_seconds=100, max_entries=1)
    entries: dict[str, dict[str, object]] = {
        "invalid": {"created_at": "bad"},
        "old": {"created_at": 1.0},
        "new": {"created_at": 2.0},
    }

    changed = cache._prune(entries, now=2.0)

    assert changed is True
    assert "invalid" not in entries
    assert "old" not in entries
    assert "new" in entries
