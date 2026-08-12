# Tests

```
tests/
  conftest.py                          shared fixtures (fake LLM, Supabase session, cleanup)
  unit/
    test_input_handler.py              stage 1
    test_extractor.py                  stage 2
    test_schema_registry.py            stage 3
    test_confidence_engine.py          stage 4
    test_contradiction_detector.py     stage 5
    test_enrichment.py                 stage 6
    test_batch_runner.py               stage 7 orchestration, every stage mocked
    test_rate_limiter.py               provider rate limiting, on a fake clock
    test_review_ordering.py            finding severity order (contradiction > unverified)
    test_db_layer.py                   Supabase persistence facade, against a fake client
  integration/
    test_pipeline_end_to_end.py        stages 1 -> 3 -> 2 -> 4 -> 5 -> 6 -> persisted to Supabase
    test_api_ingest.py                 POST /api/ingest through the real FastAPI app
    test_batch_ingest.py               a real batch of 5, and POST /api/ingest/batch
  fixtures/
    sample_fastener_spec.pdf              synthetic spec sheet (copy of backend/data/samples/)
    sample_response.json                  canned Gemini response for that PDF
    sample_fastener_spec_with_conflict.txt  spec sheet that contradicts itself (stage 5)
    sample_response_with_conflict.json      canned Gemini response for that document
    sample_response_unquoted_numbers.json   same, with numbers as bare JSON numbers
```

## Running

```bash
cd <repo root>
backend/venv/Scripts/python -m pytest tests/ --cov=backend --cov-report=term-missing   # Windows
# backend/venv/bin/python -m pytest tests/ --cov=backend --cov-report=term-missing     # macOS/Linux
```

Unit tests only (no credentials of any kind needed):

```bash
backend/venv/Scripts/python -m pytest tests/unit
```

Install the test dependencies first with `pip install -r backend/requirements-dev.txt`.

## What is real and what is faked

**The Gemini call is always faked.** Every test that needs an extraction result
uses `tests/fixtures/sample_response.json` via the `fake_llm` fixture, injected
either as the `llm` argument to `extract_fields` or by patching `main.LLMClient`.
CI runs on every push and PR; a real call per run would burn free-tier quota and
make the suite flaky on an API that is allowed to answer differently each time.
No test is permitted to reach the network for an LLM response.

**Everything else in the integration tests is real** — pdfplumber parses the
real fixture PDF, the schema registry reads the real YAML files, the confidence
engine scores against the real extracted text, and rows are written to and read
back from a real Postgres database.

### Why the fixture response is deliberately imperfect

`sample_response.json` is not a "perfect" extraction. Three of its entries are
wrong on purpose, so one fixture exercises all three confidence branches
end-to-end:

| field | fixture value | expected score | why |
|---|---|---|---|
| `material`, `diameter`, `standard`, … | correct, quoted verbatim | `high` | stated after a label in the PDF |
| `package_quantity` | `"500"` | `medium` | a real number, but lifted out of the Notes prose instead of the package line |
| `finish` | `"Hot-dip galvanized"` | `unverified` | fabricated value with an invented citation — the hallucination case |

If a change to the confidence engine ever lets `finish` come back as anything
other than `unverified`, the integration suite fails. That is the point.

### The stage 5 conflict fixture

The clean PDF is internally consistent, so it only exercises one of stage 5's
two checks. It does exercise that one honestly: the source states
`Finish: Passivated, plain` and `Package Quantity: 100 per box`, while
`sample_response.json` claims `Hot-dip galvanized` and `500`, so the detector
raises **two `contradiction` flags** — the extraction disagreeing with the
document. No value in it is implausible enough to trip a range check, so it
produces **no `out_of_range` flag**.

`sample_fastener_spec_with_conflict.txt` covers both. It is the same spec sheet
with a "Reseller summary" section appended that restates the thread diameter as
`12.7 mm` against the spec block's `6.35 mm`, and a package quantity of `0`:

| check | trigger | flag |
|---|---|---|
| cross-field | `Thread Diameter: 6.35 mm` (line 7) vs `Thread Diameter: 12.7 mm` (line 18) | `contradiction` on `diameter` |
| range | `Package Quantity: 0`, below `valid_range.min: 1` in `fasteners.yaml` | `out_of_range` on `package_quantity` |

Its companion `sample_response_with_conflict.json` is a *faithful* extraction —
every value copied verbatim from the spec block. That separates the two failure
modes the fixtures cover: the clean PDF tests a document that is right and an
LLM that is wrong, this one tests an LLM that is right and a document that is
wrong. The same section also restates `length`, `material` and `finish`
identically, and a test asserts none of those are flagged — a detector that
fires on consistent restatements would be worse than none.

It is a `.txt`, not a second PDF: the input handler normalizes both to the same
`RawDocument`, so it exercises stage 5 identically while staying diffable in
review and needing no reportlab step to regenerate.

### Why the stage 6 tests assert on the prompt, not the output

Enrichment's job is to *not* say certain things, and a canned LLM response can
satisfy that by accident. A test that only read the returned description would
pass just as happily against an implementation that fed every contradicted value
to the model and got lucky — so the load-bearing assertions read the user prompt
the stub was actually called with, and fail if an excluded value appears in it at
all.

The conflict fixture is what makes this a real test rather than a tautology: it
produces a genuine `contradiction` on `diameter` and `out_of_range` on
`package_quantity` from the real detector, and
`test_the_field_set_sent_to_the_llm_is_exactly_the_unflagged_trusted_one` states
the expected prompt contents as a *set* derived from stage 4 and 5 output, so a
future field slipping past the filter fails loudly instead of going unnoticed.

## Database used by the integration tests

**A real Supabase project** — not a local Postgres container.

The reason is the shape of the new persistence layer: `backend/models/db.py`
talks to Supabase over PostgREST (HTTP), not over the Postgres wire protocol. A
plain `postgres:16` container would have the right schema and still be
unreachable by the client, so testing against one would mean testing a code path
production never takes. The alternative — running the full Supabase stack
locally via the Supabase CLI — needs Docker plus several containers in CI for no
extra fidelity over pointing at a real project.

**Use a separate Supabase project for tests, not your production one.** The
integration tests insert real rows. They clean up after themselves (each created
product id is deleted in the `db_session` fixture teardown, and
`product_fields` / `validation_flags` cascade), but a crashed run can still
leave rows behind. Set up the test project exactly like the main one: run
`supabase/schema.sql` in its SQL editor, then point `SUPABASE_URL` /
`SUPABASE_KEY` at it.

### Skipping vs. failing

- **Locally**, if `SUPABASE_URL` / `SUPABASE_KEY` are unset, the integration
  tests skip so a fresh clone can still run `pytest tests/unit`.
- **In CI** (`CI=true`, which GitHub Actions sets), missing credentials are a
  hard failure instead. A silent skip there would quietly turn the integration
  suite into a no-op that always looks green.

## Coverage

`--cov=backend` reports the whole backend, but the number that matters is
`backend/pipeline/`. With Supabase credentials configured, the implemented
stages sit at:

| module | coverage |
|---|---|
| `pipeline/enrichment.py` | 100% (unit tests alone; no credentials needed) |
| `pipeline/extractor.py` | 100% |
| `pipeline/schema_registry.py` | 100% |
| `pipeline/types.py` | 100% |
| `pipeline/contradiction_detector.py` | 99% (the one uncovered line is a defensive guard for an empty value, which the callers already filter out) |
| `pipeline/confidence_engine.py` | 98% |
| `pipeline/batch_runner.py` | 98% (the uncovered lines are the failure path of building a database session, which needs Supabase to be unreachable mid-batch) |
| `pipeline/persistence.py` | 95% |
| `models/db.py` | 92% |
| `main.py` | 88% |
| `pipeline/input_handler.py` | 88% (the uncovered lines are the OCR fallback, which needs a scanned PDF and a tesseract binary) |

### Why the stage 7 unit tests mock every stage

`test_batch_runner.py` replaces all six pipeline stages with stand-ins. What
those stages do to one product is already covered by their own suites and by
`test_pipeline_end_to_end.py`; what nothing else covers is the three properties
the batch runner *adds* — that every item is processed, that one item's failure
doesn't take the batch with it, and that the concurrency bound bounds. Mocking
the stages is what makes those testable in milliseconds and deterministically,
including the concurrency assertion, which counts in-flight LLM calls through a
probe standing in for the client and fails if the high-water mark exceeds the
configured limit.

There is a matching lower-bound assertion
(`test_the_limit_is_actually_used_not_just_never_exceeded`) on purpose: a runner
that quietly processed everything sequentially would satisfy "never exceeds the
limit" perfectly, so the upper bound alone proves nothing.

The real-pipeline half lives in `integration/test_batch_ingest.py`, which runs a
batch of 5 mixing the clean PDF fixture with the self-contradicting one. Its
load-bearing assertion is that the conflict fixture still produces both its
`contradiction` and `out_of_range` flags as item 2 of 5 — batching is not
allowed to cost stage 5.

### Rate limiting is tested on a fake clock

`RateLimiter` takes its `monotonic` and `sleep` as constructor arguments purely
so `test_rate_limiter.py` can supply a clock it controls. Proving a
*per-minute* limit against the real clock would mean a multi-minute suite whose
assertions were timing-flaky on CI besides — the fake clock proves the same
property exactly and in milliseconds, including the sliding-window assertion
that no 60-second window ever contains more than the configured number of
requests.

Batches are rate limited to 15 requests/minute by default, so both batch suites
lift the limit for everything that isn't specifically testing it: a 5-item batch
would otherwise spend 36 seconds asleep for no assertion. The integration suite
lifts it through `NUVILOG_GEMINI_RPM`, the way a deployment would, so the real
configuration path stays under test rather than being bypassed.

### Why there is a fixture with unquoted numbers

Every other canned response quotes its numbers — `"value": "0"`. A live
`gemini-flash-lite-latest` does not always: asked for a package quantity of
zero it answers `"value": 0`, a bare JSON number. `ExtractedField.value` is
typed `Optional[str]`, so that used to raise a pydantic validation error and
fail the **entire item**, losing ten correctly extracted fields over one
unquoted digit — in single ingest as much as in batch.

The suite could not catch it, because the fixtures were all written by hand in
the shape the prompt asks for rather than the shape a model actually replies
in. `sample_response_unquoted_numbers.json` is that shape, and stage 2 now
coerces scalars to strings (`types.py`). Keep its numbers unquoted; quoting
them would silently retire the regression test.

Coercion stops at scalars on purpose. A dict or list in `value` means the
response is shaped wrongly, not typed loosely, and is still rejected — 
stringifying it would put `"{'mm': 25.4}"` in the database looking like a real
extracted value.

### What the live-API check found, and why it isn't in this suite

No test here calls the real Gemini API, so nothing here can catch a
provider-side limit. That was checked once, by hand, with a throwaway script
outside `tests/`: a batch of 20 at concurrency=4 with no rate limiter took **12
HTTP 429s and lost 11 of its 20 items**, at a peak of 29 requests/60s against a
budget of 15. With the limiter, the same batch took **zero** 429s at a peak of
exactly 15. That measurement is why `rate_limiter.py` exists; see the stage 7
section of the main README for the numbers in context.

`pipeline/llm_client.py` is ~50% by design — the half that isn't covered is the
real network call, which no test is allowed to make.
