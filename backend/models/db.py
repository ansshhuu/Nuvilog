"""
Supabase (Postgres) persistence layer for Nuvilog.

Replaces the previous SQLAlchemy/SQLite layer. The public surface used by
main.py and the pipeline stages is deliberately unchanged:

    Product, ProductField, ValidationFlag   -- constructed with keyword args
    get_db()                                -- FastAPI dependency yielding a session
    init_db()                               -- startup hook
    session.add / flush / commit / rollback / close / get
    product.fields, product.flags           -- lazily loaded child rows

so callers keep working without edits. Internally there is no ORM and no
local database file: rows go over PostgREST to a Supabase project, addressed
by SUPABASE_URL + SUPABASE_KEY.

Two honest differences from the SQLAlchemy version, because PostgREST is a
REST API and not a database connection:

  * ids are server-generated uuid strings (gen_random_uuid()), not ints.
  * there is no transaction. flush() writes immediately and commit() is a
    flush of anything still pending — a failure partway through a multi-row
    write leaves the earlier rows written. For this pipeline that means a
    product row can outlive a failed field write; it is visible in the table
    editor with no fields rather than silently vanishing.

Table definitions live in supabase/schema.sql — run it once per project.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from dotenv import load_dotenv

from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client: Optional[Client] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_client() -> Client:
    """Lazily build (and cache) the Supabase client.

    Lazy on purpose: importing this module must not require credentials, so
    unit tests can import the models without a live project.
    """
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY are not set. Copy .env.example to "
                ".env and fill in your Supabase project URL and service key."
            )
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def reset_client() -> None:
    """Drop the cached client so a later get_client() re-reads the env vars.

    Used by tests that point the layer at a different project.
    """
    global _client, SUPABASE_URL, SUPABASE_KEY
    _client = None
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _parse_timestamptz(value: Any) -> Any:
    """Turn a PostgREST timestamptz string back into an aware datetime.

    Callers do things like `product.created_at.isoformat()`, so this has to
    hand back a datetime and not the raw string.
    """
    if not isinstance(value, str):
        return value
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return value


class _Record:
    """Minimal stand-in for a declarative ORM model.

    Holds column values as plain attributes, knows its table name, and can
    serialize itself for an insert. No change tracking: rows are written once
    by the ingest path and read back by id.
    """

    __tablename__: str = ""
    __columns__: tuple[str, ...] = ()
    __timestamp_columns__: tuple[str, ...] = ()
    __defaults__: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        unknown = set(kwargs) - set(self.__columns__)
        if unknown:
            raise TypeError(
                f"{type(self).__name__} got unexpected column(s): {', '.join(sorted(unknown))}"
            )
        for column in self.__columns__:
            default = self.__defaults__.get(column)
            setattr(self, column, kwargs.get(column, default))
        self._session: Optional["SupabaseSession"] = None
        self._persisted = False

    def _insert_payload(self) -> dict:
        """Columns to send on insert.

        None values are dropped so Postgres column defaults (uuid id,
        created_at, status) apply instead of being overwritten with null.
        """
        payload = {}
        for column in self.__columns__:
            value = getattr(self, column, None)
            if value is None:
                continue
            payload[column] = _to_jsonable(value)
        return payload

    @classmethod
    def _from_row(cls, row: dict, session: Optional["SupabaseSession"] = None) -> "_Record":
        obj = cls.__new__(cls)
        for column in cls.__columns__:
            value = row.get(column)
            if column in cls.__timestamp_columns__:
                value = _parse_timestamptz(value)
            setattr(obj, column, value)
        obj._session = session
        obj._persisted = True
        return obj

    def _apply_returned_row(self, row: dict) -> None:
        """Copy server-assigned values (id, created_at, defaults) back onto
        the in-memory object after an insert."""
        for column in self.__columns__:
            if column not in row:
                continue
            value = row[column]
            if column in self.__timestamp_columns__:
                value = _parse_timestamptz(value)
            setattr(self, column, value)
        self._persisted = True

    def _children(self, child_cls: type["_Record"], cache_attr: str) -> list["_Record"]:
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached
        if self._session is None or getattr(self, "id", None) is None:
            return []
        rows = self._session.list_by(child_cls, product_id=self.id)
        setattr(self, cache_attr, rows)
        return rows

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} id={getattr(self, 'id', None)!r}>"


class Product(_Record):
    __tablename__ = "products"
    __columns__ = (
        "id",
        "raw_input_type",  # pdf | csv | text | url
        "raw_input_ref",  # file path, url, or "inline"
        "category",
        "status",
        "created_at",
    )
    __timestamp_columns__ = ("created_at",)
    __defaults__ = {"status": "ingested"}

    @property
    def fields(self) -> list["ProductField"]:
        return self._children(ProductField, "_fields_cache")  # type: ignore[return-value]

    @property
    def flags(self) -> list["ValidationFlag"]:
        return self._children(ValidationFlag, "_flags_cache")  # type: ignore[return-value]


class ProductField(_Record):
    __tablename__ = "product_fields"
    __columns__ = (
        "id",
        "product_id",
        "field_name",
        "value",
        "confidence_level",  # high | medium | unverified
        "evidence_type",  # exact_match | contextual_inference | none
        "source_snippet",
        "inference_chain",
        "is_ai_generated",
        "created_at",
    )
    __timestamp_columns__ = ("created_at",)
    __defaults__ = {"is_ai_generated": False}


class ValidationFlag(_Record):
    __tablename__ = "validation_flags"
    __columns__ = (
        "id",
        "product_id",
        "field_name",
        "issue_type",  # contradiction | out_of_range | missing_required
        "message",
        "created_at",
    )
    __timestamp_columns__ = ("created_at",)


class SupabaseSession:
    """Session-shaped facade over the Supabase REST client.

    Implements the slice of the SQLAlchemy Session API this codebase actually
    uses — add / flush / commit / rollback / close / get — so the ingest path
    in main.py reads the same as it did against SQLite.
    """

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client
        self._pending: list[_Record] = []

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = get_client()
        return self._client

    def add(self, obj: _Record) -> None:
        obj._session = self
        self._pending.append(obj)

    def add_all(self, objs: Iterable[_Record]) -> None:
        for obj in objs:
            self.add(obj)

    def flush(self) -> None:
        """Write every pending row, newest last, and copy back server-assigned
        ids so callers can use obj.id straight after.

        Consecutive rows for the same table are batched into one insert, which
        keeps the common ingest shape (1 product, then N fields) at two HTTP
        round trips. Insertion order is preserved so a child row is never
        written before the parent it references.
        """
        while self._pending:
            batch = [self._pending.pop(0)]
            table = batch[0].__tablename__
            while self._pending and self._pending[0].__tablename__ == table:
                batch.append(self._pending.pop(0))

            payload = [obj._insert_payload() for obj in batch]
            response = self.client.table(table).insert(payload).execute()
            returned = response.data or []
            for obj, row in zip(batch, returned):
                obj._apply_returned_row(row)

    def commit(self) -> None:
        """Flush anything outstanding.

        PostgREST exposes no transaction, so there is nothing to commit beyond
        the writes flush() already performs — see the module docstring.
        """
        self.flush()

    def rollback(self) -> None:
        """Discard rows not yet written. Rows already flushed stay written."""
        self._pending.clear()

    def close(self) -> None:
        self._pending.clear()

    def get(self, model: type[_Record], pk: Any) -> Optional[_Record]:
        response = (
            self.client.table(model.__tablename__).select("*").eq("id", str(pk)).limit(1).execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return model._from_row(rows[0], session=self)

    def list_by(self, model: type[_Record], **filters: Any) -> list[_Record]:
        query = self.client.table(model.__tablename__).select("*")
        for column, value in filters.items():
            query = query.eq(column, value)
        response = query.execute()
        return [model._from_row(row, session=self) for row in (response.data or [])]

    def delete(self, model: type[_Record], pk: Any) -> None:
        self.client.table(model.__tablename__).delete().eq("id", str(pk)).execute()


# Kept as an alias so `SessionLocal()` still produces a session, as before.
SessionLocal = SupabaseSession


def init_db() -> None:
    """Startup check.

    Tables are created by running supabase/schema.sql in the Supabase SQL
    editor — PostgREST cannot issue DDL, so unlike the old create_all() this
    cannot bring the schema up on its own. Instead it fails loudly and early
    with the fix, rather than letting the first ingest fail deep in a request.
    """
    client = get_client()
    for table in ("products", "product_fields", "validation_flags"):
        try:
            client.table(table).select("id").limit(1).execute()
        except Exception as e:
            raise RuntimeError(
                f"Supabase table '{table}' is not reachable ({e}). Run "
                "supabase/schema.sql in your project's SQL editor, and check "
                "SUPABASE_URL / SUPABASE_KEY in .env."
            ) from e


def get_db():
    db = SupabaseSession()
    try:
        yield db
    finally:
        db.close()
