"""Tests for filesystem walker."""

from pathlib import Path
import tarfile
import zipfile

import pytest
import askfind.search.walker as walker

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


class _EntryWithFailingStat:
    """DirEntry proxy that can raise OSError on stat()."""

    def __init__(self, entry, *, fail_stat: bool) -> None:
        self._entry = entry
        self.name = entry.name
        self.path = entry.path
        self._fail_stat = fail_stat

    def is_dir(self, follow_symlinks: bool = True) -> bool:
        return self._entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, follow_symlinks: bool = True) -> bool:
        return self._entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self) -> bool:
        return self._entry.is_symlink()

    def stat(self, follow_symlinks: bool = True):
        if self._fail_stat:
            raise OSError("simulated stat failure")
        return self._entry.stat(follow_symlinks=follow_symlinks)


class _ScandirWithStatFault:
    """scandir context manager proxy that swaps one entry with a faulty proxy."""

    def __init__(self, entries, *, failing_name: str) -> None:
        self._entries = entries
        self._failing_name = failing_name

    def __enter__(self):
        self._entries.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return self._entries.__exit__(exc_type, exc, tb)

    def __iter__(self):
        for entry in self._entries:
            if entry.name == self._failing_name:
                yield _EntryWithFailingStat(entry, fail_stat=True)
            else:
                yield entry


class _CountingScandir:
    """scandir context manager proxy that counts consumed entries."""

    def __init__(self, entries, *, counter: dict[str, int]) -> None:
        self._entries = entries
        self._counter = counter

    def __enter__(self):
        self._entries.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return self._entries.__exit__(exc_type, exc, tb)

    def __iter__(self):
        for entry in self._entries:
            self._counter["seen"] += 1
            yield entry


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

    def test_depth_prunes_recursion(self, tmp_path, monkeypatch):
        _make_tree(tmp_path)
        filters = SearchFilters(depth="<2")

        orig_scandir = walker.os.scandir
        scanned = []

        def scandir_guard(path):
            scanned.append(Path(path).resolve().as_posix())
            return orig_scandir(path)

        monkeypatch.setattr(walker.os, "scandir", scandir_guard)

        results = list(walk_and_filter(tmp_path, filters))
        names = {p.name for p in results}
        assert "src" in names
        assert "readme.md" in names
        assert scanned
        assert (tmp_path / "src").resolve().as_posix() in scanned
        assert (tmp_path / "src" / "auth").resolve().as_posix() not in scanned

    def test_depth_prunes_results(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(depth="<1")
        results = list(walk_and_filter(tmp_path, filters))
        names = {p.name for p in results}
        assert "src" in names
        assert "readme.md" in names
        assert "login.py" not in names

    def test_has_filter_does_not_follow_symlink_targets_outside_root(self, tmp_path):
        outside_root = tmp_path.parent / f"{tmp_path.name}_outside"
        outside_root.mkdir()
        outside_file = outside_root / "outside.txt"
        outside_file.write_text("SECRET_TOKEN")
        outside_dir = outside_root / "outside_dir"
        outside_dir.mkdir()
        outside_nested_file = outside_dir / "nested.txt"
        outside_nested_file.write_text("SECRET_TOKEN")

        inside_file = tmp_path / "inside.txt"
        inside_file.write_text("SECRET_TOKEN")

        file_symlink = tmp_path / "outside_file_link"
        dir_symlink = tmp_path / "outside_dir_link"
        try:
            file_symlink.symlink_to(outside_file)
            dir_symlink.symlink_to(outside_dir, target_is_directory=True)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        filters = SearchFilters(has=["SECRET_TOKEN"])
        results = list(walk_and_filter(tmp_path, filters))

        assert inside_file in results
        assert file_symlink not in results
        assert dir_symlink not in results
        assert outside_file not in results
        assert outside_nested_file not in results
        assert all(tmp_path in path.parents for path in results)

    def test_permission_error_on_root_scandir_returns_empty_results(self, tmp_path, monkeypatch):
        def denied_scandir(_path):
            raise PermissionError("denied")

        monkeypatch.setattr(walker.os, "scandir", denied_scandir)

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        assert results == []

    def test_entry_stat_oserror_branch_continues_traversal(self, tmp_path, monkeypatch):
        (tmp_path / "good_dir").mkdir()
        expected = tmp_path / "good_dir" / "expected.txt"
        expected.write_text("ok")
        broken = tmp_path / "broken.txt"
        broken.write_text("broken")

        orig_scandir = walker.os.scandir

        def scandir_with_fault(path):
            if Path(path) == tmp_path:
                return _ScandirWithStatFault(orig_scandir(path), failing_name=broken.name)
            return orig_scandir(path)

        monkeypatch.setattr(walker.os, "scandir", scandir_with_fault)

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        assert expected in results
        assert broken not in results

    def test_matches_stat_false_still_recurses_into_child_directories(
        self, tmp_path, monkeypatch
    ):
        _make_tree(tmp_path)
        filters = SearchFilters()

        monkeypatch.setattr(filters, "matches_stat", lambda _stat: False)

        orig_scandir = walker.os.scandir
        scanned = []

        def scandir_guard(path):
            scanned.append(Path(path).resolve().as_posix())
            return orig_scandir(path)

        monkeypatch.setattr(walker.os, "scandir", scandir_guard)

        results = list(walk_and_filter(tmp_path, filters))
        assert results == []
        assert (tmp_path / "src").resolve().as_posix() in scanned
        assert (tmp_path / "src" / "auth").resolve().as_posix() in scanned

    def test_depth_mismatch_still_recurses_and_finds_deeper_matches(self, tmp_path, monkeypatch):
        _make_tree(tmp_path)
        filters = SearchFilters(depth=">0", name="login.py")

        orig_scandir = walker.os.scandir
        scanned = []

        def scandir_guard(path):
            scanned.append(Path(path).resolve().as_posix())
            return orig_scandir(path)

        monkeypatch.setattr(walker.os, "scandir", scandir_guard)

        results = list(walk_and_filter(tmp_path, filters))
        assert tmp_path / "src" / "auth" / "login.py" in results
        assert tmp_path / "readme.md" not in results
        assert (tmp_path / "src").resolve().as_posix() in scanned
        assert (tmp_path / "src" / "auth").resolve().as_posix() in scanned

    def test_gitignore_excludes_matching_files(self, tmp_path):
        _make_tree(tmp_path)
        (tmp_path / ".gitignore").write_text("*.md\n")

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        names = {p.name for p in results}

        assert "readme.md" not in names
        assert "login.py" in names

    def test_askfindignore_excludes_directory(self, tmp_path):
        _make_tree(tmp_path)
        (tmp_path / ".askfindignore").write_text("tests/\n")

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        names = {p.name for p in results}

        assert "test_auth.py" not in names
        assert "config.toml" in names

    def test_ignore_negation_reincludes_file(self, tmp_path):
        _make_tree(tmp_path)
        (tmp_path / ".gitignore").write_text("*.py\n!login.py\n")

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        names = {p.name for p in results}

        assert "login.py" in names
        assert "logout.py" not in names
        assert "test_auth.py" not in names

    def test_can_disable_ignore_files(self, tmp_path):
        _make_tree(tmp_path)
        (tmp_path / ".gitignore").write_text("*.md\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(),
                respect_ignore_files=False,
            )
        )
        names = {p.name for p in results}

        assert "readme.md" in names

    def test_nested_gitignore_applies_from_its_directory(self, tmp_path):
        _make_tree(tmp_path)
        (tmp_path / "src" / ".gitignore").write_text("*.py\n!auth/login.py\n")

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        paths = {p.relative_to(tmp_path).as_posix() for p in results}

        assert "src/auth/login.py" in paths
        assert "src/auth/logout.py" not in paths
        assert "tests/test_auth.py" in paths

    def test_root_anchored_ignore_pattern_only_matches_root(self, tmp_path):
        _make_tree(tmp_path)
        nested_readme = tmp_path / "src" / "readme.md"
        nested_readme.write_text("# Nested readme")
        (tmp_path / ".gitignore").write_text("/readme.md\n")

        results = list(walk_and_filter(tmp_path, SearchFilters()))
        paths = {p.relative_to(tmp_path).as_posix() for p in results}

        assert "readme.md" not in paths
        assert "src/readme.md" in paths

    def test_excludes_binary_files_by_default(self, tmp_path):
        text_file = tmp_path / "notes.txt"
        text_file.write_text("hello")
        binary_file = tmp_path / "blob.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        results = list(walk_and_filter(tmp_path, SearchFilters(type="file")))

        assert text_file in results
        assert binary_file not in results

    def test_can_include_binary_files(self, tmp_path):
        binary_file = tmp_path / "blob.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file"),
                exclude_binary_files=False,
            )
        )

        assert binary_file in results

    def test_follow_symlinks_includes_internal_symlink_target_file(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        symlink = tmp_path / "target-link.txt"
        try:
            symlink.symlink_to(target)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", ext=[".txt"]),
                follow_symlinks=True,
            )
        )

        assert target in results
        assert symlink in results

    def test_follow_symlinks_does_not_escape_search_root(self, tmp_path):
        outside_root = tmp_path.parent / f"{tmp_path.name}_outside_follow"
        outside_root.mkdir()
        outside_file = outside_root / "secret.txt"
        outside_file.write_text("secret")
        symlink = tmp_path / "secret-link.txt"
        try:
            symlink.symlink_to(outside_file)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", ext=[".txt"]),
                follow_symlinks=True,
            )
        )

        assert symlink not in results
        assert outside_file not in results

    def test_follow_symlinks_avoids_directory_cycles(self, tmp_path):
        loop_dir = tmp_path / "loop"
        loop_dir.mkdir()
        target = loop_dir / "target.txt"
        target.write_text("ok")
        loop_link = loop_dir / "again"
        try:
            loop_link.symlink_to(loop_dir, target_is_directory=True)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", name="target.txt"),
                max_results=10,
                follow_symlinks=True,
            )
        )

        assert results.count(target) == 1

    def test_follow_symlinks_allows_content_matching_on_internal_links(self, tmp_path):
        target = tmp_path / "token.txt"
        target.write_text("SECRET_TOKEN")
        symlink = tmp_path / "token-link.txt"
        try:
            symlink.symlink_to(target)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(has=["SECRET_TOKEN"]),
                follow_symlinks=True,
            )
        )

        assert target in results
        assert symlink in results

    def test_parallel_workers_match_sequential_results(self, tmp_path):
        _make_tree(tmp_path)
        filters = SearchFilters(type="file")

        sequential = {
            p.relative_to(tmp_path).as_posix()
            for p in walk_and_filter(tmp_path, filters, traversal_workers=1)
        }
        parallel = {
            p.relative_to(tmp_path).as_posix()
            for p in walk_and_filter(tmp_path, filters, traversal_workers=4)
        }

        assert parallel == sequential

    def test_parallel_workers_respect_max_results(self, tmp_path):
        _make_tree(tmp_path)

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file"),
                max_results=2,
                traversal_workers=4,
            )
        )

        assert len(results) == 2

    def test_search_archives_zip_matches_inner_python_file(self, tmp_path):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("src/in_archive.py", "print('ok')\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", ext=[".py"]),
                search_archives=True,
            )
        )

        assert archive in results

    def test_search_archives_tar_gz_matches_inner_path_filter(self, tmp_path):
        archive = tmp_path / "bundle.tar.gz"
        inner_file = tmp_path / "inner_target.txt"
        inner_file.write_text("x")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(inner_file, arcname="pkg/deep/target.txt")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", path="deep/target"),
                search_archives=True,
            )
        )

        assert archive in results

    def test_search_archives_disabled_does_not_match_inner_entries(self, tmp_path):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("src/in_archive.py", "print('ok')\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", ext=[".py"]),
                search_archives=False,
            )
        )

        assert archive not in results

    def test_search_archives_zip_matches_inner_content_filter(self, tmp_path):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("src/", "")
            zf.writestr("src/in_archive.py", "# TODO: implement\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["TODO"]),
                search_archives=True,
            )
        )

        assert archive in results

    def test_search_archives_disabled_does_not_match_inner_content_filter(self, tmp_path):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("src/in_archive.py", "# TODO: implement\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["TODO"]),
                search_archives=False,
            )
        )

        assert archive not in results

    def test_search_archives_has_filter_respects_inner_member_name_filters(self, tmp_path):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("docs/note.txt", "TOKEN")
            zf.writestr("src/module.py", "print('ok')\n")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", ext=[".py"], has=["TOKEN"]),
                search_archives=True,
            )
        )

        assert archive not in results

    def test_search_archives_tar_gz_matches_inner_content_filter(self, tmp_path):
        archive = tmp_path / "bundle.tar.gz"
        inner_file = tmp_path / "inner_token.py"
        inner_file.write_text("# TODO: inside tar\n")
        with tarfile.open(archive, "w:gz") as tar:
            dir_info = tarfile.TarInfo("pkg")
            dir_info.type = tarfile.DIRTYPE
            tar.addfile(dir_info)
            tar.add(inner_file, arcname="pkg/inner_token.py")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["TODO"]),
                search_archives=True,
            )
        )

        assert archive in results

    def test_search_archives_zip_content_filter_skips_oversized_members(self, tmp_path, monkeypatch):
        archive = tmp_path / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("pkg/huge.txt", "AB")
        monkeypatch.setattr(walker, "MAX_CONTENT_SCAN_BYTES", 1)

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["A"]),
                search_archives=True,
            )
        )

        assert archive not in results

    def test_search_archives_tar_gz_content_filter_skips_oversized_members(self, tmp_path, monkeypatch):
        archive = tmp_path / "bundle.tar.gz"
        inner_file = tmp_path / "inner_large.txt"
        inner_file.write_text("AB")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(inner_file, arcname="pkg/inner_large.txt")
        monkeypatch.setattr(walker, "MAX_CONTENT_SCAN_BYTES", 1)

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["A"]),
                search_archives=True,
            )
        )

        assert archive not in results

    def test_search_archives_skips_corrupt_zip_for_content_filter(self, tmp_path):
        archive = tmp_path / "broken.zip"
        archive.write_text("not a real zip")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["TODO"]),
                search_archives=True,
            )
        )

        assert archive not in results

    def test_search_archives_skips_corrupt_tar_gz_for_content_filter(self, tmp_path):
        archive = tmp_path / "broken.tar.gz"
        archive.write_text("not a real tar")

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file", has=["TODO"]),
                search_archives=True,
            )
        )

        assert archive not in results

    def test_max_results_stops_scandir_iteration_early_sequential(self, tmp_path, monkeypatch):
        for idx in range(10):
            (tmp_path / f"file_{idx}.txt").write_text("text")

        counter = {"seen": 0}
        orig_scandir = walker.os.scandir

        def counting_scandir(path):
            entries = orig_scandir(path)
            if Path(path).resolve() == tmp_path.resolve():
                return _CountingScandir(entries, counter=counter)
            return entries

        monkeypatch.setattr(walker.os, "scandir", counting_scandir)

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file"),
                max_results=1,
                traversal_workers=1,
            )
        )

        assert len(results) == 1
        assert counter["seen"] == 1

    def test_max_results_stops_scandir_iteration_early_parallel(self, tmp_path, monkeypatch):
        for idx in range(10):
            (tmp_path / f"file_{idx}.txt").write_text("text")

        counter = {"seen": 0}
        orig_scandir = walker.os.scandir

        def counting_scandir(path):
            entries = orig_scandir(path)
            if Path(path).resolve() == tmp_path.resolve():
                return _CountingScandir(entries, counter=counter)
            return entries

        monkeypatch.setattr(walker.os, "scandir", counting_scandir)

        results = list(
            walk_and_filter(
                tmp_path,
                SearchFilters(type="file"),
                max_results=1,
                traversal_workers=4,
            )
        )

        assert len(results) == 1
        assert counter["seen"] == 1
