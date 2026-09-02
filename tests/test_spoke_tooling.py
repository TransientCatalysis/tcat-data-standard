"""`tcat-spoke`: the bootstrap, CODEOWNERS generation, and the placeholder gate.

The thing being fixed here is that a spoke used to be created by copying a
template and hand-editing REPLACE in five files, with nothing checking that the
edit happened. A repository could be created, committed, and pass CI while its
README still said REPLACE and its CITATION.cff credited nobody.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcat_standard import spoke
from tcat_standard.spoke_cli import main

_ORCID = "0000-0001-8311-9581"


def _steward(**over):
    d = {"name": "A J Medford", "institution": "Georgia Tech",
         "role": "data_steward", "github": "ajmedford", "orcid": _ORCID}
    d.update(over)
    return d


def _manifest(**over):
    d = {"standard_version": "0.2.0", "spoke_id": "a-spoke", "kind": "data",
         "stewards": [_steward()]}
    d.update(over)
    return d


def _answers(tmp_path: Path, manifest: dict) -> str:
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(manifest))
    return str(p)


# --- CODEOWNERS ------------------------------------------------------------

def test_codeowners_is_generated_from_the_stewards_block():
    out = spoke.build_codeowners(_manifest()).text
    assert "*\t@ajmedford" in out
    assert "GENERATED" in out


def test_the_calibration_directory_is_owned_by_the_instrument_owner():
    """The highest-value line in the file: it turns "a calibration change is
    reviewed by whoever owns the instrument" from a sentence in PROMOTION.md
    into a review GitHub will require."""
    m = _manifest(
        stewards=[_steward(), _steward(name="R Rioux", github="rmrioux", role="instrument_owner")],
        layout={"calibration": ["calibrations"]},
    )
    out = spoke.build_codeowners(m).text
    assert "calibrations/\t@rmrioux" in out
    assert "@ajmedford" not in out.split("calibrations/")[1]


def test_a_steward_with_no_github_handle_appears_as_a_comment_not_an_owner():
    """A quietly shortened owner list looks complete. A comment does not."""
    m = _manifest(stewards=[_steward(), {"name": "No Handle", "institution": "X", "role": "pi"}])
    result = spoke.build_codeowners(m)
    assert "# no GitHub handle" in result.text
    assert "No Handle" in result.text
    assert result.findings


def test_generation_refuses_when_no_steward_has_a_handle():
    """A CODEOWNERS of only comments reads to GitHub as "no owner" while the
    repository looks governed, which is worse than having no file."""
    m = _manifest(stewards=[{"name": "A", "institution": "X", "role": "pi"}])
    result = spoke.build_codeowners(m)
    assert result.refused
    assert not result.text


def test_a_spoke_holding_calibrations_with_no_instrument_owner_is_reported():
    m = _manifest(layout={"calibration": ["calibrations"]})
    findings = spoke.build_codeowners(m).findings
    assert any("instrument_owner" in str(f) for f in findings)


# --- placeholders ----------------------------------------------------------

def test_an_unfilled_placeholder_is_found_and_named_by_file_and_line(tmp_path):
    (tmp_path / "README.md").write_text("# Title\n\nOwner: REPLACE\n")
    found = spoke.find_placeholders(tmp_path)
    assert len(found) == 1
    assert found[0].where == "README.md:3"


def test_underscore_prefixed_files_may_keep_their_placeholders(tmp_path):
    """Fragile point 8. `_`-prefixed files are skipped by `tcat-validate all`
    and by the registry precisely so they can carry REPLACE as a thing to copy
    from. Flagging them would contradict the rule that makes them useful."""
    (tmp_path / "_example.json").write_text('{"sample_id": "REPLACE"}')
    assert spoke.find_placeholders(tmp_path) == []


def test_the_template_itself_must_keep_its_placeholders(tmp_path):
    """A template whose placeholders were filled in is broken for everyone who
    creates a repository from it, and the breakage is invisible."""
    (tmp_path / ".tcat").mkdir()
    (tmp_path / ".tcat" / "IS_TEMPLATE").write_text("")
    (tmp_path / "README.md").write_text("# All filled in\n")
    findings = spoke.check(tmp_path)
    assert any("filled them in" in str(f) for f in findings)


# --- init ------------------------------------------------------------------

def test_init_writes_a_manifest_codeowners_and_fills_the_citation(tmp_path):
    (tmp_path / "README.md").write_text("# [BRACKETED]\n\nContact: [YOUR NAME, EMAIL]\n")
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\ntitle: "[LAB OR CAMPAIGN NAME]"\n'
        'date-released: "REPLACE-YYYY-MM-DD"\n'
        'repository-code: "https://github.com/TransientCatalysis/REPLACE"\n'
        "authors:\n  - family-names: REPLACE\n    given-names: REPLACE\n"
    )
    rc = main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())])
    assert rc == 0
    assert (tmp_path / ".tcat-spoke.json").is_file()
    assert (tmp_path / ".github" / "CODEOWNERS").is_file()
    citation = (tmp_path / "CITATION.cff").read_text()
    assert "REPLACE" not in citation
    assert "Medford" in citation


def test_init_refuses_a_manifest_that_would_not_validate(tmp_path):
    bad = {"standard_version": "0.2.0", "spoke_id": "x", "kind": "data", "stewards": []}
    assert main(["init", str(tmp_path), "--answers", _answers(tmp_path, bad)]) == 1
    assert not (tmp_path / ".tcat-spoke.json").exists()


def test_init_does_not_overwrite_without_force(tmp_path):
    a = _answers(tmp_path, _manifest())
    assert main(["init", str(tmp_path), "--answers", a]) == 0
    assert main(["init", str(tmp_path), "--answers", a]) == 1
    assert main(["init", str(tmp_path), "--answers", a, "--force"]) == 0


def test_init_removes_the_template_sentinel(tmp_path):
    (tmp_path / ".tcat").mkdir()
    (tmp_path / ".tcat" / "IS_TEMPLATE").write_text("")
    main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())])
    assert not (tmp_path / ".tcat" / "IS_TEMPLATE").exists()


# --- check -----------------------------------------------------------------

def test_check_fails_on_a_hand_edited_codeowners(tmp_path):
    main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())])
    (tmp_path / ".github" / "CODEOWNERS").write_text("*\t@someone-else\n")
    assert main(["codeowners", "--check", str(tmp_path)]) == 1


def test_check_mode_names_the_command_that_fixes_it(tmp_path, capsys):
    main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())])
    (tmp_path / ".github" / "CODEOWNERS").write_text("*\t@someone-else\n")
    main(["codeowners", "--check", str(tmp_path)])
    assert "tcat-spoke codeowners" in capsys.readouterr().err


def test_a_repository_that_is_not_a_spoke_is_not_this_tools_business(tmp_path):
    """`tcat-spoke codeowners --check` runs in every CI. A repository with no
    manifest and no CODEOWNERS is simply not a spoke, and must not fail."""
    assert main(["codeowners", "--check", str(tmp_path)]) == 0


def test_a_committed_codeowners_with_no_manifest_fails(tmp_path):
    """Somebody hand-wrote it, which is exactly the drift being prevented."""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("*\t@someone\n")
    assert main(["codeowners", "--check", str(tmp_path)]) == 1


def test_check_passes_on_a_fully_bootstrapped_spoke(tmp_path):
    (tmp_path / "README.md").write_text("# [BRACKETED]\n")
    main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())])
    assert main(["check", str(tmp_path)]) == 0


def test_check_reports_a_missing_manifest_with_the_command_that_makes_one(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == 1
    assert "tcat-spoke init" in capsys.readouterr().err


# --- the analysis side needs a package rename ------------------------------

def _analysis_template(tmp_path: Path) -> Path:
    """A minimal stand-in for the analysis template's shape."""
    (tmp_path / "src" / "tcat_spoke_example").mkdir(parents=True)
    (tmp_path / "src" / "tcat_spoke_example" / "tool.py").write_text(
        "# tcat-fit-example is the command\nfrom tcat_spoke_example import science\n"
    )
    (tmp_path / "src" / "tcat_spoke_example.egg-info").mkdir()
    (tmp_path / "src" / "tcat_spoke_example.egg-info" / "top_level.txt").write_text(
        "tcat_spoke_example\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_conformance.py").write_text(
        'COMMAND = "tcat-fit-example"\n'
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "conform.yml").write_text(
        "run: tcat-conform tcat-fit-example --as tcat-fit\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "tcat-spoke-example"\n'
        'description = "REPLACE -- what this spoke implements, in one line."\n'
        'authors = [{ name = "REPLACE ME", email = "replace-me@example.com" }]\n'
        "\n[project.scripts]\n"
        'tcat-fit-example = "tcat_spoke_example.tool:main"\n'
        "\n[project.urls]\n"
        'Homepage = "https://github.com/TransientCatalysis/REPLACE"\n'
    )
    return tmp_path


def _analysis_answers(tmp_path: Path) -> str:
    m = _manifest(kind="analysis", spoke_id="gusmao-cqbax", name="Stiff DAE fitting")
    return _answers(tmp_path, m)


def test_init_renames_the_example_package_to_this_spokes_own(tmp_path):
    """Seven places reference it, and missing any one leaves a spoke that
    installs a package named after the template."""
    root = _analysis_template(tmp_path)
    assert main(["init", str(root), "--answers", _analysis_answers(tmp_path)]) == 0

    assert (root / "src" / "tcat_gusmao_cqbax").is_dir()
    assert not (root / "src" / "tcat_spoke_example").exists()
    assert "tcat_gusmao_cqbax" in (root / "src" / "tcat_gusmao_cqbax" / "tool.py").read_text()
    assert "tcat_spoke_example" not in (root / "tests" / "test_conformance.py").read_text()
    assert "tcat-fit-gusmao-cqbax" in (root / ".github" / "workflows" / "conform.yml").read_text()


def test_init_removes_the_stale_egg_info(tmp_path):
    """A build artifact from an editable install in the template. It describes
    the OLD package and is regenerated on install, so it is deleted rather than
    renamed."""
    root = _analysis_template(tmp_path)
    main(["init", str(root), "--answers", _analysis_answers(tmp_path)])
    assert not list((root / "src").glob("*.egg-info"))


def test_init_fills_the_pyproject_a_spoke_would_otherwise_publish(tmp_path):
    """The template leaves these valid-but-placeholder on purpose, so it installs
    before anyone edits it. That is right for the template and wrong for a spoke,
    where it means a package credited to "REPLACE ME"."""
    root = _analysis_template(tmp_path)
    main(["init", str(root), "--answers", _analysis_answers(tmp_path)])
    text = (root / "pyproject.toml").read_text()
    assert "REPLACE" not in text
    assert 'name = "gusmao-cqbax"' in text
    assert "A J Medford" in text


def test_a_data_spoke_is_not_given_a_package(tmp_path):
    """Only the analysis side has one; running the rename on a data spoke would
    be looking for something that is correctly absent."""
    (tmp_path / "README.md").write_text("# [BRACKETED]\n")
    assert main(["init", str(tmp_path), "--answers", _answers(tmp_path, _manifest())]) == 0
    assert not (tmp_path / "src").exists()
