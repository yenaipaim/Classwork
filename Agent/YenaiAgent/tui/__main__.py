"""命令行入口：``python -m tui`` 或安装后的 ``yenai``。"""

from __future__ import annotations

import argparse

from core.paths import DEFAULT_CONFIG_PATH, DEFAULT_HISTORY_DIR, DEFAULT_WORKSPACE_ROOT

from .app import YenaiApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yenai", description="YenaiAgent 终端界面")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径")
    parser.add_argument(
        "--history-dir", default=str(DEFAULT_HISTORY_DIR), help="对话存档目录"
    )
    parser.add_argument(
        "--workspace", default=str(DEFAULT_WORKSPACE_ROOT), help="文件工具沙箱根目录"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = YenaiApp(
        config_path=args.config,
        history_dir=args.history_dir,
        workspace_root=args.workspace,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())