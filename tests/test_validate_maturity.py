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
        "rung": "reviewed",
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

def test_reviewed_requires_a_named_reviewer_a_date_and_a_scope():
    report = validate(sample(maturity={"rung": "reviewed"}), "sample", version=V)
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


def test_superseded_requires_a_reason():
    """What happened is the part a reader needs. Which of the two cases it was --
    replaced, or abandoned -- is carried here and nowhere else."""
    report = validate(sample(maturity={"rung": "superseded"}), "sample", version=V)
    assert not report.ok
    assert any(p.pointer.startswith("/maturity") for p in report.errors)


def test_abandoned_work_may_be_superseded_with_no_successor():
    """`superseded` covers ABANDONMENT as well as replacement, and abandoned work
    has no successor to point at. Requiring one would force people to invent a
    replacement, or to leave the record at a rung that overstates it."""
    m = {
        "rung": "superseded",
        "superseded_reason": "the student graduated and nobody picked the approach up",
    }
    report = validate(sample(maturity=m), "sample", version=V)
    assert report.ok


def test_a_superseded_record_with_no_successor_is_warned_about_not_refused():
    """Correct for abandonment, and a dead end when something did replace it --
    which is why it is advice rather than a refusal."""
    m = {"rung": "superseded", "superseded_reason": "abandoned after the re-export arrived"}
    report = validate(sample(maturity=m), "sample", version=V)
    assert any(w.pointer == "/maturity/superseded_by" for w in report.warnings)


def test_superseded_is_complete_with_a_successor_and_a_reason():
    m = {
        "rung": "superseded",
        "superseded_by": "S2",
        "superseded_reason": "re-exported from the intact archive; this one is truncated",
    }
    assert validate(sample(maturity=m), "sample", version=V).ok


# --- the error MESSAGES, which are the point of the structural pass ---------

def test_the_reviewer_error_names_the_rung_rather_than_the_schema_path():
    report = validate(sample(maturity={"rung": "reviewed"}), "sample", version=V)
    msgs = " ".join(p.message for p in report.errors)
    assert "reviewed" in msgs
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
        "maturity": {"rung": "reviewed"},
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


# --- the permanent-home rule ----------------------------------------------

def _dataset_at(rung: str, *, url: bool = True, **maturity) -> dict:
    """A real dataset document, from the generated example, with its bytes moved.

    Derived from `examples/dataset-prbs-co-ox.json` rather than hand-written, per
    CONTRIBUTING: a hand-built fixture drifts from the schema and then fails for
    a reason that has nothing to do with what it is testing. This one did exactly
    that while being written -- five unrelated errors, none of them about
    permanent homes.
    """
    import copy
    import json
    from pathlib import Path as _Path

    example = json.loads(
        (_Path(__file__).resolve().parents[1] / "examples" / "dataset-prbs-co-ox.json").read_text()
    )
    doc = copy.deepcopy(example)

    if url:
        # The OneDrive case: bytes somewhere this project does not control.
        for entry in doc["files"]:
            entry.pop("path", None)
            entry["url"] = "https://example.sharepoint.com/a/Fast_Summary.csv"

    m = {"rung": rung, "entered_at": "2026-09-01"}
    if rung in ("reviewed", "published"):
        m |= {
            "reviewed_by": {"name": "R Rioux", "orcid": "0000-0002-1825-0097"},
            "reviewed_on": "2026-09-01",
            "review_scope": "checked the exported counts against the instrument log",
        }
    if rung == "published":
        m["published_in"] = "pub-example-2026"
    m.update(maturity)
    doc["maturity"] = m
    return doc


def _home_warnings(doc):
    r = validate(doc, "dataset", version=V)
    return [w for w in r.warnings if "/files/" in w.pointer]


@pytest.mark.parametrize("rung", ["sandbox", "working"])
def test_sandbox_and_working_data_may_live_anywhere(rung):
    """The PI rule, one half: data feeding sandbox and working pipelines lives
    wherever is convenient -- a lab share, OneDrive, scratch. Warning about it
    would be warning about the normal case, which is how people learn to skip
    warnings."""
    assert _home_warnings(_dataset_at(rung)) == []


def test_a_reviewed_record_on_a_revocable_url_is_warned_about():
    """The other half: once a record claims someone checked it, somebody may
    cite it, and a citation pointing at a share link breaks silently."""
    warnings = _home_warnings(_dataset_at("reviewed"))
    assert warnings
    assert "deposit" in warnings[0].message


def test_a_deposit_doi_settles_it():
    """A DOI is a promise a repository has made, rather than one a share link
    implies."""
    doc = _dataset_at("reviewed", deposit_doi="10.5281/zenodo.123")
    assert _home_warnings(doc) == []


def test_bytes_kept_in_the_repository_need_no_deposit():
    """`path` is as durable as the repository itself, which is the thing being
    asked for."""
    assert _home_warnings(_dataset_at("reviewed", url=False)) == []


def test_the_permanent_home_rule_is_advice_and_never_an_error():
    """Depositing takes time and a decision about where. Blocking a review claim
    on it would mean people stop claiming reviews, not that they deposit sooner."""
    assert validate(_dataset_at("reviewed"), "dataset", version=V).ok
