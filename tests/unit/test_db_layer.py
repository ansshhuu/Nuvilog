"""Unit tests for the Supabase persistence facade (models/db.py).

The facade is what lets main.py keep its SQLAlchemy-shaped call sites after
the swap, so its behaviour is pinned here against a fake client — no network,
no Supabase project. Live behaviour is covered by the integration suite.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models.db import Product, ProductField, SupabaseSession, ValidationFlag


# ---------------------------------------------------------------------------
# Fake PostgREST client
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table: "FakeTable"):
        self._table = table
        self._filters: dict = {}
        self._limit = None

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = [
            row
            for row in self._table.rows
            if all(str(row.get(k)) == str(v) for k, v in self._filters.items())
        ]
        return FakeResponse(rows[: self._limit] if self._limit else rows)


class FakeDelete(FakeQuery):
    def execute(self):
        kept, removed = [], []
        for row in self._table.rows:
            target = removed if all(str(row.get(k)) == str(v) for k, v in self._filters.items()) else kept
            target.append(row)
        self._table.rows = kept
        return FakeResponse(removed)


class FakeTable:
    def __init__(self, name: str, client: "FakeClient"):
        self.name = name
        self.rows: list[dict] = []
        self._client = client

    def insert(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        stored = []
        for row in rows:
            complete = {
                "id": f"{self.name}-uuid-{len(self.rows) + len(stored) + 1}",
                "created_at": "2026-08-11T12:00:00.123456+00:00",
                **row,
            }
            stored.append(complete)
        self._client.inserts.append((self.name, len(stored)))

        table = self

        class _Insert:
            def execute(self_inner):
                table.rows.extend(stored)
                return FakeResponse(stored)

        return _Insert()

    def select(self, *_columns):
        return FakeQuery(self)

    def delete(self):
        return FakeDelete(self)


class FakeClient:
    def __init__(self):
        self.tables: dict[str, FakeTable] = {}
        self.inserts: list[tuple[str, int]] = []

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name, self))


@pytest.fixture
def session():
    return SupabaseSession(client=FakeClient())


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
def test_column_defaults_match_the_sql_schema():
    assert Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners").status == (
        "ingested"
    )
    assert ProductField(field_name="material").is_ai_generated is False


def test_unknown_column_is_rejected_at_construction():
    with pytest.raises(TypeError, match="unexpected column"):
        Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="f", bogus=1)


def test_none_values_are_dropped_so_postgres_defaults_apply():
    """id and created_at must be left to gen_random_uuid()/now(), not sent as
    explicit nulls, which would violate the not-null constraints."""
    payload = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")._insert_payload()

    assert "id" not in payload
    assert "created_at" not in payload
    assert payload["category"] == "fasteners"


def test_datetimes_are_serialized_as_iso_strings():
    when = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    payload = Product(
        raw_input_type="pdf", raw_input_ref="a.pdf", category="f", created_at=when
    )._insert_payload()

    assert payload["created_at"] == "2026-08-11T12:00:00+00:00"


def test_timestamptz_strings_are_parsed_back_into_datetimes():
    """main.py calls product.created_at.isoformat(), so a raw string would
    break the products endpoint."""
    product = Product._from_row({"id": "x", "created_at": "2026-08-11T12:00:00.123456Z"})

    assert isinstance(product.created_at, datetime)
    assert product.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
def test_flush_assigns_server_generated_ids(session):
    product = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")
    session.add(product)
    assert product.id is None

    session.flush()

    assert product.id == "products-uuid-1"
    assert isinstance(product.created_at, datetime)


def test_consecutive_rows_for_one_table_are_batched_into_a_single_insert(session):
    product = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")
    session.add(product)
    session.flush()

    for name in ("material", "length", "grade"):
        session.add(ProductField(product_id=product.id, field_name=name))
    session.commit()

    # One insert for the product, one for all three fields — not four.
    assert session.client.inserts == [("products", 1), ("product_fields", 3)]


def test_insertion_order_is_preserved_so_children_never_precede_parents(session):
    session.add(Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners"))
    session.add(ProductField(field_name="material"))
    session.add(ValidationFlag(issue_type="contradiction", message="boom"))
    session.commit()

    assert [name for name, _ in session.client.inserts] == [
        "products",
        "product_fields",
        "validation_flags",
    ]


def test_commit_flushes_pending_rows(session):
    session.add(Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners"))
    session.commit()

    assert session.client.table("products").rows


def test_rollback_discards_unflushed_rows_only(session):
    written = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")
    session.add(written)
    session.flush()

    session.add(Product(raw_input_type="csv", raw_input_ref="b.csv", category="fasteners"))
    session.rollback()
    session.commit()

    # PostgREST has no transaction: the flushed row stays, the pending one never lands.
    assert len(session.client.table("products").rows) == 1


def test_get_returns_none_for_a_missing_id(session):
    assert session.get(Product, "no-such-uuid") is None


def test_get_round_trips_a_row(session):
    product = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners", status="scored")
    session.add(product)
    session.commit()

    fetched = session.get(Product, product.id)

    assert fetched is not None
    assert fetched.category == "fasteners"
    assert fetched.status == "scored"
    assert fetched.raw_input_ref == "a.pdf"


def test_child_rows_load_lazily_off_the_parent(session):
    product = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")
    session.add(product)
    session.flush()
    session.add(ProductField(product_id=product.id, field_name="material", value="Steel"))
    session.add(ValidationFlag(product_id=product.id, issue_type="out_of_range", message="too big"))
    session.commit()

    fetched = session.get(Product, product.id)

    assert [f.field_name for f in fetched.fields] == ["material"]
    assert [f.issue_type for f in fetched.flags] == ["out_of_range"]


def test_children_of_an_unsaved_product_are_empty_not_an_error():
    detached = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")

    assert detached.fields == []
    assert detached.flags == []


def test_delete_removes_the_row(session):
    product = Product(raw_input_type="pdf", raw_input_ref="a.pdf", category="fasteners")
    session.add(product)
    session.commit()

    session.delete(Product, product.id)

    assert session.get(Product, product.id) is None
