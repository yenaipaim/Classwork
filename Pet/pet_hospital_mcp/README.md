# Pet Hospital MCP Service

A Model Context Protocol (MCP) service that exposes the Go Pet Hospital REST API to AI agents.

## Overview

This MCP service acts as a bridge between AI agents and the Go Pet Hospital REST API. It implements the MCP protocol version 2026-07-28 using the official Python SDK 2.x (`mcp==2.0.0`).

### Key Features

- **MCP Protocol**: 2026-07-28 (stateless Streamable HTTP)
- **SDK**: `mcp==2.0.0` with `MCPServer`
- **Transport**: Stateless Streamable HTTP (no sessions, no `Mcp-Session-Id`)
- **Tools**: `list_pets` - Query and search pet records
- **Health Check**: `/health` endpoint for monitoring

## Prerequisites

1. **Go Pet Hospital Service** must be running first:
   ```bash
   cd windows
   pethospital.exe
   # Service starts at http://127.0.0.1:8080
   ```

2. **Python 3.11+**

## Installation

```bash
cd pet_hospital_mcp

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"
```

## Configuration

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | Go REST API address |
| `MCP_HOST` | `127.0.0.1` | MCP server listen host |
| `MCP_PORT` | `9000` | MCP server listen port |
| `HTTP_TIMEOUT` | `30.0` | HTTP client timeout (seconds) |
| `MAX_RETRIES` | `2` | Max retries for backend calls |

## Running

```bash
# Start the MCP server
python -m pet_hospital_mcp

# Or with custom port
MCP_PORT=9001 python -m pet_hospital_mcp
```

The MCP endpoint will be available at `http://127.0.0.1:9000/mcp`.

## MCP Endpoint

- **URL**: `http://127.0.0.1:9000/mcp`
- **Protocol**: Streamable HTTP (2026-07-28)
- **Method**: POST
- **Headers**:
  - `Content-Type: application/json`
  - `Accept: application/json, text/event-stream`
  - `MCP-Protocol-Version: 2026-07-28`

## Tools

### `list_pets`

List and search pets in the hospital database.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Full-text search across all fields |
| `name` | string | No | Filter by pet name (partial match) |
| `ownerName` | string | No | Filter by owner name (partial match) |
| `ownerPhone` | string | No | Filter by owner phone (partial match) |
| `species` | string | No | Filter by species: 犬/猫/兔/鸟/仓鼠/爬宠/其他 |
| `doctor` | string | No | Filter by attending doctor |
| `disease` | string | No | Filter by disease/diagnosis |
| `status` | string | No | Filter by status: 待就诊/就诊中/住院中/已康复/慢性病随访 |
| `min` | number | No | Minimum total cost filter (>= 0) |
| `max` | number | No | Maximum total cost filter (>= 0, must be >= min) |
| `sortBy` | string | No | Sort field: id/name/ownerName/species/doctor/disease/status/totalCost/visitCount/createdAt/updatedAt |
| `order` | string | No | Sort order: asc/desc |
| `page` | integer | No | Page number (default: 1, >= 1) |
| `pageSize` | integer | No | Items per page (default: 20, 1-500) |

**Response**:

```json
{
  "items": [
    {
      "id": "PET-000001",
      "name": "旺财",
      "species": "犬",
      "breed": "金毛",
      "gender": "公",
      "ageMonths": 36,
      "color": "金色",
      "chipNo": "CHIP-000001",
      "ownerName": "张三",
      "ownerPhone": "13800001111",
      "ownerAddr": "北京市朝阳区",
      "doctor": "李医生",
      "disease": "急性肠胃炎",
      "status": "就诊中",
      "allergy": "无",
      "note": null,
      "records": [...],
      "charges": [...],
      "totalCost": 560.0,
      "visitCount": 1,
      "createdAt": "2024-01-15T10:00:00Z",
      "updatedAt": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "pageSize": 20,
  "totalPages": 5,
  "totalCost": 50000.0
}
```

## Health Check

```bash
curl http://127.0.0.1:9000/health
```

Response:
```json
{
  "status": "healthy",
  "backend": {
    "status": "healthy",
    "petCount": 1008
  }
}
```

## Verification with MCP Inspector

1. Start the Go service:
   ```bash
   cd windows && pethospital.exe
   ```

2. Start the MCP service:
   ```bash
   cd pet_hospital_mcp && python -m pet_hospital_mcp
   ```

3. Open MCP Inspector and connect to `http://127.0.0.1:9000/mcp`

4. Discover tools and call `list_pets`

## Testing

```bash
cd pet_hospital_mcp
pytest -q
```

Expected output:
```
.............                                                     [100%]
13 passed
```

## Error Handling

All errors follow a unified structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {}
  }
}
```

Error codes:
- `VALIDATION_ERROR` - Invalid input parameters
- `BACKEND_TIMEOUT` - Backend request timed out
- `BACKEND_UNAVAILABLE` - Cannot connect to backend
- `BACKEND_API_ERROR` - Backend returned an error
- `BACKEND_INVALID_RESPONSE` - Invalid response from backend
- `INTERNAL_ERROR` - Unexpected internal error

## Security Notes

- This service is for **local/development use only**
- No authentication, CORS, or Origin validation
- Sensitive data (phone, address, chip number) is masked in logs
- The service only listens on `127.0.0.1` by default

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   AI Agent      │────▶│  MCP Service     │────▶│  Go REST API    │
│  (MCP Client)   │◀────│  (Python)        │◀────│  (Port 8080)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                        Port 9000
```

## License

MIT
