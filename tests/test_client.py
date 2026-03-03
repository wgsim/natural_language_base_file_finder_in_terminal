"""Tests for LLM client."""

import json
from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from askfind.llm.client import LLMClient, LLMResponseSchemaError


class TestLLMClient:
    @pytest.fixture(autouse=True)
    def _isolate_extract_filters_cache(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            LLMClient,
            "_EXTRACT_FILTERS_DISK_CACHE_FILE",
            tmp_path / "extract_filters_cache.json",
        )
        LLMClient.reset_extract_filters_cache()

    def test_context_manager(self):
        """Client should work as context manager."""
        with LLMClient(base_url="https://api.example.com", api_key="test-key", model="test-model") as client:
            assert client is not None
            assert client._http is not None

    def test_extract_filters_success(self):
        """extract_filters should return LLM response content."""
        LLMClient.reset_extract_filters_cache()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                result = client.extract_filters("find Python files")

            assert result == '{"ext": [".py"]}'
            mock_http.post.assert_called_once()

    def test_extract_filters_memoizes_normalized_query(self):
        """extract_filters should avoid duplicate HTTP calls for normalized identical queries."""
        LLMClient.reset_extract_filters_cache()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                result1 = client.extract_filters("find Python files")
                result2 = client.extract_filters("  find Python files  ")

            assert result1 == '{"ext": [".py"]}'
            assert result2 == '{"ext": [".py"]}'
            mock_http.post.assert_called_once()

    def test_extract_filters_cache_key_separates_model_and_base_url(self):
        """extract_filters cache key should include model and base URL."""
        LLMClient.reset_extract_filters_cache()
        response_a = MagicMock()
        response_a.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }
        response_b = MagicMock()
        response_b.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }
        response_c = MagicMock()
        response_c.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }

        with patch("httpx.Client") as mock_client_class:
            mock_http_a = MagicMock()
            mock_http_a.post.return_value = response_a
            mock_http_b = MagicMock()
            mock_http_b.post.return_value = response_b
            mock_http_c = MagicMock()
            mock_http_c.post.return_value = response_c
            mock_client_class.side_effect = [mock_http_a, mock_http_b, mock_http_c]

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client_a:
                client_a.extract_filters("find Python files")
            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4o") as client_b:
                client_b.extract_filters("find Python files")
            with LLMClient(base_url="https://api2.example.com", api_key="test-key", model="gpt-4") as client_c:
                client_c.extract_filters("find Python files")

            mock_http_a.post.assert_called_once()
            mock_http_b.post.assert_called_once()
            mock_http_c.post.assert_called_once()

    def test_extract_filters_http_error(self):
        """extract_filters should raise on HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                    client.extract_filters("test query")

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"choices": []},
            {"choices": [{}]},
            {"choices": [{"message": {}}]},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "   "}}]},
        ],
    )
    def test_extract_filters_invalid_response_schema_raises_controlled_error(self, payload):
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                with pytest.raises(LLMResponseSchemaError):
                    client.extract_filters("test query")

    def test_extract_filters_disk_cache_hit_across_instances(self, tmp_path: Path):
        """extract_filters should read persisted cache on a fresh client instance."""
        LLMClient.reset_extract_filters_cache()
        cache_file = tmp_path / "extract_filters_cache.json"

        response_first = MagicMock()
        response_first.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }
        response_second = MagicMock()
        response_second.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".md"]}'}}]
        }

        with patch.object(LLMClient, "_EXTRACT_FILTERS_DISK_CACHE_FILE", cache_file):
            with patch("httpx.Client") as mock_client_class:
                mock_http_first = MagicMock()
                mock_http_first.post.return_value = response_first
                mock_http_second = MagicMock()
                mock_http_second.post.return_value = response_second
                mock_client_class.side_effect = [mock_http_first, mock_http_second]

                with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                    result_first = client.extract_filters("find Python files")
                assert result_first == '{"ext": [".py"]}'
                mock_http_first.post.assert_called_once()
                assert cache_file.exists()

                LLMClient.reset_extract_filters_cache()

                with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                    result_second = client.extract_filters("find Python files")
                assert result_second == '{"ext": [".py"]}'
                mock_http_second.post.assert_not_called()

    def test_extract_filters_malformed_disk_cache_falls_back_to_http(self, tmp_path: Path):
        """extract_filters should ignore malformed disk cache payloads."""
        LLMClient.reset_extract_filters_cache()
        cache_file = tmp_path / "extract_filters_cache.json"
        cache_file.write_text("{not-json", encoding="utf-8")

        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ext": [".py"]}'}}]
        }

        with patch.object(LLMClient, "_EXTRACT_FILTERS_DISK_CACHE_FILE", cache_file):
            with patch("httpx.Client") as mock_client_class:
                mock_http = MagicMock()
                mock_http.post.return_value = response
                mock_client_class.return_value = mock_http

                with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                    result = client.extract_filters("find Python files")

                assert result == '{"ext": [".py"]}'
                mock_http.post.assert_called_once()

    def test_extract_filters_cache_stats_prunes_expired_entries(self):
        LLMClient.reset_extract_filters_cache()
        with LLMClient._extract_filters_cache_lock:
            LLMClient._extract_filters_cache[("a", "m", "q1")] = (0.0, "expired")
            LLMClient._extract_filters_cache[("a", "m", "q2")] = (float("inf"), "alive")
            LLMClient._extract_filters_cache_hits = 2
            LLMClient._extract_filters_cache_misses = 3

        stats = LLMClient.extract_filters_cache_stats()

        assert stats["size"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 3

    def test_enforce_extract_filters_cache_size_locked_removes_oldest(self):
        LLMClient.reset_extract_filters_cache()
        with LLMClient._extract_filters_cache_lock:
            with patch.object(LLMClient, "_EXTRACT_FILTERS_CACHE_MAX_ENTRIES", 1):
                LLMClient._extract_filters_cache[("a", "m", "q1")] = (100.0, "first")
                LLMClient._extract_filters_cache[("a", "m", "q2")] = (200.0, "second")
                LLMClient._enforce_extract_filters_cache_size_locked()

        assert ("a", "m", "q1") not in LLMClient._extract_filters_cache
        assert ("a", "m", "q2") in LLMClient._extract_filters_cache

    def test_prune_disk_entries_handles_expiry_and_size_limit(self):
        entries: OrderedDict[str, dict[str, float | str]] = OrderedDict(
            [
                ("k1", {"content": "a", "created_at": 1.0, "expires_at": 1.0}),
                ("k2", {"content": "b", "created_at": 2.0, "expires_at": 999.0}),
                ("k3", {"content": "c", "created_at": 3.0, "expires_at": 999.0}),
            ]
        )

        with patch.object(LLMClient, "_EXTRACT_FILTERS_CACHE_MAX_ENTRIES", 1):
            changed = LLMClient._prune_extract_filters_disk_entries_locked(
                entries, now_wall=2.0
            )

        assert changed is True
        assert list(entries.keys()) == ["k3"]

    @pytest.mark.parametrize(
        "payload",
        [
            json.dumps(["not-a-dict"]),
            json.dumps({"version": 999, "entries": {}}),
            json.dumps({"version": 1, "entries": []}),
        ],
    )
    def test_load_disk_entries_rejects_invalid_payload_shapes(self, tmp_path: Path, payload: str):
        cache_file = tmp_path / "extract_filters_cache.json"
        cache_file.write_text(payload, encoding="utf-8")

        with patch.object(LLMClient, "_EXTRACT_FILTERS_DISK_CACHE_FILE", cache_file):
            entries, changed = LLMClient._load_extract_filters_disk_entries_locked(now_wall=0.0)

        assert entries == OrderedDict()
        assert changed is False

    def test_get_from_disk_cache_saves_when_pruned_payload_changed(self, tmp_path: Path):
        cache_file = tmp_path / "extract_filters_cache.json"
        cache_key = ("", "", "")
        serialized_key = LLMClient._serialize_extract_filters_cache_key(cache_key)
        payload = {
            "version": 1,
            "entries": {
                serialized_key: {
                    "content": "ok",
                    "created_at": 10.0,
                    "expires_at": 999.0,
                },
                "bad-shape": [],
                "bad-content": {
                    "content": 1,
                    "created_at": 1.0,
                    "expires_at": 999.0,
                },
                "bad-created": {
                    "content": "x",
                    "created_at": "nope",
                    "expires_at": 999.0,
                },
                "bad-expires": {
                    "content": "x",
                    "created_at": 1.0,
                    "expires_at": "nope",
                },
            },
        }
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        with patch.object(LLMClient, "_EXTRACT_FILTERS_DISK_CACHE_FILE", cache_file):
            value = LLMClient._get_extract_filters_from_disk_cache_locked(cache_key, now_wall=0.0)

        assert value == "ok"
        written = json.loads(cache_file.read_text(encoding="utf-8"))
        assert list(written["entries"].keys()) == [serialized_key]

    def test_rerank_success(self):
        """rerank should return ordered list of filenames."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "file2.txt\nfile1.txt"}}]
        }

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                result = client.rerank("test query", ["file1.txt", "file2.txt"])

            assert result == ["file2.txt", "file1.txt"]

    def test_rerank_filters_invalid_paths(self):
        """rerank should filter out paths not in original list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "invalid.txt\nfile1.txt\nfile2.txt"}}]
        }

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                result = client.rerank("test query", ["file1.txt", "file2.txt"])

            assert result == ["file1.txt", "file2.txt"]
            assert "invalid.txt" not in result

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"choices": []},
            {"choices": [{"message": {"content": ""}}]},
        ],
    )
    def test_rerank_invalid_response_schema_raises_controlled_error(self, payload):
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client_class.return_value = mock_http

            with LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4") as client:
                with pytest.raises(LLMResponseSchemaError):
                    client.rerank("test query", ["file1.txt"])

    def test_close_closes_http_client(self):
        """close() should close the HTTP client."""
        with patch("httpx.Client") as mock_client_class:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_http

            client = LLMClient(base_url="https://api.example.com", api_key="test-key", model="gpt-4")
            client.__enter__()
            client.close()

            mock_http.close.assert_called_once()
