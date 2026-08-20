"""The examples must be true, not merely well-formed.

An example with a plausible-looking checksum is worse than no example: it
teaches the shape while quietly demonstrating that nobody checks the content.
These tests verify the manifest indirection end to end against real bytes.
"""

from __future__ import annotations

import json

import pytest

from tcat_standard import (
    ManifestEntry,
    is_valid_artifact_id,
    sha256_file,
    validate_calibration,
    validate_dataset,
    validate_protocol,
)

EXAMPLE_KINDS = {
    "dataset-prbs-co-ox.json": validate_dataset,
    "calibration-fixed.json": validate_calibration,
    "protocol-prbs.json": validate_protocol,
}


@pytest.mark.parametrize("name,validator", EXAMPLE_KINDS.items())
def test_examples_validate(examples_dir, name, validator):
    doc = json.loads((examples_dir / name).read_text(encoding="utf-8"))
    report = validator(doc, source=name)
    assert report.ok, report.render()


def test_example_checksum_is_the_real_checksum(examples_dir):
    """The manifest indirection, verified. If this fails, either the CSV was
    regenerated without regenerating the JSON, or the two were never consistent."""
    doc = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    entry = ManifestEntry.from_dict(doc["files"][0])
    target = examples_dir.parent / entry.path
    assert target.is_file(), f"{entry.path} does not exist"
    assert entry.sha256 == sha256_file(target)
    assert entry.size_bytes == target.stat().st_size
    assert entry.verify(examples_dir.parent)


def test_example_row_count_matches_the_file(examples_dir):
    doc = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    entry = ManifestEntry.from_dict(doc["files"][0])
    lines = (examples_dir.parent / entry.path).read_text(encoding="utf-8").splitlines()
    assert entry.rows == len(lines) - 1


def test_declared_channels_match_the_csv_header(examples_dir):
    """A canonical file whose columns disagree with its declared channels is the
    exact failure the channels object exists to prevent."""
    doc = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    entry = ManifestEntry.from_dict(doc["files"][0])
    header = (examples_dir.parent / entry.path).read_text(encoding="utf-8").splitlines()[0]
    columns = set(header.split(","))

    for name, channel in doc["channels"].items():
        assert name in columns, f"channel {name} is declared but absent from the CSV"
        unc = channel["uncertainty"]
        if unc["kind"] == "sigma_column":
            assert unc["column"] in columns, f"sigma column {unc['column']} is absent from the CSV"


def test_calibration_channels_cover_the_datasets_signal_channels(examples_dir):
    """The join that makes tcat-calibrate possible: every signal channel the
    dataset carries must have a sensitivity in the cited calibration."""
    dataset = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    cal = json.loads((examples_dir / "calibration-fixed.json").read_text(encoding="utf-8"))

    signal = {n for n, c in dataset["channels"].items() if c["quantity"] == "ion_current"}
    calibrated = set(cal["entries"][0]["channels"])
    assert signal <= calibrated, f"uncalibrated signal channels: {signal - calibrated}"


def test_dataset_cites_the_example_calibration(examples_dir):
    dataset = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    cal = json.loads((examples_dir / "calibration-fixed.json").read_text(encoding="utf-8"))
    assert dataset["calibration_ref"] == f"art://{cal['calibration_id']}"


def test_example_artifact_ids_are_well_formed(examples_dir):
    cal = json.loads((examples_dir / "calibration-fixed.json").read_text(encoding="utf-8"))
    dataset = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    assert is_valid_artifact_id(cal["calibration_id"])
    assert is_valid_artifact_id(dataset["provenance"]["artifact_id"])
    assert is_valid_artifact_id(dataset["calibration_ref"])


def test_the_protocol_in_the_dataset_matches_the_standalone_protocol(examples_dir):
    """The designed thing and the run thing are the same representation. If these
    ever diverge, the closed loop has two formats to reconcile."""
    dataset = json.loads((examples_dir / "dataset-prbs-co-ox.json").read_text(encoding="utf-8"))
    standalone = json.loads((examples_dir / "protocol-prbs.json").read_text(encoding="utf-8"))
    assert dataset["protocol"] == standalone


def test_the_prbs_sequence_is_regenerable_from_recorded_parameters(examples_dir):
    """The reason register_length, taps, and seed are required: the waveform must
    be reconstructible from metadata alone, not inferred back out of the trace."""
    import sys

    sys.path.insert(0, str(examples_dir))
    from make_examples import lfsr_sequence

    params = json.loads((examples_dir / "protocol-prbs.json").read_text(encoding="utf-8"))["parameters"]
    seq = lfsr_sequence(params["register_length"], params["taps"], params["seed"], params["n_bits"])

    assert len(seq) == params["n_bits"]
    assert set(seq) == {0, 1}
    # A maximal-length LFSR visits every non-zero state exactly once per period,
    # so a full period is balanced to within one bit.
    assert abs(sum(seq) - params["n_bits"] // 2) <= 1
