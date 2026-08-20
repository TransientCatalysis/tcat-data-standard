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

from .schema import CURRENT_SCHEMA_VERSION, KINDS, available_versions
from .validate import ValidationReport, validate_file

#: Directory-name conventions used by ``all`` to infer a document's kind, matching
#: the spoke template's layout.
_DIR_KIND = {
    "manifests": "dataset",
    "canonical": "dataset",
    "raw": "dataset",
    "derived": "dataset",
    "calibrations": "calibration",
    "protocols": "protocol",
    "provenance": "provenance",
    "ensembles": "uncertainty-ensemble",
}


def _infer_kind(path: Path) -> str | None:
    """Infer a document kind from its location, then from its own contents.

    Location first because it is cheap and, in a spoke laid out to the template,
    correct. Contents second because a hand-placed file should still be checked
    rather than skipped.
    """
    for part in reversed(path.parts[:-1]):
        if part in _DIR_KIND:
            return _DIR_KIND[part]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    if "calibration_id" in doc:
        return "calibration"
    if "artifact_id" in doc and "tool" in doc:
        return "provenance"
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

    if args.kind == "all":
        files: list[Path] = []
        for p in args.paths:
            files.extend(sorted(p.rglob("*.json")) if p.is_dir() else [p])
        for f in files:
            if f.name.startswith("_") or ".github" in f.parts:
                continue
            kind = _infer_kind(f)
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
            print(f"SKIP  could not infer document kind: {p}", file=sys.stderr)
        failed = sum(1 for r in reports if not r.ok)
        summary = f"{len(reports) - failed}/{len(reports)} passed"
        if skipped:
            summary += f", {len(skipped)} skipped"
        print(summary, file=sys.stderr)

    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
