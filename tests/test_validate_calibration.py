"""Calibration validation.

The load-bearing property: a fixed calibration must validate against the
time-indexed schema without special-casing. If it does not, every consumer grows
a branch for the one-entry case, and those branches are what break the day
someone supplies a before/after bracket.
"""

from __future__ import annotations

import copy

import pytest

from tcat_standard import validate_calibration


def test_the_example_is_valid(valid_calibration):
    assert validate_calibration(valid_calibration).ok


def test_a_single_entry_calibration_is_legal(valid_calibration):
    """A fixed calibration is the degenerate case of a drifting one. Code written
    against the general shape needs no change when a second entry appears."""
    assert len(valid_calibration["entries"]) == 1
    report = validate_calibration(valid_calibration)
    assert report.ok
    assert any("degenerate" in w.message for w in report.warnings)


def test_a_two_entry_bracket_validates_against_the_same_schema(valid_calibration):
    """The change that must NOT require a schema change or a code change."""
    doc = copy.deepcopy(valid_calibration)
    later = copy.deepcopy(doc["entries"][0])
    later["valid_from"] = "2026-09-15T09:00:00Z"
    later["channels"]["m44"]["sensitivity"] = 1.31e-9
    doc["entries"].append(later)
    report = validate_calibration(doc)
    assert report.ok, report.render()
    assert not any("degenerate" in w.message for w in report.warnings)


def test_entries_cannot_be_empty(valid_calibration):
    doc = copy.deepcopy(valid_calibration)
    doc["entries"] = []
    assert not validate_calibration(doc).ok


def test_out_of_order_entries_warn_but_do_not_fail(valid_calibration):
    doc = copy.deepcopy(valid_calibration)
    earlier = copy.deepcopy(doc["entries"][0])
    earlier["valid_from"] = "2026-08-01T09:00:00Z"
    doc["entries"].append(earlier)
    report = validate_calibration(doc)
    assert report.ok
    assert any("ascending" in w.message for w in report.warnings)


@pytest.mark.parametrize("field", ["calibration_id", "schema_version", "instrument", "entries"])
def test_required_fields(valid_calibration, field):
    doc = copy.deepcopy(valid_calibration)
    doc.pop(field)
    report = validate_calibration(doc)
    assert not report.ok
    assert any(field in p.message for p in report.errors)


def test_calibration_id_must_be_content_addressed(valid_calibration):
    """A calibration change produces a NEW id; it never mutates an existing
    artifact. A hand-written label would let it be edited in place, and then
    nothing downstream could tell which fits went stale."""
    doc = copy.deepcopy(valid_calibration)
    doc["calibration_id"] = "our-ms-calibration-v2"
    assert not validate_calibration(doc).ok


def test_every_channel_needs_a_sensitivity_and_a_unit(valid_calibration):
    for field in ("sensitivity", "units"):
        doc = copy.deepcopy(valid_calibration)
        doc["entries"][0]["channels"]["m44"].pop(field)
        report = validate_calibration(doc)
        assert not report.ok, field
        assert any(field in p.message for p in report.errors)


def test_sensitivity_units_are_written_target_over_source(valid_calibration):
    """So the conversion is checkable by inspection rather than by reading code."""
    units = valid_calibration["entries"][0]["channels"]["m44"]["units"]
    assert "/" in units and units.startswith("A")


def test_entry_valid_from_must_be_utc(valid_calibration):
    doc = copy.deepcopy(valid_calibration)
    doc["entries"][0]["valid_from"] = "2026-09-01 09:00:00"
    assert not validate_calibration(doc).ok


def test_fragmentation_matrix_is_referenced_not_inlined(valid_calibration):
    """It is revised independently of the sensitivity factors, so it is its own
    cited artifact. An inline table would be edited in place."""
    doc = copy.deepcopy(valid_calibration)
    doc["entries"][0]["fragmentation_matrix_ref"] = "art://frag-msq1-2026-09-01-77b201"
    assert validate_calibration(doc).ok

    doc["entries"][0]["fragmentation_matrix_ref"] = {"m44": {"m28": 0.11}}
    assert not validate_calibration(doc).ok


def test_unknown_channel_fields_are_rejected(valid_calibration):
    """Calibration is the tightest gate in the system -- everything downstream
    depends on it -- so it does not get a free-form escape hatch per channel."""
    doc = copy.deepcopy(valid_calibration)
    doc["entries"][0]["channels"]["m44"]["fudge"] = 1.02
    assert not validate_calibration(doc).ok


# ------------------------------------------- the shape real MS calibration has


def _first_channel(doc: dict) -> dict:
    return next(iter(doc["entries"][0]["channels"].values()))


def test_a_pressure_normalized_channel_validates(valid_calibration):
    """A quadrupole's count rate tracks chamber pressure, so a sensitivity
    determined at one pressure misreads at another. Real MS calibrations carry
    the correction; the schema has to be able to express it."""
    doc = copy.deepcopy(valid_calibration)
    _first_channel(doc)["pressure_normalization"] = {
        "reference_pressure": 8.017269059266212e-07,
        "pressure_channel": "pressure_torr",
        "units": "Torr",
        "form": "linear_scale",
    }
    assert validate_calibration(doc).ok


def test_pressure_normalization_must_name_the_channel_it_reads(valid_calibration):
    doc = copy.deepcopy(valid_calibration)
    _first_channel(doc)["pressure_normalization"] = {
        "reference_pressure": 8.0e-07, "units": "Torr",
    }
    report = validate_calibration(doc)
    assert not report.ok
    assert "pressure_channel" in report.render()


def test_a_signal_dependent_baseline_validates(valid_calibration):
    """Distinct from a cracking split: a split is a property of the molecule and
    transfers between instruments, a baseline is a property of this rig."""
    doc = copy.deepcopy(valid_calibration)
    _first_channel(doc)["baseline"] = {
        "source_channel": "co_counts", "slope": 0.0016255058062666825,
        "intercept": 104.29568912164723,
    }
    assert validate_calibration(doc).ok


def test_a_declared_floor_is_surfaced_as_advice(valid_calibration):
    """A calibration that clamps and does not say so is what makes a clamp
    indistinguishable from a measurement three artifacts downstream."""
    doc = copy.deepcopy(valid_calibration)
    _first_channel(doc)["floor"] = 0.0
    report = validate_calibration(doc)
    assert report.ok
    assert any("censoring block" in w.message for w in report.warnings)


def test_a_declared_but_unapplied_coefficient_survives_and_warns(valid_calibration):
    """The workbook this came from declares CO->O = 0.005905 in a parameter cell
    and hard-codes 0.0106 in 33,498 of 33,528 formula rows. `matrix` must carry
    what was applied; the declared value has to survive somewhere or the
    discrepancy is lost the moment anyone transcribes the parameter block."""
    doc = copy.deepcopy(valid_calibration)
    entry = doc["entries"][0]
    entry["matrix"] = {"CO->O": 0.0106}
    entry["declared_unused"] = {
        "CO->O": {"value": 0.005905,
                  "reason": "declared at W2; referenced by 1 of 1118 formula rows"},
    }
    report = validate_calibration(doc)
    assert report.ok
    assert any("0.005905" in w.message for w in report.warnings)


def test_a_declared_unused_entry_must_say_how_it_was_established(valid_calibration):
    """'They disagree' is not a work item. Which cell, and how many rows, is."""
    doc = copy.deepcopy(valid_calibration)
    doc["entries"][0]["declared_unused"] = {"CO->O": {"value": 0.005905}}
    report = validate_calibration(doc)
    assert not report.ok
    assert "reason" in report.render()
