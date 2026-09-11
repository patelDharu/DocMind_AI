# app/core/vectorstore.py

import chromadb
from rank_bm25 import BM25Okapi

from app.core.embedder import Embedder


class VectorStore:
    def __init__(
        self,
        persist_dir="app/data/vectorstore",
        collection_name="documents",
    ):
        # ---------------------------------------------------------
        # ChromaDB
        # ---------------------------------------------------------
        self.client = chromadb.PersistentClient(
            path=persist_dir
        )

        self.collection = self.client.get_or_create_collection(
            collection_name
        )

        # ---------------------------------------------------------
        # Embedding model
        # ---------------------------------------------------------
        self.embedder = Embedder()

        # ---------------------------------------------------------
        # BM25
        # ---------------------------------------------------------
        self.bm25 = None
        self.bm25_docs = []

        self._rebuild_bm25_from_existing()

    # =========================================================
    # BM25 - Rebuild from ChromaDB
    # =========================================================

    def _rebuild_bm25_from_existing(self):
        existing = self.collection.get(
            include=["documents", "metadatas"]
        )

        if not existing.get("ids"):
            return

        self.bm25_docs = []

        for doc, metadata in zip(
            existing.get("documents", []),
            existing.get("metadatas", []),
        ):
            metadata = metadata or {}

            document_id = metadata.get(
                "document_id",
                metadata.get("source", "unknown"),
            )

            self.bm25_docs.append(
                {
                    "text": doc,
                    "source": metadata.get(
                        "source",
                        "unknown",
                    ),
                    "page": metadata.get(
                        "page",
                        1,
                    ),
                    "chunk": metadata.get(
                        "chunk",
                        0,
                    ),
                    "document_id": document_id,
                }
            )

        self._rebuild_bm25()

    # =========================================================
    # BM25 - Build index
    # =========================================================

    def _rebuild_bm25(self):
        if not self.bm25_docs:
            self.bm25 = None
            return

        tokenized_documents = [
            doc["text"].lower().split()
            for doc in self.bm25_docs
        ]

        if tokenized_documents:
            self.bm25 = BM25Okapi(
                tokenized_documents
            )

    # =========================================================
    # ADD CHUNKS
    # =========================================================

    def add_chunks(self, chunks):
        if not chunks:
            return

        # -----------------------------------------------------
        # Texts
        # -----------------------------------------------------
        texts = [
            chunk["text"]
            for chunk in chunks
        ]

        # -----------------------------------------------------
        # Embeddings
        # -----------------------------------------------------
        embeddings = self.embedder.embed_passages(
            texts
        )

        # -----------------------------------------------------
        # IDs
        # -----------------------------------------------------
        ids = [
            chunk["id"]
            for chunk in chunks
        ]

        # -----------------------------------------------------
        # Metadata
        # -----------------------------------------------------
        metadatas = []

        for chunk in chunks:

            metadata = chunk.get(
                "metadata",
                {}
            )

            document_id = metadata.get(
                "document_id",
                metadata.get(
                    "source",
                    "unknown",
                ),
            )

            metadatas.append(
                {
                    "source": metadata.get(
                        "source",
                        "unknown",
                    ),
                    "page": metadata.get(
                        "page",
                        1,
                    ),
                    "chunk": metadata.get(
                        "chunk",
                        0,
                    ),
                    "document_id": document_id,
                }
            )

        # -----------------------------------------------------
        # Store in Chroma
        # -----------------------------------------------------
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # -----------------------------------------------------
        # Add to BM25
        # -----------------------------------------------------
        for chunk in chunks:

            metadata = chunk.get(
                "metadata",
                {}
            )

            document_id = metadata.get(
                "document_id",
                metadata.get(
                    "source",
                    "unknown",
                ),
            )

            self.bm25_docs.append(
                {
                    "text": chunk["text"],
                    "source": metadata.get(
                        "source",
                        "unknown",
                    ),
                    "page": metadata.get(
                        "page",
                        1,
                    ),
                    "chunk": metadata.get(
                        "chunk",
                        0,
                    ),
                    "document_id": document_id,
                }
            )

        self._rebuild_bm25()

    # =========================================================
    # SEARCH
    # =========================================================

    def search(
        self,
        query,
        top_k=8,
        document_id=None,
    ):
        """
        Hybrid search using:

        1. Semantic search with ChromaDB
        2. Keyword search with BM25

        If document_id is provided:
            Search ONLY inside that document.

        If document_id is None:
            Search across ALL documents.
        """

        # -----------------------------------------------------
        # Empty database check
        # -----------------------------------------------------

        if self.collection.count() == 0:
            return []

        # =====================================================
        # SEMANTIC SEARCH
        # =====================================================

        query_embedding = self.embedder.embed_query(
            query
        )

        # Get extra candidates so hybrid search has
        # enough results to work with.
        candidate_k = max(
            top_k * 3,
            20,
        )

        total_documents = self.collection.count()

        candidate_k = min(
            candidate_k,
            total_documents,
        )

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": candidate_k,
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }

        # -----------------------------------------------------
        # IMPORTANT:
        # Filter Chroma by document_id
        # -----------------------------------------------------

        if document_id:
            query_kwargs["where"] = {
                "document_id": document_id
            }

        semantic_results = self.collection.query(
            **query_kwargs
        )

        semantic_items = []

        documents = semantic_results.get(
            "documents",
            [[]],
        )

        metadatas = semantic_results.get(
            "metadatas",
            [[]],
        )

        distances = semantic_results.get(
            "distances",
            [[]],
        )

        if documents and documents[0]:

            for doc, metadata, distance in zip(
                documents[0],
                metadatas[0],
                distances[0],
            ):

                metadata = metadata or {}

                result_document_id = metadata.get(
                    "document_id",
                    metadata.get(
                        "source",
                        "unknown",
                    ),
                )

                semantic_items.append(
                    {
                        "text": doc,
                        "source": metadata.get(
                            "source",
                            "unknown",
                        ),
                        "page": metadata.get(
                            "page",
                            1,
                        ),
                        "chunk": metadata.get(
                            "chunk",
                            0,
                        ),
                        "document_id": result_document_id,
                        "score": max(
                            0.0,
                            1 - float(distance),
                        ),
                    }
                )

        # =====================================================
        # BM25 SEARCH
        # =====================================================

        keyword_items = []

        if self.bm25 and self.bm25_docs:

            # -------------------------------------------------
            # Select documents
            # -------------------------------------------------

            if document_id:

                candidate_indices = [
                    index
                    for index, doc in enumerate(
                        self.bm25_docs
                    )
                    if doc["document_id"] == document_id
                ]

            else:

                candidate_indices = list(
                    range(
                        len(
                            self.bm25_docs
                        )
                    )
                )

            if candidate_indices:

                query_tokens = (
                    query.lower().split()
                )

                all_scores = self.bm25.get_scores(
                    query_tokens
                )

                filtered_scores = [
                    (
                        index,
                        all_scores[index],
                    )
                    for index in candidate_indices
                ]

                filtered_scores.sort(
                    key=lambda item: item[1],
                    reverse=True,
                )

                top_candidates = filtered_scores[
                    :top_k
                ]

                max_score = max(
                    [
                        score
                        for _, score in top_candidates
                    ],
                    default=1.0,
                )

                if max_score <= 0:
                    max_score = 1.0

                for index, score in top_candidates:

                    doc = self.bm25_docs[index]

                    keyword_items.append(
                        {
                            "text": doc["text"],
                            "source": doc["source"],
                            "page": doc["page"],
                            "chunk": doc["chunk"],
                            "document_id": doc[
                                "document_id"
                            ],
                            "score": float(
                                score
                            ) / max_score,
                        }
                    )

        # =====================================================
        # MERGE SEMANTIC + BM25
        # =====================================================

        combined = {}

        for result in (
            semantic_items + keyword_items
        ):

            # Don't merge identical text from
            # different documents.
            key = (
                result["document_id"],
                result["source"],
                result["page"],
                result["chunk"],
                result["text"],
            )

            if (
                key not in combined
                or result["score"]
                > combined[key]["score"]
            ):
                combined[key] = result

        # -----------------------------------------------------
        # Sort by relevance
        # -----------------------------------------------------

        final_results = sorted(
            combined.values(),
            key=lambda item: item["score"],
            reverse=True,
        )

        return final_results[:top_k]

        # =========================================================
    # LIST DOCUMENTS
    # =========================================================

    def list_documents(self):
        """
        Return all unique indexed documents.
        """

        existing = self.collection.get(
            include=["metadatas"]
        )

        documents = {}

        for metadata in existing.get(
            "metadatas",
            []
        ):

            metadata = metadata or {}

            document_id = metadata.get(
                "document_id"
            )

            source = metadata.get(
                "source",
                "unknown"
            )

            if not document_id:
                continue

            if document_id not in documents:
                documents[document_id] = {
                    "document_id": document_id,
                    "filename": source,
                }

        return list(
            documents.values()
        )