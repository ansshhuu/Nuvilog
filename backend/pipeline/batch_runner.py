"""
Stage 7: batch mode. NOT YET IMPLEMENTED.

Contract:

    def run_batch(items: list[BatchItem]) -> list[BatchResult]

Runs the full single-product pipeline (stages 1-6) over N products with
no special-casing — a batch of 1 and a batch of 100 go through the same
code path. Contradiction detection (stage 5) must run for every item in
the batch, not be skipped for throughput.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from pipeline.types import InputType


class BatchItem(BaseModel):
    source_type: InputType
    source_ref: str
    category: str


class BatchResult(BaseModel):
    source_ref: str
    product_id: int | None
    status: Literal["ok", "error"]
    error: str | None = None


def run_batch(items: list[BatchItem]) -> list[BatchResult]:
    raise NotImplementedError("Stage 7 (batch runner) is not implemented yet.")
