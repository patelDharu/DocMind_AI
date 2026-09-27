"""
Google Drive MCP Server for DocMind AI.
Allows external AI agents (Antigravity IDE, Claude Desktop, Cursor)
and DocMind AI to list, search, read, and ingest documents from Google Drive.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("docmind.mcp_gdrive")

from mcp.server.mcpserver import MCPServer
from app.core.gdrive_mcp import (
    is_gdrive_configured,
    is_authenticated,
    list_drive_files,
    download_drive_file,
    get_client_secrets_path,
    CREDENTIALS_DIR,
)
from app.core.loader import load_document
from app.core.chunker import chunk_text
from app.core.vectorstore import VectorStore
from app.core.rag import RAGPipeline

server = MCPServer(
    name="Google-Drive-DocMind",
    instructions="Search, list, read, and index files directly from Google Drive into DocMind AI RAG."
)

store = VectorStore()
pipeline = RAGPipeline()


@server.tool()
def check_drive_auth_status() -> str:
    """
    Check if Google Drive OAuth credentials are configured and authenticated.
    """
    configured = is_gdrive_configured()
    authenticated = is_authenticated()
    secrets_path = get_client_secrets_path()

    if not configured:
        return (
            f"❌ Google Drive is not configured.\n"
            f"Please place your Google Cloud OAuth client secrets JSON file in:\n"
            f"'{CREDENTIALS_DIR}\\gcp-oauth.keys.json'"
        )
    if not authenticated:
        return (
            f"⚠️ Google Drive is configured ({secrets_path.name}), but initial authentication is required.\n"
            f"Run 'python -m app.core.gdrive_mcp' or use DocMind's web UI to sign in."
        )
    return "✅ Google Drive is fully authenticated and ready for search & retrieval."


@server.tool()
def search_drive_documents(query: str = "", max_results: int = 10) -> str:
    """
    Search files in Google Drive by name or contents.
    Returns a list of matching files with ID, name, modification date, and link.
    """
    try:
        if not is_gdrive_configured():
            return "Error: Google Drive OAuth credentials not configured."

        files = list_drive_files(query=query if query.strip() else None, page_size=max_results)
        if not files:
            return f"No Google Drive files found matching: '{query}'"

        lines = [f"Found {len(files)} file(s) in Google Drive:"]
        for idx, f in enumerate(files, 1):
            sz = f"{f['size'] / (1024*1024):.1f} MB" if f.get("size") else "Doc/Sheet"
            lines.append(f"{idx}. [{f['name']}] (ID: {f['id']}) | Type: {f['mime_type']} | Size: {sz}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error searching Drive: {e}")
        return f"Error querying Google Drive: {str(e)}"


@server.tool()
def import_drive_file_to_rag(
    file_id: str,
    user_email: str = "demo@docmind.ai",
) -> str:
    """
    Download a document from Google Drive by its file ID and index it into DocMind's RAG vector store.
    """
    try:
        upload_dir = PROJECT_ROOT / "app" / "data" / "uploads"
        dest_path, original_filename = download_drive_file(file_id, upload_dir)

        # Process document
        records = load_document(str(dest_path))
        if not records:
            records = [{
                "text": f"Google Drive Document: {original_filename}",
                "metadata": {
                    "source": original_filename,
                    "page": 1,
                    "user_email": user_email,
                    "gdrive_file_id": file_id,
                }
            }]

        import uuid
        doc_id = uuid.uuid4().hex
        for r in records:
            m = r.get("metadata", {})
            m["document_id"] = doc_id
            m["source"] = original_filename
            m["user_email"] = user_email
            m["gdrive_file_id"] = file_id
            r["metadata"] = m

        chunks = chunk_text(records)
        for c in chunks:
            cm = c.get("metadata", {})
            cm["user_email"] = user_email
            cm["gdrive_file_id"] = file_id
            c["metadata"] = cm

        pipeline.ingest(chunks, user_email=user_email)

        return (
            f"✅ Successfully imported '{original_filename}' (ID: {file_id}) into DocMind AI.\n"
            f"Document ID: {doc_id} | Chunks Indexed: {len(chunks)}."
        )
    except Exception as e:
        logger.error(f"Error importing Drive file: {e}")
        return f"Error importing document from Google Drive: {str(e)}"


if __name__ == "__main__":
    server.run()
