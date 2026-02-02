"""Configuration management for askfind."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

import keyring


SERVICE_NAME = "askfind"
CONFIG_DIR = Path.home() / ".config" / "askfind"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def get_config_path() -> Path:
    return CONFIG_FILE


@dataclass
class Config:
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4o-mini"
    default_root: str = "."
    max_results: int = 50
    editor: str = "vim"

    @classmethod
    def from_file(cls, path: Path) -> Config:
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        kwargs = {}
        provider = data.get("provider", {})
        search = data.get("search", {})
        interactive = data.get("interactive", {})
        field_map = {
            "base_url": provider,
            "model": provider,
            "default_root": search,
            "max_results": search,
            "editor": interactive,
        }
        for field in fields(cls):
            source = field_map.get(field.name)
            if source and field.name in source:
                kwargs[field.name] = source[field.name]
        return cls(**kwargs)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "[provider]",
            f'base_url = "{self.base_url}"',
            f'model = "{self.model}"',
            "",
            "[search]",
            f'default_root = "{self.default_root}"',
            f"max_results = {self.max_results}",
            "",
            "[interactive]",
            f'editor = "{self.editor}"',
            "",
        ]
        path.write_text("\n".join(lines))


def get_api_key(cli_key: str | None = None, env_key: str | None = None) -> str | None:
    if cli_key:
        return cli_key
    env_val = env_key or os.environ.get("ASKFIND_API_KEY")
    if env_val:
        return env_val
    return keyring.get_password(SERVICE_NAME, "api_key")


def set_api_key(key: str) -> None:
    keyring.set_password(SERVICE_NAME, "api_key", key)
