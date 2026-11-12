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

from tcat_data import spoke
from tcat_data.spoke_cli import main

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
        stewards=[_steward(), _steward(name="A. Researcher", github="aresearcher", role="instrument_owner")],
        layout={"calibration": ["calibrations"]},
    )
    out = spoke.build_codeowners(m).text
    assert "calibrations/\t@aresearcher" in out
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
    """`_`-prefixed files are skipped by `tcat-validate all`
    and by the registry precisely so they can carry REPLACE as a thing to copy
    from. Flagging them would contradict the rule that makes them useful."""
    (tmp_path / "_example.json").write_text('{"sample_id": "REPLACE"}')
    assert spoke.find_placeholders(tmp_path) == []


# --- init ------------------------------------------------------------------

def _init(tmp_path: Path, manifest: dict | None = None) -> Path:
    """A data spoke made the only way init makes one: into a new directory."""
    root = tmp_path / "spoke"
    default = _manifest(stewards=[_steward(), _steward(name="A. Researcher", github="aresearcher",
                                                       role="instrument_owner")])
    assert main(["init", str(root), "--kind", "data",
                 "--answers", _answers(tmp_path, manifest or default)]) == 0
    return root


def test_init_writes_a_manifest_codeowners_and_fills_the_citation(tmp_path):
    root = _init(tmp_path)
    assert (root / ".tcat-spoke.json").is_file()
    assert (root / ".github" / "CODEOWNERS").is_file()
    citation = (root / "CITATION.cff").read_text()
    assert "REPLACE" not in citation
    assert "Medford" in citation


def test_init_refuses_a_manifest_that_would_not_validate(tmp_path):
    bad = {"standard_version": "0.2.0", "spoke_id": "x", "kind": "data", "stewards": []}
    root = tmp_path / "spoke"
    assert main(["init", str(root), "--kind", "data", "--answers", _answers(tmp_path, bad)]) == 1
    assert not (root / ".tcat-spoke.json").exists()


def test_init_refuses_a_populated_directory_and_changes_nothing_in_it(tmp_path, capsys):
    """Filling a populated directory in place was the route from a cloned template
    repository. There are none now, so a populated directory is somebody's work,
    and init would have rewritten its README and citation in place."""
    root = tmp_path / "mine"
    root.mkdir()
    (root / "README.md").write_text("# mine [BRACKETED]\n")
    assert main(["init", str(root), "--kind", "data", "--answers", _answers(tmp_path, _manifest())]) == 1
    assert "not empty" in capsys.readouterr().err
    assert [p.name for p in root.iterdir()] == ["README.md"]
    assert (root / "README.md").read_text() == "# mine [BRACKETED]\n"


def test_init_deletes_the_manifest_template_once_the_manifest_is_written(tmp_path):
    """Left behind, the annotated copy reads as a second, unfilled manifest."""
    root = _init(tmp_path)
    assert not (root / "_tcat-spoke.json.template").exists()


def test_init_writes_every_file_the_org_security_gate_checks_and_they_pass_it(tmp_path):
    """A new spoke used to fail its first `security` run: the gate checks five
    generated files and the skeleton carried none of them."""
    from tcat_data import org_files

    root = _init(tmp_path)
    for rel in ("AGENTS.md", "CLAUDE.md", "SECURITY.md", ".github/dependabot.yml",
                ".github/workflows/dependabot-automerge.yml"):
        assert (root / rel).is_file(), rel
    assert org_files.drifted(root.resolve()) == []
    assert main(["check", str(root)]) == 0


# --- check -----------------------------------------------------------------

def test_check_fails_on_a_hand_edited_codeowners(tmp_path):
    root = _init(tmp_path)
    (root / ".github" / "CODEOWNERS").write_text("*\t@someone-else\n")
    assert main(["codeowners", "--check", str(root)]) == 1


def test_check_mode_names_the_command_that_fixes_it(tmp_path, capsys):
    root = _init(tmp_path)
    (root / ".github" / "CODEOWNERS").write_text("*\t@someone-else\n")
    capsys.readouterr()
    main(["codeowners", "--check", str(root)])
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
    assert main(["check", str(_init(tmp_path))]) == 0


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


def _rename(root: Path) -> None:
    """The package rename init applies to a tool spoke, on a stand-in tree, so this
    repository's tests need no tool standard installed (the full `init --kind
    tool` path is tested in tcat-tool-standard, which ships that skeleton)."""
    from tcat_data.spoke_cli import _fill_pyproject, _rename_package

    m = _manifest(kind="analysis", spoke_id="labb-circx", name="Stiff DAE fitting")
    _rename_package(root, m, "tcat-fit")
    _fill_pyproject(root, m)


def test_init_renames_the_example_package_to_this_spokes_own(tmp_path):
    """Seven places reference it, and missing any one leaves a spoke that
    installs a package named after the skeleton."""
    root = _analysis_template(tmp_path)
    _rename(root)

    assert (root / "src" / "tcat_labb_circx").is_dir()
    assert not (root / "src" / "tcat_spoke_example").exists()
    assert "tcat_labb_circx" in (root / "src" / "tcat_labb_circx" / "tool.py").read_text()
    assert "tcat_spoke_example" not in (root / "tests" / "test_conformance.py").read_text()
    assert "tcat-fit-labb-circx" in (root / ".github" / "workflows" / "conform.yml").read_text()


def test_init_removes_the_stale_egg_info(tmp_path):
    """A build artifact from an editable install in the template. It describes
    the OLD package and is regenerated on install, so it is deleted rather than
    renamed."""
    root = _analysis_template(tmp_path)
    _rename(root)
    assert not list((root / "src").glob("*.egg-info"))


def test_init_fills_the_pyproject_a_spoke_would_otherwise_publish(tmp_path):
    """The template leaves these valid-but-placeholder on purpose, so it installs
    before anyone edits it. That is right for the template and wrong for a spoke,
    where it means a package credited to "REPLACE ME"."""
    root = _analysis_template(tmp_path)
    _rename(root)
    text = (root / "pyproject.toml").read_text()
    assert "REPLACE" not in text
    assert 'name = "labb-circx"' in text
    assert "A J Medford" in text


def test_a_data_spoke_is_not_given_a_package(tmp_path):
    """Only the analysis side has one; running the rename on a data spoke would
    be looking for something that is correctly absent."""
    assert not (_init(tmp_path) / "src").exists()


def test_an_outside_owner_gets_its_own_account_in_every_home_only_credential_block():
    """tcat-campaign-standard#12: the campaign skeleton's workflow attaches the CI
    token to the org alone (the org security gate refuses a token beside any other
    account); a campaign in a student's own account also needs its owner's."""
    from tcat_data.spoke_cli import owner_credentials

    block = ('          GIT_CONFIG_COUNT=1 \\\n'
             '            GIT_CONFIG_KEY_0="url.https://x-access-token:${HUB_TOKEN}@github.com/TransientCatalysis/.insteadOf" \\\n'
             '            GIT_CONFIG_VALUE_0="https://github.com/TransientCatalysis/" \\\n'
             '            python -m pip install -r ours.txt\n')
    text = block + "\n" + block
    assert owner_credentials(text, "TransientCatalysis") == text
    out = owner_credentials(text, "jdoe")
    assert out.count("GIT_CONFIG_COUNT=2") == 2 and "GIT_CONFIG_COUNT=1" not in out
    assert out.count('GIT_CONFIG_KEY_1="url.https://x-access-token:${HUB_TOKEN}@github.com/jdoe/.insteadOf"') == 2
    assert out.count("github.com/TransientCatalysis/.insteadOf") == 2       # the org stays
    assert out.count("python -m pip install -r ours.txt") == 2
