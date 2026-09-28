"""One-click start: Go server + MCP + Web"""

import subprocess
import sys
import os
import time
import webbrowser
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

BASE = Path(__file__).parent
GO_EXE = BASE / "windows" / "pethospital.exe"
WEB_DIR = BASE / "web"
WEB_PORT = int(os.environ.get("WEB_PORT", "3000"))

processes = []

def flush(msg=""):
    print(msg, flush=True)

def banner():
    flush("=" * 55)
    flush("  Pet Hospital AI System - One Click Start")
    flush("=" * 55)

def start_go():
    if not GO_EXE.exists():
        print(f"[ERROR] Not found: {GO_EXE}")
        return False
    print(f"[GO] Starting Pet Hospital (port 8080) ...")
    p = subprocess.Popen(
        [str(GO_EXE)],
        cwd=str(GO_EXE.parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    processes.append(p)
    return True

def start_mcp():
    print(f"[MCP] Starting MCP service (port 9000) ...")
    env = os.environ.copy()
    env["MCP_PORT"] = "9000"
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen(
        [sys.executable, str(BASE / "mcp_launcher.py")],
        cwd=str(BASE),
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    processes.append(p)
    return True

def start_web():
    print(f"[WEB] Starting Web server (port {WEB_PORT}) ...")
    env = os.environ.copy()
    env["WEB_PORT"] = str(WEB_PORT)
    env["MCP_URL"] = "http://127.0.0.1:9000"
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen(
        [sys.executable, str(WEB_DIR / "server.py")],
        cwd=str(WEB_DIR),
        env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    processes.append(p)
    return True

def main():
    banner()

    if not start_go():
        input("Press Enter to exit...")
        return

    time.sleep(2)
    start_mcp()
    time.sleep(2)
    start_web()

    flush()
    flush("Waiting for services...")
    time.sleep(3)

    url = f"http://127.0.0.1:{WEB_PORT}"
    flush()
    flush(f"  Web UI:      {url}")
    flush(f"  Go API:      http://127.0.0.1:8080")
    flush(f"  MCP:         http://127.0.0.1:9000/mcp")
    flush()
    flush("Press Ctrl+C to stop all services")
    flush()

    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"[WARN] Process exited (code={p.returncode})")
    except KeyboardInterrupt:
        print("\nStopping all services...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
        print("Done.")

if __name__ == "__main__":
    main()
