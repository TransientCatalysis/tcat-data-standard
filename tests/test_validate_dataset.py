"""Dataset validation. Passing this is what 'ingestible' means.

The fixtures are generated from the valid example by ``make_fixtures.py``, so
each one differs from a passing document in exactly one way and a failure names
exactly one thing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tcat_standard import ValidationError, validate_dataset
from tcat_standard.validate import validate_or_raise

DATA = Path(__file__).resolve().parent / "data"


def load(name: str) -> dict:
    """Read a fixture. Defined here rather than imported from conftest, which only
    resolves when pytest's rootdir happens to be this repository."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))

REQUIRED = [
    "schema_version", "dataset_id", "batch_id", "lineage_id", "layer", "status",
    "autonomy_level", "measurement_type", "sample_id", "instrument", "channels",
    "files", "access_status", "license", "provenance",
]


def test_the_example_is_valid(valid_dataset):
    report = validate_dataset(valid_dataset)
    assert report.ok, report.render()


@pytest.mark.parametrize("field", REQUIRED)
def test_each_required_field_is_required_and_named_in_the_error(field):
    """A validator whose output is 'does not match schema' gets routed around
    within a week. Every failure has to name the field."""
    doc = load(f"dataset-missing-{field.replace('_', '-')}.json")
    report = validate_dataset(doc)
    assert not report.ok
    assert any(field in problem.message for problem in report.errors), report.render()


# ---- the escape hatch --------------------------------------------------


def test_extensions_are_ignored_not_rejected():
    """Labs need somewhere to record a field the standard has not caught up
    with. The alternative is that they stop recording it, or stop running the
    validator."""
    report = validate_dataset(load("dataset-with-extensions.json"))
    assert report.ok, report.render()


def test_unknown_top_level_fields_are_rejected():
    """Which is the point of having a designated extensions namespace: typos and
    private conventions land there on purpose, not at the top level by accident."""
    report = validate_dataset(load("dataset-unknown-toplevel.json"))
    assert not report.ok
    assert any("reactor_conditioning_cycles" in p.message for p in report.errors)


# ---- flag, never delete ------------------------------------------------


def test_flagged_without_a_reason_is_invalid():
    report = validate_dataset(load("dataset-flagged-no-reason.json"))
    assert not report.ok
    assert any("status_reason" in p.message for p in report.errors)


def test_flagged_with_a_reason_is_valid():
    """Retaining a bad run is the requirement; the reason is what makes the
    retained run usable in an exclusion table later."""
    assert validate_dataset(load("dataset-flagged-with-reason.json")).ok


def test_empty_status_reason_is_not_enough(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["status"] = "failed"
    doc["status_reason"] = ""
    assert not validate_dataset(doc).ok


# ---- protocol, conditionally ------------------------------------------


def test_experimental_data_must_declare_a_protocol():
    report = validate_dataset(load("dataset-experimental-no-protocol.json"))
    assert not report.ok
    assert any("protocol" in p.message for p in report.errors)


def test_computational_data_need_not():
    assert validate_dataset(load("dataset-computational-no-protocol.json")).ok


def test_an_lfsr_waveform_requires_a_seed():
    """Register length, taps, and seed are what make an LFSR waveform regenerable.
    Without the seed it can only be re-measured from the trace."""
    report = validate_dataset(load("dataset-prbs-no-seed.json"))
    assert not report.ok
    assert any("seed" in p.message for p in report.errors)


def test_a_waveform_must_say_which_form_it_is():
    """The discriminator is what tells a reader whether the authoritative record
    is a generator spec, an executed schedule, or a tracer reconstruction."""
    report = validate_dataset(load("dataset-prbs-waveform-formless.json"))
    assert not report.ok


def test_a_waveform_may_be_a_recorded_schedule():
    """A randomised-dwell train has no generator state to record. The executed
    switch times are the reproducible thing, so they are a first-class form."""
    doc = load("dataset-valid.json")
    doc["protocol"]["parameters"]["waveform"] = {
        "form": "recorded",
        "switch_times_s": [0.0, 6.5, 8.6, 12.9],
        "initial_level": "low",
    }
    assert validate_dataset(doc).ok


def test_a_waveform_may_admit_it_was_reconstructed():
    """Legacy data whose valve schedule was never logged is a legal state -- it
    just has to say so, rather than leaving the field blank."""
    doc = load("dataset-valid.json")
    doc["protocol"]["parameters"]["waveform"] = {
        "form": "reconstructed",
        "tracer_channel": "m40",
        "reason": "valve controller logged no schedule; inlet recovered from the Ar tracer",
    }
    assert validate_dataset(doc).ok


# ---- units and uncertainty travel together ----------------------------


def test_a_channel_cannot_have_a_unit_without_an_uncertainty():
    """Which is why units and uncertainty are per-channel rather than in two
    parallel top-level maps that can drift out of sync."""
    report = validate_dataset(load("dataset-channel-no-uncertainty.json"))
    assert not report.ok
    assert any("uncertainty" in p.message for p in report.errors)


def test_sigma_column_must_name_its_column():
    report = validate_dataset(load("dataset-sigma-column-unnamed.json"))
    assert not report.ok
    assert any("column" in p.message for p in report.errors)


def test_channels_cannot_be_empty(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["channels"] = {}
    assert not validate_dataset(doc).ok


# ---- indirect references ----------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    ["dataset-absolute-path.json", "dataset-escaping-path.json", "dataset-two-locations.json"],
)
def test_bad_file_references_are_rejected(fixture):
    assert not validate_dataset(load(fixture)).ok


def test_two_locations_gets_a_readable_error():
    report = validate_dataset(load("dataset-two-locations.json"))
    assert any("exactly" in p.message and "location" in p.message for p in report.errors), (
        "the most load-bearing rule in the standard needs a message a human can act on"
    )


def test_files_cannot_be_empty(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["files"] = []
    assert not validate_dataset(doc).ok


# ---- convert at ingestion ---------------------------------------------


def test_raw_layer_may_hold_an_instrument_native_blob():
    assert validate_dataset(load("dataset-raw-native-blob.json")).ok


def test_canonical_layer_may_not():
    """Convert at ingestion; never carry the blob forward."""
    report = validate_dataset(load("dataset-canonical-native-blob.json"))
    assert not report.ok
    assert any("instrument-native" in p.message for p in report.errors)


# ---- enums and formats -------------------------------------------------


def test_autonomy_scale_tops_out_at_a5():
    """TRACE-AI's scale is A0-A5. The infrastructure spec said A0-A4; the
    checklist's own autonomy-run-log template is the authority."""
    report = validate_dataset(load("dataset-bad-autonomy.json"))
    assert not report.ok
    assert any("A5" in p.message for p in report.errors)


def test_naive_timestamps_are_rejected():
    """Three institutions in two time zones plus a synchrotron cannot align
    transients on a wall clock."""
    assert not validate_dataset(load("dataset-naive-timestamp.json")).ok


@pytest.mark.parametrize("bad", ["Ok", "OK", "unknown", "", "passed"])
def test_status_enum_is_closed(valid_dataset, bad):
    doc = copy.deepcopy(valid_dataset)
    doc["status"] = bad
    assert not validate_dataset(doc).ok


@pytest.mark.parametrize("bad", ["GPL-3.0", "cc-by-4.0", "CC BY 4.0", ""])
def test_license_must_be_a_known_spdx_identifier(valid_dataset, bad):
    doc = copy.deepcopy(valid_dataset)
    doc["license"] = bad
    assert not validate_dataset(doc).ok


# ---- version handling --------------------------------------------------


def test_a_document_is_checked_against_the_version_it_declares(valid_dataset):
    """The reason schema_version is recorded at all: data is checked against the
    standard it was written against, not whatever the standard became."""
    assert validate_dataset(valid_dataset).schema_version == valid_dataset["schema_version"]


def test_an_unknown_declared_version_fails_clearly(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["schema_version"] = "9.9.9"
    report = validate_dataset(doc)
    assert not report.ok
    assert any("9.9.9" in p.message for p in report.errors)


# ---- warnings are advice, never law ------------------------------------


def test_warnings_do_not_make_a_document_invalid(valid_dataset):
    """The moment style advice can fail a build, people stop running the
    validator locally and start discovering it at the worst possible time."""
    doc = copy.deepcopy(valid_dataset)
    doc.pop("notes")
    doc["access_status"] = "internal"
    report = validate_dataset(doc)
    assert report.ok
    assert report.warnings


def test_derived_without_a_calibration_reference_warns(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["layer"] = "derived"
    doc.pop("calibration_ref", None)
    report = validate_dataset(doc)
    assert report.ok
    assert any("calibration_ref" in w.pointer for w in report.warnings)


# ---- the refuse-to-emit path ------------------------------------------


def test_validate_or_raise_is_quiet_on_success(valid_dataset):
    validate_or_raise(valid_dataset, "dataset")


def test_validate_or_raise_raises_on_failure():
    """tcat-ingest refuses to emit when data does not validate. An invalid
    canonical artifact in the store is worse than no artifact."""
    with pytest.raises(ValidationError, match="batch_id"):
        validate_or_raise(load("dataset-missing-batch-id.json"), "dataset")


def test_report_renders_readably():
    text = validate_dataset(load("dataset-missing-batch-id.json"), source="x.json").render()
    assert text.startswith("FAIL")
    assert "batch_id" in text


# --------------------------------------------------------------- censoring


def _censored(valid_dataset, censoring: dict, *, add_flag=True) -> dict:
    doc = copy.deepcopy(valid_dataset)
    if add_flag:
        doc["channels"]["m44_censored"] = {
            "units": "1",
            "quantity": "censoring_flag",
            "uncertainty": {"kind": "none", "noise_model": {"family": "exact"}},
        }
    doc["channels"]["m44"]["censoring"] = censoring
    return doc


def test_a_censored_channel_is_valid(valid_dataset):
    """Censoring is a legal, common state of real data. Declaring it must not
    cost the declarer a validation failure, or nobody declares it."""
    doc = _censored(valid_dataset, {
        "kind": "left_clipped", "lower_bound": 0.0,
        "flag_column": "m44_censored", "fraction_censored": 0.184,
    })
    assert validate_dataset(doc).ok


def test_left_clipped_censoring_must_state_its_bound(valid_dataset):
    """'Clipped' without the value clipped at is not actionable: a reader still
    cannot tell which points are bounds."""
    report = validate_dataset(_censored(valid_dataset, {"kind": "left_clipped"}))
    assert not report.ok
    assert "lower_bound" in report.render()


def test_a_flag_column_naming_no_channel_is_an_error(valid_dataset):
    """A dangling reference looks satisfied until something follows it, which is
    exactly when it is most expensive to discover."""
    doc = _censored(valid_dataset, {
        "kind": "left_clipped", "lower_bound": 0.0, "flag_column": "not_a_channel",
    }, add_flag=False)
    report = validate_dataset(doc)
    assert not report.ok
    assert "not_a_channel" in report.render()


def test_a_time_column_naming_no_channel_is_an_error(valid_dataset):
    doc = copy.deepcopy(valid_dataset)
    doc["channels"]["m44"]["time_column"] = "ghost_time_s"
    report = validate_dataset(doc)
    assert not report.ok
    assert "ghost_time_s" in report.render()


def test_censoring_without_a_flag_column_warns_but_does_not_fail(valid_dataset):
    """Warnings never fail CI. The moment style advice can block a merge, people
    stop running the validator locally."""
    doc = _censored(valid_dataset, {"kind": "left_clipped", "lower_bound": 0.0},
                    add_flag=False)
    report = validate_dataset(doc)
    assert report.ok
    assert any("flag column" in w.message for w in report.warnings)


def test_a_substantial_censored_fraction_is_surfaced(valid_dataset):
    doc = _censored(valid_dataset, {
        "kind": "left_clipped", "lower_bound": 0.0,
        "flag_column": "m44_censored", "fraction_censored": 0.184,
    })
    report = validate_dataset(doc)
    assert report.ok
    assert any("18.4%" in w.message for w in report.warnings)


def test_a_negligible_censored_fraction_is_not_surfaced(valid_dataset):
    """Warning on every censored channel regardless of size would train readers
    to ignore the warning that matters."""
    doc = _censored(valid_dataset, {
        "kind": "left_clipped", "lower_bound": 0.0,
        "flag_column": "m44_censored", "fraction_censored": 0.001,
    })
    assert not any("bound rather than a measurement" in w.message
                   for w in validate_dataset(doc).warnings)


def test_an_exact_channel_is_not_nagged_about_missing_uncertainty(valid_dataset):
    """A flag column has no sigma to be missing. Warning about it forever trains
    readers to skip the warning that means a real measurement lost its."""
    doc = copy.deepcopy(valid_dataset)
    doc["channels"]["flag"] = {
        "units": "1", "quantity": "censoring_flag",
        "uncertainty": {"kind": "none", "noise_model": {"family": "exact"}},
    }
    warnings = validate_dataset(doc).warnings
    assert not any(w.pointer == "/channels/flag/uncertainty" for w in warnings)


def test_an_exact_channel_is_not_asked_which_clock_it_is_on(valid_dataset):
    """A scan counter or a censoring flag is bookkeeping, not a quantity observed
    at an instant, so 'which timestamps apply to it' has no answer to be
    missing."""
    doc = copy.deepcopy(valid_dataset)
    doc["time_base"]["kind"] = "per_channel"
    doc["channels"]["counter"] = {
        "units": "1", "quantity": "scan_index",
        "uncertainty": {"kind": "none", "noise_model": {"family": "exact"}},
    }
    warnings = validate_dataset(doc).warnings
    assert not any(w.pointer == "/channels/counter/time_column" for w in warnings)
    # and a real measurement channel is still asked
    assert any(w.pointer.endswith("/time_column") for w in warnings)
