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


class LLMGateway:
    """Gateway that routes across primary and fallback LLM models with circuit breaking."""

    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 2,
    ):
        self.primary_model = primary_model or settings.GROQ_MODEL
        self.fallback_model = fallback_model or settings.FALLBACK_MODEL
        self.temperature = temperature
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker()

    def invoke(self, messages: list[Any], model_override: str | None = None) -> Any:
        """Invoke LLM with primary provider and fallback on failure."""
        target_model = model_override or self.primary_model

        # 1. Try Primary (if circuit not open)
        if not self.circuit_breaker.is_open:
            for attempt in range(1, self.max_retries + 1):
                try:
                    llm = get_chat_llm(temperature=self.temperature, model=target_model)
                    response = llm.invoke(messages)
                    self.circuit_breaker.record_success()
                    return response
                except Exception as e:
                    logger.warning(f"Gateway primary ({target_model}) attempt {attempt} failed: {e}")
                    if attempt == self.max_retries:
                        self.circuit_breaker.record_failure()

        # 2. Fallback execution
        logger.info(f"Gateway failing over to fallback model: {self.fallback_model}")
        llm_fallback = get_chat_llm(temperature=self.temperature, model=self.fallback_model)
        return llm_fallback.invoke(messages)

    def invoke_structured(
        self,
        schema: Type[T],
        messages_or_prompt: Any,
        model_override: str | None = None,
    ) -> T:
        """Invoke LLM with structured output binding and fallback."""
        target_model = model_override or self.primary_model

        if not self.circuit_breaker.is_open:
            try:
                llm = get_chat_llm(temperature=self.temperature, model=target_model)
                runnable = llm.with_structured_output(schema)
                result = runnable.invoke(messages_or_prompt)
                self.circuit_breaker.record_success()
                return result
            except Exception as e:
                logger.warning(f"Gateway structured primary ({target_model}) failed: {e}")
                self.circuit_breaker.record_failure()

        logger.info(f"Gateway structured failover to: {self.fallback_model}")
        llm_fb = get_chat_llm(temperature=self.temperature, model=self.fallback_model)
        return llm_fb.with_structured_output(schema).invoke(messages_or_prompt)


# Shared global gateway instance
gateway = LLMGateway()
