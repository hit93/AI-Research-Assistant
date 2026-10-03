"""Thread-safe Token-Bucket Rate Limiter with per-client burst capacity and HTTP headers."""

import time
import math
import logging
import threading
from typing import Dict, Tuple, Optional, Callable, Any
from functools import wraps

logger = logging.getLogger("research_assistant.security.rate_limiter")


class RateLimitExceeded(Exception):
    """Exception raised when a client exceeds their rate limit allocation."""
    def __init__(self, key: str, retry_after: float, limit: float):
        self.key = key
        self.retry_after = retry_after
        self.limit = limit
        super().__init__(
            f"Rate limit exceeded for '{key}'. Limit: {limit} req/sec. Retry after {retry_after:.2f}s."
        )


class TokenBucket:
    """Individual token bucket for a specific key."""
    def __init__(self, capacity: float, fill_rate: float):
        self.capacity = float(capacity)
        self.fill_rate = float(fill_rate)  # tokens per second
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> Tuple[bool, float, float]:
        """
        Attempt to consume tokens from the bucket.
        Returns: (allowed: bool, remaining_tokens: float, retry_after_seconds: float)
        """
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            # Replenish tokens based on elapsed time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, self.tokens, 0.0
            else:
                deficit = tokens - self.tokens
                retry_after = deficit / self.fill_rate if self.fill_rate > 0 else 1.0
                return False, self.tokens, retry_after


class TokenBucketRateLimiter:
    """
    Thread-safe Rate Limiter managing token buckets for multiple clients/endpoints.
    """

    def __init__(
        self,
        rate_per_second: float = 5.0,
        burst_capacity: float = 10.0,
        cleanup_interval_seconds: float = 300.0,
    ):
        self.rate_per_second = float(rate_per_second)
        self.burst_capacity = float(burst_capacity)
        self.cleanup_interval = cleanup_interval_seconds
        
        self.buckets: Dict[str, TokenBucket] = {}
        self.lock = threading.Lock()
        self.last_cleanup = time.monotonic()

    def _get_bucket(self, key: str) -> TokenBucket:
        """Get or create bucket for key, with periodic cleanup of stale buckets."""
        with self.lock:
            now = time.monotonic()
            if now - self.last_cleanup > self.cleanup_interval:
                # Cleanup buckets inactive for > 1 hour
                stale_keys = [
                    k for k, b in self.buckets.items()
                    if (now - b.last_update) > 3600.0
                ]
                for k in stale_keys:
                    del self.buckets[k]
                self.last_cleanup = now

            if key not in self.buckets:
                self.buckets[key] = TokenBucket(
                    capacity=self.burst_capacity,
                    fill_rate=self.rate_per_second
                )
            return self.buckets[key]

    def acquire(self, key: str = "global", tokens: float = 1.0) -> Tuple[bool, Dict[str, Any]]:
        """
        Check and consume rate limit quota for key.
        Returns:
            allowed: bool
            info: dict containing standard rate limit metadata and HTTP headers.
        """
        bucket = self._get_bucket(key)
        allowed, remaining, retry_after = bucket.consume(tokens)

        headers = {
            "X-RateLimit-Limit": str(int(self.burst_capacity)),
            "X-RateLimit-Remaining": str(max(0, int(remaining))),
            "X-RateLimit-Reset": str(int(time.time() + retry_after)),
        }
        if not allowed:
            headers["Retry-After"] = str(math.ceil(retry_after))

        info = {
            "allowed": allowed,
            "remaining": remaining,
            "retry_after": retry_after,
            "limit": self.burst_capacity,
            "rate_per_second": self.rate_per_second,
            "headers": headers,
        }

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for key '{key}'. Remaining: {remaining:.1f}, Retry-After: {retry_after:.2f}s"
            )

        return allowed, info

    def check_or_raise(self, key: str = "global", tokens: float = 1.0) -> Dict[str, Any]:
        """Convenience method that raises RateLimitExceeded if rejected."""
        allowed, info = self.acquire(key=key, tokens=tokens)
        if not allowed:
            raise RateLimitExceeded(key=key, retry_after=info["retry_after"], limit=self.rate_per_second)
        return info

    def reset(self, key: Optional[str] = None):
        """Reset a specific key or all buckets (useful for tests)."""
        with self.lock:
            if key:
                if key in self.buckets:
                    del self.buckets[key]
            else:
                self.buckets.clear()


def rate_limited(
    limiter: Optional[TokenBucketRateLimiter] = None,
    key_func: Optional[Callable[..., str]] = None,
    tokens: float = 1.0,
):
    """
    Decorator to apply rate limiting to functions / endpoints.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            active_limiter = limiter or global_rate_limiter
            key = "default"
            if key_func:
                try:
                    key = key_func(*args, **kwargs)
                except Exception:
                    key = "default"
            
            active_limiter.check_or_raise(key=key, tokens=tokens)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# Global singleton rate limiter instance
global_rate_limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst_capacity=20.0)


def get_rate_limiter() -> TokenBucketRateLimiter:
    """Return the global TokenBucketRateLimiter instance."""
    return global_rate_limiter
