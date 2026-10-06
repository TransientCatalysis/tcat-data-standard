"""Schema 0.7.0: a campaign may be frozen, and may hold notebooks.

Both blocks are recorded decisions, so their shape is the whole contract: a freeze
that does not say why, or a hold that does not say at which identities, would be a
state nobody could audit or undo.
"""

import copy
import json
from pathlib import Path

import pytest

from tcat_data import validate_campaign

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "campaign-example.json"

PIN = {"name": "tcat-fit", "version": "0.1.0", "digest": "fd0cf215"}
FREEZE = {"date": "2026-10-05", "reason": "published with the 2026 paper", "environment": "frozen-environment.txt"}
HOLD = {"notebook": "examples/03_fit.ipynb", "reason": "six hours on 32 cores", "date": "2026-10-05",
        "tools": [PIN]}


def _campaign(**extra):
    doc = copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    doc["schema_version"] = "0.7.0"
    doc.update(extra)
    return doc


def test_a_campaign_without_either_block_means_what_it_meant_before():
    assert validate_campaign(_campaign()).ok


def test_a_complete_campaign_may_be_frozen():
    assert validate_campaign(_campaign(status="complete", freeze=FREEZE)).ok


@pytest.mark.parametrize("status", ["planned", "active"])
def test_a_study_still_being_developed_cannot_be_frozen(status):
    """There is no single toolchain to freeze a study at while it is still moving."""
    assert not validate_campaign(_campaign(status=status, freeze=FREEZE)).ok


@pytest.mark.parametrize("missing", ["date", "reason", "environment"])
def test_a_freeze_says_when_why_and_how_to_reinstall(missing):
    freeze = {k: v for k, v in FREEZE.items() if k != missing}
    assert not validate_campaign(_campaign(status="complete", freeze=freeze)).ok


def test_a_freeze_reason_is_a_sentence_not_a_shrug():
    assert not validate_campaign(_campaign(status="complete", freeze={**FREEZE, "reason": "done"})).ok


def test_an_active_campaign_may_hold_a_notebook():
    assert validate_campaign(_campaign(held=[HOLD])).ok


@pytest.mark.parametrize("missing", ["notebook", "reason", "date", "tools"])
def test_a_hold_names_the_notebook_why_when_and_at_which_identities(missing):
    hold = {k: v for k, v in HOLD.items() if k != missing}
    assert not validate_campaign(_campaign(held=[hold])).ok


def test_a_hold_records_a_digest_for_every_identity():
    """A hold without a digest is a hold at a version number, and the version is not
    what identifies the code (contract 0.2.0)."""
    bad = {**HOLD, "tools": [{"name": "tcat-fit", "version": "0.1.0"}]}
    assert not validate_campaign(_campaign(held=[bad])).ok


def test_a_hold_names_a_repository_relative_notebook():
    assert not validate_campaign(_campaign(held=[{**HOLD, "notebook": "/abs/03_fit.ipynb"}])).ok
    assert not validate_campaign(_campaign(held=[{**HOLD, "notebook": "examples/03_fit.py"}])).ok


def test_the_blocks_do_not_exist_under_the_frozen_0_6_0():
    """0.6.0 is retained and never amended, so a record must declare 0.7.0 to use them."""
    doc = _campaign(held=[HOLD])
    doc["schema_version"] = "0.6.0"
    assert not validate_campaign(doc).ok
