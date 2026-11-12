"""`tcat-spoke check` on a campaign, the vendored org generator, and the fingerprint
check without a format marker."""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

from tcat_data import spoke
from tcat_data.spoke_cli import main


def _campaign(tmp_path: Path) -> Path:
    root = tmp_path / "a-study"
    root.mkdir()
    (root / "campaign.json").write_text(json.dumps({"campaign_id": "a-study"}))
    return root


def test_check_hands_a_campaign_to_the_campaign_gate_and_returns_its_verdict(tmp_path, monkeypatch):
    """A campaign has no .tcat-spoke.json; this check used to report "no spoke
    manifest, run tcat-spoke init" -- advice that would overwrite the campaign."""
    calls = []
    fake = types.ModuleType("tcat_campaign.cli")
    fake.main = lambda argv: calls.append(argv) or 3
    monkeypatch.setitem(sys.modules, "tcat_campaign", types.ModuleType("tcat_campaign"))
    monkeypatch.setitem(sys.modules, "tcat_campaign.cli", fake)
    root = _campaign(tmp_path)
    assert main(["check", str(root)]) == 3
    assert calls == [["check", str(root)]]


def test_check_on_a_campaign_refuses_loudly_when_the_campaign_standard_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tcat_campaign", None)
    monkeypatch.setitem(sys.modules, "tcat_campaign.cli", None)
    assert main(["check", str(_campaign(tmp_path))]) == 1
    err = capsys.readouterr().err
    assert "tcat-campaign check" in err and "Nothing was checked" in err


def test_a_fingerprint_record_is_judged_by_its_digests_not_a_format_marker(tmp_path):
    """The format marker separated a pre-digest file layout no repository carries
    any more; the digests are what the check is about."""
    pkg = tmp_path / "src" / "tcat_x"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "0.1.0"\nVALUE = 1\n')
    record = spoke.write_fingerprint(tmp_path)
    record.pop("format")
    (tmp_path / spoke.FINGERPRINT).write_text(json.dumps(record))
    assert spoke.check_fingerprint(tmp_path) == []
    (pkg / "__init__.py").write_text('__version__ = "0.1.0"\nVALUE = 2\n')
    assert any("out of date" in str(f) for f in spoke.check_fingerprint(tmp_path))


def _org_copy() -> Path | None:
    """The canonical generator, in a checkout of the org's `.github` repository:
    TCAT_ORG_TOOLING names one; otherwise a sibling checkout is looked for."""
    named = os.environ.get("TCAT_ORG_TOOLING")
    candidates = [Path(named)] if named else []
    here = Path(__file__).resolve().parents[1]
    candidates += [here.parent / "org-profile", here.parent / ".github"]
    for c in candidates:
        f = c / "scripts" / "generate_agents_md.py"
        if f.is_file():
            return f
    return None


def test_the_vendored_org_generator_is_byte_identical_to_the_orgs():
    """`tcat-spoke init` writes the gate's files with a copy of the org's generator.
    A copy that drifted would write files the gate then calls out of step, on every
    new repository. Refuses rather than skips when the org copy cannot be found: a
    check that reports success without running is worse than one that fails."""
    org = _org_copy()
    if org is None:
        pytest.fail("no checkout of the org's .github repository found: set TCAT_ORG_TOOLING "
                    "to one (CI checks it out), or clone it beside this repository")
    ours = Path(__file__).resolve().parents[1] / "src" / "tcat_data" / "org_files.py"
    assert ours.read_bytes() == org.read_bytes(), (
        f"{ours} differs from {org}: edit the org copy, then copy it here")


def test_the_generator_check_reads_and_never_writes(tmp_path):
    """The gate's --check created .github/workflows/ in the repository it checked."""
    from tcat_data import org_files

    root = tmp_path / "x"
    root.mkdir()
    (root / "campaign.json").write_text("{}")
    assert len(org_files.drifted(root)) == 5
    assert sorted(p.name for p in root.iterdir()) == ["campaign.json"]
