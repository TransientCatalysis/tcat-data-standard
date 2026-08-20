"""Manifest entries: the indirection that lets data move without breaking code."""

from __future__ import annotations

import pytest

from tcat_standard import ManifestEntry


def _csv(tmp_path):
    p = tmp_path / "raw" / "run-014.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("time_s,m44\n0.00,1.2e-9\n0.05,1.3e-9\n", encoding="utf-8")
    return p


# ---- construction ------------------------------------------------------


def test_from_file_records_path_size_checksum_and_rows(tmp_path):
    entry = ManifestEntry.from_file(_csv(tmp_path), repo_root=tmp_path)
    assert entry.path == "raw/run-014.csv"
    assert entry.format == "csv"
    assert entry.rows == 2, "rows excludes the header -- a cheap equivalence check"
    assert entry.size_bytes > 0
    assert len(entry.sha256) == 64


def test_from_file_refuses_a_path_outside_the_repo(tmp_path):
    """An absolute path committed to a manifest is only meaningful on one laptop."""
    outside = tmp_path.parent / "elsewhere.csv"
    outside.write_text("x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not inside repo_root"):
        ManifestEntry.from_file(outside, repo_root=tmp_path)


def test_from_file_on_a_directory_requires_zarr_format(tmp_path):
    d = tmp_path / "spectra.zarr"
    d.mkdir()
    (d / "0.0").write_bytes(b"chunk")
    assert ManifestEntry.from_file(d, repo_root=tmp_path).format == "zarr"
    with pytest.raises(ValueError, match="expected zarr"):
        ManifestEntry.from_file(d, repo_root=tmp_path, format="csv")


# ---- the exactly-one-location rule -------------------------------------


def test_exactly_one_location_is_required():
    common = dict(sha256="0" * 64, size_bytes=1, format="csv")
    with pytest.raises(ValueError, match="exactly one location"):
        ManifestEntry(**common)
    with pytest.raises(ValueError, match="exactly one location"):
        ManifestEntry(**common, path="a.csv", url="https://example.org/a.csv")


def test_absolute_and_escaping_paths_are_rejected():
    common = dict(sha256="0" * 64, size_bytes=1, format="csv")
    with pytest.raises(ValueError, match="repository-relative"):
        ManifestEntry(**common, path="/etc/passwd")
    with pytest.raises(ValueError, match="escape the repository"):
        ManifestEntry(**common, path="../../secrets.csv")


# ---- the payoff --------------------------------------------------------


def test_relocating_off_repo_preserves_identity(tmp_path):
    """The whole reason for the indirection. A set outgrows the repo, the path
    becomes a URL, and the checksum still proves the bytes are the same ones --
    so nothing downstream has to change or be re-verified by hand."""
    local = ManifestEntry.from_file(_csv(tmp_path), repo_root=tmp_path)

    remote = ManifestEntry(
        sha256=local.sha256,
        size_bytes=local.size_bytes,
        format=local.format,
        url="https://data.example.org/tcat/run-014.csv",
        rows=local.rows,
    )
    assert remote.sha256 == local.sha256
    assert remote.path is None and remote.url is not None


def test_resolve_and_verify_round_trip(tmp_path):
    entry = ManifestEntry.from_file(_csv(tmp_path), repo_root=tmp_path)
    assert entry.resolve(tmp_path).is_file()
    assert entry.verify(tmp_path) is True


def test_verify_detects_a_changed_file(tmp_path):
    path = _csv(tmp_path)
    entry = ManifestEntry.from_file(path, repo_root=tmp_path)
    path.write_text("time_s,m44\n0.00,9.9e-9\n", encoding="utf-8")
    assert entry.verify(tmp_path) is False


def test_resolve_refuses_non_path_forms():
    """Fetching bytes is the artifact store's job. The data standard describes
    data; it does not move it."""
    entry = ManifestEntry(
        sha256="0" * 64, size_bytes=1, format="csv", url="https://example.org/a.csv"
    )
    with pytest.raises(ValueError, match="artifact store"):
        entry.resolve("/tmp")


# ---- serialisation -----------------------------------------------------


def test_to_dict_omits_unset_optionals(tmp_path):
    d = ManifestEntry.from_file(_csv(tmp_path), repo_root=tmp_path).to_dict()
    assert "url" not in d and "lfs_oid" not in d and "shape" not in d
    assert set(d) >= {"sha256", "size_bytes", "format", "path"}


def test_from_dict_round_trips(tmp_path):
    original = ManifestEntry.from_file(_csv(tmp_path), repo_root=tmp_path)
    assert ManifestEntry.from_dict(original.to_dict()) == original


def test_from_dict_rejects_unknown_fields_and_says_where_they_belong():
    with pytest.raises(ValueError, match="extensions"):
        ManifestEntry.from_dict(
            {"sha256": "0" * 64, "size_bytes": 1, "format": "csv", "path": "a.csv",
             "beamline_proposal": "GU-999999"}
        )
