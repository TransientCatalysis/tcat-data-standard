from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcat_data.spoke_cli import main as tcat_spoke

STEWARDS = [{"name": "A Maintainer", "institution": "Example University", "role": "data_steward",
             "github": "a-maintainer", "orcid": "0000-0002-1825-0097"},
            {"name": "An Instrument Owner", "institution": "Example University", "role": "instrument_owner",
             "github": "an-instrument-owner", "orcid": "0000-0002-1825-0098"}]


def _answers(tmp_path, **fields):
    a = {"standard_version": "0.3.0", "stewards": STEWARDS, "maturity": {"rung": "sandbox"}, **fields}
    p = tmp_path / "answers.json"; p.write_text(json.dumps(a)); return str(p)


def test_init_materialises_the_data_skeleton_and_fills_it(tmp_path):
    """One command, from a NEW directory: the skeleton that used to be a GitHub
    template repository, then the manifest, placeholders, citation, CODEOWNERS."""
    root = tmp_path / "demo-lab-data"
    rc = tcat_spoke(["init", str(root), "--kind", "data", "--answers",
                     _answers(tmp_path, spoke_id="demo-lab-data", kind="data", name="Demo lab data", granularity="campaign")])
    assert rc == 0
    for rel in (".tcat-spoke.json", ".github/workflows/validate.yml", ".github/CODEOWNERS", ".gitignore",
                "START-HERE.md", "manifests/_example.json", "calibrations/.gitkeep", "CITATION.cff"):
        assert (root / rel).is_file(), rel
    assert not list(root.rglob("dot-*")) and not list(root.rglob("*.tmpl")), "storage conventions must be undone"
    assert tcat_spoke(["check", str(root)]) == 0
    assert "Use this template" not in (root / "START-HERE.md").read_text()
    assert "tcat-spoke init --kind data" in (root / "START-HERE.md").read_text()


def test_a_new_directory_needs_a_kind(tmp_path, capsys):
    assert tcat_spoke(["init", str(tmp_path / "new"), "--answers", _answers(tmp_path, spoke_id="new", kind="data")]) == 1
    assert "--kind" in capsys.readouterr().err


def test_a_populated_directory_is_filled_in_place_as_before(tmp_path):
    """The pre-2026-09-09 route (a clone of a template) still works: no skeleton
    is written over existing files."""
    root = tmp_path / "old"; root.mkdir(); (root / "README.md").write_text("mine [BRACKETED]\n")
    assert tcat_spoke(["init", str(root), "--answers", _answers(tmp_path, spoke_id="old", kind="data", name="Old")]) == 0
    assert (root / "README.md").read_text().startswith("mine Old"), "filled, not replaced"
    assert not (root / "START-HERE.md").exists()


def test_the_skeleton_source_is_the_installed_standard(tmp_path):
    from tcat_data import scaffold
    assert scaffold.source("data").is_dir()
    with pytest.raises(LookupError, match="unknown kind"):
        scaffold.source("nonsense")
