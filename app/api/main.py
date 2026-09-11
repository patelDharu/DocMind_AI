# app/api/main.py

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from app.core.loader import load_document
from app.core.chunker import chunk_text
from app.core.rag import RAGPipeline
from app.core.speech import transcribe_audio
from app.core.tts import synthesize_speech


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="DocMind AI",
    description="Trilingual Document Intelligence with RAG",
)

pipeline = RAGPipeline()


# =========================================================
# DIRECTORIES
# =========================================================

UPLOAD_DIR = Path("app/data/uploads")
UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TEMP_AUDIO_DIR = Path("app/data/audio_in")
TEMP_AUDIO_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

AUDIO_OUT_DIR = Path("app/data/audio_out")
AUDIO_OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# REQUEST MODELS
# =========================================================

class QueryRequest(BaseModel):
    question: str

    top_k: int = 8

    lang_hint: str | None = None

    # Unique ID of selected document.
    #
    # If provided:
    #     Search ONLY this document.
    #
    # If None:
    #     Search all documents.
    document_id: str | None = None


# =========================================================
# UPLOAD DOCUMENT
# =========================================================

@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):
    """
    Upload and index a new document.

    Every uploaded document receives a unique document_id.
    """

    # -----------------------------------------------------
    # Validate filename
    # -----------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is missing.",
        )

    original_filename = Path(
        file.filename
    ).name

    allowed_extensions = {
        ".pdf",
        ".docx",
        ".txt",
        ".md",
    }

    extension = Path(
        original_filename
    ).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Use PDF, DOCX, TXT, or MD."
            ),
        )

    # -----------------------------------------------------
    # Generate unique document ID
    # -----------------------------------------------------

    document_id = uuid.uuid4().hex

    # -----------------------------------------------------
    # Store physical file with unique name
    # -----------------------------------------------------

    stored_filename = (
        f"{document_id}_{original_filename}"
    )

    dest = UPLOAD_DIR / stored_filename

    try:

        with open(dest, "wb") as f:
            shutil.copyfileobj(
                file.file,
                f,
            )

        # -------------------------------------------------
        # Load document
        # -------------------------------------------------

        records = load_document(
            str(dest)
        )

        if not records:
            raise ValueError(
                "No readable text was found in the document."
            )

        # -------------------------------------------------
        # Add document metadata
        # -------------------------------------------------

        for record in records:

            metadata = record.get(
                "metadata",
                {}
            )

            metadata["document_id"] = document_id

            # Keep the original filename for display.
            metadata["source"] = original_filename

            record["metadata"] = metadata

        # -------------------------------------------------
        # Create chunks
        # -------------------------------------------------

        chunks = chunk_text(
            records
        )

        if not chunks:
            raise ValueError(
                "No chunks could be created from the document."
            )

        # -------------------------------------------------
        # Index chunks
        # -------------------------------------------------

        pipeline.ingest(
            chunks
        )

    except Exception as e:

        # Remove uploaded file if indexing failed.
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "status": "success",
        "filename": original_filename,
        "document_id": document_id,
        "chunks_indexed": len(chunks),
    }


# =========================================================
# ASK QUESTION
# =========================================================

@app.post("/ask")
async def ask_question(
    req: QueryRequest
):
    """
    Ask a typed question.

    If document_id is supplied, only that document
    will be searched.
    """

    try:

        result = pipeline.answer(
            question=req.question,
            top_k=req.top_k,
            lang_hint=req.lang_hint,
            document_id=req.document_id,
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# =========================================================
# ASK BY VOICE
# =========================================================

@app.post("/ask-voice")
async def ask_voice_question(
    file: UploadFile = File(...),
    speak_reply: bool = True,
    document_id: str | None = None,
):
    """
    Voice question.

    The transcribed question is searched inside
    the selected document when document_id is provided.
    """

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Audio filename is missing.",
        )

    # -----------------------------------------------------
    # Unique temporary audio filename
    # -----------------------------------------------------

    temp_filename = (
        f"{uuid.uuid4().hex}.wav"
    )

    temp_path = (
        TEMP_AUDIO_DIR / temp_filename
    )

    try:

        # -------------------------------------------------
        # Save audio
        # -------------------------------------------------

        with open(temp_path, "wb") as f:
            shutil.copyfileobj(
                file.file,
                f,
            )

        # -------------------------------------------------
        # Speech → Text
        # -------------------------------------------------

        transcription = transcribe_audio(
            str(temp_path)
        )

        question_text = transcription.get(
            "text",
            ""
        ).strip()

        detected_lang = transcription.get(
            "language",
            "en"
        )

        if not question_text:
            raise ValueError(
                "Could not understand the recorded question."
            )

        # -------------------------------------------------
        # RAG
        # -------------------------------------------------

        result = pipeline.answer(
            question=question_text,
            top_k=8,
            lang_hint=detected_lang,
            document_id=document_id,
        )

        # -------------------------------------------------
        # Add voice information
        # -------------------------------------------------

        result["transcribed_question"] = (
            question_text
        )

        result["detected_language"] = (
            detected_lang
        )

        # -------------------------------------------------
        # Text → Speech
        # -------------------------------------------------

        if speak_reply:

            audio_path = synthesize_speech(
                result["answer"],
                detected_lang,
                output_dir=str(
                    AUDIO_OUT_DIR
                ),
            )

            result["audio_reply_path"] = (
                audio_path
            )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    finally:

        # -------------------------------------------------
        # Delete temporary audio
        # -------------------------------------------------

        if temp_path.exists():

            try:
                temp_path.unlink()
            except Exception:
                pass


# =========================================================
# SERVE GENERATED AUDIO
# =========================================================

@app.get("/audio/{filename}")
async def get_audio(
    filename: str
):
    """
    Serve generated TTS audio.
    """

    safe_filename = Path(
        filename
    ).name

    file_path = (
        AUDIO_OUT_DIR /
        safe_filename
    )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Audio file not found.",
        )

    return FileResponse(
        str(file_path),
        media_type="audio/mpeg",
    )


# =========================================================
# TEXT → SPEECH
# =========================================================

@app.post("/speak")
async def speak_text(
    text: str,
    language: str = "en",
):
    """
    Generate speech from text.
    """

    try:

        audio_path = synthesize_speech(
            text,
            language,
            output_dir=str(
                AUDIO_OUT_DIR
            ),
        )

        return {
            "audio_path": audio_path,
            "filename": Path(
                audio_path
            ).name,
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

# =========================================================
# LIST INDEXED DOCUMENTS
# =========================================================

@app.get("/documents")
async def list_documents():
    """
    Return all documents currently indexed.
    """

    try:

        documents = pipeline.store.list_documents()

        return {
            "documents": documents
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
async def health():
    return {
        "status": "ok"
    }