# app/api/main.py

import json
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import gc
import logging
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
os.environ["ANONYMIZED_TELEMETRY"] = "False"
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
logger = logging.getLogger("docmind.api")

MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB strict upload cap
MAX_VOICE_SIZE_BYTES = 15 * 1024 * 1024   # 15 MB voice query cap

from app.core.loader import load_document
from app.core.chunker import chunk_text
from app.core.rag import RAGPipeline
from app.core.intelligence import DocumentIntelligence
from app.core.doc_editor import DocumentEditor
from app.core.speech import transcribe_audio
from app.core.tts import synthesize_speech
from app.core.resilience import GeminiServiceError
from app.core.auth import (
    authenticate_user,
    register_user,
    validate_session_token,
    generate_session_token,
    get_or_create_demo_token,
    get_database_status_info,
)

# =========================================================
# APP CONFIGURATION
# =========================================================

app = FastAPI(
    title="DocMind AI",
    description="Enterprise Trilingual Document Intelligence with Advanced RAG, Hybrid Search & Document Studio",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = RAGPipeline()
intelligence = DocumentIntelligence()
editor = DocumentEditor()

# =========================================================
# AUTHENTICATION & SECURITY DEPENDENCY
# =========================================================

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Validates token from Authorization Bearer header, X-API-Key header, or token query param.
    Rejects unauthenticated requests with HTTP 401.
    """
    auth_token = None
    if credentials and credentials.credentials:
        auth_token = credentials.credentials
    elif x_api_key:
        auth_token = x_api_key
    elif token:
        auth_token = token

    if not auth_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a Bearer token or API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = validate_session_token(auth_token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# =========================================================
# GLOBAL EXCEPTION HANDLER FOR GEMINI RESILIENCE
# =========================================================

@app.exception_handler(GeminiServiceError)
async def gemini_service_exception_handler(request: Request, exc: GeminiServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_type": "GeminiServiceError",
            "message": str(exc),
            "detail": "Automatic retries were exhausted. Please retry after a brief delay.",
        },
    )


# =========================================================
# DIRECTORIES
# =========================================================

BASE_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOAD_DIR = BASE_DATA_DIR / "uploads"
TEMP_AUDIO_DIR = BASE_DATA_DIR / "audio_in"
AUDIO_OUT_DIR = BASE_DATA_DIR / "audio_out"
GENERATED_DIR = BASE_DATA_DIR / "generated"

for _d in [UPLOAD_DIR, TEMP_AUDIO_DIR, AUDIO_OUT_DIR, GENERATED_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# =========================================================
# REQUEST MODELS
# =========================================================

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class QueryRequest(BaseModel):
    question: str
    top_k: int = 8
    lang_hint: Optional[str] = None
    document_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    history: List[dict] = []


class SummarizeRequest(BaseModel):
    document_id: str
    summary_type: str = "executive"
    language: str = "en"


class CompareRequest(BaseModel):
    document_ids: List[str]
    focus_aspects: str = "general"
    language: str = "en"


class ExtractRequest(BaseModel):
    document_id: str
    extraction_type: str = "full_schema"


class DocumentEditRequest(BaseModel):
    document_id: str
    instruction: str
    export_format: str = "docx"
    auto_index: bool = True
    edit_mode: str = "append"  # "append" or "revise"


class SpeakRequest(BaseModel):
    text: Optional[str] = None
    language: Optional[str] = "en"


# =========================================================
# ROOT & HEALTH ENDPOINTS (Public)
# =========================================================

@app.get("/")
def root():
    return {
        "service": "DocMind AI",
        "status": "running",
        "docs_url": "http://127.0.0.1:8000/docs",
        "version": "2.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "DocMind AI",
        "version": "2.1.0",
        "database": get_database_status_info(),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY", "").strip()),
    }


# =========================================================
# AUTHENTICATION ENDPOINTS
# =========================================================

@app.post("/auth/login")
def login_endpoint(req: LoginRequest):
    success, msg, user_dict = authenticate_user(req.email, req.password)
    if not success or not user_dict:
        raise HTTPException(status_code=401, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "user": user_dict,
        "token": user_dict.get("token"),
    }


@app.post("/auth/register")
def register_endpoint(req: RegisterRequest):
    success, msg, user_dict = register_user(req.name, req.email, req.password)
    if not success or not user_dict:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "user": user_dict,
        "token": user_dict.get("token"),
    }


@app.get("/auth/me")
def get_current_user_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"status": "success", "user": current_user}


# =========================================================
# 1. UPLOAD & INDEX DOCUMENT (Strictly Scoped by User)
# =========================================================

@app.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is missing.")

    original_filename = Path(file.filename).name
    allowed_extensions = {
        ".pdf", ".docx", ".doc",
        ".txt", ".md", ".markdown", ".rtf", ".log",
        ".csv", ".tsv", ".xlsx", ".xls",
        ".pptx", ".ppt",
        ".html", ".htm", ".json", ".yaml", ".yml", ".xml",
        ".png", ".jpg", ".jpeg", ".webp", ".bmp"
    }
    extension = Path(original_filename).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{extension}'. Supported formats: PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, HTML, JSON, PNG, JPG.",
        )

    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()

    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not gemini_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not set on this server. If running on Render, please add your GEMINI_API_KEY under the 'Environment' tab in your Render Dashboard.",
        )

    document_id = uuid.uuid4().hex
    stored_filename = f"{document_id}_{original_filename}"
    dest = UPLOAD_DIR / stored_filename

    try:
        gc.collect()
        total_bytes = 0
        chunk_buffer_size = 1024 * 1024  # 1 MB buffer
        with open(dest, "wb") as f:
            while True:
                chunk = file.file.read(chunk_buffer_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    f.close()
                    if dest.exists():
                        try:
                            dest.unlink()
                        except Exception:
                            pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size ({total_bytes / (1024 * 1024):.1f} MB) exceeds the 25 MB limit. Please upload a file smaller than 25 MB.",
                    )
                f.write(chunk)

        records = load_document(str(dest))
        if not records:
            records = [{
                "text": f"Document: {original_filename}\n[Content processed]",
                "metadata": {
                    "source": original_filename,
                    "page": 1,
                    "char_count": len(original_filename),
                    "user_email": user_email,
                }
            }]

        for record in records:
            metadata = record.get("metadata", {})
            metadata["document_id"] = document_id
            metadata["source"] = original_filename
            metadata["user_email"] = user_email
            record["metadata"] = metadata

        chunks = chunk_text(records)
        if not chunks:
            chunks = [{
                "id": f"{document_id}_chunk_0",
                "text": f"Document: {original_filename}",
                "metadata": {
                    "document_id": document_id,
                    "source": original_filename,
                    "page": 1,
                    "chunk": 0,
                    "user_email": user_email,
                }
            }]
        else:
            for c in chunks:
                c_meta = c.get("metadata", {})
                c_meta["user_email"] = user_email
                c["metadata"] = c_meta

        pipeline.ingest(chunks, user_email=user_email)

        # Proactively scan for actions, deadlines & consequences
        action_alert = {"requires_action": False, "urgency": "none"}
        try:
            doc_text = "\n\n".join([r.get("text", "") for r in records if r.get("text")])
            action_alert = intelligence.analyze_action_and_deadlines(
                document_text=doc_text,
                filename=original_filename,
                language="en",
            )
        except Exception as alert_err:
            logger.warning(f"Action alert analysis skipped or timed out for {original_filename}: {alert_err}")

        gc.collect()
    except HTTPException:
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        raise
    except Exception as e:
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "filename": original_filename,
        "document_id": document_id,
        "chunks_indexed": len(chunks),
        "action_alert": action_alert,
    }


# =========================================================
# 2. ASK QUESTION (CHATGPT-STYLE MASTER RAG - User Scoped)
# =========================================================

@app.post("/ask")
def ask_question(
    req: QueryRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
        target_docs = req.document_ids or []
        if req.document_id and req.document_id not in target_docs:
            target_docs.append(req.document_id)

        result = pipeline.answer(
            question=req.question,
            top_k=req.top_k,
            lang_hint=req.lang_hint,
            document_ids=target_docs if target_docs else None,
            history=req.history,
            user_email=user_email,
        )
        return result
    except GeminiServiceError as ge:
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# 3. ASK BY VOICE (Strict 15 MB Cap & Authenticated)
# =========================================================

@app.post("/ask-voice")
def ask_voice_question(
    file: UploadFile = File(...),
    speak_reply: bool = True,
    document_ids: Optional[str] = None,
    history: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file missing.")

    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    temp_path = TEMP_AUDIO_DIR / f"{uuid.uuid4().hex}.wav"

    try:
        # Enforce strict 15 MB audio stream cap
        total_audio_bytes = 0
        chunk_buffer = 1024 * 256  # 256 KB buffer
        with open(temp_path, "wb") as f:
            while True:
                chunk = file.file.read(chunk_buffer)
                if not chunk:
                    break
                total_audio_bytes += len(chunk)
                if total_audio_bytes > MAX_VOICE_SIZE_BYTES:
                    f.close()
                    if temp_path.exists():
                        temp_path.unlink()
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio file size exceeds the 15 MB limit. Please record a shorter message.",
                    )
                f.write(chunk)

        transcription = transcribe_audio(str(temp_path))
        question_text = transcription.get("text", "").strip()
        detected_lang = transcription.get("language", "en")

        if not question_text:
            raise ValueError("Could not recognize any spoken speech.")

        parsed_docs = []
        if document_ids:
            try:
                parsed_docs = json.loads(document_ids)
            except Exception:
                parsed_docs = [document_ids]

        parsed_history = []
        if history:
            try:
                parsed_history = json.loads(history)
            except Exception:
                parsed_history = []

        result = pipeline.answer(
            question=question_text,
            top_k=8,
            lang_hint=detected_lang,
            document_ids=parsed_docs if parsed_docs else None,
            history=parsed_history,
            user_email=user_email,
        )

        result["transcribed_question"] = question_text
        result["detected_language"] = detected_lang

        if speak_reply and result.get("answer"):
            audio_path = synthesize_speech(
                result["answer"],
                detected_lang,
                output_dir=str(AUDIO_OUT_DIR),
            )
            result["audio_reply_path"] = audio_path

        return result

    except HTTPException:
        raise
    except GeminiServiceError as ge:
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


# =========================================================
# 4. DOCUMENT SUMMARIZATION (User Scoped)
# =========================================================

@app.post("/summarize")
def summarize_doc(
    req: SummarizeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    chunks = pipeline.store.get_document_chunks(req.document_id, user_email=user_email)
    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no indexed content.")

    full_text = "\n\n".join([c["text"] for c in chunks])
    filename = chunks[0].get("source", "Document")

    res = intelligence.summarize(
        document_text=full_text,
        filename=filename,
        summary_type=req.summary_type,
        language=req.language,
    )
    return res


# =========================================================
# 5. DOCUMENT COMPARISON (User Scoped)
# =========================================================

@app.post("/compare")
def compare_docs(
    req: CompareRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if len(req.document_ids) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 documents to compare.")

    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    chunks_a = pipeline.store.get_document_chunks(req.document_ids[0], user_email=user_email)
    chunks_b = pipeline.store.get_document_chunks(req.document_ids[1], user_email=user_email)

    if not chunks_a or not chunks_b:
        raise HTTPException(status_code=404, detail="One or both selected documents could not be found.")

    doc_a = {
        "filename": chunks_a[0].get("source", "Document A"),
        "text": "\n\n".join([c["text"] for c in chunks_a]),
    }
    doc_b = {
        "filename": chunks_b[0].get("source", "Document B"),
        "text": "\n\n".join([c["text"] for c in chunks_b]),
    }

    res = intelligence.compare_documents(
        doc_a=doc_a,
        doc_b=doc_b,
        focus_aspects=req.focus_aspects,
        language=req.language,
    )
    return res


# =========================================================
# 6. STRUCTURED INFORMATION EXTRACTION (User Scoped)
# =========================================================

@app.post("/extract")
def extract_doc_data(
    req: ExtractRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    chunks = pipeline.store.get_document_chunks(req.document_id, user_email=user_email)
    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found.")

    full_text = "\n\n".join([c["text"] for c in chunks])
    filename = chunks[0].get("source", "Document")

    res = intelligence.extract_structured_data(
        document_text=full_text,
        filename=filename,
        extraction_type=req.extraction_type,
    )
    return res


# =========================================================
# 7. DOCUMENT STUDIO: EDIT & EXPORT (User Scoped)
# =========================================================

@app.post("/document/edit")
def edit_document(
    req: DocumentEditRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
        chunks = pipeline.store.get_document_chunks(req.document_id, user_email=user_email)
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found.")

        full_text = "\n\n".join([c["text"] for c in chunks])
        base_filename = chunks[0].get("source", "Document")
        stem_name = Path(base_filename).stem

        # 1. Generate updated content via prompt
        updated_markdown = editor.update_document(
            original_text=full_text,
            instruction=req.instruction,
            document_title=f"Updated: {stem_name}",
            edit_mode=req.edit_mode,
        )

        new_doc_id = uuid.uuid4().hex
        fmt = req.export_format.lower()
        if fmt not in ["docx", "pdf"]:
            fmt = "docx"

        out_filename = f"updated_{stem_name}_{new_doc_id[:8]}.{fmt}"
        out_path = GENERATED_DIR / out_filename

        # 2. Export to DOCX or PDF
        if fmt == "docx":
            editor.export_to_docx(updated_markdown, str(out_path), title=f"Updated: {stem_name}")
        else:
            editor.export_to_pdf(updated_markdown, str(out_path), title=f"Updated: {stem_name}")

        # 3. Auto-index the new document if requested with user isolation
        indexed_chunks_count = 0
        if req.auto_index and out_path.exists():
            try:
                records = load_document(str(out_path))
                for record in records:
                    meta = record.get("metadata", {})
                    meta["document_id"] = new_doc_id
                    meta["source"] = out_filename
                    meta["user_email"] = user_email
                    record["metadata"] = meta
                new_chunks = chunk_text(records)
                for c in new_chunks:
                    c_meta = c.get("metadata", {})
                    c_meta["user_email"] = user_email
                    c["metadata"] = c_meta
                pipeline.ingest(new_chunks, user_email=user_email)
                indexed_chunks_count = len(new_chunks)
            except Exception as e:
                logger.error(f"Auto-index error for generated document: {e}")

        return {
            "status": "success",
            "filename": out_filename,
            "new_document_id": new_doc_id,
            "download_url": f"/document/download/{out_filename}",
            "updated_content": updated_markdown[:2000] + ("..." if len(updated_markdown) > 2000 else ""),
            "indexed_chunks": indexed_chunks_count,
        }
    except HTTPException:
        raise
    except GeminiServiceError as ge:
        logger.error(f"Gemini service error in /document/edit: {ge}")
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as e:
        logger.error(f"Error in /document/edit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate updated document: {str(e)}")


@app.get("/document/download/{filename}")
def download_generated_document(
    filename: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    safe_filename = Path(filename).name
    file_path = GENERATED_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if safe_filename.endswith(".docx")
        else "application/pdf"
    )
    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=safe_filename,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    )


# =========================================================
# 8. DOCUMENT MANAGEMENT & DELETE (User Scoped)
# =========================================================

@app.delete("/documents/{document_id}")
def delete_document_api(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    deleted = pipeline.store.delete_document(document_id, user_email=user_email)

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found or you do not have permission to delete it.")

    for file_path in UPLOAD_DIR.glob(f"{document_id}_*"):
        try:
            file_path.unlink()
        except Exception:
            pass

    return {
        "status": "success",
        "deleted_document_id": document_id,
        "message": "Document successfully deleted from your personal index and storage.",
    }


@app.get("/documents")
def list_documents(current_user: Dict[str, Any] = Depends(get_current_user)):
    try:
        user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
        return {"documents": pipeline.store.list_documents(user_email=user_email)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# 9. AUDIO UTILITIES (Authenticated)
# =========================================================

@app.get("/audio/{filename}")
def get_audio(
    filename: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    safe_filename = Path(filename).name
    file_path = AUDIO_OUT_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(str(file_path), media_type="audio/mpeg")


@app.post("/speak")
def speak_endpoint(
    req: Optional[SpeakRequest] = None,
    text: Optional[str] = None,
    language: str = "en",
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    target_text = ""
    target_lang = "en"
    if req and req.text:
        target_text = req.text
        target_lang = req.language or "en"
    elif text:
        target_text = text
        target_lang = language or "en"

    if not target_text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    import re
    clean_text = re.sub(r"<[^>]+>", " ", target_text)
    clean_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean_text)
    clean_text = re.sub(r"[*_#>`~]", " ", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    clean_text = clean_text[:1200]

    try:
        path = synthesize_speech(clean_text, target_lang, output_dir=str(AUDIO_OUT_DIR))
        return {"audio_path": path, "filename": Path(path).name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# 10. PROACTIVE ACTION & DEADLINE ALERT (User Scoped)
# =========================================================

@app.get("/document/{document_id}/action-alert")
def get_action_alert(
    document_id: str,
    language: str = "en",
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_email = current_user.get("email", "demo@docmind.ai").strip().lower()
    chunks = pipeline.store.get_document_chunks(document_id, user_email=user_email)
    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found or has no indexed content.")

    filename = chunks[0].get("source", "Document")
    full_text = "\n\n".join([c["text"] for c in chunks if c.get("text")])

    try:
        alert = intelligence.analyze_action_and_deadlines(
            document_text=full_text,
            filename=filename,
            language=language,
        )
        return {
            "status": "success",
            "document_id": document_id,
            "filename": filename,
            "action_alert": alert,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze actions: {e}")