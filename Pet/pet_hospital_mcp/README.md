# Pet Hospital MCP Service

A Model Context Protocol (MCP) service that exposes the Go Pet Hospital REST API to AI
agents. It is the bridge used by the Pet web chat UI: the model calls a Chinese-named
MCP tool, the service translates it into a REST request, and returns the result as
structured JSON.

## Overview

- **SDK**: `mcp` 2.x (`MCPServer`, requires Python 3.10+)
- **Transport**: Streamable HTTP through `uvicorn` (default `127.0.0.1:9000/mcp`)
- **Tools**: 28 Chinese-named tools covering the whole REST surface
- **Health check**: `GET /health` (proxies the Go service health)

## Prerequisites

1. **Go Pet Hospital service** must be running first:
   ```bash
   cd ../windows
   pethospital.exe        # http://127.0.0.1:8080
   ```
2. **Python 3.10+**

## Installation

```bash
cd Pet/pet_hospital_mcp

# Editable install with dev dependencies (pytest, respx)
pip install -e ".[dev]"
```

The official launcher `Pet/mcp_launcher.py` puts `src/` on `sys.path`, so an editable
install is only needed when running the package directly or running the tests.

## Configuration

All settings come from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API address |
| `MCP_HOST` | `127.0.0.1` | MCP server listen host |
| `MCP_PORT` | `9000` | MCP server listen port |
| `HTTP_TIMEOUT` | `30.0` | HTTP client timeout (seconds) |
| `MAX_RETRIES` | `2` | Max retries for backend calls |

## Running

```bash
# Start the MCP server (streamable HTTP)
python -m pet_hospital_mcp

# Custom port
MCP_PORT=9001 python -m pet_hospital_mcp

# Stdio transport (for clients that spawn the server)
python -m pet_hospital_mcp --stdio
```

From the `Pet/` directory you can also use the bundled launcher:

```bash
python mcp_launcher.py
```

The endpoint is `http://127.0.0.1:9000/mcp`; the startup log prints the final address.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   AI Web Chat   │────▶│  MCP Service     │────▶│  Go REST API    │
│  (browser)      │◀────│  (Python)        │◀────│  (Port 8080)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                         Port 9000 /mcp
```

## Tools (28)

| Category | Tools |
|----------|-------|
| Records (档案) | 查询宠物列表 · 获取宠物详情 · 新增宠物 · 全量更新宠物 · 局部更新宠物 · 删除宠物 |
| Queries (查询) | 全文搜索 · 按主人查询 · 按医生查询 · 按种类查询 · 按疾病查询 · 按状态查询 · 消费排行榜 · 按花费区间查询 |
| Medical & charges (病历/收费) | 查看病历 · 添加病历 · 查看收费明细 · 添加收费 · 费用汇总 |
| Statistics (统计) | 经营统计 · 元数据字典 |
| Admin (管理) | 批量新增 · 批量删除 · 导出数据 · 压实数据库 · 生成模拟数据 · 接口清单 · 健康检查 |

Tool implementations live in `src/pet_hospital_mcp/tools/` (one module per category);
`server.py` registers them with `@mcp.tool(name="中文名")` and delegates to the
`rest_client` helpers.

### Example: `查询宠物列表`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Full-text search across all fields |
| `name` | string | No | Partial match on pet name |
| `ownerName` | string | No | Partial match on owner name |
| `ownerPhone` | string | No | Partial match on owner phone |
| `species` | string | No | 犬/猫/兔/鸟/仓鼠/爬宠/其他 |
| `doctor` | string | No | Attending doctor |
| `disease` | string | No | Disease / diagnosis |
| `status` | string | No | 待就诊/就诊中/住院中/已康复/慢性病随访 |
| `min` / `max` | number | No | Total-cost range (legal integers, `max >= min`) |
| `sortBy` | string | No | id/name/ownerName/species/doctor/disease/status/totalCost/visitCount/createdAt/updatedAt |
| `order` | string | No | asc / desc |
| `page` | integer | No | 1-based page number (default 1) |
| `pageSize` | integer | No | Page size (default 20, 1–500) |

## Health Check

```bash
curl http://127.0.0.1:9000/health
```

```json
{
  "status": "healthy",
  "backend": { "status": "healthy", "petCount": 1008 }
}
```

`/health` is a custom route registered on the MCP app; it also checks the Go backend.

## Project Structure

```text
pet_hospital_mcp/
├── pyproject.toml
├── README.md
├── src/pet_hospital_mcp/
│   ├── __main__.py       # CLI entry: streamable-http (default) or --stdio
│   ├── server.py         # MCPServer("PetHospitalMCP"), 28 tool registrations, /health
│   ├── config.py         # env-var configuration
│   ├── rest_client.py    # HTTP client for the Go API
│   ├── errors.py         # ErrorCode / ErrorDetail / PetHospitalError
│   ├── logging_config.py # logging setup (sensitive fields masked)
│   └── tools/            # one module per category
└── tests/                # pytest + respx, no network required
```

## Testing

```bash
cd Pet/pet_hospital_mcp
pytest -q
```

Current status with the installed SDK: **78 passed, 5 failed, 7 skipped**. The failing
cases are registration/description assertions written before the service grew from a
single `list_pets` tool to 28 tools; they are being updated to the new tool set. The
rest of the suite (list/query/CRUD/errors/logging) runs offline against mocked HTTP.

## Error Handling

All tool errors follow one envelope:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

Codes: `VALIDATION_ERROR`, `BACKEND_TIMEOUT`, `BACKEND_UNAVAILABLE`,
`BACKEND_API_ERROR`, `BACKEND_INVALID_RESPONSE`, `INTERNAL_ERROR`.

## Security Notes

- Local/development use only: no authentication, no CORS policy.
- Sensitive fields (phone, address, chip number) are masked in logs.
- Listens on `127.0.0.1` by default, matching the Go API.