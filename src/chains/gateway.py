"""
LLM Gateway — Resilient model router with circuit-breaking, retries, and fallback failover.
"""

import time
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

# Fraction of the context window to reserve for the LLM output (completion).
# The rest is available for the prompt. E.g. 0.45 means output ≤ 45% of window.
_OUTPUT_FRACTION = 0.45


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
                    if attempt == self.max_retries:
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
                    runnable = self._llm(target_model).with_structured_output(schema)
                    result = runnable.invoke(messages_or_prompt)
                    breaker.record_success()
                    return result
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Gateway structured primary ({target_model}) attempt {attempt} failed: {e}"
                    )
                    if attempt == self.max_retries:
                        breaker.record_failure()

        if self.fallback_model and self.fallback_model != target_model:
            logger.info(f"Gateway structured failover to: {self.fallback_model}")
            try:
                runnable = self._llm(self.fallback_model).with_structured_output(schema)
                return runnable.invoke(messages_or_prompt)
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
