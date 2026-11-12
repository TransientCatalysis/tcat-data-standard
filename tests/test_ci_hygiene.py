"""This repository's own CI: pinned actions, no hub token, one shared tcat_ref.

All three are properties of text a reviewer skims, so they are checked here
rather than left to review. A third-party action on a tag runs whatever was last
pushed to that tag; the standards and tools are public, so a token in this CI
would only widen what a compromised step could reach; and the sibling-branch
helper, pasted into each workflow, drifted between copies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))

#: First-party references follow main by design (the security gate, tcat-ref):
#: they hold no credential, and a pinned caller would keep passing a gate the org
#: has since tightened.
FIRST_PARTY = re.compile(r"^TransientCatalysis/\.github/[\w./-]+@main$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _uses(path: Path) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\s*(?:-\s+)?uses:\s*(\S+)", path.read_text(), re.M)]


def test_there_are_workflows_to_check():
    assert WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_third_party_action_is_pinned_to_a_commit(path):
    loose = [u for u in _uses(path)
             if not (u.startswith("./") or FIRST_PARTY.match(u) or PINNED.match(u))]
    assert not loose, f"{path.name}: not pinned to a 40-hex commit: {loose}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_uses_the_hub_token(path):
    text = path.read_text()
    assert "TCAT_HUB_TOKEN" not in text and "x-access-token:${" not in text, (
        f"{path.name}: every sibling is public; install it without a credential")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_defines_its_own_tcat_ref(path):
    assert "tcat_ref() {" not in path.read_text(), (
        f"{path.name}: use TransientCatalysis/.github/actions/tcat-ref, the one definition")
