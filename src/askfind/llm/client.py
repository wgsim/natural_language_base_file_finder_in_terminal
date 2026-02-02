"""OpenAI-compatible LLM HTTP client."""

from __future__ import annotations

import httpx

from askfind.llm.prompt import build_system_prompt


class LLMClient:
    """Client for OpenAI-compatible chat completion APIs."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def extract_filters(self, query: str) -> str:
        """Send query to LLM and return raw response text."""
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def rerank(self, query: str, file_list: list[str]) -> list[str]:
        """Send file list to LLM for semantic re-ranking. Returns ordered list."""
        file_text = "\n".join(file_list)
        prompt = (
            f"Given the query: \"{query}\"\n\n"
            f"Rank these files by relevance (most relevant first). "
            f"Return ONLY the file paths, one per line, no numbering:\n\n{file_text}"
        )
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        ranked = [line.strip() for line in content.splitlines() if line.strip()]
        # Only return paths that were in the original list
        valid = set(file_list)
        return [p for p in ranked if p in valid]

    def close(self) -> None:
        self._http.close()
