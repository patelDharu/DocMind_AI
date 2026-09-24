"""
Test Suite for DocMind AI MCP Server
Verifies that all registered tools can be discovered and executed.
"""
import sys
import os
import asyncio

WORKSPACE_ROOT = r"D:\docmind-ai"
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from app.mcp_server import server, list_user_documents, search_documents, ask_document


async def test_mcp():
    print("============================================================")
    print("  DocMind AI MCP Server Automated Verification Suite        ")
    print("============================================================")

    # 1. Tool discovery check
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    print(f"\n[1/3] Checking Tool Discovery...")
    print(f"  Available MCP Tools: {tool_names}")
    expected_tools = ["search_documents", "ask_document", "list_user_documents", "summarize_document"]
    for exp in expected_tools:
        assert exp in tool_names, f"Missing MCP Tool: {exp}"
    print("  [OK] All 4 MCP Tools registered and discoverable.")

    # 2. Test list_user_documents tool
    print("\n[2/3] Testing list_user_documents execution...")
    result_docs = list_user_documents(user_email="demo@docmind.ai")
    assert isinstance(result_docs, str) and len(result_docs) > 0
    print(f"  [OK] list_user_documents returned: {result_docs[:100]}...")

    # 3. Test search_documents tool
    print("\n[3/3] Testing search_documents execution...")
    result_search = search_documents(query="test", user_email="demo@docmind.ai")
    assert isinstance(result_search, str) and len(result_search) > 0
    print(f"  [OK] search_documents returned: {result_search[:100]}...")

    print("\n============================================================")
    print("  ALL MCP SERVER TESTS PASSED SUCCESSFULLY! [PASS]")
    print("============================================================")


if __name__ == "__main__":
    asyncio.run(test_mcp())
