"""
Provider rate limiting for batch runs.

Why this exists as well as the batch semaphore
----------------------------------------------
The semaphore in batch_runner bounds *concurrency* — how many items are in
flight. Gemini's free tier bounds *rate* — 15 requests per minute. Those are
not the same quantity, and bounding the first does not bound the second: a
Flash-Lite call returns in about a second, so even a single-threaded loop
issues ~54 requests/minute, and four in flight issues over 200.

Measured, before this module existed: a batch of 20 (40 calls) at
concurrency=4 produced a peak of 29 requests in 60 seconds and 12 HTTP 429s,
failing 11 of the 20 items. No concurrency setting fixes that — concurrency=1
is still ~3x over budget. The dispatch rate has to be limited directly.

How
---
Strict interval scheduling: each caller reserves the next free slot on a
shared timeline, `60 / rate_per_minute` seconds apart, and sleeps until it
comes up. Reservation happens under a lock and the sleep happens outside it,
so N threads waiting get N distinct evenly-spaced slots rather than all
waking at once and re-colliding.

Evenly spaced rather than a burst-capacity token bucket on purpose. A bucket
that allows a burst of 15 spends the entire minute's budget in the first two
seconds, which is exactly the shape that got throttled — and the provider's
window is rolling, so the next request is refused for another 58 seconds.
Smooth dispatch keeps the observed rate under the cap at every offset, not
just on average.

Why the spacing is wider than 60/rate
-------------------------------------
Spacing exactly `60 / rate` seconds apart puts precisely `rate` requests in a
window aligned to a slot boundary — and `rate + 1` in a window that isn't.
A request is issued slightly *after* the slot it reserved (thread wake-up,
TLS, the rest of the pipeline), and that skew slides the window off the
boundary: with 15 slots at 4.0s, a first request delayed by a second gives
issue times 1, 4, 8 ... 60, and the window [1, 61) holds 16.

Measured on a live key at exact spacing: peak 16 requests/60s against a budget
of 15. It did not draw a 429 on that run, but "one over the documented cap and
relying on the provider being lenient" is not a limit. `SAFETY_FACTOR` widens
the interval by 10%, which absorbs several seconds of skew and keeps the
observed peak at or below the cap. The cost is 10% throughput, which is the
right trade against a failure that loses items.

The cost is honest and worth stating: a rate-limited batch takes at least
`2 * items * SAFETY_FACTOR / rate_per_minute` minutes, because every item
spends two calls. That is a property of the quota, not of this implementation
— the only way to make a batch faster is a higher quota.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

# Gemini's documented free-tier ceiling on Flash-Lite. Overridable, because a
# paid key has a much higher one and there is no reason to crawl on it.
DEFAULT_RATE_PER_MINUTE = 15
RATE_ENV_VAR = "NUVILOG_GEMINI_RPM"

# Interval padding that absorbs the skew between reserving a slot and the
# request actually going out — see the module docstring. 1.0 would mean
# spacing exactly at the cap, which measurably peaks one request over it.
SAFETY_FACTOR = 1.1


def resolve_rate_per_minute(rate_per_minute: int | None = None) -> int:
    """Explicit argument, else the environment, else the free-tier default.

    Falls back rather than raising on an unusable value, for the same reason
    the concurrency setting does: a typo in a deployment variable should not
    take the batch endpoint down. A rate of 0 would block forever, which is a
    worse failure than ignoring the typo.
    """
    if rate_per_minute is not None and rate_per_minute > 0:
        return rate_per_minute

    raw = os.getenv(RATE_ENV_VAR)
    if raw:
        try:
            from_env = int(raw)
        except ValueError:
            from_env = 0
        if from_env > 0:
            return from_env

    return DEFAULT_RATE_PER_MINUTE


class RateLimiter:
    """Thread-safe, evenly-spaced request limiter.

    `monotonic` and `sleep` are injectable so tests can drive it on a fake
    clock instead of spending real minutes proving a per-minute limit.
    """

    def __init__(
        self,
        rate_per_minute: int | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rate_per_minute = resolve_rate_per_minute(rate_per_minute)
        self.interval = 60.0 * SAFETY_FACTOR / self.rate_per_minute
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        # Timeline cursor: the earliest instant a new request may be issued.
        # Starts unset so the very first call goes out immediately.
        self._next_slot: float | None = None

    def acquire(self) -> float:
        """Block until this caller's slot comes up. Returns how long it waited.

        The slot is reserved under the lock and waited for outside it — that
        ordering is what makes the limiter correct under concurrency. Holding
        the lock across the sleep would serialize callers onto the same
        instant; not reserving at all would let them all pick the same slot.
        """
        with self._lock:
            now = self._monotonic()
            if self._next_slot is None or self._next_slot < now:
                slot = now
            else:
                slot = self._next_slot
            self._next_slot = slot + self.interval

        wait = slot - self._monotonic()
        if wait > 0:
            self._sleep(wait)
            return wait
        return 0.0


class RateLimitedLLM:
    """Wraps an LLM client so every call passes through a shared limiter.

    A wrapper rather than a change to LLMClient: stage 2 and stage 6 call
    `complete_json` and neither should have to know a batch is happening, and
    the single-product endpoint (two calls per request) has no reason to pay
    for a limiter it cannot exceed.
    """

    def __init__(self, client, limiter: RateLimiter) -> None:
        self._client = client
        self._limiter = limiter

    @property
    def model(self) -> str:
        return getattr(self._client, "model", "unknown")

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
        self._limiter.acquire()
        return self._client.complete_json(system_prompt, user_prompt, temperature)
