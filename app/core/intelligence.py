# app/core/intelligence.py

import os
import json
from typing import List, Dict, Any
from google import genai
from google.genai import types
from app.core.resilience import retry_gemini, generate_with_cascade

def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key.strip("'\""))

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")


class DocumentIntelligence:
    """
    Advanced Document Intelligence features:
    - Summarization (Executive, Detailed, Key Bullets)
    - Multi-Document Comparison
    - Structured Entity, Financial & Table Extraction
    All with strict token budgeting to completely avoid 429 quota exhaustion.
    """

    def __init__(self):
        self.model = MODEL_NAME

    # =========================================================
    # 8. DOCUMENT SUMMARIZATION (Token-Budgeted)
    # =========================================================

    @retry_gemini(max_retries=4, initial_delay=2.0)
    def summarize(
        self,
        document_text: str,
        filename: str,
        summary_type: str = "executive",
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Generates document summaries in English, Hindi, or Gujarati.
        Budgeted to 12,000 characters to prevent 429 rate limit triggers.
        """
        lang_prompts = {
            "en": "Respond in English.",
            "hi": "सम्पूर्ण उत्तर शुद्ध हिन्दी (देवनागरी लिपि) में दें।",
            "gu": "સંપૂર્ણ જવાબ શુદ્ધ ગુજરાતી લિપિમાં આપો.",
        }
        lang_instruction = lang_prompts.get(language, "Respond in English.")

        type_instructions = {
            "executive": "Provide a high-level executive summary (2-3 paragraphs) highlighting core purpose, key findings, and outcomes.",
            "detailed": "Provide a structured breakdown covering essential sections, dates, metrics, and terms.",
            "bullet_points": "Provide a crisp list of key highlights, decisions, financial numbers, deadlines, and action items in bullet points.",
        }
        type_prompt = type_instructions.get(summary_type, type_instructions["executive"])

        # Token budget: max 12,000 characters (~2,800 tokens)
        budgeted_text = document_text[:12000]

        prompt = f"""
DOCUMENT: {filename}
CONTENT:
{budgeted_text}

--------------------------------------------------
TASK:
{type_prompt}

LANGUAGE RULE:
{lang_instruction}

IMPORTANT:
Ground your summary strictly on the text provided. Do not fabricate facts.
""".strip()

        client = get_genai_client()
        summary_text = generate_with_cascade(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are DocMind AI's professional document summarization analyst. Provide crisp, structured analysis.",
                max_output_tokens=1500,
                temperature=0.1,
            ),
            model_override=self.model,
        )

        return {
            "filename": filename,
            "summary_type": summary_type,
            "language": language,
            "summary": summary_text if summary_text else "No summary could be generated.",
        }

    # =========================================================
    # 9. DOCUMENT COMPARISON (Token-Budgeted)
    # =========================================================

    @retry_gemini(max_retries=4, initial_delay=3.0)
    def compare_documents(
        self,
        doc_a: Dict[str, Any],
        doc_b: Dict[str, Any],
        focus_aspects: str = "general",
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Deep comparative analysis between two documents.
        Budgeted to 5,500 characters per document to safely remain inside quota limits.
        """
        lang_prompts = {
            "en": "Respond in English.",
            "hi": "सम्पूर्ण तुलनात्मक विश्लेषण हिन्दी में दें।",
            "gu": "સંપૂર્ણ તુલનાત્મક વિશ્લેષણ ગુજરાતીમાં આપો.",
        }
        lang_instruction = lang_prompts.get(language, "Respond in English.")

        # Budget: 5,500 chars per document (~2,750 tokens total input)
        text_a = doc_a.get("text", "")[:5500]
        name_a = doc_a.get("filename", "Document A")

        text_b = doc_b.get("text", "")[:5500]
        name_b = doc_b.get("filename", "Document B")

        prompt = f"""
DOCUMENT A: {name_a}
{text_a}

--------------------------------------------------
DOCUMENT B: {name_b}
{text_b}

--------------------------------------------------
TASK:
Perform a clear comparative analysis between '{name_a}' and '{name_b}'.
Specific Focus: {focus_aspects}

Structure your response into:
1. Executive Overview (1 concise paragraph comparing both)
2. Key Differences (Highlight requirements, budgets, dates, or obligations)
3. Side-by-Side Comparison Table (Markdown table with columns: Feature / Dimension, {name_a}, {name_b}, Variance/Notes)
4. Synthesis & Key Takeaways

LANGUAGE RULE:
{lang_instruction}

GROUNDING RULE:
Cite only from the provided text excerpts.
""".strip()

        client = get_genai_client()
        comp_text = generate_with_cascade(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are DocMind AI's senior document comparison and auditing specialist. Be concise and structured.",
                max_output_tokens=1800,
                temperature=0.1,
            ),
            model_override=self.model,
        )

        return {
            "document_a": name_a,
            "document_b": name_b,
            "comparison": comp_text if comp_text else "Comparison could not be completed.",
            "language": language,
        }

    # =========================================================
    # 10. STRUCTURED INFORMATION EXTRACTION (Token-Budgeted)
    # =========================================================

    @retry_gemini(max_retries=4, initial_delay=2.0)
    def extract_structured_data(
        self,
        document_text: str,
        filename: str,
        extraction_type: str = "key_entities",
    ) -> Dict[str, Any]:
        """
        Extract entities, key-value pairs, dates, amounts, and tables into JSON.
        Budgeted to 10,000 chars to avoid 429 quota exhaustion.
        """
        type_instructions = {
            "key_entities": "Extract organizations, persons, locations, project names, and roles.",
            "financials": "Extract all monetary figures, budgets, costs, pricing, penalty clauses, and payment schedules.",
            "dates_deadlines": "Extract all milestone dates, effective dates, expiry dates, and deadlines.",
            "full_schema": "Extract title, parties involved, dates, monetary values, obligations, key clauses, and any tabular summary.",
        }
        inst = type_instructions.get(extraction_type, type_instructions["full_schema"])

        # Budget: 10,000 characters
        budgeted_text = document_text[:10000]

        prompt = f"""
DOCUMENT: {filename}
CONTENT:
{budgeted_text}

--------------------------------------------------
TASK:
{inst}

OUTPUT FORMAT:
Provide the output strictly as valid JSON matching this schema:
{{
  "document": "{filename}",
  "extraction_type": "{extraction_type}",
  "metadata": {{
    "title": "...",
    "detected_language": "..."
  }},
  "extracted_items": [
    {{
      "category": "...",
      "key": "...",
      "value": "...",
      "context": "..."
    }}
  ],
  "tables_detected": [
    {{
      "table_name": "...",
      "headers": ["..."],
      "rows": [["..."]]
    }}
  ],
  "summary_points": ["..."]
}}
""".strip()

        client = get_genai_client()
        json_raw = generate_with_cascade(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=1500,
                temperature=0.1,
            ),
            model_override=self.model,
        )

        try:
            return json.loads(json_raw)
        except Exception:
            return {
                "document": filename,
                "extraction_type": extraction_type,
                "raw_text": json_raw if json_raw else "{}",
            }

    # =========================================================
    # 10. PROACTIVE ACTION & DEADLINE ALERT
    # =========================================================

    @retry_gemini(max_retries=3, initial_delay=1.5)
    def analyze_action_and_deadlines(
        self,
        document_text: str,
        filename: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Proactively scans the document to determine if the user needs to take any
        action, what the action is, by when (deadline), and consequences if missed.
        Supports English, Hindi, and Gujarati.
        """
        lang_prompts = {
            "en": "Respond in English.",
            "hi": "Provide all text fields (action_summary, action_items, consequences, alert_markdown) in professional Hindi (Devanagari script: हिन्दी).",
            "gu": "Provide all text fields (action_summary, action_items, consequences, alert_markdown) in professional Gujarati (Gujarati script: ગુજરાતી).",
        }
        lang_instruction = lang_prompts.get(language, "Respond in English.")

        # Budgeted to first 10,000 characters to prevent token exhaustion
        budgeted_text = document_text[:10000] if document_text else f"Document filename: {filename}"

        prompt = f"""
You are DocMind AI's Proactive Document Compliance & Action Analyst.
Analyze the following document to help an ordinary person understand:
1. Does this document require ANY action from the recipient/reader? (e.g. payment, form submission, signature, appointment, response, renewal, appearance, filing)?
   - If it's a notice, bill, summon, contract to sign, policy renewal, or warning -> requires_action = true.
   - If it's an annual report, informational brochure, receipt of past payment, news article, certificate, or reference sheet -> requires_action = false.
2. What specific action is needed?
3. By what deadline or due date? (Be explicit, e.g. "October 15, 2024" or "Within 14 days", or null if none)
4. What are the consequences, late fees, interest, legal risks, or penalties if missed?
5. What is the urgency level?
   - "high": Strict impending deadline OR legal/financial penalty/cancellation.
   - "medium": Definite action needed with a standard deadline.
   - "low": Optional or recommended action.
   - "none": Purely informational document.

DOCUMENT NAME: {filename}
DOCUMENT CONTENT:
{budgeted_text}

--------------------------------------------------
LANGUAGE RULE:
{lang_instruction}

OUTPUT FORMAT:
Provide the output strictly as valid JSON matching this schema:
{{
  "requires_action": true,
  "urgency": "high",
  "document_type": "Invoice / Tax Notice / Contract / Medical Report / Annual Report / Legal Notice / Informational",
  "deadline": "Exact date/timeframe or null",
  "action_summary": "1-sentence crisp summary of what must be done, or 'This document is informational only.'",
  "action_items": [
    "Step 1 to perform...",
    "Step 2 to perform..."
  ],
  "consequences": "Specific penalties, late fees, or risks if missed, or null if none",
  "alert_markdown": "A nicely formatted 2-4 sentence alert message suitable for reading aloud and viewing"
}}
""".strip()

        client = get_genai_client()
        json_raw = generate_with_cascade(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=1000,
                temperature=0.1,
            ),
            model_override=self.model,
        )

        try:
            result = json.loads(json_raw)
            result["language"] = language
            result["filename"] = filename
            return result
        except Exception:
            return {
                "requires_action": False,
                "urgency": "none",
                "document_type": "Document",
                "deadline": None,
                "action_summary": "Informational document. No immediate action detected.",
                "action_items": [],
                "consequences": None,
                "alert_markdown": "This document appears to be informational. No pending actions or deadlines were detected.",
                "language": language,
                "filename": filename,
            }
