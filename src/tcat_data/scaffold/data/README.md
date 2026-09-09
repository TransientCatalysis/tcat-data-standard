# [LAB OR CAMPAIGN NAME] — a tcat data spoke

> **This is a template.** Create your repository from it, then work through [`SPOKE-SETUP.md`](SPOKE-SETUP.md) and replace this file.

**A spoke is any repository whose records validate.** That is the whole definition.

One per lab, one per student, one per instrument campaign, one per sub-project, a monorepo holding several — all valid, and none of it needs deciding in advance. The contract is per-**record**, not per-repository, and the registry records which spoke holds what, so a dataset stays findable however the repositories are carved up. Re-carving later is a metadata update, not a migration.

The one thing worth avoiding is a repository per *dataset* — not because it breaks anything, but because a repository is a unit of review and access control and neither varies per dataset. You would get hundreds of repositories with identical permissions and no shared history.

## What goes where

The layout below is the **default**, not a requirement. If yours differs, copy `_tcat-spoke.json.template` to `.tcat-spoke.json`, declare where things live, and `tcat-validate all` will believe you. With no manifest, kind is inferred from directory names and then from each document's own contents — so an unconventional spoke validates either way; the manifest just makes the intent explicit and lets you set `exclude` and `strict`.

| Directory | Layer | Mutability |
|---|---|---|
| `raw/` | raw | Immutable, checksummed. Instrument output as produced. |
| `canonical/` | canonical | Immutable once written. Units and uncertainties explicit. |
| `derived/` | derived | Regenerable. Safe to delete. |
| `manifests/` | — | One dataset document per dataset. **The bytes are referenced from here, never named in code.** |
| `calibrations/` | — | Sensor models. Time-indexed even when there is only one entry. |
| `protocols/` | — | Perturbation protocols. The designed thing and the run thing are the same object. |
| `samples/` | — | The catalyst samples **this lab made**. Authored once; datasets then carry only `sample_id`. |

## Before your first commit

```bash
pip install "git+https://github.com/TransientCatalysis/tcat-data-standard.git"
tcat-validate all .
```

**Passing CI is the definition of ingestible.** The same validator runs on every pull request, so a local pass means a clean PR.

## The four rules that will bite you

**1. Never commit binary instrument blobs.** Convert at ingestion. The schema enforces the tail of this — an `instrument-native` file is only legal in the `raw` layer — but the judgement is yours. If a file is over a few MB and is not text, stop and ask.

**2. Every file is referenced through a manifest entry with a checksum.** Not a filename in a script. The day a spectroscopy set outgrows GitHub you replace one `path` field with a `url` and nothing downstream changes. Skip this and you get open-coded paths at three institutions, which cannot be fixed afterwards.

**3. Flag, never delete.** A run that went wrong gets `status: flagged` or `failed` and a `status_reason` saying why. It stays. A deleted failed run cannot be counted in an exclusion table at manuscript time, and that table is a publication requirement.

**4. `batch_id` and `lineage_id` are required, and they are not the same thing.** `batch_id` groups data that must never be split across a train/test boundary — one synthesis batch, one catalyst charge, one beamtime. `lineage_id` groups data sharing a provenance chain — repeated conditions, one sample across modalities. Neither can be reconstructed after the fact, which is why both are required now rather than added later.

## When the validator rejects something it should accept

That is a bug in the standard, not in your data. Two options, and you are not blocked either way:

- Put the field in `extensions` — the validator **ignores** it rather than rejecting it — and [open a schema-change issue](https://github.com/TransientCatalysis/tcat-data-standard/issues/new?template=schema-change.md).
- If a required field genuinely does not apply to your measurement, say so in the issue. A required field that does not fit a real measurement is a mistake in the standard.

When the same field turns up in three labs' `extensions`, it gets promoted into the schema properly.

## Register what you deposit

Validating locally and merging a PR gets the data into this repository. It does not make it *findable* — an id is a hash, so nothing can discover it. Registering does:

```bash
# in a checkout of tcat-index
python scripts/register.py sample  ../my-spoke/samples/PSU-VOx-14.json
python scripts/register.py dataset ../my-spoke/manifests/prbs-run-014.json --spoke my-spoke --site psu-rioux
```

Then anyone — or any agent — can find it:

```bash
python scripts/query.py --sample PSU-VOx-14
```

Register the **sample first**. A dataset whose `sample_id` does not resolve produces a warning, because the data-to-sample link is the one the project's data-management plan specifically commits to.

## Pinning

`.standard-version` records which schema version this spoke is written against — or `standard_version` in `.tcat-spoke.json` if you keep a manifest, which takes precedence. Bump it deliberately, never automatically: old versions are retained forever, so there is no deadline and no benefit to being current.

## Contacts

| | |
|---|---|
| This spoke | [YOUR NAME, EMAIL] |
| Instrument owner | [WHO APPROVES CALIBRATION CHANGES] |
| Data standard | A. J. Medford (ajm@gatech.edu) |
