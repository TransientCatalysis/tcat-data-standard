# Changelog

Package and schema versions move together in 0.x. They will decouple once the
schema stabilises and the validator keeps changing without it.

## Unreleased — 2026-08-24

First contact with real data. Every change below was forced by a specific thing
in PSU's CO-oxidation PRBS export or in Kitchin's fit of it; none was designed in
the abstract. Schema `0.1.0` is amended in place rather than forked, per
`STANDARD.md` §6 — nothing has been tagged and no data was written against it.
That window closes at the first tagged release, which is why these are being
made now and circulated for the team to overrule.

- **PRBS `waveform` replaces the flat LFSR fields.** Three forms — `lfsr`,
  `recorded`, `reconstructed` — discriminated by `form`. The real experiment is a
  randomised-dwell binary train ("6sMAX_50Pulses") with no LFSR anywhere, and its
  valve schedule was never logged. The old required set could not describe it
  truthfully. `parameters.label` is added for the operator's own sequence name,
  explicitly untrusted: in the export at hand the identical label appears on all
  five runs, at five different temperatures.
- **Per-channel time bases.** A channel may name its own `time_column`, and
  `time_base.kind` may be `per_channel`. A scanning quadrupole visits its masses
  in sequence — at 283.82 ms across 5 masses, 56.76 ms apart — so each species is
  timestamped at its own acquisition instant. One shared time column would
  misdate every species but the first.
- **`t0` is no longer required**, but its absence must be explained via
  `t0_absent_reason` (advisory). The export carries elapsed milliseconds only. A
  fabricated wall-clock is worse than a stated absence: it silently licenses a
  cross-modality alignment that was never measured.
- **`corrections_applied` on a dataset.** Records transformations already baked
  into the numbers — the workbook's fraction sheets have the MS fragmentation
  split applied already. Unrecorded, that is unrecoverable in both directions.
- **`ms_fragmentation` calibrations** may carry the cracking pattern inline as a
  `matrix`. An entry now needs either `channels` or `matrix`. An `ms_sensitivity`
  calibration that cites no fragmentation matrix and never mentions why is warned
  about.
- **`sample.properties[].reference`** for values taken from an external
  publication or SI rather than measured under this award.
- **`provenance.tool.conforming`.** The tool name had to match `tcat-<verb>`,
  which no artifact predating a conforming tool can satisfy — and the first real
  canonical data was converted by a lab script, as every spoke's first data will
  be. Setting `conforming: false` permits any name; leaving it unset still
  demands a `tcat-` one, so the flag cannot be used to duck the naming rule while
  keeping its guarantees. Recorded as a queryable field rather than waived in a
  notes string, because "what here was never produced by a conforming tool?" is a
  question release review has to be able to ask.
- Validator: waveform violations name the missing field rather than emitting
  `oneOf`'s "not valid under any of the given schemas".

## 0.2.0 — 2026-08-20

Second pass, driven by a clause-by-clause audit against the project Data
Management and Sharing Plan. See `DMSP-COMPLIANCE.md` alongside the spec.

### Three new document kinds

- **`sample`** — a physical catalyst. Synthesis method, precursors with lot
  numbers, ordered thermal treatments, nominal *and* measured composition, and
  independently measured properties each with a method and uncertainty. One
  sample is measured many times across three institutions; repeating its history
  on every dataset guarantees the copies diverge. The `properties` object is the
  side of the M9 join (a rate constant against a measured catalyst property) that
  is easy to leave in a notebook until too late.
- **`model`** — a fitted or trained model as a research product. One schema for
  both ends of the graded palette, because two would put an arbitrary line down
  the middle of a palette whose point is that the boundary moves per question.
  Splits are expressed as **groups**, not rows, so leakage is checkable rather
  than asserted. Metrics declare their split and warn without an interval.
  `limitations` is warned about when empty.
- **`publication`** — a manuscript and its full dependency set, with the role
  each artifact plays. Traceability runs from the paper outward; reconstructing it
  at submission means walking every artifact asking whether a figure used it.
  `data_availability_statement` becomes required at `accepted`.

### Fields

Added, all optional: `project`, `objective`, `software` on `dataset`, `sample`,
and `model`; `chemical_identifiers` (formula, InChI, InChIKey, SMILES, CAS,
PubChem, COD/ICSD, Materials Project) on channels and samples. These are the last
of the DMSP's enumerated metadata list. Optional rather than required because
none is lost by being backfilled — a funding award can be added later from records
that already exist, whereas a deleted failed run cannot.

Added `split_assignment` to the shared definitions: TRACE-AI B2 made structural.

### TRACE-AI

Four Model Development items moved from "assembled at write-up" to "recorded as
you go" — B1, B2, B3, and B5 now have homes in the `model` document. B4 stays at
manuscript time: it is an argument, not a field, and a schema demanding one would
get "see manuscript". `profiles/trace-ai/enforcement.md` and `crosswalk.md`
updated; the pin is unchanged at v2.2.0.

### On amending 0.1.0 in place

Schema `0.1.0` was amended rather than forked to a new directory. It is a
pre-release draft that nobody has used, and manufacturing a fake version history
before either version had a consumer would be worse than saying so plainly.
`STANDARD.md` §6 now states that retention begins at the **first tagged release**.

### Fixed during development

- The new advisory checks were initially inserted into `_structural_errors` as
  well as `_advisory_checks`, because the anchor string appeared in both — so an
  empty `limitations` field failed validation instead of warning. Caught by the
  errors-versus-warnings tests, which is what they are for.
- `test_every_documented_field_has_a_description` caught twelve undescribed
  fields across the three new schemas. It has now caught real omissions on both
  passes.

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
