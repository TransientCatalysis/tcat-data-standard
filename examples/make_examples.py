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
            "bed": {
                "length_mm": 10.0,
                "diameter_mm": 4.0,
                "void_fraction": 0.60,
                "particle_diameter_um": 100.0,
                "catalyst_density_kg_per_m3": 2000.0,
                "site_density_umol_per_g": 6.0,
                "source": "SYNTHETIC, chosen to be plausible for a lab microreactor.",
                "notes": "Present so the axial reactor model has something to run "
                         "against in the examples. A real record must state where "
                         "each number was measured -- for the CO-oxidation campaigns "
                         "they existed only inside analysis code, which is the gap "
                         "this block closes.",
            },
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


def build_campaign(dataset_id: str, model_id: str) -> dict:
    """A synthetic campaign record: the STUDY as a registrable object.

    Tools produce artifacts; provenance explains each one; the campaign is the
    composition -- these datasets, these competing fits, this designed next
    experiment, held together by the question they answer. Members use the same
    {ref, kind, role} shape as publication.artifacts, deliberately, so one
    reference-checking implementation covers both.
    """
    return {
        "schema_version": "0.1.0",
        "campaign_id": "example-synthetic-prbs",
        "title": "SYNTHETIC EXAMPLE -- not a real study",
        "description": "Can the synthetic PRBS trace determine the two-site "
                       "model's constants? Exists to exercise the schema.",
        "status": "active",
        "milestone": "M3",
        "spokes": ["tcat-data-standard (examples)", "tcat-analysis"],
        "artifacts": [
            {"ref": dataset_id, "kind": "dataset", "role": "measured campaign"},
            {"ref": model_id, "kind": "model", "role": "baseline fit"},
            {"ref": SAMPLE_ID, "kind": "sample", "role": "catalyst"},
            {"ref": "10.5281/zenodo.0000000", "kind": "external",
             "role": "reference dataset",
             "notes": "External members are named, never implied."},
        ],
        "notes": "SYNTHETIC. Every id here points at the sibling examples.",
    }


def build_model_spec_axial() -> dict:
    """The same five-step network, fitted in a bed instead of at a point.

    Everything about the mechanism is identical to the fully reversible spec; the
    only difference is the `reactor` block, and that is the point. A constant fitted
    under a gradientless model is not the same quantity as one fitted under a
    dispersed plug-flow model, so the two have to be different spec ids -- otherwise
    two incomparable fits could collide on one artifact id.

    Two consequences show up in `free_parameters`. The gas activity is a PARTIAL
    PRESSURE here rather than a mole fraction, because that is the basis the
    reference implementation's constants are quoted on and the units of every
    adsorption constant depend on it. And there is no scale factor: a gradientless
    fit needs one and cannot separate it from k5, while a bed model gets it from the
    measured site density in the protocol's `bed` block.
    """
    names = ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k_4", "k5", "k_5"]
    free = []
    for n in names:
        adsorption = n in ("k1", "k2", "k_5")
        free.append({
            "name": n,
            "units": "log10(mol/(kg s Pa))" if adsorption else "log10(mol/(kg s))",
            "bounds": [-12.0, 6.0],
            "description": ("Per kilogram of catalyst, on a partial-pressure basis -- "
                            "the reference implementation's units, so that fitted "
                            "values are directly comparable with its published ones."),
        })
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-axial-dispersed",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, axially-dispersed packed bed",
        "description": "The five-step network in a one-dimensional dispersed bed: "
                       "gas is a state with an axial coordinate, the observable is "
                       "the outlet composition, and the site count comes from the "
                       "bed rather than from a fitted scale factor.",
        "derived_from": "art://spec-co-ox-5step-reversible-full-2026-09-01-000000",
        "derivation": "same mechanism, evaluated in an axially-dispersed packed bed "
                      "rather than a gradientless point reactor",
        "parameter_transform": "log10",
        "reactor": {
            "kind": "axially-dispersed-packed-bed",
            "nodes": 21,
            "convection": "upwind2",
            "outlet": "psu",
            "velocity": "psu-variable",
            "dispersion": "edwards-richardson-fuller-wilke",
            "inlet_reconstruction": {
                "method": "tracer-shift",
                "tracer": "Ar",
                "notes": "The valve schedule is not logged, so the inlet is recovered "
                         "from the co-fed inert tracer displaced by one empty-bed "
                         "residence time. Section 1.4 asks the rig to log the "
                         "schedule, which would let this become 'declared'.",
            },
            "notes": "21 nodes rather than the reference's 101: the outlet is "
                     "converged there with a second-order upwind stencil, and the "
                     "binding constraint is the timestep, not the grid. Note the "
                     "explicit expansion correction carries a Courant condition, so "
                     "REFINING the grid at fixed dt can destabilise it.",
        },
        "mechanism": _co_ox_mechanism(reversible_last_two=True, closure=False,
                                      activity_basis="partial_pressure"),
        "free_parameters": free,
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": "DRAFT (2026-08), axial-PDE branch. The reactor block is what the "
                 "September meeting is being asked to accept or overrule.",
    }


def _axial_reactor(rate_basis: str, note: str) -> dict:
    """The reactor block shared by the axial spec family.

    One function so the family stays a FAMILY: same bed treatment, same
    discretisation, differing only in mechanism and units. A drifted copy here
    would be two subtly different reactors under similar-looking names, which is
    exactly the ambiguity the block exists to remove.
    """
    return {
        "kind": "axially-dispersed-packed-bed",
        "nodes": 21,
        "convection": "upwind2",
        "outlet": "psu",
        "velocity": "psu-variable",
        "dispersion": "edwards-richardson-fuller-wilke",
        "rate_basis": rate_basis,
        "inlet_reconstruction": {
            "method": "tracer-shift",
            "tracer": "Ar",
        },
        "notes": note,
    }


def build_model_spec_axial_irreversible() -> dict:
    """Notebook 1's baseline mechanism, in the bed. The one-variable A/B.

    Same eight constants, same bounds, same mole-fraction basis, and per-site
    rates -- so every fitted constant is UNIT-IDENTICAL to the gradientless
    baseline's and the comparison between the two reactors is a subtraction,
    not a conversion. What disappears is the fitted scale factor: the bed's
    measured site density supplies the coupling the gradientless fit had to
    estimate, which also removes its documented degeneracy with k5.
    """
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-irrev-axial",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, irreversible steps 4-5, axial bed",
        "description": (
            "The eight-constant irreversible network evaluated in a "
            "one-dimensional axially-dispersed packed bed. Identical hypothesis "
            "to co-ox-5step-irreversible-45 except for where it reacts."
        ),
        "derived_from": "art://" + "spec-co-ox-5step-irreversible-45-2026-09-01-000000",
        "derivation": "same mechanism, evaluated in an axially-dispersed packed bed",
        "parameter_transform": "log10",
        "reactor": _axial_reactor(
            "per-site",
            "Per-site rates on the mole-fraction basis: constants unit-identical "
            "to the gradientless treatment's, so the reactor comparison needs no "
            "unit conversion.",
        ),
        "mechanism": _co_ox_mechanism(reversible_last_two=False, closure=False),
        "free_parameters": _free_parameters(
            ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k5"]
        ),
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "DRAFT (2026-08), axial-PDE branch. The A/B partner of "
            "co-ox-5step-irreversible-45: fit both to the same runs and the "
            "difference in the constants is the reactor model, attributably."
        ),
    }


def build_model_spec_axial_psu() -> dict:
    """PSU's own treatment: nine constants, k_4 closed, partial pressures, per kg.

    This is the M3 comparator. The milestone reads "reproduce the published PSU
    CO-oxidation fit within stated uncertainty", their per-temperature fits carry
    nlparci intervals, and comparing against them honestly means fitting the same
    free-parameter set in the same units -- per kilogram of catalyst, on a
    partial-pressure activity basis, with step 4's reverse fixed by detailed
    balance rather than fitted.
    """
    free = []
    for n in ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k5", "k_5"]:
        adsorption = n in ("k1", "k2", "k_5")
        free.append({
            "name": n,
            "units": "log10(mol/(kg s Pa))" if adsorption else "log10(mol/(kg s))",
            "bounds": [-12.0, 6.0],
            "description": ("Per kilogram of catalyst on a partial-pressure "
                            "basis -- the reference implementation's units, so "
                            "fitted values compare directly with its published "
                            "intervals."),
        })
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-psu-axial",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, PSU treatment in the axial bed",
        "description": (
            "Nine free rate constants with step 4's reverse closed by detailed "
            "balance, in the one-dimensional dispersed bed -- the published PSU "
            "fit's own free-parameter set, units, and reactor."
        ),
        "derived_from": "art://" + "spec-co-ox-5step-irreversible-45-2026-09-01-000000",
        "derivation": ("reversible with thermodynamic closure on step 4, "
                       "partial-pressure basis, axially-dispersed packed bed"),
        "parameter_transform": "log10",
        "reactor": _axial_reactor(
            "per-catalyst-mass",
            "Per-kilogram rates on the partial-pressure basis, matching the "
            "reference implementation so fitted constants compare directly "
            "against its published nlparci intervals.",
        ),
        "mechanism": _co_ox_mechanism(reversible_last_two=True, closure=True,
                                      activity_basis="partial_pressure"),
        "free_parameters": free,
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "DRAFT (2026-08), axial-PDE branch. The M3 comparator: same free "
            "set, same closure, same units, same reactor as the published fit, "
            "so 'within stated uncertainty' is checkable constant by constant."
        ),
    }


def build_model_spec_axial_thermo() -> dict:
    """The thermodynamically consistent joint fit, in the bed.

    Same 18 physical parameters as co-ox-5step-thermo-consistent -- (log10A, Ea)
    per step, (dH_ads, dS_ads <= 0) per adsorbate, every reverse from detailed
    balance -- with the same mole-fraction basis and per-site rates, so the
    fitted thermochemistry MEANS the same thing under both reactors and the
    joint-fit comparison is parameter-by-parameter. The gradientless variant's
    19th parameter, the shared scale, does not exist here: the bed supplies it.
    """
    spec = build_model_spec_thermo()
    spec = json.loads(json.dumps(spec))          # deep copy; never mutate a sibling
    spec["spec_id"] = "co-ox-5step-thermo-axial"
    spec["name"] = ("CO oxidation, five-step LH, thermodynamically consistent "
                    "joint fit in the axial bed")
    spec["description"] = (
        "Arrhenius forward constants and fitted adsorption thermochemistry, "
        "every reverse from detailed balance, evaluated in a one-dimensional "
        "axially-dispersed packed bed. One model across all campaign "
        "temperatures, with the reactor at the manuscript's fidelity."
    )
    spec["derived_from"] = "art://" + "spec-co-ox-5step-thermo-consistent-2026-09-01-000000"
    spec["derivation"] = ("the thermodynamically consistent parameterisation, "
                          "evaluated in an axially-dispersed packed bed")
    spec["reactor"] = _axial_reactor(
        "per-site",
        "Per-site rates on the mole-fraction basis: the (dH, dS) parameters "
        "mean exactly what the gradientless joint fit's mean, so the two "
        "posteriors are comparable parameter by parameter.",
    )
    spec["notes"] = (
        "DRAFT (2026-08), axial-PDE branch. The physical constants M9 asks for, "
        "fitted under the reactor model M3 is stated against."
    )
    return spec


def build_model_spec_thermo() -> dict:
    """The thermodynamically consistent variant: physical parameters, joint fit.

    Same five-step network as the fully reversible spec, but the free
    parameters are (log10A, Ea) per step and (dH_ads, dS_ads) per adsorbate;
    every reverse constant follows from detailed balance against the named
    gas-phase source, and a conforming fit treats all runs JOINTLY across
    temperature. Entropy of adsorption is bounded NON-POSITIVE -- physics as a
    bound, not a preference. Switching to or from this treatment is a
    different spec id, never a different tool.
    """
    step_bounds = {"log10A": [-2.0, 12.0], "Ea": [0.0, 250.0]}
    ads_bounds = {"dH": [-300.0, 50.0], "dS": [-250.0, 0.0]}
    free = []
    for i in range(1, 6):
        free.append({"name": f"log10A_k{i}", "units": "log10(1/s or 1/(mol_frac s))",
                     "bounds": step_bounds["log10A"]})
        free.append({"name": f"Ea_k{i}", "units": "kJ/mol",
                     "bounds": step_bounds["Ea"]})
    for ads in ("CO*", "O2*", "O*", "CO2*"):
        free.append({"name": f"dH_{ads}", "units": "kJ/mol", "bounds": ads_bounds["dH"],
                     "description": f"Adsorption enthalpy of {ads} relative to its gas parent."})
        free.append({"name": f"dS_{ads}", "units": "J/(mol K)", "bounds": ads_bounds["dS"],
                     "description": "Non-positive by physics: adsorption loses entropy."})
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-thermo-consistent",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, thermodynamically consistent joint fit",
        "description": "Arrhenius forward constants and fitted adsorption "
                       "thermochemistry; every reverse from detailed balance. "
                       "One model across all campaign temperatures.",
        "derived_from": "art://spec-co-ox-5step-irreversible-45-2026-09-01-000000",
        "derivation": "reparameterised in (log10A, Ea, dH_ads, dS_ads); all five steps reversible via detailed balance",
        "parameter_transform": "none",
        "thermodynamics": {
            "parameterisation": "arrhenius-detailed-balance",
            "gas_parents": {"CO*": {"CO": 1}, "O2*": {"O2": 1},
                            "O*": {"O2": 0.5}, "CO2*": {"CO2": 1}},
            "gas_data_source": "gas-thermo-codata-shomate-2026-08-25",
            "pressure_Pa": 101325.0,
            "notes": "Gas tables cancel out of every pure adsorption step and "
                     "enter once, as the overall reaction dG(T).",
        },
        "mechanism": _co_ox_mechanism(reversible_last_two=True, closure=False),
        "free_parameters": free,
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": "The physical constants this project is ultimately after (M9) "
                 "are these parameters, not per-temperature rate constants.",
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



# ---------------------------------------------------------- model specs

#: The five-step LH CO oxidation network, shared by three of the four variants
#: below. What differs between them is the reversibility of the last two steps
#: and whether step 4's reverse is a free parameter -- the smallest real
#: disagreements between published treatments of one mechanism, and they move
#: the free-parameter count from eight to ten.
#:
#: The fourth variant is a different NETWORK, not a different parameterisation:
#: an Eley-Rideal route with no adsorbed CO2 at all. Together the four are a
#: comparison set that costs four files and no code.
_CO_OX_STEPS = [
    ("CO + * -> CO*", "S1 CO adsorption"),
    ("O2 + * -> O2*", "S2 O2 adsorption"),
    ("O2* + * -> 2 O*", "S3 O2 dissociation"),
    ("CO* + O* -> CO2* + *", "S4 surface reaction"),
    ("CO2* -> CO2 + *", "S5 CO2 desorption"),
]

#: The Eley-Rideal network: the surface reaction releases CO2 directly, so there
#: is no CO2* intermediate and no desorption step. Structurally simpler than the
#: LH set rather than a reparameterisation of it.
_CO_OX_ER_STEPS = [
    ("CO + * -> CO*", "S1 CO adsorption"),
    ("O2 + * -> O2*", "S2 O2 adsorption"),
    ("O2* + * -> 2 O*", "S3 O2 dissociation"),
    ("CO* + O* -> CO2 + 2 *", "S4 surface reaction with direct release"),
]


def _co_ox_mechanism(reversible_last_two: bool, closure: bool,
                     activity_basis: str = "mole_fraction") -> dict:
    steps = []
    for i, (equation, name) in enumerate(_CO_OX_STEPS):
        step = {
            "equation": equation,
            "name": name,
            "reversible": True if i < 3 else reversible_last_two,
        }
        if closure and i == 3:
            step["constraint"] = {
                "kind": "thermodynamic_closure",
                # The tag names the exact vendored data an implementation must
                # compute from -- a closure whose thermochemistry moved would
                # otherwise put two computations on one artifact id. Two sources
                # because dG(T) needs both: an enthalpy anchor AND S(T)/Cp(T);
                # neither alone yields a dG at reaction temperature.
                "source": "CODATA (Cox, Wagman et al. 1984) formation enthalpies "
                          "+ NIST Shomate S(T), H(T)-H(298.15) for CO, O2, CO2 "
                          "[gas-thermo-codata-shomate-2026-08-25]",
                "notes": "The reverse constant is derived from the other nine plus the "
                         "overall equilibrium constant. The adsorbate free energies "
                         "cancel around the closure cycle, so the gas-phase tables "
                         "anchor it and the fitted constants of the other reversible "
                         "steps carry the adsorbate thermochemistry implicitly -- "
                         "fitted, not looked up.",
            }
        steps.append(step)
    return {
        "sites": [{"name": "*", "density": 1.0}],
        "gas": [{"name": "CO"}, {"name": "O2"}, {"name": "CO2"}],
        "adsorbates": [
            {"name": "CO*", "site": "*", "composition": {"C": 1, "O": 1}},
            {"name": "O2*", "site": "*", "composition": {"O": 2}},
            {"name": "O*", "site": "*", "composition": {"O": 1}},
            {"name": "CO2*", "site": "*", "composition": {"C": 1, "O": 2}},
        ],
        "steps": steps,
        # The basis is part of the mechanism because it fixes the UNITS of every
        # rate constant that touches a gas species. The axial variant declares
        # partial pressure so its constants are comparable with the reference's.
        "activity_basis": activity_basis,
        "gas_constant_J_per_mol_K": 8.314,
    }


def _co_ox_er_mechanism() -> dict:
    """The Eley-Rideal network. No CO2* adsorbate, no desorption step.

    Steps 1-3 are reversible as in the LH set; the release step is not, because
    a reverse would be a gas-phase molecule striking an adsorbed oxygen and there
    is no evidence in this data to fit one.
    """
    steps = [
        {"equation": equation, "name": name, "reversible": i < 3}
        for i, (equation, name) in enumerate(_CO_OX_ER_STEPS)
    ]
    return {
        "sites": [{"name": "*", "density": 1.0}],
        "gas": [{"name": "CO"}, {"name": "O2"}, {"name": "CO2"}],
        "adsorbates": [
            {"name": "CO*", "site": "*", "composition": {"C": 1, "O": 1}},
            {"name": "O2*", "site": "*", "composition": {"O": 2}},
            {"name": "O*", "site": "*", "composition": {"O": 1}},
        ],
        "steps": steps,
        "activity_basis": "mole_fraction",
        "gas_constant_J_per_mol_K": 8.314,
    }


#: Per-constant log10 bounds, from PHYSICS rather than from convenience.
#:
#: Bounds belong to the specification: two implementations of one mechanism
#: that use different ones are not producing comparable fits. But a bound that
#: binds at the optimum has stopped being a guardrail and become an undeclared
#: prior -- it sets the estimate, and it voids the reported uncertainty in that
#: direction, because a symmetric interval around a constrained optimum is not
#: a statement about the data. The earlier values (k1 <= 1e8, k5 <= 1e9,
#: k_3 <= 1e6) did exactly that: three of eight constants sat on them.
#:
#: These are the two rates nothing can exceed, computed at this campaign's
#: conditions (1.07e5 Pa, 459 K) rather than assumed:
#:
#:   Surface elementary steps: kT/h = 9.6e12 /s  ->  log10 = 12.98.  No
#:   activated surface process has a larger prefactor.
#:
#:   Adsorption, on the mole-fraction basis these constants use: the
#:   impingement flux P/sqrt(2 pi m k T) divided by the site density, at unit
#:   sticking. For CO over 1-2e19 sites/m2 that is 1.2-2.5e8 per unit mole
#:   fraction per second  ->  log10 = 8.1 to 8.4. Ceiling set at 8.5.
#:
#: So a constant resting on one of these bounds now means something: the data
#: wants that step faster than physics allows, which is a statement about the
#: mechanism and not about the optimiser. Values far below are unconstrained
#: territory and the lower edge is set well clear at 1e-8.
_ADSORPTION_CEILING = 8.5      # collision-limited, mole-fraction basis
_SURFACE_CEILING = 13.0        # kT/h at 459 K
_LOG10_BOUNDS = {
    "k1": (-8.0, _ADSORPTION_CEILING),    # CO adsorption
    "k_1": (-8.0, _SURFACE_CEILING),      # CO desorption
    "k2": (-8.0, _ADSORPTION_CEILING),    # O2 adsorption
    "k_2": (-8.0, _SURFACE_CEILING),
    "k3": (-8.0, _SURFACE_CEILING),       # dissociation
    "k_3": (-8.0, _SURFACE_CEILING),      # recombination
    "k4": (-8.0, _SURFACE_CEILING),       # surface reaction
    "k_4": (-8.0, _SURFACE_CEILING),
    "k5": (-8.0, _SURFACE_CEILING),       # CO2 desorption
    "k_5": (-8.0, _ADSORPTION_CEILING),   # CO2 readsorption
}


def _free_parameters(names) -> list[dict]:
    return [
        {
            "name": n,
            "units": "log10(1/(mol_frac s))" if n in ("k1", "k2") else "log10(1/s)",
            "bounds": list(_LOG10_BOUNDS.get(n, (-6.0, 9.0))),
        }
        for n in names
    ]


def build_model_spec_irreversible() -> dict:
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-irreversible-45",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, steps 4 and 5 irreversible",
        "description": (
            "Eight free rate constants. Steps 4 and 5 carry no reverse rate, which is "
            "a reasonable approximation when CO2 readsorption is negligible at the "
            "conditions of interest."
        ),
        "parameter_transform": "log10",
        "mechanism": _co_ox_mechanism(reversible_last_two=False, closure=False),
        "free_parameters": _free_parameters(
            ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k5"]
        ),
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "One of a PAIR of examples that exist to show mechanism comparison working. "
            "Its sibling, co-ox-5step-reversible-closure, describes the same chemistry "
            "with steps 4 and 5 reversible and a thermodynamic closure on step 4. Two "
            "specifications, two artifact ids, two fits, one comparison -- and no "
            "registry entry, no pull request, and no possibility of the two colliding."
        ),
    }


def build_model_spec_reversible() -> dict:
    spec = {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-reversible-closure",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, fully reversible with thermodynamic closure",
        "description": (
            "Ten free rate constants, with the reverse of step 4 fixed by thermodynamic "
            "closure rather than fitted. This is the treatment in the PSU MATLAB."
        ),
        "derived_from": "art://" + "spec-co-ox-5step-irreversible-45-2026-09-01-000000",
        "derivation": "steps 4 and 5 made reversible; thermodynamic closure added to step 4",
        "parameter_transform": "log10",
        "mechanism": _co_ox_mechanism(reversible_last_two=True, closure=True),
        # Nine, not ten: step 4's reverse constant is fixed by the closure rather
        # than fitted. PSU's MATLAB additionally fits a total site density, which
        # in this formulation is folded into the fitted scale factor instead.
        "free_parameters": _free_parameters(
            ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k5", "k_5"]
        ),
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "The sibling of co-ox-5step-irreversible-45. THE POINT OF THE PAIR: these "
            "two differ in three fields and are two different models. Under a capability "
            "registry they would have needed two curated names and a pull request each; "
            "as content-addressed artifacts they are simply two ids, and a fit records "
            "which one it used."
        ),
    }
    return spec


def build_model_spec_reversible_full() -> dict:
    """The honest ten-parameter arm: step 4's reverse is FITTED, not closed.

    Exists because the closure variant's reverse constant is not currently a
    number anyone computes -- `mechanism.from_document` gives a constrained step
    no reverse constant at all, and no implementation of thermodynamic closure
    exists in the toolchain. So the closure arm runs today with step 4 effectively
    irreversible, and this is the variant that actually tests whether the data
    supports a reverse surface reaction.

    It also has a property none of the others do: net CO2 production can go
    NEGATIVE, because CO2 readsorption is free. That is the case where a censored
    likelihood stops being a no-op on a floor of zero.
    """
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-5step-reversible-full",
        "family": "microkinetic",
        "name": "CO oxidation, five-step LH, fully reversible, no closure",
        "description": (
            "Ten free rate constants, including the reverse of step 4. The same "
            "network as co-ox-5step-reversible-closure, but with step 4's reverse "
            "fitted rather than derived -- so it is the arm that asks whether the "
            "data can determine it."
        ),
        "derived_from": "art://" + "spec-co-ox-5step-reversible-closure-2026-09-01-000000",
        "derivation": "thermodynamic closure removed from step 4; k_4 becomes a free parameter",
        "parameter_transform": "log10",
        "mechanism": _co_ox_mechanism(reversible_last_two=True, closure=False),
        "free_parameters": _free_parameters(
            ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4", "k_4", "k5", "k_5"]
        ),
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "Completes the reversibility ladder at eight, nine and ten free "
            "constants over one network, which is what makes a BIC comparison "
            "mean something: each rung buys one parameter, and the ranking says "
            "whether the datum paid for it."
        ),
    }


def build_model_spec_eley_rideal() -> dict:
    """A different NETWORK, not a different parameterisation.

    The surface reaction releases CO2 directly, so there is no adsorbed CO2 and
    no desorption step. Seven free constants over four steps. Included because a
    comparison set made only of reversibility variants tests one axis; this one
    asks whether the CO2 transient can distinguish a route with a bound product
    intermediate from one without.
    """
    return {
        "schema_version": "0.1.0",
        "spec_id": "co-ox-4step-eley-rideal",
        "family": "microkinetic",
        "name": "CO oxidation, four-step, direct CO2 release",
        "description": (
            "Seven free rate constants over four steps. The surface reaction releases "
            "gas-phase CO2 in one step, so CO2* and its desorption do not exist. "
            "Structurally simpler than the LH variants rather than a "
            "reparameterisation of them."
        ),
        "derived_from": "art://" + "spec-co-ox-5step-irreversible-45-2026-09-01-000000",
        "derivation": "steps 4 and 5 merged into a single direct-release step; CO2* removed",
        "parameter_transform": "log10",
        "mechanism": _co_ox_er_mechanism(),
        "free_parameters": _free_parameters(
            ["k1", "k_1", "k2", "k_2", "k3", "k_3", "k4"]
        ),
        "reaction_system": "CO oxidation",
        "access_status": "public",
        "license": "CC-BY-4.0",
        "notes": (
            "The set's control on network topology rather than on parameter count. "
            "Removing CO2* removes a state as well as a constant: seven against the "
            "irreversible LH arm's eight, over four steps rather than five."
        ),
    }


def write_ensemble_csv() -> Path:
    """A small, deterministic Laplace draw for the ensemble example."""
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "ensemble-samples-prbs-co-ox.csv"
    rng = random.Random(20260901)
    point = (-3.2, -1.7, 0.4)
    spread = (0.15, 0.4, 0.08)
    lines = ["log10_k_ads,log10_k_des,log10_k_rxn"]
    for _ in range(400):
        draw = [rng.gauss(mu, sigma) for mu, sigma in zip(point, spread)]
        lines.append(",".join(f"{v:.6f}" for v in draw))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_uncertainty_ensemble() -> dict:
    """A worked uncertainty-ensemble document, conditioning block included.

    The conditioning block is the point of the example: an ensemble that says
    OUT LOUD what its intervals condition on, instead of conditioning silently
    the way every interval before the field existed did. The nuisance budget
    shows both an honest null (no record states an MS sensitivity uncertainty,
    so the row routes to the prior-free envelope) and a record-sourced sigma.
    """
    samples_path = write_ensemble_csv()
    entry = ManifestEntry.from_file(samples_path, repo_root=REPO, format="csv",
                                    media_type="text/csv")
    return {
        "schema_version": "0.1.0",
        "method": "laplace",
        "method_family": "asymptotic",
        "approximation": "quadratic",
        "parameter_names": ["log10_k_ads", "log10_k_des", "log10_k_rxn"],
        "parameter_units": ["log10(1/s)", "log10(1/s)", "log10(1/s)"],
        "parameter_transform": "log10",
        "parameter_roles": ["interest", "interest", "interest"],
        "n_samples": 400,
        "point_estimate": [-3.2, -1.7, 0.4],
        "samples": entry.to_dict(),
        "conditioning": {
            "kind": "conditional",
            "held_fixed": [
                "ms_sensitivity_factors",
                "fragmentation_matrix",
                "feed_composition",
            ],
            "prior_source": (
                "none -- Type A only (JCGM 100:2008); the held_fixed list names "
                "what a marginalized re-evaluation would have to widen over"
            ),
        },
        "nuisance_budget": [
            {
                "parameter": "log10_k_ads",
                "nuisance": "ms_sensitivity_m28",
                "sensitivity": -0.42,
                "sigma_nuisance": None,
                "source": (
                    "no record states an MS sensitivity uncertainty; the "
                    "prior-free envelope is the reported answer, not an "
                    "invented sigma"
                ),
            },
            {
                "parameter": "log10_k_rxn",
                "nuisance": "fragmentation_co2_to_co",
                "sensitivity": 11.0,
                "sigma_nuisance": 0.003,
                "contribution_decades": 0.033,
                "source": (
                    "spread of the declared vs applied coefficient preserved "
                    "under declared_unused"
                ),
            },
        ],
        "notes": (
            "SYNTHETIC, for the schema's worked example. point_estimate is the "
            "optimum of the synthetic fit; the samples are a seeded Laplace draw."
        ),
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
    spec_irreversible = build_model_spec_irreversible()
    spec_reversible = build_model_spec_reversible()
    spec_reversible_full = build_model_spec_reversible_full()
    spec_eley_rideal = build_model_spec_eley_rideal()
    model = build_model(ensemble_ref, dataset["dataset_id"])
    spec_thermo = build_model_spec_thermo()
    spec_axial = build_model_spec_axial()
    spec_axial_irrev = build_model_spec_axial_irreversible()
    spec_axial_psu = build_model_spec_axial_psu()
    spec_axial_thermo = build_model_spec_axial_thermo()
    campaign = build_campaign(dataset["dataset_id"], model["model_id"])
    publication = build_publication(dataset["dataset_id"], model["model_id"])
    ensemble = build_uncertainty_ensemble()

    for name, doc in (
        ("uncertainty-ensemble-example.json", ensemble),
        ("dataset-prbs-co-ox.json", dataset),
        ("calibration-fixed.json", calibration),
        ("protocol-prbs.json", protocol),
        ("sample-synthetic.json", sample),
        ("model-lh-two-site.json", model),
        ("model-spec-co-ox-irreversible.json", spec_irreversible),
        ("model-spec-co-ox-reversible.json", spec_reversible),
        ("model-spec-co-ox-reversible-full.json", spec_reversible_full),
        ("model-spec-co-ox-eley-rideal.json", spec_eley_rideal),
        ("model-spec-co-ox-thermo.json", spec_thermo),
        ("model-spec-co-ox-axial.json", spec_axial),
        ("model-spec-co-ox-axial-irreversible.json", spec_axial_irrev),
        ("model-spec-co-ox-axial-psu.json", spec_axial_psu),
        ("model-spec-co-ox-axial-thermo.json", spec_axial_thermo),
        ("publication-example.json", publication),
        ("campaign-example.json", campaign),
    ):
        (HERE / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote examples/{name}")

    print(f"wrote examples/data/{csv_path.name}  "
          f"({entry.rows} rows, {entry.size_bytes} bytes, sha256 {entry.sha256[:12]}...)")


if __name__ == "__main__":
    main()
