"""A validator that passes on input it could not read has checked nothing.

`tcat-validate all` is the gate a data spoke's CI runs. Every case here used to
exit 0: a corrupt spoke manifest was ignored (and its declared layout with it), a
file that did not parse was reported as SKIP, a tree with nothing in it -- or a
path that does not exist -- printed "0/0 passed". And `validate()` raised a bare
TypeError on a non-string `schema_version` instead of naming the field.
"""

from __future__ import annotations

import json
from pathlib import Path

from tcat_data import validate
from tcat_data.cli import main


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_corrupt_spoke_manifest_fails_the_walk_and_is_named(tmp_path, capsys):
    _write(tmp_path / ".tcat-spoke.json", "{ not json")
    assert main(["all", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert ".tcat-spoke.json" in err and "not valid JSON" in err


def test_an_unparseable_json_file_is_an_error_not_a_skip(tmp_path, capsys):
    _write(tmp_path / "notes" / "broken.json", '{"dataset_id": ')
    assert main(["all", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "broken.json" in err and "not valid JSON" in err
    assert "SKIP" not in err


def test_an_empty_tree_is_not_a_pass(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert main(["all", str(tmp_path / "empty")]) == 1
    assert "nothing to validate" in capsys.readouterr().err


def test_a_path_that_does_not_exist_is_not_a_pass(tmp_path, capsys):
    assert main(["all", str(tmp_path / "missing")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_the_json_report_carries_the_same_failure(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert main(["--json", "all", str(tmp_path / "empty")]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_a_tree_with_one_valid_document_still_passes(tmp_path):
    """The new failures must not catch a healthy spoke."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    doc = json.loads((examples / "protocol-prbs.json").read_text(encoding="utf-8"))
    _write(tmp_path / "protocols" / "p.json", json.dumps(doc))
    assert main(["all", str(tmp_path)]) == 0


def test_a_non_string_schema_version_is_an_error_on_that_field():
    report = validate({"schema_version": 9}, "dataset")
    assert not report.ok
    assert [p.pointer for p in report.errors] == ["/schema_version"]
    assert "string" in report.errors[0].message


def test_a_document_that_is_not_an_object_is_an_error_naming_the_root():
    report = validate(["not", "an", "object"], "dataset")
    assert not report.ok
    assert report.errors[0].pointer == ""
    assert "JSON object" in report.errors[0].message and "list" in report.errors[0].message
