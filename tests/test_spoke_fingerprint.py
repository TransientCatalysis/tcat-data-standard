"""Did the shipped code change without the version changing?

The version is hashed into every artifact id a spoke's tools mint, so bumping it
is what makes older artifacts stale instead of silently reused. Forgetting to
bump it is invisible: the store keeps serving pre-change results under ids that
look correct, which is the worst failure mode this project has.

It therefore cannot be left to memory -- especially where spokes are developed by
agents, which will happily fix a solver without ever thinking about artifact
identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcat_standard.spoke import (
    FINGERPRINT,
    check_fingerprint,
    read_version,
    source_digest,
    write_fingerprint,
)


@pytest.fixture
def spoke(tmp_path: Path) -> Path:
    pkg = tmp_path / "src" / "tcat_demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (pkg / "science.py").write_text("def rate(k):\n    return k * 2\n")
    write_fingerprint(tmp_path)
    return tmp_path


def test_a_clean_spoke_passes(spoke):
    assert check_fingerprint(spoke) == []


def test_changing_shipped_code_without_the_version_is_caught(spoke):
    """The whole point."""
    (spoke / "src" / "tcat_demo" / "science.py").write_text("def rate(k):\n    return k * 3\n")
    findings = check_fingerprint(spoke)
    assert findings
    assert "VERSION DID NOT" in str(findings[0])


def test_the_message_says_what_to_do_in_both_cases(spoke):
    """A check that only says "wrong" gets worked around. This one has to
    distinguish "bump it" from "you considered it and it cannot change output"."""
    (spoke / "src" / "tcat_demo" / "science.py").write_text("def rate(k):\n    return k * 3\n")
    msg = str(check_fingerprint(spoke)[0])
    assert "bump __version__" in msg
    assert "cannot change output" in msg


def test_bumping_the_version_is_also_caught_until_recorded(spoke):
    """Not an error exactly -- a reminder that the record is the committed
    artifact, so a bump nobody recorded leaves CI red until they do."""
    init = spoke / "src" / "tcat_demo" / "__init__.py"
    init.write_text('__version__ = "0.2.0"\n')
    findings = check_fingerprint(spoke)
    assert findings and "0.2.0" in str(findings[0])
    write_fingerprint(spoke)
    assert check_fingerprint(spoke) == []


def test_editing_tests_or_docs_does_not_trip_it(spoke):
    """A rule that fired on a docstring typo would be switched off within a week.
    Only what ships in the wheel can change a tool's output."""
    (spoke / "tests").mkdir()
    (spoke / "tests" / "test_x.py").write_text("def test_nothing(): pass\n")
    (spoke / "README.md").write_text("# words\n")
    (spoke / "notebook.ipynb").write_text("{}")
    assert check_fingerprint(spoke) == []


def test_a_missing_fingerprint_is_reported_with_the_command_that_makes_one(spoke):
    (spoke / FINGERPRINT).unlink()
    findings = check_fingerprint(spoke)
    assert findings and "tcat-spoke fingerprint" in str(findings[0])


def test_a_repository_that_ships_nothing_is_not_this_checks_business(tmp_path):
    """A data spoke has no `src/`. It must not fail a check about shipped code."""
    assert check_fingerprint(tmp_path) == []


def test_the_digest_is_stable_across_runs(spoke):
    assert source_digest(spoke)[0] == source_digest(spoke)[0]


def test_the_digest_covers_file_names_not_just_contents(spoke):
    """Renaming a module changes what imports resolve, so it must change the
    digest even though the bytes are identical."""
    before = source_digest(spoke)[0]
    pkg = spoke / "src" / "tcat_demo"
    (pkg / "science.py").rename(pkg / "kinetics.py")
    assert source_digest(spoke)[0] != before


def test_the_version_is_read_without_importing_the_package(spoke):
    """The check has to run in a CI job that may deliberately lack the spoke's
    dependencies, so it must not import it."""
    (spoke / "src" / "tcat_demo" / "science.py").write_text("import a_package_that_is_not_installed\n")
    assert read_version(spoke) == "0.1.0"


def test_the_recorded_file_says_it_is_generated(spoke):
    recorded = json.loads((spoke / FINGERPRINT).read_text())
    assert "GENERATED" in recorded["$comment"]
