# Changelog

Package and schema versions move together in 0.x. They will decouple once the
schema stabilises and the validator keeps changing without it.

## 0.1.0 — 2026-08-20

Initial draft, for team review **before any real instrument data exists**. That
timing is deliberate: the required-field set is the one thing here that is
genuinely expensive to change later, so it should be argued about now.

### Schema (0.1.0)

Six document kinds: `dataset`, `manifest-entry`, `calibration`, `provenance`,
`uncertainty-ensemble`, `protocol`, plus shared `defs/common`.

Decisions worth flagging for reviewers:

- **Required fields** are the infrastructure spec's §3.1 list plus the fields the
  project DMSP commits to that would be unrecoverable if retrofitted:
  `sample_id`, `measurement_type`, `access_status`, `license`, `protocol` (for
  experimental modalities), and `layer`. `personnel`, `funding`, `publication`,
  `reaction_system`, `catalyst_family`, and `notes` are defined but optional, so
  the field names are stable when they are promoted.
- **Units and uncertainty are per channel**, not two parallel top-level maps. Two
  maps can drift apart — a channel in one and not the other — and that drift is
  the exact failure the rule exists to prevent.
- **The artifact hash rule is normative and lives here**, not in the analysis hub.
  Content addressing is only site-independent if the canonicalisation rule is
  shared; otherwise the same computation yields different ids at different
  institutions and the cross-site cache silently stops hitting.
- **PRBS protocols require `register_length`, `taps`, and `seed`**, so a waveform
  is regenerable from metadata rather than inferred back out of the trace.
- **Calibrations are time-indexed even with one entry.** A fixed calibration is
  the degenerate case of a drifting one.
- **`extensions` is ignored, not rejected**; unknown top-level fields are
  rejected. Promotion threshold: the same field in three labs' extensions.

### Validator

`tcat-validate` with per-kind and tree-walking modes, JSON output for tooling,
and errors that name the offending field. Warnings are advisory and never affect
exit status.

### TRACE-AI profile

Pinned at **v2.2.0** (`961c9a9`, 2026-06-12), not v2.0.0.

- v2.0.0 predates the accepted manuscript, and v2.1.0 revised item wording across
  A1–D3, so v2.0.0's item text is superseded.
- For the record: the infrastructure spec gave v2.0.0's commit as `5d11e14`,
  which is not that tag — v2.0.0 is `5101e24`.
- The spec also described the autonomy scale as A0–A4. It is **A0–A5**, per
  upstream's own `autonomy-run-log-template.md`. The schema enum reflects this.
- Cite the published paper (*Chem Catalysis*, DOI `10.1016/j.checat.2026.101755`),
  not the ChemRxiv preprint.

### Known gaps

- All three converters (`ms-csv`, `ir-spectra`, `xas`) are stubs. Interfaces are
  fixed; bodies wait for real instrument files. A converter written against a
  guessed file layout is worse than none, because it looks finished.
- Nothing here has been exercised against real data. The synthetic example exists
  so every required field has a worked, checkable value — its checksum is the
  real checksum of `examples/data/prbs-co-ox-synthetic.csv` — but a synthetic
  trace cannot surface the fields real acquisition turns out to need.
- Open questions are tracked in STANDARD.md §13, including AmSC/ModCon
  interoperability and cross-instrument clock alignment.
