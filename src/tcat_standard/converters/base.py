"""The converter contract.

A converter takes one instrument-native file and produces canonical-layer bytes
plus the channel metadata needed to describe them. It does NOT decide what the
data means physically -- no calibration, no background subtraction, no baseline
correction. Those are transformations with their own artifacts, applied by the
analysis hub and cited in a provenance chain. A converter that quietly
subtracts a background has destroyed the audit story.

The division: a converter changes the container. A sensor model changes the
quantity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass
class ConversionResult:
    """What a converter returns.

    ``channels`` is schema-shaped: it drops straight into a dataset's
    ``channels`` object, units and uncertainty included. Converters are required
    to fill it in, because the alternative is a canonical file whose columns mean
    whatever the reader assumes.
    """

    output_path: Path
    format: str
    channels: dict[str, dict[str, Any]]
    time_base: dict[str, Any] | None = None
    instrument: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Converter(Protocol):
    """Instrument-native -> canonical.

    ``name`` is recorded in provenance, so it must be stable once published.
    """

    name: str

    def sniff(self, path: Path) -> bool:
        """True if this converter recognises the file.

        Cheap: read a header, not the whole file. A beamline export can be
        gigabytes and sniffing happens once per candidate converter.
        """
        ...

    def convert(self, path: Path, out_dir: Path, **options: Any) -> ConversionResult:
        """Convert one file, writing canonical bytes into ``out_dir``.

        Must not mutate the input. Must fail loudly rather than emit a partial
        file: a truncated canonical artifact that validates is the worst possible
        outcome, because nothing downstream can tell it is wrong.
        """
        ...


registry: dict[str, Converter] = {}


def register(converter: Converter) -> Converter:
    """Register a converter under its ``name``. Duplicate names are an error."""
    if converter.name in registry:
        raise ValueError(f"converter {converter.name!r} is already registered")
    registry[converter.name] = converter
    return converter


def find_converter(path: Path) -> Converter | None:
    """First registered converter that recognises the file, or None."""
    for conv in registry.values():
        if conv.sniff(path):
            return conv
    return None


class NotImplementedConverter:
    """Base for the 0.1.0 stubs.

    Raises on ``convert`` with a message naming what is needed to finish it, so
    the failure is a work item rather than a mystery.
    """

    name = "abstract"
    #: What is missing before this can be implemented.
    blocked_on: str = "real instrument files"

    def sniff(self, path: Path) -> bool:  # pragma: no cover - stub
        return False

    def convert(self, path: Path, out_dir: Path, **options: Any) -> ConversionResult:
        raise NotImplementedError(
            f"converter {self.name!r} is a stub in tcat-data-standard 0.1.0. "
            f"Blocked on: {self.blocked_on}. "
            "The interface is fixed; only the body is missing. See "
            "src/tcat_standard/converters/__init__.py for what to collect first."
        )
