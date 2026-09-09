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


# ---------------------------------------------------------------- fingerprint

FINGERPRINT = ".tcat-fingerprint.json"

#: What can change a tool's OUTPUT: the code that ships in the wheel.
#:
#: Tests, docs, notebooks and examples are deliberately excluded. They can be
#: edited freely without a version bump, which is the point -- a rule that fired
#: on a typo in a docstring would be turned off within a week.
_SHIPPED = ("src",)


def source_digest(root: Path) -> tuple[str, int]:
    """Byte-level digest of everything under `src/`, and how many files went into it.

    The REPOSITORY-level fingerprint: sorted, path-qualified, content-hashed, so
    it changes if and only if any shipped byte changes -- docstrings included.
    Kept for the notebook builders' "did the source move under this run" guard,
    where any change at all is the question. For IDENTITY, which must not move on
    a comment, see `normalised_source_digest`.
    """
    import hashlib
    root = Path(root)
    files = sorted(
        p for base in _SHIPPED for p in (root / base).rglob("*.py")
        if "__pycache__" not in p.parts and ".egg-info" not in str(p)
    )
    h = hashlib.sha256()
    for f in files:
        h.update(str(f.relative_to(root)).encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest(), len(files)


def _strip_docstrings(tree):
    """Remove every docstring. Comments never reach the AST, so they are gone already."""
    import ast
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return tree


def normalised_source_digest(package_dir: Path) -> tuple[str, int]:
    """The IDENTITY digest of one package: sha256 over (module name, normalised AST) pairs.

    Four properties, each pinned by a test, each load-bearing for the identity
    rule in CONTRACT.md:

    * a docstring or comment edit does not move it -- prose is not behaviour, and
      a rule that re-hashed every artifact on a typo would be switched off within
      a week;
    * a code edit does move it -- behaviour is behaviour, and nobody has to
      remember to bump anything for a bug fix;
    * it is independent of where the package sits on disk, so extracting a
      package to its own repository is a directory move that leaves every
      artifact id where it is;
    * it is independent of the package DIRECTORY's name (module names are
      relative to the package), because the package name is carried separately
      as the tool's name.

    A file that does not parse contributes its raw bytes under a `!raw:` marker
    rather than being skipped: skipping would let a broken module change
    behaviour without changing identity, which is the one failure this exists
    to prevent.
    """
    import ast
    import hashlib
    package_dir = Path(package_dir)
    files = sorted(p for p in package_dir.rglob("*.py") if "__pycache__" not in p.parts)
    h = hashlib.sha256()
    for f in files:
        rel = f.relative_to(package_dir).with_suffix("").as_posix()
        raw = f.read_bytes()
        try:
            dumped = ast.dump(_strip_docstrings(ast.parse(raw)), include_attributes=False).encode()
        except SyntaxError:
            dumped = b"!raw:" + raw
        h.update(rel.encode()); h.update(b"\0"); h.update(dumped); h.update(b"\0")
    return h.hexdigest(), len(files)


#: Where a package may declare `__version__`, in the order searched. `version.py`
#: is here because re-exporting (`from .version import __version__`) is a normal
#: layout and the regex cannot see through an import -- the analysis hub does
#: exactly that, so the fingerprint could not read its version at all and the one
#: repository in the project with shipped source went ungated. Duplicating the
#: literal into `__init__.py` to satisfy the reader would create two places to
#: forget, which is the drift this check exists to catch.
_VERSION_FILES = ("__init__.py", "version.py", "_version.py")


def packages(root: Path) -> list[Path]:
    """Every importable package shipped under `src/`, in name order."""
    src = Path(root) / "src"
    if not src.is_dir():
        return []
    return sorted(p for p in src.iterdir()
                  if p.is_dir() and (p / "__init__.py").is_file() and ".egg-info" not in p.name)


def package_version(package_dir: Path) -> str | None:
    """A package's declared `__version__`, read rather than imported.

    Read rather than imported: importing a spoke means installing its
    dependencies, and this check has to run in a CI job that may deliberately
    not have them.
    """
    import re
    for name in _VERSION_FILES:
        path = Path(package_dir) / name
        if path.is_file():
            m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', path.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1)
    return None


def read_version(root: Path) -> str | None:
    """The FIRST package's `__version__` under `src/`. Kept for callers that assume
    one package per repository; a multi-package repository should use
    `package_version` per package, which is what the fingerprint does."""
    for pkg in packages(root):
        v = package_version(pkg)
        if v:
            return v
    return None


def fingerprint_record(root: Path) -> dict:
    """What `.tcat-fingerprint.json` holds: per package, the contract version and
    the identity digest of the source as committed."""
    return {
        "$comment": (
            "GENERATED by `tcat-spoke fingerprint`. Per shipped package: the CONTRACT version "
            "and the normalised source digest at this commit. The digest, not the version, is "
            "what identifies the code in an artifact id (tool_version = <version>+<digest8>), and "
            "it is computed from the installed source at run time -- so this file is not what "
            "makes identity work. It is the INDEX from a digest found in an artifact's provenance "
            "back to the commit that produced it (`git log -S<digest8> -- .tcat-fingerprint.json`), "
            "which is how a defect recorded against a digest is traced. CI fails when it is out "
            "of date, because an index with a gap cannot answer that question. Do not edit by hand."
        ),
        "format": 2,
        "packages": {
            p.name: {
                "version": package_version(p) or "unknown",
                "digest": normalised_source_digest(p)[0],
                "files": normalised_source_digest(p)[1],
            }
            for p in packages(Path(root))
        },
    }


def check_fingerprint(root: Path) -> list[Finding]:
    """Is the committed fingerprint the current source?

    Before 2026-09-08 this asked "did the code change without the version
    changing?", because the hand-maintained version was what invalidated a cache.
    Identity now derives from the source itself, so a code change with no version
    bump is the NORMAL case and not a finding. What the file guards instead is
    the digest-to-commit index described in `fingerprint_record`: a stale file
    means a digest that appears in provenance cannot be traced to a commit.

    THE HONEST LIMIT: this watches `src/`. A behaviour change that arrives
    through a dependency the tool does not list, a data file, or a compiled
    extension will not appear in any digest. Those are real, and this is not a
    substitute for thinking -- it is a floor under the cases that are easy to miss.
    """
    root = Path(root)
    pkgs = packages(root)
    if not pkgs:
        return []  # not a packaged spoke; nothing ships
    path = root / FINGERPRINT
    if not path.is_file():
        return [Finding(FINGERPRINT,
                        "missing. Run `tcat-spoke fingerprint` and commit it -- without it a digest in an "
                        "artifact's provenance cannot be traced back to the commit that produced it.")]
    recorded = json.loads(path.read_text(encoding="utf-8"))
    if recorded.get("format") != 2:
        return [Finding(FINGERPRINT,
                        "is in the pre-2026-09-08 single-version format. Run `tcat-spoke fingerprint` "
                        "and commit the result.")]
    findings = []
    current = fingerprint_record(root)["packages"]
    for name, now in current.items():
        was = recorded.get("packages", {}).get(name)
        if was is None:
            findings.append(Finding(FINGERPRINT, f"{name}: not recorded. Run `tcat-spoke fingerprint` and commit."))
            continue
        if now["version"] == "unknown":
            findings.append(Finding(FINGERPRINT, f"{name}: no __version__ in {'/'.join(_VERSION_FILES)}."))
        if was.get("version") != now["version"] or was.get("digest") != now["digest"]:
            findings.append(Finding(
                FINGERPRINT,
                f"{name}: out of date (recorded {was.get('version')}+{str(was.get('digest'))[:8]}, "
                f"source is {now['version']}+{now['digest'][:8]}). Run `tcat-spoke fingerprint` and "
                f"commit the result in the same commit as the change, so the digest this source "
                f"stamps into provenance is traceable to a commit."))
    for name in set(recorded.get("packages", {})) - set(current):
        findings.append(Finding(FINGERPRINT, f"{name}: recorded but no longer shipped. Run `tcat-spoke fingerprint`."))
    return findings


def write_fingerprint(root: Path) -> dict:
    """Record every shipped package's version and identity digest."""
    root = Path(root)
    record = fingerprint_record(root)
    (root / FINGERPRINT).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


