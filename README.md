# 🏭 Nuvilog

Turns messy, unstructured product data — PDFs, spec sheets, partial CSVs, URLs — into structured, evidence-backed product listings for B2B industrial distributors.

## 🌟 The Problem

- Industrial distributors get product data from suppliers in every format imaginable: scanned PDF spec sheets, half-filled CSVs, a manufacturer's product page. None of it is structured.
- Turning that into a clean catalog listing today means a person manually reading a spec sheet and retyping fields — slow, and it doesn't scale past a few hundred SKUs.
- Feeding it to an LLM and trusting whatever comes back is worse: LLMs will confidently fill in a voltage rating or a thread pitch that was never in the source document, and there's no way to tell which fields are real.
- What's actually needed is extraction that shows its work — every field traceable to the exact text it came from, or explicitly flagged as a guess — so a human reviewer can trust the output instead of re-checking all of it by hand.

## 🛠️ The Solution

A pipeline of independently testable stages, each with a typed input/output contract, so a stage can be built, tested, and trusted in isolation before the next one is wired in.

### 1. Input handler
**How it works:** Accepts a PDF, CSV, raw text, or URL and normalizes every format down to the same shape — plain text plus any tables found. PDFs are parsed with `pdfplumber`; pages with too little extractable text fall back to `pytesseract` OCR. URLs are scraped with `requests` + `BeautifulSoup`.
**Result:** A `RawDocument` — one consistent shape downstream stages can rely on regardless of where the data came from.

### 2. Extraction
**How it works:** One Gemini (`gemini-flash-lite-latest`) call per product, using the category's field list as the prompt and Gemini's native JSON mode to keep output machine-parseable. The model is a floating alias rather than a pinned version — a pinned `gemini-2.5-flash-lite` was withdrawn for new API keys and 404'd every call, so tracking the current Flash-Lite is the more durable default. Override with `GEMINI_MODEL`. For every field, the model returns both a value and the verbatim snippet of source text it claims supports it.
**Result:** A value *and* a citation for every field — the raw material the confidence engine needs to check its work.

### 3. Category-aware schema layer
**How it works:** Each product category (fasteners, electrical, plumbing) is a YAML file under `backend/schemas/` listing its required and optional fields, types, units, and valid ranges. The registry loads every file in that directory at startup — nothing in the pipeline code branches on category name.
**Result:** Adding a 4th category is dropping in a new YAML file, not writing new code.

### 4. Confidence engine
**How it works:** Pure evidence checking against the source text — no second LLM call, no self-rating. A value stated directly in a "Field: value" pattern in the source scores **HIGH**. A value only supported by surrounding context (mentioned, but not directly stated) scores **MEDIUM**, with the supporting phrase recorded as an `inference_chain`. A value with no support anywhere in the source scores **UNVERIFIED** and is flagged as AI-suggested rather than fact.
**Result:** Every stored field carries a confidence level a human can trust, because it was computed from the text — not asked from the model that generated it.

### 5. Contradiction detection
**How it works:** Deterministic re-reading of the source, no second LLM call. Every `Label: value` statement in the document — in prose and in table rows — is collected, and each field's statements are grouped by equivalence: numeric fields by magnitude (so `25.4 mm` and `25.40 mm (1 in)` agree), text fields by containment (so `Hex` and `Hex Head` agree). More than one group means the document says two different things about one attribute, or says something different from what was extracted. Separately, numeric values are checked against the `valid_range` declared for that field in the category YAML.
**Result:** Conflicts surfaced as `validation_flags` rows (`contradiction` / `out_of_range`) before a product ever reaches review, each message naming every conflicting value and the line or table row it came from. Nothing is auto-resolved — a detector that quietly picked a winner would be guessing at exactly the moment a human needs to look.

### 6. Enrichment
**How it works:** A genuine second Gemini call, separate from extraction, that writes a 2–4 sentence commerce description and fills non-critical gaps. What it is allowed to see is the whole design: only fields that are **both** HIGH/MEDIUM confidence **and** carry no stage 5 flag are put in the prompt as facts. Unverified, contradicted and out-of-range values are dropped from the prompt entirely rather than passed with a caveat — a value the model never sees is a value it cannot assert, whereas a caveat is an instruction it can ignore. Gap filling is restricted to *optional* fields that are genuinely empty: a required field is never auto-filled, and a field that already holds a value (even an unverified one) is never overwritten, because that value is a real claim from the source a reviewer still needs to see.
**Result:** A description written only from data that survived stages 4 and 5, stored on `products.description`. Any field this stage invents lands in `product_fields` under the same trust labels as everything else — `is_ai_generated=true`, `confidence_level=unverified`, `evidence_type=none` — so it shows up in `review_findings` like any other unsupported value. There is deliberately no "generated by enrichment, trust it" shortcut: this is the one stage where fluent prose could silently launder bad data, and the filter is what stops it.

### 7. Batch mode
**How it works:** The same single-product pipeline (stages 1–6) looped over N inputs with no special-casing — `POST /api/ingest/batch` calls the identical six stage functions in the identical order as `POST /api/ingest`, and hands the result to the same persistence helper, so a product ingested in a batch lands in the database indistinguishable from the same product ingested on its own. There is no batch-only branch inside a stage and no fast path that skips stage 5: contradiction detection runs on every item, because a batch buying throughput by not checking some of its products would defeat the entire pipeline. Items run concurrently on a bounded `asyncio.Semaphore` (default 4 in flight), each in its own worker thread and its own database session, and each inside its own error boundary — with LLM dispatch separately rate-limited to stay inside the provider quota.
**Result:** One request, N products, and a summary that is honest about what happened to each: `total` / `succeeded` / `failed`, every successful product's id, and for every failure the stage it died at (`failed_stage`) plus the reason — reusing the `"<Stage> failed: <cause>"` shape stage 6's fail-soft path already established rather than inventing a second error format. **One item's failure never aborts the batch:** if input #7 of 20 hits a corrupt PDF or an LLM timeout, the other 19 still complete, persist, and come back in the response. Stage 6 keeps its fail-soft rule inside a batch too — an item whose enrichment call fails is still a *success*, with its full scored field set persisted and an `enrichment_error` string alongside.

**This closes the last PRD "must have".** Batch mode was the final unimplemented item on the required list; stages 1–7 are all live. Stages 8 (export) and 9 (review dashboard) remain, and both are PRD *nice-to-haves*, not must-haves.

#### Two different bounds: concurrency and rate

These are separate knobs and conflating them is a real bug, so they're documented separately.

**Concurrency** — how many items are processed at once. Default **4**, via an `asyncio.Semaphore`. It caps memory and open file handles and keeps a slow item from starving the rest.

**Rate** — how many requests per minute reach Gemini. Default **15/minute**, matching the free tier's Flash-Lite ceiling, enforced by a token-style limiter in [`backend/pipeline/rate_limiter.py`](backend/pipeline/rate_limiter.py) that is shared across the whole batch and spaces dispatches evenly.

**The semaphore does not bound the rate, and an earlier version of this README wrongly claimed it did.** A Flash-Lite call returns in about a second, so 4 in flight issues requests at over 200/minute against a ceiling of 15. Measured on a live key before the limiter existed:

```
20 items, concurrency=4, no rate limiter
  peak requests/60s  : 29   (budget: 15)
  LLM calls 429'd    : 12 of 29
  items failed       : 11 of 20
```

Lowering concurrency does not fix this — at ~1s per call, even concurrency=1 issues ~54/minute, still 3.6× over. Rate has to be limited directly. With the limiter in place, same batch, same key:

```
20 items, concurrency=4, rate limiter at 15/min
  peak requests/60s  : 14   (budget: 15)
  LLM calls 429'd    : 0 of 38
  wall clock         : 165s
```

The limiter spaces requests 10% wider than `60 / rate` (`SAFETY_FACTOR` in `rate_limiter.py`). Exact spacing is off-by-one under load: a request goes out slightly after the slot it reserved, which slides the provider's counting window off the slot boundary and lets it hold `rate + 1`. An intermediate run at exact spacing measured a peak of **16**/60s against a budget of 15 — it drew no 429, but depending on the provider being lenient about a documented cap is not a limit. The padding costs 10% throughput and moved the measured peak to 14.

Tuning, most specific first:

| Knob | How | Scope |
|---|---|---|
| concurrency | `concurrency` form field on the request | that one request |
| concurrency | `NUVILOG_BATCH_CONCURRENCY` | the deployment |
| concurrency | `DEFAULT_CONCURRENCY` in `batch_runner.py` | the code default |
| rate | `NUVILOG_GEMINI_RPM` | the deployment |
| rate | `DEFAULT_RATE_PER_MINUTE` in `rate_limiter.py` | the code default |

The rate is deliberately **not** a request parameter: a per-request override would let any client spend the whole key's quota. For either knob, a missing, zero, negative or unparseable value falls back to the default rather than raising — a typo in a deployment variable shouldn't take the endpoint down, and a limit of 0 would block forever instead of failing visibly. The concurrency actually applied is echoed back in the response.

On a paid key, raise both together; they only make sense in proportion.

#### Why the endpoint is synchronous

`POST /api/ingest/batch` blocks until the whole batch is done and returns every result in one response. The alternative — return a `batch_id` immediately, write progress to a jobs table, add `GET /api/batches/{id}` for polling — was considered and rejected *at this scale and quota*, with the caveat below:

- **Async buys a lot of failure modes.** A job table, a status endpoint, a state machine per batch, and a new way to lose work: an in-memory job queue evaporates on a restart or a second replica, and this deployment has no worker process to own it.
- **Synchronous is already honest about partial failure.** The thing polling normally buys — visibility into which items failed — is in the response body here, per item, with the stage that failed. Nothing is hidden by waiting.
- **The cap is explicit and derived.** `MAX_BATCH_ITEMS = 25` in `backend/main.py`. A larger batch is rejected with a `413` naming the limit rather than quietly holding a connection open.

**The honest caveat: the rate limit, not the pipeline, sets the wall clock.** A batch takes roughly `2 × items / rate_per_minute` minutes, because each item spends two LLM calls. On the free tier that is ~3.7 minutes for 25 items (measured: 165s for 20). That is a long-lived HTTP request — long enough that a default 60s proxy or client timeout will cut it, so a demo needs to allow for it. The trade is still right for a hackathon demo of dozens of items, but it is a trade, not a free win. Two things move the ceiling: a paid key (raise `NUVILOG_GEMINI_RPM`, which shortens the wait proportionally) or the async job path. If batches ever need to be genuinely large, the 413 is the signal to build the latter — and the runner needs no changes, since `run_batch_async` is already the interface a worker would call.

### 8. Export & 9. Review dashboard — *not yet implemented*
**How it works (planned):** Structured JSON/CSV export, and a thin React dashboard showing per-field confidence, source snippet on hover, and contradiction flags.

**Note for the review UI:** findings are ranked, and the ranking is already computed server-side — both `POST /api/ingest` and `GET /api/products/{id}` return a `review_findings` array sorted most-severe-first, alongside the raw `flags`. The order is `contradiction` → `out_of_range` → `unverified`, because *"the source says something different"* is a stronger signal than *"the source says nothing"*: a contradiction points at a specific line to go read. A field can carry both — a fabricated value that the source explicitly contradicts is `unverified` from stage 4 **and** `contradiction` from stage 5 — and in that case the contradiction is what should get the visual weight. Render `review_findings` in the order given rather than re-deriving the precedence client-side.

## 🏗️ Technical Infra at a Glance

```
                     ┌──────────────────┐
  pdf / csv / text / │  1. Input Handler │  pdfplumber + OCR fallback
  url                │                   │  requests + BeautifulSoup
                     └─────────┬─────────┘
                               │ RawDocument {raw_text, tables}
                               ▼
                     ┌──────────────────┐      ┌─────────────────────┐
                     │  3. Schema        │◄─────┤ schemas/*.yaml       │
                     │     Registry      │      │ fasteners/electrical/│
                     │                   │      │ plumbing (add more   │
                     └─────────┬─────────┘      │ by dropping a file)  │
                               │ field list for category
                               ▼
                     ┌──────────────────┐
                     │  2. Extraction    │  Gemini 2.5 Flash-Lite
                     │                   │  JSON mode, 1 call/product
                     └─────────┬─────────┘
                               │ value + source_snippet per field
                               ▼
                     ┌──────────────────┐
                     │  4. Confidence    │  pure string evidence check
                     │     Engine        │  HIGH / MEDIUM / UNVERIFIED
                     └─────────┬─────────┘  (no LLM call)
                               │ scored fields
                               ▼
                     ┌──────────────────┐
                     │  5. Contradiction │  labelled-statement + range check
                     │     Detector      │  contradiction / out_of_range
                     └─────────┬─────────┘  (no LLM call)
                               │ scored fields + flags
                               ▼
                     ┌──────────────────┐
                     │  6. Enrichment    │  Gemini 2.5 Flash-Lite, 2nd call
                     │                   │  HIGH/MEDIUM + unflagged fields ONLY
                     └─────────┬─────────┘  output → unverified, ai_generated
                               │
                 ┌─────────────┴─────────────┐
                 ▼ IMPLEMENTED                ▼ NOT YET IMPLEMENTED
        products / product_fields    8. Export (JSON/CSV)
        validation_flags             9. Review Dashboard (React)
           (Supabase / Postgres)

        7. Batch Runner wraps the whole column above: N inputs, the same
           stages 1-6 per item, bounded concurrency (default 4 in flight),
           one error boundary per item.  POST /api/ingest/batch
```

## ⚠️ Important Caveats

- **Sample data is synthetic.** `backend/data/samples/sample_fastener_spec.pdf` is a spec sheet generated by `backend/data/samples/make_sample_pdf.py` for testing — not a real manufacturer document. Treat all example output in this repo as illustrative, not a demo of real-world accuracy.
- **Honest implementation status:** stages 1 (input handler), 2 (extraction), 3 (schema registry), 4 (confidence engine), 5 (contradiction detection), and 6 (enrichment) are implemented and wired into `POST /api/ingest`; stage 7 (batch mode) is implemented and wired into `POST /api/ingest/batch`. That completes every PRD must-have. Stages 8 (export) and 9 (review dashboard) are stubs only — each has a typed contract and docstring in its module under `backend/pipeline/`, but calling them raises `NotImplementedError`. There is no frontend yet.
- **Enrichment is the only stage allowed to fail soft.** If the stage 6 call errors, the ingest still returns 200 with the full scored field set, a null `description`, and an `enrichment_error` string in the response. Extraction produces what a reviewer needs; enrichment only adds copy on top of it, so a 502 there would throw away a complete result over a missing paragraph. The failure is reported, never swallowed.
- **Known v2 gap: string fields have no enum checking.** Stage 5 range-checks numeric fields against `valid_range`, but there is no `valid_values` key in the schemas and no enum check for text fields — a `head_type` of `"banana"` passes today. Adding it means a new `FieldDef` key plus a third check type, and needs care not to false-positive on free-text fields like `finish` and `material`.
- **Contradiction detection is deterministic, not LLM-judged.** Stage 5 finds conflicts by re-reading the source text — labelled-statement matching and numeric range checks — for the same reason stage 4 computes confidence from evidence instead of asking the model to rate itself: a model grading its own extraction produces a number nobody can check. The tradeoff is real and worth stating: it catches conflicts that are *stated* somewhere in the document, and will miss ones that need semantic judgment (a material that's incompatible with a listed temperature rating, say). It flags what it can prove and stays quiet otherwise, rather than guessing.
- **No auth, single-tenant.** This is a hackathon prototype: no login, no API keys beyond the LLM provider and Supabase, no multi-user isolation. Every product in the database is visible to anyone who can reach the API. Do not point this at real customer or supplier data as-is.
- **No transactions.** The backend talks to Supabase over PostgREST, which has no transaction support. A failure partway through an ingest can leave a `products` row with none of its `product_fields`. Nothing silently disappears, but partial rows are possible. This applies per item in a batch: a batch is N independent writes, not one atomic one, so a partial batch is a normal outcome and the summary reports exactly which items made it.
- **Batch mode is synchronous and capped at 25 items per request.** The client holds the connection until the whole batch finishes, which on the free tier's 15 requests/minute is about 3.7 minutes for a full batch (measured: 165s for 20 items). Long enough that a default 60s proxy or client timeout will cut it. That is the right trade at demo scale and the wrong one at catalog-migration scale — see [stage 7](#7-batch-mode) for the reasoning, the measurements, and what would have to be built instead.
- **Throughput is bounded by the LLM quota, not by the code.** A batch takes roughly `2 × items / rate_per_minute` minutes because every item spends two Gemini calls. The only ways to make it faster are a higher quota or fewer calls per item; adding concurrency past the rate limit does nothing but queue.

## 🚀 Getting Started

**Prerequisites:** Python 3.11+, a free [Gemini API key](https://aistudio.google.com/app/apikey), and a free [Supabase](https://supabase.com) project. (Optional, for OCR fallback on scanned PDFs: the `tesseract` binary on PATH.)

### 1. Create the Supabase project and schema

1. Sign in at [supabase.com](https://supabase.com) and create a new project (the free tier is enough). Note the database password you set — you won't need it here, but Supabase will ask for it once.
2. Wait for provisioning to finish, then open **SQL Editor → New query**.
3. Paste the entire contents of [`supabase/schema.sql`](supabase/schema.sql) and hit **Run**. This creates `products`, `product_fields`, and `validation_flags` with their indexes and foreign keys, and enables row level security on all three.
4. Open **Table Editor** and confirm the three tables are listed.

The schema is idempotent (`create table if not exists`), so re-running it on an existing project is safe.

### 2. Get your keys

In the Supabase dashboard, go to **Project Settings → API** and copy:

- **Project URL** → `SUPABASE_URL`
- **service_role key** (under *Project API keys*) → `SUPABASE_KEY`

Use the `service_role` key, not the `anon` key. It is a server-side secret — it bypasses row level security and must never be committed or shipped to a browser. `.env` is gitignored; keep it that way.

### 3. Install and run

```bash
cd backend
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # Windows
# venv/bin/pip install -r requirements.txt       # macOS/Linux

cp ../.env.example ../.env
# edit .env: set GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY

./venv/Scripts/uvicorn main:app --reload   # Windows
# venv/bin/uvicorn main:app --reload       # macOS/Linux
```

On startup the API checks that all three Supabase tables are reachable and refuses to start with a clear error if they aren't — unlike the old SQLite setup, it cannot create them for you, because PostgREST can't issue DDL. If you see that error, re-run step 1.

API docs (interactive, try-it-out) live at **http://127.0.0.1:8000/docs**.

Test the pipeline against the included sample PDF:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -F "category=fasteners" \
  -F "input_type=pdf" \
  -F "file=@backend/data/samples/sample_fastener_spec.pdf"
```

Returns the created `product_id` (a uuid) and every extracted field with its `value`, `confidence_level` (`high` / `medium` / `unverified`), `source_snippet`, and `inference_chain`. The same row should now be visible in the Supabase **Table Editor** under `products`. Fetch the persisted record any time with:

```bash
curl http://127.0.0.1:8000/api/products/<product_id>
```

Run a whole batch through the same pipeline (stage 7). Uploaded files go in `files`, and text/URL inputs go in `items` as a JSON array, so one batch can mix formats:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/batch \
  -F "category=fasteners" \
  -F "files=@backend/data/samples/sample_fastener_spec.pdf" \
  -F "files=@another_spec.pdf" \
  -F 'items=[{"source_type":"url","source_ref":"https://example.com/part-page"},
             {"source_type":"text","source_ref":"Material: Stainless 18-8..."}]' \
  -F "concurrency=4"
```

Returns the summary, not the full detail of every product:

```json
{
  "total": 4, "succeeded": 3, "failed": 1, "concurrency": 4,
  "product_ids": ["8f3c...", "b21a...", "d907..."],
  "results": [
    {"source_ref": "...", "product_id": "8f3c...", "status": "ok",
     "failed_stage": null, "error": null, "enrichment_error": null},
    {"source_ref": "...", "product_id": null, "status": "error",
     "failed_stage": "input_handler",
     "error": "Input handling failed: No /Root object! - Is this really a PDF?",
     "enrichment_error": null}
  ]
}
```

Fetch full detail for any of them with the same `GET /api/products/{id}` a single ingest uses — a batched product has no separate read path, because it is not a separate kind of product.

Note that a failed *item* is not a failed *request*: the other items succeeded, so the response is a 200 with the failure described in the body. Only a malformed request (unknown category, no inputs, bad `items` JSON) is a 4xx.

List available categories and their schemas:

```bash
curl http://127.0.0.1:8000/api/categories
```

Sanity-check the confidence engine on its own (no API key needed — it's pure string logic, no LLM call):

```bash
cd backend
./venv/Scripts/python data/samples/test_confidence_engine.py
```

## 🧪 Tests

```bash
pip install -r backend/requirements-dev.txt
pytest tests/ --cov=backend --cov-report=term-missing
```

Unit tests need no credentials at all; the integration tests need a Supabase project (a **separate test project**, not the one holding real data — they insert and delete rows). No test ever calls the real Gemini API — the LLM response is a fixture. Full details, including why the integration tests target a real Supabase project rather than a local Postgres container, are in [`tests/README.md`](tests/README.md).

## 🐳 Docker

```bash
docker build -t nuvilog:latest .
docker run --rm -p 8000:8000 --env-file .env nuvilog:latest
```

**Quote your `.env` values at your peril.** `python-dotenv` (used when running locally) strips surrounding quotes from a value; `docker run --env-file` does **not** — it passes them through literally, so `SUPABASE_URL="https://xyz.supabase.co"` reaches the container with the quotes still attached and the Supabase client rejects it as `Invalid URL`. Write the values unquoted:

```bash
SUPABASE_URL=https://xyz.supabase.co   # correct
SUPABASE_URL="https://xyz.supabase.co" # breaks under --env-file
```

The image bundles `tesseract-ocr` for the scanned-PDF fallback, so `TESSERACT_CMD` can be left empty inside the container.

## ⚙️ CI Setup

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull request to `main`: unit tests, integration tests, `ruff` lint, and then a Docker image build. Nothing soft-fails — any test failure or lint error fails the run.

**Before CI can go green you must add these three repository secrets by hand**, in **GitHub → your repo → Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key. The tests stub the LLM call, so this is only needed for modules that construct a client at import time — set it to a real key or any non-empty placeholder. |
| `SUPABASE_URL` | Project URL of the Supabase project CI should write to. Use a dedicated test project. |
| `SUPABASE_KEY` | That project's `service_role` key. |

The test project needs [`supabase/schema.sql`](supabase/schema.sql) applied to it, exactly like a local setup.

If the Supabase secrets are missing, the integration job **fails** rather than skipping. That is deliberate: locally the integration tests skip when credentials are absent, but a skip in CI would quietly report green on a suite that never ran.

## Data model

Supabase (Postgres), defined in [`supabase/schema.sql`](supabase/schema.sql) and applied manually once per project. Primary keys are `uuid` (`gen_random_uuid()`) and timestamps are `timestamptz`:

- `products(id, raw_input_type, raw_input_ref, category, status, description, created_at)` — `description` is written by stage 6 and is nullable: a product ingested before stage 6 existed, or one whose enrichment call failed, still has a complete scored field set and is not invalid without it
- `product_fields(id, product_id, field_name, value, confidence_level, evidence_type, source_snippet, inference_chain, is_ai_generated, created_at)`
- `validation_flags(id, product_id, field_name, issue_type, message, created_at)` — written by stage 5; `issue_type` is `contradiction` or `out_of_range`

`backend/models/db.py` wraps the Supabase client in a session-shaped facade (`add` / `flush` / `commit` / `get`), so the pipeline and API code reads the same as it did against SQLAlchemy. Clients are scoped per thread (`get_thread_client`), because the client owns an HTTP connection pool and driving one pool from several threads at once produces sporadic `Server disconnected` errors — which is exactly what stage 7 does, since each batch item's blocking pipeline runs in a worker thread.

## Next steps

Every PRD must-have is implemented as of stage 7. What's left is the nice-to-have list:

1. Add export (JSON/CSV) — stage 8.
2. Add the React review dashboard — stage 9. `review_findings` is already ranked server-side for it; see the note under stage 7's neighbours above.
3. If batches ever need to exceed the 50-item synchronous cap, add the job table and `GET /api/batches/{id}` polling path described in [stage 7](#7-batch-mode). `run_batch_async` is already the interface a worker would call, so the runner itself wouldn't change.
