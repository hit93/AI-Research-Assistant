"""
LLM Factory — Provides configured ChatGroq instances and execution helpers.
"""

import json
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("chains.llm")


def get_chat_llm(
    temperature: float = 0.3,
    max_tokens: int = 4096,
    model: str | None = None,
) -> ChatGroq:
    """
    Return a configured LangChain ChatGroq instance.

    Args:
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
        max_tokens: Maximum tokens in generated response.
        model: Model name override (defaults to settings.GROQ_MODEL).

    Returns:
        A ChatGroq LLM instance.
    """
    chosen_model = model or settings.GROQ_MODEL

    # Google AI Studio / Gemini models
    if chosen_model.startswith("gemini") or chosen_model.startswith("google/"):
        gemini_api_key = settings.GEMINI_API_KEY
        if not gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file.\n"
                "Get a free key at https://aistudio.google.com"
            )
        clean_model_name = chosen_model.replace("google/", "")
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.debug(f"Instantiating ChatGoogleGenerativeAI (model: {clean_model_name}, temp: {temperature})")
        return ChatGoogleGenerativeAI(
            model=clean_model_name,
            google_api_key=gemini_api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    if not settings.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to your .env file.\n"
            "Get a free key at https://console.groq.com"
        )

    # Normalize common model names if missing provider prefix on Groq
    if chosen_model in ("gpt-oss-120b", "gpt_oss_120b"):
        chosen_model = "openai/gpt-oss-120b"
    elif chosen_model in ("gpt-oss-20b", "gpt_oss_20b"):
        chosen_model = "openai/gpt-oss-20b"
    elif chosen_model in ("qwen3.8-27b", "qwen-3.8-27b"):
        chosen_model = "qwen/qwen3.8-27b"

    # Groq decommissioned these IDs on 2026-08-16 (free/developer tier).
    deprecated = {
        "llama-3.1-8b-instant": "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile": "qwen/qwen3.8-27b",
    }
    if chosen_model in deprecated:
        replacement = deprecated[chosen_model]
        logger.warning(
            f"Groq model '{chosen_model}' is decommissioned; using '{replacement}' instead."
        )
        chosen_model = replacement

    logger.debug(f"Instantiating ChatGroq (model: {chosen_model}, temp: {temperature})")

    return ChatGroq(
        model=chosen_model,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    retries: int = 3,
) -> str:
    """Send a prompt to ChatGroq and return the text response."""
    llm = get_chat_llm(temperature=temperature, max_tokens=max_tokens)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    for attempt in range(1, retries + 1):
        try:
            response = llm.invoke(messages)
            if isinstance(response.content, str):
                text = response.content
            elif isinstance(response.content, list):
                text = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in response.content
                )
            else:
                text = str(response.content)
            return text
        except Exception as e:
            logger.warning(f"LLM invocation failed on attempt {attempt}/{retries}: {e}")
            if attempt == retries:
                raise
            import time
            chosen_model = str(getattr(llm, "model_name", getattr(llm, "model", ""))).lower()
            wait_time = (8.0 * attempt) if "qwen" in chosen_model else (2.0 * attempt)
            logger.info(f"Waiting {wait_time:.1f}s before retry attempt {attempt + 1}...")
            time.sleep(wait_time)

    raise RuntimeError(f"LLM call failed after {retries} retries")


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict | list:
    """Call the LLM and parse the response as JSON (with code-fence cleanup)."""
    raw = call_llm(system_prompt, user_prompt, temperature, max_tokens)

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON output: {e}\nRaw: {raw[:500]}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e
