"""Admin and system tools."""

from __future__ import annotations
from typing import Any


async def batch_create_pets(rest_client: Any, *, pets: list[dict[str, Any]]) -> dict:
    """批量新增宠物档案。每个元素为一条宠物记录的字段对象。"""
    return await rest_client.post("/api/v1/pets/batch", json_body=pets)


async def batch_delete_pets(rest_client: Any, *, ids: list[str]) -> dict:
    """批量删除宠物档案，传入id列表。操作不可逆。"""
    return await rest_client.post("/api/v1/pets/batch-delete", json_body=ids)


async def compact_database(rest_client: Any) -> dict:
    """手动压实数据库文件，回收垃圾空间。一般无需手动调用。"""
    return await rest_client.post("/api/v1/admin/compact")


async def seed_data(rest_client: Any, *, count: int = 8, force: bool = False) -> dict:
    """写入模拟数据。force=true时追加，count=all写入1000条。仅开发用。"""
    params: dict[str, Any] = {"count": count, "force": force}
    return await rest_client.post("/api/v1/admin/seed", json_body=params)


async def get_endpoints(rest_client: Any) -> dict:
    """获取全部API接口清单（JSON机器可读）。"""
    return await rest_client.get("/api/v1/endpoints")


async def health_check(rest_client: Any) -> dict:
    """检查Go后端服务健康状态。"""
    return await rest_client.get("/health")
