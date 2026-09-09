# Setting up a spoke

Twenty minutes, once. Work down the list.

## 1. Name it, at whatever granularity suits you

**A spoke is any repository whose records validate.** Pick the unit that matches how you actually work — nobody can usefully decide this for you in advance, and the registry means it is not a decision you are stuck with.

```
spoke-psu-prbs           by instrument or campaign
spoke-rioux-lab          by lab
spoke-jsmith             by student
spoke-odh-mechanism      by sub-project
psu-transient-data       a monorepo holding several
```

Two things worth knowing. A repository is a unit of **review and access control**, so the granularity that usually feels right is whatever matches who reviews and who needs access. And a repository per *dataset* is the one shape to avoid — not because it breaks anything, but because you would get hundreds of repositories with identical permissions and no shared history, for no gain.

If your granularity changes later, moving records between spokes is a `git mv` plus a re-register. Nothing joins on a repository name.

## 2. Make it private

The DMSP: private during early development, public on release. Data is released no later than the publication it supports.

Repository visibility is a coarse gate; the fine-grained one is each dataset's `access_status` field (`internal` / `staged` / `public`). Set that per dataset and the release conversation later is a query rather than an audit.

## 3. Fill in the placeholders

- `README.md` — every `[BRACKETED]` item, then delete the "this is a template" line
- `LICENSE` — the copyright holder
- `.standard-version` — leave as-is unless you have a reason
- `_tcat-spoke.json.template` — **only if your layout differs from the default**, or you want `exclude` / `strict`. Copy it to `.tcat-spoke.json`, strip the `$comment` keys, fill it in. Otherwise delete it: the default directory names work without a manifest, and so does content-based inference for a layout that matches neither.

## 4. Install the validator

```bash
pip install "git+https://github.com/TransientCatalysis/tcat-data-standard.git"
tcat-validate versions
```

## 5. Register your site

Your data lives somewhere with a name. Open a PR against [`tcat-index`](https://github.com/TransientCatalysis/tcat-index) adding your site to `index/sites.yml`.

The field that matters is **`egress`** — whether your compute nodes can reach the network. It decides whether tools can pull artifacts mid-job or whether inputs must be staged in advance. If you do not know, write `unknown`; a wrong guess costs a debugging afternoon.

## 6. Your first calibration

Do this **before** your first dataset. A dataset citing a calibration that does not exist yet is a dataset you will have to revisit.

Copy `calibrations/_example.json` and fill it in. The one thing people get wrong: **use the time-indexed form even though you have only one entry.** A fixed calibration is the degenerate case of a drifting one. Written this way, the day you have a before/after bracket you append a second entry and nothing downstream changes. Written as a single flat set of numbers, everything that reads it grows a special case.

`calibration_id` is content-addressed. Generate it rather than naming it:

```python
from tcat_data import make_artifact_id
print(make_artifact_id(
    tool="cal", name="msq1", when="2026-09-01",
    tool_name="tcat-calibrate", tool_version="0.1.0",
    inputs=[], parameters={"determined_from": "cal-gas-run-003"},
))
```

A hand-written label like `our-calibration-v2` could be edited in place, and then nothing downstream could tell which fits went stale. That is the whole reason it is a hash.

## 7. Your first sample

Before your first dataset, if this lab makes catalysts. `samples/_example.json` is
the template.

Authored **once** per sample, by the lab that made it. Every dataset measured on
it then carries only `sample_id`. The thing worth taking seriously is
`properties`: correlating a fitted rate constant against a catalyst property is a join between a fit and an
independently measured catalyst property recorded there, so a surface area or a
TPR maximum that lives only in a notebook is a comparison that becomes a
spreadsheet exercise later.

Record precursor `lot` numbers. They are unrecoverable once the bottle is gone,
and a lot change is a classic culprit for unexplained drift between nominally
identical samples.

## 8. Your first protocol

Copy `protocols/_example.json`. A PRBS protocol must declare a `waveform` in one of three forms, and which one you can honestly use is worth knowing before your first run rather than after:

- `lfsr` — `register_length`, `taps`, `seed`, `bit_period_s`, `n_bits`. Three integers regenerate the sequence exactly. Use this if your sequence really is LFSR-generated.
- `recorded` — the executed `switch_times_s`. Use this if your valve controller can log what it did. A randomised-dwell train has no generator state, so the executed schedule *is* the reproducible object.
- `reconstructed` — a `tracer_channel` and the `reason`. The honest fallback when neither exists and the inlet has to be recovered from an inert tracer.

If you find yourself reaching for the third form, that is worth an instrument work item rather than a metadata one: logging the schedule is usually a small change, and everything downstream of a reconstructed inlet inherits the reconstruction's assumptions.

Do not use `parameters.label` as metadata. It is there to hold the operator's own sequence name verbatim, and in the first real dataset the project ingested the identical label appeared on five runs at five different temperatures.

## 9. Your first dataset

Copy `manifests/_example.json`. Compute the checksum rather than typing one:

```python
from tcat_data import ManifestEntry
entry = ManifestEntry.from_file("raw/prbs/2026-09-01/run-014.csv", repo_root=".")
print(entry.to_dict())
```

Then:

```bash
tcat-validate dataset manifests/prbs-run-014.json
```

Read the warnings as well as the errors. Warnings never fail CI, and the one about empty `notes` is the one worth acting on — pretreatment history, reactor conditioning, and deviations from protocol are routinely essential to interpreting a result and routinely absent.

## 10. Turn on the CI gate

`.github/workflows/validate.yml` runs on every PR. In repository settings, make it a **required status check** so a failing validation blocks the merge. Without that, "passing CI is the definition of ingestible" is a convention rather than a mechanism.

The `TransientCatalysis` org is on the **Team plan**, so this works on private repositories. (It did not on Free, and an earlier version of this guide told you to record the gap instead — that no longer applies.)

## 11. Check the whole tree

```bash
tcat-validate all .
```

`SKIP` lines mean the validator could not infer a document's kind from its location. Either move the file into the directory that matches it, or pass `--kind` explicitly.

## 12. Register what you deposited

A merged PR gets data into the repository; registering makes it findable. From a
checkout of [`tcat-index`](https://github.com/TransientCatalysis/tcat-index):

```bash
python scripts/register.py sample  ../my-spoke/samples/PSU-VOx-14.json
python scripts/register.py dataset ../my-spoke/manifests/prbs-run-014.json \
    --spoke my-spoke --site psu-rioux
python scripts/check_index.py
```

Sample first — a dataset whose `sample_id` does not resolve warns, because that
link is one the project's data-management plan explicitly commits to.

---

## Checklist

```
[ ] Named at whatever granularity matches who reviews and who needs access
[ ] Private
[ ] README placeholders filled in, template line removed
[ ] .tcat-spoke.json written, or the template deleted
[ ] LICENSE copyright filled in
[ ] Site registered in tcat-index, with an honest egress value
[ ] First calibration written in the TIME-INDEXED form
[ ] calibration_id generated, not hand-written
[ ] First sample registered, with measured properties and precursor lots
[ ] First protocol has everything needed to regenerate the waveform
[ ] First dataset validates locally
[ ] CI is a required status check
[ ] tcat-validate all . is clean
[ ] Deposited records registered in tcat-index
```

## Getting help

The validator's error messages name the field and its JSON pointer. If one is unclear, that is worth an issue on its own — a validator nobody can read gets routed around, and then the gate stops meaning anything.
