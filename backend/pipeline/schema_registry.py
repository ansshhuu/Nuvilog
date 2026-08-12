"""
Stage 3 (partial): category-aware schema layer.

Category field sets live in /schemas/*.yaml, not in code. Adding a new
category is dropping a new YAML file into that directory — nothing in
this module or the pipeline needs to change. Full contradiction-range
enforcement (stage 5) also reads `valid_range` from these same schemas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


class ValidRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class FieldDef(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "dimension", "boolean"]
    required: bool = False
    description: str = ""
    unit: Optional[str] = None
    valid_range: Optional[ValidRange] = None


class CategorySchema(BaseModel):
    category: str
    display_name: str
    description: str = ""
    fields: list[FieldDef] = Field(default_factory=list)

    def required_fields(self) -> list[FieldDef]:
        return [f for f in self.fields if f.required]

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


class SchemaRegistry:
    """Loads and caches every category schema found in SCHEMAS_DIR."""

    def __init__(self, schemas_dir: Path = SCHEMAS_DIR):
        self._schemas_dir = schemas_dir
        self._registry: dict[str, CategorySchema] = {}
        self.reload()

    def reload(self) -> None:
        self._registry.clear()
        for path in sorted(self._schemas_dir.glob("*.yaml")):
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            schema = CategorySchema.model_validate(raw)
            self._registry[schema.category] = schema

    def get(self, category: str) -> CategorySchema:
        try:
            return self._registry[category]
        except KeyError:
            available = ", ".join(sorted(self._registry)) or "none"
            raise ValueError(f"Unknown category '{category}'. Available: {available}")

    def list_categories(self) -> list[str]:
        return sorted(self._registry)

    def all_schemas(self) -> dict[str, CategorySchema]:
        return dict(self._registry)


# Module-level singleton — cheap to build, read constantly.
registry = SchemaRegistry()
