"""Unit tests for stage 3 (category-aware schema registry).

The headline claim of this stage is "adding a category is dropping in a YAML
file, not writing code" — so the load-a-new-file-from-disk path is tested
directly against a temp directory, not just the three shipped schemas.
"""
from __future__ import annotations

import pytest
import yaml

from pipeline.schema_registry import CategorySchema, SchemaRegistry, registry


def test_ships_with_the_three_documented_categories():
    assert registry.list_categories() == ["electrical", "fasteners", "plumbing"]


def test_get_returns_a_parsed_schema():
    schema = registry.get("fasteners")

    assert isinstance(schema, CategorySchema)
    assert schema.display_name == "Fasteners"
    assert "product_name" in schema.field_names()
    assert "material" in schema.field_names()


def test_required_fields_is_a_subset_of_all_fields():
    schema = registry.get("fasteners")
    required = {f.name for f in schema.required_fields()}

    assert required, "fasteners should declare at least one required field"
    assert required.issubset(set(schema.field_names()))
    assert all(f.required for f in schema.required_fields())


def test_valid_range_is_parsed_for_dimension_fields():
    """Stage 5 (contradiction detection) reads valid_range off these same
    schemas, so it has to survive YAML loading as numbers."""
    diameter = next(f for f in registry.get("fasteners").fields if f.name == "diameter")

    assert diameter.type == "dimension"
    assert diameter.unit == "mm"
    assert diameter.valid_range is not None
    assert diameter.valid_range.min == 0.5
    assert diameter.valid_range.max == 100


def test_unknown_category_raises_with_the_available_ones_listed():
    with pytest.raises(ValueError) as excinfo:
        registry.get("sprockets")

    message = str(excinfo.value)
    assert "sprockets" in message
    assert "fasteners" in message  # error tells the caller what it can use


def test_a_new_category_is_just_a_new_yaml_file(tmp_path):
    schema_file = tmp_path / "bearings.yaml"
    schema_file.write_text(
        yaml.safe_dump(
            {
                "category": "bearings",
                "display_name": "Bearings",
                "description": "Ball and roller bearings.",
                "fields": [
                    {"name": "bore_diameter", "type": "dimension", "unit": "mm", "required": True},
                    {"name": "seal_type", "type": "string"},
                ],
            }
        ),
        encoding="utf-8",
    )

    local_registry = SchemaRegistry(schemas_dir=tmp_path)

    assert local_registry.list_categories() == ["bearings"]
    assert local_registry.get("bearings").field_names() == ["bore_diameter", "seal_type"]
    # Defaults applied without being spelled out in the YAML.
    assert local_registry.get("bearings").fields[1].required is False


def test_reload_picks_up_a_file_added_after_startup(tmp_path):
    (tmp_path / "one.yaml").write_text(
        yaml.safe_dump({"category": "one", "display_name": "One", "fields": []}), encoding="utf-8"
    )
    local_registry = SchemaRegistry(schemas_dir=tmp_path)
    assert local_registry.list_categories() == ["one"]

    (tmp_path / "two.yaml").write_text(
        yaml.safe_dump({"category": "two", "display_name": "Two", "fields": []}), encoding="utf-8"
    )
    local_registry.reload()

    assert local_registry.list_categories() == ["one", "two"]


def test_malformed_schema_fails_loudly_at_load_time(tmp_path):
    """A typo'd type must break at startup, not silently produce a category
    whose fields the extractor can't prompt for."""
    (tmp_path / "broken.yaml").write_text(
        yaml.safe_dump(
            {
                "category": "broken",
                "display_name": "Broken",
                "fields": [{"name": "x", "type": "not_a_real_type"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        SchemaRegistry(schemas_dir=tmp_path)


def test_all_schemas_returns_a_copy_not_the_live_registry():
    schemas = registry.all_schemas()
    schemas.pop("fasteners")

    assert "fasteners" in registry.list_categories()
