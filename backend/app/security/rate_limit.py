"""Tiny in-memory sliding-window rate limiter for sensitive endpoints (login, register, uploads).

LIMITATION (documented in README): state is per-process, so with several workers each has its
own counters. For production use a shared store such as Redis. Behind a reverse proxy, make sure
the proxy passes the real client address (uvicorn --proxy-headers) or all users share one bucket.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _hits.clear()


def rate_limit(name: str, max_calls: int, window_seconds: int):
    def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        client = request.client.host if request.client else "unknown"
        key = f"{name}:{client}"
        now = time.monotonic()
        window = _hits[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= max_calls:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Please wait a moment and try again.",
                headers={"Retry-After": str(window_seconds)},
            )
        window.append(now)

    return dependency
