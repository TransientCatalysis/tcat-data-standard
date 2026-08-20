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
    source: str = "<in-memory>",
) -> ValidationReport:
    """Validate one document of a given kind.

    If the document declares its own ``schema_version`` and no explicit version
    was requested, that declared version is used. This is the point of recording
    it: data is checked against the standard it was written against, not against
    whatever the standard has since become.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown document kind {kind!r}; expected one of {', '.join(KINDS)}")

    declared = document.get("schema_version") if isinstance(document, dict) else None
    effective = version or declared or CURRENT_SCHEMA_VERSION

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


def _structural_errors(document: Any, kind: str) -> list[Problem]:
    """Errors phrased for a human, for rules JSON Schema states unreadably.

    These are real errors and do fail CI. They are additive to the schema check,
    not a replacement: the schema remains the authority on what is valid, and
    this function only improves how a violation is described.
    """
    out: list[Problem] = []
    if not isinstance(document, dict):
        return out

    if kind == "manifest-entry":
        p = _manifest_location_problem(document, "")
        if p:
            out.append(p)

    if kind == "dataset":
        for i, entry in enumerate(document.get("files") or []):
            p = _manifest_location_problem(entry, f"/files/{i}")
            if p:
                out.append(p)

    if kind == "uncertainty-ensemble":
        p = _manifest_location_problem(document.get("samples"), "/samples")
        if p:
            out.append(p)

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
            if unc.get("kind") == "none":
                out.append(
                    Problem(f"/channels/{name}/uncertainty", "channel declares no uncertainty")
                )
            if (unc.get("noise_model") or {}).get("family") == "unknown":
                out.append(
                    Problem(f"/channels/{name}/uncertainty/noise_model", "noise model is 'unknown'")
                )

    if kind == "calibration":
        entries = document.get("entries") or []
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
validate_publication = _validate_kind("publication")


def validate_file(path: str | Path, kind: str, *, version: str | None = None) -> ValidationReport:
    """Validate a JSON document on disk."""
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
    return validate(document, kind, version=version, source=str(path))


def validate_or_raise(document: dict[str, Any], kind: str, *, version: str | None = None) -> None:
    """Validate, raising :class:`ValidationError` on failure.

    Used by tools that must refuse to emit an artifact when the data does not
    validate -- ``tcat-ingest`` in particular. Refusing to write is the point:
    an invalid canonical artifact in the store is worse than no artifact.
    """
    report = validate(document, kind, version=version)
    if not report.ok:
        raise ValidationError(report.render(show_warnings=False))
