# canonical/

**Immutable once written. Units explicit, uncertainties explicit.**

Converted at ingestion, by a converter, once. CSV for tabular data and tidy time
series; Zarr for bulk arrays such as spectra and large multi-channel series.

## This layer holds raw QUANTITIES

A canonical MS file holds **ion currents**, not concentrations. That distinction
is the whole point of the layer separation: a raw ion current and a derived
concentration are different quantities, and the sensor model that maps between
them is a separate, cited artifact.

If a converter returned concentrations, it would have folded a calibration into
ingestion — and the day someone finds an m/z 44 artifact eighteen months from now,
there would be no calibration id to swap and no way to know which fits went
stale. Ion currents in, ion currents out.

## Every channel declares its units and its uncertainty

Both, per channel, in the dataset document. Not one map of units and another of
uncertainties — those drift apart, and a channel with a unit and no uncertainty is
exactly the implicit-convention failure the rule exists to prevent.

Uncertainty declares its kind (`sigma_column`, `constant_sigma`, or `none`) and a
**noise model family**. `none` is legal — some measurements genuinely have no
estimate — but it must be *stated* rather than left blank.
