"""Entry point for running the pet hospital MCP service."""

from __future__ import annotations

import sys

from .config import load_config
from .logging_config import setup_logging
from .server import create_mcp_server


def main() -> None:
    """Start the MCP server."""
    config = load_config()
    setup_logging()

    mcp = create_mcp_server(config)

    # 判断启动模式：--stdio 用stdio模式，默认用 streamable-http
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        import uvicorn

        app = mcp.streamable_http_app()
        print(f"MCP 服务启动中... http://{config.mcp_host}:{config.mcp_port}/mcp")
        uvicorn.run(
            app,
            host=config.mcp_host,
            port=config.mcp_port,
            log_level="info",
        )


if __name__ == "__main__":
    main()
