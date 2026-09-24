"""
DocMind AI — Model Context Protocol (MCP) Server
Allows external AI agents (Antigravity IDE, Claude Desktop, Cursor)
to securely interact with DocMind AI's RAG, Vector Search, and Document Intelligence.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Silence noisy third-party logs
os.environ["ANONYMIZED_TELEMETRY"] = "False"
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

logger = logging.getLogger("docmind.mcp")

from mcp.server.mcpserver import MCPServer
from app.core.rag import RAGPipeline
from app.core.vectorstore import VectorStore
from app.core.intelligence import DocumentIntelligence

# Initialize Core Engines
server = MCPServer(
    name="DocMind-AI",
    instructions="DocMind AI Server: Search, query, and extract insights from documents."
)
rag = RAGPipeline()
store = VectorStore()
intelligence = DocumentIntelligence()


@server.tool()
def search_documents(
    query: str,
    user_email: str = "demo@docmind.ai",
    top_k: int = 5,
) -> str:
    """
    Search indexed documents using hybrid semantic and BM25 search.
    Returns matched excerpts, filenames, page numbers, and relevance scores.
    """
    try:
        results = store.search(query=query, top_k=top_k, user_email=user_email)
        if not results:
            return f"No relevant documents found for query: '{query}'"

        formatted = []
        for idx, r in enumerate(results, 1):
            source = r.get("source", "Unknown")
            page = r.get("page", 1)
            score = r.get("score", 0.0)
            text = r.get("text", "").strip().replace("\n", " ")
            formatted.append(f"{idx}. [{source} | Page {page} | Score: {score:.2f}]\n   {text}")

        return "\n\n".join(formatted)
    except Exception as e:
        logger.error(f"Error in search_documents: {e}")
        return f"Error executing search: {str(e)}"


@server.tool()
def ask_document(
    question: str,
    document_id: Optional[str] = None,
    user_email: str = "demo@docmind.ai",
) -> str:
    """
    Ask a question to DocMind AI about uploaded documents with zero-hallucination citations.
    Supports English, Hindi, and Gujarati.
    """
    try:
        doc_ids = [document_id] if document_id else None
        res = rag.answer(
            question=question,
            document_ids=doc_ids,
            user_email=user_email,
        )
        answer = res.get("answer", "No answer could be generated.")
        sources = res.get("sources", [])

        if sources:
            citations = []
            for s in sources:
                citations.append(f"- {s.get('source')} (Page {s.get('page')})")
            answer += "\n\n**Sources:**\n" + "\n".join(citations)

        return answer
    except Exception as e:
        logger.error(f"Error in ask_document: {e}")
        return f"Error querying document: {str(e)}"


@server.tool()
def list_user_documents(user_email: str = "demo@docmind.ai") -> str:
    """
    List all documents currently indexed for the given user email.
    """
    try:
        docs = store.list_documents(user_email=user_email)
        if not docs:
            return f"No documents found for user {user_email}."

        lines = [f"Documents for {user_email}:"]
        for d in docs:
            lines.append(f"• ID: {d['document_id']} | File: {d['filename']} | Chunks: {d['chunks_count']}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error in list_user_documents: {e}")
        return f"Error listing documents: {str(e)}"


@server.tool()
def summarize_document(
    document_id: str,
    summary_type: str = "executive",
    language: str = "en",
    user_email: str = "demo@docmind.ai",
) -> str:
    """
    Generate an executive, detailed, or bullet_points summary of a document in English, Hindi, or Gujarati.
    """
    try:
        chunks = store.get_document_chunks(document_id, user_email=user_email)
        if not chunks:
            return f"Document '{document_id}' not found for user {user_email}."

        doc_text = " ".join(c.get("text", "") for c in chunks)
        filename = chunks[0].get("source", "document")
        res = intelligence.summarize(
            document_text=doc_text,
            filename=filename,
            summary_type=summary_type,
            language=language,
        )
        return res.get("summary", "Could not generate summary.")
    except Exception as e:
        logger.error(f"Error in summarize_document: {e}")
        return f"Error summarizing document: {str(e)}"


if __name__ == "__main__":
    server.run()
