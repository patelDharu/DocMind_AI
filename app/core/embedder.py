# app/core/embedder.py

import os
import time
import logging
from typing import List
from google import genai
from app.core.resilience import retry_gemini

logger = logging.getLogger("docmind.embedder")


def _extract_batch_embeddings(response) -> List[List[float]]:
    """Extract list of embedding vectors from EmbedContentResponse."""
    if hasattr(response, "embeddings") and response.embeddings:
        vectors = []
        for e in response.embeddings:
            if hasattr(e, "values"):
                vectors.append(list(e.values))
            else:
                vectors.append(list(e))
        return vectors
    elif hasattr(response, "embedding") and response.embedding:
        emb = response.embedding
        if hasattr(emb, "values"):
            return [list(emb.values)]
        return [list(emb)]
    raise ValueError("Could not extract embeddings from response.")


def _extract_embedding_values(response) -> List[float]:
    """
    Extract the list of float values from the response.
    In google-genai SDK, the attribute is response.embeddings (list of ContentEmbedding).
    """
    if hasattr(response, "embeddings") and response.embeddings:
        first = response.embeddings[0]
        if hasattr(first, "values"):
            return list(first.values)
        return list(first)
    elif hasattr(response, "embedding") and response.embedding:
        emb = response.embedding
        if hasattr(emb, "values"):
            return list(emb.values)
        return list(emb)
    raise ValueError("Could not extract embedding values from Gemini EmbedContentResponse.")


class Embedder:
    """
    Generates dense vector embeddings using Google Gemini's active embedding models
    with automatic candidate fallback and 429/503 retry resilience.
    """

    def __init__(self, model_name: str | None = None):
        self._client = None
        custom_model = model_name or os.getenv("GEMINI_EMBEDDING_MODEL")
        self.candidate_models = [
            m for m in [
                custom_model,
                "gemini-embedding-001",
                "gemini-embedding-2",
                "text-embedding-004",
            ] if m
        ]
        self.active_model = self.candidate_models[0]

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not set. Please add your Gemini API key to .env file."
                )
            api_key = api_key.strip("'\"")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _embed_single(self, text: str) -> List[float]:
        last_error = None

        ordered_models = [self.active_model] + [
            m for m in self.candidate_models if m != self.active_model
        ]

        for model in ordered_models:
            try:
                response = self.client.models.embed_content(
                    model=model,
                    contents=text,
                )
                self.active_model = model
                return _extract_embedding_values(response)
            except Exception as e:
                err_str = str(e).lower()
                last_error = e
                if "404" in err_str or "not found" in err_str or "not supported" in err_str:
                    logger.warning(
                        f"Embedding model '{model}' returned 404. Falling back to next candidate..."
                    )
                    continue
                raise e

        raise last_error

    def _embed_batch(self, batch_texts: List[str]) -> List[List[float]]:
        last_error = None
        ordered_models = [self.active_model] + [
            m for m in self.candidate_models if m != self.active_model
        ]

        for model in ordered_models:
            try:
                response = self.client.models.embed_content(
                    model=model,
                    contents=batch_texts,
                )
                self.active_model = model
                vectors = _extract_batch_embeddings(response)
                # Ensure the API returned a separate embedding for each text in the batch
                if len(vectors) != len(batch_texts):
                    raise ValueError(
                        f"Batch API returned {len(vectors)} vectors for {len(batch_texts)} texts. "
                        "Falling back to individual embedding."
                    )
                return vectors
            except Exception as e:
                err_str = str(e).lower()
                last_error = e
                if "404" in err_str or "not found" in err_str or "not supported" in err_str:
                    logger.warning(
                        f"Embedding model '{model}' returned 404. Falling back to next candidate..."
                    )
                    continue
                raise e

        raise last_error

    @retry_gemini(max_retries=4, initial_delay=2.0)
    def embed_passages(self, texts: List[str], batch_size: int = 30) -> List[List[float]]:
        if not texts:
            return []

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = [t.strip() or "empty" for t in texts[i : i + batch_size]]
            try:
                # 1. Native batch embedding: embeds up to 30 passages in a single API call
                batch_vectors = self._embed_batch(batch)
                if len(batch_vectors) == len(batch):
                    all_embeddings.extend(batch_vectors)
                else:
                    raise ValueError(f"Batch returned {len(batch_vectors)} vs expected {len(batch)}")
            except Exception as e:
                logger.warning(
                    f"Native batch embed failed ({e}). Falling back to sequential embedding for batch of {len(batch)}..."
                )
                for text in batch:
                    try:
                        all_embeddings.append(self._embed_single(text))
                    except Exception as single_err:
                        logger.warning(f"Single embed failed for chunk ({single_err}). Padding with fallback vector.")
                        dim = len(all_embeddings[0]) if all_embeddings else 768
                        all_embeddings.append([0.0] * dim)

            # Light pacing between batches to stay safely within RPM
            if i + batch_size < len(texts):
                time.sleep(0.5)

        # Invariant Guarantee: Number of embeddings must EXACTLY match number of texts
        if len(all_embeddings) != len(texts):
            logger.warning(
                f"Embedding count gap: {len(all_embeddings)} embeddings for {len(texts)} texts. Aligning..."
            )
            dim = len(all_embeddings[0]) if all_embeddings else 768
            if len(all_embeddings) > len(texts):
                all_embeddings = all_embeddings[:len(texts)]
            else:
                while len(all_embeddings) < len(texts):
                    all_embeddings.append([0.0] * dim)

        return all_embeddings

    @retry_gemini(max_retries=4, initial_delay=1.0)
    def embed_query(self, text: str) -> List[float]:
        clean_text = text.strip() or "query"
        return self._embed_single(clean_text)