"""MCP server with all 28 tools (Chinese names) for the Pet Hospital API."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Config
from .rest_client import PetHospitalClient

logger = logging.getLogger(__name__)

mcp = MCPServer("PetHospitalMCP", version="0.3.0")


def create_mcp_server(config: Config) -> MCPServer:
    rest_client = PetHospitalClient(config)

    # ── 档案查询 ──────────────────────────────────────────────────
    @mcp.tool(name="查询宠物列表")
    async def list_pets(
        q: str | None = None, name: str | None = None,
        ownerName: str | None = None, ownerPhone: str | None = None,
        species: str | None = None, doctor: str | None = None,
        disease: str | None = None, status: str | None = None,
        min: float | None = None, max: float | None = None,
        sortBy: str | None = None, order: str | None = None,
        page: int = 1, pageSize: int = 20,
    ) -> dict[str, Any]:
        """查询宠物医院档案列表。支持关键词搜索、按种类/医生/状态/费用等筛选、排序和分页。"""
        from .tools.list_pets import list_pets as _lp
        kwargs: dict[str, Any] = {"page": page, "pageSize": pageSize}
        for k, v in {"q": q, "name": name, "ownerName": ownerName, "ownerPhone": ownerPhone,
                      "species": species, "doctor": doctor, "disease": disease, "status": status,
                      "min": min, "max": max, "sortBy": sortBy, "order": order}.items():
            if v is not None:
                kwargs[k] = v
        return await _lp(rest_client, **kwargs)

    # ── 增删改查 ──────────────────────────────────────────────────
    @mcp.tool(name="获取宠物详情")
    async def get_pet(pet_id: str) -> dict[str, Any]:
        """根据ID获取单个宠物档案的完整信息（含病历和收费明细）。"""
        from .tools.pets_crud import get_pet as _f
        return await _f(rest_client, pet_id=pet_id)

    @mcp.tool(name="新增宠物")
    async def create_pet(
        name: str, species: str, ownerName: str, ownerPhone: str,
        doctor: str, disease: str, status: str = "待就诊",
        breed: str | None = None, gender: str | None = None,
        ageMonths: int | None = None, color: str | None = None,
        chipNo: str | None = None, ownerAddr: str | None = None,
        allergy: str | None = None, note: str | None = None,
    ) -> dict[str, Any]:
        """在宠物医院新增一条宠物档案。id自动生成。"""
        from .tools.pets_crud import create_pet as _f
        return await _f(rest_client, name=name, species=species, ownerName=ownerName,
                        ownerPhone=ownerPhone, doctor=doctor, disease=disease, status=status,
                        breed=breed, gender=gender, ageMonths=ageMonths, color=color,
                        chipNo=chipNo, ownerAddr=ownerAddr, allergy=allergy, note=note)

    @mcp.tool(name="全量更新宠物")
    async def update_pet(
        pet_id: str, name: str, species: str, ownerName: str, ownerPhone: str,
        doctor: str, disease: str, status: str,
        breed: str | None = None, gender: str | None = None,
        ageMonths: int | None = None, color: str | None = None,
        chipNo: str | None = None, ownerAddr: str | None = None,
        allergy: str | None = None, note: str | None = None,
    ) -> dict[str, Any]:
        """全量更新宠物档案。未传字段会被清空，仅改部分字段请用局部更新。"""
        from .tools.pets_crud import update_pet as _f
        return await _f(rest_client, pet_id=pet_id, name=name, species=species,
                        ownerName=ownerName, ownerPhone=ownerPhone, doctor=doctor,
                        disease=disease, status=status, breed=breed, gender=gender,
                        ageMonths=ageMonths, color=color, chipNo=chipNo,
                        ownerAddr=ownerAddr, allergy=allergy, note=note)

    @mcp.tool(name="局部更新宠物")
    async def patch_pet(
        pet_id: str,
        name: str | None = None, species: str | None = None,
        ownerName: str | None = None, ownerPhone: str | None = None,
        doctor: str | None = None, disease: str | None = None,
        status: str | None = None, breed: str | None = None,
        gender: str | None = None, ageMonths: int | None = None,
        color: str | None = None, chipNo: str | None = None,
        ownerAddr: str | None = None, allergy: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """局部更新宠物档案，只改传入的字段，其余保持不变。"""
        from .tools.pets_crud import patch_pet as _f
        kwargs: dict[str, Any] = {"pet_id": pet_id}
        for k, v in {"name": name, "species": species, "ownerName": ownerName,
                      "ownerPhone": ownerPhone, "doctor": doctor, "disease": disease,
                      "status": status, "breed": breed, "gender": gender,
                      "ageMonths": ageMonths, "color": color, "chipNo": chipNo,
                      "ownerAddr": ownerAddr, "allergy": allergy, "note": note}.items():
            if v is not None:
                kwargs[k] = v
        return await _f(rest_client, **kwargs)

    @mcp.tool(name="删除宠物")
    async def delete_pet(pet_id: str) -> dict[str, Any]:
        """删除一条宠物档案，操作不可逆。"""
        from .tools.pets_crud import delete_pet as _f
        return await _f(rest_client, pet_id=pet_id)

    # ── 高级查询 ──────────────────────────────────────────────────
    @mcp.tool(name="全文搜索")
    async def search_pets(q: str) -> dict[str, Any]:
        """全文检索宠物档案（跨字段，空格分词AND，含病历全文）。"""
        from .tools.pets_query import search_pets as _f
        return await _f(rest_client, q=q)

    @mcp.tool(name="按主人查询")
    async def get_pets_by_owner(ownerName: str, phone: str | None = None) -> dict[str, Any]:
        """按主人姓名查询宠物，可附加电话过滤。"""
        from .tools.pets_query import get_pets_by_owner as _f
        return await _f(rest_client, ownerName=ownerName, phone=phone)

    @mcp.tool(name="按医生查询")
    async def get_pets_by_doctor(doctor: str) -> dict[str, Any]:
        """按主治医生查询宠物列表。"""
        from .tools.pets_query import get_pets_by_doctor as _f
        return await _f(rest_client, doctor=doctor)

    @mcp.tool(name="按种类查询")
    async def get_pets_by_species(species: str) -> dict[str, Any]:
        """按种类查询宠物（犬/猫/兔/鸟/仓鼠/爬宠/其他）。"""
        from .tools.pets_query import get_pets_by_species as _f
        return await _f(rest_client, species=species)

    @mcp.tool(name="按疾病查询")
    async def get_pets_by_disease(disease: str) -> dict[str, Any]:
        """按疾病名称查询宠物。"""
        from .tools.pets_query import get_pets_by_disease as _f
        return await _f(rest_client, disease=disease)

    @mcp.tool(name="按状态查询")
    async def get_pets_by_status(status: str) -> dict[str, Any]:
        """按就诊状态查询（待就诊/就诊中/住院中/已康复/慢性病随访）。"""
        from .tools.pets_query import get_pets_by_status as _f
        return await _f(rest_client, status=status)

    @mcp.tool(name="消费排行榜")
    async def get_top_spenders(limit: int = 10) -> dict[str, Any]:
        """获取消费排行前N名的宠物。"""
        from .tools.pets_query import get_top_spenders as _f
        return await _f(rest_client, limit=limit)

    @mcp.tool(name="按花费区间查询")
    async def get_pets_by_cost_range(min: float = 0, max: float = 999999) -> dict[str, Any]:
        """按总花费区间查询宠物。"""
        from .tools.pets_query import get_pets_by_cost_range as _f
        return await _f(rest_client, min=min, max=max)

    # ── 病历管理 ──────────────────────────────────────────────────
    @mcp.tool(name="查看病历")
    async def get_pet_records(pet_id: str) -> dict[str, Any]:
        """查看某只宠物的历史病历列表。"""
        from .tools.pets_records import get_pet_records as _f
        return await _f(rest_client, pet_id=pet_id)

    @mcp.tool(name="添加病历")
    async def add_pet_record(
        pet_id: str, doctor: str, diagnosis: str,
        symptoms: str | None = None, treatment: str | None = None,
        prescription: list[str] | None = None, weightKg: float | None = None,
        temperature: float | None = None, followUp: str | None = None,
        charge: float | None = None,
    ) -> dict[str, Any]:
        """为某只宠物追加一条就诊病历。"""
        from .tools.pets_records import add_pet_record as _f
        return await _f(rest_client, pet_id=pet_id, doctor=doctor, diagnosis=diagnosis,
                        symptoms=symptoms, treatment=treatment, prescription=prescription,
                        weightKg=weightKg, temperature=temperature, followUp=followUp,
                        charge=charge)

    # ── 收费管理 ──────────────────────────────────────────────────
    @mcp.tool(name="查看收费明细")
    async def get_pet_charges(pet_id: str) -> dict[str, Any]:
        """查看某只宠物的消费明细列表。"""
        from .tools.pets_charges import get_pet_charges as _f
        return await _f(rest_client, pet_id=pet_id)

    @mcp.tool(name="添加收费")
    async def add_pet_charge(
        pet_id: str, item: str, category: str, amount: float,
        doctor: str | None = None, date: str | None = None,
    ) -> dict[str, Any]:
        """为某只宠物追加一笔收费记录，总花费自动累计。"""
        from .tools.pets_charges import add_pet_charge as _f
        return await _f(rest_client, pet_id=pet_id, item=item, category=category,
                        amount=amount, doctor=doctor, date=date)

    @mcp.tool(name="费用汇总")
    async def get_pet_summary(pet_id: str) -> dict[str, Any]:
        """查看某只宠物的费用与就诊汇总。"""
        from .tools.pets_charges import get_pet_summary as _f
        return await _f(rest_client, pet_id=pet_id)

    # ── 统计 ──────────────────────────────────────────────────────
    @mcp.tool(name="经营统计")
    async def get_stats() -> dict[str, Any]:
        """获取医院经营统计：档案数、总收入、客单价、种类/医生排行等。"""
        from .tools.pets_stats import get_stats as _f
        return await _f(rest_client)

    @mcp.tool(name="元数据字典")
    async def get_meta() -> dict[str, Any]:
        """获取枚举字典：种类列表、状态列表、字段说明等元数据。"""
        from .tools.pets_stats import get_meta as _f
        return await _f(rest_client)

    # ── 管理 ──────────────────────────────────────────────────────
    @mcp.tool(name="批量新增")
    async def batch_create_pets(pets: list[dict[str, Any]]) -> dict[str, Any]:
        """批量新增宠物档案，传入宠物记录对象数组。"""
        from .tools.pets_admin import batch_create_pets as _f
        return await _f(rest_client, pets=pets)

    @mcp.tool(name="批量删除")
    async def batch_delete_pets(ids: list[str]) -> dict[str, Any]:
        """批量删除宠物档案，传入id列表。操作不可逆。"""
        from .tools.pets_admin import batch_delete_pets as _f
        return await _f(rest_client, ids=ids)

    @mcp.tool(name="导出数据")
    async def export_data(format: str = "json") -> dict[str, Any]:
        """导出全部宠物数据。format支持json或csv。"""
        from .tools.pets_export import export_data as _f
        return await _f(rest_client, format=format)

    @mcp.tool(name="压实数据库")
    async def compact_database() -> dict[str, Any]:
        """手动压实数据库文件，回收垃圾空间。一般无需手动调用。"""
        from .tools.pets_admin import compact_database as _f
        return await _f(rest_client)

    @mcp.tool(name="生成模拟数据")
    async def seed_data(count: int = 8, force: bool = False) -> dict[str, Any]:
        """写入模拟数据。force=true追加写入，count=all写入1000条。仅开发用。"""
        from .tools.pets_admin import seed_data as _f
        return await _f(rest_client, count=count, force=force)

    @mcp.tool(name="接口清单")
    async def get_endpoints() -> dict[str, Any]:
        """获取全部API接口清单（JSON，机器可读）。"""
        from .tools.pets_admin import get_endpoints as _f
        return await _f(rest_client)

    @mcp.tool(name="健康检查")
    async def check_health() -> dict[str, Any]:
        """检查Go后端服务健康状态。"""
        from .tools.pets_admin import health_check as _f
        return await _f(rest_client)

    # ── Health route ──────────────────────────────────────────────
    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        try:
            backend_health = await rest_client.health_check()
            return JSONResponse({"status": "healthy", "backend": backend_health})
        except Exception as e:
            return JSONResponse({"status": "degraded", "backend": {"status": "unavailable", "error": str(e)}})

    return mcp
