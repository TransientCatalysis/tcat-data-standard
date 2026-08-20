"""Instrument-native to canonical converters.

Conversion happens at ingestion, once. Never commit binary instrument blobs and
never carry an instrument-native file forward past the raw layer -- the schema
enforces that half of it, and these converters are the other half.

Every converter is a STUB in 0.1.0. The signatures are real and the contract is
fixed, because the interface is what three institutions have to agree on and it
is much cheaper to agree now than after each lab has written its own one-off
parser. The bodies wait for real instrument files, which do not exist yet: a
converter written against a guessed file layout is worse than no converter,
because it looks finished.

To implement one, you need from the owning lab:
  1. two or three real exported files, including one from a run that went wrong
  2. what each column means and its units, in writing
  3. whether the export is stable across instrument-software updates
"""

from .base import (
    ConversionResult,
    Converter,
    NotImplementedConverter,
    find_converter,
    register,
    registry,
)

# Import the concrete converters for their side effect: each registers itself at
# import time. Without this, `registry` is empty for anyone who imports the
# package rather than the individual modules -- which looks like "no converters
# exist" rather than "converters exist but are stubs", and those are very
# different things to a reader.
from . import ir_spectra, ms_csv, xas  # noqa: E402,F401

__all__ = [
    "ConversionResult",
    "Converter",
    "NotImplementedConverter",
    "find_converter",
    "register",
    "registry",
]
