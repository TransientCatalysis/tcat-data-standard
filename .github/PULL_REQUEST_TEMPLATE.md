## What changes

<!-- One or two sentences. -->

## Kind of change

- [ ] Validator or tooling only — no schema change
- [ ] Schema **patch**: clarification, no structural change
- [ ] Schema **minor**: adds optional fields only; all existing data stays valid
- [ ] Schema **major**: breaks existing data (needs a migration script and a §6 justification)
- [ ] Documentation

## Checklist

- [ ] `pytest` passes
- [ ] If a field was added, it has a `description` that says **why** it exists, not just what it holds
- [ ] If the schema changed, `STANDARD.md`'s version header, changelog table, and `LAST_REVIEWED` are updated
- [ ] If a new version directory was created, the old one is **untouched** (STANDARD.md §6 — old versions are never removed or edited)
- [ ] `examples/make_examples.py` and `tests/make_fixtures.py` re-run, and the regenerated output is committed
- [ ] If the TRACE-AI pin moved, `profiles/trace-ai/crosswalk.md` and `enforcement.md` were re-read, not just the pin bumped

## Who is affected

<!-- Which spokes have to do something? "None" is a fine and preferred answer.
     Remember three institutions pin this repository. -->

## For a schema change: what would break

<!-- Name the datasets or repositories that would stop validating. If the answer
     is "nothing, because no real data exists yet", say so -- that window is
     open now and closes as soon as the first PRBS run lands. -->
