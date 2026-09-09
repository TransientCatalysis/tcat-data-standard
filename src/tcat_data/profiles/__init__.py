"""Machine-readable profile data: vendored upstream checklists and our claims.

Package data, not repo-root files, for the same reason the schema tree is
(STANDARD.md, and the `wheel` CI job): a validator or report generator installed
from a wheel must be able to find these. A repo-root `profiles/` directory does
not ship, and the failure mode is silent -- a generator that cannot find its
checklist has nothing to check against and can only emit an empty one.

The prose lives at the repository root under `profiles/trace-ai/`: the crosswalk,
the enforcement split, and the pin. That is documentation and is meant to be read
by people. What is here is what code loads.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


class ProfileNotFound(FileNotFoundError):
    """A profile file that should ship with the package is missing.

    Raised loudly rather than returning an empty checklist, because a report
    generator with no checklist would emit a document that looks complete and
    asserts nothing.
    """


def _load(relative: str) -> dict:
    path = HERE / relative
    if not path.exists():
        raise ProfileNotFound(
            f"{relative} is missing from the installed package. It is package data; "
            f"if this is an editable install the file should be at {path}. A wheel "
            "built without it produces a report generator with nothing to check."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def trace_ai_checklist(version: str = "2.2.0") -> dict:
    """The vendored upstream checklist, exactly as pinned.

    Vendored rather than fetched: a report must be reproducible offline and years
    later, and the pinned commit is recorded in profiles/trace-ai/pin.json along
    with this file's sha256 so drift from upstream is detectable.
    """
    return _load(f"trace_ai/trace-ai-checklist-{version}.json")


def trace_ai_claims(version: str = "2.2.0") -> dict:
    """What THIS project claims, item by item, against that checklist.

    Separate from the checklist on purpose. The checklist is upstream's and is
    not ours to edit; the claims are policy, and a different project using the
    same standard would claim differently.
    """
    return _load(f"trace_ai/claims-{version}.json")
