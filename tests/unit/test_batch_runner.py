"""Stage 7 unit tests: orchestration only.

Every pipeline stage is mocked here on purpose. What stages 1-6 do to one
product is already covered by their own suites and by the end-to-end tests;
what is under test here is the three things the batch runner adds and nothing
else does — that every item is processed, that one failure doesn't take the
batch with it, and that the concurrency bound actually bounds.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from pipeline import batch_runner
from pipeline.batch_runner import (
    DEFAULT_CONCURRENCY,
    BatchItem,
    resolve_concurrency,
    run_batch,
    summarize,
)


class _FakeProduct:
    def __init__(self, product_id: str) -> None:
        self.id = product_id


class _FakeSession:
    def close(self) -> None:
        pass


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Replace every stage the runner calls with a trivial stand-in.

    Returns a recorder holding the source_refs each stage saw, so a test can
    assert on which items reached which stage.
    """

    class Recorder:
        def __init__(self) -> None:
            self.handled: list[str] = []
            self.extracted: list[str] = []
            self.detected: list[str] = []
            self.enriched: list[str] = []
            self.persisted: list[str] = []
            self.lock = threading.Lock()

        def note(self, bucket: list[str], ref: str) -> None:
            with self.lock:
                bucket.append(ref)

    rec = Recorder()

    class _Doc:
        def __init__(self, ref: str) -> None:
            self.source_ref = ref
            self.raw_text = f"spec sheet for {ref}"

    def fake_handle_input(source_type, source_ref):
        rec.note(rec.handled, source_ref)
        return _Doc(source_ref)

    def fake_extract(raw_doc, schema, llm):
        rec.note(rec.extracted, raw_doc.source_ref)
        return {"doc": raw_doc}

    def fake_score(extraction, raw_doc):
        return []

    def fake_detect(scored, raw_doc, schema):
        rec.note(rec.detected, raw_doc.source_ref)
        return []

    def fake_enrich(scored, schema, llm, flags):
        rec.note(rec.enriched, schema.source_ref)
        return None

    def fake_persist(session, **kwargs):
        rec.note(rec.persisted, kwargs["source_ref"])
        return _FakeProduct(f"id-{kwargs['source_ref']}")

    class _Schema:
        source_ref = "n/a"

    monkeypatch.setattr(batch_runner.registry, "get", lambda category: _Schema())
    monkeypatch.setattr(batch_runner, "handle_input", fake_handle_input)
    monkeypatch.setattr(batch_runner, "extract_fields", fake_extract)
    monkeypatch.setattr(batch_runner, "score_fields", fake_score)
    monkeypatch.setattr(batch_runner, "detect_contradictions", fake_detect)
    monkeypatch.setattr(batch_runner, "enrich", fake_enrich)
    monkeypatch.setattr(batch_runner, "persist_product", fake_persist)
    return rec


def _items(count: int, category: str = "fasteners") -> list[BatchItem]:
    return [
        BatchItem(source_type="text", source_ref=f"item-{i}", category=category)
        for i in range(count)
    ]


def _run(items, **kwargs):
    kwargs.setdefault("llm_factory", lambda: object())
    kwargs.setdefault("session_factory", _FakeSession)
    # Batches are rate limited to 15 requests/minute by default, which would
    # make a 20-item test take two and a half minutes of real sleeping. The
    # limiter has its own suite (test_rate_limiter.py) driven on a fake clock;
    # tests here that aren't about rate limiting run with it out of the way.
    if "rate_limiter" not in kwargs:
        kwargs.setdefault("rate_per_minute", 6_000_000)
    return run_batch(items, **kwargs)


# ---------------------------------------------------------------------------
# Every item gets processed
# ---------------------------------------------------------------------------
def test_all_items_are_processed(stub_pipeline):
    results = _run(_items(12))

    assert len(results) == 12
    assert all(r.status == "ok" for r in results)
    assert sorted(stub_pipeline.handled) == sorted(f"item-{i}" for i in range(12))
    assert sorted(stub_pipeline.persisted) == sorted(f"item-{i}" for i in range(12))


def test_results_come_back_in_input_order(stub_pipeline):
    """Items finish out of order under concurrency; the caller still has to be
    able to line results up with its own list positionally."""
    results = _run(_items(10), concurrency=5)

    assert [r.source_ref for r in results] == [f"item-{i}" for i in range(10)]
    assert [r.product_id for r in results] == [f"id-item-{i}" for i in range(10)]


def test_contradiction_detection_runs_for_every_item(stub_pipeline):
    """The stage most tempting to skip for throughput. A batch is not allowed
    to buy speed by not checking some of its products."""
    _run(_items(8))

    assert sorted(stub_pipeline.detected) == sorted(f"item-{i}" for i in range(8))


def test_an_empty_batch_is_not_an_error(stub_pipeline):
    assert _run([]) == []


# ---------------------------------------------------------------------------
# Isolation: one failure must not stop the rest
# ---------------------------------------------------------------------------
def test_one_failing_item_does_not_stop_the_others(stub_pipeline, monkeypatch):
    real_handle = batch_runner.handle_input

    def sometimes_explodes(source_type, source_ref):
        if source_ref == "item-7":
            raise RuntimeError("corrupt pdf")
        return real_handle(source_type, source_ref)

    monkeypatch.setattr(batch_runner, "handle_input", sometimes_explodes)

    results = _run(_items(20))
    summary = summarize(results)

    assert summary.total == 20
    assert summary.succeeded == 19
    assert summary.failed == 1
    assert [r.source_ref for r in results if r.status == "error"] == ["item-7"]
    assert len(summary.product_ids) == 19


def test_a_failure_records_the_stage_and_the_cause(stub_pipeline, monkeypatch):
    def boom(raw_doc, schema, llm):
        raise RuntimeError("gemini timed out")

    monkeypatch.setattr(batch_runner, "extract_fields", boom)

    (result,) = _run(_items(1))

    assert result.status == "error"
    assert result.product_id is None
    assert result.failed_stage == "extraction"
    # Same "<Stage> failed: <cause>" shape POST /api/ingest already returns.
    assert result.error == "Extraction failed: gemini timed out"


@pytest.mark.parametrize(
    "stage,target",
    [
        ("schema_registry", "registry"),
        ("input_handler", "handle_input"),
        ("extraction", "extract_fields"),
        ("persist", "persist_product"),
    ],
)
def test_every_hard_stage_failure_is_attributed_to_that_stage(
    stub_pipeline, monkeypatch, stage, target
):
    def boom(*args, **kwargs):
        raise RuntimeError("nope")

    if target == "registry":
        monkeypatch.setattr(batch_runner.registry, "get", boom)
    else:
        monkeypatch.setattr(batch_runner, target, boom)

    (result,) = _run(_items(1))

    assert result.status == "error"
    assert result.failed_stage == stage


def test_an_input_with_no_extractable_text_fails_that_item_only(stub_pipeline, monkeypatch):
    real_handle = batch_runner.handle_input

    def blank_for_one(source_type, source_ref):
        doc = real_handle(source_type, source_ref)
        if source_ref == "item-2":
            doc.raw_text = "   "
        return doc

    monkeypatch.setattr(batch_runner, "handle_input", blank_for_one)

    results = _run(_items(4))
    failed = [r for r in results if r.status == "error"]

    assert [r.source_ref for r in failed] == ["item-2"]
    assert failed[0].failed_stage == "input_handler"
    assert summarize(results).succeeded == 3


def test_enrichment_failure_keeps_the_item_successful(stub_pipeline, monkeypatch):
    """Stage 6's fail-soft rule survives the trip into batch mode: the item
    still persists, still gets an id, and reports the error alongside."""

    def boom(scored, schema, llm, flags):
        raise RuntimeError("gemini exploded")

    monkeypatch.setattr(batch_runner, "enrich", boom)

    (result,) = _run(_items(1))

    assert result.status == "ok"
    assert result.product_id == "id-item-0"
    assert result.enrichment_error == "Enrichment failed: gemini exploded"
    assert result.error is None
    assert summarize([result]).failed == 0


def test_each_item_gets_its_own_session(stub_pipeline):
    """Sessions buffer pending rows on the instance, so sharing one across
    threads would interleave two products' rows into a single insert."""
    handed_out = []

    def counting_session():
        session = _FakeSession()
        handed_out.append(session)
        return session

    _run(_items(6), session_factory=counting_session)

    assert len(handed_out) == 6
    assert len({id(s) for s in handed_out}) == 6


# ---------------------------------------------------------------------------
# Concurrency bound
# ---------------------------------------------------------------------------
class _ConcurrencyProbe:
    """Counts how many LLM calls are in flight at once, and the high-water mark."""

    def __init__(self, hold: float = 0.02) -> None:
        self.hold = hold
        self.in_flight = 0
        self.peak = 0
        self.total_calls = 0
        self._lock = threading.Lock()

    def __call__(self):  # used as the llm_factory
        return self

    def complete_json(self, system_prompt, user_prompt, temperature=0.1) -> dict:
        with self._lock:
            self.in_flight += 1
            self.total_calls += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            # Hold the slot long enough that an unbounded runner would pile up.
            threading.Event().wait(self.hold)
            return {}
        finally:
            with self._lock:
                self.in_flight -= 1


@pytest.fixture
def probing_pipeline(stub_pipeline, monkeypatch):
    """Route the stubbed extraction and enrichment stages through the LLM
    stand-in, so the probe sees a real call per stage per item."""

    def extract_via_llm(raw_doc, schema, llm):
        llm.complete_json("sys", "user")
        return {"doc": raw_doc}

    def enrich_via_llm(scored, schema, llm, flags):
        llm.complete_json("sys", "user")
        return None

    monkeypatch.setattr(batch_runner, "extract_fields", extract_via_llm)
    monkeypatch.setattr(batch_runner, "enrich", enrich_via_llm)
    return stub_pipeline


@pytest.mark.parametrize("limit", [1, 2, 3, 5])
def test_in_flight_llm_calls_never_exceed_the_configured_limit(probing_pipeline, limit):
    probe = _ConcurrencyProbe()

    results = _run(_items(20), concurrency=limit, llm_factory=probe)

    assert len(results) == 20
    assert all(r.status == "ok" for r in results)
    assert probe.total_calls == 40, "two LLM calls per item: extraction + enrichment"
    assert probe.peak <= limit, f"{probe.peak} concurrent LLM calls exceeded the limit of {limit}"


def test_the_limit_is_actually_used_not_just_never_exceeded(probing_pipeline):
    """A runner that processed everything sequentially would also pass the
    upper-bound assertion, so pin the lower bound too."""
    probe = _ConcurrencyProbe(hold=0.05)

    _run(_items(12), concurrency=4, llm_factory=probe)

    assert probe.peak > 1, "batch ran sequentially — the concurrency is not doing anything"


def test_the_bound_holds_when_some_items_fail(probing_pipeline, monkeypatch):
    """A failing item releases its slot; it must not leak one either."""
    real_handle = batch_runner.handle_input

    def every_third_explodes(source_type, source_ref):
        if int(source_ref.split("-")[1]) % 3 == 0:
            raise RuntimeError("bad input")
        return real_handle(source_type, source_ref)

    monkeypatch.setattr(batch_runner, "handle_input", every_third_explodes)
    probe = _ConcurrencyProbe()

    results = _run(_items(15), concurrency=3, llm_factory=probe)

    assert probe.peak <= 3
    assert summarize(results).failed == 5


# ---------------------------------------------------------------------------
# Concurrency configuration
# ---------------------------------------------------------------------------
def test_concurrency_defaults_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv(batch_runner.CONCURRENCY_ENV_VAR, raising=False)

    assert resolve_concurrency() == DEFAULT_CONCURRENCY


def test_environment_variable_overrides_the_default(monkeypatch):
    monkeypatch.setenv(batch_runner.CONCURRENCY_ENV_VAR, "9")

    assert resolve_concurrency() == 9


def test_an_explicit_argument_beats_the_environment(monkeypatch):
    monkeypatch.setenv(batch_runner.CONCURRENCY_ENV_VAR, "9")

    assert resolve_concurrency(2) == 2


@pytest.mark.parametrize("bad", ["0", "-4", "banana", ""])
def test_an_unusable_environment_value_falls_back_rather_than_raising(monkeypatch, bad):
    """0 in-flight items would hang instead of failing visibly, and a typo in
    a deployment env var should not take the endpoint down."""
    monkeypatch.setenv(batch_runner.CONCURRENCY_ENV_VAR, bad)

    assert resolve_concurrency() == DEFAULT_CONCURRENCY


def test_summary_counts_match_the_results(stub_pipeline, monkeypatch):
    real_handle = batch_runner.handle_input

    def two_explode(source_type, source_ref):
        if source_ref in ("item-1", "item-4"):
            raise RuntimeError("bad input")
        return real_handle(source_type, source_ref)

    monkeypatch.setattr(batch_runner, "handle_input", two_explode)

    summary = summarize(_run(_items(6)))

    assert (summary.total, summary.succeeded, summary.failed) == (6, 4, 2)
    assert summary.succeeded + summary.failed == summary.total
    assert summary.product_ids == ["id-item-0", "id-item-2", "id-item-3", "id-item-5"]


# ---------------------------------------------------------------------------
# Rate limiting (the quota bound, as opposed to the concurrency bound)
# ---------------------------------------------------------------------------
def test_every_llm_call_in_a_batch_passes_through_the_rate_limiter(probing_pipeline):
    """The semaphore bounds how many calls are in flight; it does not bound
    how many are issued per minute. Both LLM calls of every item have to go
    through the limiter or the batch will blow the provider quota."""
    from pipeline.rate_limiter import RateLimiter

    acquired = []
    limiter = RateLimiter(15, monotonic=lambda: 0.0, sleep=lambda s: acquired.append(s))
    real_acquire = limiter.acquire

    def counting_acquire():
        acquired.append("acquire")
        return real_acquire()

    limiter.acquire = counting_acquire
    probe = _ConcurrencyProbe(hold=0.0)

    _run(_items(10), concurrency=4, llm_factory=probe, rate_limiter=limiter)

    assert probe.total_calls == 20, "two calls per item"
    assert acquired.count("acquire") == 20, "every call must be limited, not just the first"


def test_one_limiter_is_shared_across_the_whole_batch(probing_pipeline):
    """A per-item limiter would bound nothing — the quota is per API key, not
    per product."""
    from pipeline.rate_limiter import RateLimiter

    seen: list[int] = []

    class _TrackingLimiter(RateLimiter):
        def acquire(self) -> float:
            seen.append(id(self))
            return 0.0

    limiter = _TrackingLimiter(15, monotonic=lambda: 0.0, sleep=lambda s: None)
    probe = _ConcurrencyProbe(hold=0.0)

    _run(_items(8), concurrency=4, llm_factory=probe, rate_limiter=limiter)

    assert len(seen) == 16
    assert len(set(seen)) == 1, "items were given separate limiters"


def test_the_batch_builds_a_limiter_when_none_is_supplied(probing_pipeline, monkeypatch):
    """The default path is the one production takes, so it must not be
    possible to run a batch with no rate limiting at all."""
    built = []
    real = batch_runner.RateLimiter

    def tracking(*args, **kwargs):
        limiter = real(*args, **kwargs)
        built.append(limiter)
        return limiter

    monkeypatch.setattr(batch_runner, "RateLimiter", tracking)
    probe = _ConcurrencyProbe(hold=0.0)

    _run(_items(3), concurrency=2, llm_factory=probe, rate_per_minute=6000)

    assert len(built) == 1
    assert built[0].rate_per_minute == 6000


def test_async_entry_point_is_awaitable_from_a_running_loop(stub_pipeline):
    """The endpoint is async, so `run_batch`'s asyncio.run() is unusable there
    — run_batch_async has to work from inside an existing loop."""

    async def main():
        return await batch_runner.run_batch_async(
            _items(3), llm_factory=lambda: object(), session_factory=_FakeSession
        )

    results = asyncio.run(main())

    assert [r.status for r in results] == ["ok", "ok", "ok"]
