"""Advanced query tools: search, by-owner, by-doctor, etc."""

from __future__ import annotations
from typing import Any


async def search_pets(rest_client: Any, *, q: str) -> dict:
    """全文检索宠物档案（跨字段，空格分词AND，含病历全文）。"""
    return await rest_client.get("/api/v1/pets/search", params={"q": q})


async def get_pets_by_owner(rest_client: Any, *, ownerName: str, phone: str | None = None) -> dict:
    """按主人姓名查询宠物，可附加电话过滤。"""
    params: dict[str, Any] = {"ownerName": ownerName}
    if phone:
        params["phone"] = phone
    return await rest_client.get("/api/v1/pets/by-owner", params=params)


async def get_pets_by_doctor(rest_client: Any, *, doctor: str) -> dict:
    """按主治医生查询宠物列表。"""
    return await rest_client.get("/api/v1/pets/by-doctor", params={"doctor": doctor})


async def get_pets_by_species(rest_client: Any, *, species: str) -> dict:
    """按种类查询宠物（犬/猫/兔/鸟/仓鼠/爬宠/其他）。"""
    return await rest_client.get("/api/v1/pets/by-species", params={"species": species})


async def get_pets_by_disease(rest_client: Any, *, disease: str) -> dict:
    """按疾病名称查询宠物。"""
    return await rest_client.get("/api/v1/pets/by-disease", params={"disease": disease})


async def get_pets_by_status(rest_client: Any, *, status: str) -> dict:
    """按就诊状态查询（待就诊/就诊中/住院中/已康复/慢性病随访）。"""
    return await rest_client.get("/api/v1/pets/by-status", params={"status": status})


async def get_top_spenders(rest_client: Any, *, limit: int = 10) -> dict:
    """获取消费排行前N名的宠物。"""
    return await rest_client.get("/api/v1/pets/top-spenders", params={"limit": limit})


async def get_pets_by_cost_range(rest_client: Any, *, min: float = 0, max: float = 999999) -> dict:
    """按总花费区间查询宠物。"""
    return await rest_client.get("/api/v1/pets/cost-range", params={"min": min, "max": max})
