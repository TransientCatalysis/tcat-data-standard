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


def test_the_skeleton_source_is_the_installed_standard(tmp_path):
    from tcat_data import scaffold
    assert scaffold.source("data").is_dir()
    with pytest.raises(LookupError, match="unknown kind"):
        scaffold.source("nonsense")


def test_a_spoke_in_a_personal_account_carries_its_owners_url_and_title(tmp_path):
    """`--owner` (or `owner` in the answers): a student's spoke in their own account
    is cited at its own url under its own title, while the links to the standards
    still point where the toolchain lives. The owner is init-only -- the git remote
    records it -- so it never reaches the manifest the schema validates."""
    root = tmp_path / "echem-data"
    rc = tcat_spoke(["init", str(root), "--kind", "data", "--answers",
                     _answers(tmp_path, spoke_id="echem-data", kind="data", name="Potential steps", owner="jdoe")])
    assert rc == 0
    cff = (root / "CITATION.cff").read_text()
    assert 'repository-code: "https://github.com/jdoe/echem-data"' in cff
    assert 'title: "Potential steps"' in cff, "a study outside the collaboration is not titled as one of its spokes"
    assert "github.com/TransientCatalysis/tcat-data-standard" in cff, "the standard it conforms to has not moved"
    assert "owner" not in json.loads((root / ".tcat-spoke.json").read_text())
    assert tcat_spoke(["check", str(root)]) == 0


def test_the_owner_flag_overrides_the_answers_and_the_default_is_the_org(tmp_path):
    a = tcat_spoke(["init", str(tmp_path / "a"), "--kind", "data", "--owner", "postdoc-lab", "--answers",
                    _answers(tmp_path, spoke_id="a", kind="data", owner="jdoe")])
    assert a == 0 and "github.com/postdoc-lab/a" in (tmp_path / "a" / "CITATION.cff").read_text()
    b = tcat_spoke(["init", str(tmp_path / "b"), "--kind", "data", "--answers",
                    _answers(tmp_path, spoke_id="b", kind="data", name="B")])
    cff = (tmp_path / "b" / "CITATION.cff").read_text()
    assert b == 0 and "github.com/TransientCatalysis/b" in cff and "transient kinetics spoke" in cff


def test_an_owner_that_is_not_a_github_account_name_is_refused(tmp_path, capsys):
    rc = tcat_spoke(["init", str(tmp_path / "c"), "--kind", "data", "--owner", "https://github.com/jdoe",
                     "--answers", _answers(tmp_path, spoke_id="c", kind="data")])
    assert rc == 1 and "not a GitHub account name" in capsys.readouterr().err


def test_the_data_skeletons_example_declares_the_installed_schema_and_fails_only_on_its_placeholders():
    """Newcomers copy it. At 0.2.0 it refused `protocol: custom` with an error that
    never mentioned the version (found by an outside-user walkthrough, 2026-10-08)."""
    from tcat_data import scaffold, validate_dataset
    from tcat_data.schema import CURRENT_SCHEMA_VERSION

    doc = json.loads((scaffold.source("data") / "manifests" / "_example.json").read_text())
    assert doc["schema_version"] == CURRENT_SCHEMA_VERSION
    doc = {k: v for k, v in doc.items() if not k.startswith("$comment")}
    errors = validate_dataset(doc).errors
    assert all("REPLACE" in json.dumps(e.message) or "REPLACE" in e.message for e in errors), \
        [f"{e.pointer}: {e.message}" for e in errors]


def test_init_without_a_tty_or_answers_fails_cleanly_and_writes_nothing(tmp_path, capsys, monkeypatch):
    """With stdin closed and no --answers, init used to copy the skeleton, then
    die on an EOFError traceback -- leaving a half-made directory that the
    corrected re-run refused as not empty."""
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    root = tmp_path / "scripted"
    assert tcat_spoke(["init", str(root), "--kind", "tool"]) == 1
    err = capsys.readouterr().err
    assert "--answers" in err and "Spoke id" in err
    assert not root.exists() or not any(root.iterdir())


def test_init_refuses_a_populated_directory_before_asking_anything(tmp_path, capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    root = tmp_path / "busy"
    root.mkdir()
    (root / "work.txt").write_text("someone's work\n")
    assert tcat_spoke(["init", str(root), "--kind", "data"]) == 1
    err = capsys.readouterr().err
    assert "not empty" in err and "no answer" not in err
    assert [p.name for p in root.iterdir()] == ["work.txt"]
