"""The converter registry and contract.

All three converters are stubs. What is tested is that they are HONEST stubs --
registered, discoverable, and each naming what it needs before it can be written.
A converter implemented against a guessed file layout looks finished, which is
worse than one that says it is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tcat_standard.converters import find_converter, register, registry


def test_all_three_modalities_are_registered():
    """Importing the package must populate the registry. If it does not, a reader
    sees 'no converters exist' rather than 'converters exist but are stubs'."""
    assert set(registry) == {"ms-csv", "ir-spectra", "xas"}


@pytest.mark.parametrize("name", sorted(registry))
def test_each_converter_names_what_it_is_blocked_on(name):
    converter = registry[name]
    with pytest.raises(NotImplementedError) as exc:
        converter.convert(Path("input.raw"), Path("out"))
    message = str(exc.value)
    assert name in message
    assert "Blocked on" in message
    assert len(converter.blocked_on) > 30, "a stub reason is a work item, not a shrug"


@pytest.mark.parametrize("name", sorted(registry))
def test_stubs_sniff_nothing(name, tmp_path):
    """So find_converter returns None rather than picking a converter that will
    then fail -- the failure should be 'no converter for this file', not a
    NotImplementedError from an arbitrary one."""
    f = tmp_path / "sample.raw"
    f.write_bytes(b"\x00\x01")
    assert registry[name].sniff(f) is False
    assert find_converter(f) is None


def test_duplicate_registration_is_an_error():
    """Two converters under one name would make provenance ambiguous, since the
    converter name is a hashed parameter."""
    class Duplicate:
        name = "ms-csv"

        def sniff(self, path):
            return False

        def convert(self, path, out_dir, **options):
            raise NotImplementedError

    with pytest.raises(ValueError, match="already registered"):
        register(Duplicate())
