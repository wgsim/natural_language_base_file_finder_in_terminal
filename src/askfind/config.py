"""Configuration management for askfind."""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import keyring
import tomli_w


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
        # Create config directory with restrictive permissions (700)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Use tomli_w for safe TOML serialization
        config_dict = {
            "provider": {
                "base_url": self.base_url,
                "model": self.model,
            },
            "search": {
                "default_root": self.default_root,
                "max_results": self.max_results,
            },
            "interactive": {
                "editor": self.editor,
            },
        }

        with open(path, "wb") as f:
            tomli_w.dump(config_dict, f)

        # Set restrictive file permissions (600 - owner read/write only)
        path.chmod(0o600)


def get_api_key(cli_key: str | None = None, env_var: str = "ASKFIND_API_KEY") -> str | None:
    """Get API key from CLI arg, environment variable, or keyring (in that order).

    Args:
        cli_key: API key passed via CLI argument (highest priority)
        env_var: Name of environment variable to check (default: ASKFIND_API_KEY)

    Returns:
        API key string or None if not found
    """
    if cli_key:
        return cli_key
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val
    return keyring.get_password(SERVICE_NAME, "api_key")


def set_api_key(key: str) -> None:
    keyring.set_password(SERVICE_NAME, "api_key", key)
