# app/core/rag.py

import os
from typing import List, Dict, Any
from google import genai
from google.genai import types

from app.core.vectorstore import VectorStore
from app.core.query_rewriter import QueryRewriter
from app.core.resilience import retry_gemini, GeminiServiceError, generate_with_cascade


def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiServiceError(
            "GEMINI_API_KEY is not set. Please add GEMINI_API_KEY to your .env file.",
            status_code=400,
        )
    return genai.Client(api_key=api_key.strip("'\""))


MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# =========================================================
# CHATGPT-STYLE MASTER MODEL SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are DocMind Master AI, an advanced document intelligence assistant delivering authoritative, highly accurate, and beautifully structured responses.

CORE OPERATIONAL PRINCIPLES:
1. Deliver answers with executive polish, structured formatting, and zero fluff.
2. Structure your answers with clear visual hierarchy:
   - 📌 **Direct Summary**: Start with a crisp, direct answer (1-2 sentences).
   - 🔍 **Detailed Breakdown**: Use bold bullet points to explain details, deadlines, monetary amounts, and terms.
   - 📊 **Tabular Comparison/Data**: If the query involves numbers, metrics, or comparisons, format them in a clean Markdown table.
   - 📖 **Exact Citations**: Always mention the source document name and page number at the end.

STRICT GROUNDING (ZERO-HALLUCINATION POLICY):
1. Rely EXCLUSIVELY on facts explicitly stated in the DOCUMENT CONTEXT below.
2. NEVER use prior knowledge, outside speculation, or unverified assumptions.
3. If the question asks about information NOT present in the context, you MUST reply with the exact not-found phrase:
   - English: "I couldn't find relevant information in the selected document(s) to answer that."
   - Hindi: "मुझे चयनित दस्तावेज़(ज़ों) में इस प्रश्न का उत्तर देने के लिए कोई प्रासंगिक जानकारी नहीं मिली।"
   - Gujarati: "મને પસંદ કરેલા દસ્તાવેજ(જો)માં આ પ્રશ્નનો જવાબ આપવા માટે કોઈ સંબંધિત માહિતી મળી નથી."

TRILINGUAL MASTERY:
- English question -> English response.
- Hindi question -> Pure, professional Hindi in Devanagari script.
- Gujarati question -> Pure, professional Gujarati in Gujarati script.

CONVERSATION CONTEXT:
The conversation history is provided ONLY to resolve follow-up pronouns (e.g., 'it', 'the second one', 'tell me more'). Every fact in your answer must be verified against the DOCUMENT CONTEXT.
"""

NOT_FOUND_MESSAGES = {
    "en": "I couldn't find relevant information in the selected document(s) to answer that.",
    "hi": "मुझे चयनित दस्तावेज़(ज़ों) में इस प्रश्न का उत्तर देने के लिए कोई प्रासंगिक जानकारी नहीं मिली।",
    "gu": "મને પસંદ કરેલા દસ્તાવેજ(જો)માં આ પ્રશ્નનો જવાબ આપવા માટે કોઈ સંબંધિત માહિતી મળી નથી.",
}


class RAGPipeline:
    def __init__(self):
        self.store = VectorStore()
        self.rewriter = QueryRewriter()
        self.model = MODEL_NAME

    def ingest(self, chunks: List[Dict[str, Any]], user_email: str = "demo@docmind.ai"):
        self.store.add_chunks(chunks, user_email=user_email)

    def _confidence_label(self, top_score: float, top_dense: float = 0.0) -> str:
        best = max(top_score, top_dense)
        if best >= 0.50:
            return "high"
        elif best >= 0.32:
            return "medium"
        return "low"

    def _detect_query_lang(self, text: str, hint: str | None = None) -> str:
        if hint in NOT_FOUND_MESSAGES:
            return hint
        if any('\u0A80' <= ch <= '\u0AFF' for ch in text):
            return "gu"
        if any('\u0900' <= ch <= '\u097F' for ch in text):
            return "hi"
        return "en"

    @retry_gemini(max_retries=4, initial_delay=2.0)
    def _generate_answer(self, prompt: str) -> str:
        client = get_genai_client()
        return generate_with_cascade(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=2000,
                temperature=0.1,
            ),
            model_override=self.model,
        )

    def answer(
        self,
        question: str,
        top_k: int = 8,
        lang_hint: str | None = None,
        document_ids: List[str] | str | None = None,
        history: List[Dict[str, str]] | None = None,
        user_email: str | None = None,
    ) -> Dict[str, Any]:
        raw_question = question.strip()
        if not raw_question:
            return {
                "answer": "Please enter a valid question.",
                "sources": [],
                "confidence": "low",
                "rewritten_query": "",
            }

        detected_lang = self._detect_query_lang(raw_question, lang_hint)

        # 1. QUERY REWRITING
        search_query = raw_question
        if history and len(history) > 0:
            search_query = self.rewriter.rewrite_query(raw_question, history)

        # 2. HYBRID SEARCH (Semantic AI + BM25 + User Isolation)
        target_ids = None
        if isinstance(document_ids, str) and document_ids.strip():
            target_ids = [document_ids.strip()]
        elif isinstance(document_ids, list):
            target_ids = [str(d).strip() for d in document_ids if str(d).strip()]

        retrieved_chunks = self.store.search(
            query=search_query,
            top_k=top_k,
            document_ids=target_ids,
            user_email=user_email,
            min_relevance_threshold=0.08,
        )

        # 3. HALLUCINATION PROTECTION & HYBRID GENERAL CHAT INTELLIGENCE
        top_score = retrieved_chunks[0].get("score", 0.0) if retrieved_chunks else 0.0
        top_dense = max((c.get("dense_score", 0.0) for c in retrieved_chunks), default=0.0)

        # Case A: No specific document targeted and no document chunks exist in library
        # Provide general conversational AI response for any prompt
        if not target_ids and not retrieved_chunks:
            history_str = ""
            if history and len(history) > 0:
                turns = []
                for h in history[-4:]:
                    role = "User" if h.get("role") == "user" else "Assistant"
                    turns.append(f"{role}: {h.get('content', '')}")
                history_str = "CONVERSATION HISTORY:\n" + "\n".join(turns) + "\n\n"

            general_prompt = f"""
{history_str}CURRENT USER QUESTION:
{raw_question}

INSTRUCTIONS:
You are DocMind AI, a helpful, intelligent trilingual AI assistant.
Answer the user's question accurately, helpfully, and comprehensively in {detected_lang}.
Use clear Markdown formatting, bullet points, and code blocks where helpful.
"""
            try:
                answer_text = self._generate_answer(general_prompt)
                return {
                    "answer": answer_text,
                    "sources": [],
                    "confidence": "high",
                    "rewritten_query": search_query if search_query != raw_question else None,
                    "detected_language": detected_lang,
                }
            except Exception as e:
                return {
                    "answer": f"Service Notice: {str(e)}",
                    "sources": [],
                    "confidence": "low",
                    "rewritten_query": search_query,
                    "detected_language": detected_lang,
                }

        # Case B: A document was targeted or retrieved, but relevance score is low
        if not retrieved_chunks or (top_score < 0.22 and top_dense < 0.30):
            history_str = ""
            if history and len(history) > 0:
                turns = []
                for h in history[-4:]:
                    role = "User" if h.get("role") == "user" else "Assistant"
                    turns.append(f"{role}: {h.get('content', '')}")
                history_str = "CONVERSATION HISTORY:\n" + "\n".join(turns) + "\n\n"

            fallback_prompt = f"""
{history_str}CURRENT USER QUESTION:
{raw_question}

INSTRUCTIONS:
You are DocMind AI. The user asked a question, but their currently selected document does not contain this specific information.
First, politely state in 1 brief sentence in {detected_lang} that the targeted document does not contain information on this topic.
Then, directly answer the user's question using your general knowledge in {detected_lang} with clear, helpful details.
"""
            try:
                answer_text = self._generate_answer(fallback_prompt)
                return {
                    "answer": answer_text,
                    "sources": [],
                    "confidence": "medium",
                    "rewritten_query": search_query if search_query != raw_question else None,
                    "detected_language": detected_lang,
                }
            except Exception:
                return {
                    "answer": NOT_FOUND_MESSAGES.get(detected_lang, NOT_FOUND_MESSAGES["en"]),
                    "sources": [],
                    "confidence": "low",
                    "rewritten_query": search_query if search_query != raw_question else None,
                    "detected_language": detected_lang,
                }

        # 4. CONTEXT ASSEMBLY
        context_parts = []
        for c in retrieved_chunks:
            source = c.get("source", "unknown")
            page = c.get("page", 1)
            text = c.get("text", "")
            context_parts.append(
                f"[DOCUMENT: {source} | PAGE: {page}]\n{text}"
            )

        context_block = "\n\n---\n\n".join(context_parts)

        # History context for pronoun resolution
        history_str = ""
        if history and len(history) > 0:
            turns = []
            for h in history[-4:]:
                role = "User" if h.get("role") == "user" else "Assistant"
                turns.append(f"{role}: {h.get('content', '')}")
            history_str = "CONVERSATION HISTORY (Reference for follow-ups only):\n" + "\n".join(turns) + "\n\n"

        # 5. MASTER PROMPT COMPOSITION
        prompt = f"""
DOCUMENT CONTEXT:
{context_block}

--------------------------------------------------
{history_str}CURRENT USER QUESTION:
{raw_question}

--------------------------------------------------
ANSWER INSTRUCTIONS:
1. Verify if the DOCUMENT CONTEXT contains the answer to the CURRENT USER QUESTION.
2. If YES:
   - Provide a direct answer in 1-2 sentences.
   - Follow with structured bullet points detailing key evidence, numbers, and dates.
   - If tabular data exists, summarize it in a clean Markdown table.
   - At the bottom, cite: **Sources: [Filename], Page [Page]**
3. If NO: Output strictly: "{NOT_FOUND_MESSAGES.get(detected_lang, NOT_FOUND_MESSAGES['en'])}"
4. Respond in {detected_lang}.
"""

        # 6. RESILIENT GENERATION
        try:
            answer_text = self._generate_answer(prompt)
        except GeminiServiceError as ge:
            return {
                "answer": f"Service Notice: {str(ge)}",
                "sources": [],
                "confidence": "low",
                "rewritten_query": search_query,
            }
        except Exception as e:
            return {
                "answer": f"An unexpected error occurred: {str(e)}",
                "sources": [],
                "confidence": "low",
                "rewritten_query": search_query,
            }

        # 7. CITATIONS FORMATTING
        sources = []
        seen_keys = set()
        for chunk in retrieved_chunks:
            source_file = chunk.get("source", "unknown")
            page_num = chunk.get("page", 1)
            key = (source_file, page_num)

            if key in seen_keys:
                continue
            seen_keys.add(key)

            snippet_text = chunk.get("text", "").replace("\n", " ").strip()
            preview = snippet_text[:140] + "..." if len(snippet_text) > 140 else snippet_text

            sources.append({
                "source": source_file,
                "page": page_num,
                "score": round(chunk.get("score", 0.0), 3),
                "snippet": preview,
            })

        return {
            "answer": answer_text,
            "sources": sources,
            "confidence": self._confidence_label(top_score, top_dense),
            "rewritten_query": search_query if search_query != raw_question else None,
            "detected_language": detected_lang,
        }