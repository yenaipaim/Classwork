"""Statistics and metadata tools."""

from __future__ import annotations
from typing import Any


async def get_stats(rest_client: Any) -> dict:
    """获取医院经营统计：档案数、总收入、客单价、种类/医生排行等。"""
    return await rest_client.get("/api/v1/stats")


async def get_meta(rest_client: Any) -> dict:
    """获取枚举字典：种类列表、状态列表、字段说明等元数据。"""
    return await rest_client.get("/api/v1/meta")
