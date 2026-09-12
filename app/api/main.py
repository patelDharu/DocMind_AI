# app/api/main.py

import json
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from app.core.loader import load_document
from app.core.chunker import chunk_text
from app.core.rag import RAGPipeline
from app.core.intelligence import DocumentIntelligence
from app.core.doc_editor import DocumentEditor
from app.core.speech import transcribe_audio
from app.core.tts import synthesize_speech
from app.core.resilience import GeminiServiceError

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

UPLOAD_DIR = Path("app/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

TEMP_AUDIO_DIR = Path("app/data/audio_in")
TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_OUT_DIR = Path("app/data/audio_out")
AUDIO_OUT_DIR.mkdir(parents=True, exist_ok=True)

GENERATED_DIR = Path("app/data/generated")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# REQUEST MODELS
# =========================================================

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
    edit_mode: str = "append"  # "append" (fast, lightweight, safe) or "revise"


# =========================================================
# ROOT & HEALTH ENDPOINTS
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
    }


# =========================================================
# 1. UPLOAD & INDEX DOCUMENT
# =========================================================

@app.post("/upload")
def upload_document(file: UploadFile = File(...)):
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

    document_id = uuid.uuid4().hex
    stored_filename = f"{document_id}_{original_filename}"
    dest = UPLOAD_DIR / stored_filename

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        records = load_document(str(dest))
        if not records:
            records = [{
                "text": f"Document: {original_filename}\n[Content processed]",
                "metadata": {
                    "source": original_filename,
                    "page": 1,
                    "char_count": len(original_filename),
                }
            }]

        for record in records:
            metadata = record.get("metadata", {})
            metadata["document_id"] = document_id
            metadata["source"] = original_filename
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
                }
            }]

        pipeline.ingest(chunks)

        # Proactively scan for actions, deadlines & consequences
        doc_text = "\n\n".join([r.get("text", "") for r in records if r.get("text")])
        action_alert = intelligence.analyze_action_and_deadlines(
            document_text=doc_text,
            filename=original_filename,
            language="en",
        )

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
# 2. ASK QUESTION (CHATGPT-STYLE MASTER RAG)
# =========================================================

@app.post("/ask")
def ask_question(req: QueryRequest):
    try:
        target_docs = req.document_ids or []
        if req.document_id and req.document_id not in target_docs:
            target_docs.append(req.document_id)

        result = pipeline.answer(
            question=req.question,
            top_k=req.top_k,
            lang_hint=req.lang_hint,
            document_ids=target_docs if target_docs else None,
            history=req.history,
        )
        return result
    except GeminiServiceError as ge:
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# 3. ASK BY VOICE (SPEECH -> RAG -> TTS)
# =========================================================

@app.post("/ask-voice")
def ask_voice_question(
    file: UploadFile = File(...),
    speak_reply: bool = True,
    document_ids: Optional[str] = None,
    history: Optional[str] = None,
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file missing.")

    temp_path = TEMP_AUDIO_DIR / f"{uuid.uuid4().hex}.wav"

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

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
# 8. DOCUMENT SUMMARIZATION
# =========================================================

@app.post("/summarize")
def summarize_doc(req: SummarizeRequest):
    chunks = pipeline.store.get_document_chunks(req.document_id)
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
# 9. DOCUMENT COMPARISON
# =========================================================

@app.post("/compare")
def compare_docs(req: CompareRequest):
    if len(req.document_ids) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 documents to compare.")

    chunks_a = pipeline.store.get_document_chunks(req.document_ids[0])
    chunks_b = pipeline.store.get_document_chunks(req.document_ids[1])

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
# 10. STRUCTURED INFORMATION EXTRACTION
# =========================================================

@app.post("/extract")
def extract_doc_data(req: ExtractRequest):
    chunks = pipeline.store.get_document_chunks(req.document_id)
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
# [NEW] DOCUMENT STUDIO: EDIT & EXPORT TO PDF/DOCX
# =========================================================

@app.post("/document/edit")
def edit_document(req: DocumentEditRequest):
    chunks = pipeline.store.get_document_chunks(req.document_id)
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

    # 3. Auto-index the new document if requested
    indexed_chunks_count = 0
    if req.auto_index and out_path.exists():
        try:
            records = load_document(str(out_path))
            for record in records:
                meta = record.get("metadata", {})
                meta["document_id"] = new_doc_id
                meta["source"] = out_filename
                record["metadata"] = meta
            new_chunks = chunk_text(records)
            pipeline.ingest(new_chunks)
            indexed_chunks_count = len(new_chunks)
        except Exception as e:
            print(f"Auto-index error for generated document: {e}")

    return {
        "status": "success",
        "filename": out_filename,
        "new_document_id": new_doc_id,
        "download_url": f"/document/download/{out_filename}",
        "updated_content": updated_markdown[:2000] + ("..." if len(updated_markdown) > 2000 else ""),
        "indexed_chunks": indexed_chunks_count,
    }


@app.get("/document/download/{filename}")
def download_generated_document(filename: str):
    safe_filename = Path(filename).name
    file_path = GENERATED_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if safe_filename.endswith(".docx") else "application/pdf"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=safe_filename,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    )


# =========================================================
# DOCUMENT MANAGEMENT & DELETE
# =========================================================

@app.delete("/documents/{document_id}")
def delete_document_api(document_id: str):
    deleted = pipeline.store.delete_document(document_id)

    for file_path in UPLOAD_DIR.glob(f"{document_id}_*"):
        try:
            file_path.unlink()
        except Exception:
            pass

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found or could not be removed.")

    return {
        "status": "success",
        "deleted_document_id": document_id,
        "message": "Document successfully deleted from vector index and storage.",
    }


@app.get("/documents")
def list_documents():
    try:
        return {"documents": pipeline.store.list_documents()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# AUDIO UTILITIES
# =========================================================

@app.get("/audio/{filename}")
def get_audio(filename: str):
    safe_filename = Path(filename).name
    file_path = AUDIO_OUT_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(str(file_path), media_type="audio/mpeg")


@app.post("/speak")
def speak_endpoint(text: str, language: str = "en"):
    try:
        path = synthesize_speech(text, language, output_dir=str(AUDIO_OUT_DIR))
        return {"audio_path": path, "filename": Path(path).name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================
# 10. PROACTIVE ACTION & DEADLINE ALERT ENDPOINT
# =========================================================

@app.get("/document/{document_id}/action-alert")
def get_action_alert(document_id: str, language: str = "en"):
    """
    Returns proactive action & deadline alert for an indexed document in English, Hindi, or Gujarati.
    """
    chunks = pipeline.store.get_document_chunks(document_id)
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