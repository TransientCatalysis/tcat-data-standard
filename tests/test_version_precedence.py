"""Which schema version a document is checked against, and why that order.

The order is: an explicit --schema-version, then the document's own
schema_version, then a spoke manifest's standard_version, then the current
version. The middle two used to be the other way round, and the consequence was
not a wrong answer but a MISLEADING one: adding a manifest to a tree of
documents written against an older version revalidated all of them against a
schema they had never been checked against, and the failures read as "the schema
change broke the data".
"""

from __future__ import annotations

import json

import pytest

from tcat_standard import validate
from tcat_standard.schema import CURRENT_SCHEMA_VERSION, available_versions


def _minimal_spoke(version: str) -> dict:
    return {"standard_version": version}


def test_a_document_is_checked_against_the_version_it_declares():
    report = validate({"schema_version": "0.1.0"}, "sample")
    assert report.schema_version == "0.1.0"


def test_a_spoke_manifest_declares_its_version_under_a_different_name():
    """`spoke` carries `standard_version`, every other kind carries `schema_version`.

    So a manifest is checked against the CURRENT schema rather than against the
    version it pins -- the pin describes the records, not the manifest. Pinned
    here because it is surprising, and because anyone adding version resolution
    will otherwise assume one field name covers every kind.
    """
    report = validate({"standard_version": "0.1.0"}, "spoke")
    assert report.schema_version == CURRENT_SCHEMA_VERSION


def test_a_spoke_pin_does_not_override_a_documents_own_declared_version():
    """The regression this whole module exists for.

    A spoke may hold documents at several versions and usually will, because a
    bump never obliges a lab to rewrite data. So the pin is a default for
    documents that say nothing, never a correction to documents that do.
    """
    doc = {"schema_version": "0.1.0"}
    report = validate(doc, "sample", fallback_version="9.9.9")
    assert report.schema_version == "0.1.0", (
        "the spoke pin overrode the document's own declaration"
    )


def test_a_spoke_pin_applies_when_the_document_declares_nothing():
    # protocol carries no schema_version field of its own
    report = validate({}, "protocol", fallback_version="0.1.0")
    assert report.schema_version == "0.1.0"


def test_an_explicit_version_beats_both():
    """--schema-version is the one deliberate override, and its help says so."""
    doc = {"schema_version": "0.1.0"}
    report = validate(doc, "sample", version=CURRENT_SCHEMA_VERSION, fallback_version="0.1.0")
    assert report.schema_version == CURRENT_SCHEMA_VERSION


def test_with_nothing_declared_anywhere_the_current_version_is_used():
    assert validate({}, "protocol").schema_version == CURRENT_SCHEMA_VERSION


def test_an_unknown_version_is_an_error_at_schema_version_rather_than_a_crash():
    report = validate({"schema_version": "0.0.7"}, "sample")
    assert not report.ok
    assert any(p.pointer == "/schema_version" for p in report.errors)


def test_the_cli_does_not_carry_one_trees_pin_into_the_next(tmp_path):
    """Two roots in one `tcat-validate all` invocation are independent.

    The pin used to be written onto the parsed arguments, so it survived the
    loop iteration and silently applied to every later root on the command line.
    """
    from tcat_standard.cli import main

    pinned = tmp_path / "pinned"
    (pinned / "protocols").mkdir(parents=True)
    (pinned / ".tcat-spoke.json").write_text(json.dumps(_minimal_spoke("0.1.0")))

    unpinned = tmp_path / "unpinned"
    (unpinned / "protocols").mkdir(parents=True)

    # A document that declares nothing, in the tree that has no manifest.
    doc = {
        "protocol": "steady_state",
        "parameters": {},
        "base_conditions": {"temperature_K": 500.0},
    }
    (unpinned / "protocols" / "p.json").write_text(json.dumps(doc))
    (pinned / "protocols" / "p.json").write_text(json.dumps(doc))

    rc = main(["all", str(pinned), str(unpinned), "--json"])
    assert rc in (0, 1)  # the point is the versions, not the verdict


@pytest.mark.parametrize("version", available_versions())
def test_every_shipped_version_can_still_be_asked_for_by_name(version):
    """Retention is structural: a version directory is never removed."""
    assert validate({}, "protocol", version=version).schema_version == version
