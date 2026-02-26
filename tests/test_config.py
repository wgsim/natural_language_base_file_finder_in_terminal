"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

from askfind.config import Config, get_api_key, get_config_path


class TestGetConfigPath:
    def test_default_path(self):
        path = get_config_path()
        assert path == Path.home() / ".config" / "askfind" / "config.toml"


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.model == "openai/gpt-4o-mini"
        assert config.default_root == "."
        assert config.max_results == 50
        assert config.respect_ignore_files is True
        assert config.follow_symlinks is False
        assert config.exclude_binary_files is True
        assert config.editor == "vim"

    def test_from_toml_string(self, tmp_path):
        toml_content = b'[provider]\nbase_url = "http://localhost:11434/v1"\nmodel = "llama3"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = Config.from_file(config_file)
        assert config.base_url == "http://localhost:11434/v1"
        assert config.model == "llama3"

    def test_from_missing_file_returns_defaults(self, tmp_path):
        config = Config.from_file(tmp_path / "nonexistent.toml")
        assert config.base_url == "https://openrouter.ai/api/v1"

    def test_partial_toml_merges_with_defaults(self, tmp_path):
        toml_content = b'[provider]\nmodel = "gpt-4o"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)
        config = Config.from_file(config_file)
        assert config.model == "gpt-4o"
        assert config.base_url == "https://openrouter.ai/api/v1"  # default preserved

    def test_save_and_reload(self, tmp_path):
        config = Config(
            model="custom-model",
            respect_ignore_files=False,
            follow_symlinks=True,
            exclude_binary_files=False,
            editor="nano",
        )
        config_file = tmp_path / "config.toml"
        config.save(config_file)
        reloaded = Config.from_file(config_file)
        assert reloaded.model == "custom-model"
        assert reloaded.respect_ignore_files is False
        assert reloaded.follow_symlinks is True
        assert reloaded.exclude_binary_files is False
        assert reloaded.editor == "nano"

    def test_invalid_respect_ignore_files_type_falls_back_to_default(self, tmp_path):
        toml_content = b'[search]\nrespect_ignore_files = "yes"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)

        config = Config.from_file(config_file)
        assert config.respect_ignore_files is True

    def test_invalid_follow_symlinks_type_falls_back_to_default(self, tmp_path):
        toml_content = b'[search]\nfollow_symlinks = "yes"\nexclude_binary_files = "no"\n'
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(toml_content)

        config = Config.from_file(config_file)
        assert config.follow_symlinks is False
        assert config.exclude_binary_files is True


class TestGetApiKey:
    def test_cli_flag_takes_priority(self):
        key = get_api_key(cli_key="sk-cli")
        assert key == "sk-cli"

    @patch.dict(os.environ, {"ASKFIND_API_KEY": "sk-env"})
    def test_env_var_fallback(self):
        key = get_api_key(cli_key=None)
        assert key == "sk-env"

    @patch("askfind.config.keyring")
    def test_keychain_fallback(self, mock_keyring):
        mock_keyring.get_password.return_value = "sk-keychain"
        with patch.dict(os.environ, {}, clear=True):
            # Remove ASKFIND_API_KEY if present
            os.environ.pop("ASKFIND_API_KEY", None)
            key = get_api_key(cli_key=None)
        assert key == "sk-keychain"

    @patch("askfind.config.keyring")
    def test_no_key_returns_none(self, mock_keyring):
        mock_keyring.get_password.return_value = None
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASKFIND_API_KEY", None)
            key = get_api_key(cli_key=None)
        assert key is None
