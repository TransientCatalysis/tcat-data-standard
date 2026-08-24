#!/usr/bin/env python3
"""Generate the test fixtures by mutating the valid example.

Deriving the invalid fixtures from the valid one is deliberate: a hand-written
invalid fixture drifts out of sync with the schema and starts failing for the
wrong reason, which is worse than not testing at all -- the test still goes red,
so nobody notices it stopped testing what it claimed to.

Run:  python tests/make_fixtures.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
EXAMPLE = HERE.parent / "examples" / "dataset-prbs-co-ox.json"

#: Every field the dataset schema requires. One fixture per field, each with that
#: single field removed, so a failure names exactly one thing.
REQUIRED = [
    "schema_version", "dataset_id", "batch_id", "lineage_id", "layer", "status",
    "autonomy_level", "measurement_type", "sample_id", "instrument", "channels",
    "files", "access_status", "license", "provenance",
]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    base = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    # The valid baseline, copied so tests do not depend on examples/ staying put.
    (DATA / "dataset-valid.json").write_text(json.dumps(base, indent=2) + "\n")

    for field in REQUIRED:
        doc = copy.deepcopy(base)
        doc.pop(field, None)
        (DATA / f"dataset-missing-{field.replace('_', '-')}.json").write_text(
            json.dumps(doc, indent=2) + "\n"
        )

    # --- one fixture per rule that is not just "a field is absent" -----------

    # extensions must be IGNORED, not rejected. This is the escape hatch that
    # keeps labs recording things the schema has not caught up with.
    doc = copy.deepcopy(base)
    doc["extensions"] = {
        "psu": {"reactor_conditioning_cycles": 3, "mfc_calibration_date": "2026-08-30"},
        "bnl": {"proposal_id": "GU-999999", "ring_current_mA": 398.2},
    }
    (DATA / "dataset-with-extensions.json").write_text(json.dumps(doc, indent=2) + "\n")

    # An unknown TOP-LEVEL field must be rejected. That is the point of having a
    # designated extensions namespace: typos and private conventions land there
    # on purpose, not by accident at the top level.
    doc = copy.deepcopy(base)
    doc["reactor_conditioning_cycles"] = 3
    (DATA / "dataset-unknown-toplevel.json").write_text(json.dumps(doc, indent=2) + "\n")

    # status flagged with no reason: 'flag, never delete' is only useful if the
    # flag says why.
    doc = copy.deepcopy(base)
    doc["status"] = "flagged"
    (DATA / "dataset-flagged-no-reason.json").write_text(json.dumps(doc, indent=2) + "\n")

    doc = copy.deepcopy(base)
    doc["status"] = "flagged"
    doc["status_reason"] = "MFC drift suspected after 40 min; trace retained for the record."
    (DATA / "dataset-flagged-with-reason.json").write_text(json.dumps(doc, indent=2) + "\n")

    # An experimental modality with no protocol cannot be reproduced.
    doc = copy.deepcopy(base)
    doc.pop("protocol", None)
    (DATA / "dataset-experimental-no-protocol.json").write_text(json.dumps(doc, indent=2) + "\n")

    # ...but a computational dataset legitimately has none.
    doc = copy.deepcopy(base)
    doc.pop("protocol", None)
    doc.pop("time_base", None)
    doc["measurement_type"] = "computational"
    (DATA / "dataset-computational-no-protocol.json").write_text(json.dumps(doc, indent=2) + "\n")

    # A channel with a unit but no uncertainty. Impossible to express, which is
    # exactly why units and uncertainty are per-channel rather than in two
    # parallel maps that can drift apart.
    doc = copy.deepcopy(base)
    doc["channels"]["m44"].pop("uncertainty")
    (DATA / "dataset-channel-no-uncertainty.json").write_text(json.dumps(doc, indent=2) + "\n")

    # sigma_column kind without naming the column.
    doc = copy.deepcopy(base)
    doc["channels"]["m44"]["uncertainty"].pop("column")
    (DATA / "dataset-sigma-column-unnamed.json").write_text(json.dumps(doc, indent=2) + "\n")

    # Two location forms on one manifest entry defeats the indirection: a
    # consumer would not know which one is authoritative.
    doc = copy.deepcopy(base)
    doc["files"][0]["url"] = "https://example.org/prbs-co-ox-synthetic.csv"
    (DATA / "dataset-two-locations.json").write_text(json.dumps(doc, indent=2) + "\n")

    # An absolute path, and a path escaping the repository.
    doc = copy.deepcopy(base)
    doc["files"][0]["path"] = "/absolute/prbs.csv"
    (DATA / "dataset-absolute-path.json").write_text(json.dumps(doc, indent=2) + "\n")

    doc = copy.deepcopy(base)
    doc["files"][0]["path"] = "../elsewhere/prbs.csv"
    (DATA / "dataset-escaping-path.json").write_text(json.dumps(doc, indent=2) + "\n")

    # An instrument-native blob past the raw layer: convert at ingestion, never
    # carry the blob forward.
    doc = copy.deepcopy(base)
    doc["files"][0]["format"] = "instrument-native"
    (DATA / "dataset-canonical-native-blob.json").write_text(json.dumps(doc, indent=2) + "\n")

    doc = copy.deepcopy(base)
    doc["layer"] = "raw"
    doc["files"][0]["format"] = "instrument-native"
    (DATA / "dataset-raw-native-blob.json").write_text(json.dumps(doc, indent=2) + "\n")

    # Bad autonomy level: A6 does not exist; A5 is the top of the TRACE-AI scale.
    doc = copy.deepcopy(base)
    doc["autonomy_level"] = "A6"
    (DATA / "dataset-bad-autonomy.json").write_text(json.dumps(doc, indent=2) + "\n")

    # A naive local timestamp. Three institutions in two time zones plus a
    # synchrotron cannot align transients on a wall clock.
    doc = copy.deepcopy(base)
    doc["time_base"]["t0"] = "2026-09-01 14:03:00"
    doc["protocol"]["time_base"]["t0"] = "2026-09-01 14:03:00"
    (DATA / "dataset-naive-timestamp.json").write_text(json.dumps(doc, indent=2) + "\n")

    # An lfsr waveform with no seed: the sequence becomes unreproducible.
    doc = copy.deepcopy(base)
    doc["protocol"]["parameters"]["waveform"].pop("seed")
    (DATA / "dataset-prbs-no-seed.json").write_text(json.dumps(doc, indent=2) + "\n")

    # A waveform with no form. Without the discriminator nothing says which
    # fields are authoritative, so the reader cannot tell a generator spec from
    # an executed schedule.
    doc = copy.deepcopy(base)
    doc["protocol"]["parameters"]["waveform"].pop("form")
    (DATA / "dataset-prbs-waveform-formless.json").write_text(json.dumps(doc, indent=2) + "\n")

    written = sorted(p.name for p in DATA.glob("*.json"))
    print(f"wrote {len(written)} fixtures to tests/data/")
    for name in written:
        print(f"  {name}")


if __name__ == "__main__":
    main()
