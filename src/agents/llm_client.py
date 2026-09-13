"""
LLM Client — Thin wrapper around the Groq SDK.

Every agent calls the LLM through this single function.
To switch providers later, only this file needs to change.
"""

import json
import time
from groq import Groq, RateLimitError, APIConnectionError
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("llm_client")

# ── Lazy singleton so we don't create a new client per call ───
_client: Groq | None = None


def _get_client() -> Groq:
    """Return (or create) the Groq client singleton."""
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file.\n"
                "Get a free key at https://console.groq.com"
            )
        _client = Groq(api_key=settings.GROQ_API_KEY)
        logger.info(f"Groq client initialized (model: {settings.GROQ_MODEL})")
    return _client


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    retries: int = 3,
) -> str:
    """
    Send a prompt to the LLM and return the text response.

    Args:
        system_prompt: Behavioral instructions for the model.
        user_prompt:   The actual user/task content.
        temperature:   Creativity dial (0 = deterministic, 1 = creative).
        max_tokens:    Maximum length of the response.
        retries:       Number of retry attempts on rate-limit or connection errors.

    Returns:
        The model's response as a plain string.
    """
    client = _get_client()

    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content or ""
            logger.info(
                f"LLM responded ({len(text)} chars, "
                f"model={settings.GROQ_MODEL}, attempt={attempt})"
            )
            return text

        except RateLimitError:
            wait = 2 ** attempt  # exponential backoff: 2s, 4s, 8s
            logger.warning(f"Rate limited. Waiting {wait}s (attempt {attempt}/{retries})")
            time.sleep(wait)

        except APIConnectionError as e:
            logger.error(f"Connection error on attempt {attempt}/{retries}: {e}")
            if attempt == retries:
                raise
            time.sleep(1)

        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}")
            raise

    raise RuntimeError(f"LLM call failed after {retries} retries")


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict | list:
    """
    Call the LLM and parse the response as JSON.

    The system prompt should instruct the model to output valid JSON.
    This function strips markdown code fences if present and parses.
    """
    raw = call_llm(system_prompt, user_prompt, temperature, max_tokens)

    # Strip ```json ... ``` fences the model sometimes adds
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove first line (```json) and last line (```)
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON output: {e}\nRaw: {raw[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e
