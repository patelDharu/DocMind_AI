import hashlib
from typing import List, Dict, Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(
    documents: List[Dict[str, Any]],
    chunk_size: int = 1800,
    chunk_overlap: int = 250
) -> List[Dict[str, Any]]:
    """
    Split loaded documents into overlapping chunks.

    Each chunk keeps the document_id so retrieval can later
    filter results by the currently selected document.
    """

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    chunks = []

    for document in documents:
        text = document.get("text", "").strip()
        metadata = document.get("metadata", {}).copy()

        if not text:
            continue

        split_texts = splitter.split_text(text)

        for chunk_index, chunk in enumerate(split_texts):
            chunk = chunk.strip()

            if not chunk:
                continue

            source = str(metadata.get("source", "unknown"))
            page = str(metadata.get("page", 1))

            # document_id must already be supplied by loader/API
            document_id = str(
                metadata.get("document_id", source)
            )

            unique_string = (
                f"{document_id}|{source}|{page}|"
                f"{chunk_index}|{chunk}"
            )

            chunk_id = hashlib.sha256(
                unique_string.encode("utf-8")
            ).hexdigest()[:16]

            chunk_metadata = metadata.copy()
            chunk_metadata["document_id"] = document_id
            chunk_metadata["chunk"] = chunk_index
            chunk_metadata["char_count"] = len(chunk)

            chunks.append({
                "id": f"{chunk_id}_chunk_{chunk_index}",
                "text": chunk,
                "metadata": chunk_metadata
            })

    return chunks