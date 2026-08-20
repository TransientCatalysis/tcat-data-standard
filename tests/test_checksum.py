"""Checksums over files and Zarr-style trees."""

from __future__ import annotations

import hashlib

import pytest

from tcat_standard import sha256_file, sha256_tree


def test_file_checksum_matches_hashlib(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes(b"time_s,m44\n0.0,1.2e-9\n")
    assert sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_file_checksum_handles_multi_chunk_files(tmp_path):
    """Chunked reading must not change the digest -- spectroscopy files will
    exceed the chunk size routinely."""
    p = tmp_path / "big.bin"
    payload = bytes(range(256)) * 8192  # 2 MiB, larger than the 1 MiB chunk
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()


def test_empty_file_is_the_empty_digest(tmp_path):
    p = tmp_path / "empty.csv"
    p.touch()
    assert sha256_file(p) == hashlib.sha256(b"").hexdigest()


def _make_tree(root, files):
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return root


def test_tree_checksum_is_stable(tmp_path):
    a = _make_tree(tmp_path / "a", {"0.0": b"x", "1.0": b"y", ".zarray": b"{}"})
    assert sha256_tree(a) == sha256_tree(a)


def test_tree_checksum_ignores_enumeration_order(tmp_path):
    """Two trees with the same content must agree even though they were created
    in different orders -- filesystem enumeration order differs between macOS,
    Linux, and the parallel filesystems this will eventually run on."""
    a = _make_tree(tmp_path / "a", {"0.0": b"x", "1.0": b"y", "2.0": b"z"})
    b = _make_tree(tmp_path / "b", {"2.0": b"z", "0.0": b"x", "1.0": b"y"})
    assert sha256_tree(a) == sha256_tree(b)


def test_tree_checksum_covers_paths_not_just_bytes(tmp_path):
    """Renaming a chunk must change the digest. Otherwise two different arrays
    holding the same bytes in different places would collide."""
    a = _make_tree(tmp_path / "a", {"0.0": b"x", "1.0": b"y"})
    b = _make_tree(tmp_path / "b", {"0.1": b"x", "1.0": b"y"})
    assert sha256_tree(a) != sha256_tree(b)


def test_tree_checksum_detects_content_change(tmp_path):
    a = _make_tree(tmp_path / "a", {"0.0": b"x"})
    before = sha256_tree(a)
    (a / "0.0").write_bytes(b"X")
    assert sha256_tree(a) != before


def test_tree_checksum_rejects_a_file(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes(b"x")
    with pytest.raises(NotADirectoryError):
        sha256_tree(p)


def test_os_debris_does_not_change_identity(tmp_path):
    """Browsing a store on a Mac must not change its checksum."""
    a = _make_tree(tmp_path / "a", {"0.0": b"x", ".zarray": b"{}"})
    before = sha256_tree(a)
    (a / ".DS_Store").write_bytes(b"junk")
    (a / "._0.0").write_bytes(b"resource fork")
    (a / ".git" / "HEAD").parent.mkdir(exist_ok=True)
    (a / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main")
    assert sha256_tree(a) == before
    assert sha256_tree(a, skip_junk=False) != before


def test_zarr_metadata_is_not_treated_as_debris(tmp_path):
    """.zarray IS the array's dtype, shape, and chunking. If a blanket dot-file
    skip hid it, a store's dtype could change without its checksum changing --
    exactly the failure a content-addressed store exists to prevent."""
    a = _make_tree(tmp_path / "a", {"0.0": b"x", ".zarray": b'{"dtype":"<f8"}'})
    before = sha256_tree(a)
    (a / ".zarray").write_bytes(b'{"dtype":"<f4"}')
    assert sha256_tree(a) != before


def test_zattrs_and_zgroup_also_count(tmp_path):
    a = _make_tree(tmp_path / "a", {".zgroup": b"{}", "x/.zattrs": b'{"units":"A"}'})
    before = sha256_tree(a)
    (a / "x" / ".zattrs").write_bytes(b'{"units":"mol/m^3"}')
    assert sha256_tree(a) != before
