"""Record the commit a wheel is built from, as package data (the tcat build record).

A wheel has no ``.git``, so without this the tool standard's SDK cannot tell which
commit the installed code is: it records ``git_sha: unknown`` and every artifact
an installed tool mints is ephemeral. This writes ``<package>/_tcat_build.json``
(``{"commit": <40 hex>, "dirty": <bool>}``) into each package of a wheel build,
and into an sdist's tree so a wheel built from the sdist carries it too. JSON,
never Python, so it does not enter the package's source digest. ``dirty`` follows
the SDK's rule: a modified tracked file, or an untracked ``*.py``, under the
package. Editable installs are untouched: their tree has ``.git``, which the SDK
reads directly.

Generic: the same file serves every repository whose packages live under
``src/``; list ``_tcat_build.json`` in each package's package-data. Everything
else about the build is in ``pyproject.toml``.
"""

import json
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

RECORD = "_tcat_build.json"
ROOT = Path(__file__).resolve().parent


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _record(package_dir):
    """The build record for one package, or None outside a git checkout."""
    commit = (_git("rev-parse", "HEAD") or "").strip()
    if len(commit) != 40:
        return None
    status = _git("status", "--porcelain", "--untracked-files=all", "--", str(package_dir))
    if status is None:
        return None
    dirty = any(line.strip() and (not line.startswith("??")
                                  or line[3:].strip().strip('"').endswith(".py"))
                for line in status.splitlines())
    return {"commit": commit, "dirty": dirty}


def _packages():
    src = ROOT / "src"
    return sorted(p for p in src.iterdir() if p.is_dir() and (p / "__init__.py").is_file())


class BuildPyRecordingCommit(build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            return
        for package in _packages():
            record = _record(package)
            if record is None:
                continue  # no git (a build from an sdist): the record it carried stands
            target = Path(self.build_lib) / package.name / RECORD
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record) + "\n", encoding="utf-8")


class SdistRecordingCommit(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        for package in _packages():
            record = _record(package)
            if record is not None:
                target = Path(base_dir) / "src" / package.name / RECORD
                target.write_text(json.dumps(record) + "\n", encoding="utf-8")


setup(cmdclass={"build_py": BuildPyRecordingCommit, "sdist": SdistRecordingCommit})
