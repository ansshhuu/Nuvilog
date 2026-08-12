"""Rate limiter unit tests.

Driven on a fake clock throughout. A per-minute limit tested against the real
clock would mean a multi-minute suite to prove anything, and the assertions
would be timing-flaky on CI besides — so the limiter takes its `monotonic` and
`sleep` as parameters and these tests supply a clock they control exactly.
"""
from __future__ import annotations

import threading

import pytest

from pipeline.rate_limiter import (
    DEFAULT_RATE_PER_MINUTE,
    SAFETY_FACTOR,
    RateLimitedLLM,
    RateLimiter,
    resolve_rate_per_minute,
)


class FakeClock:
    """A monotonic clock that only advances when something sleeps on it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _limiter(clock: FakeClock, rate: int = 15) -> RateLimiter:
    return RateLimiter(rate, monotonic=clock.monotonic, sleep=clock.sleep)


def test_the_first_request_goes_out_immediately(clock):
    limiter = _limiter(clock)

    assert limiter.acquire() == 0.0
    assert clock.sleeps == []


def test_requests_are_spaced_by_the_interval(clock):
    """15/minute is one every 4 seconds, plus the safety padding."""
    limiter = _limiter(clock, rate=15)
    expected = 60.0 * SAFETY_FACTOR / 15

    limiter.acquire()
    assert limiter.acquire() == pytest.approx(expected)
    assert limiter.acquire() == pytest.approx(expected)


def test_the_spacing_leaves_headroom_under_the_cap(clock):
    """Spacing at exactly 60/rate puts `rate` requests in an aligned window and
    `rate + 1` in an unaligned one. Issuing `rate` requests must take longer
    than a minute, so no window of any alignment can hold more."""
    limiter = _limiter(clock, rate=15)

    for _ in range(15):
        limiter.acquire()

    assert clock.now > 60.0, "15 requests fit inside a minute — no headroom for skew"


def test_no_minute_window_ever_contains_more_than_the_limit(clock):
    """Checked as a sliding window over the issue times, which is how the
    provider actually counts — an average under the cap is not enough."""
    limiter = _limiter(clock, rate=15)

    issued = []
    for _ in range(40):
        limiter.acquire()
        issued.append(clock.now)

    for start in issued:
        in_window = sum(1 for t in issued if start <= t < start + 60.0)
        assert in_window <= 15, f"{in_window} requests in the window starting at {start}s"


def test_the_limit_holds_even_when_requests_are_issued_late(clock):
    """The bug the safety factor exists for, reproduced directly.

    A request goes out somewhat after the slot it reserved — thread wake-up,
    TLS, the rest of the pipeline. That skew slides the counting window off the
    slot boundary. Measured against a live key at exact spacing, the peak was
    16 requests/60s against a budget of 15; this pins that it no longer is.
    """
    limiter = _limiter(clock, rate=15)

    reserved = []
    for _ in range(40):
        limiter.acquire()
        reserved.append(clock.now)

    # Model the skew: the first request is a second late, the rest on time.
    issued = [reserved[0] + 1.0] + reserved[1:]

    for start in issued:
        in_window = sum(1 for t in issued if start <= t < start + 60.0)
        assert in_window <= 15, f"{in_window} requests in the window starting at {start}s"


def test_an_idle_gap_does_not_bank_up_a_burst(clock):
    """The failure mode a token bucket with burst capacity would have: sit
    idle for five minutes, then fire 75 requests at once and get throttled.
    The timeline cursor is pulled forward to now instead of accumulating."""
    limiter = _limiter(clock, rate=15)
    limiter.acquire()

    clock.now += 300.0  # five idle minutes

    assert limiter.acquire() == 0.0, "one free slot after idling, not a backlog"
    assert limiter.acquire() == pytest.approx(
        60.0 * SAFETY_FACTOR / 15
    ), "and then back to the normal spacing"


def test_concurrent_callers_get_distinct_slots(clock):
    """The load-bearing concurrency property. If reservation weren't atomic,
    threads would compute the same slot and all fire at once."""
    limiter = _limiter(clock, rate=60)  # 1s spacing, easier arithmetic
    slots: list[float] = []
    slots_lock = threading.Lock()
    start = threading.Barrier(8)

    def worker():
        start.wait()
        limiter.acquire()
        with slots_lock:
            slots.append(limiter._next_slot)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(slots)) == 8, "two callers were handed the same slot"


def test_the_limiter_is_shared_state_not_per_caller(clock):
    """Two clients built from the same limiter must contend for one budget —
    a per-client limiter would bound nothing, since the quota is per key."""
    limiter = _limiter(clock, rate=15)
    first = RateLimitedLLM(_StubLLM(), limiter)
    second = RateLimitedLLM(_StubLLM(), limiter)

    first.complete_json("s", "u")
    second.complete_json("s", "u")

    assert clock.sleeps == [pytest.approx(60.0 * SAFETY_FACTOR / 15)]


class _StubLLM:
    model = "stub"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def complete_json(self, system_prompt, user_prompt, temperature=0.1) -> dict:
        self.calls.append((system_prompt, user_prompt, temperature))
        return {"ok": True}


def test_the_wrapper_passes_everything_through(clock):
    stub = _StubLLM()
    wrapped = RateLimitedLLM(stub, _limiter(clock))

    result = wrapped.complete_json("system", "user", 0.7)

    assert result == {"ok": True}
    assert stub.calls == [("system", "user", 0.7)]
    assert wrapped.model == "stub"


def test_the_wrapper_limits_before_calling_not_after(clock):
    """A limiter that ran after the call would let the first burst through."""
    order: list[str] = []

    class _Recording(_StubLLM):
        def complete_json(self, system_prompt, user_prompt, temperature=0.1):
            order.append("called")
            return {}

    limiter = RateLimiter(
        15,
        monotonic=clock.monotonic,
        sleep=lambda s: (order.append("slept"), clock.sleep(s))[1],
    )
    wrapped = RateLimitedLLM(_Recording(), limiter)

    wrapped.complete_json("s", "u")
    wrapped.complete_json("s", "u")

    assert order == ["called", "slept", "called"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def test_rate_defaults_to_the_free_tier_ceiling(monkeypatch):
    monkeypatch.delenv("NUVILOG_GEMINI_RPM", raising=False)

    assert resolve_rate_per_minute() == DEFAULT_RATE_PER_MINUTE == 15


def test_environment_variable_overrides_the_default(monkeypatch):
    monkeypatch.setenv("NUVILOG_GEMINI_RPM", "1000")

    assert resolve_rate_per_minute() == 1000


def test_an_explicit_argument_beats_the_environment(monkeypatch):
    monkeypatch.setenv("NUVILOG_GEMINI_RPM", "1000")

    assert resolve_rate_per_minute(30) == 30


@pytest.mark.parametrize("bad", ["0", "-1", "banana", ""])
def test_an_unusable_rate_falls_back_rather_than_raising(monkeypatch, bad):
    """A rate of 0 would block forever — a worse failure than ignoring a typo."""
    monkeypatch.setenv("NUVILOG_GEMINI_RPM", bad)

    assert resolve_rate_per_minute() == DEFAULT_RATE_PER_MINUTE


def test_a_higher_rate_really_is_faster(clock):
    """A paid key shouldn't crawl at the free tier's pace."""
    fast = RateLimiter(600, monotonic=clock.monotonic, sleep=clock.sleep)

    fast.acquire()
    assert fast.acquire() == pytest.approx(60.0 * SAFETY_FACTOR / 600)
