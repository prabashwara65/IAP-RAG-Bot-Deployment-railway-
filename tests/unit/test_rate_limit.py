"""Tests for the in-process fixed-window rate limiter."""

from __future__ import annotations

import pytest

from app.core.rate_limit import (
    UNKNOWN_CLIENT,
    FixedWindowRateLimiter,
    RateLimitPolicy,
    client_key,
)

VIEWER = "203.0.113.10"
CLOUDFRONT_EDGE = "198.51.100.5"


def _limiter(max_requests: int = 5, window_seconds: int = 60) -> FixedWindowRateLimiter:
    return FixedWindowRateLimiter(
        RateLimitPolicy(max_requests=max_requests, window_seconds=window_seconds)
    )


def test_the_peer_address_is_used_without_a_forwarded_header() -> None:
    assert client_key(None, "127.0.0.1", trusted_proxy_hops=1) == "127.0.0.1"


def test_an_unknown_client_falls_back_to_a_stable_key() -> None:
    assert client_key(None, None, trusted_proxy_hops=1) == UNKNOWN_CLIENT


def test_the_viewer_is_selected_behind_cloudfront_and_the_alb() -> None:
    """The ALB appends CloudFront's address, so one hop in from the right wins."""
    header = f"{VIEWER}, {CLOUDFRONT_EDGE}"

    assert client_key(header, "10.0.1.20", trusted_proxy_hops=1) == VIEWER


def test_a_single_entry_is_used_when_fewer_hops_are_present() -> None:
    assert client_key(VIEWER, "10.0.1.20", trusted_proxy_hops=1) == VIEWER


def test_surrounding_whitespace_and_empty_entries_are_ignored() -> None:
    header = f"  {VIEWER} , , {CLOUDFRONT_EDGE}  "

    assert client_key(header, None, trusted_proxy_hops=1) == VIEWER


def test_zero_trusted_hops_takes_the_rightmost_entry() -> None:
    header = f"{VIEWER}, {CLOUDFRONT_EDGE}"

    assert client_key(header, None, trusted_proxy_hops=0) == CLOUDFRONT_EDGE


def test_a_spoofed_prefix_cannot_push_the_selection_past_the_left_edge() -> None:
    """More hops than entries degrades to the leftmost entry, never an index error."""
    assert client_key(VIEWER, None, trusted_proxy_hops=5) == VIEWER


def test_requests_below_the_limit_are_allowed() -> None:
    limiter = _limiter(max_requests=5)

    assert [limiter.check(VIEWER, now=1000.0) for _ in range(5)] == [None] * 5


def test_the_request_after_the_limit_is_refused_with_a_retry_delay() -> None:
    limiter = _limiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        limiter.check(VIEWER, now=1000.0)

    retry_after = limiter.check(VIEWER, now=1000.0)

    assert retry_after is not None
    assert 1 <= retry_after <= 60


def test_a_refused_request_is_not_counted_against_the_next_window() -> None:
    limiter = _limiter(max_requests=1, window_seconds=60)
    assert limiter.check(VIEWER, now=1000.0) is None
    assert limiter.check(VIEWER, now=1000.0) is not None

    assert limiter.check(VIEWER, now=1060.0) is None


def test_a_new_window_resets_the_count() -> None:
    limiter = _limiter(max_requests=2, window_seconds=60)
    limiter.check(VIEWER, now=1000.0)
    limiter.check(VIEWER, now=1000.0)
    assert limiter.check(VIEWER, now=1000.0) is not None

    assert limiter.check(VIEWER, now=1080.0) is None


def test_clients_are_counted_independently() -> None:
    limiter = _limiter(max_requests=1)
    assert limiter.check(VIEWER, now=1000.0) is None

    assert limiter.check(CLOUDFRONT_EDGE, now=1000.0) is None
    assert limiter.check(VIEWER, now=1000.0) is not None


@pytest.mark.parametrize("window_seconds", [1, 60, 3600])
def test_the_retry_delay_never_exceeds_the_window(window_seconds: int) -> None:
    limiter = _limiter(max_requests=1, window_seconds=window_seconds)
    limiter.check(VIEWER, now=1000.0)

    retry_after = limiter.check(VIEWER, now=1000.0)

    assert retry_after is not None
    assert 1 <= retry_after <= window_seconds
