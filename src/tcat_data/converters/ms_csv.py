"""Mass spectrometer export -> canonical CSV. STUB.

Emits ION CURRENTS, not concentrations. The distinction is the entire point of
the layer separation: a raw m/z ion current and a derived concentration are
different quantities, and the sensor model that maps between them is a separate
cited artifact. A converter that returns concentrations has silently folded a
calibration into ingestion, and the day someone finds an m/z 44 artifact
eighteen months from now, there is no calibration id to swap.

What this must produce:
  * one column per m/z channel, quantity ion_current, units A
  * a time column on an explicit time base, UTC-anchored
  * per-channel uncertainty: counting statistics where the instrument reports
    counts, otherwise a declared baseline-drift or calibrated estimate

Open questions for the Rioux lab:
  * which export format -- instrument software CSV, or the MATLAB intermediate
    the existing CO-oxidation workflow already produces?
  * are ion currents already background-subtracted on export? If so that is a
    transformation and needs its own artifact.
  * how is the MS clock aligned to the reactor clock, and to what precision?
"""

from __future__ import annotations

from pathlib import Path

from .base import NotImplementedConverter, register


class MSCsvConverter(NotImplementedConverter):
    name = "ms-csv"
    blocked_on = (
        "two or three real MS exports from the PSU PRBS reactor (one from a failed run), "
        "a written column dictionary, and an answer on MS/reactor clock alignment"
    )

    def sniff(self, path: Path) -> bool:  # pragma: no cover - stub
        return False


register(MSCsvConverter())
