"""Medical records tools."""

from __future__ import annotations
from typing import Any


async def get_pet_records(rest_client: Any, *, pet_id: str) -> dict:
    """查看某只宠物的历史病历列表。"""
    return await rest_client.get(f"/api/v1/pets/{pet_id}/records")


async def add_pet_record(
    rest_client: Any,
    *,
    pet_id: str,
    doctor: str,
    diagnosis: str,
    symptoms: str | None = None,
    treatment: str | None = None,
    prescription: list[str] | None = None,
    weightKg: float | None = None,
    temperature: float | None = None,
    followUp: str | None = None,
    charge: float | None = None,
) -> dict:
    """为某只宠物追加一条就诊病历。"""
    body: dict[str, Any] = {"doctor": doctor, "diagnosis": diagnosis}
    for k, v in {"symptoms": symptoms, "treatment": treatment,
                  "prescription": prescription, "weightKg": weightKg,
                  "temperature": temperature, "followUp": followUp,
                  "charge": charge}.items():
        if v is not None:
            body[k] = v
    return await rest_client.post(f"/api/v1/pets/{pet_id}/records", json_body=body)
