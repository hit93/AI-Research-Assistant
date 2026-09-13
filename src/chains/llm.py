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
    if not settings.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to your .env file.\n"
            "Get a free key at https://console.groq.com"
        )

    chosen_model = model or settings.GROQ_MODEL
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
            text = response.content if isinstance(response.content, str) else str(response.content)
            return text
        except Exception as e:
            logger.warning(f"LLM invocation failed on attempt {attempt}/{retries}: {e}")
            if attempt == retries:
                raise

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
