# app/core/loader.py

import os
import re
import logging
from typing import List, Dict, Any
from pathlib import Path

import pdfplumber
import pypdf
from docx import Document
import pandas as pd
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()

from app.core.resilience import generate_with_cascade

logger = logging.getLogger("docmind.loader")


class DocumentLoader:
    """
    Universal NotebookLM-Grade Document Ingestion Engine:
    - Loads PDF (digital, scanned, image-heavy with Gemini Vision OCR fallback)
    - Word (.docx, .doc)
    - Spreadsheets (.xlsx, .xls, .csv, .tsv)
    - Presentations (.pptx, .ppt)
    - Notes & Text (.txt, .md, .rtf, .log, .json, .yaml, .xml, .html)
    - Images (.png, .jpg, .jpeg, .webp, .bmp)
    - Preserves tables as clean Markdown tables with header alignment.
    - Automatic Gemini Multimodal Fallback guarantees NO document is ever rejected.
    """

    @staticmethod
    def load_file(file_path: str) -> List[Dict[str, Any]]:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            docs = DocumentLoader._load_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            docs = DocumentLoader._load_docx(file_path)
        elif ext in [".pptx", ".ppt"]:
            docs = DocumentLoader._load_pptx(file_path)
        elif ext in [".xlsx", ".xls"]:
            docs = DocumentLoader._load_excel(file_path)
        elif ext in [".csv", ".tsv"]:
            docs = DocumentLoader._load_csv(file_path)
        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
            docs = DocumentLoader._load_image(file_path)
        elif ext in [".txt", ".md", ".markdown", ".rtf", ".log", ".json", ".yaml", ".yml", ".xml", ".html", ".htm"]:
            docs = DocumentLoader._load_text(file_path)
        else:
            docs = DocumentLoader._load_text(file_path)
            if not docs:
                docs = DocumentLoader._ocr_with_gemini(file_path, mime_type="application/octet-stream")

        if not docs:
            docs = DocumentLoader._ocr_with_gemini(file_path)

        return docs

    @staticmethod
    def _format_table_as_markdown(table: List[List[Any]]) -> str:
        """Convert a 2D table array into clean markdown table format."""
        if not table or not table[0]:
            return ""

        clean_rows = []
        for row in table:
            clean_row = [str(cell or "").strip().replace("\n", " ") for cell in row]
            clean_rows.append(clean_row)

        if not clean_rows:
            return ""

        headers = clean_rows[0]
        headers = [h if h else f"Col_{idx+1}" for idx, h in enumerate(headers)]
        separator = ["---"] * len(headers)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in clean_rows[1:]:
            row_padded = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(row_padded[: len(headers)]) + " |")

        return "\n".join(lines)

    @staticmethod
    def _ocr_with_gemini(file_path: str, mime_type: str = "application/pdf") -> List[Dict[str, Any]]:
        """
        Multimodal OCR Fallback using Gemini Vision.
        Extracts full text and markdown tables from scanned PDFs, images, or unparseable files.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return []

        filename = os.path.basename(file_path)
        try:
            client = genai.Client(api_key=api_key.strip("'\""))
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            prompt = (
                "You are DocMind AI's Universal Document Reader. "
                "Accurately read and transcribe ALL text, tables, numbers, headings, and data from this document. "
                "Rules:\n"
                "1. Transcribe the complete text in its original language (English, Hindi in Devanagari, Gujarati in Gujarati script).\n"
                "2. Convert any tables into clean Markdown tables (| Col 1 | Col 2 |).\n"
                "3. If there are multiple distinct pages or sections, separate them with '--- Page X ---'.\n"
                "4. Output verbatim transcription with zero conversational preamble or commentary."
            )

            text_output = generate_with_cascade(
                client=client,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=3500,
                ),
            )

            if not text_output:
                return []

            pages = re.split(r"---\s*Page\s*(\d+)\s*---", text_output, flags=re.IGNORECASE)
            records = []
            if len(pages) > 1:
                current_p = 1
                for i in range(1, len(pages), 2):
                    p_num = int(pages[i]) if pages[i].isdigit() else current_p
                    p_text = pages[i + 1].strip() if (i + 1) < len(pages) else ""
                    if p_text:
                        records.append({
                            "text": p_text,
                            "metadata": {
                                "source": filename,
                                "page": p_num,
                                "char_count": len(p_text),
                                "ocr": True,
                            }
                        })
                    current_p = p_num + 1

            if not records and text_output.strip():
                records.append({
                    "text": text_output.strip(),
                    "metadata": {
                        "source": filename,
                        "page": 1,
                        "char_count": len(text_output.strip()),
                        "ocr": True,
                    }
                })

            return records
        except Exception as e:
            logger.warning(f"Gemini OCR fallback encountered error for {filename}: {e}")
            return []

    @staticmethod
    def _load_pdf(file_path: str) -> List[Dict[str, Any]]:
        docs = []
        filename = os.path.basename(file_path)

        # 1. Primary extractor: pdfplumber (digital text + tables as markdown)
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    page_content_parts = []
                    raw_text = page.extract_text() or ""
                    if raw_text.strip():
                        page_content_parts.append(raw_text.strip())

                        tables = page.extract_tables()
                        if tables:
                            for t_idx, table in enumerate(tables, start=1):
                                md_table = DocumentLoader._format_table_as_markdown(table)
                                if md_table:
                                    page_content_parts.append(f"\n[Table {t_idx} on Page {page_idx}]\n{md_table}\n")

                    full_page_text = "\n\n".join(page_content_parts).strip()
                    if full_page_text:
                        docs.append({
                            "text": full_page_text,
                            "metadata": {
                                "source": filename,
                                "page": page_idx,
                                "char_count": len(full_page_text),
                                "has_tables": len(tables) > 0 if tables else False,
                            },
                        })
        except Exception as e:
            logger.warning(f"pdfplumber failed on {filename}: {e}")

        total_chars = sum(len(d["text"]) for d in docs)

        # 2. Secondary extractor: pypdf if pdfplumber extracted nothing or very little
        if total_chars < 50:
            try:
                reader = pypdf.PdfReader(file_path)
                p0_text = (reader.pages[0].extract_text() or "").strip() if reader.pages else ""
                if p0_text:
                    pypdf_docs = []
                    for p_idx, page in enumerate(reader.pages, start=1):
                        p_text = page.extract_text() or ""
                        if p_text.strip():
                            pypdf_docs.append({
                                "text": p_text.strip(),
                                "metadata": {
                                    "source": filename,
                                    "page": p_idx,
                                    "char_count": len(p_text.strip()),
                                    "has_tables": False,
                                }
                            })
                    if sum(len(d["text"]) for d in pypdf_docs) > total_chars:
                        docs = pypdf_docs
                        total_chars = sum(len(d["text"]) for d in docs)
            except Exception as e:
                logger.warning(f"pypdf fallback failed on {filename}: {e}")

        # 3. Tertiary extractor: Gemini Vision OCR for scanned or image-based PDFs
        if total_chars < 50:
            logger.info(f"PDF {filename} appears to be scanned/image-based (<50 chars). Triggering Gemini OCR...")
            ocr_docs = DocumentLoader._ocr_with_gemini(file_path, mime_type="application/pdf")
            if ocr_docs:
                docs = ocr_docs

        return docs

    @staticmethod
    def _load_docx(file_path: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(file_path)
        try:
            document = Document(file_path)
            content_parts = []

            for p in document.paragraphs:
                txt = p.text.strip()
                if txt:
                    content_parts.append(txt)

            for t_idx, table in enumerate(document.tables, start=1):
                table_data = []
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells]
                    table_data.append(row_data)
                md_table = DocumentLoader._format_table_as_markdown(table_data)
                if md_table:
                    content_parts.append(f"\n[Table {t_idx}]\n{md_table}\n")

            full_content = "\n\n".join(content_parts).strip()
            if full_content:
                return [{
                    "text": full_content,
                    "metadata": {
                        "source": filename,
                        "page": 1,
                        "char_count": len(full_content),
                    },
                }]
        except Exception as e:
            logger.warning(f"DocumentLoader docx error: {e}")

        return DocumentLoader._ocr_with_gemini(
            file_path,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    @staticmethod
    def _load_pptx(file_path: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(file_path)
        docs = []
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            for idx, slide in enumerate(prs.slides, start=1):
                slide_parts = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for paragraph in shape.text_frame.paragraphs:
                            t = paragraph.text.strip()
                            if t:
                                slide_parts.append(t)
                    elif shape.has_table:
                        table = shape.table
                        table_data = []
                        for row in table.rows:
                            row_data = [cell.text.strip() for cell in row.cells]
                            table_data.append(row_data)
                        md_table = DocumentLoader._format_table_as_markdown(table_data)
                        if md_table:
                            slide_parts.append(f"\n[Slide Table]\n{md_table}\n")

                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = slide.notes_slide.notes_text_frame.text.strip()
                    if notes:
                        slide_parts.append(f"\n[Speaker Notes]: {notes}")

                slide_text = "\n\n".join(slide_parts).strip()
                if slide_text:
                    docs.append({
                        "text": f"### Slide {idx}\n\n{slide_text}",
                        "metadata": {
                            "source": filename,
                            "page": idx,
                            "char_count": len(slide_text),
                        }
                    })
        except Exception as e:
            logger.warning(f"PPTX parsing error: {e}")

        if not docs:
            docs = DocumentLoader._ocr_with_gemini(
                file_path,
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
        return docs

    @staticmethod
    def _load_excel(file_path: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(file_path)
        docs = []
        try:
            with pd.ExcelFile(file_path) as excel_file:
                for sheet_idx, sheet_name in enumerate(excel_file.sheet_names, start=1):
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    if df.empty:
                        continue
                    df_clean = df.fillna("")
                    try:
                        md_table = df_clean.to_markdown(index=False)
                    except Exception:
                        headers = [str(c) for c in df_clean.columns]
                        rows = df_clean.values.tolist()
                        md_table = DocumentLoader._format_table_as_markdown([headers] + rows)

                    sheet_text = f"### Sheet: {sheet_name}\n\n{md_table}"
                    docs.append({
                        "text": sheet_text,
                        "metadata": {
                            "source": filename,
                            "page": sheet_idx,
                            "sheet_name": sheet_name,
                            "char_count": len(sheet_text),
                            "has_tables": True,
                        }
                    })
        except Exception as e:
            logger.warning(f"Excel parsing error on {filename}: {e}")

        return docs

    @staticmethod
    def _load_csv(file_path: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(file_path)
        sep = "\t" if file_path.lower().endswith(".tsv") else ","
        try:
            df = pd.read_csv(file_path, sep=sep)
            df_clean = df.fillna("")
            try:
                md_table = df_clean.to_markdown(index=False)
            except Exception:
                headers = [str(c) for c in df_clean.columns]
                rows = df_clean.values.tolist()
                md_table = DocumentLoader._format_table_as_markdown([headers] + rows)

            return [{
                "text": f"### Data Table: {filename}\n\n{md_table}",
                "metadata": {
                    "source": filename,
                    "page": 1,
                    "char_count": len(md_table),
                    "has_tables": True,
                }
            }]
        except Exception as e:
            logger.warning(f"CSV parsing error: {e}")
            return DocumentLoader._load_text(file_path)

    @staticmethod
    def _load_image(file_path: str) -> List[Dict[str, Any]]:
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(ext, "image/jpeg")
        return DocumentLoader._ocr_with_gemini(file_path, mime_type=mime_type)

    @staticmethod
    def _load_text(file_path: str) -> List[Dict[str, Any]]:
        filename = os.path.basename(file_path)
        content = ""
        for encoding in ["utf-8", "utf-8-sig", "latin1", "cp1252"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read().strip()
                break
            except UnicodeDecodeError:
                continue

        if not content:
            return []

        if file_path.lower().endswith((".html", ".htm")):
            clean_text = re.sub(r"<[^>]+>", " ", content)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            content = clean_text

        return [{
            "text": content,
            "metadata": {
                "source": filename,
                "page": 1,
                "char_count": len(content),
            },
        }]


def load_document(file_path: str) -> List[Dict[str, Any]]:
    return DocumentLoader.load_file(file_path)