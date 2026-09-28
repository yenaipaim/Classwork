"""Web server: serves frontend + proxies AI & MCP requests."""

import json, os, asyncio, threading, queue
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import httpx

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:9000")

DEFAULT_CONFIG = {
    "ai": {"baseUrl": "https://api.openai.com/v1", "apiKey": "", "model": "gpt-4o-mini"},
    "mcp": {"enabledTools": []}
}

ALL_MCP_TOOLS = [
    "查询宠物列表", "获取宠物详情", "新增宠物", "全量更新宠物", "局部更新宠物", "删除宠物",
    "全文搜索", "按主人查询", "按医生查询", "按种类查询",
    "按疾病查询", "按状态查询", "消费排行榜", "按花费区间查询",
    "查看病历", "添加病历",
    "查看收费明细", "添加收费", "费用汇总",
    "经营统计", "元数据字典",
    "批量新增", "批量删除", "压实数据库",
    "生成模拟数据", "接口清单", "健康检查", "导出数据",
]

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")

# ── MCP session management ───────────────────────────────────────
class MCPSession:
    """Manages MCP protocol session (init + tools/list + tools/call)."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session_id: str | None = None
        self._lock = threading.Lock()

    def _ensure_session(self):
        """Initialize MCP session if not active."""
        if self.session_id:
            return
        with self._lock:
            if self.session_id:
                return
            resp = httpx.post(f"{self.base_url}/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "web-proxy", "version": "1.0"}
                }
            }, headers={"Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"}, timeout=10.0)
            self.session_id = resp.headers.get("mcp-session-id")
            # Send initialized notification
            httpx.post(f"{self.base_url}/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={"Content-Type": "application/json",
                         "Mcp-Session-Id": self.session_id}, timeout=5.0)

    def _call(self, method: str, params: dict = None) -> dict:
        self._ensure_session()
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        headers = {"Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        try:
            resp = httpx.post(f"{self.base_url}/mcp", json=payload, headers=headers, timeout=60.0)
            # Check for session expiry
            if resp.status_code == 400:
                self.session_id = None
                self._ensure_session()
                resp = httpx.post(f"{self.base_url}/mcp", json=payload, headers=headers, timeout=60.0)
        except Exception:
            self.session_id = None
            raise
        # Parse SSE response
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return {"error": "empty SSE"}
        return resp.json() if resp.text else {}

    def list_tools(self) -> list[dict]:
        try:
            r = self._call("tools/list")
            return r.get("result", {}).get("tools", [])
        except Exception:
            return []

    def call_tool(self, name: str, arguments: dict) -> dict:
        try:
            r = self._call("tools/call", {"name": name, "arguments": arguments})
            return r.get("result", r)
        except Exception as e:
            return {"error": str(e)}

mcp = MCPSession(MCP_URL)

# ── AI streaming ─────────────────────────────────────────────────
def ai_stream_sync(messages, tools, config):
    """Generator: yields SSE data lines from AI chat completion."""
    ai = config["ai"]
    url = f"{ai['baseUrl'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if ai.get("apiKey"):
        headers["Authorization"] = f"Bearer {ai['apiKey']}"
    body = {"model": ai["model"], "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    with httpx.Client(timeout=120.0) as c:
        with c.stream("POST", url, json=body, headers=headers) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    yield line[6:]

# ── HTTP Handler ─────────────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(BASE / "frontend"), **kw)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/config":
            self._json(load_config())
        elif p == "/api/mcp/tools":
            self._json({"tools": ALL_MCP_TOOLS})
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        body = self._read_body()
        if p == "/api/config":
            save_config(json.loads(body)); self._json({"ok": True})
        elif p == "/api/mcp/tools":
            self._json({"tools": ALL_MCP_TOOLS})
        elif p == "/api/mcp/discover":
            self._handle_discover()
        elif p == "/api/mcp/call":
            self._handle_mcp_call(body)
        elif p == "/api/ai/stream":
            self._handle_ai_stream(body)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_discover(self):
        tools = mcp.list_tools()
        self._json({"tools": [{"name": t["name"], "description": t.get("description", ""),
                                "inputSchema": t.get("inputSchema", {})} for t in tools]})

    def _handle_mcp_call(self, body):
        d = json.loads(body)
        result = mcp.call_tool(d["tool"], d.get("arguments", {}))
        self._json(result)

    def _handle_ai_stream(self, body):
        d = json.loads(body)
        cfg = load_config()

        # Build tool schemas for AI
        tool_defs = []
        enabled = set(cfg.get("mcp", {}).get("enabledTools", []))
        if enabled:
            for t in mcp.list_tools():
                if t["name"] in enabled:
                    tool_defs.append({
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
                        }
                    })

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            for chunk in ai_stream_sync(d["messages"], tool_defs if tool_defs else None, cfg):
                self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as e:
            err = json.dumps({"error": str(e)})
            self.wfile.write(f"data: {err}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b"{}"

    def _json(self, data, code=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *a):
        if "/api/" in str(a[0]):
            print(f"  {a[0]}")

def main():
    port = int(os.environ.get("WEB_PORT", "3000"))
    srv = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Web: http://127.0.0.1:{port}")
    srv.serve_forever()

if __name__ == "__main__":
    main()
