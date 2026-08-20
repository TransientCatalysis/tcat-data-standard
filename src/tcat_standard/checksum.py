"""SHA-256 over files and trees.

Every byte-bearing pointer in this standard carries a checksum. That is what
makes a relative path swappable for a URL or an LFS pointer without breaking a
downstream consumer: the path says where to look, the checksum says whether you
found the right thing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: str | Path) -> str:
    """Return the lowercase hex SHA-256 of one file, read in chunks.

    Chunked because spectroscopy sets are large and we should never assume a
    file fits in memory.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


#: Filesystem debris that must not affect a store's identity. Deliberately a
#: SHORT DENYLIST rather than "skip anything starting with a dot": Zarr keeps its
#: array metadata in dot-files (.zarray, .zattrs, .zgroup, .zmetadata), and those
#: files ARE the array's dtype, shape, and chunking. Excluding them would let a
#: store's dtype change without its checksum changing, which is precisely the
#: failure a content-addressed store exists to prevent.
JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
JUNK_DIRS = frozenset({".git", "__pycache__", ".ipynb_checkpoints"})


def _is_junk(rel: Path) -> bool:
    if any(part in JUNK_DIRS for part in rel.parts[:-1]):
        return True
    name = rel.name
    return name in JUNK_NAMES or name.startswith("._")


def sha256_tree(root: str | Path, *, skip_junk: bool = True) -> str:
    """Return a single checksum over a directory tree, for Zarr stores.

    A Zarr store is a directory, so it needs a tree checksum rather than a file
    checksum. The digest covers both the relative paths and the contents, so
    renaming a chunk changes the result -- otherwise two different arrays with
    the same bytes in different places would collide.

    Paths are sorted so the result does not depend on filesystem enumeration
    order, which differs between macOS, Linux, and the parallel filesystems this
    will eventually run on.

    ``skip_junk`` excludes editor and OS debris (see :data:`JUNK_NAMES` and
    :data:`JUNK_DIRS`) so that browsing a store on a Mac does not change its
    identity. It does NOT exclude dot-files in general -- see the note on
    :data:`JUNK_NAMES` for why that distinction matters.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if skip_junk and _is_junk(rel):
            continue
        h.update(rel.as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(path).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()
