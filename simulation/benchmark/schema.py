from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_TOP_LEVEL_KEYS = {
    "version",
    "benchmark",
    "defaults",
    "seed_sets",
    "scenarios",
    "arms",
    "matrix",
    "metrics",
    "criteria",
    "wandb",
}
_BENCHMARK_KEYS = {"id", "version", "description"}
_OVERRIDE_KEYS = {
    "runtime",
    "capabilities",
    "persistence",
    "oracle",
    "world_overrides",
    "tags",
}
_RUNTIME_KEYS = {
    "use_llm",
    "model",
    "agents",
    "ticks",
    "seed",
    "width",
    "height",
    "start_hour",
}
_CAPABILITY_KEYS = {
    "explicit_planning",
    "semantic_memory",
    "innovation",
    "item_reflection",
    "social",
    "teach",
    "reproduction",
}
_PERSISTENCE_KEYS = {"mode", "clean_before_run"}
_ORACLE_KEYS = {"mode", "freeze_precedents_path"}
_WORLD_OVERRIDE_KEYS = {
    "initial_resource_scale",
    "regen_chance_scale",
    "regen_amount_scale",
    "world_fixture",
}
_MATRIX_KEYS = {"seed_sets", "scenarios", "arms"}
_METRIC_KEYS = {"primary", "secondary"}
_WANDB_KEYS = {"enabled", "project", "group_by"}
_CRITERION_KEYS = {
    "id",
    "scenario",
    "compare",
    "metric",
    "min_delta_abs",
    "min_delta_rel",
    "arm",
    "op",
    "threshold",
    "description",
    "when_seed_set",
    "group_by",
}
_PERSISTENCE_MODES = {"none", "oracle", "lineage", "full"}
_ORACLE_MODES = {"live", "frozen", "symbolic"}


@dataclass(slots=True)
class ManifestValidationIssue:
    path: str
    message: str


class ManifestValidationError(ValueError):
    def __init__(
        self,
        issues: Sequence[ManifestValidationIssue],
        *,
        source: str | Path | None = None,
    ) -> None:
        self.issues = list(issues)
        self.source = str(source) if source is not None else None
        super().__init__(str(self))

    def __str__(self) -> str:
        header = "Invalid benchmark manifest"
        if self.source:
            header = f"{header} {self.source}"
        details = [f"- {issue.path}: {issue.message}" for issue in self.issues]
        return "\n".join([header, *details])


@dataclass(slots=True)
class BenchmarkInfo:
    id: str
    version: str
    description: str | None = None


@dataclass(slots=True)
class ProfileOverride:
    runtime: dict[str, object] = field(default_factory=dict)
    capabilities: dict[str, object] = field(default_factory=dict)
    persistence: dict[str, object] = field(default_factory=dict)
    oracle: dict[str, object] = field(default_factory=dict)
    world_overrides: dict[str, object] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MatrixSelection:
    seed_sets: list[str]
    scenarios: list[str]
    arms: list[str]


@dataclass(slots=True)
class MetricsConfig:
    primary: list[str]
    secondary: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CriterionConfig:
    id: str | None = None
    scenario: str | None = None
    compare: str | None = None
    metric: str | None = None
    min_delta_abs: int | float | None = None
    min_delta_rel: int | float | None = None
    arm: str | None = None
    op: str | None = None
    threshold: int | float | None = None
    description: str | None = None
    when_seed_set: str | None = None
    group_by: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WandbConfig:
    enabled: bool | None = None
    project: str | None = None
    group_by: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkManifest:
    version: int
    benchmark: BenchmarkInfo
    defaults: ProfileOverride
    seed_sets: dict[str, list[int]]
    scenarios: dict[str, ProfileOverride]
    arms: dict[str, ProfileOverride]
    matrix: MatrixSelection
    metrics: MetricsConfig
    criteria: list[CriterionConfig]
    wandb: WandbConfig


def validate_manifest_document(
    document: object,
    *,
    source: str | Path | None = None,
) -> BenchmarkManifest:
    issues: list[ManifestValidationIssue] = []

    if not isinstance(document, Mapping):
        raise ManifestValidationError(
            [ManifestValidationIssue("document", "must be a mapping")],
            source=source,
        )

    raw = dict(document)
    _check_unknown_keys(raw, _TOP_LEVEL_KEYS, "top-level", issues)

    version = _validate_version(raw.get("version"), issues)
    benchmark = _validate_benchmark(raw.get("benchmark"), issues)
    defaults = _validate_override(raw.get("defaults"), "defaults", issues)
    seed_sets = _validate_seed_sets(raw.get("seed_sets"), issues)
    scenarios = _validate_overrides_map(raw.get("scenarios"), "scenarios", issues)
    arms = _validate_overrides_map(raw.get("arms"), "arms", issues)
    matrix = _validate_matrix(raw.get("matrix"), seed_sets, scenarios, arms, issues)
    metrics = _validate_metrics(raw.get("metrics"), issues)
    criteria = _validate_criteria(raw.get("criteria"), issues)
    wandb = _validate_wandb(raw.get("wandb"), issues)

    if issues:
        raise ManifestValidationError(issues, source=source)

    return BenchmarkManifest(
        version=version,
        benchmark=benchmark,
        defaults=defaults,
        seed_sets=seed_sets,
        scenarios=scenarios,
        arms=arms,
        matrix=matrix,
        metrics=metrics,
        criteria=criteria,
        wandb=wandb,
    )


def _validate_version(value: object, issues: list[ManifestValidationIssue]) -> int:
    if value is None:
        issues.append(ManifestValidationIssue("version", "is required"))
        return 1
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(ManifestValidationIssue("version", "must be integer literal 1"))
        return 1
    if value != 1:
        issues.append(ManifestValidationIssue("version", "expected literal 1"))
    return value


def _validate_benchmark(value: object, issues: list[ManifestValidationIssue]) -> BenchmarkInfo:
    mapping = _require_mapping(value, "benchmark", issues)
    _check_unknown_keys(mapping, _BENCHMARK_KEYS, "benchmark", issues)

    benchmark_id = _require_non_empty_string(mapping.get("id"), "benchmark.id", issues)
    version = _require_string(mapping.get("version"), "benchmark.version", issues)
    description = _optional_string(mapping.get("description"), "benchmark.description", issues)
    return BenchmarkInfo(id=benchmark_id, version=version, description=description)


def _validate_override(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
) -> ProfileOverride:
    mapping = _require_mapping(value, path, issues)
    _check_unknown_keys(mapping, _OVERRIDE_KEYS, path, issues)

    return ProfileOverride(
        runtime=_validate_typed_section(mapping.get("runtime"), path, "runtime", _RUNTIME_KEYS, _validate_runtime_value, issues),
        capabilities=_validate_typed_section(mapping.get("capabilities"), path, "capabilities", _CAPABILITY_KEYS, _validate_bool, issues),
        persistence=_validate_typed_section(mapping.get("persistence"), path, "persistence", _PERSISTENCE_KEYS, _validate_persistence_value, issues),
        oracle=_validate_typed_section(mapping.get("oracle"), path, "oracle", _ORACLE_KEYS, _validate_oracle_value, issues),
        world_overrides=_validate_typed_section(mapping.get("world_overrides"), path, "world_overrides", _WORLD_OVERRIDE_KEYS, _validate_world_override_value, issues),
        tags=_validate_tags(mapping.get("tags"), f"{path}.tags", issues),
    )


def _validate_seed_sets(
    value: object,
    issues: list[ManifestValidationIssue],
) -> dict[str, list[int]]:
    mapping = _require_mapping(value, "seed_sets", issues)
    result: dict[str, list[int]] = {}
    for key, seeds in mapping.items():
        key_path = f"seed_sets.{key}"
        if not isinstance(key, str) or not key:
            issues.append(ManifestValidationIssue(key_path, "key must be a non-empty string"))
            continue
        if not isinstance(seeds, list):
            issues.append(ManifestValidationIssue(key_path, "must be a list of integers"))
            result[key] = []
            continue
        if not seeds:
            issues.append(ManifestValidationIssue(key_path, "must contain at least one seed"))
        typed_seeds: list[int] = []
        for index, seed in enumerate(seeds):
            if not isinstance(seed, int) or isinstance(seed, bool):
                issues.append(
                    ManifestValidationIssue(
                        f"{key_path}[{index}]",
                        f"expected int, got {seed!r}",
                    )
                )
                continue
            typed_seeds.append(seed)
        result[key] = typed_seeds
    return result


def _validate_overrides_map(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
) -> dict[str, ProfileOverride]:
    mapping = _require_mapping(value, path, issues)
    result: dict[str, ProfileOverride] = {}
    for key, override_value in mapping.items():
        key_path = f"{path}.{key}"
        if not isinstance(key, str) or not key:
            issues.append(ManifestValidationIssue(key_path, "key must be a non-empty string"))
            continue
        result[key] = _validate_override(override_value, key_path, issues)
    return result


def _validate_matrix(
    value: object,
    seed_sets: Mapping[str, list[int]],
    scenarios: Mapping[str, ProfileOverride],
    arms: Mapping[str, ProfileOverride],
    issues: list[ManifestValidationIssue],
) -> MatrixSelection:
    mapping = _require_mapping(value, "matrix", issues)
    _check_unknown_keys(mapping, _MATRIX_KEYS, "matrix", issues)

    seed_set_values = _validate_matrix_axis(
        mapping.get("seed_sets"),
        "matrix.seed_sets",
        seed_sets,
        "seed set",
        issues,
    )
    scenario_values = _validate_matrix_axis(
        mapping.get("scenarios"),
        "matrix.scenarios",
        scenarios,
        "scenario",
        issues,
    )
    arm_values = _validate_matrix_axis(
        mapping.get("arms"),
        "matrix.arms",
        arms,
        "arm",
        issues,
    )
    return MatrixSelection(
        seed_sets=seed_set_values,
        scenarios=scenario_values,
        arms=arm_values,
    )


def _validate_metrics(value: object, issues: list[ManifestValidationIssue]) -> MetricsConfig:
    mapping = _require_mapping(value, "metrics", issues)
    _check_unknown_keys(mapping, _METRIC_KEYS, "metrics", issues)
    primary = _validate_string_list(mapping.get("primary"), "metrics.primary", issues, required=True)
    secondary = _validate_string_list(mapping.get("secondary"), "metrics.secondary", issues, required=False)
    return MetricsConfig(primary=primary, secondary=secondary)


def _validate_criteria(value: object, issues: list[ManifestValidationIssue]) -> list[CriterionConfig]:
    if value is None:
        issues.append(ManifestValidationIssue("criteria", "is required"))
        return []
    if not isinstance(value, list):
        issues.append(ManifestValidationIssue("criteria", "must be a list"))
        return []
    result: list[CriterionConfig] = []
    for index, item in enumerate(value):
        path = f"criteria[{index}]"
        if not isinstance(item, Mapping):
            issues.append(ManifestValidationIssue(path, "must be a mapping"))
            continue
        criterion = dict(item)
        _check_unknown_keys(criterion, _CRITERION_KEYS, path, issues)

        result.append(
            CriterionConfig(
                id=_optional_non_empty_string(criterion.get("id"), f"{path}.id", issues),
                scenario=_optional_non_empty_string(criterion.get("scenario"), f"{path}.scenario", issues),
                compare=_optional_non_empty_string(criterion.get("compare"), f"{path}.compare", issues),
                metric=_optional_non_empty_string(criterion.get("metric"), f"{path}.metric", issues),
                min_delta_abs=_optional_number(criterion.get("min_delta_abs"), f"{path}.min_delta_abs", issues),
                min_delta_rel=_optional_number(criterion.get("min_delta_rel"), f"{path}.min_delta_rel", issues),
                arm=_optional_non_empty_string(criterion.get("arm"), f"{path}.arm", issues),
                op=_optional_non_empty_string(criterion.get("op"), f"{path}.op", issues),
                threshold=_optional_number(criterion.get("threshold"), f"{path}.threshold", issues),
                description=_optional_non_empty_string(criterion.get("description"), f"{path}.description", issues),
                when_seed_set=_optional_non_empty_string(criterion.get("when_seed_set"), f"{path}.when_seed_set", issues),
                group_by=_validate_string_list(criterion.get("group_by"), f"{path}.group_by", issues, required=False),
            )
        )
    return result


def _validate_wandb(value: object, issues: list[ManifestValidationIssue]) -> WandbConfig:
    mapping = _require_mapping(value, "wandb", issues)
    _check_unknown_keys(mapping, _WANDB_KEYS, "wandb", issues)
    enabled = mapping.get("enabled")
    if enabled is not None:
        _validate_bool(enabled, "wandb.enabled", issues)
    project = mapping.get("project")
    if project is not None:
        _require_string(project, "wandb.project", issues)
    group_by = mapping.get("group_by")
    typed_group_by: list[str] = []
    if group_by is not None:
        typed_group_by = _validate_string_list(group_by, "wandb.group_by", issues, required=False)
    return WandbConfig(
        enabled=enabled if isinstance(enabled, bool) else None,
        project=project if isinstance(project, str) else None,
        group_by=typed_group_by,
    )


def _validate_typed_section(
    value: object,
    parent_path: str,
    section_name: str,
    allowed_keys: set[str],
    value_validator,
    issues: list[ManifestValidationIssue],
) -> dict[str, object]:
    if value is None:
        return {}
    path = f"{parent_path}.{section_name}"
    mapping = _require_mapping(value, path, issues)
    _check_unknown_keys(mapping, allowed_keys, path, issues)
    result: dict[str, object] = {}
    for key, item in mapping.items():
        result[key] = value_validator(item, f"{path}.{key}", issues, key)
    return result


def _validate_tags(value: object, path: str, issues: list[ManifestValidationIssue]) -> list[str]:
    return _validate_string_list(value, path, issues, required=False)


def _validate_matrix_axis(
    value: object,
    path: str,
    known_values: Mapping[str, object],
    label: str,
    issues: list[ManifestValidationIssue],
) -> list[str]:
    values = _validate_string_list(value, path, issues, required=True)
    seen: set[str] = set()
    for index, item in enumerate(values):
        if item in seen:
            issues.append(ManifestValidationIssue(f"{path}[{index}]", f"duplicate {label} reference {item!r}"))
        else:
            seen.add(item)
        if item not in known_values:
            issues.append(ManifestValidationIssue(f"{path}[{index}]", f"unknown {label} {item!r}"))
    return values


def _validate_string_list(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
    *,
    required: bool,
) -> list[str]:
    if value is None:
        if required:
            issues.append(ManifestValidationIssue(path, "is required"))
        return []
    if not isinstance(value, list):
        issues.append(ManifestValidationIssue(path, "must be a list of strings"))
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            issues.append(ManifestValidationIssue(f"{path}[{index}]", "must be a non-empty string"))
            continue
        result.append(item)
    if required and not result:
        issues.append(ManifestValidationIssue(path, "must contain at least one value"))
    return result


def _validate_runtime_value(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
    key: str,
) -> object:
    if key in {"use_llm"}:
        _validate_bool(value, path, issues)
        return value
    if key in {"model"}:
        if value is not None and not isinstance(value, str):
            issues.append(ManifestValidationIssue(path, "must be a string or null"))
        return value
    if key in {"ticks", "seed"}:
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            issues.append(ManifestValidationIssue(path, "must be an int or null"))
        return value
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(ManifestValidationIssue(path, f"expected int, got {value!r}"))
    return value


def _validate_persistence_value(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
    key: str,
) -> object:
    if key == "mode":
        if not isinstance(value, str) or value not in _PERSISTENCE_MODES:
            issues.append(
                ManifestValidationIssue(
                    path,
                    f"must be one of {sorted(_PERSISTENCE_MODES)!r}",
                )
            )
        return value
    _validate_bool(value, path, issues)
    return value


def _validate_oracle_value(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
    key: str,
) -> object:
    if key == "mode":
        if not isinstance(value, str) or value not in _ORACLE_MODES:
            issues.append(
                ManifestValidationIssue(
                    path,
                    f"must be one of {sorted(_ORACLE_MODES)!r}",
                )
            )
        return value
    if value is not None and not isinstance(value, str):
        issues.append(ManifestValidationIssue(path, "must be a string or null"))
    return value


def _validate_world_override_value(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
    key: str,
) -> object:
    if key == "world_fixture":
        if value is not None and not isinstance(value, str):
            issues.append(ManifestValidationIssue(path, "must be a string or null"))
        return value
    if value is not None and not isinstance(value, (int, float)):
        issues.append(ManifestValidationIssue(path, "must be a number or null"))
    return value


def _validate_bool(value: object, path: str, issues: list[ManifestValidationIssue], *_: object) -> bool:
    if not isinstance(value, bool):
        issues.append(ManifestValidationIssue(path, "must be a boolean"))
    return bool(value)


def _require_mapping(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
) -> dict[str, object]:
    if value is None:
        issues.append(ManifestValidationIssue(path, "is required"))
        return {}
    if not isinstance(value, Mapping):
        issues.append(ManifestValidationIssue(path, "must be a mapping"))
        return {}
    return dict(value)


def _require_non_empty_string(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
) -> str:
    if not isinstance(value, str) or not value:
        issues.append(ManifestValidationIssue(path, "must be a non-empty string"))
        return ""
    return value


def _require_string(value: object, path: str, issues: list[ManifestValidationIssue]) -> str:
    if not isinstance(value, str):
        issues.append(ManifestValidationIssue(path, "must be a string"))
        return ""
    return value


def _optional_string(value: object, path: str, issues: list[ManifestValidationIssue]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(ManifestValidationIssue(path, "must be a string"))
        return None
    return value


def _optional_non_empty_string(
    value: object,
    path: str,
    issues: list[ManifestValidationIssue],
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        issues.append(ManifestValidationIssue(path, "must be a non-empty string"))
        return None
    return value


def _optional_number(value: object, path: str, issues: list[ManifestValidationIssue]) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(ManifestValidationIssue(path, "must be a number"))
        return None
    return value


def _check_unknown_keys(
    mapping: Mapping[str, object],
    allowed_keys: set[str],
    path: str,
    issues: list[ManifestValidationIssue],
) -> None:
    for key in mapping:
        if key in allowed_keys:
            continue
        issues.append(ManifestValidationIssue(f"{path}.{key}", "is not allowed"))
