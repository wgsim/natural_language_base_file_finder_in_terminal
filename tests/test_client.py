"""Tests for LLM client."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from askfind.llm.client import LLMClient


class TestLLMClient:
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
