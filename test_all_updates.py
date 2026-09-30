# test_all_updates.py
"""
Comprehensive verification test suite for:
1. ChromaDB dimension error: collection preservation (no deletion of shared collection).
2. Vector indexing: all chunks indexed (no 30-chunk capping or stride sampling).
3. PDF text quality & OCR fallback: detects CID font corruption, replacement characters, sparse headers.
4. Pluggable 3rd-Party Object Storage (S3 / Local backend).
5. Advanced Semantic Chunker (tables, sections, multilingual sentences).
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE_ROOT = Path(__file__).resolve().parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from dotenv import load_dotenv
load_dotenv(WORKSPACE_ROOT / ".env")


class TestVectorStoreDimensionSafety(unittest.TestCase):
    """Test Issue 1: VectorStore must NEVER delete collection on dimensionality mismatch."""

    def test_dimensionality_mismatch_does_not_delete_collection(self):
        from app.core.vectorstore import VectorStore

        vs = VectorStore(collection_name="test_safety_collection")

        # Mock collection and client
        mock_collection = MagicMock()
        mock_collection.add.side_effect = Exception("Dimensionality of input embeddings does not match collection")
        mock_client = MagicMock()

        vs.collection = mock_collection
        vs.client = mock_client
        vs.embedder = MagicMock()
        vs.embedder.embed_passages.return_value = [[0.1] * 768]

        sample_chunks = [{
            "id": "c1",
            "text": "sample text",
            "metadata": {"document_id": "doc1", "source": "test.txt", "page": 1, "chunk": 0}
        }]

        with self.assertRaises(ValueError) as ctx:
            vs.add_chunks(sample_chunks, user_email="test@docmind.ai")

        self.assertIn("Embedding dimension mismatch", str(ctx.exception))
        # Ensure delete_collection was NEVER called!
        mock_client.delete_collection.assert_not_called()
        print("  [OK] Issue 1 Verified: delete_collection was NOT called on dimension mismatch.")


class TestVectorIndexingFullCoverage(unittest.TestCase):
    """Test Issue 2: VectorStore must index ALL chunks (no 30-chunk limit)."""

    def test_large_chunk_set_is_not_capped_at_30(self):
        from app.core.vectorstore import VectorStore

        vs = VectorStore(collection_name="test_large_chunks_collection")

        # Create 75 chunks
        chunks = [
            {
                "id": f"chunk_{i}",
                "text": f"This is test chunk number {i} with substantial detailed text content.",
                "metadata": {"document_id": "large_doc", "source": "large.pdf", "page": i // 2 + 1, "chunk": i}
            }
            for i in range(75)
        ]

        mock_collection = MagicMock()
        mock_collection.add.return_value = None
        vs.collection = mock_collection
        vs.embedder = MagicMock()
        vs.embedder.embed_passages.return_value = [[0.1] * 768 for _ in range(75)]

        vs.add_chunks(chunks, user_email="full_index@docmind.ai")

        # Verify that all 75 chunks were passed to embedder
        texts_passed = vs.embedder.embed_passages.call_args[0][0]
        self.assertEqual(len(texts_passed), 75, f"Expected 75 chunks embedded, got {len(texts_passed)}")

        # Verify collection.add received all 75 chunks across batches
        total_added_ids = 0
        for call in mock_collection.add.call_args_list:
            total_added_ids += len(call[1]["ids"])
        self.assertEqual(total_added_ids, 75, f"Expected 75 chunks added to Chroma, got {total_added_ids}")
        print("  [OK] Issue 2 Verified: All 75 chunks embedded and added to ChromaDB (no 30-chunk cap).")


class TestLoaderOCRQualityChecks(unittest.TestCase):
    """Test Issue 3: OCR fallback triggers on CID corruption, replacement characters, and sparse text."""

    def test_text_quality_evaluator(self):
        from app.core.loader import DocumentLoader

        # 1. Clean valid text -> Should NOT trigger OCR
        clean_docs = [{
            "text": "DocMind AI is an enterprise trilingual document intelligence platform supporting PDF, Word, Excel, and PPTX."
        }]
        is_garbled, reason = DocumentLoader._is_garbled_or_insufficient(clean_docs, total_pages=1)
        self.assertFalse(is_garbled, f"Clean text should not be flagged as garbled: {reason}")

        # 2. Font encoding CID corruption -> Should trigger OCR
        cid_docs = [{
            "text": "Report Header: (cid:10) (cid:25) (cid:33) (cid:45) (cid:52) (cid:61) (cid:78) (cid:89) (cid:92)"
        }]
        is_garbled, reason = DocumentLoader._is_garbled_or_insufficient(cid_docs, total_pages=1)
        self.assertTrue(is_garbled)
        self.assertIn("CID", reason)

        # 3. Unicode replacement characters -> Should trigger OCR
        rep_docs = [{
            "text": "This is a document with broken encoding \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd \ufffd characters."
        }]
        is_garbled, reason = DocumentLoader._is_garbled_or_insufficient(rep_docs, total_pages=1)
        self.assertTrue(is_garbled)
        self.assertIn("replacement", reason)

        # 4. Multi-page document with only headers on each page (< 40 chars/page on 5 pages)
        sparse_docs = [
            {"text": f"Page {i} Header"} for i in range(1, 6)
        ]
        is_garbled, reason = DocumentLoader._is_garbled_or_insufficient(sparse_docs, total_pages=5)
        self.assertTrue(is_garbled)
        self.assertIn("Sparse page content", reason)

        print("  [OK] Issue 3 Verified: Broken font encodings, CID artifacts, and sparse headers trigger OCR fallback.")


class TestStorageBackend(unittest.TestCase):
    """Test Suggestion A: 3rd-party object storage abstraction."""

    def test_local_storage_backend(self):
        from app.core.storage import LocalStorageBackend

        temp_dir = WORKSPACE_ROOT / "app" / "data" / "test_storage_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        storage = LocalStorageBackend(root_dir=temp_dir)

        test_content = b"DocMind Test Storage Content"
        meta = storage.upload_file(
            file_data=test_content,
            filename="sample_test_doc.txt",
            document_id="doc_abc123",
            user_email="tester@docmind.ai",
        )

        self.assertTrue(storage.exists(meta["storage_key"]))
        read_back = storage.read_bytes(meta["storage_key"])
        self.assertEqual(read_back, test_content)

        # Delete by document_id
        deleted_count = storage.delete_document_files("doc_abc123")
        self.assertGreaterEqual(deleted_count, 1)
        self.assertFalse(storage.exists(meta["storage_key"]))

        # Cleanup test dir
        try:
            temp_dir.rmdir()
        except Exception:
            pass
        print("  [OK] Suggestion A Verified: Storage backend correctly uploads, reads, and deletes document files.")

    def test_s3_storage_initialization_guard(self):
        from app.core.storage import S3StorageBackend
        # Without bucket configured, should raise informative ValueError
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                S3StorageBackend(bucket_name=None)
        print("  [OK] Suggestion A Verified: S3 storage cleanly validates bucket configuration.")


class TestAdvancedChunker(unittest.TestCase):
    """Test Suggestion B: Advanced semantic chunker."""

    def test_markdown_table_integrity(self):
        from app.core.chunker import chunk_text

        doc_with_table = [{
            "text": (
                "# Financial Summary\n\n"
                "Here is the revenue breakdown for Q3:\n\n"
                "| Department | Revenue | Growth |\n"
                "|---|---|---|\n"
                "| Engineering | $1.2M | +15% |\n"
                "| Sales | $3.5M | +24% |\n"
                "| Marketing | $800K | +8% |\n\n"
                "Conclusion: All targets exceeded successfully."
            ),
            "metadata": {"source": "report.md", "page": 1, "document_id": "rep_001"}
        }]

        chunks = chunk_text(doc_with_table, chunk_size=300)
        self.assertGreaterEqual(len(chunks), 1)

        # Verify table chunk has has_table=True
        table_chunk = next((c for c in chunks if c["metadata"].get("has_table")), None)
        self.assertIsNotNone(table_chunk, "Table was not recognized in chunk metadata")
        self.assertIn("| Department | Revenue | Growth |", table_chunk["text"])
        self.assertIn("section_title", table_chunk["metadata"])

        print("  [OK] Suggestion B Verified: Semantic chunker preserved markdown table structure and section metadata.")


if __name__ == "__main__":
    unittest.main()
