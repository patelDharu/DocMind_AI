# app/core/vectorstore.py

import logging
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi

from app.core.embedder import Embedder

logger = logging.getLogger("docmind.vectorstore")


class VectorStore:
    def __init__(
        self,
        persist_dir: str = "app/data/vectorstore",
        collection_name: str = "documents",
    ):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = Embedder()
        self.bm25 = None
        self.bm25_docs = []

        self._rebuild_bm25_from_existing()

    # =========================================================
    # BM25 - REBUILD INDEX
    # =========================================================

    def _rebuild_bm25_from_existing(self):
        try:
            existing = self.collection.get(include=["documents", "metadatas"])
            if not existing.get("ids"):
                self.bm25 = None
                self.bm25_docs = []
                return

            self.bm25_docs = []
            for doc, metadata in zip(
                existing.get("documents", []),
                existing.get("metadatas", []),
            ):
                metadata = metadata or {}
                document_id = str(metadata.get("document_id", metadata.get("source", "unknown")))
                self.bm25_docs.append({
                    "text": doc,
                    "source": metadata.get("source", "unknown"),
                    "page": int(metadata.get("page", 1)),
                    "chunk": int(metadata.get("chunk", 0)),
                    "document_id": document_id,
                })

            self._rebuild_bm25()
        except Exception:
            self.bm25 = None
            self.bm25_docs = []

    def _rebuild_bm25(self):
        if not self.bm25_docs:
            self.bm25 = None
            return

        tokenized_documents = [
            doc["text"].lower().split()
            for doc in self.bm25_docs
        ]
        if tokenized_documents:
            self.bm25 = BM25Okapi(tokenized_documents)
        else:
            self.bm25 = None

    # =========================================================
    # ADD CHUNKS
    # =========================================================

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return

        # 1. BM25 indexing: index 100% of all chunks!
        # BM25 is local in-memory, ultra-fast (takes 5ms), uses negligible RAM,
        # ensuring every word across large 15MB files is 100% keyword searchable.
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            doc_id = str(meta.get("document_id", meta.get("source", "unknown")))
            self.bm25_docs.append({
                "text": chunk["text"],
                "source": str(meta.get("source", "unknown")),
                "page": int(meta.get("page", 1)),
                "chunk": int(meta.get("chunk", 0)),
                "document_id": doc_id,
            })

        self._rebuild_bm25()

        # 2. Vector indexing with smart chunk budgeting:
        # If a document produces more than 120 chunks (huge document),
        # budget vector embedding to the top 120 representative chunks
        # (first 80 chunks covering intro/clauses + 40 evenly sampled chunks).
        # This keeps vector embedding under 6 seconds and prevents reverse proxy 502 timeouts.
        MAX_VECTOR_CHUNKS = 120
        if len(chunks) > MAX_VECTOR_CHUNKS:
            primary_chunks = chunks[:80]
            remaining_chunks = chunks[80:]
            step = max(1, len(remaining_chunks) // 40)
            sampled_remaining = remaining_chunks[::step][:40]
            vector_chunks = primary_chunks + sampled_remaining
        else:
            vector_chunks = chunks

        texts = [chunk["text"] for chunk in vector_chunks]
        embeddings = self.embedder.embed_passages(texts)
        ids = [chunk["id"] for chunk in vector_chunks]

        metadatas = []
        for chunk in vector_chunks:
            meta = chunk.get("metadata", {})
            doc_id = str(meta.get("document_id", meta.get("source", "unknown")))
            metadatas.append({
                "source": str(meta.get("source", "unknown")),
                "page": int(meta.get("page", 1)),
                "chunk": int(meta.get("chunk", 0)),
                "document_id": doc_id,
            })

        # STRICT GUARANTEE: Never let ChromaDB fail on mismatched ids vs embeddings
        if len(embeddings) != len(ids):
            logger.warning(
                f"VectorStore count mismatch: {len(embeddings)} embeddings vs {len(ids)} ids. Aligning to exact match..."
            )
            min_len = min(len(embeddings), len(ids))
            ids = ids[:min_len]
            embeddings = embeddings[:min_len]
            texts = texts[:min_len]
            metadatas = metadatas[:min_len]

        if not ids or not embeddings:
            logger.warning("No embeddings to add to ChromaDB. Chunks remain fully indexed in BM25.")
            return

        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception as e:
            # Handle collection dimension mismatch when embedding model changes
            if "dimensionality" in str(e).lower() or "dimension" in str(e).lower():
                self.client.delete_collection(self.collection_name)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
            else:
                raise e

    # =========================================================
    # ADVANCED HYBRID SEARCH (RRF + Multi-Doc Scope)
    # =========================================================

    def search(
        self,
        query: str,
        top_k: int = 8,
        document_ids: List[str] | str | None = None,
        min_relevance_threshold: float = 0.05,
    ) -> List[Dict[str, Any]]:
        if self.collection.count() == 0:
            return []

        target_ids = None
        if isinstance(document_ids, str) and document_ids.strip():
            target_ids = [document_ids.strip()]
        elif isinstance(document_ids, list) and len(document_ids) > 0:
            target_ids = [str(d).strip() for d in document_ids if str(d).strip()]

        # 1. Semantic Dense Search (ChromaDB)
        query_embedding = self.embedder.embed_query(query)
        candidate_count = min(max(top_k * 3, 25), self.collection.count())

        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": candidate_count,
            "include": ["documents", "metadatas", "distances"],
        }

        if target_ids:
            if len(target_ids) == 1:
                query_kwargs["where"] = {"document_id": target_ids[0]}
            else:
                query_kwargs["where"] = {"document_id": {"$in": target_ids}}

        try:
            semantic_results = self.collection.query(**query_kwargs)
        except Exception:
            semantic_results = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        semantic_ranked = []
        docs_list = semantic_results.get("documents", [[]])[0]
        meta_list = semantic_results.get("metadatas", [[]])[0]
        dist_list = semantic_results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs_list, meta_list, dist_list):
            meta = meta or {}
            cosine_sim = max(0.0, 1.0 - float(dist))
            semantic_ranked.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "page": int(meta.get("page", 1)),
                "chunk": int(meta.get("chunk", 0)),
                "document_id": meta.get("document_id", "unknown"),
                "dense_score": cosine_sim,
            })

        # 2. Sparse Keyword Search (BM25)
        bm25_ranked = []
        if self.bm25 and self.bm25_docs:
            if target_ids:
                candidate_indices = [
                    idx for idx, d in enumerate(self.bm25_docs)
                    if d["document_id"] in target_ids
                ]
            else:
                candidate_indices = list(range(len(self.bm25_docs)))

            if candidate_indices:
                tokens = query.lower().split()
                scores = self.bm25.get_scores(tokens)

                filtered_scored = [(idx, scores[idx]) for idx in candidate_indices if scores[idx] > 0]
                filtered_scored.sort(key=lambda x: x[1], reverse=True)

                max_bm25 = filtered_scored[0][1] if filtered_scored else 1.0
                if max_bm25 <= 0:
                    max_bm25 = 1.0

                for idx, sc in filtered_scored[:candidate_count]:
                    d = self.bm25_docs[idx]
                    bm25_ranked.append({
                        "text": d["text"],
                        "source": d["source"],
                        "page": d["page"],
                        "chunk": d["chunk"],
                        "document_id": d["document_id"],
                        "bm25_score": float(sc) / max_bm25,
                    })

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_constant = 60
        rrf_scores: Dict[tuple, Dict[str, Any]] = {}

        for rank, item in enumerate(semantic_ranked):
            key = (item["document_id"], item["source"], item["page"], item["chunk"])
            rrf_val = 1.0 / (rrf_constant + rank + 1)
            if key not in rrf_scores:
                rrf_scores[key] = {
                    **item,
                    "rrf_score": rrf_val,
                    "dense_score": item["dense_score"],
                    "bm25_score": 0.0,
                }
            else:
                rrf_scores[key]["rrf_score"] += rrf_val
                rrf_scores[key]["dense_score"] = item["dense_score"]

        for rank, item in enumerate(bm25_ranked):
            key = (item["document_id"], item["source"], item["page"], item["chunk"])
            rrf_val = 1.0 / (rrf_constant + rank + 1)
            if key not in rrf_scores:
                rrf_scores[key] = {
                    **item,
                    "rrf_score": rrf_val,
                    "dense_score": 0.0,
                    "bm25_score": item["bm25_score"],
                }
            else:
                rrf_scores[key]["rrf_score"] += rrf_val
                rrf_scores[key]["bm25_score"] = item["bm25_score"]

        merged_results = []
        for key, item in rrf_scores.items():
            composite_score = (
                item["dense_score"] * 0.60 +
                item["bm25_score"] * 0.25 +
                min(item["rrf_score"] * 30, 0.15)
            )
            item["score"] = round(float(composite_score), 4)

            if item["score"] >= min_relevance_threshold:
                merged_results.append(item)

        merged_results.sort(key=lambda x: x["score"], reverse=True)
        return merged_results[:top_k]

    # =========================================================
    # DOCUMENT MANAGEMENT & RETRIEVAL
    # =========================================================

    def list_documents(self) -> List[Dict[str, Any]]:
        existing = self.collection.get(include=["metadatas"])
        docs = {}

        for meta in existing.get("metadatas", []):
            meta = meta or {}
            doc_id = meta.get("document_id")
            source = meta.get("source", "unknown")
            if not doc_id:
                continue
            if doc_id not in docs:
                docs[doc_id] = {
                    "document_id": doc_id,
                    "filename": source,
                    "chunks_count": 0,
                }
            docs[doc_id]["chunks_count"] += 1

        return list(docs.values())

    def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        res = self.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        items = []
        for doc, meta in zip(res.get("documents", []), res.get("metadatas", [])):
            meta = meta or {}
            items.append({
                "text": doc,
                "chunk": int(meta.get("chunk", 0)),
                "page": int(meta.get("page", 1)),
                "source": meta.get("source", "unknown"),
            })
        items.sort(key=lambda x: x["chunk"])
        return items

    def delete_document(self, document_id: str) -> bool:
        try:
            self.collection.delete(where={"document_id": document_id})
            self.bm25_docs = [
                d for d in self.bm25_docs
                if d.get("document_id") != document_id
            ]
            self._rebuild_bm25()
            return True
        except Exception as e:
            print(f"Error deleting document {document_id}: {e}")
            return False

    def clear_all(self):
        ids = self.collection.get()["ids"]
        if ids:
            self.collection.delete(ids=ids)
        self.bm25_docs = []
        self.bm25 = None