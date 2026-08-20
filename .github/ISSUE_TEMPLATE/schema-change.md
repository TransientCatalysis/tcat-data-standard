---
name: Schema change request
about: Propose adding, promoting, or changing a field in the data standard
title: "[schema] "
labels: ["schema"]
---

<!--
Read STANDARD.md §6 first. The short version: a field is promoted into the schema
once the same field appears independently in THREE labs' `extensions`. Schema
follows practice; it does not predict it.

If you need to record something today, put it in `extensions` and open this issue.
The validator ignores `extensions` rather than rejecting it, so nothing blocks you
in the meantime.
-->

## What do you need to record?

<!-- The information, not the field name. What question does it answer? -->

## Are you blocked right now?

- [ ] No — I am recording it in `extensions` and this is a promotion request
- [ ] Yes — the validator is rejecting something it should accept (say what)

## If this is a promotion request: where else does it already appear?

Promotion needs the same field, independently, in three labs. List where:

| Lab | Repository / dataset | Field name used there |
|---|---|---|
| | | |
| | | |
| | | |

<!-- Different names for the same thing still count -- reconciling the names is
     part of what promotion is for. -->

## Proposed field

```json
{
  "field_name": {
    "type": "",
    "description": ""
  }
}
```

- [ ] Optional (minor bump — existing data stays valid)
- [ ] Required (**major** bump — needs a migration script and a reason why data written without it is unusable)

## Would retrofitting this later lose information?

<!-- This is the question that decides required vs optional. `status` and
     `batch_id` are required because a deleted failed run and a lost batch
     grouping cannot be recovered. Most fields are not like that. -->

## Which document kinds does it belong on?

- [ ] dataset
- [ ] manifest-entry
- [ ] calibration
- [ ] provenance
- [ ] uncertainty-ensemble
- [ ] protocol

## TRACE-AI

Does this correspond to a checklist item, or to a gap in the upstream standard?
If it is a gap, it may belong in the transient-kinetics profile we contribute
back — see `profiles/trace-ai/crosswalk.md`.
