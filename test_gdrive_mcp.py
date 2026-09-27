"""
Automated Verification Suite for Google Drive MCP Integration in DocMind AI.
Verifies MCP tools, configuration checks, and FastAPI endpoints.
"""

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import asyncio
from fastapi.testclient import TestClient
from app.api.main import app
from app.core.auth import get_or_create_demo_token
from app.core.gdrive_mcp import is_gdrive_configured, is_authenticated
from app.mcp_gdrive_server import server as gdrive_server
from app.mcp_server import server as docmind_server


def test_gdrive_mcp():
    print("============================================================")
    print("  DocMind AI — Google Drive MCP Automated Test Suite        ")
    print("============================================================")

    # 1. Test Core Module Checks
    print("\n[1/4] Testing Core Status & Configuration Checks...")
    conf = is_gdrive_configured()
    auth = is_authenticated()
    print(f"  Drive Configured: {conf}")
    print(f"  Drive Authenticated: {auth}")
    assert isinstance(conf, bool)
    assert isinstance(auth, bool)
    print("  [OK] Core checks executed without exceptions.")

    # 2. Test Standalone Google Drive MCP Server Tools
    print("\n[2/4] Testing Standalone Google Drive MCP Server Tools...")
    g_tools = asyncio.run(gdrive_server.list_tools())
    g_tool_names = [t.name for t in g_tools]
    print(f"  Google Drive MCP Tools: {g_tool_names}")
    for exp in ["check_drive_auth_status", "search_drive_documents", "import_drive_file_to_rag"]:
        assert exp in g_tool_names, f"Missing tool: {exp}"
    print("  [OK] All Google Drive MCP tools registered.")

    # 3. Test DocMind Main MCP Server Google Drive Tools
    print("\n[3/4] Testing DocMind Main MCP Server Integration...")
    d_tools = asyncio.run(docmind_server.list_tools())
    d_tool_names = [t.name for t in d_tools]
    assert "search_google_drive" in d_tool_names, "Missing search_google_drive in docmind server"
    assert "import_google_drive_document" in d_tool_names, "Missing import_google_drive_document in docmind server"
    print("  [OK] Google Drive tools present in DocMind main MCP server.")

    # 4. Test FastAPI Drive MCP Endpoints
    print("\n[4/4] Testing FastAPI /drive/mcp/* Endpoints...")
    client = TestClient(app)
    token = get_or_create_demo_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Status endpoint (Authenticated user)
    status_resp = client.get("/drive/mcp/status", headers=headers)
    assert status_resp.status_code == 200, f"Expected 200, got {status_resp.status_code}"
    status_data = status_resp.json()
    assert "configured" in status_data
    assert "authenticated" in status_data
    print(f"  [OK] /drive/mcp/status returned: {status_data['message']}")

    # Files endpoint (When not configured, should return 400 with helpful message)
    files_resp = client.get("/drive/mcp/files", headers=headers)
    if not conf:
        assert files_resp.status_code == 400
        print(f"  [OK] /drive/mcp/files properly caught unconfigured state (HTTP 400).")
    else:
        print(f"  [OK] /drive/mcp/files response: HTTP {files_resp.status_code}")

    print("\n============================================================")
    print("  ALL GOOGLE DRIVE MCP TESTS PASSED SUCCESSFULLY! [PASS]   ")
    print("============================================================")


if __name__ == "__main__":
    test_gdrive_mcp()
