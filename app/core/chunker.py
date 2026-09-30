# app/core/chunker.py
"""
DocMind AI — Advanced Semantic Chunker
Features:
1. Semantic Section & Header Tracking (Markdown #, ##, ###, and numbered clauses).
2. Context Enrichment: Prepend section breadcrumbs so split chunks retain topic context.
3. Markdown Table Preservation: Keeps tables atomic; splits oversized tables row-by-row
   while re-attaching table headers to every chunk.
4. Trilingual Sentence Boundary Respect (English '. ', Hindi/Devanagari '। ', Gujarati '। ').
5. Sentence-aligned overlap: Prevents slicing words or numbers in half.
6. Rich metadata: section_title, has_table, estimated_tokens, char_count, page, document_id.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple


# Regex for detecting markdown headings and numbered legal/business sections
HEADING_REGEX = re.compile(
    r"^(#{1,6}\s+.+|(?:\d+\.){1,4}\s+[A-Z].+|ARTICLE\s+[IVXLCDM\d]+|SECTION\s+\d+|SCHEDULE\s+[A-Z\d]+)",
    re.IGNORECASE | re.MULTILINE,
)

# Regex for sentence boundaries supporting English, Hindi (।), Gujarati (।), and punctuation
SENTENCE_SPLIT_REGEX = re.compile(
    r"(?<=[.!?\u0964\u0965])\s+(?=[A-Z\u0900-\u097F\u0A80-\u0AFF\d\"'‘“])"
)

# Regex to detect markdown tables
TABLE_BLOCK_REGEX = re.compile(
    r"((?:^[ \t]*\|.+?\|[ \t]*\r?\n){2,}(?:^[ \t]*\|.+?\|[ \t]*(?:\r?\n|$))+)",
    re.MULTILINE,
)


def _is_table_block(text: str) -> bool:
    """Check if the text is primarily a markdown table."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    table_lines = sum(1 for line in lines if line.startswith("|") and line.endswith("|"))
    return table_lines >= len(lines) * 0.75


def _split_markdown_table(
    table_text: str,
    max_chunk_size: int = 1200,
    section_prefix: str = "",
) -> List[str]:
    """
    Splits large markdown tables by row while re-attaching the header and separator
    to each generated chunk. Guarantees column context is NEVER lost.
    """
    lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
    if len(lines) <= 2:
        return [table_text.strip()]

    header_lines = lines[:2]  # Header row and |---|---| separator row
    header_block = "\n".join(header_lines) + "\n"
    data_rows = lines[2:]

    chunks = []
    current_rows = []
    prefix = f"{section_prefix}\n" if section_prefix else ""
    base_len = len(prefix) + len(header_block)

    for row in data_rows:
        candidate_len = base_len + sum(len(r) + 1 for r in current_rows) + len(row) + 1
        if candidate_len > max_chunk_size and current_rows:
            chunk_content = prefix + header_block + "\n".join(current_rows)
            chunks.append(chunk_content.strip())
            current_rows = [row]
        else:
            current_rows.append(row)

    if current_rows:
        chunk_content = prefix + header_block + "\n".join(current_rows)
        chunks.append(chunk_content.strip())

    return chunks if chunks else [table_text.strip()]


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences while respecting trilingual terminators."""
    if not text or not text.strip():
        return []
    parts = SENTENCE_SPLIT_REGEX.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_paragraph(
    paragraph: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> List[str]:
    """
    Split a single paragraph into overlapping sentence chunks.
    Ensures breaks occur cleanly on sentence or clause boundaries.
    """
    if len(paragraph) <= chunk_size:
        return [paragraph.strip()]

    sentences = _split_into_sentences(paragraph)
    if len(sentences) <= 1:
        # Fallback to word splitting if sentences cannot be cleanly separated
        words = paragraph.split(" ")
        chunks = []
        current = []
        current_len = 0
        for w in words:
            if current_len + len(w) + 1 > chunk_size and current:
                chunks.append(" ".join(current).strip())
                # Overlap last few words
                overlap_words = []
                overlap_len = 0
                for ow in reversed(current):
                    if overlap_len + len(ow) + 1 <= chunk_overlap:
                        overlap_words.insert(0, ow)
                        overlap_len += len(ow) + 1
                    else:
                        break
                current = overlap_words + [w]
                current_len = sum(len(x) + 1 for x in current)
            else:
                current.append(w)
                current_len += len(w) + 1
        if current:
            chunks.append(" ".join(current).strip())
        return [c for c in chunks if c]

    chunks = []
    current_sentences = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len + 1 > chunk_size and current_sentences:
            chunks.append(" ".join(current_sentences).strip())

            # Sentence-aligned overlap
            overlap_sentences = []
            overlap_len = 0
            for prev_s in reversed(current_sentences):
                if overlap_len + len(prev_s) + 1 <= chunk_overlap:
                    overlap_sentences.insert(0, prev_s)
                    overlap_len += len(prev_s) + 1
                else:
                    break
            current_sentences = overlap_sentences + [sentence]
            current_len = sum(len(s) + 1 for s in current_sentences)
        else:
            current_sentences.append(sentence)
            current_len += s_len + 1

    if current_sentences:
        chunks.append(" ".join(current_sentences).strip())

    return [c for c in chunks if c]


def _recursive_split_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
    separators: Optional[List[str]] = None,
) -> List[str]:
    """
    Backward-compatible recursive text splitter with semantic hierarchy:
    Markdown headers -> Markdown tables -> Paragraphs -> Sentences -> Words.
    """
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    # Split into major structural blocks: double newlines
    blocks = text.split("\n\n")
    chunks = []
    current_chunk_parts = []
    current_len = 0
    current_section = ""

    for block in blocks:
        block_clean = block.strip()
        if not block_clean:
            continue

        # Check if block is a heading
        heading_match = HEADING_REGEX.match(block_clean)
        if heading_match:
            current_section = heading_match.group(0).strip("# ").strip()

        # Check if block is a Markdown table
        if _is_table_block(block_clean):
            # Flush existing accumulated parts
            if current_chunk_parts:
                chunks.append("\n\n".join(current_chunk_parts).strip())
                current_chunk_parts = []
                current_len = 0

            section_prefix = f"[Section: {current_section}]" if current_section else ""
            if len(block_clean) <= chunk_size:
                table_chunk = f"{section_prefix}\n{block_clean}".strip() if section_prefix else block_clean
                chunks.append(table_chunk)
            else:
                table_chunks = _split_markdown_table(
                    block_clean, max_chunk_size=chunk_size, section_prefix=section_prefix
                )
                chunks.extend(table_chunks)
            continue

        # If block fits in current chunk
        block_len = len(block_clean)
        if current_len + block_len + 2 <= chunk_size:
            current_chunk_parts.append(block_clean)
            current_len += block_len + 2
        else:
            # Block causes chunk to exceed chunk_size
            if current_chunk_parts:
                chunks.append("\n\n".join(current_chunk_parts).strip())
                current_chunk_parts = []
                current_len = 0

            # If the single block itself exceeds chunk_size, split by sentences
            if block_len > chunk_size:
                sub_chunks = _split_paragraph(
                    block_clean, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
                chunks.extend(sub_chunks)
            else:
                current_chunk_parts.append(block_clean)
                current_len = block_len

    if current_chunk_parts:
        chunks.append("\n\n".join(current_chunk_parts).strip())

    return [c for c in chunks if c and len(c.strip()) >= 15]


def chunk_text(
    documents: List[Dict[str, Any]],
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> List[Dict[str, Any]]:
    """
    Split loaded documents into overlapping chunks while preserving
    document_id, table structure, section titles, and page references for accurate citations.
    """
    chunks = []

    for document in documents:
        text = document.get("text", "").strip()
        metadata = document.get("metadata", {}).copy()

        if not text:
            continue

        source = str(metadata.get("source", "unknown"))
        page = int(metadata.get("page", 1))
        document_id = str(metadata.get("document_id", source))

        split_texts = _recursive_split_text(
            text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        total_in_doc = len(split_texts)
        for chunk_index, chunk in enumerate(split_texts):
            chunk = chunk.strip()
            if not chunk or len(chunk) < 10:
                continue

            # Detect section title if present
            section_title = None
            heading_match = HEADING_REGEX.search(chunk)
            if heading_match:
                section_title = heading_match.group(0).strip("# \t\r\n")

            has_table = _is_table_block(chunk) or ("|" in chunk and "---" in chunk)

            unique_string = f"{document_id}|{source}|{page}|{chunk_index}|{chunk[:100]}"
            chunk_id = hashlib.sha256(unique_string.encode("utf-8")).hexdigest()[:16]

            chunk_metadata = metadata.copy()
            chunk_metadata["document_id"] = document_id
            chunk_metadata["chunk"] = chunk_index
            chunk_metadata["total_chunks"] = total_in_doc
            chunk_metadata["char_count"] = len(chunk)
            chunk_metadata["estimated_tokens"] = max(1, len(chunk) // 4)
            chunk_metadata["page"] = page
            chunk_metadata["source"] = source
            chunk_metadata["has_table"] = has_table
            if section_title:
                chunk_metadata["section_title"] = section_title

            chunks.append({
                "id": f"{chunk_id}_chunk_{chunk_index}",
                "text": chunk,
                "metadata": chunk_metadata,
            })

    return chunks