import os
from typing import List, Dict, Any

import pdfplumber
from docx import Document


class DocumentLoader:
    """
    Loads PDF, DOCX, TXT and Markdown files.

    Returns page/document-level text with metadata
    that can be used by the chunking and RAG pipeline.
    """

    @staticmethod
    def load_file(file_path: str) -> List[Dict[str, Any]]:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return DocumentLoader._load_pdf(file_path)

        elif ext in [".docx"]:
            return DocumentLoader._load_docx(file_path)

        elif ext in [".txt", ".md"]:
            return DocumentLoader._load_text(file_path)

        else:
            raise ValueError(
                f"Unsupported file format: {ext}. "
                "Supported formats: PDF, DOCX, TXT, MD."
            )

    @staticmethod
    def _load_pdf(file_path: str) -> List[Dict[str, Any]]:
        docs = []

        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""

                if text.strip():
                    docs.append({
                        "text": text,
                        "metadata": {
                            "source": os.path.basename(file_path),
                            "page": page_idx,
                            "char_count": len(text),
                        },
                    })

        return docs

    @staticmethod
    def _load_docx(file_path: str) -> List[Dict[str, Any]]:
        document = Document(file_path)

        paragraphs = [
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        content = "\n".join(paragraphs)

        if not content.strip():
            return []

        return [{
            "text": content,
            "metadata": {
                "source": os.path.basename(file_path),
                "page": 1,
                "char_count": len(content),
            },
        }]

    @staticmethod
    def _load_text(file_path: str) -> List[Dict[str, Any]]:
        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:
            content = f.read()

        if not content.strip():
            return []

        return [{
            "text": content,
            "metadata": {
                "source": os.path.basename(file_path),
                "page": 1,
                "char_count": len(content),
            },
        }]


def load_document(file_path: str) -> List[Dict[str, Any]]:
    """
    Backward-compatible helper used by the API/RAG pipeline.

    Example:
        documents = load_document("app/data/uploads/file.pdf")
    """
    return DocumentLoader.load_file(file_path)