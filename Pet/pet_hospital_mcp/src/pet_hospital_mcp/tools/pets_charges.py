"""Charges/billing tools."""

from __future__ import annotations
from typing import Any


async def get_pet_charges(rest_client: Any, *, pet_id: str) -> dict:
    """查看某只宠物的消费明细列表。"""
    return await rest_client.get(f"/api/v1/pets/{pet_id}/charges")


async def add_pet_charge(
    rest_client: Any,
    *,
    pet_id: str,
    item: str,
    category: str,
    amount: float,
    doctor: str | None = None,
    date: str | None = None,
) -> dict:
    """为某只宠物追加一笔收费记录，总花费会自动累计。"""
    body: dict[str, Any] = {"item": item, "category": category, "amount": amount}
    if doctor:
        body["doctor"] = doctor
    if date:
        body["date"] = date
    return await rest_client.post(f"/api/v1/pets/{pet_id}/charges", json_body=body)


async def get_pet_summary(rest_client: Any, *, pet_id: str) -> dict:
    """查看某只宠物的费用与就诊汇总（总花费、就诊次数等）。"""
    return await rest_client.get(f"/api/v1/pets/{pet_id}/summary")
