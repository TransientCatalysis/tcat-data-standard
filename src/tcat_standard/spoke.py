"""Spoke repository tooling: the manifest, CODEOWNERS, and the placeholder gate.

This lives in the data standard because `.tcat-spoke.json` is its schema, and
co-locating them is the mechanism by which "the metadata and the repository
permission cannot drift" is actually true. A generator living somewhere else
would be a second thing to keep in step with the schema, and it would be the one
that drifted.

It is not an implementation in the sense the hub rule forbids. There is no
science here -- no sensor model, no fitting method, no design criterion. It reads
one JSON file this package defines and writes a text file, which is the same
category of thing as the validator itself.

Both KINDS of spoke use it. Analysis spokes had no manifest at all before 0.2.0,
which is why they had nowhere to record who owned them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPOKE_MANIFEST = ".tcat-spoke.json"
CODEOWNERS = Path(".github") / "CODEOWNERS"

#: Strings that mean "this template was never filled in". A repository carrying
#: any of them is not configured, however green its other checks are.
PLACEHOLDERS = (
    "REPLACE",
    "[BRACKETED]",
    "tcat_spoke_example",
    "tcat-fit-example",
    "replace-me@example.com",
    "[YOUR NAME, EMAIL]",
    "[YOUR LAB / INSTITUTION]",
    "[WHO APPROVES CALIBRATION CHANGES]",
)

#: Files that are ALLOWED to contain placeholder strings: the template's own
#: scaffolding, and anything documenting the placeholders themselves.
PLACEHOLDER_EXEMPT = (
    ".git",
    ".tcat",
    "SPOKE-SETUP.md",
    "START-HERE.md",
    "bootstrap.py",
    "spoke.py",
    "test_spoke.py",
)

_TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yml", ".yaml", ".cff", ".txt", ".cfg"}

_HEADER = """\
# GENERATED from .tcat-spoke.json by `tcat-spoke codeowners`. Do not edit by hand.
#
# Edit the `stewards` block in the manifest instead. The metadata and the GitHub
# permission are generated from one source so that they cannot drift -- and when
# they drift, the one that is wrong is always the one nobody is looking at.
#
# Check it in CI with `tcat-spoke codeowners --check`.
"""


@dataclass
class Finding:
    """One problem, phrased so it can be acted on without reading the code."""

    where: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.where}: {self.message}"


@dataclass
class CodeownersResult:
    text: str
    findings: list[Finding] = field(default_factory=list)
    refused: bool = False


def load_manifest(root: Path) -> dict[str, Any] | None:
    """Read a spoke manifest, or None when there is none."""
    path = Path(root) / SPOKE_MANIFEST
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def _owner(steward: dict[str, Any]) -> str | None:
    handle = steward.get("github")
    return f"@{handle}" if handle else None


def _describe(steward: dict[str, Any]) -> str:
    bits = [steward.get("name", "?")]
    if steward.get("role"):
        bits.append(str(steward["role"]))
    if steward.get("institution"):
        bits.append(str(steward["institution"]))
    if steward.get("orcid"):
        bits.append(f"ORCID {steward['orcid']}")
    return " -- ".join(bits[:1] + [", ".join(bits[1:])]) if len(bits) > 1 else bits[0]


def build_codeowners(manifest: dict[str, Any]) -> CodeownersResult:
    """Render a CODEOWNERS file from a manifest's stewards block.

    Refuses rather than writing a file with no owners in it. A CODEOWNERS
    containing only comments is read by GitHub as "nobody owns this", while the
    repository looks governed -- which is worse than having no file, because the
    absence is at least visible.
    """
    stewards = manifest.get("stewards") or []
    findings: list[Finding] = []

    handled = [s for s in stewards if isinstance(s, dict) and _owner(s)]
    unhandled = [s for s in stewards if isinstance(s, dict) and not _owner(s)]

    lines = [_HEADER]
    for s in unhandled:
        # A comment, not silence. A quietly shortened owner list looks complete.
        lines.append(f"# no GitHub handle, so not an owner here: {_describe(s)}")
        findings.append(
            Finding(
                "stewards",
                f"{s.get('name', '?')} has no github handle, so they cannot own "
                "anything in CODEOWNERS. Recorded as a comment rather than dropped.",
            )
        )
    if unhandled:
        lines.append("")

    if not handled:
        findings.append(
            Finding(
                "stewards",
                "no steward has a github handle, so there is nobody to own this "
                "repository. Refusing to write a CODEOWNERS that grants nothing "
                "while looking as though it grants something.",
            )
        )
        return CodeownersResult(text="", findings=findings, refused=True)

    everyone = " ".join(sorted({_owner(s) for s in handled if _owner(s)}))
    lines.append(f"*\t{everyone}")

    # The calibration directory is the highest-value line in the file: it turns
    # "a calibration change is reviewed by whoever owns the instrument" from a
    # sentence in PROMOTION.md into a review GitHub will actually require.
    owners_of_instrument = sorted(
        {_owner(s) for s in handled if s.get("role") == "instrument_owner" and _owner(s)}
    )
    layout = manifest.get("layout") or {}
    for directory in layout.get("calibration") or []:
        if owners_of_instrument:
            lines.append(f"{directory.rstrip('/')}/\t{' '.join(owners_of_instrument)}")
        else:
            findings.append(
                Finding(
                    "stewards",
                    f"{directory}/ holds calibrations but no steward has "
                    "role=instrument_owner, so the review that matters most is "
                    "assigned to nobody in particular.",
                )
            )

    return CodeownersResult(text="\n".join(lines).rstrip() + "\n", findings=findings)


def find_placeholders(root: Path) -> list[Finding]:
    """Every surviving template placeholder, named by file and line.

    Nothing verified this before, so a spoke could be created, committed, and
    have green CI while its README still said REPLACE and its CITATION.cff
    credited nobody.
    """
    out: list[Finding] = []
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in PLACEHOLDER_EXEMPT for part in rel.parts):
            continue
        if rel.name in PLACEHOLDER_EXEMPT:
            continue
        # `_`-prefixed files are skipped by `tcat-validate all` and by the
        # registry's iter_records, precisely so they can carry REPLACE and
        # $comment keys as things to copy from. Flagging them here would
        # contradict the rule that makes them useful, and would train people to
        # ignore this check.
        if rel.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for token in PLACEHOLDERS:
                if token in line:
                    out.append(
                        Finding(f"{rel}:{n}", f"unfilled template placeholder {token!r}")
                    )
                    break
    return out


def check(root: Path) -> list[Finding]:
    """Everything that makes a spoke configured rather than merely created."""
    root = Path(root)
    findings: list[Finding] = []

    if (root / ".tcat" / "IS_TEMPLATE").is_file():
        # The template's own CI. Its placeholders SHOULD still be there; a
        # template whose placeholders were filled in is broken for everyone
        # downstream, so assert the opposite.
        if not find_placeholders(root):
            findings.append(
                Finding(
                    ".tcat/IS_TEMPLATE",
                    "this is the template, but no placeholders remain -- somebody "
                    "filled them in, and every repository created from it will "
                    "inherit their name.",
                )
            )
        return findings

    findings.extend(find_placeholders(root))

    manifest = load_manifest(root)
    if manifest is None:
        findings.append(
            Finding(
                SPOKE_MANIFEST,
                "no spoke manifest. Run `tcat-spoke init` -- it writes the "
                "manifest, fills the placeholders, and generates CODEOWNERS.",
            )
        )
        return findings

    result = build_codeowners(manifest)
    findings.extend(result.findings)

    committed = root / CODEOWNERS
    if result.refused:
        return findings
    if not committed.is_file():
        findings.append(
            Finding(str(CODEOWNERS), "missing. Run `tcat-spoke codeowners`.")
        )
    elif committed.read_text(encoding="utf-8") != result.text:
        findings.append(
            Finding(
                str(CODEOWNERS),
                "does not match the stewards block. Run `tcat-spoke codeowners` "
                "and commit the result -- do not edit it by hand.",
            )
        )
    return findings
