"""Shared test fixtures.

`backend/` is put on sys.path here rather than in each test file: the app is
run with `backend` as the working directory (`uvicorn main:app`), so its
modules import each other as top-level packages (`pipeline.*`, `models.*`)
and the tests have to resolve them the same way.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(REPO_ROOT / ".env")


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def sample_pdf_path(fixtures_dir: Path) -> Path:
    path = fixtures_dir / "sample_fastener_spec.pdf"
    assert path.exists(), f"missing test fixture: {path}"
    return path


@pytest.fixture(scope="session")
def conflict_spec_text(fixtures_dir: Path) -> str:
    """A spec sheet that contradicts itself, as raw text.

    Plain text rather than a second PDF: the input handler normalizes both to
    the same RawDocument, so a .txt exercises stage 5 identically while
    staying diffable in review and needing no reportlab step to regenerate.
    """
    path = fixtures_dir / "sample_fastener_spec_with_conflict.txt"
    assert path.exists(), f"missing test fixture: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def sample_llm_response(fixtures_dir: Path) -> dict:
    """The canned Gemini response used everywhere instead of a real call."""
    with open(fixtures_dir / "sample_response.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def conflict_llm_response(fixtures_dir: Path) -> dict:
    """Canned response for the self-contradicting fixture."""
    with open(fixtures_dir / "sample_response_with_conflict.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def unquoted_numbers_llm_response(fixtures_dir: Path) -> dict:
    """Same document, but the model answered numeric fields with bare numbers.

    A separate fixture rather than an edit to the one above: the existing
    fixtures are asserted on all over the suite, and their quoted values are
    load-bearing there. This one exists to cover the case they all miss.
    """
    with open(fixtures_dir / "sample_response_unquoted_numbers.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _fake_llm_client(response: dict):
    """A drop-in LLMClient that returns `response` and records its prompts.

    Nothing in the test suite is allowed to hit the real Gemini API — CI runs
    on every push and would burn quota (and be flaky) if it did.
    """

    class FakeLLMClient:
        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[str, str]] = []
            self.model = "fake-model"

        def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
            self.calls.append((system_prompt, user_prompt))
            return response

    return FakeLLMClient()


@pytest.fixture
def fake_llm(sample_llm_response: dict):
    return _fake_llm_client(sample_llm_response)


@pytest.fixture
def fake_llm_conflict(conflict_llm_response: dict):
    return _fake_llm_client(conflict_llm_response)


@pytest.fixture
def fake_llm_unquoted_numbers(unquoted_numbers_llm_response: dict):
    return _fake_llm_client(unquoted_numbers_llm_response)


# ---------------------------------------------------------------------------
# Supabase (integration tests only)
# ---------------------------------------------------------------------------
def _supabase_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


@pytest.fixture(scope="session")
def supabase_available() -> bool:
    """Gate for tests that need a live Supabase project.

    Locally, missing credentials skip the integration tests so a fresh clone
    can still run `pytest tests/unit`. In CI they must be present — the
    workflow injects them from repo secrets, and a silent skip there would
    turn the integration suite into a no-op that always "passes".
    """
    if _supabase_configured():
        return True
    if os.getenv("CI"):
        pytest.fail(
            "SUPABASE_URL / SUPABASE_KEY are not set in CI. Add them as repo "
            "secrets (Settings -> Secrets and variables -> Actions); the "
            "integration suite must not be skipped in CI."
        )
    pytest.skip("SUPABASE_URL / SUPABASE_KEY not set — skipping Supabase integration test.")


@pytest.fixture
def db_session(supabase_available: bool):
    """A live session against the configured Supabase project.

    Yields a session plus a cleanup list: append any product id created by the
    test and it is deleted afterwards, so repeated runs don't accumulate rows
    in the test project.
    """
    from models.db import Product, SupabaseSession

    session = SupabaseSession()
    created_product_ids: list[str] = []
    try:
        yield session, created_product_ids
    finally:
        for product_id in created_product_ids:
            try:
                # product_fields / validation_flags cascade on delete.
                session.delete(Product, product_id)
            except Exception as e:  # pragma: no cover - cleanup best effort
                print(f"warning: could not clean up product {product_id}: {e}")
        session.close()
