# tcat Data Standard

<!-- VERSION: 0.3.0 -->
<!-- MAINTAINER: A. J. Medford (Georgia Tech) -->
<!-- LAST_REVIEWED: 2026-09-01 -->
<!--
  This is the rulebook for what counts as a valid dataset in the TransientCatalysis
  collaboration. It is small on purpose: three institutions depend on it for the
  definition of ingestible data, so it must be stable.

  Sections are tagged [FIXED] or [ADAPTABLE].
    [FIXED]      cannot be overridden locally. Changing one is a major version bump.
    [ADAPTABLE]  a default. A lab may diverge, in writing, in its own spoke README.

  To propose a change: open an issue using the schema-change template, or a PR
  against main. See CONTRIBUTING.md.
-->

**Standards version:** 0.3.0
**Schema version:** 0.2.0 (`src/tcat_standard/schema/0.2.0/`; `0.1.0/` is frozen and retained)
**Status:** accepted by the team, September 2026, and exercised against a real campaign — 26 PSU CO-oxidation PRBS runs across four batches, ingested and validating. Six schema changes came out of that exercise rather than out of anticipation, which is the difference between this version and the last.

---

## Identity

This standard serves the DOE Genesis Mission Phase I project *Transient Kinetics and Spectroscopy for Agentic Digital Twins to Upgrade Domestic Alkane Feedstocks into Value-Added Chemicals* (DE-FOA-0003612), across:

| Institution | Role | Data it produces |
|---|---|---|
| Penn State (Janik, Rioux, Hodges) | Prime. PRBS reactor kinetics, transient IR, catalyst synthesis | PRBS traces, MS, gas-phase and transient IR, characterization |
| Brookhaven National Laboratory (Frenkel) | Modulation-excitation fast-scan XAS | Operando XAS, derived oxidation state and coordination |
| Georgia Tech (Medford) | Agentic AI kinetic fitting and workflow integration | Fits, ensembles, designed experiments, sensor models |
| ExxonMobil (Meyer) | Industrial partner (unfunded) | Framing; no data deposition expected |

The design goal beyond this project is that the standard survives it — a transient-kinetics profile that a wider community could adopt. That ambition is the reason for the strictness below; it is much cheaper to be strict now than to retrofit a field into three institutions' historical data later.

---

## [FIXED] 1. The dependency rule

**The analysis hub depends on the data hub. Never the reverse.** No exceptions.

If a new analysis or design feature appears to require a change here, that is evidence the schema is wrong, not that the boundary should be crossed. Fusing the two means every experimental-analysis feature touches the artifact three institutions depend on for data validity, and the artifact stops being stable.

Concretely: `tcat-analysis` pins a version of `tcat-data-standard`. This repository has no knowledge of `tcat-analysis` and never imports from it.

---

## [FIXED] 2. The three data layers

| Layer | Mutability | Contents |
|---|---|---|
| **raw** | Immutable, checksummed | Instrument output as produced. MS ion currents with instrument-native tags. Beamline files. IR interferograms or single-beam spectra. |
| **canonical** | Immutable once written | Tidy. Units explicit, uncertainties explicit. Converted at ingestion. |
| **derived** | Regenerable | Concentrations, fits, posteriors, designed experiments. Always reproducible from raw plus a recorded transformation chain. |

Rules:

1. **Never commit binary instrument blobs.** Convert at ingestion. A file with `format: instrument-native` is legal only in the `raw` layer; the schema enforces this.
2. **A raw ion current and a derived concentration are different quantities**, and the sensor model that maps between them is a separate, cited artifact. This is non-negotiable: it is the entire audit story. A converter that returns concentrations has folded a calibration into ingestion, and the day someone finds an m/z 44 artifact eighteen months from now there is no calibration id to swap.
3. **Derived data is deletable.** If deleting a derived artifact loses information, it was not actually derived and the transformation chain has a gap.

### File formats

- **CSV** for tabular data — traces, tidy time series.
- **Zarr** for bulk arrays — spectra, large multi-channel time series. Chunking means a large spectroscopic set can live off-repo behind the same manifest pointer.
- **JSON** for all metadata, validated against the schemas here.

---

## [FIXED] 3. Indirect file references

**Every dataset references its files through a manifest entry carrying a location plus a checksum. Never a direct filename in code.**

A manifest entry has exactly one of `path`, `url`, or `lfs_oid`. When a set outgrows GitHub's limits, replace `path` with `url` and every downstream consumer keeps working, with the checksum proving the bytes are the same. Adding a second location alongside the first is invalid — a consumer would not know which is authoritative.

The cost of following this is one indirection. The cost of not following it is open-coded paths scattered through analysis scripts at three institutions, which is not fixable after the fact. This is why the rule applies from day one rather than when it first hurts.

---

## [FIXED] 4. Required fields, and why each one is required now

A field is required in 0.1.0 only when retrofitting it later would destroy information that cannot be recovered. Everything else is optional and gets promoted per §6.

| Field | Why it cannot wait |
|---|---|
| `schema_version` | Data is validated against the version it was written against. Without it, a later bump silently reinterprets old data. |
| `dataset_id` | Stable identity that survives reprocessing, which artifact ids deliberately do not. |
| `batch_id` | TRACE-AI **B2**. Groups data that must never be split across a train/test boundary — one synthesis batch, one catalyst charge, one beamtime. A validator cannot enforce grouped splits unless this exists, and it cannot be reconstructed after the fact. |
| `lineage_id` | TRACE-AI **B2**. Groups data sharing a provenance chain. Catalysis datasets have shared lineages, repeated conditions, and time-series structure — every one of them a leakage pathway into a fitted or trained model. |
| `layer` | Determines what is immutable and what is regenerable. Ambiguity here makes the other two layers meaningless. |
| `status` | TRACE-AI **A5**. **Flag, never delete.** Required in 0.1.0 rather than added later, because retrofitting it means the historical record of what failed is already gone. |
| `status_reason` | Required whenever `status` is not `ok`. A flag without a reason cannot become an exclusion table at manuscript time. |
| `autonomy_level` | TRACE-AI autonomy level, A0–A5. This project runs at A1–A2 (human-gated). Recording it is nearly free now and impossible later. |
| `measurement_type` | Selects which conditional rules apply, and is the coarsest useful query key. |
| `sample_id` | The join key between kinetics, spectroscopy, and characterization of the same material. Without it the multimodal dataset is three parallel datasets. |
| `instrument` | Joins a dataset to the calibration that applies to it. |
| `channels` | Units and uncertainty, per channel. See §5. |
| `files` | The bytes, referenced indirectly. See §3. |
| `access_status` | DMSP three-tier model (`internal`/`staged`/`public`). Drives what may be released and when. |
| `license` | Committed in the DMSP. Unlicensed data cannot be released without going back to ask. |
| `provenance` | See §7. |
| `protocol` | Required for every experimental modality. Carries the perturbation waveform and time base. See §8. |

### Deliberately optional

`personnel`, `funding`, `publication`, `project`, `objective`, `software`, `reaction_system`, `catalyst_family`, `notes`, `embargo_until`, `calibration_ref`, `time_base`, and per-channel `identifiers`. Each is defined in the schema so the field *name* is stable when it is promoted; none is enforced.

Every one of these is a field the DMSP commits to recording. They are optional rather than required because none of them is lost by being backfilled — a funding award or a chemical identifier can be added later from records that already exist, whereas a deleted failed run cannot. The validator warns where absence is likely to be an oversight.

`notes` deserves a specific mention. It is where catalyst pretreatment history, reactor conditioning, failed runs, and deviations from the standard protocol belong. The DMSP asks for narrative fields explicitly, because this context is routinely essential to interpreting a catalysis experiment and routinely absent from structured fields. It is optional because a required free-text field gets filled with "n/a"; the validator warns when it is empty instead.

---

## [FIXED] 5. Units and uncertainty travel together

Units and uncertainty are declared **per channel**, inside `channels`, and both are required for every channel.

This differs from listing them as two top-level maps. Two parallel maps can drift apart — a channel present in `units` and absent from `uncertainty`, or the reverse — and that drift is exactly the implicit-convention failure the rule exists to prevent. Making them properties of one channel object makes the inconsistent state unrepresentable.

Uncertainty declares its `kind` (`sigma_column`, `constant_sigma`, or `none`) and a **noise model family** (`counting`, `gaussian_homoscedastic`, `gaussian_heteroscedastic`, `baseline_drift`, `calibrated_estimate`, `unknown`). Naming the family is the point: a counting-statistics sigma and a calibrated-estimate sigma propagate differently and must not be silently interchanged.

`kind: none` is legal. Some measurements genuinely have no uncertainty estimate. It must be **stated**, not left blank, and the validator warns.

### Three kinds of uncertainty, kept separate

1. **Data uncertainty** rides with the data — per-point sigma columns plus the declared noise model.
2. **Parameter uncertainty** is its own artifact. **Store the sample, not the summary.** A covariance matrix is a derived summary; Gaussian summaries discard exactly the correlation structure that drives experimental design. Frequentist output declares itself as a sampling representation too, so a maximum-likelihood fit emits its point estimate plus a bootstrap or Laplace ensemble in the same shape a sampler would use — which means experiment design consumes one shape regardless of provenance, and there is no need for two design pathways. Every ensemble carries `method` and `method_family` so nobody mistakes an asymptotic approximation for a sampled posterior.
3. **Calibration uncertainty** propagates but belongs to neither of the above. Its own artifact, cited in the chain.

---

## [FIXED] 6. Schema versioning, and the escape hatch

Semver on the schema.

- **Patch**: clarification. No structural change.
- **Minor**: adds optional fields only. Existing data stays valid.
- **Major**: rare. Ships a migration script rather than demanding labs fix existing data.

**The validator retains every old version forever.** This is structural, not a promise: versions live in `src/tcat_standard/schema/<version>/` and nothing is removed. A dataset that declares `schema_version: 0.1.0` is validated against 0.1.0 for as long as the repository exists.

**Retention now applies, and `0.1.0` is frozen.** The honest history, because it is
short and someone will otherwise find it: `0.1.0` was amended in place four times
between 2026-08-20 and 2026-08-29 — three document kinds after the first draft,
then the changes the first real dataset forced. The last two of those amendments
landed *after* real data arrived on 2026-08-26, which is later than this section
intended. Nothing was reinterpreted: every one was additive and optional, and the
changelog entries say so at the time. But the licence was being used past the
point it was written for, and prose is evidently not what stops that. So `0.1.0`
is frozen as amended, a checked-in checksum manifest makes the freeze structural,
and this release is where retention starts doing work.

From here: adding a document kind or an optional field is a minor bump into a new
directory, and the old one is never touched again. Manufacturing a fake version
history before anyone had used either version would have been worse than saying
this.

### When a bump is actually required

A version increment is only *needed* once somebody else could be holding the old
bytes — if nothing has been cloned, forked, or branched between pushes, amending
in place is fine and burning a version number is pointless ceremony.

One sharpening, specific to a **schema**: the operative question is not only "has
the repository been cloned" but **"does any document declare this version"**. A
dataset carrying `schema_version: 0.2.0` in some spoke is a consumer whether or
not anyone cloned this repository, and amending 0.2.0 then silently changes what
that document was checked against. So the test is:

- **Nothing declares it, and nothing has cloned it** → amend in place.
- **Something declares it** → new version, always. This is the case retention
  exists for.
- **In between** — cloned but not yet written against — → judgement. Note that
  every downstream CI installs this package from `@main` on every run, so in
  practice "cloned" happens continuously once pushed.

`0.1.0` is past all of that and is frozen; a checked-in checksum manifest and
`test_schema_0_1_0_is_byte_identical_to_the_manifest_committed_when_it_froze`
make that structural rather than a promise.

### The escape hatch

Every document may carry a free-form `extensions` object. **The validator ignores it rather than rejecting it.**

Unknown *top-level* fields are rejected. That is the point of having a designated namespace: typos and lab-private conventions land in `extensions` on purpose, not at the top level by accident.

**Promotion rule:** when the same field appears independently in **three** labs' `extensions`, it is promoted into the schema proper as an optional field. Schema follows practice; it does not predict it. Open a schema-change issue to start that conversation.

---

## [FIXED] 7. Artifact identity and provenance

### The id grammar

```
<tool>-<dataset-short-name>-<YYYY-MM-DD>-<short-hash>
calib-ptal2o3-co-ox-2026-03-14-a3f91c
```

The prefix is for humans and **carries no authority**; only the hash is trusted. Same discipline as git short SHAs: you read the prefix, the machine reads the digest.

### The hash rule is normative and lives here

The digest covers **tool name + tool version + ordered input ids + parameters**, canonicalised as specified in `tcat_standard.ids`.

This rule lives in the data hub rather than the analysis hub for a specific reason. The distributed design rests on the claim that an artifact id computed at Georgia Tech is byte-identical to one computed on a cluster at Penn State, so multiple stores can agree on names without a central authority. That claim is only true if the hashing rule is shared. If each site canonicalises parameters slightly differently — key order, float formatting, how an empty input list is encoded — the same computation yields two ids, the cross-site cache never hits, and the design degrades into per-site scratch directories without anyone noticing.

Consequences worth knowing:

- Input **order** is significant; parameter **key order** is not.
- `1` and `1.0` hash differently. A tool that treats them as equivalent must normalise before hashing.
- Adding a parameter at its default value changes the hash, so tools must not inject defaults into the hashed parameter dict.
- The tool's **git sha is recorded but not hashed.** Hashing it would mean every commit — including a docstring fix — invalidated every cached artifact, which makes the cache useless and pushes people to work around it. The version is the promise; the sha is the audit trail.

### The provenance record

Written by every tool, on every run, in an identical shape (`provenance.schema.json`). Every field is required. Tools **stamp their own version and the schema version**; nothing here is manually logged, because manual logging is the first thing to rot.

`durability` is marked at creation and never inferred later:

- **ephemeral** — solver checkpoints, intermediate residuals. Garbage-collectable, never synced between institutions.
- **durable** — fitted parameters, processed datasets, calibrations. Pushed to the shared store.

Without this distinction the project ships gigabytes of scratch between institutions.

---

## [FIXED] 8. Protocols: the designed thing and the run thing are the same object

A candidate or executed experiment is a **named protocol plus its parameters** — never a raw time series.

Transient experiments make the design space a function space rather than a vector, since one of the tunable knobs is *when transients fire*. The saving grace is that the general case is almost never needed: real transient experiments are parameterised. So the parameterisation is the representation, and each protocol declares its own parameter space (`prbs`, `pulse_train`, `temperature_ramp`, `step_change`, `multi_pulse`, `steady_state`).

The same object is stored alongside executed data and emitted by experiment design. Keeping one representation is what makes closing the loop later a matter of plumbing rather than translation.

**A PRBS protocol must declare a `waveform`, in one of three forms.** What all three deliver is the ability to reconstruct the actual perturbation; what differs is how much of it survived.

- `lfsr` — `register_length`, `taps`, `seed`, `bit_period_s`, `n_bits`. Three integers regenerate the sequence exactly.
- `recorded` — the executed `switch_times_s`. A randomised-dwell train has no generator state to record, so the schedule as run *is* the reproducible object.
- `reconstructed` — a `tracer_channel` and the `reason` no better record exists. The inlet is recovered from an inert tracer.

The third form exists because the alternative is worse. The first real dataset in this project is a randomised-dwell train whose valve schedule was never logged; requiring an LFSR seed would have meant either rejecting it or writing a fiction. A fit built on a tracer-reconstructed inlet inherits that reconstruction's assumptions, and the record has to show it — the sequence label the instrument writes does not, since it is routinely copied across runs it does not describe.

Chemical-looping operation is expressed as `multi_pulse` with labelled segments (`reduction`, `purge`, `reoxidation`) and a cycle count.

---

## [FIXED] 9. Calibrations are artifacts, not metadata

A calibration is a versioned, content-addressed artifact in its own right, with its own schema.

1. **Time-indexed from the start**, even with one entry. A fixed calibration is the degenerate case of a drifting one; code written against the general shape needs no change the day someone hands you a before/after bracket. The alternative — every consumer growing a branch for the single-entry case — produces exactly the branches that break when the second entry arrives.
2. **A derived concentration cites both** the raw artifact id **and** the calibration artifact id. That pairing is what lets one calibration id be swapped to re-derive every affected trace, and content addressing then tells you exactly which downstream fits are stale.
3. **Never silently applied to existing artifacts.** A calibration change produces new artifacts with new ids; it does not mutate old ones. The schema enforces a content-addressed `calibration_id` so a hand-written label cannot be edited in place.
4. **Stricter promotion gate.** Everything downstream depends on calibration code, so it gets a tighter gate than a fitting tool: reviewed by whoever owns the instrument. See `tcat-analysis/PROMOTION.md`.
5. **Background subtraction and reference selection are transformations with their own artifacts**, not silent preprocessing. This applies to IR backgrounds, XAS reference standards, MS fragmentation matrices, and MES phase conventions alike.
6. Calibration channels have **no per-channel escape hatch**. `extensions` exists at the document level, but a channel's fields are closed, because this is the tightest gate in the system.

---

## [FIXED] 10. Samples, models, and publications are documents

Three kinds exist because the project's Data Management and Sharing Plan commits to them, and because each is a link the registry needs in order to answer a question that will actually be asked.

### Samples

One sample is measured many times, across modalities, at three institutions. Repeating its synthesis history on every dataset guarantees the copies diverge and then nobody knows which is right — so a dataset carries `sample_id`, and a `sample` document carries everything the id stands for: synthesis method, precursors with lots, ordered thermal treatments, nominal *and* measured composition, and independently measured properties.

The `properties` object is the part worth planning for. Milestone M9 — a rate constant correlating with an independently measured catalyst property — is a **join** between a fitted parameter and this field. If the properties live in a notebook, that milestone becomes a spreadsheet exercise at the worst possible time.

Flag-never-delete applies here too. A failed synthesis is retained with a reason; those are often the most informative entries in a materials series.

### Models

A fitted or trained model is a research product, distributed with its training-data references, architecture, hyperparameters, seed, metrics, uncertainty, and **limitations on appropriate use**.

**One schema covers both ends of the graded palette.** A neural ODE and a reduced microkinetic model are described by the same fields. Two schemas would mean two report paths, two query surfaces, and an arbitrary line down the middle of a palette whose entire point is that the boundary moves per question.

Three things the schema insists on:

- **Splits are groups, not rows.** `split_assignment` lists `batch_id` or `lineage_id` values per split, so a validator can check that no group appears in two splits. That is TRACE-AI B2 made mechanical: catalysis data has shared lineages and repeated conditions, so a row-level split leaks and looks fine.
- **Metrics declare their split, and should carry an interval.** A bare number is best-only reporting (TRACE-AI B3); the validator warns.
- **`limitations` is warned about when empty.** A model released without stated limits gets applied outside them by someone who did not fit it.

### Publications

Traceability has a direction, and it is from the paper outward. A `publication` document enumerates every artifact, dataset, sample, and model the paper rests on, with the **role** each plays — `figure`, `table`, `underlying_data`, `model`, `calibration`, `validation`, `software`, `supporting`.

Reconstructing that at submission means walking every artifact asking whether some figure used it. Recording it as you go makes "data available at time of publication" a query instead of an audit.

By `accepted`, the data-availability statement must exist. There is no later moment at which to discover it does not.

---

## [FIXED] 11. Enforcement

**Passing CI is the definition of ingestible.** Not a review convention, not a checklist someone remembers — a status check that fails.

```bash
tcat-validate dataset path/to/dataset.json
tcat-validate all spoke-repo/            # walks a tree, infers kind per file
```

Exit status is 0 only when every document passes. **Warnings never affect exit status.** The moment style advice can fail a build, people stop running the validator locally and start discovering it at the worst possible time.

Errors name the offending field and give its JSON pointer. A validator whose output is "does not match schema" gets routed around within a week.

---

## [ADAPTABLE] 12. Spokes: granularity and layout are yours

**A spoke is any repository whose records validate.** That is the entire definition.

The contract is per-**record**, not per-repository. Nothing in this standard, the validator, or the registry assumes anything about how many spokes exist or what each one is organised around. One per lab, one per student, one per instrument campaign, one per sub-project, a monorepo holding several, or a mixture that changed as the project went — all valid, and none of them needs deciding in advance.

That is deliberate rather than permissive. Whether the right unit is a lab or a campaign is not knowable before the work happens, and a standard that guessed would be forcing a decision it cannot inform. The registry (`tcat-index`) is what makes granularity a non-decision: it records which spoke holds which record, so a dataset is findable regardless of how its repository is carved up, and re-carving later is a metadata update rather than a migration.

### Practical guidance, not rules

Some tradeoffs worth knowing, none of them binding:

| Coarser (fewer, bigger spokes) | Finer (more, smaller spokes) |
|---|---|
| One CI configuration, one set of permissions | Access control per lab or per student |
| Shared history is easy to search | A repository stays small and fast |
| One place to look | A student can be given their own without touching anyone else's |

The one thing genuinely worth avoiding is **one repository per dataset** — not because it breaks anything, but because a repository is a unit of review and access control, and neither of those varies per dataset. You would get hundreds of repositories with identical permissions and no shared history, for no gain.

### Declaring a layout

The validator's directory-name convention is a **default**:

```
manifests/  raw/  canonical/  derived/  calibrations/  protocols/  samples/
```

A spoke that diverges declares its layout in `.tcat-spoke.json` at its root, and `tcat-validate all` believes it:

```json
{
  "standard_version": "0.1.0",
  "granularity": "campaign",
  "layout": {
    "dataset": ["2026-09-campaign/measurements", "2026-11-campaign/measurements"],
    "calibration": ["2026-09-campaign"],
    "sample": ["materials"]
  },
  "exclude": ["scratch", "notebooks"],
  "strict": false
}
```

Everything in it is optional except `standard_version`. With no manifest at all, kind is inferred from directory names and then from each document's own contents — so an unconventional spoke validates without a manifest too; the manifest just makes the intent explicit and lets `exclude` and `strict` be set.

`strict: true` turns an unrecognised JSON file from a skip into an error. Off by default, because a spoke legitimately holds configuration and working notes, and forcing every JSON file to be a valid document would make people keep their real files somewhere the validator never sees.

---

## [ADAPTABLE] 13. Naming

| Thing | Pattern | Example |
|---|---|---|
| `dataset_id` | lowercase, hyphen or underscore separated | `prbs-co-ox-synthetic-001` |
| `batch_id` | lab prefix + synthesis or campaign identifier | `psu-vox-2026-09-a` |
| `lineage_id` | descriptive, stable across modalities | `vox-c3h8-odh-sample-14` |
| `sample_id` | the lab's own sample label, verbatim | `PSU-VOx-SiO2-14` |
| Instrument `identifier` | short, stable, uppercase | `MS-Q1`, `NSLS2-QAS-XAS` |
| Artifact id prefix | short verb or noun | `conc`, `fit`, `cal`, `frag` |

`sample_id` is deliberately the lab's own label rather than a project-assigned one. A relabelling scheme that disagrees with what is written on the vial is a scheme that gets ignored.

---

## [ADAPTABLE] 14. Open questions

These are recorded rather than guessed at. Each needs an answer from someone specific.

| Question | Who | Why it matters |
|---|---|---|
| **AmSC/ModCon**: is the position below sufficient, or is there a concrete interface specification? | DOE / Janik | See the note under this table. Tracked as a watch item rather than a blocker. |
| Does the HPC allocation permit **outbound network access from compute nodes**? | GT / PACE | Determines whether artifact pulls can happen mid-job or must be staged in advance. |
| Which **NSLS-II beamline and endstation**, and what does its data policy require us to retain versus link? | Frenkel | Shapes the XAS converter and whether raw beamline data enters a spoke at all. |
| How are the **MS, IR, XAS, and reactor clocks aligned**, and to what precision? | Rioux / Frenkel | Multimodal fusion is meaningless without it. A shared `time_base` assumes an answer exists. |
| Are exported **MS ion currents and IR spectra already background-subtracted**? | Rioux | If so, that background is a transformation and needs its own artifact, or the chain has a hole. |
| Is a git-backed registry accepted as the **web-accessible research database**, or is a hosted service expected? | Janik | `tcat-index` is built on the former reading. See `tcat-index/DATABASE.md` for the argument and the honest limits. |
| Which **public repository** for publication data packages? | Medford / Janik | Needed before first submission. Criteria in `tcat-index/RELEASE.md`. |

### On AmSC/ModCon

The DMSP commits that "all datasets, models, and workflows developed in this project will be structured for deployment on the AmSC/ModCon platform ... includ[ing] standardized data formats, model interfaces, and digital twin workflows."

No concrete specification has been provided. Rather than guess an interface — a guessed interface is worse than a documented gap, because it looks like a decision — the position taken is that the requirement is met in substance by what exists:

- **Standardized data formats**: CSV, Zarr, JSON, with a published versioned JSON Schema defining every document.
- **Model interfaces**: `model` documents declare features with units, hyperparameters, splits, metrics, and limitations; the CLI tool contract declares what each tool consumes and emits.
- **Digital twin workflows**: pipelines are sequences of content-addressed artifact ids with provenance, reproducible from raw by construction.

If a specification arrives, adapting is an **exporter reading these documents** — not a change to how data is collected. Keeping that true is the reason for the portability constraints in `tcat-index/DATABASE.md`.

---

## [FIXED] 15. Maturity: how much weight someone else may put on this

A record's `maturity.rung` says how much scrutiny it has survived. It is a
self-assessment, and every rung has an entry criterion a machine can check —
because the ethos of this project is checked, not claimed, and a ladder of vibes
would be the one soft thing in a hard system.

### It is not any of the four state fields that already exist

This is the part to read before filling the field in. The standard already
carries four state vocabularies and it would be easy to make this a fifth that
overlaps them. It does not overlap any of them, and every one of the four 2×2s
below has all four cells populated in practice.

| Field | The question it answers | Why maturity is not it |
|---|---|---|
| `status` — `ok` / `flagged` / `failed` | **Is this observation sound?** TRACE-AI A5, *flag never delete*. | A `failed` run can be `reviewed`: a well-documented failure is a valuable, mature record, and the exclusion table at manuscript time is built from exactly those. A pristine `ok` run written this morning is `sandbox`. |
| `access_status` — `internal` / `staged` / `public` | **Who may see it?** The DMSP's three-tier model. | Permission is a decision made *about* a record; maturity is a property *of* it. `public` + `sandbox` (scratch attached to a preprint) and `internal` + `reviewed` (embargoed and checked) are both ordinary. |
| `autonomy_level` — A0–A5 | **How human-gated was the process?** | An A0 record written entirely by hand is not thereby checked; an A4 record is not thereby unreliable. Folding them would let "a human did it" launder itself into "it was reviewed", which is precisely what TRACE-AI exists to stop. |
| `campaign.status` — `planned` … `abandoned` | **Where is this STUDY in its life?** | A study is `complete` when its last run finishes; its conclusions stay `sandbox` until somebody checks them. And `abandoned` ≠ `superseded`: abandoned means nobody finished it, superseded means somebody did it better. |
| `publication.status` — `planned` … `withdrawn` | **Where is this PAPER in the editorial process?** | It is the *anchor* for the `published` rung, not the rung. A paper being `accepted` does not make every record it cites `published` — each still has to be public and deposited, which is why the rung is checked against the paper rather than copied from it. |

In one sentence: **`status` is about the observation, `access_status` about
permission, `autonomy_level` about process, `campaign.status` and
`publication.status` about a study and a paper — and `maturity` is about how much
weight someone else may put on this record.**

### What each rung means

The plain-language definition first, because this is the part people will read
and the part they will fill the field in from.

| Rung | What it means |
|---|---|
| **`sandbox`** | Testing and exploration. **No expectation of quality or correctness.** It may be rewritten or deleted without notice, and nothing may depend on it. |
| **`working`** | A promising direction, actively pursued, still exploratory. **May contain errors or inconsistencies.** Others may build on it and must expect it to change. If nobody is pursuing it any more, it is `superseded`, not `working`. |
| **`reviewed`** | Carefully checked and vetted by **the stewards**, who are at this point effectively signing their names to the validity of the work. Like a drafted manuscript: correct and final in its basic form, though details may still change. |
| **`published`** | Associated with a **peer-reviewed publication**. Correct and fully vetted. A paper under review is not this yet — its data is `reviewed` until the paper is accepted. |
| **`superseded`** | Abandoned, or replaced by something better. **Never a dependency**, and removed from public and shared exports. Not deleted — see below. |

### What each rung costs to claim

Every criterion is mechanically checkable, and that is the point: the ethos here
is checked, not claimed, and a ladder of vibes would be the one soft thing in a
hard system.

| Rung | What makes it checkable |
|---|---|
| `sandbox` | The record validates. **This is what absence means**, so everything written before this field existed is correctly labelled by saying nothing. |
| `working` | Every advisory warning the document raises is either fixed or listed in `warnings_accepted` with a reason of at least thirty characters. |
| `reviewed` | `reviewed_by` with an ORCID or GitHub handle, `reviewed_on`, and a `review_scope` of at least thirty characters. The validator warns when the named reviewer is not among the record's stewards, and when the review predates the content it reviews. **The bytes must have a permanent home** — see below. |
| `published` | `published_in` names a `publication` whose own status is `accepted` or `published`, `access_status` is `public`, and `deposit_doi` is recorded. The criterion **is** the eight-step gate in `tcat-index/RELEASE.md`; this rung references it and never restates it. |
| `superseded` | `superseded_reason` says what happened. `superseded_by` names the successor **when there is one** — abandoned work has none, and requiring one would force people to invent a replacement. |

### `reviewed` is where a human becomes answerable

This is the rung that matters most, and it is worth stating in one sentence:

> **Below `reviewed`, a record may be entirely agent-generated with nobody
> claiming it is right. At `reviewed` and above, a named human is claiming it.**

That is the whole reason the ladder has this shape. Agent-generated work is not a
problem to be hidden — `sandbox` and `working` exist to describe it honestly, and
`autonomy_level` already records how much of it was gated by a person. What would
be a problem is agent-generated work arriving somewhere it looks vouched for
without anyone having vouched.

So the criterion is **accountability, not independence**. The reviewer should be
one of the record's own stewards, and a sole steward vetting their own work is
the intended case rather than a suspicious one — a one-person spoke is real, and
demanding a second name would produce a second name that did not check anything.
What is being asserted is not "somebody else agreed" but "I am answerable for
this", which is exactly what a signature is.

Two consequences worth being explicit about:

- **`review_scope` is the load-bearing field**, not `reviewed_by`. A name is easy
  to type; a sentence saying *what was checked, against what* is what makes the
  claim auditable later, and it is why the minimum length exists. The model is
  the calibration case: *"reproduced PSU's own exported mole fractions from raw
  counts through the four-stage chain — 130,537 of 130,560 values bit-identical
  across 26 runs."*
- **`autonomy_level` does not move when a record is reviewed.** It records how
  the work was *produced*, which does not change retroactively. A record produced
  at A4 and then reviewed is still A4 — and the pair, high autonomy plus a named
  reviewer, is a perfectly honest thing to have on the record. Collapsing the two
  would let "a human did it" and "a human checked it" become the same claim, and
  they are not.

### Three things the rungs deliberately do not say

**They do not set access.** `access_status` does, and it is not derivable from
maturity: `public` + `sandbox` (scratch attached to a preprint) and `internal` +
`reviewed` (embargoed and checked) are both ordinary. What the rungs carry is an
*expectation* — sandbox and working work is usually private and usually shared
only internally, with the disclaimer the rung already implies — and an expectation
is not a rule the validator enforces. Set `access_status` deliberately.

**They are not monotone in time.** A record can go *down*. A review that finds
real problems moves something from `reviewed` back to `working`, and that is the
system functioning rather than failing. Only `published` is effectively one-way,
because a paper cannot be un-accepted without a retraction — and a retraction is
`status: failed` with a `status_reason`, which is a different field answering a
different question.

**`superseded` does not mean deleted.** Superseded work is removed from public and
shared *exports*, and must never be a dependency. The artifacts themselves stay,
for two reasons this project has already committed to: their ids are how
published results are traced, so deleting them breaks the provenance of work that
cited them (`PROMOTION.md`, "never delete or edit the artifacts it produced"); and
a deleted failed run cannot be counted in an exclusion table at manuscript time,
which is TRACE-AI A5 and the reason `status` exists at all. `tcat-index` is
append-only for the same reason. If storage is the concern, that is what
`durability: ephemeral` and `tcat-store gc` are for, and they operate on
regenerable intermediates rather than on the record.

**Why `superseded` and not `deprecated`.** Data is not an API. A capability name
is deprecated because you should stop passing it; a dataset's bytes never stop
being a true record of what the instrument said. What actually happens is that a
better record of the same measurement appears — a clean re-export, a
recalibration, a corrected clock. Calling that "deprecated" would read as a
retraction, and a retraction is a serious thing to say about a scientific record.
Saying *this observation is unsound* is `status: failed` with a `status_reason`,
which is a different field answering a different question.

### A permanent home is part of being reviewed

Data feeding `sandbox` and `working` pipelines may live wherever is convenient —
a lab share, OneDrive, a scratch filesystem. That is normal, and the validator
says nothing about it, because warning about the ordinary case is how people
learn to skip warnings.

**At `reviewed` and above it stops being convenient and starts being a
promise.** A record that says somebody checked it is a record somebody may cite,
and a citation pointing at a share link breaks silently — revoked, re-issued, or
expired with an institutional account, with nothing anywhere reporting it.

So a record at those rungs whose `files[]` point at a `url` is warned about unless
`maturity.deposit_doi` names where the bytes were deposited. A `path` (in the
repository, hence in git) or an `lfs_oid` is already as durable as the repository,
and needs nothing further.

It is advice rather than a refusal, deliberately. Depositing takes time and a
decision about *where* — and `STANDARD.md` §14 records that the project has not
yet chosen a public repository. Blocking the claim on it would mean people stop
claiming reviews, not that they deposit sooner.

### `warnings_accepted`, and the one place advice has a consequence

§11 says warnings never fail CI, and that does not change. But a `working` claim
is defined against them: *the validator is quiet, or every remaining warning is
named here with a reason.* So every advisory check in this repository finally
carries weight — attached to a claim somebody chose to make, never to a build.
Thirty characters minimum on the reason, for the same reason a stub must name
what blocks it: "known" is not a reason.

### Per record, per spoke, and why the spoke is capped

A record with no `maturity` inherits the spoke's `maturity.rung`; a record that
has one uses its own. The resolution rule is one line:

```
effective = record.maturity.rung  or  spoke.maturity.rung  or  "sandbox"
```

A spoke may only declare `sandbox` or `working`, and the **schema** enforces that
rather than the prose. The rungs above rest on facts about a particular record —
a named reviewer of *this* record, a paper citing *this* record — which cannot be
true of a directory. Uncapped, one edit to one file would promote a whole tree
nobody looked at: a claim manufactured by inheritance, which is the failure this
ladder exists to prevent.

It is a floor, not a ceiling. A `sandbox` spoke may hold one `published` dataset,
and requiring otherwise would be bureaucrat's arithmetic.

### The analysis side uses one of these words for something else

`tcat-analysis`'s tool declarations carry `sandbox` / `wrapping` / `conforming`.
That vocabulary answers **is this code wired to the contract**; this one answers
**how much scrutiny has this artifact survived**. `sandbox` is deliberately the
same word in both, because it means compatibly the same thing — not connected,
not relied upon, may change without notice. The rest do not correspond, and
`wrapping` is not more mature than `sandbox`; it is a different route in.

### Crosswalk to established schemes

Recorded so the scheme is recognisable to an external reviewer and at deposit
time, and so nobody has to guess how to map it.

| tcat | NASA/NOAA data-product maturity | ADMS `status` (DCAT-AP) | PyPI Trove `Development Status ::` |
|---|---|---|---|
| `sandbox` | below beta — research | `UnderDevelopment` | 1 – Planning / 2 – Pre-Alpha |
| `working` | `beta` | `UnderDevelopment` | 3 – Alpha / 4 – Beta |
| `reviewed` | `provisional` | `Completed` | 5 – Production/Stable |
| `published` | `validated` (Stages 1–4) | `Completed` | 6 – Mature |
| `superseded` | retired | `Deprecated` | 7 – Inactive |

Four caveats, without which the table is decoration:

- **NASA/NOAA maturity assesses a whole product line** — its algorithm and
  validation record, across six categories, through an external review panel.
  Ours is a per-record self-assessment with one external anchor (`published`).
  This is a reading aid, not an equivalence, and in particular we must not tell a
  DOE reader "validated" on the strength of `published`.
- **ADMS collapses our middle three into `Completed`**, losing the distinction
  that matters most to us. Treat it as a known-lossy export direction: an
  exporter should carry the rung in `dct:description` rather than pretend.
- **`superseded` maps to `Deprecated`, never `Withdrawn`.** Withdrawn means
  retracted, and a retraction here is `status: failed`.
- **Trove is about code**, and is listed only so the two axes are visibly not the
  same one. The code side has its own ladder in `tcat-analysis/PROMOTION.md`.

Sources: NASA Earthdata, *Data Maturity Levels*; the stewardship-matrix lineage
is Bates & Privette (2012, *Eos*) and the NOAA Data Stewardship Maturity Matrix;
ADMS 2.00 as used by DCAT-AP 3.0.

---

## [ADAPTABLE] 16. Stewardship: who is answerable now

`.tcat-spoke.json` carries a required `stewards` block, and `.github/CODEOWNERS`
is generated from it. That is the whole mechanism, and the reason for it is that
ownership recorded in two places diverges — and then one of them is wrong and
nobody knows which.

### Stewards are not personnel

| | `stewards` | `personnel` |
|---|---|---|
| Tense | present — who answers for this now | past — who did the work |
| Consequence | generates a repository permission | none; it is a record |
| When someone leaves | they are replaced, or given an `until` | they stay, forever |

Merging the two would either hand every historical contributor write access, or
delete the historical record the moment somebody graduates. Both are worse than
carrying two blocks.

`role` is a closed set — `data_steward`, `instrument_owner`, `analysis_owner`,
`pi` — because the point is that each duty has an owner and a validator can check
the set is covered. **`instrument_owner` is load-bearing**: §9 and
`tcat-analysis/PROMOTION.md` both make a calibration change that person's review,
and the review is worthless if nobody knows who it is.

`credit_roles` is separate from `role`, and closed at exactly the fourteen CRediT
terms (ANSI/NISO Z39.104-2022). Conflating *who do I email when the calibration
is wrong* with *who goes on the paper* gets both wrong. The values are
lowercase-hyphen rather than the NISO display strings, which contain an en dash
that is a footgun in every shell and grep; the mapping is one-to-one.

### On a record, `stewards` replaces rather than merges

Absence means the spoke's stewards apply, which is the usual case. Presence means
*these people instead*. Merge semantics are unimplementable in the head — one
record steward beside three spoke stewards is either one or four, and nobody
would agree which — so the validator warns when an override drops a role the
spoke covered.

### `until` is the field that makes this survive an academic group

Nothing else in the standard records that a name has gone stale, and a stale
steward is worse than no steward because it looks answered. A student graduates,
a postdoc's term ends; set `until`, add the successor, regenerate CODEOWNERS.

### What this replaced

`spoke.contacts` is gone in 0.2.0 — zero instances existed anywhere, so §6's
promise that existing data stays valid is intact, and 0.1.0 still accepts it.
`calibration.owner` is deprecated in favour of a steward with
`role: instrument_owner`: its own examples were lab *groups*, and a review has to
route to a person.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.3.0 | 2026-09-01 | Accepted by the team, and the first version written against real data rather than in anticipation of it. **Schema `0.2.0` is minted and `0.1.0` is frozen** — 47 real PSU documents declare 0.1.0, and amending a version that real data declares is the thing `schema_version` exists to prevent. Adds **`maturity`** (`sandbox` / `working` / `reviewed` / `published`, plus the terminal `superseded`), whose absence means `sandbox` so nothing already written changes meaning, and every rung of which has an entry criterion a validator can check — including `warnings_accepted`, which makes a `working` claim falsifiable and is the only place an advisory check gains a consequence. Adds **`stewards`**, required on the spoke manifest, with a closed duty enum and CRediT contributor roles, and generating `.github/CODEOWNERS` so ownership metadata and repository permission cannot drift; `personnel` stays alongside it, because who did the work and who answers for it now are different questions. The spoke manifest also gains `spoke_id` and `kind`, and loses `contacts` (zero instances anywhere, and 0.1.0 still accepts it — pinned by a test). **Fixed:** a spoke's `standard_version` was applied as an override that beat each document's own `schema_version`, which would have silently revalidated a whole tree against a schema it was never written against on the first manifest anyone wrote; it is now a fallback, and the precedence is documented. `_infer_kind` learned about spoke manifests, which it had been skipping in silence. Examples now source the current version instead of hardcoding one, and a `spoke-example.json` exists because the manifest is the one document every new spoke must write. |
| 0.2.0 | 2026-08-20 | Second pass, driven by a clause-by-clause audit against the project DMSP (see `DMSP-COMPLIANCE.md` alongside the spec). Adds three document kinds the DMSP commits to and the first draft lacked: **`sample`** (materials data, and the measured properties milestone M9 joins a rate constant against), **`model`** (fitted and trained models as research products, with grouped splits, metrics with intervals, and limitations on appropriate use), and **`publication`** (the data-to-publication link, and the unit the release gate operates on). Adds the last of the DMSP's enumerated metadata fields — `project`, `objective`, `software`, and per-channel `chemical_identifiers` — all optional, because none is lost by being backfilled. Schema `0.1.0` was amended in place rather than forked to `0.2.0`: it is a pre-release draft nobody has used, and manufacturing a fake version history would have been worse than saying so. Retention now explicitly begins at the first tagged release. AmSC/ModCon moved from an open question to a stated position with a watch item. |
| 0.1.0 | 2026-08-20 | Initial draft, for team review before any real data exists. Required-field set is the infrastructure spec's §3.1 list plus the fields the DMSP commits to that would be unrecoverable if retrofitted (`sample_id`, `measurement_type`, `access_status`, `license`, `protocol`, `layer`). Units and uncertainty are per-channel rather than two top-level maps, so the inconsistent state is unrepresentable. The artifact hash rule is normative and lives here rather than in the analysis hub, because content addressing is only site-independent if the rule is shared. TRACE-AI is pinned at v2.2.0 — see `profiles/trace-ai/pin.json` for why not v2.0.0. Nothing in this version has been exercised against real instrument data. |
