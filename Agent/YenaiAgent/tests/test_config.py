"""config.ini 读写测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import ConfigStore
from core.errors import ConfigError, ErrorCode


def test_load_missing_file_raises(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "absent.ini")
    assert store.exists() is False
    with pytest.raises(ConfigError) as excinfo:
        store.load()
    assert excinfo.value.code is ErrorCode.CONFIG_MISSING


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    store = ConfigStore(path)
    saved = store.save(" http://example.test/v1 ", " secret ", " model ")

    assert saved.base_url == "http://example.test/v1"
    assert saved.api_key == "secret"
    assert saved.model_name == "model"
    assert store.exists() is True
    assert store.load() == saved

    text = path.read_text(encoding="utf-8")
    assert "[llm]" in text
    assert "base_url = http://example.test/v1" in text


def test_save_rejects_blank_values(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.ini")
    with pytest.raises(ConfigError) as excinfo:
        store.save("http://example.test/v1", "  ", "model")
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID
    assert "API 密钥" in excinfo.value.detail


def test_load_rejects_missing_section(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text("[other]\nkey = value\n", encoding="utf-8")
    store = ConfigStore(path)
    assert store.exists() is False
    with pytest.raises(ConfigError) as excinfo:
        store.load()
    assert excinfo.value.code is ErrorCode.CONFIG_INVALID


def test_load_rejects_empty_required_key(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text(
        "[llm]\nbase_url = http://x\napi_key =\nmodel_name = m\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as excinfo:
        ConfigStore(path).load()
    assert "API 密钥" in excinfo.value.detail