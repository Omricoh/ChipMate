"""Rate limiting middleware for ChipMate API.

Provides in-memory rate limiting to protect against brute force attacks
and API abuse. Uses a sliding window algorithm for accurate rate limiting.

Rate limits:
- Admin login: 5 attempts per IP per 15 minutes
- Game code lookups: 10 requests per IP per minute
- Game creation: 5 games per IP per hour
- Game joins: 10 joins per IP per game per hour
"""

import os
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable
from functools import wraps

from fastapi import Request, HTTPException, status

logger = logging.getLogger("chipmate.middleware.rate_limit")


def _is_rate_limiting_disabled() -> bool:
    """Check if rate limiting should be disabled (e.g., in test environment)."""
    return os.getenv("TESTING", "").lower() in ("1", "true", "yes")


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    max_requests: int
    window_seconds: int
    key_prefix: str


# Predefined rate limit configurations
RATE_LIMITS = {
    "admin_login": RateLimitConfig(
        max_requests=5,
        window_seconds=15 * 60,  # 15 minutes
        key_prefix="admin_login",
    ),
    "game_lookup": RateLimitConfig(
        max_requests=10,
        window_seconds=60,  # 1 minute
        key_prefix="game_lookup",
    ),
    "game_create": RateLimitConfig(
        max_requests=5,
        window_seconds=60 * 60,  # 1 hour
        key_prefix="game_create",
    ),
    "game_join": RateLimitConfig(
        max_requests=10,
        window_seconds=60 * 60,  # 1 hour
        key_prefix="game_join",
    ),
}


@dataclass
class RateLimitEntry:
    """Tracks request timestamps for rate limiting."""
    timestamps: list = field(default_factory=list)


class InMemoryRateLimiter:
    """Thread-safe in-memory rate limiter using sliding window algorithm."""

    def __init__(self):
        self._buckets: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self._lock = Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Clean up every 5 minutes

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        # Check for forwarded headers (common in production behind load balancers)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        if request.client:
            return request.client.host
        return "unknown"

    def _cleanup_old_entries(self, now: float) -> None:
        """Remove expired entries to prevent memory growth."""
        if now - self._last_cleanup < self._cleanup_interval:
            return

        max_window = max(cfg.window_seconds for cfg in RATE_LIMITS.values())
        cutoff = now - max_window

        keys_to_delete = []
        for key, entry in self._buckets.items():
            # Remove old timestamps
            entry.timestamps = [ts for ts in entry.timestamps if ts > cutoff]
            # Mark empty entries for deletion
            if not entry.timestamps:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._buckets[key]

        self._last_cleanup = now
        if keys_to_delete:
            logger.debug("Cleaned up %d expired rate limit entries", len(keys_to_delete))

    def is_rate_limited(
        self,
        request: Request,
        limit_name: str,
        extra_key: str = "",
    ) -> tuple[bool, int, int]:
        """Check if a request should be rate limited.

        Args:
            request: The FastAPI request object.
            limit_name: Name of the rate limit config to apply.
            extra_key: Optional extra key component (e.g., game_id).

        Returns:
            Tuple of (is_limited, remaining_requests, retry_after_seconds).
        """
        config = RATE_LIMITS.get(limit_name)
        if config is None:
            logger.warning("Unknown rate limit name: %s", limit_name)
            return False, 0, 0

        now = time.time()
        client_ip = self._get_client_ip(request)
        bucket_key = f"{config.key_prefix}:{client_ip}"
        if extra_key:
            bucket_key = f"{bucket_key}:{extra_key}"

        with self._lock:
            self._cleanup_old_entries(now)

            entry = self._buckets[bucket_key]
            window_start = now - config.window_seconds

            # Remove timestamps outside the window
            entry.timestamps = [ts for ts in entry.timestamps if ts > window_start]

            current_count = len(entry.timestamps)
            remaining = max(0, config.max_requests - current_count)

            if current_count >= config.max_requests:
                # Calculate retry-after based on oldest timestamp in window
                if entry.timestamps:
                    oldest = min(entry.timestamps)
                    retry_after = int(oldest + config.window_seconds - now) + 1
                else:
                    retry_after = config.window_seconds
                return True, 0, retry_after

            # Record this request
            entry.timestamps.append(now)
            return False, remaining - 1, 0

    def check_rate_limit(
        self,
        request: Request,
        limit_name: str,
        extra_key: str = "",
    ) -> None:
        """Check rate limit and raise HTTPException if exceeded.

        Args:
            request: The FastAPI request object.
            limit_name: Name of the rate limit config to apply.
            extra_key: Optional extra key component (e.g., game_id).

        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded.
        """
        # Skip rate limiting in test environment
        if _is_rate_limiting_disabled():
            return

        is_limited, remaining, retry_after = self.is_rate_limited(
            request, limit_name, extra_key
        )

        if is_limited:
            logger.warning(
                "Rate limit exceeded: %s from %s (retry after %ds)",
                limit_name,
                self._get_client_ip(request),
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        """Reset all rate limit buckets. Used for testing."""
        with self._lock:
            self._buckets.clear()


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


def rate_limit(limit_name: str, extra_key_func: Callable[[Request], str] | None = None):
    """Decorator to apply rate limiting to an endpoint.

    Args:
        limit_name: Name of the rate limit config to apply.
        extra_key_func: Optional function to extract extra key from request.

    Example:
        @router.post("/login")
        @rate_limit("admin_login")
        async def login(request: Request, body: LoginRequest):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find the Request object in args or kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                # No request found, skip rate limiting
                logger.warning(
                    "Rate limit decorator on %s: no Request object found",
                    func.__name__,
                )
                return await func(*args, **kwargs)

            extra_key = ""
            if extra_key_func:
                extra_key = extra_key_func(request)

            rate_limiter.check_rate_limit(request, limit_name, extra_key)
            return await func(*args, **kwargs)

        return wrapper
    return decorator
