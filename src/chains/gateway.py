"""
LLM Gateway — Resilient model router with circuit-breaking, retries, and fallback failover.
"""

import re
import time
import random
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from config.settings import settings
from src.chains.llm import get_chat_llm
from src.utils.logger import get_logger

logger = get_logger("chains.gateway")

T = TypeVar("T", bound=BaseModel)

# Per-model context-window limits (total tokens in + out).
# If a model is not listed it is assumed to have a large enough context.
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "openai/gpt-oss-20b": 8000,
    "openai/gpt-oss-120b": 32768,
}

# Base retry wait (seconds) per model family.
# Qwen free-tier has strict rate limits (TPM / RPM); give it a larger waiting window.
MODEL_RETRY_BASE_WAIT: dict[str, float] = {
    "qwen/qwen3.8-27b": 10.0,
    "qwen": 10.0,          # prefix match fallback for any qwen variant
}
_DEFAULT_RETRY_BASE_WAIT: float = 3.0

# Fraction of the context window to reserve for the LLM output (completion).
# The rest is available for the prompt. E.g. 0.45 means output ≤ 45% of window.
_OUTPUT_FRACTION = 0.45


def _base_wait_for(model: str) -> float:
    """Return the base retry wait seconds for a given model."""
    if model in MODEL_RETRY_BASE_WAIT:
        return MODEL_RETRY_BASE_WAIT[model]
    model_lower = model.lower()
    for prefix, wait in MODEL_RETRY_BASE_WAIT.items():
        if model_lower.startswith(prefix):
            return wait
    return _DEFAULT_RETRY_BASE_WAIT


def _retry_wait(model: str, attempt: int, error: Exception) -> float:
    """Compute how long to wait before the next retry and sleep that long.

    Priority:
    1. If error message contains a ``Retry-After: N`` header value or 'try again in Xs/ms', sleep that duration.
    2. If it's a rate limit or TPM error on Qwen, enforce minimum generous cooldown.
    3. Otherwise use exponential backoff: base_wait * 2^(attempt-1) + jitter.

    Returns the actual seconds slept.
    """
    err_str = str(error)
    is_qwen = "qwen" in model.lower()

    # 1. Check for standard Retry-After header or seconds/ms in message
    match = re.search(r"retry[-_]?after[:\s]+([\d.]+)", err_str, re.IGNORECASE)
    if not match:
        match = re.search(r"(?:try again in|please wait|retry in)\s+([\d.]+)\s*(s|sec|seconds|m|min|minutes)?", err_str, re.IGNORECASE)
    
    if match:
        val = float(match.group(1))
        unit = match.group(2).lower() if match.lastindex and match.lastindex >= 2 and match.group(2) else "s"
        if unit.startswith("m"):
            val *= 60.0
        wait = val + 1.5  # buffer
    else:
        base = _base_wait_for(model)
        wait = base * (2 ** (attempt - 1)) + random.uniform(0.5, 2.0)

    # For Qwen on rate-limit/error, ensure a solid minimum backoff
    if is_qwen:
        wait = max(wait, 8.0 * attempt)

    logger.info(
        f"[Gateway] Retry wait {wait:.1f}s for model '{model}' "
        f"(attempt {attempt}, error: {err_str[:120]})"
    )
    time.sleep(wait)
    return wait


def _attempt_json_recovery(err_str: str, schema: Type[T]) -> T | None:
    """Attempt to recover and parse a truncated or malformed JSON object from an LLM tool call error."""
    import json
    import re

    # Look for 'failed_generation': '...' or raw JSON string in the error message
    match = re.search(r"['\"]failed_generation['\"]\s*:\s*['\"](.*)", err_str, re.DOTALL)
    candidate_str = ""
    if match:
        raw_tail = match.group(1)
        # unescape escaped quotes/newlines if present
        candidate_str = raw_tail.encode().decode("unicode_escape", errors="ignore")
    else:
        # Check if there is an embedded JSON arguments block
        arg_match = re.search(r'("arguments"\s*:\s*\{.*)', err_str, re.DOTALL)
        if arg_match:
            candidate_str = "{" + arg_match.group(1)

    if not candidate_str:
        return None

    # Try extracting arguments dictionary
    args_match = re.search(r'["\']arguments["\']\s*:\s*(\{.*)', candidate_str, re.DOTALL)
    payload = args_match.group(1) if args_match else candidate_str

    # Progressively trim from end until valid JSON is achieved or closed
    for trim_idx in range(len(payload), max(0, len(payload) - 2000), -5):
        slice_candidate = payload[:trim_idx].strip()
        # Ensure brackets are balanced
        open_curly = slice_candidate.count("{") - slice_candidate.count("}")
        open_sq = slice_candidate.count("[") - slice_candidate.count("]")
        if open_sq > 0:
            # Drop trailing incomplete object inside array if unclosed
            last_comma = slice_candidate.rfind(",")
            if last_comma > 0:
                slice_candidate = slice_candidate[:last_comma]
            slice_candidate += "]" * max(0, slice_candidate.count("[") - slice_candidate.count("]"))
        slice_candidate += "}" * max(0, slice_candidate.count("{") - slice_candidate.count("}"))

        try:
            parsed = json.loads(slice_candidate)
            # If wrapped under 'sections' or directly matching schema fields
            if isinstance(parsed, dict):
                if hasattr(schema, "model_validate"):
                    return schema.model_validate(parsed)
                elif hasattr(schema, "parse_obj"):
                    return schema.parse_obj(parsed)
                return schema(**parsed)
        except Exception:
            continue

    return None


def _safe_max_tokens(model: str, requested: int) -> int:
    """Cap requested max_tokens so it does not exceed the model's context limit.

    Keeps an input budget of (1 - _OUTPUT_FRACTION) of the context window for
    the prompt, reserving _OUTPUT_FRACTION for the completion.
    """
    limit = MODEL_CONTEXT_LIMITS.get(model)
    if limit is None:
        return requested
    cap = int(limit * _OUTPUT_FRACTION)
    return min(requested, cap)


# Per-model breakers so a dead ID does not skip an unrelated live model.
_breakers: dict[str, "CircuitBreaker"] = {}


class CircuitBreaker:
    """Tracks provider failures and opens circuit when failure threshold is reached."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.threshold = failure_threshold
        self.cooldown = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0

    @property
    def is_open(self) -> bool:
        if self.failure_count >= self.threshold:
            if time.time() - self.last_failure_time < self.cooldown:
                return True
            self.reset()
        return False

    def record_success(self) -> None:
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(f"CircuitBreaker failure recorded ({self.failure_count}/{self.threshold})")

    def reset(self) -> None:
        self.failure_count = 0
        self.last_failure_time = 0.0


def reset_breakers() -> None:
    """Clear shared circuit-breaker state (used by tests)."""
    _breakers.clear()


def _breaker_for(model: str) -> CircuitBreaker:
    if model not in _breakers:
        _breakers[model] = CircuitBreaker()
    return _breakers[model]


class LLMGateway:
    """Gateway that routes across primary and fallback LLM models with circuit breaking."""

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 2,
        max_tokens: int = 4096,
    ):
        self.primary_model = primary_model or settings.GROQ_MODEL
        self.fallback_model = fallback_model or settings.FALLBACK_MODEL
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.circuit_breaker = _breaker_for(self.primary_model)

    def _llm(self, model: str):
        safe_tokens = _safe_max_tokens(model, self.max_tokens)
        return get_chat_llm(
            temperature=self.temperature,
            model=model,
            max_tokens=safe_tokens,
        )

    def invoke(self, messages: list[Any], model_override: str | None = None) -> Any:
        """Invoke LLM with primary provider and fallback on failure."""
        target_model = model_override or self.primary_model
        breaker = _breaker_for(target_model)
        last_error: Exception | None = None

        if not breaker.is_open:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = self._llm(target_model).invoke(messages)
                    breaker.record_success()
                    return response
                except Exception as e:
                    last_error = e
                    logger.warning(f"Gateway primary ({target_model}) attempt {attempt} failed: {e}")
                    if attempt < self.max_retries:
                        _retry_wait(target_model, attempt, e)
                    else:
                        breaker.record_failure()

        if self.fallback_model and self.fallback_model != target_model:
            logger.info(f"Gateway failing over to fallback model: {self.fallback_model}")
            try:
                response = self._llm(self.fallback_model).invoke(messages)
                return response
            except Exception as e:
                last_error = e
                logger.error(f"Gateway fallback ({self.fallback_model}) failed: {e}")

        raise last_error or RuntimeError("LLM gateway invoke failed")

    def _invoke_structured_with_recovery(
        self,
        model_name: str,
        schema: Type[T],
        messages_or_prompt: Any,
    ) -> T:
        """Invoke structured output with tool-calling first, falling back to json_mode if tool_use_failed."""
        llm = self._llm(model_name)
        try:
            runnable = llm.with_structured_output(schema)
            return runnable.invoke(messages_or_prompt)
        except Exception as tool_err:
            err_str = str(tool_err)
            recovered = _attempt_json_recovery(err_str, schema)
            if recovered is not None:
                logger.warning(
                    f"Gateway recovered structured output from failed tool call JSON on {model_name}."
                )
                return recovered

            # If tool choice failed (Groq 400 tool_use_failed or Tool choice is required)
            if "tool_use_failed" in err_str or "Tool choice is required" in err_str or "failed_generation" in err_str:
                logger.warning(
                    f"Tool calling failed on {model_name} ({err_str[:120]}); falling back to JSON-mode prompt extraction..."
                )
                try:
                    # Attempt json_mode if supported
                    json_runnable = llm.with_structured_output(schema, method="json_mode")
                    return json_runnable.invoke(messages_or_prompt)
                except Exception as json_mode_err:
                    logger.warning(f"json_mode also failed on {model_name}: {json_mode_err}")
                    # Direct raw JSON prompt fallback
                    from langchain_core.messages import HumanMessage, SystemMessage
                    json_prompt = (
                        f"\n\nCRITICAL: Respond ONLY with a valid JSON object strictly matching the schema for {schema.__name__}. "
                        "Do not include any commentary or markdown outside the JSON."
                    )
                    raw_resp = llm.invoke([
                        SystemMessage(content=f"You are a helpful assistant that outputs only valid JSON conforming to {schema.__name__}."),
                        HumanMessage(content=str(messages_or_prompt) + json_prompt),
                    ])
                    raw_text = raw_resp.content if isinstance(raw_resp.content, str) else str(raw_resp.content)
                    raw_cleaned = raw_text.strip()
                    if raw_cleaned.startswith("```"):
                        raw_cleaned = re.sub(r"^```(?:json)?\s*", "", raw_cleaned)
                        raw_cleaned = re.sub(r"\s*```$", "", raw_cleaned)
                    import json as _json
                    parsed_dict = _json.loads(raw_cleaned)
                    if hasattr(schema, "model_validate"):
                        return schema.model_validate(parsed_dict)
                    return schema(**parsed_dict)
            raise tool_err

    def invoke_structured(
        self,
        schema: Type[T],
        messages_or_prompt: Any,
        model_override: str | None = None,
    ) -> T:
        """Invoke LLM with structured output binding, retries, and fallback."""
        target_model = model_override or self.primary_model
        breaker = _breaker_for(target_model)
        last_error: Exception | None = None

        if not breaker.is_open:
            for attempt in range(1, self.max_retries + 1):
                try:
                    result = self._invoke_structured_with_recovery(target_model, schema, messages_or_prompt)
                    breaker.record_success()
                    return result
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Gateway structured primary ({target_model}) attempt {attempt} failed: {e}"
                    )
                    if attempt < self.max_retries:
                        _retry_wait(target_model, attempt, e)
                    else:
                        breaker.record_failure()

        if self.fallback_model and self.fallback_model != target_model:
            logger.info(f"Gateway structured failover to: {self.fallback_model}")
            try:
                return self._invoke_structured_with_recovery(self.fallback_model, schema, messages_or_prompt)
            except Exception as e:
                last_error = e
                logger.error(f"Gateway structured fallback ({self.fallback_model}) failed: {e}")

        raise last_error or RuntimeError("LLM gateway structured invoke failed")


def run_structured(
    schema: Type[T],
    prompt_value: Any,
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 2,
) -> T:
    """Run a structured LLM call through the gateway (retries + fallback)."""
    gateway = LLMGateway(
        primary_model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )
    return gateway.invoke_structured(schema, prompt_value, model_override=model)


# Shared global gateway instance
gateway = LLMGateway()
