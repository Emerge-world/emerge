from __future__ import annotations

from pathlib import Path

import yaml

from simulation.benchmark.schema import (
    BenchmarkManifest,
    ManifestValidationError,
    ManifestValidationIssue,
    validate_manifest_document,
)


def load_manifest(path: str | Path) -> BenchmarkManifest:
    manifest_path = Path(path)
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ManifestValidationError(
            [ManifestValidationIssue("document", f"YAML parse error: {exc}")],
            source=manifest_path,
        ) from exc
    return validate_manifest_document(document, source=manifest_path)
