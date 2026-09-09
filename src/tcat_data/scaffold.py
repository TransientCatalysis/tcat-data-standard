"""The skeleton a new spoke or campaign starts from, shipped INSIDE the standard.

Until 2026-09-09 each kind had a GitHub template repository ("Use this template").
A template is a repository whose whole content becomes the new one, so the
skeleton could not live beside the standard that defines it -- and a skeleton
kept apart from its standard drifts (the tool template's naming rule had). Now
each standard ships its skeleton as package data and `tcat-spoke init --kind ...`
materialises it, so what a new repository starts from is exactly what the
installed version of the standard says it should be.

Storage conventions, so packaging tools and test collectors leave the skeleton
alone: a leading dot is stored as the prefix `dot-` (`dot-github/`,
`dot-gitignore`), and a Python file carries the suffix `.tmpl` (so it is neither
collected by pytest nor scanned as an implementation of the standard). Both are
undone on materialisation.
"""

from __future__ import annotations

import importlib
import importlib.resources
from pathlib import Path

#: kind -> (the package that ships it, the distribution to install for it)
SHIPPED_BY = {
    "data": ("tcat_data", "tcat-data-standard"),
    "tool": ("tcat_tool", "tcat-tool-standard"),
    "campaign": ("tcat_campaign", "tcat-campaign-standard"),
}


def source(kind: str) -> Path:
    """Where the skeleton for `kind` is installed, or a LookupError naming what to install."""
    if kind not in SHIPPED_BY:
        raise LookupError(f"unknown kind {kind!r}; one of {sorted(SHIPPED_BY)}")
    package, dist = SHIPPED_BY[kind]
    try:
        importlib.import_module(package)
    except ImportError as exc:
        raise LookupError(
            f"the {kind} skeleton ships with {dist}, which is not installed "
            f"(`pip install {dist}`)") from exc
    root = Path(str(importlib.resources.files(package))) / "scaffold" / kind
    if not root.is_dir():
        raise LookupError(f"{dist} is installed but carries no {kind} skeleton at {root}")
    return root


def _real_name(stored: str) -> str:
    name = "." + stored[4:] if stored.startswith("dot-") else stored
    return name[:-5] if name.endswith(".tmpl") else name


def materialise(kind: str, target: Path) -> list[Path]:
    """Copy the skeleton for `kind` into `target`, which must not exist or must be
    an empty directory. Returns the files written, relative to `target`."""
    root = source(kind)
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} is not empty; init materialises a skeleton only into a new directory")
    written: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = Path(*[_real_name(part) for part in path.relative_to(root).parts])
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        written.append(rel)
    return written
