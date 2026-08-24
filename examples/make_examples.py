#!/usr/bin/env python3
"""Regenerate the example documents, with real data and real checksums.

The examples are not hand-written JSON with plausible-looking hashes. They point
at a synthetic CSV that this script generates, and their checksums are computed
from it -- so ``tcat-validate`` passing on them means something, and a reader can
verify the manifest indirection end to end rather than taking it on faith.

The trace is SYNTHETIC. It is a toy first-order response to a real LFSR-generated
PRBS sequence, standing in for the PSU CO-oxidation dataset that the pipeline
will bootstrap on. Nothing here is measured data and nothing here should be used
to draw a conclusion about a catalyst.

Run:  python examples/make_examples.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from tcat_standard import ManifestEntry, make_artifact_id

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATA = HERE / "data"

# ---------------------------------------------------------------- PRBS

REGISTER_LENGTH = 7
TAPS = [7, 6]          # x^7 + x^6 + 1, a maximal-length LFSR
SEED = 1
BIT_PERIOD_S = 2.0
N_BITS = 127           # 2**7 - 1: one full period
DT_S = 0.05            # 40 samples per bit
LOW_MOL_FRAC = 0.005
HIGH_MOL_FRAC = 0.020


def lfsr_sequence(register_length: int, taps: list[int], seed: int, n_bits: int) -> list[int]:
    """Maximal-length LFSR bit sequence.

    Written out rather than imported so the example has no hidden dependency and
    so the sequence is reproducible from the recorded (register_length, taps,
    seed) triple alone -- which is exactly what the protocol schema requires be
    recorded, and why it requires it.
    """
    state = [(seed >> i) & 1 for i in range(register_length)]
    if not any(state):
        raise ValueError("LFSR seed must be non-zero")
    out = []
    for _ in range(n_bits):
        out.append(state[-1])
        fb = 0
        for t in taps:
            fb ^= state[t - 1]
        state = [fb] + state[:-1]
    return out


def synthetic_trace() -> list[tuple[float, float, float, float]]:
    """A toy response: CO tracks the inlet with lag, O2 and CO2 respond in kind.

    Two first-order lags with different time constants, which is enough to make
    the trace look like transient data without pretending to be a mechanism.
    """
    rng = random.Random(20260820)
    bits = lfsr_sequence(REGISTER_LENGTH, TAPS, SEED, N_BITS)

    tau_co = 1.4      # s, gas-phase mixing + detector
    tau_co2 = 3.2     # s, slower: surface reservoir
    n = int(N_BITS * BIT_PERIOD_S / DT_S)

    # Sensitivities are arbitrary-but-fixed; they exist so the CSV is in amperes
    # (a raw ion current) rather than in mole fraction, which is the whole point.
    s_co, s_o2, s_co2 = 1.10e-9, 8.4e-10, 1.24e-9

    rows = []
    x_co = LOW_MOL_FRAC
    x_co2 = 0.0
    for i in range(n):
        t = i * DT_S
        bit = bits[min(int(t / BIT_PERIOD_S), N_BITS - 1)]
        inlet = HIGH_MOL_FRAC if bit else LOW_MOL_FRAC

        x_co += (inlet - x_co) * (DT_S / tau_co)
        conversion = 0.35 * x_co / (x_co + 0.004)      # toy saturating rate
        target_co2 = conversion * x_co
        x_co2 += (target_co2 - x_co2) * (DT_S / tau_co2)
        x_o2 = 0.05 - 0.5 * x_co2

        def noisy(x: float, sens: float, rel: float) -> float:
            base = x * sens
            return base * (1.0 + rng.gauss(0.0, rel)) + rng.gauss(0.0, 2e-13)

        rows.append(
            (
                round(t, 4),
                noisy(x_co, s_co, 0.012),
                noisy(x_o2, s_o2, 0.008),
                noisy(x_co2, s_co2, 0.020),
            )
        )
    return rows


def write_csv() -> Path:
    """Write the canonical CSV: time, three ion currents, three sigma columns."""
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "prbs-co-ox-synthetic.csv"
    rows = synthetic_trace()

    # Per-point sigma. Declared as sigma_column in the dataset, so a reader never
    # has to guess whether uncertainty is absolute, relative, or absent.
    lines = ["time_s,m28,m28_sigma,m32,m32_sigma,m44,m44_sigma"]
    for t, m28, m32, m44 in rows:
        lines.append(
            f"{t:.4f},{m28:.6e},{abs(m28) * 0.012 + 2e-13:.6e},"
            f"{m32:.6e},{abs(m32) * 0.008 + 2e-13:.6e},"
            f"{m44:.6e},{abs(m44) * 0.020 + 2e-13:.6e}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- documents

T0 = "2026-09-01T14:03:00Z"


def build_protocol(n_samples: int) -> dict:
    return {
        "protocol": "prbs",
        "parameters": {
            "species": "CO",
            "low_mol_frac": LOW_MOL_FRAC,
            "high_mol_frac": HIGH_MOL_FRAC,
            "waveform": {
                "form": "lfsr",
                "register_length": REGISTER_LENGTH,
                "taps": TAPS,
                "seed": SEED,
                "bit_period_s": BIT_PERIOD_S,
                "n_bits": N_BITS,
            },
        },
        "base_conditions": {
            "temperature_K": 473.0,
            "pressure_kPa": 101.3,
            "total_flow_sccm": 100.0,
            "carrier": "He",
            "feed_mol_frac": {"O2": 0.05, "He": 0.93},
            "catalyst_mass_g": 0.0502,
        },
        "time_base": {"t0": T0, "dt_s": DT_S, "n_samples": n_samples},
        "notes": (
            "SYNTHETIC. Maximal-length LFSR, one full 127-bit period, declared under "
            "the lfsr waveform form: register length, taps, and seed are recorded so "
            "the waveform can be regenerated exactly rather than re-measured from the "
            "trace. Real legacy runs often cannot do this -- see the recorded and "
            "reconstructed forms."
        ),
    }


def build_calibration() -> dict:
    cal_id = make_artifact_id(
        tool="cal",
        name="msq1-synthetic",
        when="2026-09-01",
        tool_name="tcat-calibrate",
        tool_version="0.1.0",
        inputs=[],
        parameters={"source": "synthetic-example", "instrument": "MS-Q1-SYNTH"},
    )
    return {
        "calibration_id": cal_id,
        "schema_version": "0.1.0",
        "instrument": {"model": "Synthetic quadrupole MS", "identifier": "MS-Q1-SYNTH", "site": "gt"},
        "kind": "ms_sensitivity",
        "owner": "example",
        "entries": [
            {
                "valid_from": "2026-09-01T09:00:00Z",
                "channels": {
                    "m28": {"sensitivity": 1.10e-9, "sensitivity_sigma": 2.8e-11,
                            "units": "A/(mol/m^3)", "mz": 28, "species": "CO"},
                    "m32": {"sensitivity": 8.40e-10, "sensitivity_sigma": 2.1e-11,
                            "units": "A/(mol/m^3)", "mz": 32, "species": "O2"},
                    "m44": {"sensitivity": 1.24e-9, "sensitivity_sigma": 3.1e-11,
                            "units": "A/(mol/m^3)", "mz": 44, "species": "CO2"},
                },
            }
        ],
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "SYNTHETIC, single-entry. A fixed calibration is the degenerate case of a "
            "time-indexed one, so it is stored in the general shape: the day someone "
            "supplies a before/after bracket, a second entry is appended and no "
            "consuming code changes. m/z 28 has no CO2 fragmentation correction here; "
            "real MS work needs a fragmentation matrix, cited as its own artifact."
        ),
    }


def build_dataset(entry: ManifestEntry, protocol: dict, cal_id: str) -> dict:
    def channel(units, quantity, sigma_col, mz=None, species=None, family="gaussian_heteroscedastic"):
        ch = {
            "units": units,
            "quantity": quantity,
            "uncertainty": {
                "kind": "sigma_column",
                "column": sigma_col,
                "noise_model": {
                    "family": family,
                    "notes": "Synthetic: relative detector noise plus a constant floor.",
                },
            },
        }
        if mz is not None:
            ch["mz"] = mz
        if species is not None:
            ch["species"] = species
        return ch

    return {
        "schema_version": "0.1.0",
        "dataset_id": "prbs-co-ox-synthetic-001",
        "batch_id": "synthetic-batch-a",
        "lineage_id": "synthetic-co-ox-lineage",
        "layer": "canonical",
        "status": "ok",
        "autonomy_level": "A1",
        "measurement_type": "prbs_kinetics",
        "sample_id": "SYNTH-CATALYST-001",
        "instrument": {
            "model": "Synthetic quadrupole MS on synthetic PRBS reactor",
            "identifier": "MS-Q1-SYNTH",
            "site": "gt",
        },
        "channels": {
            "time_s": {
                "units": "s",
                "quantity": "time",
                "uncertainty": {
                    "kind": "constant_sigma",
                    "value": 0.001,
                    "noise_model": {"family": "calibrated_estimate", "notes": "Sampling jitter."},
                },
            },
            "m28": channel("A", "ion_current", "m28_sigma", 28, "CO"),
            "m32": channel("A", "ion_current", "m32_sigma", 32, "O2"),
            "m44": channel("A", "ion_current", "m44_sigma", 44, "CO2"),
        },
        "files": [entry.to_dict()],
        "protocol": protocol,
        "time_base": protocol["time_base"],
        "access_status": "public",
        "license": "CC-BY-4.0",
        "provenance": {
            "artifact_id": make_artifact_id(
                # `canon`, not `conc`: tcat-ingest emits a CANONICAL artifact.
                # `conc` is tcat-calibrate's prefix, and using it here described an
                # ingest record as though a calibration had been applied.
                tool="canon",
                name="prbs-co-ox-synthetic",
                when="2026-09-01",
                tool_name="tcat-ingest",
                tool_version="0.1.0",
                inputs=[],
                parameters={"converter": "ms-csv", "source": "examples/make_examples.py"},
            ),
            "tool": {"name": "tcat-ingest", "version": "0.1.0", "git_sha": "unknown"},
            "inputs": [],
            "parameters": {"converter": "ms-csv", "source": "examples/make_examples.py"},
            "data_schema_version": "0.1.0",
            "autonomy_level": "A1",
            "durability": "durable",
            "created_at": "2026-09-01T14:20:11Z",
            "host": "example-generator",
            "notes": "Generated by examples/make_examples.py, not by a real tool run.",
        },
        "calibration_ref": f"art://{cal_id}",
        "reaction_system": "CO oxidation",
        "catalyst_family": "synthetic",
        "funding": [
            {"funder": "US Department of Energy", "award": "DE-FOA-0003612", "program": "Genesis Mission"}
        ],
        "notes": (
            "SYNTHETIC EXEMPLAR -- not measured data. Exists so that every required "
            "field has a worked, checkable value, and so the manifest indirection can "
            "be verified end to end: the sha256 below is the real checksum of "
            "examples/data/prbs-co-ox-synthetic.csv. Layer is canonical because the "
            "channels are ion currents with explicit units and per-point sigma; it is "
            "NOT derived, because no calibration has been applied -- calibration_ref "
            "records which calibration would apply, not one that has been used."
        ),
    }


SAMPLE_ID = "SYNTH-CATALYST-001"


def build_sample() -> dict:
    """A synthetic catalyst sample, with every field a real one would carry.

    Shaped after supported vanadium oxide because that is the Phase I system, but
    the numbers are invented. It exists so that the M9 join -- a fitted rate
    constant against an independently measured property -- has a worked example of
    the property side, which is the side that is easy to leave until too late.
    """
    return {
        "schema_version": "0.1.0",
        "sample_id": SAMPLE_ID,
        "status": "ok",
        "catalyst_family": "synthetic supported oxide",
        "identifiers": {"formula": "VOx/SiO2"},
        "composition": {
            "nominal": {"V": {"value": 3.0, "units": "wt%"}},
            "measured": {
                "V": {"value": 2.84, "sigma": 0.09, "units": "wt%", "method": "XRF"}
            },
            "support": "SiO2",
        },
        "synthesis": {
            "method": "incipient wetness impregnation",
            "precursors": [
                {
                    "name": "ammonium metavanadate",
                    "identifiers": {"formula": "NH4VO3", "cas": "7803-55-6"},
                    "supplier": "SYNTHETIC",
                    "lot": "SYNTHETIC-LOT-A",
                    "purity": "99.9%",
                },
                {"name": "silica gel", "identifiers": {"formula": "SiO2"}, "supplier": "SYNTHETIC"},
            ],
            "thermal_treatments": [
                {"label": "drying", "temperature_K": 373.0, "duration_s": 43200, "atmosphere": "air"},
                {
                    "label": "calcination",
                    "temperature_K": 823.0,
                    "ramp_K_per_min": 2.0,
                    "duration_s": 14400,
                    "atmosphere": "air",
                    "flow_sccm": 50.0,
                },
            ],
            "date": "2026-08-25T10:00:00Z",
            "notes": "SYNTHETIC. No such sample exists.",
        },
        "properties": {
            "surface_area": {
                "value": 212.0, "sigma": 4.0, "units": "m^2/g",
                "method": "BET N2 physisorption",
            },
            "reducibility_T_max": {
                "value": 723.0, "sigma": 8.0, "units": "K", "method": "H2-TPR",
                "notes": "The kind of property milestone M9 correlates a rate constant against.",
            },
            "v_surface_density": {
                "value": 2.3, "sigma": 0.2, "units": "V/nm^2", "method": "XRF + BET",
            },
        },
        "characterization": [
            {"technique": "XRF", "summary": "2.84 wt% V, no crystalline V2O5 detected."},
            {"technique": "N2 physisorption", "summary": "212 m^2/g, type IV isotherm."},
        ],
        "batch_id": "synthetic-batch-a",
        "quantity_g": 2.5,
        "location": "gt",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "funding": [
            {"funder": "US Department of Energy", "award": "DE-FOA-0003612", "program": "Genesis Mission"}
        ],
        "project": "genesis-prbs-phase-1",
        "notes": (
            "SYNTHETIC EXEMPLAR. Stored at ambient in a sealed vial; no pretreatment "
            "beyond the calcination recorded above. Present so every field of the "
            "sample schema has a worked value."
        ),
    }


def build_model(ensemble_ref: str, dataset_id: str) -> dict:
    """A synthetic fitted model, with metrics phrased the way a milestone is.

    The metrics carry intervals on purpose: TRACE-AI B3 exists to prevent
    best-only reporting, and an example without intervals would teach the
    opposite of the rule.
    """
    model_id = make_artifact_id(
        tool="model",
        name="lh-two-site-synthetic",
        when="2026-09-01",
        tool_name="tcat-fit",
        tool_version="0.1.0",
        inputs=[],
        parameters={"algorithm": "lh-two-site", "source": "synthetic-example"},
    )
    return {
        "schema_version": "0.1.0",
        "model_id": model_id,
        "family": "microkinetic",
        "algorithm": "lh-two-site",
        "interpretable": True,
        "description": (
            "SYNTHETIC. Two-site Langmuir-Hinshelwood model, fit to the synthetic "
            "PRBS trace. Present so the model schema has a worked example; the "
            "numbers are invented and describe no real catalyst."
        ),
        "architecture": {
            "summary": "Two site types, competitive adsorption, one surface reaction.",
            "n_parameters": 3,
            "n_species": 3,
            "n_reactions": 3,
        },
        "hyperparameters": {
            "solver": "radau",
            "rtol": 1e-8,
            "atol": 1e-10,
            "parameter_transform": "log10",
        },
        "seed": 20260820,
        "features": [
            {"name": "m28_conc", "units": "mol/m^3", "quantity": "concentration", "source": "m28"},
            {"name": "m32_conc", "units": "mol/m^3", "quantity": "concentration", "source": "m32"},
            {"name": "m44_conc", "units": "mol/m^3", "quantity": "concentration", "source": "m44"},
        ],
        "parameters_ref": f"art://{ensemble_ref}",
        "uncertainty_ref": f"art://{ensemble_ref}",
        "training_data": {
            "dataset_ids": [dataset_id],
            "sample_ids": [SAMPLE_ID],
            "n_observations": 5080,
            "splits": {
                "strategy": "leave_one_batch_out",
                "grouped_by": ["batch_id"],
                "train": ["synthetic-batch-a"],
                "test": ["synthetic-batch-b"],
                "seed": 20260820,
                "notes": (
                    "Grouped by batch so no batch spans the split. Ungrouped splitting "
                    "of this data leaks: a PRBS trace is autocorrelated and repeated "
                    "conditions share a lineage."
                ),
            },
        },
        "metrics": {
            "steady_state_rate_rel_error": {
                "value": 11.8, "units": "%", "split": "held_out",
                "interval": [8.4, 15.9], "interval_kind": "95% CI", "n": 6,
                "notes": "SYNTHETIC. Milestone M3 target is <= 15%.",
            },
            "trace_nrmse": {
                "value": 0.041, "units": "1", "split": "test",
                "interval": [0.033, 0.052], "interval_kind": "95% CI", "n": 6,
            },
        },
        "identifiability": {
            "identifiable": ["log10_k_rxn"],
            "unidentifiable": ["log10_k_ads", "log10_k_des"],
            "criterion": "profile likelihood",
            "notes": (
                "SYNTHETIC. Adsorption and desorption are correlated along a flat "
                "direction here, which is the normal situation and the reason M9 is "
                "worded in terms of IDENTIFIABLE constants."
            ),
        },
        "limitations": (
            "SYNTHETIC MODEL -- not usable for any real prediction. Even taken on its "
            "own terms it was fit at a single temperature (473 K), on one synthetic "
            "sample, under PRBS forcing only. It has not been validated on "
            "chemical-looping operation, on any temperature ramp, or on any other "
            "catalyst, and only one of its three rate constants is identifiable."
        ),
        "software": {
            "name": "tcat-analysis",
            "repository": "https://github.com/TransientCatalysis/tcat-analysis",
            "version": "0.1.0",
            "license": "MIT",
        },
        "example_use": "examples/worked_example.py",
        "autonomy_level": "A1",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "project": "genesis-prbs-phase-1",
        "objective": {"label": "1b-mechanism", "milestone": "M9"},
        "notes": "Generated by examples/make_examples.py. No solve was performed.",
    }


def build_publication(dataset_id: str, model_id: str) -> dict:
    """A synthetic publication record, showing the traceability direction.

    Status is deliberately `drafting`: an example in `published` state would need
    real deposits and DOIs, and inventing those is exactly the kind of
    plausible-looking fiction this project's examples avoid.
    """
    return {
        "schema_version": "0.1.0",
        "publication_id": "0000-example-synthetic-prbs-worked-example",
        "title": "SYNTHETIC EXAMPLE -- not a real manuscript",
        "authors": ["Example, A."],
        "status": "drafting",
        "artifacts": [
            {"ref": dataset_id, "kind": "dataset", "role": "underlying_data",
             "locator": "Figure 1", "notes": "The PRBS trace itself."},
            {"ref": SAMPLE_ID, "kind": "sample", "role": "supporting",
             "notes": "Catalyst the trace was measured on."},
            {"ref": model_id, "kind": "model", "role": "model", "locator": "Figure 2"},
            {"ref": "tcat-analysis", "kind": "external", "role": "software",
             "notes": "Analysis code; a release DOI would go in `software` below."},
        ],
        "data_availability_statement": (
            "SYNTHETIC. Drafted here rather than written from memory at submission, so "
            "that what it promises can be checked against what is actually registered."
        ),
        "software": [
            {
                "name": "tcat-analysis",
                "repository": "https://github.com/TransientCatalysis/tcat-analysis",
                "version": "0.1.0",
                "license": "MIT",
            }
        ],
        "trace_ai_checklist": {"checklist_version": "2.2.0", "gaps": [
            "Sections B and C are not substantiable for a synthetic example."
        ]},
        "funding": [
            {"funder": "US Department of Energy", "award": "DE-FOA-0003612", "program": "Genesis Mission"}
        ],
        "project": "genesis-prbs-phase-1",
        "notes": "Generated by examples/make_examples.py. Not a real manuscript.",
    }


def main() -> None:
    csv_path = write_csv()
    entry = ManifestEntry.from_file(csv_path, repo_root=REPO, format="csv", media_type="text/csv")

    protocol = build_protocol(entry.rows or 0)
    calibration = build_calibration()
    dataset = build_dataset(entry, protocol, calibration["calibration_id"])

    # A synthetic ensemble id, so the model example can cite something well-formed.
    ensemble_ref = make_artifact_id(
        tool="fit", name="prbs-co-ox-synthetic", when="2026-09-01",
        tool_name="tcat-fit", tool_version="0.1.0", inputs=[],
        parameters={"model": "lh-two-site", "method": "laplace"},
    )
    sample = build_sample()
    model = build_model(ensemble_ref, dataset["dataset_id"])
    publication = build_publication(dataset["dataset_id"], model["model_id"])

    for name, doc in (
        ("dataset-prbs-co-ox.json", dataset),
        ("calibration-fixed.json", calibration),
        ("protocol-prbs.json", protocol),
        ("sample-synthetic.json", sample),
        ("model-lh-two-site.json", model),
        ("publication-example.json", publication),
    ):
        (HERE / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote examples/{name}")

    print(f"wrote examples/data/{csv_path.name}  "
          f"({entry.rows} rows, {entry.size_bytes} bytes, sha256 {entry.sha256[:12]}...)")


if __name__ == "__main__":
    main()
