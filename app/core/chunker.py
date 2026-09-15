# app/core/chunker.py

import hashlib
from typing import List, Dict, Any
def _recursive_split_text(
    text: str,
    chunk_size: int = 1400,
    chunk_overlap: int = 200,
    separators: List[str] | None = None,
) -> List[str]:
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    if separators is None:
        separators = ["\n\n", "\n", "|---", ". ", " ", ""]

    def _split(text_block: str, sep_index: int) -> List[str]:
        if len(text_block) <= chunk_size:
            return [text_block.strip()] if text_block.strip() else []

        if sep_index >= len(separators):
            step = max(1, chunk_size - chunk_overlap)
            return [
                text_block[i:i + chunk_size].strip()
                for i in range(0, len(text_block), step)
                if text_block[i:i + chunk_size].strip()
            ]

        sep = separators[sep_index]
        splits = text_block.split(sep) if sep else list(text_block)

        chunks = []
        current_chunk = []
        current_len = 0

        for s in splits:
            item = s + (sep if sep else "")
            item_len = len(item)

            if current_len + item_len > chunk_size and current_chunk:
                merged = "".join(current_chunk).strip()
                if len(merged) > chunk_size:
                    chunks.extend(_split(merged, sep_index + 1))
                elif merged:
                    chunks.append(merged)

                overlap_chunk = []
                overlap_len = 0
                for prev in reversed(current_chunk):
                    if overlap_len + len(prev) <= chunk_overlap:
                        overlap_chunk.insert(0, prev)
                        overlap_len += len(prev)
                    else:
                        break
                current_chunk = overlap_chunk
                current_len = overlap_len

            current_chunk.append(item)
            current_len += item_len

        if current_chunk:
            merged = "".join(current_chunk).strip()
            if len(merged) > chunk_size:
                chunks.extend(_split(merged, sep_index + 1))
            elif merged:
                chunks.append(merged)

        return [c for c in chunks if c]

    return _split(text, 0)


def chunk_text(
    documents: List[Dict[str, Any]],
    chunk_size: int = 1400,
    chunk_overlap: int = 200,
) -> List[Dict[str, Any]]:
    """
    Split loaded documents into overlapping chunks while preserving
    document_id, table structure, and page references for accurate citations.
    Ultra-lightweight pure Python implementation (0MB extra overhead vs 400MB LangChain).
    """
    chunks = []

    for document in documents:
        text = document.get("text", "").strip()
        metadata = document.get("metadata", {}).copy()

        if not text:
            continue

        split_texts = _recursive_split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for chunk_index, chunk in enumerate(split_texts):
            chunk = chunk.strip()
            if not chunk:
                continue

            source = str(metadata.get("source", "unknown"))
            page = int(metadata.get("page", 1))
            document_id = str(metadata.get("document_id", source))

            unique_string = (
                f"{document_id}|{source}|{page}|{chunk_index}|{chunk}"
            )
            chunk_id = hashlib.sha256(unique_string.encode("utf-8")).hexdigest()[:16]

            chunk_metadata = metadata.copy()
            chunk_metadata["document_id"] = document_id
            chunk_metadata["chunk"] = chunk_index
            chunk_metadata["char_count"] = len(chunk)
            chunk_metadata["page"] = page
            chunk_metadata["source"] = source

            chunks.append({
                "id": f"{chunk_id}_chunk_{chunk_index}",
                "text": chunk,
                "metadata": chunk_metadata,
            })

    return chunks