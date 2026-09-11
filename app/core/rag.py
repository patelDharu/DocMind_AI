# app/core/rag.py

import os

from google import genai
from google.genai import types

from app.core.vectorstore import VectorStore


# =========================================================
# Gemini Configuration
# =========================================================

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)


# =========================================================
# System Prompt
# =========================================================

SYSTEM_PROMPT = """
You are DocMind AI, a trilingual document question-answering assistant.

LANGUAGE RULE:
Always respond in the SAME language as the user's question.

- English question → answer in English.
- Hindi question → answer fully in Hindi using Devanagari script.
- Gujarati question → answer fully in Gujarati script.

If the source document is written in another language,
translate the relevant information into the user's question language.

CONTENT RULE:
Answer ONLY using the provided context.

You may:
- summarize information
- combine information from multiple chunks
- reason over information contained in the context

You must NOT:
- invent facts
- use outside knowledge
- assume information that is not present in the context

If the answer is not available in the provided context,
clearly say that you could not find the answer.

SOURCE RULE:
At the end of the answer, mention the relevant source
filename and page number when available.
"""


# =========================================================
# Not Found Messages
# =========================================================

NOT_FOUND_MESSAGES = {
    "en": (
        "I couldn't find relevant information in the "
        "selected document to answer that."
    ),

    "hi": (
        "मुझे चयनित दस्तावेज़ में इस प्रश्न का उत्तर देने "
        "के लिए प्रासंगिक जानकारी नहीं मिली।"
    ),

    "gu": (
        "મને પસંદ કરેલા દસ્તાવેજમાં આ પ્રશ્નનો જવાબ આપવા "
        "માટે સંબંધિત માહિતી મળી નથી."
    ),
}


# =========================================================
# RAG Pipeline
# =========================================================

class RAGPipeline:

    def __init__(self):
        self.store = VectorStore()

    # -----------------------------------------------------
    # Ingest
    # -----------------------------------------------------

    def ingest(self, chunks: list[dict]):
        """
        Add document chunks to the vector store.
        """

        self.store.add_chunks(chunks)

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    def _confidence_label(
        self,
        top_score: float
    ) -> str:

        if top_score >= 0.50:
            return "high"

        elif top_score >= 0.30:
            return "medium"

        return "low"

    # -----------------------------------------------------
    # Answer
    # -----------------------------------------------------

    def answer(
        self,
        question: str,
        top_k: int = 8,
        lang_hint: str | None = None,
        document_id: str | None = None,
    ) -> dict:
        """
        Answer a question using retrieved document context.

        document_id:
            If provided → search only that document.

            If None → search across all indexed documents.
        """

        question = question.strip()

        if not question:
            return {
                "answer": "Please enter a question.",
                "sources": [],
                "confidence": "low",
            }

        # =================================================
        # RETRIEVAL
        # =================================================

        retrieved = self.store.search(
            query=question,
            top_k=top_k,
            document_id=document_id,
        )

        # =================================================
        # RELEVANCE FILTER
        # =================================================

        relevant = [
            result
            for result in retrieved
            if result.get("score", 0) > 0.25
        ]

        # =================================================
        # NO RELEVANT INFORMATION
        # =================================================

        if not relevant:

            fallback_language = (
                lang_hint
                if lang_hint in NOT_FOUND_MESSAGES
                else "en"
            )

            return {
                "answer": NOT_FOUND_MESSAGES[
                    fallback_language
                ],
                "sources": [],
                "confidence": "low",
            }

        # =================================================
        # BUILD CONTEXT
        # =================================================

        context_parts = []

        for result in relevant:

            source = result.get(
                "source",
                "unknown"
            )

            page = result.get(
                "page",
                1
            )

            text = result.get(
                "text",
                ""
            )

            context_parts.append(
                f"""
[Source: {source}, Page: {page}]
{text}
""".strip()
            )

        context_block = "\n\n".join(
            context_parts
        )

        # =================================================
        # GEMINI PROMPT
        # =================================================

        user_prompt = f"""
CONTEXT:

{context_block}

--------------------------------------------------

USER QUESTION:

{question}

--------------------------------------------------

IMPORTANT:

Answer the user's question using ONLY the context above.

Use the same language as the user's question.

If the context does not contain the answer,
say that the information was not found.

Do not use outside knowledge.
"""

        # =================================================
        # GEMINI GENERATION
        # =================================================

        try:

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=1200,
                ),
            )

            answer_text = (
                response.text
                if response.text
                else "No answer was generated."
            )

        except Exception as e:

            return {
                "answer": (
                    "An error occurred while generating "
                    f"the answer: {str(e)}"
                ),
                "sources": [],
                "confidence": "low",
            }

        # =================================================
        # SOURCES
        # =================================================

        sources = []

        seen_sources = set()

        for result in relevant:

            source = result.get(
                "source",
                "unknown"
            )

            page = result.get(
                "page",
                1
            )

            source_key = (
                source,
                page
            )

            if source_key in seen_sources:
                continue

            seen_sources.add(
                source_key
            )

            sources.append(
                {
                    "source": source,
                    "page": page,
                    "score": round(
                        result.get(
                            "score",
                            0
                        ),
                        3
                    ),
                }
            )

        # =================================================
        # CONFIDENCE
        # =================================================

        top_score = relevant[0].get(
            "score",
            0
        )

        confidence = self._confidence_label(
            top_score
        )

        # =================================================
        # FINAL RESULT
        # =================================================

        return {
            "answer": answer_text.strip(),
            "sources": sources,
            "confidence": confidence,
        }