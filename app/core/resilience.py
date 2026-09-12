import os
import time
import random
import logging
from functools import wraps

logger = logging.getLogger("docmind.resilience")
logging.basicConfig(level=logging.INFO)


class GeminiServiceError(Exception):
    """Custom exception raised when Gemini API calls fail after all retries."""
    def __init__(self, message: str, status_code: int = 500, original_error: Exception | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


def is_rate_limit_error(exception: Exception) -> bool:
    """Check if the error is 429 / RESOURCE_EXHAUSTED / quota exceeded."""
    err_str = str(exception).lower()
    return any(k in err_str for k in ["429", "resource_exhausted", "quota", "rate limit", "too many requests"])


def is_retryable_error(exception: Exception) -> bool:
    """Check if the error corresponds to 429, 503, or transient network timeouts."""
    err_str = str(exception).lower()
    retryable_keywords = [
        "429",
        "resource_exhausted",
        "quota",
        "rate limit",
        "503",
        "unavailable",
        "timeout",
        "deadline exceeded",
        "connection reset",
        "try again",
        "temporarily unavailable",
    ]
    return any(keyword in err_str for keyword in retryable_keywords)


def retry_gemini(
    max_retries: int = 4,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True,
):
    """
    Decorator for Gemini API calls to handle 429 (Resource Exhausted) and 503 (Unavailable).
    For 429 quota limits, applies a 10s-25s cooling backoff to allow Google's token window to reset.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if not is_retryable_error(e) or attempt == max_retries:
                        logger.error(
                            f"[{func.__name__}] Request failed after attempt {attempt}/{max_retries}: {e}"
                        )
                        err_text = str(e).lower()
                        if is_rate_limit_error(e):
                            raise GeminiServiceError(
                                "Gemini API rate limit or quota exceeded. Please wait a moment before trying again.",
                                status_code=429,
                                original_error=e,
                            )
                        elif "503" in err_text or "unavailable" in err_text:
                            raise GeminiServiceError(
                                "Gemini service is temporarily unavailable (503). Retries failed. Please try again shortly.",
                                status_code=503,
                                original_error=e,
                            )
                        else:
                            raise GeminiServiceError(
                                f"Gemini API request failed: {str(e)}",
                                status_code=500,
                                original_error=e,
                            )

                    # Determine sleep duration
                    if is_rate_limit_error(e):
                        # 429 Quota resets on a sliding window; use cooling pause: 8s, 16s, 24s
                        actual_delay = 8.0 * attempt
                        if jitter:
                            actual_delay += random.uniform(1.0, 4.0)
                        logger.warning(
                            f"[{func.__name__}] 429 Rate limit detected. Applying cooling backoff of {actual_delay:.1f}s (Attempt {attempt}/{max_retries})..."
                        )
                    else:
                        actual_delay = delay
                        if jitter:
                            actual_delay += random.uniform(0.5, 1.5 * delay)
                        actual_delay = min(actual_delay, max_delay)
                        logger.warning(
                            f"[{func.__name__}] Transient error {type(e).__name__}: {e}. Retrying in {actual_delay:.1f}s..."
                        )

                    time.sleep(actual_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


DEFAULT_GENERATION_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-flash-latest",
    "gemini-3.6-flash",
]


def generate_with_cascade(
    client,
    contents,
    config=None,
    model_override: str | None = None,
    candidate_models: list[str] | None = None,
) -> str:
    """
    Generates content using Gemini with automatic multi-model failover.
    If the active model hits a daily or minute quota limit (429) or 503 unavailable,
    it automatically fails over to the next candidate model in the cascade without interrupting the user.
    """
    candidates = candidate_models or DEFAULT_GENERATION_MODELS
    if model_override:
        candidates = [model_override] + [m for m in candidates if m != model_override]

    unique_candidates = []
    for m in candidates:
        if m and m not in unique_candidates:
            unique_candidates.append(m)

    last_err = None
    for idx, model in enumerate(unique_candidates):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            if response and response.text:
                return response.text.strip()
            return ""
        except Exception as e:
            last_err = e
            logger.warning(
                f"[generate_with_cascade] Model '{model}' failed ({type(e).__name__}: {str(e)[:120]}). "
                f"Falling back to next candidate model..."
            )
            if idx < len(unique_candidates) - 1:
                time.sleep(0.5)
                continue
            else:
                break

    if last_err:
        if is_rate_limit_error(last_err):
            raise GeminiServiceError(
                "Gemini API rate limit or quota exceeded across all fallback models. Please wait a moment before trying again.",
                status_code=429,
                original_error=last_err,
            )
        raise GeminiServiceError(
            f"Gemini generation failed: {str(last_err)}",
            status_code=500,
            original_error=last_err,
        )
    return ""

