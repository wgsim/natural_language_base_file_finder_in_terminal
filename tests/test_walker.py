"""Tests for filesystem walker."""

from pathlib import Path

from askfind.search.filters import SearchFilters
from askfind.search.walker import walk_and_filter


def _make_tree(tmp_path: Path) -> None:
    """Create a test file tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "src" / "auth" / "login.py").write_text("def login(): pass")
    (tmp_path / "src" / "auth" / "logout.py").write_text("def logout(): pass")
    (tmp_path / "src" / "config.toml").write_text('[db]\nhost = "localhost"')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("# TODO: add tests\nimport pytest")
    (tmp_path / "readme.md").write_text("# Project")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("gitconfig")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module")


class TestWalkAndFilter:
    def test_no_filters_returns_all_files(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        paths = [r.name for r in results]
        assert "login.py" in paths
        assert "readme.md" in paths

    def test_skips_git_directory(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        paths = [str(r) for r in results]
        assert not any(".git" in p for p in paths)

    def test_skips_node_modules(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters))
        names = [r.name for r in results]
        assert "node_modules" not in names
        assert "pkg.js" not in names  # file inside node_modules should also be skipped

    def test_ext_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(ext=[".py"])
        results = list(walk_and_filter(tmp_path, filters))
        assert all(r.suffix == ".py" for r in results)
        assert len(results) == 3  # login.py, logout.py, test_auth.py

    def test_name_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(name="*login*")
        results = list(walk_and_filter(tmp_path, filters))
        assert len(results) == 1
        assert results[0].name == "login.py"

    def test_has_content_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(has=["TODO"])
        results = list(walk_and_filter(tmp_path, filters))
        assert len(results) == 1
        assert results[0].name == "test_auth.py"

    def test_path_filter(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(path="auth")
        results = list(walk_and_filter(tmp_path, filters))
        names = [r.name for r in results]
        assert "login.py" in names
        assert "logout.py" in names
        assert "readme.md" not in names

    def test_type_dir(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(type="dir")
        results = list(walk_and_filter(tmp_path, filters))
        names = [r.name for r in results]
        assert "src" in names
        assert "auth" in names
        assert "tests" in names

    def test_max_results(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters()
        results = list(walk_and_filter(tmp_path, filters, max_results=2))
        assert len(results) == 2

    def test_depth_prunes_recursion(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(depth="<1")
        results = list(walk_and_filter(tmp_path, filters))
        names = {p.name for p in results}
        assert "src" in names
        assert "readme.md" in names
        assert "login.py" not in names

    def test_depth_zero_matches_root_only(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(depth="0")
        results = list(walk_and_filter(tmp_path, filters))
        names = {p.name for p in results}
        assert "readme.md" in names
        assert "src" in names
        assert "login.py" not in names
