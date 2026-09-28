"""MCP launcher - standalone entry point."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pet_hospital_mcp", "src"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from pet_hospital_mcp.__main__ import main
main()
