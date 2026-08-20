# Crosswalk: TRACE-AI data manifest ↔ tcat dataset

Upstream source: `templates/data-manifest-template.yaml` at `trace-ai-checklist` **v2.2.0** (see `pin.json`).

Two structural differences shape the whole mapping, and they are worth stating before the table.

**Granularity.** TRACE-AI's manifest describes **one dataset snapshot** — an ML-ready assembly, with its sources, its build script, and its feature definitions. A tcat dataset document describes **one measurement or one derived product**. So the mapping is not one-to-one: a TRACE-AI manifest corresponds to a *set* of tcat datasets plus the provenance chain that links them. That is a deliberate difference, not an oversight — the chain is what we have that they do not, and reconstructing a manifest from it is mechanical, whereas going the other way is not.

**When it is written.** TRACE-AI's manifest is authored at publication. A tcat dataset document is authored at acquisition. This is why fields like `doi_or_url` and `landing_page` have no counterpart at write time: they do not exist yet, and inventing a placeholder for them is how placeholders end up in published records.

Consequence: the TRACE-AI manifest is a **generated artifact** in this project, produced at manuscript time by `tcat-analysis/report/trace_ai.py` from accumulated provenance. It is not a file anyone hand-maintains.

---

## `dataset:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `dataset.id` | `dataset_id` | Direct. Ours is constrained to lowercase with hyphens or underscores. |
| `dataset.doi_or_url` | `publication.repository_doi` | Optional, and absent until deposition. Reported to DOE OSTI on release per the DMSP. |
| `dataset.license` | `license` | Required in ours. Closed SPDX enum: `CC-BY-4.0`, `CC0-1.0`, `MIT`, `proprietary`. |
| `dataset.description` | `notes` | Ours is explicitly the narrative field — pretreatment, conditioning, deviations, why a run went wrong. |
| `dataset.custodians` | `personnel` | Ours carries per-person `role` and optional ORCID. |
| — | `batch_id`, `lineage_id` | **No upstream counterpart in the manifest template.** Upstream, leakage control is item B2 prose. We make it structural. See `enforcement.md`. |
| — | `sample_id` | No counterpart. The join key across modalities for one physical catalyst. |
| — | `access_status`, `embargo_until` | No counterpart. The DMSP's three-tier model. |
| — | `layer` | No counterpart. Upstream has no raw/canonical/derived distinction, because a reporting standard describes the finished dataset. |
| — | `autonomy_level` | Upstream this is item C2 prose, per campaign. We record it per dataset, since a project can move between levels mid-campaign. |

## `sources:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `sources[].name` | — | Implicit in the provenance chain: a tcat dataset's sources are its `provenance.inputs`. |
| `sources[].path_or_uri` | `files[].path` / `.url` / `.lfs_oid` | Ours allows **exactly one** location form and requires `sha256` beside it. Upstream has no checksum field. |
| `sources[].modality` | `measurement_type` | Ours is a closed enum tuned to this project: `prbs_kinetics`, `ms`, `ir_gas`, `ir_transient`, `xas_mes`, `steady_state`, `characterization`, `computational`. |
| `sources[].harmonization` | `provenance.parameters` + `channels[].units` | Harmonisation is not free text here; it is the recorded transformation. Units are explicit per channel, timestamps are UTC with an offset, and the transformation that got there is a provenance record with an artifact id. |

## `processing:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `processing.code_repo` | `provenance.tool.name` | Names the tool, which resolves to `tcat-analysis`. |
| `processing.entrypoint` | `provenance.tool.name` | Ours is a CLI verb, not a script path. Script paths move; tool names are part of the contract. |
| `processing.version` | `provenance.tool.version` | Stamped by the tool, never hand-entered. |
| `processing.hash_or_commit` | `provenance.tool.git_sha` | Ours permits the literal `dirty`, which is the honest answer for a working-tree run and disqualifies the artifact from promotion. |
| `processing.deterministic` | *structural* | Not a field. Determinism is the content-addressing invariant: re-running an unchanged pipeline must produce identical ids and recompute nothing. A boolean anyone can set to `true` is not evidence. |
| `processing.equivalence_checks` | `files[].sha256`, `files[].rows`, `files[].shape` | Upstream suggests row counts and ID-set equality in prose. We carry checksum, row count, and array shape as fields, so the check is mechanical. |

## `quality_control:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `quality_control.replicate_strategy` | `batch_id` + `lineage_id` + `notes` | Replicates share a lineage. The strategy is prose; the grouping is structural. |
| `quality_control.calibration_checks` | `calibration_ref` → `calibration.schema.json` | Upstream this is a sentence ("weekly flow/calibration references"). Here a calibration is a versioned, content-addressed artifact with its own schema, time-indexed entries, and per-channel uncertainty. **This is the largest single divergence, and the one most worth contributing upstream.** |
| `quality_control.anomaly_policy` | `status` + `status_reason` | Upstream: "flag; do not drop without review." Ours: required enum plus a mandatory reason whenever status is not `ok`. |

## `features:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `features[].name` | `channels.<name>` | Keyed by column or array name. |
| `features[].type` | `channels[].quantity` | Ours names the physical quantity (`ion_current`, `concentration`, `absorbance`), which is what distinguishes a raw signal from a derived one. |
| `features[].source` | `provenance.inputs` | |
| `features[].generation` | `provenance` chain | The whole chain, not a sentence describing it. |
| `features[].notes` | `channels[].notes` | |
| — | `channels[].units` | **Required** in ours. Upstream has no units field, which is the single most consequential gap for physical data. |
| — | `channels[].uncertainty` | **Required** in ours, with a declared noise-model family. No upstream counterpart. |

## `negative_data_policy:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `negative_data_policy.included` | `status` enum | A failed run is a dataset with `status: failed`, retained. |
| `negative_data_policy.description` | `status_reason` | Per-dataset rather than per-project, so an exclusion table can be generated with counts rather than asserted in prose. |

## `access:` block

| TRACE-AI | tcat | Notes |
|---|---|---|
| `access.landing_page` | `publication.repository_doi` | Absent until deposition. |
| `access.api` | — | The DMSP's web-accessible research database, once it exists. See `tcat-index/MIGRATION.md`. |
| `access.contact` | `personnel` | |

---

## Present in tcat, absent upstream

These are the substance of a transient-kinetics profile, and the concrete content of a contribution back to TRACE-AI.

| tcat | Why it has no upstream counterpart |
|---|---|
| `protocol` (`protocol.schema.json`) | TRACE-AI is written around steady-state screening and closed-loop synthesis. It has no representation for a perturbation waveform, and none for one that must be **exactly regenerable** — our PRBS protocol requires `register_length`, `taps`, and `seed` for that reason. |
| `time_base` | Multimodal acquisition on a shared clock has no upstream counterpart. Without it, simultaneously-acquired IR, XAS, and MS streams cannot be aligned, and "multimodal" means "parallel" instead of "fused". |
| `calibration.schema.json` | Sensor models as versioned, citable artifacts, time-indexed even when fixed. Upstream, calibration is a QC sentence. |
| `uncertainty-ensemble.schema.json` | Item B5 asks for a UQ method description. It does not specify a shape, and in particular does not require the *sample* rather than a summary — which is the thing experimental design actually needs, since a Gaussian summary discards the correlation structure that drives it. |
| `layer` | No raw/canonical/derived distinction, because a reporting standard describes the finished dataset rather than the pipeline that produced it. |
| Normative artifact-hash rule | Content addressing that is reproducible **across institutions** requires the canonicalisation rule to be shared, not merely the id format. |
