"""终端界面层：只依赖 core 的事件与工厂，不复制任何业务逻辑。"""

from .app import YenaiApp

__all__ = ["YenaiApp"]