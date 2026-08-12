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
**How it works:** One Gemini (`gemini-2.5-flash-lite`) call per product, using the category's field list as the prompt and Gemini's native JSON mode to keep output machine-parseable. For every field, the model returns both a value and the verbatim snippet of source text it claims supports it.
**Result:** A value *and* a citation for every field — the raw material the confidence engine needs to check its work.

### 3. Category-aware schema layer
**How it works:** Each product category (fasteners, electrical, plumbing) is a YAML file under `backend/schemas/` listing its required and optional fields, types, units, and valid ranges. The registry loads every file in that directory at startup — nothing in the pipeline code branches on category name.
**Result:** Adding a 4th category is dropping in a new YAML file, not writing new code.

### 4. Confidence engine
**How it works:** Pure evidence checking against the source text — no second LLM call, no self-rating. A value stated directly in a "Field: value" pattern in the source scores **HIGH**. A value only supported by surrounding context (mentioned, but not directly stated) scores **MEDIUM**, with the supporting phrase recorded as an `inference_chain`. A value with no support anywhere in the source scores **UNVERIFIED** and is flagged as AI-suggested rather than fact.
**Result:** Every stored field carries a confidence level a human can trust, because it was computed from the text — not asked from the model that generated it.

### 5. Contradiction detection — *not yet implemented*
**How it works (planned):** Cross-checks extracted fields against each other and against each field's `valid_range` from the schema, catching things like two different voltages found in different sections of the same document.
**Result (planned):** Conflicts surfaced as `validation_flags` rows before a product ever reaches review.

### 6. Enrichment — *not yet implemented*
**How it works (planned):** A second, separate LLM call that writes a clean commerce description and fills non-critical gaps — always marked `is_ai_generated=True`, never mixed in with verified data.

### 7. Batch mode — *not yet implemented*
**How it works (planned):** The same single-product pipeline (stages 1–6) looped over N products with no special-casing, so contradiction detection runs on every item in a batch, not just single-product runs.

### 8. Export & 9. Review dashboard — *not yet implemented*
**How it works (planned):** Structured JSON/CSV export, and a thin React dashboard showing per-field confidence, source snippet on hover, and contradiction flags.

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
                               │
                 ┌─────────────┴─────────────┐
                 ▼ IMPLEMENTED                ▼ NOT YET IMPLEMENTED
        products / product_fields    5. Contradiction Detector
           (Supabase / Postgres)     6. Enrichment (2nd LLM call)
                                     7. Batch Runner
                                     8. Export (JSON/CSV)
                                     9. Review Dashboard (React)
```

## ⚠️ Important Caveats

- **Sample data is synthetic.** `backend/data/samples/sample_fastener_spec.pdf` is a spec sheet generated by `backend/data/samples/make_sample_pdf.py` for testing — not a real manufacturer document. Treat all example output in this repo as illustrative, not a demo of real-world accuracy.
- **Honest implementation status:** stages 1 (input handler), 2 (extraction), 3 (schema registry), and 4 (confidence engine) are implemented and wired into `POST /api/ingest`. Stages 5 (contradiction detection), 6 (enrichment), 7 (batch mode), 8 (export), and 9 (review dashboard) are stubs only — each has a typed contract and docstring in its module under `backend/pipeline/`, but calling them raises `NotImplementedError`. There is no frontend yet.
- **No auth, single-tenant.** This is a hackathon prototype: no login, no API keys beyond the LLM provider and Supabase, no multi-user isolation. Every product in the database is visible to anyone who can reach the API. Do not point this at real customer or supplier data as-is.
- **No transactions.** The backend talks to Supabase over PostgREST, which has no transaction support. A failure partway through an ingest can leave a `products` row with none of its `product_fields`. Nothing silently disappears, but partial rows are possible.

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

- `products(id, raw_input_type, raw_input_ref, category, status, created_at)`
- `product_fields(id, product_id, field_name, value, confidence_level, evidence_type, source_snippet, inference_chain, is_ai_generated, created_at)`
- `validation_flags(id, product_id, field_name, issue_type, message, created_at)` — table exists, not yet written to (stage 5 is unimplemented)

`backend/models/db.py` wraps the Supabase client in a session-shaped facade (`add` / `flush` / `commit` / `get`), so the pipeline and API code reads the same as it did against SQLAlchemy.

## Next steps

1. Implement `contradiction_detector.detect_contradictions`, write findings to `validation_flags`.
2. Implement `enrichment.enrich` as a second, clearly-marked LLM call.
3. Implement `batch_runner.run_batch` over the same stage 1–4 path.
4. Add export (JSON/CSV) and the React review dashboard.
