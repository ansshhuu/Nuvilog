"""
Stage 7: batch mode.

Contract:

    def run_batch(items: list[BatchItem]) -> list[BatchResult]

Runs the full single-product pipeline (stages 1-6) over N products with
no special-casing — a batch of 1 and a batch of 100 go through the same
code path. Contradiction detection (stage 5) must run for every item in
the batch, not be skipped for throughput.

How that is kept true
---------------------
`_process_item` calls the same six stage functions in the same order as
`POST /api/ingest`, and hands the result to the same `persist_product`
helper that endpoint uses. There is no batch-only branch anywhere in a
stage, no shared cache between items, and no "fast path" that skips
stage 5 — the only thing this module adds is a scheduler around a call
that already existed.

Isolation
---------
One bad input must not cost the other N-1 their results, so every item is
processed inside its own try/except and its own database session. A failure
is recorded as a `BatchResult` with `status="error"` and travels back in the
summary rather than propagating; the batch always returns one result per
item, in the order the items were given.

The error shape is the one stage 6's fail-soft path already established in
`main.py` — a human-readable `"<Stage> failed: <cause>"` string — with the
stage recorded separately in `failed_stage` so a client can group failures
without parsing prose. `enrichment_error` keeps its existing meaning too: it
is set on a *successful* item whose stage 6 call failed, because that item
still has a complete scored field set and a real product id.

Concurrency and rate are two different bounds
---------------------------------------------
Items are independent, and the wall-clock cost of one is dominated by two
network calls to Gemini, so they are run concurrently. The stages themselves
are ordinary blocking functions (pdfplumber, requests, the genai SDK), so each
item runs in a worker thread via `asyncio.to_thread` and an `asyncio.Semaphore`
bounds how many are in flight — `DEFAULT_CONCURRENCY`, tunable per call or via
`NUVILOG_BATCH_CONCURRENCY`.

That semaphore does **not** keep the run inside the provider's quota, and it
was a mistake to think it did. Concurrency is "how many at once"; the quota is
"how many per minute". A Flash-Lite call returns in about a second, so four in
flight issues requests at over 200/minute against a free-tier ceiling of 15 —
measured, a batch of 20 at concurrency=4 hit a peak of 29 requests/60s, took
12 HTTP 429s, and lost 11 of its 20 items. Lowering the concurrency does not
fix it either: concurrency=1 still issues ~54/minute.

So dispatch is rate-limited directly and separately, by a single
`RateLimiter` shared across the whole batch (see pipeline/rate_limiter.py).
The semaphore still earns its place — it caps memory and open PDF handles, and
keeps a slow item from being starved — but the quota is the limiter's job.
"""
from __future__ import annotations

import asyncio
import os
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from pipeline.confidence_engine import score_fields
from pipeline.contradiction_detector import detect_contradictions
from pipeline.enrichment import enrich
from pipeline.extractor import extract_fields
from pipeline.input_handler import handle_input
from pipeline.llm_client import LLMClient
from pipeline.persistence import persist_product
from pipeline.rate_limiter import RateLimitedLLM, RateLimiter
from pipeline.schema_registry import registry
from pipeline.types import InputType

# Two LLM calls per item against a 15 RPM free-tier budget — see module
# docstring. Overridable per call, or globally via the environment.
DEFAULT_CONCURRENCY = 4
CONCURRENCY_ENV_VAR = "NUVILOG_BATCH_CONCURRENCY"

# The stage labels a failure is reported under. Same wording as the messages
# `POST /api/ingest` already returns, so a client that knows one knows both.
STAGE_LABELS = {
    "schema_registry": "Unknown category",
    "input_handler": "Input handling failed",
    "extraction": "Extraction failed",
    "persist": "Persist failed",
}


class BatchItem(BaseModel):
    source_type: InputType
    source_ref: str
    category: str


class BatchResult(BaseModel):
    source_ref: str
    # str, not int: ids are server-generated uuids (see models/db.py). The
    # stub predated the Supabase swap.
    product_id: str | None = None
    status: Literal["ok", "error"]
    failed_stage: str | None = None
    error: str | None = None
    # Set on an item that succeeded despite stage 6 erroring — same fail-soft
    # rule and same field name as the single-product ingest response.
    enrichment_error: str | None = None


class BatchSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    concurrency: int
    results: list[BatchResult] = Field(default_factory=list)

    @property
    def product_ids(self) -> list[str]:
        return [r.product_id for r in self.results if r.product_id]


def resolve_concurrency(concurrency: Optional[int] = None) -> int:
    """Explicit argument, else the environment, else the default.

    A non-positive or unparseable value falls back rather than raising: a
    typo'd env var should not take the batch endpoint down, and 0 in-flight
    items would deadlock instead of erroring visibly.
    """
    if concurrency is not None and concurrency > 0:
        return concurrency

    raw = os.getenv(CONCURRENCY_ENV_VAR)
    if raw:
        try:
            from_env = int(raw)
        except ValueError:
            from_env = 0
        if from_env > 0:
            return from_env

    return DEFAULT_CONCURRENCY


def _new_session():
    """A session backed by the calling thread's own Supabase client.

    Not the shared module-level client: it wraps a connection pool that
    misbehaves when several threads drive it at once (see
    models.db.get_thread_client). Import is deferred so this module stays
    importable without credentials, matching the lazy client in models/db.py.
    """
    from models.db import SupabaseSession, get_thread_client

    return SupabaseSession(client=get_thread_client())


def _process_item(
    item: BatchItem,
    llm_factory: Callable[[], object],
    session_factory: Callable[[], object],
) -> BatchResult:
    """Stages 1-6 plus persist for one item. Never raises.

    Runs in a worker thread, so it gets its own session: `SupabaseSession`
    buffers pending rows on the instance, and sharing one across threads would
    interleave two products' rows into a single insert.
    """
    try:
        schema = registry.get(item.category)
    except Exception as e:
        return _failure(item, "schema_registry", e)

    try:
        raw_doc = handle_input(item.source_type, item.source_ref)
    except Exception as e:
        return _failure(item, "input_handler", e)

    if not raw_doc.raw_text.strip():
        return BatchResult(
            source_ref=item.source_ref,
            status="error",
            failed_stage="input_handler",
            error="Input handling failed: no extractable text found in input.",
        )

    try:
        extraction = extract_fields(raw_doc, schema, llm_factory())
    except Exception as e:
        return _failure(item, "extraction", e)

    # Stages 4 and 5 are pure functions over data already in hand. They run for
    # every item — a batch never trades contradiction detection for throughput.
    scored = score_fields(extraction, raw_doc)
    flags = detect_contradictions(scored, raw_doc, schema)

    # Stage 6 fails soft here exactly as it does in the single-product path:
    # the scored fields are what a reviewer needs, the description is copy on
    # top of them, and losing the item over a missing paragraph is the wrong
    # trade in a batch just as much as on its own.
    enrichment = None
    enrichment_error = None
    try:
        enrichment = enrich(scored, schema, llm_factory(), flags)
    except Exception as e:
        enrichment_error = f"Enrichment failed: {e}"

    try:
        session = session_factory()
    except Exception as e:
        return _failure(item, "persist", e)

    try:
        product = persist_product(
            session,
            input_type=item.source_type,
            source_ref=raw_doc.source_ref,
            category=item.category,
            scored=scored,
            flags=flags,
            enrichment=enrichment,
        )
    except Exception as e:
        return _failure(item, "persist", e)
    finally:
        try:
            session.close()
        except Exception:  # pragma: no cover - close is best effort
            pass

    return BatchResult(
        source_ref=item.source_ref,
        product_id=str(product.id),
        status="ok",
        enrichment_error=enrichment_error,
    )


def _failure(item: BatchItem, stage: str, error: Exception) -> BatchResult:
    return BatchResult(
        source_ref=item.source_ref,
        status="error",
        failed_stage=stage,
        error=f"{STAGE_LABELS.get(stage, stage)}: {error}",
    )


async def run_batch_async(
    items: list[BatchItem],
    concurrency: Optional[int] = None,
    llm_factory: Optional[Callable[[], object]] = None,
    session_factory: Optional[Callable[[], object]] = None,
    rate_per_minute: Optional[int] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> list[BatchResult]:
    """Run every item concurrently, bounded by `concurrency` and by rate.

    Results come back in the order the items were given, regardless of the
    order they finished in, so a caller can line them up with its own input
    list without matching on `source_ref` (which is not unique — the same
    document can legitimately appear twice in one batch).
    """
    llm_factory = llm_factory or LLMClient
    session_factory = session_factory or _new_session

    limit = resolve_concurrency(concurrency)
    semaphore = asyncio.Semaphore(limit)

    # One limiter for the whole batch — a per-item limiter would bound nothing,
    # since the quota is shared across every call the run makes. See
    # pipeline/rate_limiter.py for why the semaphore alone is not enough.
    limiter = rate_limiter or RateLimiter(rate_per_minute)
    base_factory = llm_factory

    def limited_factory():
        return RateLimitedLLM(base_factory(), limiter)

    llm_factory = limited_factory

    async def worker(item: BatchItem) -> BatchResult:
        # The semaphore is held for the whole item, not just its LLM calls, so
        # it bounds everything an item holds open — the parsed PDF, the worker
        # thread, the database session — and not only the network calls. It is
        # not what keeps the run inside the provider's quota; the limiter above
        # is. Both bounds are needed and neither substitutes for the other.
        async with semaphore:
            return await asyncio.to_thread(
                _process_item, item, llm_factory, session_factory
            )

    return list(await asyncio.gather(*(worker(item) for item in items)))


def summarize(results: list[BatchResult], concurrency: Optional[int] = None) -> BatchSummary:
    """Roll per-item results up into the batch summary.

    Pass the same `concurrency` the run was given, so the summary reports the
    bound that was actually applied rather than re-deriving the default.
    """
    succeeded = sum(1 for r in results if r.status == "ok")
    return BatchSummary(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        concurrency=resolve_concurrency(concurrency),
        results=results,
    )


def run_batch(
    items: list[BatchItem],
    concurrency: Optional[int] = None,
    llm_factory: Optional[Callable[[], object]] = None,
    session_factory: Optional[Callable[[], object]] = None,
    rate_per_minute: Optional[int] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> list[BatchResult]:
    """Synchronous entry point, per the stage contract.

    A convenience wrapper for scripts and tests. Async callers — including the
    `POST /api/ingest/batch` endpoint, which is already inside a running event
    loop where `asyncio.run` would raise — should await `run_batch_async`.
    """
    return asyncio.run(
        run_batch_async(
            items,
            concurrency=concurrency,
            llm_factory=llm_factory,
            session_factory=session_factory,
            rate_per_minute=rate_per_minute,
            rate_limiter=rate_limiter,
        )
    )
