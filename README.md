# Nuvilog

Turns Unilog's raw dishwasher catalog rows into structured, enriched product records — and is honest about what it can and can't verify.

## What it does

Input is Unilog's 1000-row raw product catalog (6 columns: brand fields, model, description). Output is a structured, enriched dishwasher product record per row, built up through UOM normalization, manufacturer/brand resolution, a 15-label attribute scaffold, and a generated commerce description. Every row is scored against a real evaluation harness, not just checked by eye. The two rows with a known manufacturer page and verified attributes are used as ground truth; everything else is scored on structural and honesty checks only, since there's nothing to compare it against.

## Why it's different

- Confidence is scored from real evidence (source-text matches, verified fetches) — never an LLM rating its own output
- Every gap is explicitly flagged `NOT_BUILT` with a real row count, never silently guessed or padded
- Self-tested against real ground truth at every pipeline step, not just internal consistency checks

## Scope

The pipeline is proven on 10 real dishwasher rows, 2 of which (`PDSH4816AF`, `WDTS7024RZ`) have verified ground truth to score against. The other 8 dishwasher rows and the remaining 990 rows (other appliance categories) are explicitly flagged `NOT_BUILT` with their real row counts rather than run through unverified — there's no ground truth to check the output against for the rest, so nothing is claimed for it.

## Pipeline

1. **Data prep** (`step1_data_prep.py`) — load and clean the raw 1000-row CSV
2. **Schema** (`delivery_format.py`) — the 252-column delivery format target
3. **UOM/fraction normalize** (`uom_normalizer.py`, `fraction_converter.py`) — units and fractional dimensions to a consistent format
4. **Manufacturer/brand honesty layer** (`step4_manufacturer.py`) — vendor clustering and code parsing, no fabrication
5. **Dishwasher scaffold** (`step5_dishwasher_schema.py`) — 15-label attribute structure, blank unless evidenced
6. **Description builder** (`step6_description_builder.py`) — generates commerce descriptions from verified fields only
7. **Manufacturer enrichment** (`step8_manufacturer_enrichment.py`) — real fetch of manufacturer pages, measured attribute lift
8. **Evaluation harness** (`step2_evaluate.py`) — self-tests, then scores real output against ground truth

## Getting started

**Prerequisites:** Python 3.11+, Node, a free [Gemini API key](https://aistudio.google.com/app/apikey), a free [Supabase](https://supabase.com) project.

```bash
git clone <repo-url>
cd Nuvilog/backend
python -m venv venv

# Windows PowerShell
./venv/Scripts/pip install -r requirements.txt
cp ../.env.example ../.env

# macOS/Linux bash
venv/bin/pip install -r requirements.txt
cp ../.env.example ../.env
```

Edit `.env` and set `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (Supabase → Project Settings → API; use the `service_role` key).

**Run backend:**

```bash
./venv/Scripts/uvicorn main:app --reload   # Windows
venv/bin/uvicorn main:app --reload         # macOS/Linux
```

**Run frontend:**

```bash
cd frontend
npm install
npm run dev
```

**Run the eval report:**

```bash
python backend/scripts/step6_7_full_run.py
```

Full eval numbers live in `backend/reports/`, not copy-pasted into this file — that way this README doesn't go stale.
