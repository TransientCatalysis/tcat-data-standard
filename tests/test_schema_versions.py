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


def test_the_package_version_matches_the_standard_document():
    """Four places record a version and they had all drifted apart.

    `pyproject.toml` and `__init__` said 0.1.0 while `STANDARD.md` and the
    changelog said 0.2.0, and a commit subject claimed 0.2.1 that no file
    recorded. The repository whose subject is version discipline is the last one
    that should be guessing at its own version, so this parses all four.

    Note the package version and the SCHEMA version are deliberately different
    numbers and move independently -- the changelog used to claim they moved
    together, which is what produced the drift.
    """
    import re
    from pathlib import Path

    import tcat_standard

    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    pkg = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)

    standard = (root / "STANDARD.md").read_text(encoding="utf-8")
    doc_comment = re.search(r"<!-- VERSION: ([^ ]+) -->", standard).group(1)
    doc_header = re.search(r"\*\*Standards version:\*\* (\S+)", standard).group(1)

    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    cff = re.search(r"^version: (\S+)", citation, re.M).group(1)

    assert pkg == tcat_standard.__version__ == doc_comment == doc_header == cff, (
        f"pyproject={pkg} __version__={tcat_standard.__version__} "
        f"STANDARD comment={doc_comment} STANDARD header={doc_header} CITATION={cff}"
    )


def test_the_standard_document_names_the_schema_version_that_ships():
    """They are different numbers on purpose, so the document has to say which
    schema directory it is describing, and be right about it."""
    import re
    from pathlib import Path

    from tcat_standard.schema import CURRENT_SCHEMA_VERSION

    standard = (Path(__file__).resolve().parents[1] / "STANDARD.md").read_text(encoding="utf-8")
    named = re.search(r"\*\*Schema version:\*\* (\S+)", standard).group(1)
    assert named == CURRENT_SCHEMA_VERSION


def test_schema_0_1_0_is_byte_identical_to_the_manifest_committed_when_it_froze():
    """Retention, made structural rather than promised.

    STANDARD.md 6 says a shipped version is never edited. Prose said that
    before, and 0.1.0 was nonetheless amended four times -- twice after real
    data already declared it. Real PSU documents declare 0.1.0, so an edit here
    silently changes what those documents were checked against, and the change
    is invisible in review because a schema diff looks like every other diff.

    If this fails, the fix is essentially never to update the manifest. It is to
    put the change in the CURRENT version directory instead.
    """
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "tcat_standard" / "schema" / "0.1.0"
    expected = json.loads(
        (Path(__file__).resolve().parent / "data" / "schema-0.1.0-frozen.sha256.json").read_text()
    )
    actual = {
        str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(root.rglob("*"))
        if f.is_file()
    }
    assert actual == expected, (
        "schema/0.1.0 has changed since it was frozen. It is retained forever and "
        "real data declares it; put the change in the current version instead."
    )
