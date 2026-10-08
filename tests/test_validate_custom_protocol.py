"""Schema 0.8.0: a `custom` protocol, for experiments no named protocol describes.

The named protocols all perturb a gas feed. A potential step, an impedance
measurement or a cooling profile could only be recorded by mislabelling it,
which is worse than refusing it. `custom` admits them and keeps the one
obligation every named protocol meets: the perturbation can be reconstructed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tcat_data import validate_dataset
from tcat_data.validate import validate

DATA = Path(__file__).resolve().parent / "data"

POTENTIAL_STEP = {
    "protocol": "custom",
    "parameters": {
        "name": "echem.potential-step",
        "description": "Working-electrode potential stepped from open circuit to -0.4 V vs Ag/AgCl and held for 60 s.",
        "inputs": [{"quantity": "potential", "units": "V vs Ag/AgCl", "channel": "m28"}],
    },
    "base_conditions": {"temperature_K": 298.15, "electrolyte": "0.1 M KHCO3", "pH": 6.8},
}


def _dataset(protocol: dict) -> dict:
    doc = json.loads((DATA / "dataset-valid.json").read_text(encoding="utf-8"))
    doc["protocol"] = copy.deepcopy(protocol)
    return doc


def test_an_electrochemical_step_is_a_valid_custom_protocol_with_no_pressure():
    report = validate_dataset(_dataset(POTENTIAL_STEP))
    assert report.ok, report.render()


def test_a_programmed_schedule_stands_in_for_a_recorded_channel():
    cooling = copy.deepcopy(POTENTIAL_STEP)
    cooling["parameters"] = {
        "name": "linear-cooling",
        "description": "Batch cooled linearly from 333 K to 293 K at 0.5 K/min, then held for one hour.",
        "inputs": [{"quantity": "temperature", "units": "K",
                    "schedule": [{"duration_s": 4800, "from": 333, "to": 293},
                                 {"duration_s": 3600, "from": 293, "to": 293, "label": "hold"}]}],
    }
    assert validate(cooling, "protocol").ok


def test_an_input_with_neither_channel_nor_schedule_is_named():
    doc = copy.deepcopy(POTENTIAL_STEP)
    del doc["parameters"]["inputs"][0]["channel"]
    report = validate(doc, "protocol")
    assert not report.ok
    assert any(p.pointer == "/parameters/inputs/0" and "`channel`" in p.message for p in report.errors), report.render()


def test_an_input_channel_must_exist_in_the_dataset_that_embeds_it():
    doc = copy.deepcopy(POTENTIAL_STEP)
    doc["parameters"]["inputs"][0]["channel"] = "applied_potential"
    report = validate_dataset(_dataset(doc))
    assert not report.ok
    assert any(p.pointer == "/protocol/parameters/inputs/0/channel" for p in report.errors), report.render()


@pytest.mark.parametrize("field", ["name", "description", "inputs"])
def test_a_custom_protocol_must_name_describe_and_list_its_inputs(field):
    doc = copy.deepcopy(POTENTIAL_STEP)
    del doc["parameters"][field]
    assert not validate(doc, "protocol").ok


def test_temperature_is_still_required():
    doc = copy.deepcopy(POTENTIAL_STEP)
    del doc["base_conditions"]["temperature_K"]
    assert not validate(doc, "protocol").ok


def test_a_gas_phase_record_still_validates_unchanged():
    """Additive: the PRBS example means under 0.8.0 what it meant under 0.7.0."""
    doc = json.loads((DATA / "dataset-valid.json").read_text(encoding="utf-8"))
    assert validate_dataset(doc).ok
