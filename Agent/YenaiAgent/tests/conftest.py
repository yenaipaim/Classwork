"""测试夹具：保证能直接 import core / tui，并提供临时目录下的会话。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig  # noqa: E402
from core.factory import build_registry  # noqa: E402
from core.session import AgentSession  # noqa: E402
from core.transcript import Transcript  # noqa: E402

from support import FakeBackend  # noqa: E402


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(base_url="http://example.test/v1", api_key="test-key", model_name="test-model")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def history_dir(tmp_path: Path) -> Path:
    return tmp_path / "chat_history"


@pytest.fixture
def make_session(config, workspace, history_dir):
    def factory(backend=None, *, config=config) -> AgentSession:
        # 与 create_session 一致：注入注册表工厂，支持切换工作区
        def registry_factory(root):
            return build_registry(root)

        return AgentSession(
            backend or FakeBackend(),
            registry_factory(workspace),
            config,
            Transcript(history_dir, config.model_name),
            registry_factory=registry_factory,
        )

    return factory