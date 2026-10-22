"""YenaiAgent 启动入口。

保留 ``python main.py`` 的习惯用法，真正的实现都在 core / tui 两个包内。
"""

from __future__ import annotations

import sys

from tui.__main__ import main

if __name__ == "__main__":
    sys.exit(main())