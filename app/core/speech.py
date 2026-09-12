# app/core/speech.py

import os
import json
from google import genai
from google.genai import types
from app.core.resilience import retry_gemini, generate_with_cascade

def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key.strip("'\""))

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")


@retry_gemini(max_retries=3, initial_delay=1.0)
def transcribe_audio(audio_path: str) -> dict:
    """
    Transcribes spoken questions in English, Hindi, or Gujarati using Gemini.
    Detects the spoken language automatically.
    """
    client = get_genai_client()
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    prompt = (
        "Accurately transcribe the spoken speech in this audio. "
        "The language may be English, Hindi, or Gujarati. "
        "Return ONLY a valid JSON object matching this schema:\n"
        '{"text": "<exact transcript>", "language": "<en|hi|gu>"}'
    )

    contents = [
        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
        prompt,
    ]

    response_text = generate_with_cascade(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
        model_override=MODEL_NAME,
    )

    try:
        data = json.loads(response_text)
        return {
            "text": data.get("text", "").strip(),
            "language": data.get("language", "en"),
        }
    except Exception:
        return {
            "text": response_text.strip() if response_text else "",
            "language": "en",
        }