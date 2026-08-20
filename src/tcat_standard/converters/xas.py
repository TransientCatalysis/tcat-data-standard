"""XAS / modulation-excitation XAS -> canonical Zarr. STUB.

Beamline data is the one modality this project does not own end to end. Large
facility data follows the user facility's own policies and preservation
capabilities; what belongs in a tcat spoke is the converted derivative plus
metadata that links back to the facility record. So this converter's job is
narrower than the others: read the facility export, emit a canonical array, and
carry the facility identifiers through so the original is findable.

Emits NORMALISED OR RAW ABSORPTION as exported. Energy alignment, background
removal, and reference-standard fitting are transformations with their own
artifacts -- and for MES-XAS specifically, phase-sensitive demodulation is a
transformation too, with a demodulation reference and a phase convention that
must be recorded. Folding demodulation into ingestion would make the phase
convention invisible, and phase is where the mechanistic content lives.

What this must produce:
  * a (time, energy) array, both axes explicit, energy in eV
  * edge identity (element, edge) as metadata, not inferred from the energy range
  * the facility record identifier -- proposal, beamline, endstation, scan id
  * a time base alignable with the reactor and IR streams

Open questions for the Frenkel group:
  * which beamline and endstation, and what does its export look like?
  * fast-scan XAS raw form: individual scans, or an already-binned array?
  * how is the beamline clock aligned to the reactor clock?
  * what does NSLS-II's data policy require us to keep versus link?
"""

from __future__ import annotations

from pathlib import Path

from .base import NotImplementedConverter, register


class XASConverter(NotImplementedConverter):
    name = "xas"
    blocked_on = (
        "beamline assignment and a sample export from Frenkel's group, plus NSLS-II's "
        "data-policy answer on what we retain versus link"
    )

    def sniff(self, path: Path) -> bool:  # pragma: no cover - stub
        return False


register(XASConverter())
