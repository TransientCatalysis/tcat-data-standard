# derived/

**Regenerable. Safe to delete.**

Concentrations, fits, posteriors, designed experiments. Always reproducible from
raw plus a recorded transformation chain.

## The test for whether something belongs here

If deleting it loses information, it is not derived — the transformation chain has
a gap, and the gap is the bug.

That test is worth applying literally. It is the fastest way to find a step that
happened in a notebook nobody kept.

## Every derived artifact cites both of its parents

A derived concentration trace cites the **raw artifact id** *and* the
**calibration artifact id**. That pairing is what lets one calibration id be
swapped to re-derive every affected trace, and what lets `tcat-provenance
--reverse` name exactly which downstream fits went stale.

## Committing derived data at all is a choice

Two reasons to do it: a figure in a paper depends on it, or regenerating it is
expensive enough that the convenience is worth the bytes. Otherwise leave it in
the artifact store, where content addressing already means nobody recomputes it
twice.
