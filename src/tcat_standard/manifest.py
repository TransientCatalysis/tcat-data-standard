"""Manifest entries: the indirection layer between code and bytes.

The rule is absolute and applies from day one: a dataset references its files
through a manifest entry carrying a relative path plus a checksum. Never a
direct filename in code.

The cost of following it is one indirection. The payoff arrives the first time a
spectroscopy set outgrows a git repository: swap ``path`` for ``url`` or
``lfs_oid`` in one JSON field and every downstream consumer keeps working, with
the checksum proving the bytes are the same ones. The alternative -- open-coded
paths scattered through analysis scripts at three institutions -- is not
fixable after the fact, which is why this is not deferred.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .checksum import sha256_file, sha256_tree

Format = Literal["csv", "zarr", "json", "instrument-native"]


@dataclass
class ManifestEntry:
    """An indirect, checksummed reference to bytes.

    Exactly one of ``path``, ``url``, or ``lfs_oid`` is set. That is enforced by
    the schema too, but checked here so a Python caller fails at construction
    rather than at validation.
    """

    sha256: str
    size_bytes: int
    format: Format
    path: str | None = None
    url: str | None = None
    lfs_oid: str | None = None
    media_type: str | None = None
    compression: str | None = None
    rows: int | None = None
    shape: list[int] | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        locations = [n for n in ("path", "url", "lfs_oid") if getattr(self, n) is not None]
        if len(locations) != 1:
            raise ValueError(
                "a manifest entry needs exactly one location -- path, url, or lfs_oid -- "
                f"but {len(locations)} were given ({', '.join(locations) or 'none'})"
            )
        if self.path is not None:
            p = PurePosixPath(self.path)
            if p.is_absolute():
                raise ValueError(f"manifest path must be repository-relative, got {self.path!r}")
            if ".." in p.parts:
                raise ValueError(f"manifest path must not escape the repository, got {self.path!r}")

    # -- construction -----------------------------------------------------

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        repo_root: str | Path,
        format: Format | None = None,
        **extra: Any,
    ) -> "ManifestEntry":
        """Build an entry for a file on disk, computing size and checksum.

        ``repo_root`` is required rather than optional: the stored path has to be
        relative to something, and guessing that something is how absolute paths
        end up committed.
        """
        path = Path(path).resolve()
        root = Path(repo_root).resolve()
        try:
            rel = path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{path} is not inside repo_root {root}") from exc

        if format is None:
            format = _infer_format(path)

        if path.is_dir():
            if format != "zarr":
                raise ValueError(f"{path} is a directory but format is {format!r}; expected zarr")
            digest = sha256_tree(path)
            size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        else:
            digest = sha256_file(path)
            size = path.stat().st_size

        entry = cls(
            sha256=digest,
            size_bytes=size,
            format=format,
            path=rel.as_posix(),
            **extra,
        )
        if format == "csv" and entry.rows is None and path.is_file():
            entry.rows = _count_csv_rows(path)
        return entry

    # -- use --------------------------------------------------------------

    def resolve(self, repo_root: str | Path) -> Path:
        """Materialise a local path for a ``path``-form entry.

        Deliberately narrow. ``url`` and ``lfs_oid`` forms need a fetch, which is
        the artifact store's job in the analysis hub, not this package's -- the
        data standard describes data; it does not move it.
        """
        if self.path is None:
            raise ValueError(
                "this entry is not path-form; fetching url or lfs_oid entries is the "
                "artifact store's responsibility, not the data standard's"
            )
        return Path(repo_root) / self.path

    def verify(self, repo_root: str | Path) -> bool:
        """Recompute the checksum and compare. False means the bytes changed."""
        target = self.resolve(repo_root)
        actual = sha256_tree(target) if target.is_dir() else sha256_file(target)
        return actual == self.sha256

    def to_dict(self) -> dict[str, Any]:
        """Schema-shaped dict, with unset optional fields omitted."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestEntry":
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"unknown manifest-entry field(s): {', '.join(sorted(unknown))}. "
                "Project-specific fields belong in the dataset's extensions object."
            )
        return cls(**data)


def _infer_format(path: Path) -> Format:
    """Guess a format from the filename. Explicit beats inferred; this is a fallback."""
    if path.is_dir() or path.suffix == ".zarr":
        return "zarr"
    return {".csv": "csv", ".json": "json"}.get(path.suffix.lower(), "instrument-native")


def _count_csv_rows(path: Path) -> int:
    """Row count excluding the header -- a cheap dataset-equivalence check (TRACE-AI A2)."""
    with open(path, "rb") as fh:
        n = sum(1 for _ in fh)
    return max(n - 1, 0)
