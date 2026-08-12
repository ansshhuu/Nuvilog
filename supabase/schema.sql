-- Nuvilog Postgres schema (Supabase).
--
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query)
-- for a new project. Adapted 1:1 from the previous SQLite/SQLAlchemy schema:
-- same columns, same relationships, with two deliberate changes —
--   * id columns are uuid (gen_random_uuid()) instead of autoincrement integers
--   * created_at columns are timestamptz instead of naive timestamp
--
-- gen_random_uuid() is built into Postgres 13+, which every Supabase project
-- runs, so no pgcrypto extension is needed.

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
create table if not exists public.products (
    id             uuid primary key default gen_random_uuid(),
    raw_input_type varchar(20)   not null,   -- pdf | csv | text | url
    raw_input_ref  varchar(1024) not null,   -- file path, url, or "inline"
    category       varchar(100)  not null,
    status         varchar(30)   not null default 'ingested',

    -- Written by the enrichment pass (stage 6): a commerce-ready description
    -- generated from the verified fields only. Nullable — a product ingested
    -- before stage 6 existed, or one whose enrichment call failed, still has
    -- a complete scored field set and is not invalid without this.
    description    text,

    created_at     timestamptz   not null default now()
);

-- Migration for projects created before stage 6. Safe to re-run: this whole
-- file is idempotent, and `add column if not exists` is a no-op on a project
-- built from the create table above.
alter table public.products add column if not exists description text;

create index if not exists idx_products_category on public.products (category);

-- ---------------------------------------------------------------------------
-- product_fields
-- ---------------------------------------------------------------------------
create table if not exists public.product_fields (
    id               uuid primary key default gen_random_uuid(),
    product_id       uuid         not null references public.products (id) on delete cascade,
    field_name       varchar(100) not null,
    value            text,

    -- Populated by the confidence engine (stage 4).
    confidence_level varchar(20),             -- high | medium | unverified
    evidence_type    varchar(30),             -- exact_match | contextual_inference | none
    source_snippet   text,
    inference_chain  text,                    -- phrase that implied a "medium" confidence value
    is_ai_generated  boolean      not null default false,

    created_at       timestamptz  not null default now()
);

create index if not exists idx_product_fields_product_id on public.product_fields (product_id);

-- ---------------------------------------------------------------------------
-- validation_flags
-- ---------------------------------------------------------------------------
create table if not exists public.validation_flags (
    id          uuid primary key default gen_random_uuid(),
    product_id  uuid         not null references public.products (id) on delete cascade,
    field_name  varchar(100),
    issue_type  varchar(50)  not null,        -- contradiction | out_of_range | missing_required
    message     text         not null,
    created_at  timestamptz  not null default now()
);

create index if not exists idx_validation_flags_product_id on public.validation_flags (product_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- Nuvilog is a single-tenant prototype with no auth: the backend talks to
-- Supabase with a server-side key and is the only writer. RLS is enabled so the
-- tables are not world-readable through the anon key, and no permissive policy
-- is added — the service_role key used by the backend bypasses RLS.
--
-- If you point SUPABASE_KEY at the anon key instead, every request will be
-- rejected until you add policies here. That is intentional: fail closed.
alter table public.products         enable row level security;
alter table public.product_fields   enable row level security;
alter table public.validation_flags enable row level security;
