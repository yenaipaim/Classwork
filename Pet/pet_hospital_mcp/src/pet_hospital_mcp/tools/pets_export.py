"""Export tool."""

from __future__ import annotations
from typing import Any


async def export_data(rest_client: Any, *, format: str = "json") -> dict:
    """导出全部宠物数据。format支持json或csv。"""
    return await rest_client.get("/api/v1/export", params={"format": format})
