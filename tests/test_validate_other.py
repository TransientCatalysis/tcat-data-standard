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


def test_a_non_conforming_producer_must_say_so():
    """Every spoke bootstraps with a lab script before a conforming tool exists,
    and legacy deposits stay that way forever. The name is allowed to be
    anything only once the record admits what produced it."""
    doc = copy.deepcopy(PROVENANCE)
    doc["tool"]["name"] = "convert_workbook.py"
    doc["tool"]["conforming"] = False
    assert validate_provenance(doc).ok


def test_conforming_true_still_demands_a_tcat_name():
    """Otherwise the flag would be a way to opt out of the naming rule while
    still claiming the guarantees that come with it."""
    doc = copy.deepcopy(PROVENANCE)
    doc["tool"]["name"] = "convert_workbook.py"
    doc["tool"]["conforming"] = True
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


def test_an_ensemble_without_a_conditioning_block_is_valid_and_means_conditional():
    """The single most important absence rule in the uncertainty additions:
    every ensemble written before the block existed conditioned silently, so
    absence must mean 'conditional' and stay valid -- nothing already in a
    store changes meaning."""
    assert "conditioning" not in ENSEMBLE
    assert validate_uncertainty_ensemble(ENSEMBLE).ok


def test_a_marginalized_ensemble_declares_what_it_marginalized():
    doc = dict(ENSEMBLE, conditioning={
        "kind": "marginalized",
        "marginalized": ["co_to_o_fragmentation", "void_fraction"],
        "held_fixed": ["ms_sensitivity_CO", "site_density"],
        "prior_source": "calibration entry priors + bed uncertainty map",
    })
    report = validate_uncertainty_ensemble(doc)
    assert report.ok
    assert not any("conditioning" in w.pointer for w in report.warnings)


def test_a_marginalized_claim_with_no_named_nuisances_warns():
    doc = dict(ENSEMBLE, conditioning={"kind": "marginalized"})
    report = validate_uncertainty_ensemble(doc)
    assert report.ok
    assert any("conditioning" in w.pointer for w in report.warnings)


def test_parameter_roles_must_parallel_parameter_names():
    doc = dict(ENSEMBLE, parameter_roles=["interest", "nuisance"])
    report = validate_uncertainty_ensemble(doc)
    assert any("parameter_roles" in w.pointer for w in report.warnings)
    doc = dict(ENSEMBLE, parameter_roles=["interest", "interest", "nuisance"])
    report = validate_uncertainty_ensemble(doc)
    assert report.ok
    assert not any("parameter_roles" in w.pointer for w in report.warnings)


def test_a_nuisance_budget_row_may_be_honestly_priorless():
    """sigma_nuisance is nullable ON PURPOSE: where no record states an
    uncertainty, the row routes to the prior-free envelope instead of carrying
    an invented sigma."""
    doc = dict(ENSEMBLE, nuisance_budget=[{
        "parameter": "log10_k_ads",
        "nuisance": "ms_sensitivity_CO",
        "sensitivity": -0.42,
        "sigma_nuisance": None,
        "source": "no record states an MS sensitivity uncertainty; envelope",
    }])
    assert validate_uncertainty_ensemble(doc).ok


def test_mixture_weights_must_sum_to_one():
    components = [
        {"ensemble_id": "art://fit-a-2026-09-01-aaaaaa", "weight": 0.7,
         "weight_criterion": "BIC"},
        {"ensemble_id": "art://fit-b-2026-09-01-bbbbbb", "weight": 0.2,
         "weight_criterion": "BIC"},
    ]
    doc = dict(ENSEMBLE, method="posterior_mixture", method_family="sampled",
               components=components)
    report = validate_uncertainty_ensemble(doc)
    assert report.ok
    assert any("sum to" in w.message for w in report.warnings)
    components[1]["weight"] = 0.3
    report = validate_uncertainty_ensemble(doc)
    assert not any("sum to" in w.message for w in report.warnings)


def test_a_mixture_declares_a_sampled_family():
    doc = dict(ENSEMBLE, method="posterior_mixture",
               components=[{"ensemble_id": "art://fit-a-2026-09-01-aaaaaa",
                            "weight": 1.0}])
    report = validate_uncertainty_ensemble(doc)
    assert any("sampled family" in w.message for w in report.warnings)


def test_approximation_distinguishes_quadratic_from_profiled():
    """laplace and profile_likelihood share method_family='asymptotic'; the
    quadratic-vs-actual-shape distinction is the entire reason to profile, so
    it needs its own field rather than an enum split of a hashed registry."""
    assert validate_uncertainty_ensemble(
        dict(ENSEMBLE, approximation="quadratic")).ok
    assert validate_uncertainty_ensemble(
        dict(ENSEMBLE, method="profile_likelihood",
             approximation="profiled")).ok
    assert not validate_uncertainty_ensemble(
        dict(ENSEMBLE, approximation="exact")).ok


# ---- protocols ---------------------------------------------------------


def test_protocol_example_is_valid(valid_protocol):
    assert validate_protocol(valid_protocol).ok


def test_a_bed_uncertainty_key_must_name_a_real_bed_field():
    """Same rule as channel references: a sigma keyed to nothing looks
    satisfied right up until something tries to use it."""
    doc = {
        "protocol": "step_change",
        "parameters": {"species": "O2", "from_mol_frac": 0.0,
                       "to_mol_frac": 0.05, "step_at_s": 10.0},
        "base_conditions": {
            "temperature_K": 459.15, "pressure_kPa": 101.3,
            "bed": {"length_mm": 10.0, "diameter_mm": 3.9,
                    "void_fraction": 0.853,
                    "uncertainty": {"void_fraction": 0.05}},
        },
    }
    assert validate_protocol(doc).ok
    doc["base_conditions"]["bed"]["uncertainty"] = {"porosity": 0.05}
    report = validate_protocol(doc)
    assert not report.ok
    assert any("names no bed field" in p.message for p in report.errors)


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


# ---- model specifications ----------------------------------------------
#
# The argument these tests defend: a mechanism is an ARTIFACT, not a name in a
# capability registry. Registries suit method vocabularies -- few, stable,
# shared. Mechanisms are combinatorially many, are generated automatically by
# discovery and reduction, and comparing competing ones is the science. A
# registry entry per candidate would put a pull request in front of every
# hypothesis.


def _spec(name):
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "examples"
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_both_example_specifications_are_valid():
    from tcat_standard import validate_model_spec

    for name in ("model-spec-co-ox-irreversible.json", "model-spec-co-ox-reversible.json"):
        report = validate_model_spec(_spec(name))
        assert report.ok, report.render()


def test_the_two_variants_really_are_different_models():
    """Not a tautology. They describe the same five steps and differ in three
    fields, and that difference is eight free parameters against ten. If the
    schema let them look identical, a comparison between them would be
    meaningless."""
    a = _spec("model-spec-co-ox-irreversible.json")
    b = _spec("model-spec-co-ox-reversible.json")

    assert a["mechanism"]["steps"][3]["reversible"] is False
    assert b["mechanism"]["steps"][3]["reversible"] is True
    assert "constraint" not in a["mechanism"]["steps"][3]
    assert b["mechanism"]["steps"][3]["constraint"]["kind"] == "thermodynamic_closure"
    # Eight against nine: step 4 gains a reverse constant in b, but it is FIXED
    # by the closure rather than fitted, so it costs no free parameter -- while
    # step 5's reverse does. Getting this count wrong in either direction is how
    # a comparison between the two silently stops being fair.
    assert len(a["free_parameters"]) == 8
    assert len(b["free_parameters"]) == 9


def test_a_microkinetic_specification_must_carry_a_mechanism():
    from tcat_standard import validate_model_spec

    doc = _spec("model-spec-co-ox-irreversible.json")
    doc.pop("mechanism")
    report = validate_model_spec(doc)
    assert not report.ok
    assert any("mechanism" in p.message for p in report.errors)


def test_a_step_must_declare_its_reversibility():
    """Required rather than defaulted, because an unstated reversibility is the
    difference between an eight-parameter and a ten-parameter fit -- and a
    default would silently pick one."""
    from tcat_standard import validate_model_spec

    doc = _spec("model-spec-co-ox-irreversible.json")
    doc["mechanism"]["steps"][0].pop("reversible")
    report = validate_model_spec(doc)
    assert not report.ok
    assert any("reversible" in p.message for p in report.errors)


def test_a_neural_specification_needs_an_architecture_not_a_mechanism():
    """The same document kind covers the M3 baseline. A trained network's
    architecture is as much 'what was fitted' as a mechanism is, and it has been
    exactly as likely to live only in a script."""
    from tcat_standard import validate_model_spec

    doc = {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-lstm-baseline",
        "family": "rnn",
        "name": "LSTM baseline",
    }
    assert not validate_model_spec(doc).ok

    doc["architecture"] = {"layers": [{"kind": "lstm", "hidden": 8, "layers": 4}], "seed": 11}
    assert validate_model_spec(doc).ok


def test_two_specifications_differing_anywhere_get_different_ids():
    """What content addressing buys, and what the registry was protecting: two
    mechanisms cannot collide on one id, and nobody has to coordinate to
    guarantee it."""
    from tcat_standard import make_artifact_id

    a = _spec("model-spec-co-ox-irreversible.json")
    b = _spec("model-spec-co-ox-reversible.json")

    def ident(doc):
        return make_artifact_id(
            tool="spec", name=doc["spec_id"], when="2026-09-01",
            tool_name="tcat-spec", tool_version="0.1.0", inputs=[],
            parameters={"specification": doc["mechanism"]},
        )

    assert ident(a) != ident(b)
    assert ident(a) == ident(a)
