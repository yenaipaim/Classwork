"""Pet CRUD tools: get, create, update, patch, delete."""

from __future__ import annotations
from typing import Any


async def get_pet(rest_client: Any, *, pet_id: str) -> dict:
    """根据ID获取单个宠物档案的完整信息（含病历和收费明细）。"""
    return await rest_client.get(f"/api/v1/pets/{pet_id}")


async def create_pet(
    rest_client: Any,
    *,
    name: str,
    species: str,
    ownerName: str,
    ownerPhone: str,
    doctor: str,
    disease: str,
    status: str = "待就诊",
    breed: str | None = None,
    gender: str | None = None,
    ageMonths: int | None = None,
    color: str | None = None,
    chipNo: str | None = None,
    ownerAddr: str | None = None,
    allergy: str | None = None,
    note: str | None = None,
) -> dict:
    """在宠物医院新增一条宠物档案。id自动生成，status默认待就诊。"""
    body: dict[str, Any] = {
        "name": name, "species": species, "ownerName": ownerName,
        "ownerPhone": ownerPhone, "doctor": doctor, "disease": disease,
        "status": status,
    }
    for k, v in {"breed": breed, "gender": gender, "ageMonths": ageMonths,
                  "color": color, "chipNo": chipNo, "ownerAddr": ownerAddr,
                  "allergy": allergy, "note": note}.items():
        if v is not None:
            body[k] = v
    return await rest_client.post("/api/v1/pets", json_body=body)


async def update_pet(
    rest_client: Any,
    *,
    pet_id: str,
    name: str,
    species: str,
    ownerName: str,
    ownerPhone: str,
    doctor: str,
    disease: str,
    status: str,
    breed: str | None = None,
    gender: str | None = None,
    ageMonths: int | None = None,
    color: str | None = None,
    chipNo: str | None = None,
    ownerAddr: str | None = None,
    allergy: str | None = None,
    note: str | None = None,
) -> dict:
    """全量更新宠物档案。未传的字段会被清空，仅改部分字段请用patch_pet。"""
    body: dict[str, Any] = {
        "name": name, "species": species, "ownerName": ownerName,
        "ownerPhone": ownerPhone, "doctor": doctor, "disease": disease,
        "status": status,
    }
    for k, v in {"breed": breed, "gender": gender, "ageMonths": ageMonths,
                  "color": color, "chipNo": chipNo, "ownerAddr": ownerAddr,
                  "allergy": allergy, "note": note}.items():
        body[k] = v  # PUT intentionally clears unset fields
    return await rest_client.put(f"/api/v1/pets/{pet_id}", json_body=body)


async def patch_pet(
    rest_client: Any,
    *,
    pet_id: str,
    name: str | None = None,
    species: str | None = None,
    ownerName: str | None = None,
    ownerPhone: str | None = None,
    doctor: str | None = None,
    disease: str | None = None,
    status: str | None = None,
    breed: str | None = None,
    gender: str | None = None,
    ageMonths: int | None = None,
    color: str | None = None,
    chipNo: str | None = None,
    ownerAddr: str | None = None,
    allergy: str | None = None,
    note: str | None = None,
) -> dict:
    """局部更新宠物档案，只改传入的字段，未传的保持不变。"""
    body: dict[str, Any] = {}
    for k, v in {"name": name, "species": species, "ownerName": ownerName,
                  "ownerPhone": ownerPhone, "doctor": doctor, "disease": disease,
                  "status": status, "breed": breed, "gender": gender,
                  "ageMonths": ageMonths, "color": color, "chipNo": chipNo,
                  "ownerAddr": ownerAddr, "allergy": allergy, "note": note}.items():
        if v is not None:
            body[k] = v
    return await rest_client.patch(f"/api/v1/pets/{pet_id}", json_body=body)


async def delete_pet(rest_client: Any, *, pet_id: str) -> dict:
    """删除一条宠物档案，操作不可逆。"""
    return await rest_client.delete(f"/api/v1/pets/{pet_id}")
