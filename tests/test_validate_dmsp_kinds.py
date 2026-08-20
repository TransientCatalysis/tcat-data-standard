"""Sample, model, and publication records.

These three exist because the DMSP commits to them: a registry that links data to
samples and publications, materials data with synthesis and characterization, and
models distributed with training-data references, hyperparameters, metrics,
uncertainty, and limitations on appropriate use.

The tests worth reading are the ones that check the *advisory* warnings, because
those encode the failure modes that are technically valid and practically useless
-- a model with no stated limits, an ungrouped split, a metric with no interval.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tcat_standard import validate_model, validate_publication, validate_sample

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def sample() -> dict:
    return _load("sample-synthetic.json")


@pytest.fixture
def model() -> dict:
    return _load("model-lh-two-site.json")


@pytest.fixture
def publication() -> dict:
    return _load("publication-example.json")


# ===================================================================== sample


def test_the_sample_example_is_valid(sample):
    assert validate_sample(sample).ok


@pytest.mark.parametrize("field", ["schema_version", "sample_id", "status", "access_status", "license"])
def test_sample_required_fields(sample, field):
    doc = copy.deepcopy(sample)
    doc.pop(field)
    report = validate_sample(doc)
    assert not report.ok
    assert any(field in p.message for p in report.errors)


def test_a_failed_synthesis_is_retained_with_a_reason(sample):
    """Flag, never delete, applies to samples too. A synthesis that failed is
    often the most informative entry in a materials series."""
    doc = copy.deepcopy(sample)
    doc["status"] = "failed"
    assert not validate_sample(doc).ok, "no reason given"

    doc["status_reason"] = "V loading came out at 0.4 wt% against a 3 wt% target; support was wet."
    assert validate_sample(doc).ok


def test_a_measured_composition_must_name_its_method(sample):
    """A composition without its method is not comparable across labs."""
    doc = copy.deepcopy(sample)
    doc["composition"]["measured"]["V"].pop("method")
    assert not validate_sample(doc).ok


def test_a_nominal_composition_needs_no_method(sample):
    """Because there is none -- it is what was intended, not what was found."""
    assert "method" not in sample["composition"]["nominal"]["V"]
    assert validate_sample(sample).ok


def test_thermal_treatments_are_ordered_and_carry_conditions(sample):
    treatments = sample["synthesis"]["thermal_treatments"]
    assert [t["label"] for t in treatments] == ["drying", "calcination"]
    for t in treatments:
        assert {"label", "temperature_K", "duration_s"} <= set(t)


def test_every_measured_property_carries_units_and_a_method(sample):
    """This is the side of the M9 join that gets left until too late: 'a rate
    constant correlating with an independently measured catalyst property' needs
    the property to exist here with a number, a unit, and a method."""
    for name, prop in sample["properties"].items():
        assert {"value", "units", "method"} <= set(prop), name


def test_a_property_without_a_method_is_rejected(sample):
    doc = copy.deepcopy(sample)
    doc["properties"]["surface_area"].pop("method")
    assert not validate_sample(doc).ok


def test_a_sample_with_no_properties_warns_about_m9(sample):
    doc = copy.deepcopy(sample)
    doc.pop("properties")
    report = validate_sample(doc)
    assert report.ok, "advisory, not law"
    assert any("M9" in w.message for w in report.warnings)


def test_chemical_identifiers_are_optional_but_defined(sample):
    """The DMSP commits to using them 'when available'. A surface intermediate
    often has no CAS number, so every sub-field is optional."""
    assert sample["identifiers"]["formula"]
    doc = copy.deepcopy(sample)
    doc["identifiers"] = {}
    assert validate_sample(doc).ok


def test_a_bad_cas_number_is_rejected(sample):
    doc = copy.deepcopy(sample)
    doc["synthesis"]["precursors"][0]["identifiers"]["cas"] = "not-a-cas"
    assert not validate_sample(doc).ok


def test_unknown_top_level_fields_are_rejected(sample):
    doc = copy.deepcopy(sample)
    doc["calcination_furnace"] = "tube-3"
    assert not validate_sample(doc).ok, "lab-private fields belong in extensions"


def test_extensions_are_ignored(sample):
    doc = copy.deepcopy(sample)
    doc["extensions"] = {"psu": {"calcination_furnace": "tube-3"}}
    assert validate_sample(doc).ok


# ====================================================================== model


def test_the_model_example_is_valid(model):
    assert validate_model(model).ok


@pytest.mark.parametrize(
    "field",
    ["schema_version", "model_id", "family", "algorithm", "parameters_ref",
     "training_data", "metrics", "access_status", "license"],
)
def test_model_required_fields(model, field):
    doc = copy.deepcopy(model)
    doc.pop(field)
    report = validate_model(doc)
    assert not report.ok
    assert any(field in p.message for p in report.errors)


def test_one_schema_covers_both_ends_of_the_palette(model):
    """A neural ODE and a reduced microkinetic model are described by the same
    fields. Two schemas would mean two report paths and an arbitrary line down the
    middle of a palette whose whole point is that the boundary moves per question."""
    for family, algorithm, interpretable in [
        ("data_driven", "neural-ode", False),
        ("sparse_regression", "reactive-sindy", True),
        ("microkinetic", "reduced-mkm", True),
        ("hybrid", "neural-ode", False),
    ]:
        doc = copy.deepcopy(model)
        doc.update(family=family, algorithm=algorithm, interpretable=interpretable)
        assert validate_model(doc).ok, family


def test_model_id_must_be_content_addressed(model):
    """A retrained model is a new id. A hand-written label could be edited in
    place, and then a published citation would quietly stop being true."""
    doc = copy.deepcopy(model)
    doc["model_id"] = "our-best-model-v2"
    assert not validate_model(doc).ok


def test_training_data_must_enumerate_its_datasets(model):
    """A model whose training data cannot be enumerated cannot be reproduced."""
    doc = copy.deepcopy(model)
    doc["training_data"]["dataset_ids"] = []
    assert not validate_model(doc).ok


def test_parameters_may_be_an_ensemble_reference_or_a_file(model):
    """For a fitted kinetic model the parameters ARE the ensemble; a point
    estimate alone is not a result this project accepts."""
    assert model["parameters_ref"].startswith("art://")
    assert validate_model(model).ok

    doc = copy.deepcopy(model)
    doc["parameters_ref"] = {
        "path": "derived/weights.csv", "sha256": "0" * 64,
        "size_bytes": 1024, "format": "csv",
    }
    assert validate_model(doc).ok


def test_metrics_must_declare_which_split_they_came_from(model):
    """A metric without a split is uninterpretable: train and held-out error are
    different claims."""
    doc = copy.deepcopy(model)
    doc["metrics"]["trace_nrmse"].pop("split")
    assert not validate_model(doc).ok


def test_a_metric_with_no_interval_warns(model):
    """TRACE-AI B3 exists to prevent best-only reporting."""
    doc = copy.deepcopy(model)
    doc["metrics"] = {"rel_error": {"value": 11.8, "units": "%", "split": "held_out"}}
    report = validate_model(doc)
    assert report.ok, "advisory, not law"
    assert any("best-only" in w.message for w in report.warnings)


def test_an_ungrouped_split_warns_loudly(model):
    """For this project's data an ungrouped split is almost always leakage: a
    PRBS trace is autocorrelated and repeated conditions share a lineage."""
    doc = copy.deepcopy(model)
    doc["training_data"]["splits"] = {"strategy": "grouped_random", "grouped_by": ["none"]}
    report = validate_model(doc)
    assert report.ok
    assert any("leakage" in w.message for w in report.warnings)


def test_a_missing_split_strategy_warns(model):
    doc = copy.deepcopy(model)
    doc["training_data"].pop("splits")
    report = validate_model(doc)
    assert report.ok
    assert any("B2" in w.message for w in report.warnings)


def test_split_strategy_is_a_closed_set(model):
    doc = copy.deepcopy(model)
    doc["training_data"]["splits"]["strategy"] = "vibes"
    assert not validate_model(doc).ok


def test_a_model_without_stated_limitations_warns(model):
    """The DMSP requires limits on appropriate use. A model released without them
    gets applied outside them by someone who did not fit it."""
    doc = copy.deepcopy(model)
    doc.pop("limitations")
    report = validate_model(doc)
    assert report.ok
    assert any("limitations" in w.pointer for w in report.warnings)


def test_a_model_without_an_uncertainty_reference_warns(model):
    doc = copy.deepcopy(model)
    doc.pop("uncertainty_ref")
    report = validate_model(doc)
    assert report.ok
    assert any("design" in w.message for w in report.warnings)


def test_identifiability_is_expressible(model):
    """Milestone M9 is stated in terms of IDENTIFIABLE rate constants, so a model
    returning twelve numbers when the data pins four has to be able to say so."""
    ident = model["identifiability"]
    assert ident["identifiable"] and ident["criterion"]
    assert set(ident["identifiable"]).isdisjoint(ident["unidentifiable"])


def test_the_seed_is_recordable(model):
    """The DMSP commits to preserving random seeds where applicable."""
    assert isinstance(model["seed"], int)


# ================================================================ publication


def test_the_publication_example_is_valid(publication):
    assert validate_publication(publication).ok


@pytest.mark.parametrize("field", ["schema_version", "publication_id", "title", "status", "artifacts"])
def test_publication_required_fields(publication, field):
    doc = copy.deepcopy(publication)
    doc.pop(field)
    report = validate_publication(doc)
    assert not report.ok
    assert any(field in p.message for p in report.errors)


def test_a_publication_must_name_what_it_rests_on(publication):
    """A record naming nothing is a bibliography entry, not traceability. The
    DMSP requires each public result be traceable back to the runs, samples,
    calculations, and model versions behind it."""
    doc = copy.deepcopy(publication)
    doc["artifacts"] = []
    assert not validate_publication(doc).ok


def test_every_referenced_artifact_declares_its_role(publication):
    doc = copy.deepcopy(publication)
    doc["artifacts"][0].pop("role")
    assert not validate_publication(doc).ok


def test_roles_are_a_closed_set(publication):
    doc = copy.deepcopy(publication)
    doc["artifacts"][0]["role"] = "vibes"
    assert not validate_publication(doc).ok


def test_acceptance_requires_a_data_availability_statement(publication):
    """By acceptance the statement must exist, because the data it describes is
    due at publication and there is no later moment to discover it does not."""
    for status in ("accepted", "published"):
        doc = copy.deepcopy(publication)
        doc["status"] = status
        doc.pop("data_availability_statement")
        assert not validate_publication(doc).ok, status


def test_drafting_does_not_require_one(publication):
    doc = copy.deepcopy(publication)
    doc["status"] = "drafting"
    doc.pop("data_availability_statement")
    assert validate_publication(doc).ok


def test_publishing_without_a_deposit_warns(publication):
    doc = copy.deepcopy(publication)
    doc["status"] = "published"
    report = validate_publication(doc)
    assert report.ok, "advisory -- the record may be written before deposition completes"
    assert any("no deposit recorded" in w.message for w in report.warnings)


def test_an_unreported_osti_deposit_warns(publication):
    """A reporting obligation that is easy to complete late and impossible to
    notice, so it is a tracked field rather than a memory."""
    doc = copy.deepcopy(publication)
    doc["status"] = "published"
    doc["reproducibility_reviewed"] = True
    doc["deposits"] = [{
        "repository": "Zenodo", "doi": "10.5281/zenodo.9999999",
        "contents": "Figure data", "osti_reported": False,
    }]
    doc["artifacts"].append({"ref": "x", "kind": "external", "role": "figure"})
    report = validate_publication(doc)
    assert report.ok
    assert any("OSTI" in w.message for w in report.warnings)


def test_a_fully_released_publication_has_no_warnings(publication):
    """The state the release gate is aiming at."""
    doc = copy.deepcopy(publication)
    doc.update(
        status="published",
        doi="10.1021/example.6c00000",
        reproducibility_reviewed=True,
        reproducibility_reviewer="A. Example",
        deposits=[{
            "repository": "Zenodo", "doi": "10.5281/zenodo.9999999",
            "contents": "Underlying data for Figures 1-3", "license": "CC-BY-4.0",
            "deposited_at": "2027-06-01T00:00:00Z", "osti_reported": True,
        }],
    )
    doc["artifacts"].append({
        "ref": "prbs-co-ox-synthetic-001", "kind": "dataset",
        "role": "figure", "locator": "Figure 1",
    })
    report = validate_publication(doc)
    assert report.ok
    assert not report.warnings, [str(w) for w in report.warnings]


def test_a_bad_doi_is_rejected(publication):
    doc = copy.deepcopy(publication)
    doc["doi"] = "https://doi.org/10.1021/example"
    assert not validate_publication(doc).ok, "DOIs are stored bare, without a resolver prefix"


def test_trace_ai_gaps_are_expressible(publication):
    """A generated checklist must report what it could not substantiate. An
    absence laundered into 'N-A' is worse than an empty checklist."""
    assert publication["trace_ai_checklist"]["gaps"]
