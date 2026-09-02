"""Validation. Passing this is the definition of 'ingestible'.

Runs in CI on every pull request to any spoke repository. That is the whole
enforcement mechanism: not a review convention, not a checklist someone
remembers, a status check that fails.

Two design choices worth stating:

* Errors name the offending field and give its JSON pointer. A validator whose
  output is "does not match schema" gets routed around within a week.
* ``extensions`` is ignored, never rejected. Labs need somewhere to put a field
  the standard has not caught up with yet, and the alternative is that they stop
  recording it or stop running the validator. When the same field shows up
  independently in three labs' extensions, it gets promoted into the schema
  proper -- schema follows practice, it does not predict it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .schema import CURRENT_SCHEMA_VERSION, KINDS, load_all_schemas, load_schema


class ValidationError(Exception):
    """Raised by the ``*_or_raise`` helpers when a document is invalid."""


@dataclass(frozen=True)
class Problem:
    """One validation failure, located."""

    pointer: str
    message: str
    schema_pointer: str = ""

    def __str__(self) -> str:
        where = self.pointer or "<root>"
        return f"{where}: {self.message}"


@dataclass
class ValidationReport:
    """Result of validating one document."""

    kind: str
    source: str
    schema_version: str
    errors: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok

    def render(self, *, show_warnings: bool = True) -> str:
        """Human-readable summary, for the CLI and for CI logs."""
        head = f"{'PASS' if self.ok else 'FAIL'}  {self.kind}  {self.source}"
        lines = [head]
        for p in self.errors:
            lines.append(f"  error   {p}")
        if show_warnings:
            for p in self.warnings:
                lines.append(f"  warning {p}")
        return "\n".join(lines)


def _registry(version: str | None):
    """Build a reference registry so cross-file ``$ref``s resolve offline.

    Schemas reference each other by ``$id`` (a https:// URI that is a stable
    name, not a fetchable address). Registering every document up front means
    validation never touches the network -- which matters because this runs in CI
    and, eventually, on compute nodes that may have no egress at all.
    """
    from referencing import Registry, Resource

    docs = load_all_schemas(version)
    # Every document declares $schema, so from_contents infers the dialect and
    # no default specification is needed.
    return Registry().with_resources(
        (doc_id, Resource.from_contents(doc)) for doc_id, doc in docs.items()
    )


def _validator(kind: str, version: str | None):
    from jsonschema import Draft202012Validator

    schema = load_schema(kind, version)
    return Draft202012Validator(schema, registry=_registry(version))


def _pointer(path: Iterable[Any]) -> str:
    parts = []
    for p in path:
        parts.append(str(p))
    return "/" + "/".join(parts) if parts else ""


def validate(
    document: dict[str, Any],
    kind: str,
    *,
    version: str | None = None,
    fallback_version: str | None = None,
    source: str = "<in-memory>",
) -> ValidationReport:
    """Validate one document of a given kind.

    Version precedence, highest first:

    1. ``version`` -- an explicit, deliberate override. Only ``--schema-version``
       sets it, and its help text says what it does.
    2. the document's own ``schema_version``. This is the point of recording it:
       data is checked against the standard it was written against, not against
       whatever the standard has since become.
    3. ``fallback_version`` -- a default for documents that declare nothing, which
       is how a spoke manifest's ``standard_version`` is applied.
    4. ``CURRENT_SCHEMA_VERSION``.

    A spoke pin is deliberately WEAKER than a document's own declaration. It used
    to be stronger, which meant that adding a manifest pinned one version above a
    tree of documents written against another silently revalidated all of them
    against a schema they had never been checked against -- and the failures read
    as "the schema change broke the data" rather than "the pin was applied to the
    wrong thing". A spoke legitimately holds documents at several versions, and
    usually will, because a version bump does not oblige a lab to rewrite data.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown document kind {kind!r}; expected one of {', '.join(KINDS)}")

    declared = document.get("schema_version") if isinstance(document, dict) else None
    effective = version or declared or fallback_version or CURRENT_SCHEMA_VERSION

    report = ValidationReport(kind=kind, source=source, schema_version=effective)

    try:
        validator = _validator(kind, effective)
    except FileNotFoundError as exc:
        report.errors.append(Problem("/schema_version", str(exc)))
        return report

    for err in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
        report.errors.append(
            Problem(
                pointer=_pointer(err.absolute_path),
                message=err.message,
                schema_pointer=_pointer(err.absolute_schema_path),
            )
        )

    report.errors.extend(_structural_errors(document, kind))
    report.warnings.extend(_advisory_checks(document, kind, effective))
    # Last, and deliberately: a `working` claim is checked against the warnings
    # this document actually raised, so it has to run after they exist.
    report.warnings.extend(_maturity_advice(document, kind, report.warnings))
    if kind == "spoke":
        report.warnings.extend(_steward_advice(document))
    return report


_LOCATION_FIELDS = ("path", "url", "lfs_oid")


def _manifest_location_problem(entry: Any, pointer: str) -> Problem | None:
    """Explain a manifest entry's location cardinality in words.

    JSON Schema can enforce "exactly one of path, url, lfs_oid" but cannot say so
    readably -- the raw failure dumps the whole object and names no field. Since
    this is the single most load-bearing rule in the standard, and the one a lab
    will hit first when relocating a dataset off-repo, it gets a real message.
    """
    if not isinstance(entry, dict):
        return None
    present = [f for f in _LOCATION_FIELDS if entry.get(f) is not None]
    if len(present) == 1:
        return None
    if not present:
        return Problem(
            pointer,
            "manifest entry has no location: set exactly one of path, url, or lfs_oid",
        )
    return Problem(
        pointer,
        f"manifest entry has {len(present)} locations ({', '.join(present)}); set exactly "
        "one. To move data off-repo, REPLACE path with url or lfs_oid rather than adding "
        "alongside it -- the checksum is what proves the bytes are unchanged.",
    )


_WAVEFORM_REQUIRED = {
    "lfsr": ("register_length", "taps", "seed", "bit_period_s", "n_bits"),
    "recorded": ("switch_times_s",),
    "reconstructed": ("tracer_channel", "reason"),
}


def _waveform_problems(protocol: Any, prefix: str) -> list[Problem]:
    """Name the missing waveform field.

    A oneOf failure reports only "not valid under any of the given schemas",
    which is exactly the kind of error the standard promises not to emit: the
    reader is left to work out which of three forms they were writing and what
    it wanted. The schema stays the authority on validity; this says which field
    is missing.
    """
    out: list[Problem] = []
    if not isinstance(protocol, dict) or protocol.get("protocol") != "prbs":
        return out
    params = protocol.get("parameters")
    if not isinstance(params, dict) or "waveform" not in params:
        return out
    wave = params["waveform"]
    at = f"{prefix}/parameters/waveform"
    if not isinstance(wave, dict):
        return out

    form = wave.get("form")
    if form is None:
        out.append(
            Problem(
                f"{at}/form",
                "waveform has no form: must be one of lfsr (a generator spec), "
                "recorded (the executed switch schedule), or reconstructed "
                "(recovered from a tracer, with the reason it had to be)",
            )
        )
        return out
    if form not in _WAVEFORM_REQUIRED:
        out.append(
            Problem(
                f"{at}/form",
                f"unknown waveform form {form!r}: expected lfsr, recorded, or reconstructed",
            )
        )
        return out

    for field in _WAVEFORM_REQUIRED[form]:
        if field not in wave:
            out.append(
                Problem(f"{at}/{field}", f"waveform form {form!r} requires {field}")
            )
    return out


_MATURITY_KINDS = frozenset(
    {
        "dataset",
        "sample",
        "model",
        "model-spec",
        "calibration",
        "protocol",
        "uncertainty-ensemble",
        "campaign",
    }
)

#: What each rung requires, and the sentence that explains why.
_RUNG_REQUIREMENTS: dict[str, tuple[tuple[str, ...], str]] = {
    "internally_reviewed": (
        ("reviewed_by", "reviewed_on", "review_scope"),
        "someone other than the producer checked this record and said what they "
        'checked. "The team looked at it" is how that obligation quietly becomes '
        "nothing -- the same rule the publication record applies to "
        "reproducibility_reviewer",
    ),
    "published": (
        ("reviewed_by", "reviewed_on", "review_scope", "published_in"),
        "released alongside a publication that has passed the release gate in "
        "tcat-index/RELEASE.md. This rung REFERENCES that gate rather than "
        "restating it, so it needs to name the publication",
    ),
    "superseded": (
        ("superseded_by", "superseded_reason"),
        "a better record of the same thing exists and a reader who lands here "
        "needs to be sent to it. A retirement with no forward pointer is a dead end",
    ),
}


def _maturity_errors(document: Any, kind: str) -> list[Problem]:
    """Say what a maturity rung requires, in the words of the rung.

    JSON Schema enforces these through `if`/`then`, and reports them as
    "'reviewed_by' is a required property" against a schema pointer nobody
    reads. Same rule, better message -- no new law. The `anyOf` on a person is
    the worst of them: it surfaces as "is not valid under any of the given
    schemas", which tells a reader nothing about what to type.
    """
    out: list[Problem] = []
    maturity = document.get("maturity")
    if not isinstance(maturity, dict):
        return out

    rung = maturity.get("rung")
    required, why = _RUNG_REQUIREMENTS.get(rung, ((), ""))
    missing = [f for f in required if not maturity.get(f)]
    if missing:
        out.append(
            Problem(
                f"/maturity/{missing[0]}",
                f"rung {rung!r} requires {', '.join(missing)}: {why}",
            )
        )

    reviewer = maturity.get("reviewed_by")
    if isinstance(reviewer, dict) and not (reviewer.get("orcid") or reviewer.get("github")):
        out.append(
            Problem(
                "/maturity/reviewed_by",
                "a reviewer needs an orcid or a github handle, not just a name. "
                "People change institutions and share names, and a review "
                "attributed to a string nobody can resolve is a review nobody "
                "can ask about",
            )
        )
    return out


def _structural_errors(document: Any, kind: str) -> list[Problem]:
    """Errors phrased for a human, for rules JSON Schema states unreadably.

    These are real errors and do fail CI. They are additive to the schema check,
    not a replacement: the schema remains the authority on what is valid, and
    this function only improves how a violation is described.
    """
    out: list[Problem] = []
    if not isinstance(document, dict):
        return out

    # Deliberately a set-membership test rather than an `if kind == ...` anchor:
    # this function and _advisory_checks share those anchors, and a careless bulk
    # edit has already once landed a block in both and turned warnings into
    # errors. A different shape cannot be copied across by accident.
    if kind in _MATURITY_KINDS or kind == "spoke":
        out.extend(_maturity_errors(document, kind))

    if kind == "manifest-entry":
        p = _manifest_location_problem(document, "")
        if p:
            out.append(p)

    if kind == "dataset":
        for i, entry in enumerate(document.get("files") or []):
            p = _manifest_location_problem(entry, f"/files/{i}")
            if p:
                out.append(p)
        out.extend(_waveform_problems(document.get("protocol"), "/protocol"))
        out.extend(_channel_reference_errors(document.get("channels")))

    if kind == "protocol":
        out.extend(_waveform_problems(document, ""))
        out.extend(_bed_uncertainty_errors(document, ""))

    if kind == "dataset":
        out.extend(_bed_uncertainty_errors(document.get("protocol"), "/protocol"))

    if kind == "uncertainty-ensemble":
        p = _manifest_location_problem(document.get("samples"), "/samples")
        if p:
            out.append(p)

    return out


def _bed_uncertainty_errors(protocol: Any, prefix: str) -> list[Problem]:
    """A bed.uncertainty key must name a sibling bed field that exists.

    An error rather than advice, by the `_channel_reference_errors` rule: a key
    naming nothing looks satisfied right up until something tries to use the
    sigma, and then it silently applies to no quantity at all.
    """
    out: list[Problem] = []
    if not isinstance(protocol, dict):
        return out
    bed = (protocol.get("base_conditions") or {}).get("bed")
    if not isinstance(bed, dict):
        return out
    uncertainty = bed.get("uncertainty")
    if not isinstance(uncertainty, dict):
        return out
    siblings = {k for k in bed if k not in ("uncertainty", "source", "notes")}
    for key in uncertainty:
        if key not in siblings:
            out.append(
                Problem(
                    f"{prefix}/base_conditions/bed/uncertainty/{key}",
                    f"names no bed field (declared: {', '.join(sorted(siblings)) or 'none'})",
                )
            )
    return out


def _channel_reference_errors(channels: Any) -> list[Problem]:
    """Channel fields that name another channel must name one that exists.

    An error rather than advice, and deliberately not the same judgement as
    `_time_base_advice`: that function warns when a channel names NO time
    column, which is a gap a reader can see. This one catches a name that
    resolves to nothing, which a reader cannot -- the reference looks satisfied
    right up until something tries to follow it.
    """
    out: list[Problem] = []
    if not isinstance(channels, dict):
        return out

    for name, ch in channels.items():
        if not isinstance(ch, dict):
            continue
        referring = [("time_column", ch.get("time_column"))]
        censoring = ch.get("censoring")
        if isinstance(censoring, dict):
            referring.append(("censoring/flag_column", censoring.get("flag_column")))
        for field, target in referring:
            if target is None:
                continue
            if target not in channels:
                out.append(
                    Problem(
                        f"/channels/{name}/{field}",
                        f"names channel {target!r}, which is not declared in "
                        f"/channels (declared: {', '.join(sorted(channels)) or 'none'})",
                    )
                )
    return out


def _censoring_advice(channels: Any) -> list[Problem]:
    """Advice about censored channels.

    Advisory because a censored channel is legal and common -- the point is that
    a reader, and a fitting tool, can see it. The fraction threshold exists
    because censoring changes from a footnote to the dominant feature of a
    dataset somewhere in this range, and nobody computes the number by hand.
    """
    out: list[Problem] = []
    if not isinstance(channels, dict):
        return out

    for name, ch in channels.items():
        if not isinstance(ch, dict):
            continue
        censoring = ch.get("censoring")
        if not isinstance(censoring, dict) or censoring.get("kind") in (None, "none"):
            continue
        if not censoring.get("flag_column"):
            out.append(
                Problem(
                    f"/channels/{name}/censoring/flag_column",
                    "channel is censored but names no flag column, so censored points "
                    "can only be found by comparing against the bound -- which also "
                    "catches values that genuinely landed on it",
                )
            )
        fraction = censoring.get("fraction_censored")
        if isinstance(fraction, (int, float)) and fraction >= 0.05:
            out.append(
                Problem(
                    f"/channels/{name}/censoring/fraction_censored",
                    f"{fraction:.1%} of this channel is a bound rather than a "
                    "measurement; a least-squares fit will treat every one of those "
                    "as an exact observation unless it reads the censoring block",
                )
            )
    return out


def _time_base_advice(time_base: Any, channels: Any) -> list[Problem]:
    """Advice about a time base, for any document that carries one.

    Advisory rather than structural because both gaps are legal states of real
    legacy data: the point is that they be visible, not that they be rejected.
    """
    out: list[Problem] = []
    if not isinstance(time_base, dict):
        return out

    if "t0" not in time_base and not time_base.get("t0_absent_reason"):
        out.append(
            Problem(
                "/time_base",
                "no absolute t0 and no t0_absent_reason: without one of the two, "
                "nothing records whether this trace can be aligned to another modality",
            )
        )

    if time_base.get("kind") == "per_channel" and isinstance(channels, dict):
        for name, ch in channels.items():
            if not isinstance(ch, dict) or ch.get("quantity") == "time":
                continue
            # An exact channel is bookkeeping -- a scan counter, an index, a
            # censoring flag -- not a quantity observed at an instant, so asking
            # which timestamps apply to it has no answer to be missing.
            if (ch.get("uncertainty") or {}).get(
                    "noise_model", {}).get("family") == "exact":
                continue
            if not ch.get("time_column"):
                out.append(
                    Problem(
                        f"/channels/{name}/time_column",
                        "time base is per_channel but this channel names no time_column, "
                        "so which timestamps apply to it is left to the reader to guess",
                    )
                )
    return out


def _maturity_advice(document: Any, kind: str, raised: list[Problem]) -> list[Problem]:
    """Advice about a maturity claim. Never an error -- see _advisory_checks.

    `raised` is the set of warnings this document already produced, which is what
    lets `working` be checkable: the claim is "the validator is quiet, or every
    remaining warning is named in warnings_accepted". That makes this the only
    place an advisory check has a consequence, and the consequence attaches to a
    VOLUNTARY claim rather than to CI.
    """
    out: list[Problem] = []
    maturity = document.get("maturity")
    if not isinstance(maturity, dict):
        # Deliberately silent. Absence means `sandbox`, which is true, and
        # warning on every record that has made no claim is how people learn to
        # skip the warnings that mean something.
        return out

    rung = maturity.get("rung")
    if rung and rung != "sandbox" and not maturity.get("entered_at"):
        out.append(
            Problem(
                "/maturity/entered_at",
                f"rung {rung!r} with no date. A claim that cannot be aged is the "
                "one that quietly goes stale",
            )
        )

    if rung in ("working", "internally_reviewed", "published"):
        accepted = {
            w.get("pointer")
            for w in (maturity.get("warnings_accepted") or [])
            if isinstance(w, dict)
        }
        unaccounted = [w.pointer for w in raised if w.pointer not in accepted]
        if unaccounted:
            shown = ", ".join(unaccounted[:4]) + ("..." if len(unaccounted) > 4 else "")
            out.append(
                Problem(
                    "/maturity/rung",
                    f"claims {rung!r}, but {len(unaccounted)} advisory warning(s) are "
                    f"neither fixed nor listed in warnings_accepted: {shown}",
                )
            )

    reviewer = maturity.get("reviewed_by")
    if isinstance(reviewer, dict) and rung in ("internally_reviewed", "published"):
        producers = _named_people(document)
        rname = (reviewer.get("orcid") or reviewer.get("github") or reviewer.get("name") or "")
        if rname and producers and {rname} >= producers:
            out.append(
                Problem(
                    "/maturity/reviewed_by",
                    "the reviewer is the only person this record names. A one-person "
                    "spoke is real, so this is advice rather than a refusal -- but a "
                    "second name that did not review anything would be worse",
                )
            )

    reviewed_on = maturity.get("reviewed_on")
    newest = _newest_timestamp(document)
    if reviewed_on and newest and str(reviewed_on) < newest[:10]:
        out.append(
            Problem(
                "/maturity/reviewed_on",
                f"reviewed {reviewed_on}, but this record carries content from "
                f"{newest[:10]}. A badge outliving its review is the failure mode",
            )
        )

    out.extend(_permanent_home_advice(document, rung))

    if rung == "published" and document.get("access_status") != "public":
        out.append(
            Problem(
                "/maturity/rung",
                f"claims 'published' while access_status is "
                f"{document.get('access_status')!r}. Mid-release the two are "
                "legitimately out of step for a few minutes; in the registry it is "
                "an error, because that is the record of what was actually released",
            )
        )
    return out


def _permanent_home_advice(document: Any, rung: str | None) -> list[Problem]:
    """At `internally_reviewed` and above, the bytes need a permanent home.

    PI rule, 2026-09-01: data feeding sandbox and working pipelines may live
    wherever it is convenient -- a lab share, OneDrive, a scratch filesystem.
    The moment a record claims someone else checked it, somebody may cite it,
    and a citation pointing at a revocable location is a citation that will
    break without anyone noticing.

    Checked rather than asserted, because "we should really deposit that" is how
    the obligation quietly becomes nothing.

    A `url` entry is the case this catches: it means the bytes are somewhere this
    project does not control, and a share link can be revoked, re-issued, or
    expire with an institutional account. `path` (in the repository, so in git)
    and `lfs_oid` are as durable as the repository itself. A `deposit_doi` on the
    maturity block settles it either way, because that is a promise a repository
    has made rather than one a share link implies.
    """
    out: list[Problem] = []
    if rung not in ("internally_reviewed", "published"):
        return out

    maturity = document.get("maturity") or {}
    if maturity.get("deposit_doi"):
        return out

    for i, entry in enumerate(document.get("files") or []):
        if isinstance(entry, dict) and entry.get("url"):
            out.append(
                Problem(
                    f"/files/{i}/url",
                    f"rung {rung!r} but the bytes are at a url this project does "
                    "not control, and no deposit_doi is recorded. A share link "
                    "can be revoked or expire with an account, and a reviewed "
                    "record is one somebody may cite. Deposit it and record the "
                    "DOI, or keep the copy in the repository",
                )
            )
    return out


def _named_people(document: Any) -> set[str]:
    """Everyone this record names as producer or steward, by best handle."""
    out: set[str] = set()
    for block in ("personnel", "stewards"):
        for person in document.get(block) or []:
            if isinstance(person, dict):
                handle = person.get("orcid") or person.get("github") or person.get("name")
                if handle:
                    out.add(handle)
    return out


def _newest_timestamp(document: Any) -> str | None:
    """The newest ISO timestamp the record carries, for the stale-review check."""
    stamps: list[str] = []
    prov = document.get("provenance")
    if isinstance(prov, dict) and isinstance(prov.get("created_at"), str):
        stamps.append(prov["created_at"])
    for entry in document.get("entries") or []:
        if isinstance(entry, dict) and isinstance(entry.get("valid_from"), str):
            stamps.append(entry["valid_from"])
    return max(stamps) if stamps else None


def _steward_advice(document: Any) -> list[Problem]:
    """Advice about a spoke manifest's stewards block."""
    out: list[Problem] = []
    stewards = document.get("stewards")
    if not isinstance(stewards, list) or not stewards:
        return out

    roles = {s.get("role") for s in stewards if isinstance(s, dict)}
    if "data_steward" not in roles and "analysis_owner" not in roles:
        out.append(
            Problem(
                "/stewards",
                "no data_steward and no analysis_owner, so the generated CODEOWNERS "
                "has no owner for the repository as a whole",
            )
        )
    if not any(isinstance(s, dict) and s.get("github") for s in stewards):
        out.append(
            Problem(
                "/stewards",
                "no steward has a github handle, so CODEOWNERS cannot be generated "
                "and the metadata and the repository permission cannot be kept in step",
            )
        )
    if not any(isinstance(s, dict) and s.get("orcid") for s in stewards):
        out.append(
            Problem(
                "/stewards",
                "no steward has an ORCID. A person named only by a string cannot be "
                "resolved once they leave the project",
            )
        )
    layout = document.get("layout") or {}
    if layout.get("calibration") and "instrument_owner" not in roles:
        out.append(
            Problem(
                "/stewards",
                "this spoke holds calibrations but names no instrument_owner. A "
                "calibration change is reviewed by whoever owns the instrument, and "
                "the review is worthless if nobody knows who that is",
            )
        )
    return out


def _advisory_checks(document: Any, kind: str, version: str) -> list[Problem]:
    """Checks that are advice, not law.

    Kept strictly separate from errors. A warning must never fail CI: the moment
    style advice can block a merge, people stop running the validator locally and
    start discovering it at the worst possible time.
    """
    out: list[Problem] = []
    if not isinstance(document, dict):
        return out

    if kind == "dataset":
        if document.get("schema_version") and document["schema_version"] != CURRENT_SCHEMA_VERSION:
            out.append(
                Problem(
                    "/schema_version",
                    f"written against {document['schema_version']}, current is "
                    f"{CURRENT_SCHEMA_VERSION}; still valid, no action required",
                )
            )
        if document.get("layer") == "derived" and "calibration_ref" not in document:
            out.append(
                Problem(
                    "/calibration_ref",
                    "derived layer with no calibration_ref: if a sensor model was applied, "
                    "cite it -- that citation is what lets the trace be re-derived later",
                )
            )
        if document.get("access_status") in ("internal", "staged") and "embargo_until" not in document:
            out.append(
                Problem(
                    "/embargo_until",
                    "unreleased data with no expected release date",
                )
            )
        if not document.get("notes"):
            out.append(
                Problem(
                    "/notes",
                    "no narrative notes: pretreatment history, reactor conditioning, and "
                    "protocol deviations are routinely essential and rarely recoverable later",
                )
            )
        for name, ch in (document.get("channels") or {}).items():
            unc = (ch or {}).get("uncertainty") or {}
            family = (unc.get("noise_model") or {}).get("family")
            # An exact channel -- a flag, an index -- has no sigma to be missing.
            # Warning about it forever would train readers to skip the warning
            # that means a real measurement lost its uncertainty.
            if unc.get("kind") == "none" and family != "exact":
                out.append(
                    Problem(f"/channels/{name}/uncertainty", "channel declares no uncertainty")
                )
            if (unc.get("noise_model") or {}).get("family") == "unknown":
                out.append(
                    Problem(f"/channels/{name}/uncertainty/noise_model", "noise model is 'unknown'")
                )
        out.extend(_time_base_advice(document.get("time_base"), document.get("channels")))
        out.extend(_censoring_advice(document.get("channels")))

    if kind == "calibration":
        entries = document.get("entries") or []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            for target, detail in (entry.get("declared_unused") or {}).items():
                out.append(
                    Problem(
                        f"/entries/{i}/declared_unused/{target}",
                        f"this export declared {target} = "
                        f"{(detail or {}).get('value')!r} and applied something else; "
                        "which value is physically right is a question for the "
                        "instrument owner",
                    )
                )
            for name, ch in (entry.get("channels") or {}).items():
                if isinstance(ch, dict) and ch.get("floor") is not None:
                    out.append(
                        Problem(
                            f"/entries/{i}/channels/{name}/floor",
                            f"clamps at {ch['floor']!r}; datasets derived through it should "
                            "carry a matching censoring block on this channel, or the clamp "
                            "becomes indistinguishable from a measurement downstream",
                        )
                    )
        stamps = [e.get("valid_from") for e in entries if isinstance(e, dict)]
        if stamps != sorted(stamps):
            out.append(Problem("/entries", "entries are not in ascending valid_from order"))
        if len(entries) == 1:
            out.append(
                Problem(
                    "/entries",
                    "single-entry (fixed) calibration -- valid, and the degenerate case of a "
                    "time-indexed one; no action needed",
                )
            )
        if document.get("kind") == "ms_sensitivity":
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                mentions = "fragment" in (entry.get("notes") or "").lower() or "fragment" in (
                    document.get("notes") or ""
                ).lower()
                if not entry.get("fragmentation_matrix_ref") and not mentions:
                    out.append(
                        Problem(
                            f"/entries/{i}/fragmentation_matrix_ref",
                            "MS sensitivity calibration that neither cites a fragmentation "
                            "matrix nor says why none applies; on a shared m/z an uncorrected "
                            "cracking contribution is indistinguishable from signal",
                        )
                    )

    if kind == "model-spec":
        body = document.get("mechanism")
        declared = document.get("free_parameters")
        if isinstance(body, dict) and isinstance(declared, list):
            implied = 0
            for step in body.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                implied += 1
                if step.get("reversible") and not step.get("constraint"):
                    implied += 1
            if implied != len(declared):
                out.append(
                    Problem(
                        "/free_parameters",
                        f"{len(declared)} parameters declared but the steps imply "
                        f"{implied} free rate constants. Legitimate when the model "
                        "carries parameters that are not rate constants (a site "
                        "density, a calibration scale) -- but if it does not, one of "
                        "the two is wrong, and a fit would pack the vector one way "
                        "while a reader interprets it the other",
                    )
                )
        if document.get("parameter_transform", "none") == "none" and body:
            out.append(
                Problem(
                    "/parameter_transform",
                    "no parameter transform declared for a microkinetic model. Rate "
                    "constants span decades; fitting them linearly is usually a "
                    "mistake, and an interval reported in the wrong space means "
                    "something else entirely",
                )
            )

    if kind == "sample":
        if not document.get("properties"):
            out.append(
                Problem(
                    "/properties",
                    "no independently measured catalyst properties recorded. Milestone M9 "
                    "is a join between a fitted rate constant and a property recorded HERE; "
                    "if it lives in a notebook, that milestone becomes a spreadsheet exercise",
                )
            )
        if not (document.get("synthesis") or {}).get("precursors"):
            out.append(Problem("/synthesis/precursors", "no precursors recorded"))
        if not document.get("identifiers"):
            out.append(
                Problem(
                    "/identifiers",
                    "no chemical identifiers; the DMSP commits to using them when available",
                )
            )

    if kind == "model":
        if not document.get("limitations"):
            out.append(
                Problem(
                    "/limitations",
                    "no stated limitations on appropriate use. The DMSP requires them, and a "
                    "model released without limits will be applied outside them by someone "
                    "who did not fit it",
                )
            )
        if not document.get("uncertainty_ref"):
            out.append(
                Problem(
                    "/uncertainty_ref",
                    "no uncertainty ensemble cited; a point estimate alone cannot be used for "
                    "experiment design and must not be mistaken for a characterised result",
                )
            )
        splits = (document.get("training_data") or {}).get("splits")
        if not splits:
            out.append(
                Problem(
                    "/training_data/splits",
                    "no split strategy declared (TRACE-AI B2). Catalysis data has shared "
                    "lineages and repeated conditions, so an unstated split is usually a "
                    "leaked one",
                )
            )
        elif "none" in (splits.get("grouped_by") or []):
            out.append(
                Problem(
                    "/training_data/splits/grouped_by",
                    "ungrouped split. For this project's data that is almost always leakage: "
                    "same-batch data must stay within one split",
                )
            )
        for name, metric in (document.get("metrics") or {}).items():
            if isinstance(metric, dict) and "interval" not in metric:
                out.append(
                    Problem(
                        f"/metrics/{name}",
                        "no interval; a bare number is best-only reporting (TRACE-AI B3)",
                    )
                )
        if not document.get("example_use"):
            out.append(Problem("/example_use", "no runnable example cited (TRACE-AI D1)"))

    if kind == "publication":
        status = document.get("status")
        if status in ("accepted", "published"):
            if not document.get("deposits"):
                out.append(
                    Problem(
                        "/deposits",
                        "accepted or published with no deposit recorded. Supporting data is "
                        "due no later than publication",
                    )
                )
            if not document.get("reproducibility_reviewed"):
                out.append(
                    Problem(
                        "/reproducibility_reviewed",
                        "reproducibility package not marked reviewed; the DMSP requires review "
                        "before release",
                    )
                )
            unreported = [
                d.get("doi")
                for d in (document.get("deposits") or [])
                if not d.get("osti_reported")
            ]
            if unreported:
                out.append(
                    Problem(
                        "/deposits",
                        f"{len(unreported)} deposit(s) not yet reported to DOE OSTI",
                    )
                )
        figures = [
            a for a in (document.get("artifacts") or [])
            if a.get("role") in ("figure", "table")
        ]
        if status in ("accepted", "published") and not figures:
            out.append(
                Problem(
                    "/artifacts",
                    "no artifact carries role 'figure' or 'table'; those are the ones whose "
                    "underlying data must be public at publication",
                )
            )

    if kind == "uncertainty-ensemble":
        names = document.get("parameter_names") or []
        point = document.get("point_estimate") or []
        if names and point and len(names) != len(point):
            out.append(
                Problem(
                    "/point_estimate",
                    f"length {len(point)} does not match parameter_names length {len(names)}",
                )
            )
        units = document.get("parameter_units")
        if names and units and len(units) != len(names):
            out.append(Problem("/parameter_units", "length does not match parameter_names"))
        if not units:
            out.append(Problem("/parameter_units", "no units declared for fitted parameters"))
        if document.get("method_family") == "asymptotic":
            out.append(
                Problem(
                    "/method_family",
                    "asymptotic ensemble: usable for design, but not a sampled posterior",
                )
            )
        roles = document.get("parameter_roles")
        if names and roles and len(roles) != len(names):
            out.append(
                Problem(
                    "/parameter_roles",
                    f"length {len(roles)} does not match parameter_names length {len(names)}",
                )
            )
        conditioning = document.get("conditioning")
        if isinstance(conditioning, dict):
            if (conditioning.get("kind") in ("marginalized", "profiled")
                    and not conditioning.get("marginalized")):
                out.append(
                    Problem(
                        "/conditioning/marginalized",
                        f"kind={conditioning.get('kind')!r} but no nuisance quantities "
                        "are named; name them or the claim is unverifiable",
                    )
                )
        components = document.get("components")
        if isinstance(components, list) and components:
            total = sum(c.get("weight", 0) for c in components
                        if isinstance(c, dict))
            if abs(total - 1.0) > 1e-6:
                out.append(
                    Problem(
                        "/components",
                        f"mixture weights sum to {total:.6g}, not 1",
                    )
                )
            if document.get("method_family") != "sampled":
                out.append(
                    Problem(
                        "/components",
                        "a mixture's samples are a weighted resample, which is a "
                        "sampled family; method_family says "
                        f"{document.get('method_family')!r}",
                    )
                )

    return out


def _validate_kind(kind: str):
    def _fn(document, *, version=None, source="<in-memory>"):
        return validate(document, kind, version=version, source=source)

    _fn.__name__ = f"validate_{kind.replace('-', '_')}"
    _fn.__doc__ = f"Validate one {kind} document. See :func:`validate`."
    return _fn


validate_dataset = _validate_kind("dataset")
validate_manifest_entry = _validate_kind("manifest-entry")
validate_calibration = _validate_kind("calibration")
validate_provenance = _validate_kind("provenance")
validate_uncertainty_ensemble = _validate_kind("uncertainty-ensemble")
validate_protocol = _validate_kind("protocol")
validate_sample = _validate_kind("sample")
validate_model = _validate_kind("model")
validate_model_spec = _validate_kind("model-spec")
validate_publication = _validate_kind("publication")
validate_spoke = _validate_kind("spoke")
validate_campaign = _validate_kind("campaign")


def validate_file(
    path: str | Path,
    kind: str,
    *,
    version: str | None = None,
    fallback_version: str | None = None,
) -> ValidationReport:
    """Validate a JSON document on disk. See :func:`validate` for precedence."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ValidationReport(
            kind=kind,
            source=str(path),
            schema_version=version or CURRENT_SCHEMA_VERSION,
            errors=[Problem("", f"not valid JSON: {exc}")],
        )
    return validate(
        document, kind, version=version, fallback_version=fallback_version, source=str(path)
    )


def validate_or_raise(document: dict[str, Any], kind: str, *, version: str | None = None) -> None:
    """Validate, raising :class:`ValidationError` on failure.

    Used by tools that must refuse to emit an artifact when the data does not
    validate -- ``tcat-ingest`` in particular. Refusing to write is the point:
    an invalid canonical artifact in the store is worse than no artifact.
    """
    report = validate(document, kind, version=version)
    if not report.ok:
        raise ValidationError(report.render(show_warnings=False))
