"""IR spectra -> canonical Zarr. STUB.

Covers both gas-phase IR used as a composition analyser and transient/operando
IR used to watch surface species. Zarr rather than CSV because a transient IR
run is a (time, wavenumber) array that will not stay small.

Emits SINGLE-BEAM or as-exported spectra. Background subtraction and reference
selection are transformations with their own artifacts, not silent
preprocessing -- same rule as the MS converter, same reason. If the instrument
software has already ratioed against a background, that background must be
captured as its own artifact and cited, or the chain has a hole in it.

What this must produce:
  * a 2-D array on (time, wavenumber) with both axes stored explicitly
  * quantity: absorbance or single_beam_intensity, declared, never assumed
  * a time base shared with the kinetic stream, so the modalities can be aligned
  * uncertainty: detector noise where available, otherwise a declared estimate

Open questions for the PSU team:
  * export format -- OPUS, SPA, JCAMP-DX, or a text dump?
  * is the exported spectrum already background-ratioed?
  * is the wavenumber axis identical across runs, or per-run?
"""

from __future__ import annotations

from pathlib import Path

from .base import NotImplementedConverter, register


class IRSpectraConverter(NotImplementedConverter):
    name = "ir-spectra"
    blocked_on = (
        "real IR exports plus a decision on whether background ratioing happens on the "
        "instrument (in which case the background becomes its own cited artifact)"
    )

    def sniff(self, path: Path) -> bool:  # pragma: no cover - stub
        return False


register(IRSpectraConverter())
