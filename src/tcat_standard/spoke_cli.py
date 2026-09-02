"""`tcat-spoke` -- create a spoke, and keep it honest afterwards.

Three subcommands, and each exists because something was previously done by hand
and therefore sometimes not done at all:

    init        write the manifest, fill the placeholders, generate CODEOWNERS
    codeowners  regenerate CODEOWNERS from the stewards block (--check in CI)
    check       every placeholder filled, manifest present and valid, no drift

`init` is deliberately the only thing a newcomer has to run. The previous route
in was "use this template, then hand-edit REPLACE in five files", with nothing
verifying the edit happened.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .schema import CURRENT_SCHEMA_VERSION
from .spoke import (
    CODEOWNERS,
    SPOKE_MANIFEST,
    build_codeowners,
    check as check_spoke,
    load_manifest,
)
from .validate import validate

_ROLES = ("data_steward", "instrument_owner", "analysis_owner", "pi")


def _ask(prompt: str, default: str | None = None, *, required: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        got = input(f"{prompt}{suffix}: ").strip() or (default or "")
        if got or not required:
            return got
        print("  needed.", file=sys.stderr)


def _ask_choice(prompt: str, choices: tuple[str, ...], default: str) -> str:
    while True:
        got = _ask(f"{prompt} ({'/'.join(choices)})", default)
        if got in choices:
            return got
        print(f"  one of: {', '.join(choices)}", file=sys.stderr)


def _ask_stewards() -> list[dict[str, Any]]:
    print(
        "\nStewards -- who is answerable for this spoke NOW. This generates\n"
        ".github/CODEOWNERS, so a handle here is a real repository permission.\n"
        "At least one needs a GitHub handle, or CODEOWNERS cannot be written.\n"
    )
    out: list[dict[str, Any]] = []
    while True:
        s: dict[str, Any] = {"name": _ask("  name")}
        s["institution"] = _ask("  institution")
        s["role"] = _ask_choice("  role", _ROLES, "data_steward")
        for key, prompt in (("github", "  github handle"), ("orcid", "  ORCID")):
            got = _ask(prompt, required=False)
            if got:
                s[key] = got
        out.append(s)
        if _ask("  add another steward?", "n").lower() not in ("y", "yes"):
            break
    return out


def _default_slug(root: Path) -> str:
    return root.resolve().name


def _gather(root: Path, answers: dict[str, Any] | None) -> dict[str, Any]:
    if answers is not None:
        return answers
    print(f"Creating a spoke in {root.resolve()}\n")
    kind = _ask_choice("Kind", ("data", "analysis"), "data")
    manifest: dict[str, Any] = {
        "standard_version": CURRENT_SCHEMA_VERSION,
        "spoke_id": _ask("Spoke id (lowercase, hyphens)", _default_slug(root)),
        "kind": kind,
        "name": _ask("Human-readable name", required=False),
        "stewards": _ask_stewards(),
    }
    if kind == "data":
        manifest["granularity"] = _ask(
            "Granularity (lab / student / instrument / campaign / monorepo)",
            "campaign",
            required=False,
        )
    rung = _ask_choice(
        "Default maturity for records that make no claim", ("sandbox", "working"), "sandbox"
    )
    manifest["maturity"] = {"rung": rung}
    return {k: v for k, v in manifest.items() if v not in ("", None)}


def _fill_placeholders(root: Path, manifest: dict[str, Any]) -> list[Path]:
    """Substitute the template's placeholders from the manifest.

    Best-effort and reported: what it cannot infer, `tcat-spoke check` will
    name, which is better than a silent partial fill.
    """
    stewards = manifest.get("stewards") or [{}]
    first = stewards[0]
    subs = {
        "[BRACKETED]": manifest.get("name") or manifest["spoke_id"],
        "[YOUR NAME, EMAIL]": f"{first.get('name', '')} <{first.get('email', '')}>".strip(),
        "[YOUR LAB / INSTITUTION]": first.get("institution", ""),
        "[WHO APPROVES CALIBRATION CHANGES]": next(
            (s.get("name", "") for s in stewards if s.get("role") == "instrument_owner"),
            "",
        ),
    }
    touched: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".cff", ".toml"}:
            continue
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for token, value in subs.items():
            if value:
                new = new.replace(token, value)
        if new != text:
            path.write_text(new, encoding="utf-8")
            touched.append(path.relative_to(root))
    return touched


def _rename_package(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Rename the analysis template's example package to this spoke's own.

    The data side needs none of this: a data spoke has no package. The analysis
    side does, and renaming it by hand means a directory move plus edits in
    pyproject.toml, the README, the tool module, two test files, and the CI
    workflow -- seven places, and missing any one of them leaves a spoke that
    installs a package named after the template, or a workflow that
    conformance-checks a command nobody installs.

    Derived from `spoke_id` so the package, the command and the repository share
    a name. Someone implementing a tool other than `tcat-fit` still has to change
    the `--as` argument, and the summary printed at the end says so.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", manifest["spoke_id"].lower()).strip("_")
    package = f"tcat_{slug}"
    command = f"tcat-fit-{slug.replace('_', '-')}"

    old_pkg, old_cmd = "tcat_spoke_example", "tcat-fit-example"
    src = root / "src" / old_pkg
    if not src.is_dir():
        return []

    changed: list[str] = []
    src.rename(root / "src" / package)
    changed.append(f"src/{old_pkg}/ -> src/{package}/")

    # Build artifacts from an editable install in the template. They describe
    # the OLD package and are regenerated on install, so they are removed rather
    # than rewritten.
    for stale in (root / "src").glob("*.egg-info"):
        shutil.rmtree(stale)
        changed.append(f"removed {stale.relative_to(root)} (stale build artifact)")

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".toml", ".md", ".yml", ".yaml"}:
            continue
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        new = text.replace(old_pkg, package).replace(old_cmd, command)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(str(path.relative_to(root)))
    return changed


def _fill_citation(root: Path, manifest: dict[str, Any]) -> bool:
    """Fill CITATION.cff from the manifest.

    Separate from the token substitution because this file is structured rather
    than templated: its placeholders are whole YAML values, and one of them is a
    LIST of authors that has to be rebuilt from the stewards block rather than
    string-replaced. It is also the file most likely to be left unfilled and
    least likely to be noticed, since nothing reads it until somebody tries to
    cite the spoke.
    """
    path = root / "CITATION.cff"
    if not path.is_file():
        return False
    import datetime

    stewards = [s for s in (manifest.get("stewards") or []) if s.get("name")]
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    name = manifest.get("name") or manifest["spoke_id"]
    skipping_authors = False

    for line in lines:
        if skipping_authors:
            # consume the templated author block
            if line.startswith("  ") or line.startswith("    "):
                continue
            skipping_authors = False

        if line.startswith("title:"):
            out.append(f'title: "{name} -- transient kinetics spoke"')
        elif line.strip().startswith("REPLACE. What"):
            kind = manifest.get("kind", "data")
            out.append(
                f"  {name}. Replace this with "
                + (
                    "what this spoke implements and which declared tool it conforms to."
                    if kind == "analysis"
                    else "what was measured, on what system, by what method."
                )
            )
        elif line.startswith("date-released:"):
            out.append(f'date-released: "{datetime.date.today().isoformat()}"')
        elif line.startswith("repository-code:") and "REPLACE" in line:
            out.append(
                f'repository-code: "https://github.com/TransientCatalysis/'
                f'{manifest["spoke_id"]}"'
            )
        elif line.startswith("authors:"):
            out.append("authors:")
            for st in stewards:
                parts = st["name"].rsplit(" ", 1)
                given, family = (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])
                out.append(f"  - family-names: {family}")
                if given:
                    out.append(f"    given-names: {given}")
                if st.get("institution"):
                    out.append(f"    affiliation: {st['institution']}")
                if st.get("orcid"):
                    out.append(f'    orcid: "https://orcid.org/{st["orcid"]}"')
            skipping_authors = True
        elif line.startswith("    version:") and "0.1.0" in line:
            out.append(f'    version: "{CURRENT_SCHEMA_VERSION}"')
        else:
            out.append(line)

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def _fill_pyproject(root: Path, manifest: dict[str, Any]) -> bool:
    """Fill an analysis spoke's pyproject from the manifest.

    The template leaves `name`, `description`, `authors` and the Homepage url as
    valid-but-placeholder values on purpose, so that it installs and
    `tcat-conform` runs before anyone has edited anything -- a template you must
    fix before you can try it is one people abandon at step one. That is the
    right default for the TEMPLATE and the wrong one for a spoke, where it means
    a published package credited to "REPLACE ME".
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return False
    stewards = [s for s in (manifest.get("stewards") or []) if s.get("name")]
    text = path.read_text(encoding="utf-8")
    before = text

    text = text.replace(
        'name = "tcat-spoke-example"', f'name = "{manifest["spoke_id"]}"'
    )
    text = text.replace(
        'description = "REPLACE -- what this spoke implements, in one line."',
        f'description = "{manifest.get("name") or manifest["spoke_id"]}"',
    )
    if stewards:
        authors = ", ".join(
            "{ name = \"%s\"%s }"
            % (s["name"], f', email = "{s["email"]}"' if s.get("email") else "")
            for s in stewards
        )
        text = text.replace(
            'authors = [{ name = "REPLACE ME", email = "replace-me@example.com" }]',
            f"authors = [{authors}]",
        )
    text = text.replace(
        "https://github.com/TransientCatalysis/REPLACE",
        f"https://github.com/TransientCatalysis/{manifest['spoke_id']}",
    )
    if text != before:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def _write_codeowners(root: Path, manifest: dict[str, Any]) -> bool:
    result = build_codeowners(manifest)
    for f in result.findings:
        print(f"  note: {f}", file=sys.stderr)
    if result.refused:
        return False
    target = root / CODEOWNERS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.text, encoding="utf-8")
    return True


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path)
    target = root / SPOKE_MANIFEST
    if target.exists() and not args.force:
        print(f"{target} already exists; --force to overwrite", file=sys.stderr)
        return 1

    answers = json.loads(Path(args.answers).read_text()) if args.answers else None
    manifest = _gather(root, answers)

    report = validate(manifest, "spoke")
    if not report.ok:
        print(report.render(), file=sys.stderr)
        return 1

    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SPOKE_MANIFEST}")

    for rel in _fill_placeholders(root, manifest):
        print(f"filled placeholders in {rel}")
    if _fill_citation(root, manifest):
        print("filled CITATION.cff from the stewards block")

    if manifest.get("kind") == "analysis":
        for line in _rename_package(root, manifest):
            print(f"renamed: {line}")
        if _fill_pyproject(root, manifest):
            print("filled pyproject.toml from the manifest")

    if _write_codeowners(root, manifest):
        print(f"wrote {CODEOWNERS}")

    sentinel = root / ".tcat" / "IS_TEMPLATE"
    if sentinel.is_file():
        sentinel.unlink()
        print("removed .tcat/IS_TEMPLATE -- this is a spoke now, not a template")

    remaining = check_spoke(root)
    print()
    if remaining:
        print("Still to do:", file=sys.stderr)
        for f in remaining:
            print(f"  {f}", file=sys.stderr)
    else:
        print("Nothing outstanding. Next:")
        print(f"  tcat-validate all {root}")
    if report.warnings:
        print("\nAdvice on the manifest:", file=sys.stderr)
        for w in report.warnings:
            print(f"  {w.pointer}: {w.message}", file=sys.stderr)
    return 0


def _cmd_codeowners(args: argparse.Namespace) -> int:
    root = Path(args.path)
    manifest = load_manifest(root)
    if manifest is None:
        if (root / CODEOWNERS).is_file():
            print(
                f"{CODEOWNERS} exists but there is no {SPOKE_MANIFEST}, so it was "
                "written by hand and nothing keeps it in step with anyone's "
                "actual role. Run `tcat-spoke init`.",
                file=sys.stderr,
            )
            return 1
        return 0  # not a spoke; not this tool's business

    result = build_codeowners(manifest)
    for f in result.findings:
        print(f"note: {f}", file=sys.stderr)
    if result.refused:
        return 1

    target = root / CODEOWNERS
    if args.check:
        if not target.is_file():
            print(f"{CODEOWNERS} is missing. Run `tcat-spoke codeowners`.", file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8") != result.text:
            print(
                f"{CODEOWNERS} does not match the stewards block. Run "
                "`tcat-spoke codeowners` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{CODEOWNERS} matches the manifest")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.text, encoding="utf-8")
    print(f"wrote {CODEOWNERS}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.path)
    is_template = (root / ".tcat" / "IS_TEMPLATE").is_file()
    findings = check_spoke(root)
    if not findings:
        # Say which check passed. In the template the check is INVERTED -- it
        # asserts the placeholders survive -- and reporting that as "configured"
        # would describe the opposite of what was verified.
        print(
            "template intact: placeholders still present for repositories made from it"
            if is_template
            else "spoke is configured"
        )
        return 0
    for f in findings:
        print(f, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tcat-spoke",
        description=(
            "Create a spoke and keep it honest. `init` replaces hand-editing "
            "template placeholders; `check` is the CI gate that nothing was left "
            "unfilled."
        ),
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create the manifest, fill placeholders, write CODEOWNERS")
    p.add_argument("path", nargs="?", default=".", type=Path)
    p.add_argument("--answers", help="a JSON file of answers, so an agent can drive this")
    p.add_argument("--force", action="store_true", help="overwrite an existing manifest")
    p.set_defaults(func=_cmd_init)

    p = sub.add_parser("codeowners", help="generate .github/CODEOWNERS from the manifest")
    p.add_argument("path", nargs="?", default=".", type=Path)
    p.add_argument("--check", action="store_true", help="fail if it has drifted")
    p.set_defaults(func=_cmd_codeowners)

    p = sub.add_parser("check", help="placeholders filled, manifest present, CODEOWNERS current")
    p.add_argument("path", nargs="?", default=".", type=Path)
    p.set_defaults(func=_cmd_check)

    args = ap.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
