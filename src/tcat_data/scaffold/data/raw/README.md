# raw/

**Immutable, checksummed. Instrument output as produced.**

MS ion currents with instrument-native tags. Beamline exports. IR interferograms
or single-beam spectra.

## Never commit binary instrument blobs

Convert at ingestion. The schema enforces the tail of this — a file with
`format: instrument-native` is only legal in this layer, never in `canonical/` or
`derived/` — but the judgement about what to commit is yours.

The rule of thumb: if it is over a few MB and it is not text, stop. Either it
belongs behind an LFS pointer or a URL in its manifest entry, or it should have
been converted first. Both are one field in a manifest entry, and both keep
working for every downstream consumer.

## What "immutable" means here

Once a file lands here and a manifest entry names its checksum, the bytes do not
change. If an instrument re-export differs, that is a **new** file with a new
entry, not an edit — because a published result cites a checksum, and quietly
changing the bytes underneath it makes that citation a lie.

## Suggested layout

```
raw/
  prbs/2026-09-01/run-014.csv
  ir/2026-09-01/run-014.spa
  xas/2026-09-03/scan-0042.h5
```

Date-partitioned, because that is the one grouping that never needs revisiting.
Anything more elaborate — by catalyst, by campaign, by hypothesis — is a grouping
that will change, and it belongs in metadata where changing it is free.
