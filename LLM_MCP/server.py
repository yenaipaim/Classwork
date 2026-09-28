import json
import httpx
from mcp.server import MCPServer

ANYTHINGLLM_BASE = "http://localhost:3001/api/v1"
ANYTHINGLLM_KEY = "YM478Q1-R7J4B6W-GMTZJ3B-E7RKPTT"
WORKSPACE_SLUG = "mods"

mcp = MCPServer("anythingllm")


@mcp.tool()
async def query_mods(question: str) -> str:
    """Query the mods workspace in AnythingLLM. Returns AI-generated answer based on workspace documents."""
    url = f"{ANYTHINGLLM_BASE}/workspace/{WORKSPACE_SLUG}/stream-chat"
    headers = {
        "Authorization": f"Bearer {ANYTHINGLLM_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"message": question, "mode": "query"}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            full_text = []
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if chunk.get("type") in ("textResponseChunk", "textResponse"):
                    full_text.append(chunk.get("textResponse", ""))
                if chunk.get("close"):
                    break
            return "".join(full_text) or "No response from AnythingLLM."


if __name__ == "__main__":
    mcp.run("streamable-http")
