"""Schema version retention and self-consistency.

The promise is that the validator retains every old version forever, so a
dataset written against 0.1.0 still validates against 0.1.0 in five years and a
minor bump never obliges a lab to rewrite existing data. These tests make that
promise checkable rather than aspirational.
"""

from __future__ import annotations

import json

import pytest

from tcat_standard import available_versions, load_schema, schema_dir
from tcat_standard.schema import CURRENT_SCHEMA_VERSION, KINDS, load_all_schemas


def test_at_least_one_version_is_present():
    assert available_versions()


def test_the_current_version_is_on_disk():
    assert CURRENT_SCHEMA_VERSION in available_versions()


def test_every_version_ever_shipped_still_loads():
    """The retention promise. When 0.2.0 lands, this test starts covering both
    versions with no edit -- which is the point."""
    for version in available_versions():
        for kind in KINDS:
            assert load_schema(kind, version), f"{kind} missing from {version}"


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_exists_in_the_current_version(kind):
    assert load_schema(kind)["$id"].endswith(f"{kind}.schema.json")


@pytest.mark.parametrize("kind", KINDS)
def test_every_schema_declares_a_dialect_and_an_id(kind):
    """Both are needed for offline reference resolution: $id is the name a $ref
    resolves against, $schema is how the dialect is inferred without a network
    lookup."""
    doc = load_schema(kind)
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert doc["$id"].startswith("https://transientcatalysis.github.io/tcat-data-standard/")


def test_ids_carry_the_version_they_live_under():
    """So a stale $id cannot silently make two versions look like one."""
    for version in available_versions():
        for doc in load_all_schemas(version).values():
            assert f"/{version}/" in doc["$id"], doc["$id"]


def test_ids_are_unique_within_a_version():
    for version in available_versions():
        directory = schema_dir(version)
        ids = [
            json.loads(p.read_text(encoding="utf-8"))["$id"]
            for p in sorted(directory.rglob("*.schema.json"))
        ]
        assert len(ids) == len(set(ids))


def test_every_cross_file_ref_resolves():
    """Catches the most common schema-authoring mistake -- a typo'd $ref -- which
    otherwise surfaces as a confusing runtime error during a lab's CI run rather
    than during ours."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    for version in available_versions():
        docs = load_all_schemas(version)
        registry = Registry().with_resources(
            (doc_id, Resource.from_contents(doc)) for doc_id, doc in docs.items()
        )
        for kind in KINDS:
            validator = Draft202012Validator(load_schema(kind, version), registry=registry)
            # Validating an empty object walks every $ref reachable from the root.
            list(validator.iter_errors({}))


def test_every_schema_is_itself_a_valid_json_schema():
    from jsonschema import Draft202012Validator

    for version in available_versions():
        for doc in load_all_schemas(version).values():
            Draft202012Validator.check_schema(doc)


def test_unknown_kinds_and_versions_fail_clearly():
    with pytest.raises(ValueError, match="unknown document kind"):
        load_schema("spectrum")
    with pytest.raises(FileNotFoundError, match="available"):
        schema_dir("9.9.9")


def test_versions_sort_numerically_not_lexically():
    """So 0.10.0 lands after 0.9.0. Only meaningful once there are ten minor
    versions, which is exactly when nobody will remember to check."""
    from tcat_standard.schema import available_versions as av

    assert av() == sorted(av(), key=lambda v: tuple(int(x) for x in v.split(".")))


def test_every_documented_field_has_a_description():
    """A schema is documentation for three institutions. An undescribed field is
    a field someone will fill in by guessing from its name."""
    missing = []
    for kind in KINDS:
        doc = load_schema(kind)
        for name, sub in (doc.get("properties") or {}).items():
            if "description" not in sub and "$ref" not in sub:
                missing.append(f"{kind}.{name}")
    assert not missing, f"undocumented properties: {missing}"
