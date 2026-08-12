# Tests

```
tests/
  conftest.py                          shared fixtures (fake LLM, Supabase session, cleanup)
  unit/
    test_input_handler.py              stage 1
    test_extractor.py                  stage 2
    test_schema_registry.py            stage 3
    test_confidence_engine.py          stage 4
    test_db_layer.py                   Supabase persistence facade, against a fake client
  integration/
    test_pipeline_end_to_end.py        stages 1 -> 3 -> 2 -> 4 -> persisted to Supabase
    test_api_ingest.py                 POST /api/ingest through the real FastAPI app
  fixtures/
    sample_fastener_spec.pdf           synthetic spec sheet (copy of backend/data/samples/)
    sample_response.json               canned Gemini response for that PDF
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
| `pipeline/extractor.py` | 100% |
| `pipeline/schema_registry.py` | 100% |
| `pipeline/types.py` | 100% |
| `pipeline/confidence_engine.py` | 98% |
| `pipeline/input_handler.py` | 88% (the uncovered lines are the OCR fallback, which needs a scanned PDF and a tesseract binary) |
| `models/db.py` | 92% |
| `main.py` | 88% |

`contradiction_detector.py`, `enrichment.py` and `batch_runner.py` report 0%
and are expected to: they are stage 5–7 stubs that raise `NotImplementedError`
and nothing imports them yet. They drag the repo-wide total down, which is why
the per-module numbers above are the ones to read.

`pipeline/llm_client.py` is ~50% by design — the half that isn't covered is the
real network call, which no test is allowed to make.
