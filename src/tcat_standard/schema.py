"""Locate and load pinned schema versions.

The validator retains every old schema version forever. This is structural, not
a promise: versions live in ``schema/<version>/`` and nothing is ever removed
from that directory. A dataset written against 0.1.0 still validates against
0.1.0 in five years, which means a minor bump never obliges a lab to rewrite
existing data -- and a major bump ships a migration script rather than a demand.

The tree lives INSIDE the package, at ``src/tcat_standard/schema/``, rather than
at the repository root. One extra path segment buys a working ``pip install
git+https://...`` -- which is how a spoke's CI installs the validator, and
therefore how the ingestion gate actually runs. Schemas that only exist in a
source checkout are schemas that silently stop being enforced.

Layout::

    src/tcat_standard/schema/
      VERSION            <- the current version, one line
      0.1.0/
        dataset.schema.json
        manifest-entry.schema.json
        calibration.schema.json
        provenance.schema.json
        uncertainty-ensemble.schema.json
        protocol.schema.json
        defs/common.schema.json
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

# The schema tree ships as package data but is authored at the repository root,
# so resolve it relative to this file and fall back to the installed location.
_HERE = Path(__file__).resolve().parent


def _find_schema_root() -> Path:
    """Locate the schema tree, whether running from a checkout or an install."""
    candidates = [
        _HERE / "schema",                 # canonical: inside the package, so a wheel carries it
        _HERE.parent.parent / "schema",   # legacy repo-root location, kept as a fallback
    ]
    for c in candidates:
        if (c / "VERSION").is_file():
            return c
    raise FileNotFoundError(
        "cannot locate the schema tree; looked in "
        + ", ".join(str(c) for c in candidates)
    )


SCHEMA_ROOT = _find_schema_root()

#: Current schema version, read from schema/VERSION so there is exactly one
#: place to bump it. Never hardcode a version string elsewhere.
CURRENT_SCHEMA_VERSION = (SCHEMA_ROOT / "VERSION").read_text(encoding="utf-8").strip()

#: The document kinds this standard defines. Each maps to <kind>.schema.json.
KINDS = (
    "dataset",
    "manifest-entry",
    "calibration",
    "provenance",
    "uncertainty-ensemble",
    "protocol",
    "sample",
    "model",
    "publication",
    "spoke",
)


def available_versions() -> list[str]:
    """Every schema version present on disk, oldest first.

    Sorted numerically rather than lexically so 0.10.0 lands after 0.9.0.
    """

    def key(v: str) -> tuple[int, ...]:
        return tuple(int(p) for p in v.split("-")[0].split(".") if p.isdigit())

    versions = [p.name for p in SCHEMA_ROOT.iterdir() if p.is_dir() and (p / "defs").is_dir()]
    return sorted(versions, key=key)


def schema_dir(version: str | None = None) -> Path:
    """Directory holding one version's schemas. Defaults to the current version."""
    version = version or CURRENT_SCHEMA_VERSION
    path = SCHEMA_ROOT / version
    if not path.is_dir():
        raise FileNotFoundError(
            f"schema version {version!r} is not present; available: "
            + ", ".join(available_versions())
        )
    return path


@functools.lru_cache(maxsize=None)
def load_schema(kind: str, version: str | None = None) -> dict[str, Any]:
    """Load one schema document by kind.

    Cached: the validator is called once per file in a CI run over a spoke with
    hundreds of manifests, and re-reading and re-parsing the tree each time is
    the difference between a two-second check and a visible one.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown document kind {kind!r}; expected one of {', '.join(KINDS)}")
    path = schema_dir(version) / f"{kind}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def load_all_schemas(version: str | None = None) -> dict[str, dict[str, Any]]:
    """Every schema document for one version, keyed by its ``$id``.

    This is what the reference registry is built from: cross-file ``$ref``s
    resolve against ``$id``, so the whole version has to be loaded together
    rather than one file at a time.
    """
    directory = schema_dir(version)
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.rglob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = doc.get("$id")
        if not doc_id:
            raise ValueError(f"{path} has no $id; every schema document must declare one")
        docs[doc_id] = doc
    return docs
