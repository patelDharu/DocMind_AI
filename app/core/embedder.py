# app/core/embedder.py
#
# CHANGED FROM ORIGINAL: swapped "all-MiniLM-L6-v2" (English-only) for
# "intfloat/multilingual-e5-base" (100+ languages including Hindi and
# Gujarati). This is the model that lets a Gujarati question find the
# right chunk in an English PDF, because it maps meaning - not exact
# words - into the same vector space across languages.
#
# IMPORTANT: e5 models require a "query: " or "passage: " prefix on every
# piece of text you embed. Skipping this prefix quietly produces WORSE
# results - it's not optional, it's how the model was trained.

from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-base"):
        self.model = SentenceTransformer(model_name)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Use this when embedding DOCUMENT CHUNKS (at upload/indexing time)."""
        prefixed = [f"passage: {t}" for t in texts]
        return self.model.encode(prefixed, show_progress_bar=False, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        """Use this when embedding a USER QUESTION (at search time)."""
        prefixed = f"query: {text}"
        return self.model.encode([prefixed], normalize_embeddings=True).tolist()[0]