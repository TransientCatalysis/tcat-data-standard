"""Artifact identity: the grammar AND the normative hash rule.

Why the hash rule lives in the DATA hub rather than the analysis hub
-------------------------------------------------------------------
The distributed design rests on one claim: an artifact id computed at Georgia
Tech is byte-identical to one computed on a cluster at Penn State, so multiple
stores can agree on names without a central authority. That claim is only true
if the hashing rule is normative and shared. If each site's tooling canonicalises
parameters slightly differently -- key order, float formatting, how an empty
input list is encoded -- then the same computation yields two ids, the cache
never hits across sites, and the design quietly degrades into per-site scratch
directories.

So the rule is specified here, in the artifact three institutions pin, and the
analysis hub calls into it. The analysis hub still owns *what* goes into the
hash for a given tool; this module owns *how* those inputs become a digest.

Id shape
--------
    <tool>-<dataset-short-name>-<YYYY-MM-DD>-<short-hash>
    calib-ptal2o3-co-ox-2026-03-14-a3f91c

The prefix is for humans and carries no authority -- it makes a directory
listing browsable and a pipeline legible in a shell. Only the hash is trusted.
Same discipline as git short SHAs: you read the prefix, the machine reads the
digest.

Gotchas that are deliberate, not accidental
-------------------------------------------
* ``1`` and ``1.0`` hash differently. Ints and floats are distinct parameter
  values. A tool that accepts ``rtol=1`` and ``rtol=1.0`` as the same thing must
  normalise before hashing, not hope this module does it.
* Input ORDER is significant. ``tcat-calibrate --in SIGNAL --in CAL`` is not the
  same call as the reverse, because the roles are positional. Inputs are not
  sorted.
* Parameter KEY order is not significant; keys are sorted during
  canonicalisation.
* Adding a parameter with its default value still changes the hash. That is
  correct -- an explicitly-passed default is a different provenance record than
  an unstated one -- but it means tools should not helpfully inject defaults into
  the hashed parameter dict.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

#: Default short-hash length. Six hex characters is 24 bits: ample for a project
#: whose artifact count will be measured in thousands, and short enough to read
#: aloud on a call. Lengthen (never shorten) if collisions ever become plausible.
SHORT_HASH_LEN = 6

ARTIFACT_ID_RE = re.compile(
    r"^(?P<tool>[a-z][a-z0-9]*)"
    r"-(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"-(?P<date>\d{4}-\d{2}-\d{2})"
    r"-(?P<hash>[0-9a-f]{6,16})$"
)

ARTIFACT_REF_RE = re.compile(r"^art://(?P<id>.+)$")


@dataclass(frozen=True)
class ArtifactId:
    """A parsed artifact id. Purely a view over the string; carries no authority."""

    tool: str
    name: str
    date: str
    short_hash: str

    def __str__(self) -> str:
        return f"{self.tool}-{self.name}-{self.date}-{self.short_hash}"

    @property
    def ref(self) -> str:
        """The ``art://`` reference form, used where a record cites an artifact."""
        return f"art://{self}"


def _canonical(obj: Any) -> Any:
    """Recursively canonicalise a value for hashing.

    Mappings become dicts with sorted keys; sequences keep their order; sets are
    rejected rather than silently sorted, because a set-valued parameter almost
    always means the caller has lost track of an ordering that mattered.
    """
    if isinstance(obj, Mapping):
        return {str(k): _canonical(obj[k]) for k in sorted(obj, key=str)}
    if isinstance(obj, (set, frozenset)):
        raise TypeError(
            "set-valued parameters are not hashable by this rule: convert to a "
            "sorted list at the call site so the ordering is explicit and recorded"
        )
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    raise TypeError(
        f"parameter value of type {type(obj).__name__!r} cannot be canonicalised; "
        "hashed parameters must be JSON scalars, lists, or mappings"
    )


def compute_artifact_hash(
    *,
    tool_name: str,
    tool_version: str,
    inputs: Sequence[str],
    parameters: Mapping[str, Any] | None = None,
    length: int = SHORT_HASH_LEN,
) -> str:
    """Compute the normative short hash for an artifact.

    The digest covers the tool name, the tool version, the ordered input ids, and
    the parameters -- exactly the four things that determine the output. Two runs
    that agree on all four are the same computation and must produce the same id,
    which is what gives the pipeline caching for free: if the id already exists
    in the store, print it and exit.

    ``tool_version`` is included so that fixing a bug in a tool invalidates its
    prior artifacts instead of silently leaving wrong results in the cache under
    ids that still look valid.

    Note that the tool's git sha is recorded in provenance but deliberately NOT
    hashed. Hashing it would mean every commit to the analysis hub -- including a
    docstring fix -- invalidated every cached artifact, which would make the
    cache useless and push people to work around it. The version is the promise;
    the sha is the audit trail.
    """
    payload = {
        "tool_name": tool_name,
        "tool_version": tool_version,
        "inputs": list(inputs),
        "parameters": _canonical(parameters or {}),
    }
    blob = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if length < 6 or length > 16:
        raise ValueError("short hash length must be between 6 and 16 characters")
    return hashlib.sha256(blob).hexdigest()[:length]


def format_artifact_id(tool: str, name: str, when: date | str, short_hash: str) -> str:
    """Assemble an id from its parts, validating the grammar on the way out."""
    day = when.isoformat() if isinstance(when, date) else str(when)
    candidate = f"{tool}-{name}-{day}-{short_hash}"
    if not ARTIFACT_ID_RE.match(candidate):
        raise ValueError(
            f"assembled id {candidate!r} does not match the artifact-id grammar; "
            "tool and name must be lowercase alphanumeric with single hyphens"
        )
    return candidate


def make_artifact_id(
    *,
    tool: str,
    name: str,
    when: date | str,
    tool_name: str | None = None,
    tool_version: str,
    inputs: Sequence[str],
    parameters: Mapping[str, Any] | None = None,
    length: int = SHORT_HASH_LEN,
) -> str:
    """Convenience: compute the hash and format the id in one call.

    ``tool`` is the short human-facing prefix that appears in the id (``calib``,
    ``conc``, ``fit``); ``tool_name`` is the full executable name that goes into
    the hash and the provenance record (``tcat-calibrate``). They differ because
    the prefix should stay short in a shell and the tool name should stay
    unambiguous in a provenance record. Defaults to ``tool`` if omitted.
    """
    short = compute_artifact_hash(
        tool_name=tool_name or tool,
        tool_version=tool_version,
        inputs=inputs,
        parameters=parameters,
        length=length,
    )
    return format_artifact_id(tool, name, when, short)


def parse_artifact_id(artifact_id: str) -> ArtifactId:
    """Parse an id (or an ``art://`` ref) into its parts, or raise ValueError."""
    text = artifact_id
    ref = ARTIFACT_REF_RE.match(text)
    if ref:
        text = ref.group("id")
    m = ARTIFACT_ID_RE.match(text)
    if not m:
        raise ValueError(
            f"{artifact_id!r} is not a valid artifact id; expected "
            "<tool>-<name>-<YYYY-MM-DD>-<hash>"
        )
    return ArtifactId(
        tool=m.group("tool"),
        name=m.group("name"),
        date=m.group("date"),
        short_hash=m.group("hash"),
    )


def is_valid_artifact_id(artifact_id: str) -> bool:
    """True if the string is a well-formed artifact id or ``art://`` reference."""
    try:
        parse_artifact_id(artifact_id)
    except ValueError:
        return False
    return True
