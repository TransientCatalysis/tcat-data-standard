"""The maturity rung: how much weight someone else may put on a record.

Maturity is the fifth state vocabulary in this standard and the first one that
is a self-assessment. That is exactly why every rung has an entry criterion a
machine can check: this framework's ethos is checked-not-claimed, and a ladder
whose rungs were vibes would be the one soft thing in a hard system.
"""

from __future__ import annotations

import pytest

from tcat_standard import validate

V = "0.2.0"
_ORCID = "0000-0001-8311-9581"


def sample(**over) -> dict:
    d = {
        "schema_version": V,
        "sample_id": "S1",
        "status": "ok",
        "access_status": "internal",
        "license": "CC-BY-4.0",
    }
    d.update(over)
    return d


def _reviewed(**over) -> dict:
    d = {
        "rung": "internally_reviewed",
        "entered_at": "2026-09-01",
        "reviewed_by": {"name": "A J Medford", "orcid": _ORCID},
        "reviewed_on": "2026-09-01",
        "review_scope": "reproduced the workbook's own mole fractions from raw counts",
    }
    d.update(over)
    return d


def _errors_at(report, prefix):
    return [p for p in report.errors if p.pointer.startswith(prefix)]


def _warnings_at(report, prefix):
    return [p for p in report.warnings if p.pointer.startswith(prefix)]


# --- the enum itself -------------------------------------------------------

def test_a_document_with_no_maturity_block_is_valid_and_means_sandbox():
    """Absence is the bottom rung, so nothing written before the field existed
    changes meaning when the field arrives."""
    report = validate(sample(), "sample", version=V)
    assert report.ok
    assert not _warnings_at(report, "/maturity")


def test_an_unknown_rung_is_rejected():
    report = validate(sample(maturity={"rung": "validated"}), "sample", version=V)
    assert not report.ok


def test_sandbox_needs_nothing_else():
    assert validate(sample(maturity={"rung": "sandbox"}), "sample", version=V).ok


# --- the conditional requirements ------------------------------------------

def test_internally_reviewed_requires_a_named_reviewer_a_date_and_a_scope():
    report = validate(sample(maturity={"rung": "internally_reviewed"}), "sample", version=V)
    assert not report.ok
    assert _errors_at(report, "/maturity")


def test_a_reviewer_named_only_by_a_string_is_rejected():
    """People change institutions and share names. A review attributed to a
    string nobody can resolve is a review nobody can ask about."""
    m = _reviewed(reviewed_by={"name": "A Person"})
    report = validate(sample(maturity=m), "sample", version=V)
    assert not report.ok


@pytest.mark.parametrize("handle", [{"orcid": _ORCID}, {"github": "ajmedford"}])
def test_either_an_orcid_or_a_github_handle_satisfies_the_reviewer(handle):
    m = _reviewed(reviewed_by={"name": "A J Medford", **handle})
    assert validate(sample(maturity=m), "sample", version=V).ok


def test_a_review_scope_of_reviewed_is_too_short_to_be_a_scope():
    """Mirrors the analysis hub's blocked_on rule: "reviewed" describes nothing
    and cannot be audited."""
    report = validate(sample(maturity=_reviewed(review_scope="reviewed")), "sample", version=V)
    assert not report.ok


def test_published_requires_the_publication_it_was_published_in():
    """The rung REFERENCES the release gate in tcat-index/RELEASE.md rather than
    restating it, so it has to name the publication that passed it."""
    m = _reviewed(rung="published")
    report = validate(sample(maturity=m), "sample", version=V)
    assert not report.ok
    assert any("published_in" in p.message for p in report.errors)


def test_superseded_requires_a_successor_and_a_reason():
    report = validate(sample(maturity={"rung": "superseded"}), "sample", version=V)
    assert not report.ok
    assert any("superseded_by" in p.message for p in report.errors)


def test_superseded_is_complete_with_a_successor_and_a_reason():
    m = {
        "rung": "superseded",
        "superseded_by": "S2",
        "superseded_reason": "re-exported from the intact archive; this one is truncated",
    }
    assert validate(sample(maturity=m), "sample", version=V).ok


# --- the error MESSAGES, which are the point of the structural pass ---------

def test_the_reviewer_error_names_the_rung_rather_than_the_schema_path():
    report = validate(sample(maturity={"rung": "internally_reviewed"}), "sample", version=V)
    msgs = " ".join(p.message for p in report.errors)
    assert "internally_reviewed" in msgs
    assert "reviewed_by" in msgs


def test_the_unresolvable_reviewer_error_says_what_to_type():
    report = validate(sample(maturity=_reviewed(reviewed_by={"name": "A Person"})), "sample", version=V)
    msgs = " ".join(p.message for p in report.errors)
    assert "orcid" in msgs and "github" in msgs


# --- advice, never law -----------------------------------------------------

def test_no_maturity_check_ever_reaches_the_error_list():
    """Fragile point 9. The two functions share anchors, and a bulk edit has
    once landed a block in both and turned warnings into errors."""
    m = _reviewed(rung="published", published_in="P1", reviewed_on="1999-01-01")
    report = validate(sample(maturity=m, access_status="internal"), "sample", version=V)
    assert report.ok, "an advisory maturity check became an error"
    assert _warnings_at(report, "/maturity")


def test_a_working_claim_warns_when_the_document_still_raises_warnings():
    report = validate(sample(maturity={"rung": "working", "entered_at": "2026-09-01"}), "sample", version=V)
    assert report.ok
    assert any("warnings_accepted" in w.message for w in report.warnings)


def test_a_working_claim_is_quiet_when_every_warning_is_accepted_by_pointer():
    """This is what makes `working` checkable rather than felt, and the only
    place an advisory check has a consequence -- on a voluntary claim."""
    bare = validate(sample(), "sample", version=V)
    accepted = [
        {"pointer": w.pointer, "reason": "accepted for the purposes of this test, with a reason"}
        for w in bare.warnings
    ]
    m = {"rung": "working", "entered_at": "2026-09-01", "warnings_accepted": accepted}
    report = validate(sample(maturity=m), "sample", version=V)
    assert not any("warnings_accepted" in w.message for w in report.warnings)


def test_an_accepted_warning_needs_a_real_reason():
    m = {
        "rung": "working",
        "warnings_accepted": [{"pointer": "/notes", "reason": "known"}],
    }
    assert not validate(sample(maturity=m), "sample", version=V).ok


def test_a_self_review_warns_but_does_not_fail():
    """A one-person spoke is real. Refusing it would produce a second name that
    did not review anything, which is worse than the warning."""
    doc = sample(
        stewards=[{"name": "A J Medford", "institution": "GT", "role": "data_steward", "orcid": _ORCID}],
        maturity=_reviewed(),
    )
    report = validate(doc, "sample", version=V)
    assert report.ok
    assert any(w.pointer == "/maturity/reviewed_by" for w in report.warnings)


def test_a_non_sandbox_rung_without_a_date_warns():
    report = validate(sample(maturity={"rung": "working"}), "sample", version=V)
    assert any(w.pointer == "/maturity/entered_at" for w in report.warnings)


def test_published_maturity_on_a_non_public_record_warns_here_but_does_not_fail():
    """An error in the registry, advice here: mid-release the two are
    legitimately out of step for a few minutes."""
    m = _reviewed(rung="published", published_in="P1")
    report = validate(sample(maturity=m, access_status="internal"), "sample", version=V)
    assert report.ok
    assert any("access_status" in w.message for w in report.warnings)


# --- where it is carried ---------------------------------------------------

@pytest.mark.parametrize(
    "kind", ["dataset", "sample", "model", "model-spec", "calibration", "protocol",
             "uncertainty-ensemble", "campaign"],
)
def test_every_kind_that_carries_maturity_refs_the_shared_definition(kind):
    """Nobody re-inlines the enum. A second copy is how two rungs called
    `published` come to mean different things."""
    from tcat_standard.schema import load_schema

    schema = load_schema(kind, V)
    ref = schema["properties"]["maturity"]["$ref"]
    assert ref.endswith("#/$defs/maturity")


@pytest.mark.parametrize("kind", ["publication", "provenance", "manifest-entry"])
def test_the_kinds_that_deliberately_do_not_carry_maturity(kind):
    """`publication.status` IS its own ladder and is the anchor the `published`
    rung points at; provenance is an immutable fact about a computation that
    happened; a manifest entry is a checksummed pointer, and bytes do not
    mature."""
    from tcat_standard.schema import load_schema

    assert "maturity" not in load_schema(kind, V).get("properties", {})


def test_a_spoke_cannot_claim_a_rung_that_rests_on_a_named_reviewer():
    """Uncapped, one edit to one file would promote every record in the tree --
    a claim manufactured by inheritance, which is the failure the ladder exists
    to prevent."""
    spoke = {
        "standard_version": V,
        "spoke_id": "s",
        "kind": "data",
        "stewards": [{"name": "A", "institution": "GT", "role": "data_steward", "github": "a"}],
        "maturity": {"rung": "internally_reviewed"},
    }
    assert not validate(spoke, "spoke", version=V).ok


@pytest.mark.parametrize("rung", ["sandbox", "working"])
def test_a_spoke_may_default_to_the_two_rungs_that_do_not(rung):
    spoke = {
        "standard_version": V,
        "spoke_id": "s",
        "kind": "data",
        "stewards": [{"name": "A", "institution": "GT", "role": "data_steward", "github": "a"}],
        "maturity": {"rung": rung},
    }
    assert validate(spoke, "spoke", version=V).ok


def test_maturity_did_not_exist_in_0_1_0():
    """Old versions are never edited. A 0.1.0 document that carries a maturity
    block is rejected by 0.1.0, which is correct."""
    doc = dict(sample(), schema_version="0.1.0", maturity={"rung": "sandbox"})
    assert not validate(doc, "sample", version="0.1.0").ok
