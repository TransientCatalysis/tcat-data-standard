# TRACE-AI profile

This standard is a **profile of** the TRACE-AI reporting guidelines, not an invention alongside them.

The distinction matters for a practical reason. The stated ambition is that this outlives one project and becomes a community resource for transient kinetics. A standard presented as an *extension of* an existing community guideline is credible on those terms; a standard presented as a *rival* to one has to win an argument it does not need to have. TRACE-AI already has the community, the checklist, and the publication route.

Two of this project's investigators — Medford and Kitchin — are co-authors on the TRACE-AI paper, which makes contributing a transient-kinetics profile back upstream a realistic output rather than a hopeful one. See "Contribution opportunity" below.

## Files here

| File | What it is |
|---|---|
| `pin.json` | The exact upstream version we profile, with SHAs verified against the live repository, and why it is not the version the infrastructure spec named. |
| `crosswalk.md` | Field-by-field mapping between TRACE-AI's `data-manifest-template.yaml` and our `dataset.schema.json`. |
| `enforcement.md` | Which checklist items are enforced in CI, which are required schema fields, and which are deferred to manuscript time — and why the split falls where it does. |

## The short version

- **Adopted as required schema fields:** item **A5** (negative/failed data policy) becomes `status` + `status_reason`; item **B2** (data-split leakage) becomes `batch_id` + `lineage_id`. Both are required in 0.1.0 rather than added later, because retrofitting either means the information is already lost.
- **Adopted as a recorded field:** autonomy level (A0–A5). Nearly free to record now, impossible later.
- **Adopted as-is:** the format recommendations — CSV for tabular, Zarr for bulk arrays, JSON for metadata.
- **Enforced in CI:** data items **A1–A4** only.
- **Deferred to manuscript time:** sections **B**, **C**, **D**, via a report generator run against accumulated provenance records. Not a commit gate.
- **Deferred entirely:** the agent card, and ontology / controlled-vocabulary alignment.

## Where we deliberately diverge

**TRACE-AI is a reporting standard, not an operational data model.** It is written to be filled in at publication. Enforcing publication-time requirements on every commit would be intolerable, and intolerable process gets routed around — which costs more than not having had it. So the split is: things that are unrecoverable if not captured at write time are enforced continuously; things that are assembled at write-up are assembled at write-up.

**The agent card is deferred.** The full card (observation space, action space, objectives, constraints, policy, tool access, safety checks, seeds) targets unattended closed loops. This project sits at A1–A2, human-gated. Recording the autonomy level is nearly free; the card waits until something genuinely runs unattended, at which point it will be written against the real loop rather than an imagined one.

**Ontology alignment is skipped for now.** It is aspirational even in the paper. Vocabulary is allowed to emerge through the `extensions` namespace and gets promoted once the same field shows up independently in three labs — see STANDARD.md §6.

## Contribution opportunity

Transient kinetics, operando spectroscopy, stiff solvers, and model-based design of experiments are genuinely underspecified in TRACE-AI, which is written around steady-state screening and closed-loop synthesis. Specifically absent upstream:

- perturbation waveforms as first-class, regenerable objects (our `protocol.schema.json`)
- time-base alignment across simultaneously-acquired modalities
- sensor models as versioned, citable artifacts distinct from the data they transform
- parameter uncertainty as a *sample* rather than a summary, with frequentist and Bayesian output in one shape

A transient-kinetics profile contributed upstream is a natural output of this work, and the crosswalk in this directory is the first draft of it.
