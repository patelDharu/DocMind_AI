# app/core/query_rewriter.py

import os
from typing import List, Dict
from google import genai
from google.genai import types
from app.core.resilience import retry_gemini, generate_with_cascade

def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key.strip("'\""))

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

REWRITE_PROMPT = """
You are an expert query decontextualizer for a trilingual document search engine (English, Hindi, Gujarati).

TASK:
Given the conversation history and the user's latest follow-up question, rewrite the question into a completely SELF-CONTAINED search query.
Resolve all conversational pronouns (e.g., "it", "this", "that", "the second one", "તે", "આ", "इसका", "उसका") and implicit references.

RULES:
1. If the question is ALREADY self-contained, return it unchanged.
2. Maintain the SAME LANGUAGE as the user's question (English -> English, Hindi -> Hindi, Gujarati -> Gujarati).
3. Do NOT answer the question. Only output the reformulated question string.
4. Output ONLY the rewritten question text with no quotes, commentary, or markdown.

EXAMPLES:
History:
User: What is the project budget for Phase 1?
Assistant: The budget for Phase 1 is ₹50 Lakhs.
User question: What about the second project?
Rewritten: What is the project budget for the second project?

History:
User: પોલિસીમાં મેડિકલ કવરેજ કેટલું છે?
Assistant: પોલિસી ₹5 લાખ સુધીનું કવરેજ આપે છે.
User question: અને ડેન્ટલ કવરેજ?
Rewritten: પોલિસીમાં ડેન્ટલ કવરેજ કેટલું છે?

History:
User: कंपनी की छुट्टी की नीति क्या है?
Assistant: कंपनी साल में 20 सवैतनिक छुट्टियां देती है।
User question: मातृत्व अवकाश के क्या नियम हैं?
Rewritten: मातृत्व अवकाश के क्या नियम हैं?
"""


class QueryRewriter:
    def __init__(self):
        self.model = MODEL_NAME

    @retry_gemini(max_retries=3, initial_delay=1.0)
    def rewrite_query(self, question: str, history: List[Dict[str, str]] | None = None) -> str:
        """
        Decontextualizes a follow-up question using the conversation history.
        """
        clean_q = question.strip()
        if not history or len(history) == 0:
            return clean_q

        # Format past turns
        history_text = []
        for turn in history[-4:]:  # last 2 turns are sufficient for context
            role = "User" if turn.get("role") == "user" else "Assistant"
            content = turn.get("content", "").strip()
            if content:
                history_text.append(f"{role}: {content}")

        if not history_text:
            return clean_q

        prompt = f"""
CONVERSATION HISTORY:
{chr(10).join(history_text)}

USER QUESTION:
{clean_q}

REWRITTEN STANDALONE QUESTION:
""".strip()

        try:
            client = get_genai_client()
            rewritten = generate_with_cascade(
                client=client,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=REWRITE_PROMPT,
                    max_output_tokens=150,
                    temperature=0.1,
                ),
                model_override=self.model,
            )
            rewritten = (rewritten or clean_q).strip('"\'')
            return rewritten or clean_q
        except Exception:
            return clean_q
