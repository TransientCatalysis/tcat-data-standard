"""What the data skeleton's workflows and guides may say.

Every repository made by `tcat-spoke init --kind data` inherits these files, so
a floating action tag or an instruction that only made sense while the toolchain
was private is copied into every new spoke.
"""

from __future__ import annotations

import re

from tcat_data import scaffold

#: The org's own gate, called as a reusable workflow, tracks main on purpose (the
#: workflow file says why); every other `uses:` names a commit.
ORG_GATE = "TransientCatalysis/.github/.github/workflows/security.yml@main"


def _workflows():
    return sorted((scaffold.source("data") / "dot-github" / "workflows").glob("*.yml"))


def test_every_action_in_the_skeletons_workflows_is_pinned_to_a_commit():
    unpinned = []
    for wf in _workflows():
        for ref in re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", wf.read_text(encoding="utf-8"), re.M):
            if ref != ORG_GATE and not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref):
                unpinned.append(f"{wf.name}: {ref}")
    assert _workflows() and unpinned == []


def test_the_skeleton_tells_nobody_to_make_it_private_or_find_a_token():
    """The toolchain is public: a token is needed only for a private dependency,
    and a repository's visibility is its owner's choice. Template wording goes
    too -- init writes a new directory; there is no template repository."""
    banned = re.compile(r"--private|Team plan|TCAT_HUB_TOKEN|Make it private|This is a template|"
                        r"IS_TEMPLATE|template repository")
    hits = []
    for path in scaffold.source("data").rglob("*"):
        if path.is_file():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if banned.search(line):
                    hits.append(f"{path.name}:{n}: {line.strip()}")
    assert hits == []
