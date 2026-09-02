"""Stewards: who is answerable now, as opposed to who did the work.

`personnel` is past tense and historical. `stewards` is present tense and
generates a repository permission, because .github/CODEOWNERS is derived from
it. They must not be merged: merging would either hand every historical
contributor write access, or lose the historical record the moment someone
leaves.
"""

from __future__ import annotations

import json

import pytest

from tcat_standard import validate
from tcat_standard.schema import load_schema, schema_dir

V = "0.2.0"
_ORCID = "0000-0001-8311-9581"

CREDIT_14 = [
    "conceptualization", "data-curation", "formal-analysis", "funding-acquisition",
    "investigation", "methodology", "project-administration", "resources", "software",
    "supervision", "validation", "visualization", "writing-original-draft",
    "writing-review-editing",
]


def _common(version: str = V) -> dict:
    """The shared $defs file, which is not a document kind and so is not
    reachable through load_schema."""
    return json.loads((schema_dir(version) / "defs" / "common.schema.json").read_text())


def steward(**over) -> dict:
    d = {"name": "A J Medford", "institution": "Georgia Tech",
         "role": "data_steward", "github": "ajmedford", "orcid": _ORCID}
    d.update(over)
    return d


def spoke(**over) -> dict:
    d = {"standard_version": V, "spoke_id": "psu-coox", "kind": "data",
         "stewards": [steward()]}
    d.update(over)
    return d


# --- the manifest ----------------------------------------------------------

def test_a_valid_spoke_manifest():
    assert validate(spoke(), "spoke", version=V).ok


def test_a_spoke_manifest_without_stewards_is_rejected():
    d = spoke()
    del d["stewards"]
    assert not validate(d, "spoke", version=V).ok


def test_an_empty_stewards_list_is_rejected():
    assert not validate(spoke(stewards=[]), "spoke", version=V).ok


def test_a_spoke_manifest_needs_an_id_and_a_kind():
    """`name` is explicitly a label nothing joins on, so without `spoke_id` a
    spoke can never be registered."""
    for missing in ("spoke_id", "kind"):
        d = spoke()
        del d[missing]
        assert not validate(d, "spoke", version=V).ok, missing


def test_an_analysis_spoke_may_carry_a_manifest_too():
    """The manifest used to be a data-spoke concept only, which left analysis
    spokes with nowhere to record ownership at all."""
    assert validate(spoke(kind="analysis"), "spoke", version=V).ok


def test_contacts_is_gone_in_0_2_0_and_still_accepted_in_0_1_0():
    """Removing a field in a minor bump is normally forbidden. The promise §6
    makes is that existing data stays valid, and `contacts` had zero instances
    anywhere in the tree -- so there is no data to invalidate. 0.1.0 is retained
    forever and still accepts it, and this test is what makes that mechanical
    rather than a promise."""
    with_contacts = {"standard_version": "0.1.0", "contacts": [{"name": "A"}]}
    assert validate(with_contacts, "spoke", version="0.1.0").ok
    assert not validate(spoke(contacts=[{"name": "A"}]), "spoke", version=V).ok


# --- a steward ------------------------------------------------------------

@pytest.mark.parametrize("missing", ["name", "institution", "role"])
def test_a_steward_needs_a_name_an_institution_and_a_role(missing):
    s = steward()
    del s[missing]
    assert not validate(spoke(stewards=[s]), "spoke", version=V).ok


def test_a_steward_role_outside_the_closed_set_is_rejected():
    """Closed because the point is that each duty has an owner and a validator
    can check the set is covered."""
    assert not validate(spoke(stewards=[steward(role="maintainer")]), "spoke", version=V).ok


@pytest.mark.parametrize("role", ["data_steward", "instrument_owner", "analysis_owner", "pi"])
def test_the_four_duties(role):
    assert validate(spoke(stewards=[steward(role=role)]), "spoke", version=V).ok


@pytest.mark.parametrize("credit", CREDIT_14)
def test_all_fourteen_credit_roles_are_accepted(credit):
    """Parametrised one per term: this is the test that catches a typo in the
    enum, which a single all-fourteen assertion would report as one failure."""
    assert validate(spoke(stewards=[steward(credit_roles=[credit])]), "spoke", version=V).ok


def test_a_credit_role_outside_the_fourteen_is_rejected():
    """CRediT is a fixed taxonomy; an open list would be a different vocabulary
    wearing its name."""
    assert not validate(spoke(stewards=[steward(credit_roles=["debugging"])]), "spoke", version=V).ok


def test_the_credit_enum_holds_exactly_fourteen_terms():
    defs = _common()["$defs"]
    enum = defs["stewards"]["items"]["properties"]["credit_roles"]["items"]["enum"]
    assert len(enum) == 14 and len(set(enum)) == 14


@pytest.mark.parametrize("handle", ["-leading", "trailing-", "double--hyphen", "a" * 40])
def test_a_malformed_github_handle_is_rejected(handle):
    """Validated rather than free text because a typo here is a wrong repository
    permission, not a cosmetic error."""
    assert not validate(spoke(stewards=[steward(github=handle)]), "spoke", version=V).ok


def test_a_well_formed_github_handle_is_accepted():
    assert validate(spoke(stewards=[steward(github="a-b-c1")]), "spoke", version=V).ok


# --- advice ---------------------------------------------------------------

def _warn_messages(report):
    return " | ".join(w.message for w in report.warnings)


def test_a_spoke_with_no_github_handle_anywhere_warns_and_says_why():
    s = steward()
    del s["github"]
    r = validate(spoke(stewards=[s]), "spoke", version=V)
    assert r.ok
    assert "CODEOWNERS" in _warn_messages(r)


def test_a_spoke_with_no_orcid_anywhere_warns():
    s = steward()
    del s["orcid"]
    r = validate(spoke(stewards=[s]), "spoke", version=V)
    assert r.ok and "ORCID" in _warn_messages(r)


def test_a_spoke_holding_calibrations_with_no_instrument_owner_warns():
    """A calibration change is reviewed by whoever owns the instrument, and the
    review is worthless if nobody knows who that is."""
    r = validate(spoke(layout={"calibration": ["calibrations"]}), "spoke", version=V)
    assert r.ok and "instrument_owner" in _warn_messages(r)


def test_a_spoke_with_only_a_pi_warns_that_codeowners_has_no_owner():
    r = validate(spoke(stewards=[steward(role="pi")]), "spoke", version=V)
    assert r.ok and "CODEOWNERS" in _warn_messages(r)


def test_no_stewardship_check_ever_reaches_the_error_list():
    """Fragile point 9, again -- the advisory/structural split is easy to break
    by bulk edit and has been broken once."""
    s = steward()
    del s["github"]
    del s["orcid"]
    r = validate(spoke(stewards=[s], layout={"calibration": ["c"]}), "spoke", version=V)
    assert r.ok, "a stewardship advisory check became an error"
    assert len(r.warnings) >= 3


# --- the record level -----------------------------------------------------

@pytest.mark.parametrize("kind", ["dataset", "sample", "model", "model-spec", "calibration"])
def test_records_may_override_the_spokes_stewards(kind):
    schema = load_schema(kind, V)
    assert schema["properties"]["stewards"]["$ref"].endswith("#/$defs/stewards")


def test_personnel_and_stewards_are_separate_definitions():
    """Not an alias and not a subset: one is who did the work, the other is who
    answers for it now."""
    defs = _common()["$defs"]
    assert defs["personnel"]["items"]["required"] == ["name"]
    assert set(defs["stewards"]["items"]["required"]) == {"name", "institution", "role"}


def test_personnel_no_longer_accepts_arbitrary_keys():
    """An open person object is where a stray email lands and then leaks through
    an export that does not know to strip it."""
    defs = _common()["$defs"]
    assert defs["personnel"]["items"]["additionalProperties"] is False
    assert _common("0.1.0")["$defs"]["personnel"]["items"]["additionalProperties"] is True


def test_a_spoke_manifest_away_from_a_spoke_root_is_still_checked(tmp_path):
    """It used to fall through to None and be skipped in silence. `spoke_id`
    gives the contents fallback something unique to key on."""
    from tcat_standard.cli import _infer_kind

    f = tmp_path / "somewhere" / "a-manifest.json"
    f.parent.mkdir()
    f.write_text(json.dumps(spoke()))
    assert _infer_kind(f) == "spoke"
