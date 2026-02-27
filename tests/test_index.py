"""Tests for search index management."""

from __future__ import annotations

import json

import pytest

from askfind.search import index


def _options(
    *,
    respect_ignore_files: bool = True,
    follow_symlinks: bool = False,
    exclude_binary_files: bool = True,
    traversal_workers: int = 1,
) -> index.IndexOptions:
    return index.IndexOptions(
        respect_ignore_files=respect_ignore_files,
        follow_symlinks=follow_symlinks,
        exclude_binary_files=exclude_binary_files,
        traversal_workers=traversal_workers,
    )


def test_build_index_and_status_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    (root / "b.txt").write_text("hello\n")

    result = index.build_index(root=root, options=_options())

    assert result.root == root
    assert result.file_count == 2
    assert result.index_path.is_file()

    payload = json.loads(result.index_path.read_text(encoding="utf-8"))
    assert payload["version"] == index.INDEX_VERSION
    assert payload["root"] == str(root)
    assert payload["root_fingerprint"] == result.root_fingerprint
    assert payload["options"] == {
        "respect_ignore_files": True,
        "follow_symlinks": False,
        "exclude_binary_files": True,
        "traversal_workers": 1,
    }
    assert payload["paths"] == sorted([str(root / "a.py"), str(root / "b.txt")])

    status = index.get_index_status(root=root)
    assert status.exists is True
    assert status.file_count == 2
    assert status.stale is False


def test_update_index_refreshes_after_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")

    first = index.build_index(root=root, options=_options())
    (root / "b.py").write_text("print('b')\n")
    second = index.update_index(root=root, options=_options())

    assert first.file_count == 1
    assert second.file_count == 2
    status = index.get_index_status(root=root)
    assert status.exists is True
    assert status.file_count == 2


def test_status_reports_stale_when_root_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    index.build_index(root=root, options=_options())

    (root / "new.py").write_text("print('new')\n")
    status = index.get_index_status(root=root)

    assert status.exists is True
    assert status.stale is True


def test_status_missing_index_returns_exists_false(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()

    status = index.get_index_status(root=root)

    assert status.exists is False
    assert status.file_count == 0
    assert status.stale is True


def test_clear_index_returns_true_then_false(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    index.build_index(root=root, options=_options())

    first = index.clear_index(root=root)
    second = index.clear_index(root=root)

    assert first.cleared is True
    assert second.cleared is False


def test_build_index_raises_for_missing_or_non_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        index.build_index(root=missing, options=_options())

    not_dir = tmp_path / "file.txt"
    not_dir.write_text("x")
    with pytest.raises(NotADirectoryError):
        index.build_index(root=not_dir, options=_options())


def test_collect_file_paths_forces_minimum_worker_count(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")

    seen: dict[str, object] = {}

    def fake_walk_and_filter(*args, **kwargs):
        seen["workers"] = kwargs["traversal_workers"]
        return iter([root / "a.py"])

    monkeypatch.setattr(index, "walk_and_filter", fake_walk_and_filter)
    paths = index._collect_file_paths(root=root, options=_options(traversal_workers=0))

    assert seen["workers"] == 1
    assert paths == [str(root / "a.py")]


def test_index_path_for_root_is_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = (tmp_path / "repo").resolve()

    p1 = index._index_path_for_root(root)
    p2 = index._index_path_for_root(root)

    assert p1 == p2
    assert p1.parent == tmp_path / "indexes"
    assert p1.name.endswith(".json")


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        json.dumps(["not", "a", "dict"]),
        json.dumps({"version": 999, "paths": [], "root_fingerprint": "fp"}),
        json.dumps({"version": 1, "paths": [], "root_fingerprint": 123}),
        json.dumps({"version": 1, "paths": "bad", "root_fingerprint": "fp"}),
        json.dumps({"version": 1, "paths": [1, 2], "root_fingerprint": "fp"}),
    ],
)
def test_read_payload_rejects_invalid_payloads(tmp_path, payload):
    index_path = tmp_path / "idx.json"
    index_path.write_text(payload, encoding="utf-8")

    assert index._read_payload(index_path=index_path) is None


def test_read_payload_handles_missing_file(tmp_path):
    missing = tmp_path / "missing.json"
    assert index._read_payload(index_path=missing) is None


def test_read_payload_accepts_valid_payload(tmp_path):
    index_path = tmp_path / "idx.json"
    index_path.write_text(
        json.dumps({"version": 1, "root_fingerprint": "fp", "paths": ["a.py", "b.py"]}),
        encoding="utf-8",
    )

    payload = index._read_payload(index_path=index_path)

    assert payload is not None
    assert payload.root_fingerprint == "fp"
    assert payload.paths == ("a.py", "b.py")


def test_query_index_returns_matches_when_index_is_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    py_file = root / "a.py"
    txt_file = root / "b.txt"
    py_file.write_text("print('a')\n")
    txt_file.write_text("hello\n")
    options = _options()
    index.build_index(root=root, options=options)

    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=0,
        options=options,
    )

    assert results == [py_file]


def test_query_index_populates_diagnostics_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    py_file = root / "a.py"
    py_file.write_text("print('a')\n")
    options = _options()
    index.build_index(root=root, options=options)
    diagnostics = index.IndexQueryDiagnostics()

    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=0,
        options=options,
        diagnostics=diagnostics,
    )

    assert results == [py_file]
    assert diagnostics.fallback_reason is None


def test_query_index_returns_none_when_options_do_not_match(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    index.build_index(root=root, options=_options())

    diagnostics = index.IndexQueryDiagnostics()
    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=0,
        options=_options(follow_symlinks=True),
        diagnostics=diagnostics,
    )

    assert results is None
    assert diagnostics.fallback_reason == "options_mismatch"


def test_query_index_returns_none_when_index_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    options = _options()
    index.build_index(root=root, options=options)
    (root / "b.py").write_text("print('b')\n")

    diagnostics = index.IndexQueryDiagnostics()
    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=0,
        options=options,
        diagnostics=diagnostics,
    )

    assert results is None
    assert diagnostics.fallback_reason == "stale_index"


def test_query_index_returns_none_for_corrupt_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    index_path = index._index_path_for_root(root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{not-json", encoding="utf-8")

    diagnostics = index.IndexQueryDiagnostics()
    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=0,
        options=_options(),
        diagnostics=diagnostics,
    )

    assert results is None
    assert diagnostics.fallback_reason == "missing_or_invalid_index"


def test_query_index_returns_none_for_non_searchfilters(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    diagnostics = index.IndexQueryDiagnostics()

    results = index.query_index(
        root=root,
        filters={},  # type: ignore[arg-type]
        max_results=0,
        options=_options(),
        diagnostics=diagnostics,
    )

    assert results is None
    assert diagnostics.fallback_reason == "invalid_filters"


def test_query_index_returns_none_for_non_file_type(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    opts = _options()
    index.build_index(root=root, options=opts)

    diagnostics = index.IndexQueryDiagnostics()
    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="dir"),
        max_results=0,
        options=opts,
        diagnostics=diagnostics,
    )

    assert results is None
    assert diagnostics.fallback_reason == "unsupported_filters"


def test_query_index_respects_max_results(tmp_path, monkeypatch):
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("print('a')\n")
    (root / "b.py").write_text("print('b')\n")
    opts = _options()
    index.build_index(root=root, options=opts)

    results = index.query_index(
        root=root,
        filters=index.SearchFilters(type="file", ext=[".py"]),
        max_results=1,
        options=opts,
    )

    assert results is not None
    assert len(results) == 1


def test_matches_indexed_path_filter_rejections(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    path = root / "a.py"
    path.write_text("print('a')\n")

    assert index._matches_indexed_path(
        root=root,
        path=path,
        filters=index.SearchFilters(type="dir"),
        follow_symlinks=False,
    ) is False
    assert index._matches_indexed_path(
        root=root,
        path=path,
        filters=index.SearchFilters(type="file", depth=">0"),
        follow_symlinks=False,
    ) is False
    assert index._matches_indexed_path(
        root=root,
        path=path,
        filters=index.SearchFilters(type="file", path="missing-subpath"),
        follow_symlinks=False,
    ) is False
    assert index._matches_indexed_path(
        root=root,
        path=path,
        filters=index.SearchFilters(type="file", size=">10GB"),
        follow_symlinks=False,
    ) is False
    assert index._matches_indexed_path(
        root=root,
        path=path,
        filters=index.SearchFilters(type="file", has=["not-found-token"]),
        follow_symlinks=False,
    ) is False


def test_matches_indexed_path_outside_root_returns_false(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("print('x')\n")

    assert index._matches_indexed_path(
        root=root,
        path=outside,
        filters=index.SearchFilters(type="file"),
        follow_symlinks=False,
    ) is False


@pytest.mark.parametrize(
    "raw_options",
    [
        [],
        {"follow_symlinks": False, "exclude_binary_files": True, "traversal_workers": 1},
        {
            "respect_ignore_files": "yes",
            "follow_symlinks": False,
            "exclude_binary_files": True,
            "traversal_workers": 1,
        },
        {
            "respect_ignore_files": True,
            "follow_symlinks": "no",
            "exclude_binary_files": True,
            "traversal_workers": 1,
        },
        {
            "respect_ignore_files": True,
            "follow_symlinks": False,
            "exclude_binary_files": "no",
            "traversal_workers": 1,
        },
        {
            "respect_ignore_files": True,
            "follow_symlinks": False,
            "exclude_binary_files": True,
            "traversal_workers": True,
        },
    ],
)
def test_parse_options_rejects_invalid_shapes(raw_options):
    assert index._parse_options(raw_options) is None
