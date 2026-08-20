"""Provenance, uncertainty ensembles, and protocols."""

from __future__ import annotations

import copy

import pytest

from tcat_standard import (
    validate_protocol,
    validate_provenance,
    validate_uncertainty_ensemble,
)

PROVENANCE = {
    "artifact_id": "fit-synth-co-ox-2026-09-01-9b12ee",
    "tool": {"name": "tcat-fit", "version": "0.1.3", "git_sha": "4c1a09e"},
    "inputs": ["conc-synth-co-ox-2026-09-01-77b201", "cal-msq1-synthetic-2026-09-01-a3f91c"],
    "parameters": {"solver": "radau", "rtol": 1e-8, "method": "laplace"},
    "data_schema_version": "0.1.0",
    "autonomy_level": "A1",
    "durability": "durable",
    "created_at": "2026-09-01T18:22:11Z",
    "host": "gt-workstation-04",
}

ENSEMBLE = {
    "schema_version": "0.1.0",
    "method": "laplace",
    "method_family": "asymptotic",
    "parameter_names": ["log10_k_ads", "log10_k_des", "log10_k_rxn"],
    "parameter_units": ["log10(1/(Pa s))", "log10(1/s)", "log10(1/s)"],
    "parameter_transform": "log10",
    "n_samples": 2000,
    "point_estimate": [-3.2, -1.7, 0.4],
    "samples": {
        "sha256": "0" * 64,
        "size_bytes": 48000,
        "format": "csv",
        "path": "derived/ensembles/fit-synth-co-ox-samples.csv",
    },
}


# ---- provenance --------------------------------------------------------


def test_provenance_example_is_valid():
    assert validate_provenance(PROVENANCE).ok


@pytest.mark.parametrize("field", list(PROVENANCE))
def test_every_provenance_field_is_required(field):
    """The shape is identical on every run of every tool. Optional provenance
    fields are how records become unusable in aggregate."""
    doc = copy.deepcopy(PROVENANCE)
    doc.pop(field)
    report = validate_provenance(doc)
    assert not report.ok
    assert any(field in p.message for p in report.errors)


def test_tool_name_must_be_a_tcat_tool():
    doc = copy.deepcopy(PROVENANCE)
    doc["tool"]["name"] = "my_fit_script.py"
    assert not validate_provenance(doc).ok


def test_dirty_working_tree_is_recordable():
    """The honest answer for a working-tree run. Recording 'dirty' is better than
    recording a sha that does not describe the code that ran -- and it is what
    disqualifies the artifact from promotion."""
    doc = copy.deepcopy(PROVENANCE)
    doc["tool"]["git_sha"] = "dirty"
    assert validate_provenance(doc).ok


def test_durability_is_a_closed_choice():
    doc = copy.deepcopy(PROVENANCE)
    doc["durability"] = "maybe"
    assert not validate_provenance(doc).ok


def test_inputs_may_be_empty_at_the_raw_boundary():
    """tcat-ingest reads a manifest from disk; it has no artifact inputs."""
    doc = copy.deepcopy(PROVENANCE)
    doc["inputs"] = []
    assert validate_provenance(doc).ok


def test_inputs_must_be_artifact_ids_not_paths():
    doc = copy.deepcopy(PROVENANCE)
    doc["inputs"] = ["data/raw/run-014.csv"]
    assert not validate_provenance(doc).ok


def test_interpolation_rule_lives_in_parameters():
    """So the choice is auditable rather than buried in code."""
    doc = copy.deepcopy(PROVENANCE)
    doc["parameters"]["interpolation"] = "hold_constant"
    assert validate_provenance(doc).ok


# ---- uncertainty ensembles ---------------------------------------------


def test_ensemble_example_is_valid():
    assert validate_uncertainty_ensemble(ENSEMBLE).ok


def test_a_frequentist_fit_uses_the_same_shape_as_a_sampler():
    """The reason there is one shape: experiment design consumes it without
    caring how the fit was done, so there is no need for two design pathways."""
    lap = validate_uncertainty_ensemble(ENSEMBLE)
    hmc = validate_uncertainty_ensemble(
        dict(ENSEMBLE, method="nuts", method_family="sampled",
             convergence={"r_hat_max": 1.01, "ess_min": 820, "divergences": 0, "seed": 7})
    )
    assert lap.ok and hmc.ok


def test_the_sample_is_required_not_just_a_summary():
    """Gaussian summaries discard exactly the correlation structure that drives
    experimental design, so the sample is the primary record."""
    doc = copy.deepcopy(ENSEMBLE)
    doc.pop("samples")
    report = validate_uncertainty_ensemble(doc)
    assert not report.ok
    assert any("samples" in p.message for p in report.errors)


def test_covariance_is_a_derived_summary_reference():
    """Direction of the arrow: the ensemble points AT its summary, not the other
    way round."""
    doc = dict(ENSEMBLE, summary_ref="art://cov-synth-co-ox-2026-09-01-abcdef")
    assert validate_uncertainty_ensemble(doc).ok


def test_method_is_required_so_nobody_mistakes_laplace_for_a_posterior():
    doc = copy.deepcopy(ENSEMBLE)
    doc.pop("method")
    assert not validate_uncertainty_ensemble(doc).ok


def test_asymptotic_family_is_flagged_as_such():
    report = validate_uncertainty_ensemble(ENSEMBLE)
    assert any("asymptotic" in w.message for w in report.warnings)


def test_point_estimate_length_mismatch_warns():
    doc = copy.deepcopy(ENSEMBLE)
    doc["point_estimate"] = [-3.2, -1.7]
    report = validate_uncertainty_ensemble(doc)
    assert any("parameter_names" in w.message for w in report.warnings)


def test_log_transform_must_be_declared():
    """Kinetic parameters are routinely fit in log space; leaving that implicit
    is a reliable way to be wrong by orders of magnitude."""
    assert ENSEMBLE["parameter_transform"] == "log10"
    doc = copy.deepcopy(ENSEMBLE)
    doc["parameter_transform"] = "log"
    assert not validate_uncertainty_ensemble(doc).ok


# ---- protocols ---------------------------------------------------------


def test_protocol_example_is_valid(valid_protocol):
    assert validate_protocol(valid_protocol).ok


def test_chemical_looping_is_expressible_as_multi_pulse():
    """An extended propane pulse followed by an extended O2 re-oxidation pulse --
    the M6 milestone's held-out prediction target."""
    doc = {
        "protocol": "multi_pulse",
        "parameters": {
            "segments": [
                {"species": "C3H8", "duration_s": 120.0, "mol_frac": 0.05, "label": "reduction"},
                {"species": "He", "duration_s": 30.0, "mol_frac": 1.0, "label": "purge"},
                {"species": "O2", "duration_s": 180.0, "mol_frac": 0.10, "label": "reoxidation"},
            ],
            "cycles": 3,
        },
        "base_conditions": {"temperature_K": 723.0, "pressure_kPa": 101.3},
    }
    assert validate_protocol(doc).ok


def test_each_protocol_owns_its_parameter_space():
    """prbs parameters on a temperature_ramp is a mistake the schema catches."""
    doc = {
        "protocol": "temperature_ramp",
        "parameters": {"species": "CO", "bit_period_s": 2.0},
        "base_conditions": {"temperature_K": 573.0, "pressure_kPa": 101.3},
    }
    assert not validate_protocol(doc).ok


def test_base_conditions_require_temperature_and_pressure():
    doc = {"protocol": "step_change",
           "parameters": {"species": "O2", "from_mol_frac": 0.0, "to_mol_frac": 0.05, "step_at_s": 10.0},
           "base_conditions": {"temperature_K": 573.0}}
    assert not validate_protocol(doc).ok


def test_unknown_protocol_names_are_rejected():
    doc = {"protocol": "chirp", "parameters": {}, "base_conditions": {"temperature_K": 573.0, "pressure_kPa": 101.3}}
    assert not validate_protocol(doc).ok
