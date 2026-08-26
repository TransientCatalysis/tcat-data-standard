"""``tcat-validate`` -- the command CI runs.

Usage shapes::

    tcat-validate dataset path/to/dataset.json [more.json ...]
    tcat-validate calibration calibrations/*.json
    tcat-validate all some/spoke/          # walk a tree, infer kind per file
    tcat-validate versions                 # what schema versions are available

Exit status is 0 only when every document passed. Warnings never affect exit
status: advice that can fail a build stops being advice and starts being an
obstacle to route around.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from typing import Any

from .schema import CURRENT_SCHEMA_VERSION, KINDS, available_versions
from .validate import ValidationReport, validate, validate_file

#: The spoke manifest filename. Optional; a spoke with no manifest falls back to
#: the directory-name convention below.
SPOKE_MANIFEST = ".tcat-spoke.json"

#: DEFAULT directory-name conventions used by ``all`` to infer a document's kind.
#:
#: A default, not a requirement. A spoke organised by campaign, by student, by
#: instrument, or as a monorepo is equally valid -- the contract is per-RECORD, not
#: per-repository. A spoke that diverges declares its layout in
#: ``.tcat-spoke.json`` and this table is bypassed for the kinds it names.
_DIR_KIND = {
    "manifests": "dataset",
    "canonical": "dataset",
    "raw": "dataset",
    "derived": "dataset",
    "calibrations": "calibration",
    "protocols": "protocol",
    "provenance": "provenance",
    "ensembles": "uncertainty-ensemble",
    "samples": "sample",
    "models": "model",
    "specs": "model-spec",
    "mechanisms": "model-spec",
    "publications": "publication",
    "campaigns": "campaign",
    "artifacts": "provenance",
    "datasets": "dataset",
}


def _load_spoke_manifest(root: Path) -> dict[str, Any] | None:
    """Read ``.tcat-spoke.json`` from a walk root, if there is one.

    Its absence is the common and entirely fine case: the directory-name
    convention covers a spoke that has no reason to diverge.
    """
    path = root / SPOKE_MANIFEST if root.is_dir() else root.parent / SPOKE_MANIFEST
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _declared_layout(manifest: dict[str, Any] | None, root: Path) -> dict[Path, str]:
    """Map declared directories to kinds, resolved against the walk root."""
    out: dict[Path, str] = {}
    for kind, paths in ((manifest or {}).get("layout") or {}).items():
        for rel in paths:
            out[(root / rel).resolve()] = kind
    return out


def _infer_kind(
    path: Path,
    declared: dict[Path, str] | None = None,
) -> str | None:
    """Infer a document kind from its location, then from its own contents.

    Declared layout first, because a spoke that took the trouble to say where
    things are should be believed. Then the directory-name convention, which is
    cheap and correct for a spoke with no reason to diverge. Contents last,
    because a hand-placed file should still be checked rather than skipped.
    """
    if declared:
        resolved = path.resolve()
        for directory, kind in declared.items():
            if directory == resolved.parent or directory in resolved.parents:
                return kind

    for part in reversed(path.parts[:-1]):
        if part in _DIR_KIND:
            return _DIR_KIND[part]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    # Ordered most-specific first: a model document also carries a `metrics` key
    # that nothing else does, but a sample carries `sample_id` which a dataset
    # also has -- so the discriminating key has to be the unique one.
    if "calibration_id" in doc:
        return "calibration"
    if "model_id" in doc:
        return "model"
    if "spec_id" in doc and "family" in doc:
        return "model-spec"
    if "publication_id" in doc:
        return "publication"
    if "campaign_id" in doc:
        return "campaign"
    if "artifact_id" in doc and "tool" in doc:
        return "provenance"
    if "sample_id" in doc and "dataset_id" not in doc:
        return "sample"
    if "dataset_id" in doc:
        return "dataset"
    if "parameter_names" in doc and "samples" in doc:
        return "uncertainty-ensemble"
    if "protocol" in doc and "base_conditions" in doc:
        return "protocol"
    return None


def _report_lines(reports: list[ValidationReport], *, quiet: bool) -> None:
    for r in reports:
        if r.ok and quiet:
            continue
        print(r.render(), file=sys.stderr if not r.ok else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tcat-validate",
        description=(
            "Validate tcat documents against a pinned schema version. "
            "Passing this is the definition of ingestible."
        ),
    )
    ap.add_argument(
        "kind",
        choices=[*KINDS, "all", "versions"],
        help="document kind, 'all' to walk a tree and infer per file, or 'versions'",
    )
    ap.add_argument("paths", nargs="*", type=Path, help="files, or directories when kind is 'all'")
    ap.add_argument(
        "--schema-version",
        default=None,
        help=(
            "force a schema version instead of honouring each document's own "
            f"schema_version field (current: {CURRENT_SCHEMA_VERSION})"
        ),
    )
    ap.add_argument("--quiet", "-q", action="store_true", help="print only failures")
    ap.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit a machine-readable report instead of text",
    )
    args = ap.parse_args(argv)

    if args.kind == "versions":
        for v in available_versions():
            marker = " (current)" if v == CURRENT_SCHEMA_VERSION else ""
            print(f"{v}{marker}")
        return 0

    if not args.paths:
        ap.error("at least one path is required")

    reports: list[ValidationReport] = []
    skipped: list[Path] = []
    # Hoisted to sit with the other accumulators: the reporting tail below reads `strict`
    # on every path, including single-document validation, which never enters the `all`
    # branch. Left inside that branch it is an UnboundLocalError on `tcat-validate
    # calibration <file>`.
    strict = False

    if args.kind == "all":
        for root in args.paths:
            manifest = _load_spoke_manifest(root)
            declared = _declared_layout(manifest, root if root.is_dir() else root.parent)
            excluded = [
                (root / e).resolve() for e in ((manifest or {}).get("exclude") or [])
            ]
            strict = strict or bool((manifest or {}).get("strict"))

            if manifest is not None:
                report = validate(manifest, "spoke", source=str(root / SPOKE_MANIFEST))
                reports.append(report)
                if (manifest or {}).get("standard_version") and not args.schema_version:
                    # A spoke that pins a version means it; honour the pin unless
                    # the caller overrode it explicitly.
                    args.schema_version = manifest["standard_version"]

            files = sorted(root.rglob("*.json")) if root.is_dir() else [root]
            for f in files:
                if f.name.startswith("_") or ".github" in f.parts:
                    continue
                if f.name == SPOKE_MANIFEST:
                    continue
                resolved = f.resolve()
                if any(x == resolved or x in resolved.parents for x in excluded):
                    continue
                kind = _infer_kind(f, declared)
                if kind is None:
                    skipped.append(f)
                    continue
                reports.append(validate_file(f, kind, version=args.schema_version))
    else:
        for p in args.paths:
            reports.append(validate_file(p, args.kind, version=args.schema_version))

    if args.as_json:
        payload = {
            "ok": all(r.ok for r in reports),
            "checked": len(reports),
            "skipped": [str(p) for p in skipped],
            "reports": [
                {
                    "kind": r.kind,
                    "source": r.source,
                    "schema_version": r.schema_version,
                    "ok": r.ok,
                    "errors": [{"pointer": e.pointer, "message": e.message} for e in r.errors],
                    "warnings": [{"pointer": w.pointer, "message": w.message} for w in r.warnings],
                }
                for r in reports
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        _report_lines(reports, quiet=args.quiet)
        for p in skipped:
            label = "ERROR" if strict else "SKIP "
            print(f"{label} could not infer document kind: {p}", file=sys.stderr)
        failed = sum(1 for r in reports if not r.ok)
        summary = f"{len(reports) - failed}/{len(reports)} passed"
        if skipped:
            summary += f", {len(skipped)} {'unrecognised (strict)' if strict else 'skipped'}"
        print(summary, file=sys.stderr)

    if strict and skipped:
        # A spoke that turned on strict mode wants a stray file noticed.
        return 1
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
