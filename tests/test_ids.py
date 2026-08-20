"""Artifact identity.

The tests that matter here are the ones that protect the distributed premise:
the same computation must hash identically no matter who runs it or in what
order they happened to build their parameter dict, and a different computation
must never collide with it. If that breaks, the cross-site cache silently stops
hitting and nobody notices until someone recomputes an eight-hour fit.
"""

from __future__ import annotations

import pytest

from tcat_standard import (
    compute_artifact_hash,
    format_artifact_id,
    is_valid_artifact_id,
    make_artifact_id,
    parse_artifact_id,
)
from tcat_standard.ids import ArtifactId

BASE = dict(
    tool_name="tcat-fit",
    tool_version="0.1.0",
    inputs=["conc-synth-co-ox-2026-09-01-abc123"],
    parameters={"solver": "radau", "rtol": 1e-8, "method": "laplace"},
)


# ---- determinism -------------------------------------------------------


def test_hash_is_deterministic():
    assert compute_artifact_hash(**BASE) == compute_artifact_hash(**BASE)


def test_parameter_key_order_does_not_matter():
    """Key order is an artifact of how the dict was built, not of the computation."""
    a = compute_artifact_hash(**BASE)
    reordered = dict(BASE, parameters={"method": "laplace", "rtol": 1e-8, "solver": "radau"})
    assert compute_artifact_hash(**reordered) == a


def test_nested_parameter_key_order_does_not_matter():
    p1 = {"model": {"sites": 2, "kind": "lh"}, "solver": "radau"}
    p2 = {"solver": "radau", "model": {"kind": "lh", "sites": 2}}
    assert compute_artifact_hash(**dict(BASE, parameters=p1)) == compute_artifact_hash(
        **dict(BASE, parameters=p2)
    )


def test_input_order_does_matter():
    """Inputs are positional: signal-then-calibration is a different call."""
    two = ["conc-a-2026-09-01-aaaaaa", "cal-b-2026-09-01-bbbbbb"]
    a = compute_artifact_hash(**dict(BASE, inputs=two))
    b = compute_artifact_hash(**dict(BASE, inputs=list(reversed(two))))
    assert a != b


# ---- invalidation ------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"tool_version": "0.1.1"},
        {"tool_name": "tcat-calibrate"},
        {"inputs": ["conc-synth-co-ox-2026-09-01-zzzzzz"]},
        {"inputs": []},
        {"parameters": {"solver": "bdf", "rtol": 1e-8, "method": "laplace"}},
        {"parameters": {"solver": "radau", "rtol": 1e-9, "method": "laplace"}},
        {"parameters": {}},
    ],
    ids=["version", "tool", "input-id", "no-inputs", "param-value", "param-tol", "no-params"],
)
def test_any_change_yields_a_new_hash(override):
    assert compute_artifact_hash(**dict(BASE, **override)) != compute_artifact_hash(**BASE)


def test_int_and_float_are_distinct():
    """1 and 1.0 hash differently. Documented, deliberate, and a real trap:
    a tool that treats them as equivalent must normalise before hashing."""
    a = compute_artifact_hash(**dict(BASE, parameters={"n": 1}))
    b = compute_artifact_hash(**dict(BASE, parameters={"n": 1.0}))
    assert a != b


def test_adding_an_explicit_default_changes_the_hash():
    """So tools must not inject defaults into the hashed parameter dict."""
    a = compute_artifact_hash(**dict(BASE, parameters={"solver": "radau"}))
    b = compute_artifact_hash(**dict(BASE, parameters={"solver": "radau", "verbose": False}))
    assert a != b


# ---- canonicalisation guardrails ---------------------------------------


def test_sets_are_rejected_rather_than_silently_sorted():
    with pytest.raises(TypeError, match="set-valued"):
        compute_artifact_hash(**dict(BASE, parameters={"species": {"CO", "O2"}}))


def test_unhashable_types_are_rejected_with_a_useful_message():
    with pytest.raises(TypeError, match="cannot be canonicalised"):
        compute_artifact_hash(**dict(BASE, parameters={"when": object()}))


def test_nan_is_rejected():
    """NaN has no canonical JSON form and no meaningful equality; it must not
    reach a content address."""
    with pytest.raises(ValueError):
        compute_artifact_hash(**dict(BASE, parameters={"rtol": float("nan")}))


@pytest.mark.parametrize("length", [5, 17, 0, -1])
def test_hash_length_is_bounded(length):
    with pytest.raises(ValueError):
        compute_artifact_hash(**BASE, length=length)


def test_longer_hash_is_a_prefix_extension():
    """Lengthening the short hash must not change the leading characters, so an
    id recorded at six characters stays findable if the project later widens it."""
    short = compute_artifact_hash(**BASE, length=6)
    long = compute_artifact_hash(**BASE, length=16)
    assert long.startswith(short)


# ---- grammar -----------------------------------------------------------


def test_round_trip():
    aid = "calib-ptal2o3-co-ox-2026-03-14-a3f91c"
    parsed = parse_artifact_id(aid)
    assert parsed == ArtifactId("calib", "ptal2o3-co-ox", "2026-03-14", "a3f91c")
    assert str(parsed) == aid
    assert parsed.ref == f"art://{aid}"


def test_art_scheme_refs_parse():
    assert parse_artifact_id("art://fit-vox-2026-09-01-9b12ee").tool == "fit"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "no-date-here-abc123",
        "Calib-Upper-2026-03-14-a3f91c",          # uppercase
        "calib-ptal2o3-2026-3-14-a3f91c",         # unpadded date
        "calib-ptal2o3-2026-03-14-A3F91C",        # uppercase hash
        "calib-ptal2o3-2026-03-14-a3f9",          # hash too short
        "calib--doublehyphen-2026-03-14-a3f91c",  # empty name segment
        "9calib-ptal2o3-2026-03-14-a3f91c",       # tool starts with a digit
        "calib-ptal2o3-2026-03-14-a3f91cg",       # non-hex in hash
    ],
)
def test_invalid_ids_are_rejected(bad):
    assert not is_valid_artifact_id(bad)
    with pytest.raises(ValueError):
        parse_artifact_id(bad)


def test_format_rejects_ungrammatical_parts():
    with pytest.raises(ValueError):
        format_artifact_id("Calib", "name", "2026-03-14", "a3f91c")


def test_make_artifact_id_is_well_formed_and_stable():
    kwargs = dict(
        tool="fit",
        name="synth-co-ox",
        when="2026-09-01",
        tool_name="tcat-fit",
        tool_version="0.1.0",
        inputs=["conc-synth-co-ox-2026-09-01-abc123"],
        parameters={"model": "lh-two-site"},
    )
    first = make_artifact_id(**kwargs)
    assert is_valid_artifact_id(first)
    assert make_artifact_id(**kwargs) == first
    parsed = parse_artifact_id(first)
    assert (parsed.tool, parsed.name, parsed.date) == ("fit", "synth-co-ox", "2026-09-01")


def test_human_prefix_carries_no_authority():
    """Two different prefixes over the same computation share the same hash --
    the prefix is for reading, the hash is for trusting."""
    common = dict(tool_name="tcat-fit", tool_version="0.1.0", inputs=[], parameters={"a": 1})
    a = make_artifact_id(tool="fit", name="x", when="2026-09-01", **common)
    b = make_artifact_id(tool="conc", name="y", when="2026-09-01", **common)
    assert parse_artifact_id(a).short_hash == parse_artifact_id(b).short_hash
