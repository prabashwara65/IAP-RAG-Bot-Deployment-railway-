"""In-process rate limiting for expensive public endpoints.

**Limitation, stated plainly.** The counters live in this process's memory.
Every application instance therefore enforces the limit independently: N
running ECS tasks allow up to N times the configured rate in aggregate, and
every deployment resets all windows. This is a deliberate, proportionate
control for the current single-task portfolio deployment. It protects against
casual abuse, a runaway client loop, and accidental cost, not against a
determined or distributed attacker.

A production-grade limiter needs shared storage (Redis or ElastiCache) or an
edge control such as an AWS WAF rate-based rule on the CloudFront
distribution. Neither is in place today.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status

FORWARDED_FOR_HEADER = "X-Forwarded-For"
RETRY_AFTER_HEADER = "Retry-After"
UNKNOWN_CLIENT = "unknown"
RATE_LIMITED_MESSAGE = "Too many requests. Please retry shortly."

# Bounds how many distinct clients are tracked before stale windows are swept,
# so a burst of unique source addresses cannot grow the map without limit.
MAX_TRACKED_CLIENTS = 10_000


def client_key(
    forwarded_for: str | None,
    peer_host: str | None,
    *,
    trusted_proxy_hops: int,
) -> str:
    """Return the address to rate-limit on, read right-to-left.

    ``X-Forwarded-For`` grows left to right: each proxy appends the address it
    saw. Behind CloudFront and an ALB the header reads
    ``<viewer>, <cloudfront-edge>`` because the ALB appends the peer it
    observed. Counting ``trusted_proxy_hops`` entries in from the right
    therefore lands on the viewer rather than on a shared edge address.

    **This header is spoofable.** A client may send its own
    ``X-Forwarded-For``, and every proxy appends rather than replaces, so the
    entry selected here is attacker-influenced if the load balancer can be
    reached directly. The trust assumption is that only the documented proxies
    sit in front of this application. Treat the result as a cost-control key,
    never as an identity.
    """
    entries = [
        entry.strip() for entry in (forwarded_for or "").split(",") if entry.strip()
    ]
    if entries:
        index = len(entries) - 1 - trusted_proxy_hops
        return entries[index] if index >= 0 else entries[0]
    return peer_host or UNKNOWN_CLIENT


def client_identifier(request: Request) -> str:
    """Extract the rate-limit key for one request."""
    settings = getattr(request.app.state, "settings", None)
    trusted_proxy_hops: int = getattr(settings, "rate_limit_trusted_proxy_hops", 0)
    peer_host = request.client.host if request.client is not None else None
    return client_key(
        request.headers.get(FORWARDED_FOR_HEADER),
        peer_host,
        trusted_proxy_hops=trusted_proxy_hops,
    )


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """How many requests one client may make per fixed window."""

    max_requests: int
    window_seconds: int


class FixedWindowRateLimiter:
    """Count requests per client in fixed wall-clock windows.

    A fixed window is chosen over a sliding window deliberately: it needs one
    integer pair per client and no per-request list, which keeps the memory
    profile flat. The known trade-off is that a client may issue up to twice
    the limit across a window boundary, which is acceptable for cost control.

    Instances are per application, so separate app objects never share state.
    The lock is required because the HR endpoint is declared with ``def`` and
    therefore runs in a worker thread.
    """

    def __init__(self, policy: RateLimitPolicy) -> None:
        self._policy = policy
        self._lock = Lock()
        self._windows: dict[str, tuple[int, int]] = {}

    @property
    def policy(self) -> RateLimitPolicy:
        return self._policy

    def check(self, key: str, *, now: float | None = None) -> int | None:
        """Record one request, returning ``None`` when it is allowed.

        When the client is over its limit the request is not recorded and the
        whole seconds remaining in the current window are returned, suitable
        for a ``Retry-After`` header.
        """
        moment = int(time.time() if now is None else now)
        window_start = moment - (moment % self._policy.window_seconds)

        with self._lock:
            recorded_start, count = self._windows.get(key, (window_start, 0))
            if recorded_start != window_start:
                recorded_start, count = window_start, 0

            if count >= self._policy.max_requests:
                self._windows[key] = (recorded_start, count)
                remaining = recorded_start + self._policy.window_seconds - moment
                return max(remaining, 1)

            self._windows[key] = (recorded_start, count + 1)
            if len(self._windows) > MAX_TRACKED_CLIENTS:
                self._sweep(window_start)
            return None

    def _sweep(self, window_start: int) -> None:
        """Drop clients whose window has closed. The caller holds the lock."""
        self._windows = {
            key: value
            for key, value in self._windows.items()
            if value[0] >= window_start
        }


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency that rejects a client over its configured limit.

    Raising ``HTTPException`` keeps the response inside the application's
    existing error contract, so a rate-limited caller receives the same
    ``code``/``message``/``correlation_id`` shape as any other failure.
    """
    limiter: FixedWindowRateLimiter | None = getattr(
        request.app.state, "rate_limiter", None
    )
    if limiter is None:
        return

    retry_after = limiter.check(client_identifier(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMITED_MESSAGE,
            headers={RETRY_AFTER_HEADER: str(retry_after)},
        )
