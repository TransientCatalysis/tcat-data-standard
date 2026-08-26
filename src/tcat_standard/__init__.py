"""tcat data standard -- the definition of a valid transient-kinetics dataset.

This package is deliberately small and deliberately boring. Three institutions
depend on it for the answer to one question: is this data ingestible? Everything
that is scientific judgement -- what a good calibration is, which fitting method
to trust -- lives in the analysis hub instead.

The dependency rule is one-directional and has no exceptions: the analysis hub
depends on this package, never the reverse. If a new analysis feature seems to
require a change here, that is evidence the schema is wrong, not that the
boundary should be crossed.

Public surface
--------------
schema      resolve and load any pinned schema version (old versions never removed)
validate    validate_dataset / _manifest_entry / _calibration / _provenance /
            _uncertainty_ensemble / _protocol -> ValidationReport
manifest    ManifestEntry: indirect, checksummed reference to bytes
checksum    sha256 of a file or a directory tree
ids         artifact-id grammar AND the normative hash rule (see ids docstring)
"""

from .checksum import sha256_file, sha256_tree
from .ids import (
    ArtifactId,
    compute_artifact_hash,
    format_artifact_id,
    is_valid_artifact_id,
    make_artifact_id,
    parse_artifact_id,
)
from .manifest import ManifestEntry
from .schema import (
    CURRENT_SCHEMA_VERSION,
    available_versions,
    load_schema,
    schema_dir,
)
from .validate import (
    ValidationError,
    ValidationReport,
    validate,
    validate_calibration,
    validate_campaign,
    validate_dataset,
    validate_manifest_entry,
    validate_model,
    validate_model_spec,
    validate_protocol,
    validate_provenance,
    validate_publication,
    validate_sample,
    validate_spoke,
    validate_uncertainty_ensemble,
)

__version__ = "0.1.0"

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ArtifactId",
    "ManifestEntry",
    "ValidationError",
    "ValidationReport",
    "available_versions",
    "compute_artifact_hash",
    "format_artifact_id",
    "is_valid_artifact_id",
    "load_schema",
    "make_artifact_id",
    "parse_artifact_id",
    "schema_dir",
    "sha256_file",
    "sha256_tree",
    "validate",
    "validate_calibration",
    "validate_campaign",
    "validate_dataset",
    "validate_manifest_entry",
    "validate_model",
    "validate_model_spec",
    "validate_protocol",
    "validate_provenance",
    "validate_publication",
    "validate_sample",
    "validate_spoke",
    "validate_uncertainty_ensemble",
    "__version__",
]
