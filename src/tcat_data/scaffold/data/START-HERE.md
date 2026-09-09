# Start here

**You have data. This turns it into something the rest of the project can find,
cite, and build on — without you having to reorganise how you work.**

That is the whole promise. If it starts asking you to restructure your
directories or rename your samples, something has gone wrong; say so in an issue.

You do not need to read the standard first. It is 500 lines and it is a reference,
not a tutorial.

---

## What you are about to make

A **data spoke**: a repository holding your measurements, plus a small JSON
document per measurement saying what it is, what the units are, and where the
bytes live. Those documents are what makes the data findable later — by you, in
eighteen months, as much as by anyone else.

**What it is not:** it is not a new place to keep your files, and not a rewrite of
your workflow. Raw files stay raw. The instrument keeps writing what it writes.

---

## What you need

Python and a browser. Nothing else.

```bash
pip install "git+https://github.com/TransientCatalysis/tcat-data-standard.git"
```

If `pip` is not a command you have, install Python from python.org first, or ask
— that is a completely normal place to be stuck and not worth an afternoon.

---

## 1. Make the repository

One command, from the data standard's package (there is no template repository to clone):

```bash
tcat-spoke init --kind data <your-repo>
```

It writes the whole skeleton and then asks who is answerable for it.

Name it after whatever unit you actually work in — your lab, yourself, one
campaign, one instrument. **There is no right answer and it is not a commitment**;
the registry records which spoke holds what, so re-carving later is a metadata
update rather than a migration. The one shape worth avoiding is one repository
per dataset, because a repository is a unit of review and access control and
neither of those varies per dataset.

Then clone it:

```bash
git clone https://github.com/TransientCatalysis/<your-repo>.git
cd <your-repo>
```

## 2. Run one command

```bash
tcat-spoke init
```

It asks about eight questions and then writes everything: the spoke manifest,
your `.github/CODEOWNERS`, your `CITATION.cff` with real authors and ORCIDs, and
it fills in every placeholder in the README.

Two of the questions are worth thinking about for a moment:

- **Stewards.** Who is answerable for this repository *now*. This is the one
  answer with a consequence outside the file: `.github/CODEOWNERS` is generated
  from it, so a GitHub handle here is a real review permission. Name whoever
  owns the instrument too — a calibration change is their review, and that only
  works if the file says who they are.
- **Maturity.** Say `sandbox`. It means *this may change without notice and
  nobody should depend on it yet*, which is true, and saying so is worth more
  than a claim you have not earned. You raise it later, per record, when it is
  earned.

## 3. Describe one measurement

Copy `manifests/_example.json` to `manifests/<something>.json` and edit it to
describe **one** run. Not all of them. One.

The files starting with `_` are examples and are skipped by every check, so you
can leave them alone and copy from them forever.

Two fields people get wrong, and both are worth getting right the first time
because neither can be reconstructed afterwards:

- **`batch_id`** — one synthesis batch, one catalyst charge, one beamtime.
  Anything that must never be split across a train/test boundary later.
- **`status`** — `ok`, `flagged`, or `failed`. **Flag, never delete.** A failed
  run you kept is a row in the exclusion table at publication; a failed run you
  deleted is a hole in it.

Never type a checksum by hand. Compute it:

```python
from tcat_data import ManifestEntry
print(ManifestEntry.from_file("raw/my-run.csv", format="csv"))
```

## 4. Check it

```bash
tcat-validate all .
```

Errors name the field and the file. **Warnings are advice and never fail
anything** — you can leave them, and the honest thing to do with one you have
decided to live with is to record it rather than silence it.

When that is clean, you have a spoke. Everything past here is optional and can
wait.

---

## Then what

- `SPOKE-SETUP.md` is the full checklist, including registering the spoke so
  other people can find it.
- Turn on the CI gate (it is already in `.github/workflows/`) so the check runs
  on every push instead of only when you remember.
- The worked example on real data is
  [`tcat-data-psu-coox`](https://github.com/TransientCatalysis/tcat-data-psu-coox)
  — 26 PSU CO-oxidation runs, and `scripts/build_records.py` is 905 lines of
  what this actually looks like once it is real. Read it when the example here
  runs out.

## If you get stuck

Open an issue on this template. Genuinely — a confusing error message here is a
bug in the tooling, not a gap in your knowledge, and it is the single most useful
thing you can report. The people who wrote this have all been reading it for
months and can no longer see what is missing from it.
