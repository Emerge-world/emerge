#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise SystemExit(
            "PyYAML no está instalado. Ejecuta: uv add pyyaml\n"
            f"Detalle original: {exc}"
        ) from exc

    if not path.exists():
        raise SystemExit(f"Manifest no encontrado: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Manifest inválido: {path}")
    return data


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return rows


def _ensure_repo_root(repo_root: Path) -> None:
    expected = [repo_root / "main.py", repo_root / "run_batch.py", repo_root / "simulation"]
    missing = [str(p.relative_to(repo_root)) for p in expected if not p.exists()]
    if missing:
        raise SystemExit(
            "Este script debe ejecutarse dentro del repo de Emerge o con --repo-root apuntando al repo.\n"
            f"Faltan: {', '.join(missing)}"
        )


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _snapshot_run_dirs(runs_root: Path) -> dict[str, float]:
    if not runs_root.exists():
        return {}
    out: dict[str, float] = {}
    for path in runs_root.iterdir():
        if path.is_dir():
            try:
                out[path.name] = path.stat().st_mtime
            except OSError:
                continue
    return out


def _detect_new_run_dir(before: dict[str, float], after: dict[str, float], runs_root: Path) -> Path | None:
    new_names = sorted(set(after) - set(before))
    if len(new_names) == 1:
        return runs_root / new_names[0]
    if len(new_names) > 1:
        newest = max(new_names, key=lambda name: after.get(name, 0.0))
        return runs_root / newest
    if after:
        newest_existing = max(after, key=lambda name: after.get(name, 0.0))
        if after[newest_existing] > max(before.values(), default=0.0):
            return runs_root / newest_existing
    return None


def _clean_persistence(repo_root: Path, seed: int) -> list[str]:
    removed: list[str] = []
    for rel in [f"data/precedents_{seed}.json", f"data/lineage_{seed}.json"]:
        path = repo_root / rel
        if path.exists():
            try:
                path.unlink()
                removed.append(rel)
            except OSError:
                pass
    return removed


def _read_metrics(run_dir: Path) -> dict[str, Any]:
    meta = _load_json(run_dir / "meta.json", default={}) or {}
    summary = _load_json(run_dir / "metrics" / "summary.json", default={}) or {}
    timeseries = _load_jsonl(run_dir / "metrics" / "timeseries.jsonl")

    initial_count = (summary.get("agents") or {}).get("initial_count", 0) or 0
    final_survivors = (summary.get("agents") or {}).get("final_survivors", []) or []
    survival_rate = (summary.get("agents") or {}).get("survival_rate")
    oracle_success_rate = (summary.get("actions") or {}).get("oracle_success_rate")
    parse_fail_rate = (summary.get("actions") or {}).get("parse_fail_rate")
    total_ticks = summary.get("total_ticks") or 0

    alive_auc_ratio = None
    tail20_mean_hunger = None
    tail20_mean_energy = None

    if timeseries and initial_count:
        alive_sum = sum(max(0, int(row.get("alive", 0) or 0)) for row in timeseries)
        denom = initial_count * len(timeseries)
        alive_auc_ratio = round(alive_sum / denom, 4) if denom else None

        tail_n = max(1, math.ceil(len(timeseries) * 0.20))
        tail = timeseries[-tail_n:]
        hunger_vals = [float(row.get("mean_hunger", 0.0) or 0.0) for row in tail]
        energy_vals = [float(row.get("mean_energy", 0.0) or 0.0) for row in tail]
        tail20_mean_hunger = round(sum(hunger_vals) / len(hunger_vals), 4) if hunger_vals else None
        tail20_mean_energy = round(sum(energy_vals) / len(energy_vals), 4) if energy_vals else None

    return {
        "run_id": meta.get("run_id"),
        "run_dir": str(run_dir),
        "summary_path": str(run_dir / "metrics" / "summary.json"),
        "timeseries_path": str(run_dir / "metrics" / "timeseries.jsonl"),
        "created_at": meta.get("created_at"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "seed": meta.get("seed"),
        "initial_count": initial_count,
        "final_survivors_count": len(final_survivors),
        "deaths": (summary.get("agents") or {}).get("deaths"),
        "survival_rate": survival_rate,
        "oracle_success_rate": oracle_success_rate,
        "parse_fail_rate": parse_fail_rate,
        "total_ticks": total_ticks,
        "alive_auc_ratio": alive_auc_ratio,
        "tail20_mean_hunger": tail20_mean_hunger,
        "tail20_mean_energy": tail20_mean_energy,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]], field_order: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        headers = field_order or ["note"]
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers)
            writer.writeheader()
        return

    headers = field_order or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _mean(values: list[float | None]) -> float | None:
    real = [float(v) for v in values if v is not None]
    if not real:
        return None
    return round(sum(real) / len(real), 4)


def _median(values: list[float | None]) -> float | None:
    real = [float(v) for v in values if v is not None]
    if not real:
        return None
    return round(statistics.median(real), 4)


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "OK":
            continue
        key = (str(row["scenario"]), str(row["arm"]))
        groups.setdefault(key, []).append(row)

    aggregates: list[dict[str, Any]] = []
    for (scenario, arm), bucket in sorted(groups.items()):
        aggregates.append(
            {
                "scenario": scenario,
                "arm": arm,
                "n_runs": len(bucket),
                "survival_rate_mean": _mean([row.get("survival_rate") for row in bucket]),
                "survival_rate_median": _median([row.get("survival_rate") for row in bucket]),
                "alive_auc_ratio_mean": _mean([row.get("alive_auc_ratio") for row in bucket]),
                "alive_auc_ratio_median": _median([row.get("alive_auc_ratio") for row in bucket]),
                "oracle_success_rate_mean": _mean([row.get("oracle_success_rate") for row in bucket]),
                "parse_fail_rate_median": _median([row.get("parse_fail_rate") for row in bucket]),
                "tail20_mean_hunger_mean": _mean([row.get("tail20_mean_hunger") for row in bucket]),
                "tail20_mean_energy_mean": _mean([row.get("tail20_mean_energy") for row in bucket]),
            }
        )
    return aggregates


def _evaluate_criteria(
    manifest: dict[str, Any],
    seed_set: str,
    raw_rows: list[dict[str, Any]],
    aggregate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    criteria = manifest.get("success_criteria", []) or []
    if not isinstance(criteria, list):
        return []

    agg_lookup = {(row["scenario"], row["arm"]): row for row in aggregate_rows}
    results: list[dict[str, Any]] = []

    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        if criterion.get("when_seed_set") and criterion["when_seed_set"] != seed_set:
            continue

        cid = str(criterion.get("id", "criterion"))
        metric = str(criterion.get("metric", ""))
        description = str(criterion.get("description", ""))

        if "compare" in criterion:
            threshold = float(criterion.get("threshold", 0.0))
            for scenario in sorted({row["scenario"] for row in aggregate_rows}):
                full_row = agg_lookup.get((scenario, "full"))
                base_row = agg_lookup.get((scenario, "no_llm"))
                if not full_row or not base_row:
                    results.append(
                        {
                            "criterion_id": cid,
                            "scenario": scenario,
                            "status": "SKIP",
                            "description": description,
                            "observed": None,
                            "threshold": threshold,
                            "reason": "missing full or no_llm aggregate",
                        }
                    )
                    continue
                observed = None
                if metric == "survival_rate":
                    fval = full_row.get("survival_rate_mean")
                    bval = base_row.get("survival_rate_mean")
                    observed = round(float(fval) - float(bval), 4) if fval is not None and bval is not None else None
                elif metric == "alive_auc_ratio":
                    fval = full_row.get("alive_auc_ratio_mean")
                    bval = base_row.get("alive_auc_ratio_mean")
                    observed = round(float(fval) - float(bval), 4) if fval is not None and bval is not None else None

                passed = observed is not None and observed >= threshold
                results.append(
                    {
                        "criterion_id": cid,
                        "scenario": scenario,
                        "status": "PASS" if passed else "FAIL",
                        "description": description,
                        "observed": observed,
                        "threshold": threshold,
                        "reason": "full_mean - no_llm_mean",
                    }
                )
            continue

        arm = str(criterion.get("arm", ""))
        op = str(criterion.get("op", ""))
        threshold = float(criterion.get("threshold", 0.0))
        relevant = [row for row in raw_rows if row.get("status") == "OK" and row.get("arm") == arm]
        values = [row.get(metric) for row in relevant]

        observed = None
        if op in {"<=", ">="}:
            observed = _median(values)

        passed = None
        if observed is not None:
            if op == "<=":
                passed = observed <= threshold
            elif op == ">=":
                passed = observed >= threshold

        results.append(
            {
                "criterion_id": cid,
                "scenario": "*",
                "status": "PASS" if passed else ("FAIL" if passed is False else "SKIP"),
                "description": description,
                "observed": observed,
                "threshold": threshold,
                "reason": f"median({metric}) {op} {threshold}" if op else "unsupported operator",
            }
        )

    return results


def _format_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_sin filas_"

    widths: dict[str, int] = {}
    for col in columns:
        widths[col] = max(
            len(col),
            max(len("" if row.get(col) is None else str(row.get(col))) for row in rows),
        )

    def fmt_cell(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    header = "| " + " | ".join(col.ljust(widths[col]) for col in columns) + " |"
    sep = "| " + " | ".join("-" * widths[col] for col in columns) + " |"
    body = [
        "| " + " | ".join(fmt_cell(row.get(col)).ljust(widths[col]) for col in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _build_markdown_report(
    manifest: dict[str, Any],
    session_id: str,
    seed_set: str,
    raw_rows: list[dict[str, Any]],
    aggregate_rows: list[dict[str, Any]],
    criteria_rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"# survival_v1 — sesión {session_id}")
    lines.append("")
    lines.append(f"- Benchmark: `{manifest.get('benchmark', {}).get('id', 'survival_v1')}`")
    lines.append(f"- Seed set: `{seed_set}`")
    lines.append(f"- Runs resueltas: `{len(raw_rows)}`")
    lines.append(f"- Runs OK: `{sum(1 for row in raw_rows if row.get('status') == 'OK')}`")
    lines.append("")

    lines.append("## Runs")
    lines.append("")
    run_cols = [
        "label",
        "scenario",
        "arm",
        "seed",
        "status",
        "run_id",
        "survival_rate",
        "alive_auc_ratio",
        "oracle_success_rate",
        "parse_fail_rate",
    ]
    lines.append(_format_table(raw_rows, run_cols))
    lines.append("")

    lines.append("## Agregado por escenario y brazo")
    lines.append("")
    agg_cols = [
        "scenario",
        "arm",
        "n_runs",
        "survival_rate_mean",
        "alive_auc_ratio_mean",
        "oracle_success_rate_mean",
        "parse_fail_rate_median",
        "tail20_mean_hunger_mean",
        "tail20_mean_energy_mean",
    ]
    lines.append(_format_table(aggregate_rows, agg_cols))
    lines.append("")

    if criteria_rows:
        lines.append("## Criterios de éxito")
        lines.append("")
        crit_cols = [
            "criterion_id",
            "scenario",
            "status",
            "observed",
            "threshold",
            "reason",
        ]
        lines.append(_format_table(criteria_rows, crit_cols))
        lines.append("")

    lines.append("## Notas")
    lines.append("")
    lines.append("- `alive_auc_ratio` = suma de `alive` en `timeseries.jsonl` / (agentes iniciales × nº de ticks observados).")
    lines.append("- `tail20_mean_hunger` y `tail20_mean_energy` son medias del último 20% de la serie temporal.")
    lines.append("- Los runs fallidos se mantienen en la tabla para preservar trazabilidad, pero se excluyen de los agregados.")
    lines.append("")
    return "\n".join(lines)


def _save_session_outputs(
    session_dir: Path,
    manifest: dict[str, Any],
    resolved_runs: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    seed_set: str,
) -> None:
    aggregate_rows = _aggregate_rows(raw_rows)
    criteria_rows = _evaluate_criteria(manifest, seed_set, raw_rows, aggregate_rows)
    markdown = _build_markdown_report(manifest, session_dir.name, seed_set, raw_rows, aggregate_rows, criteria_rows)

    _write_json(session_dir / "resolved_runs.json", resolved_runs)
    _write_jsonl(session_dir / "run_index.jsonl", raw_rows)
    _write_json(session_dir / "aggregate.json", aggregate_rows)
    _write_json(session_dir / "criteria.json", criteria_rows)
    _write_csv(
        session_dir / "summary.csv",
        raw_rows,
        field_order=[
            "label",
            "scenario",
            "arm",
            "seed",
            "status",
            "returncode",
            "run_id",
            "run_dir",
            "survival_rate",
            "alive_auc_ratio",
            "oracle_success_rate",
            "parse_fail_rate",
            "tail20_mean_hunger",
            "tail20_mean_energy",
            "summary_path",
            "timeseries_path",
            "command",
            "removed_persistence",
        ],
    )
    (session_dir / "summary.md").write_text(markdown, encoding="utf-8")


def _resolve_runs(
    manifest: dict[str, Any],
    seed_set: str,
    scenarios: list[str] | None,
    arms: list[str] | None,
    model_override: str | None,
    wandb: bool,
    wandb_project: str | None,
    wandb_entity: str | None,
    no_digest: bool,
) -> list[dict[str, Any]]:
    benchmark = manifest.get("benchmark", {}) or {}
    defaults = manifest.get("defaults", {}) or {}
    all_seed_sets = manifest.get("seed_sets", {}) or {}
    all_scenarios = manifest.get("scenarios", {}) or {}
    all_arms = manifest.get("arms", {}) or {}

    if seed_set not in all_seed_sets:
        available = ", ".join(sorted(all_seed_sets))
        raise SystemExit(f"Seed set desconocido: {seed_set}. Disponibles: {available}")

    selected_scenarios = scenarios or sorted(all_scenarios)
    selected_arms = arms or sorted(all_arms)

    unknown_scenarios = [s for s in selected_scenarios if s not in all_scenarios]
    unknown_arms = [a for a in selected_arms if a not in all_arms]
    if unknown_scenarios:
        raise SystemExit(f"Escenarios desconocidos: {', '.join(unknown_scenarios)}")
    if unknown_arms:
        raise SystemExit(f"Brazos desconocidos: {', '.join(unknown_arms)}")

    run_name_pattern = defaults.get("run_name_pattern", "{benchmark}__{scenario}__{arm}__s{seed}")
    resolved: list[dict[str, Any]] = []

    for scenario_id in selected_scenarios:
        scenario = all_scenarios[scenario_id] or {}
        for arm_id in selected_arms:
            arm = all_arms[arm_id] or {}
            for seed in all_seed_sets[seed_set]:
                label = run_name_pattern.format(
                    benchmark=benchmark.get("id", "survival_v1"),
                    scenario=scenario_id,
                    arm=arm_id,
                    seed=seed,
                )
                command = [
                    "uv",
                    "run",
                    "main.py",
                    "--agents",
                    str(defaults.get("agents", 3)),
                    "--ticks",
                    str(scenario["ticks"]),
                    "--seed",
                    str(seed),
                    "--width",
                    str(scenario["width"]),
                    "--height",
                    str(scenario["height"]),
                    "--start-hour",
                    str(scenario["start_hour"]),
                ]

                no_llm = bool(arm.get("no_llm", False))
                if no_llm:
                    command.append("--no-llm")

                effective_model = model_override if model_override is not None else defaults.get("model")
                if effective_model and not no_llm:
                    command += ["--model", str(effective_model)]

                if wandb:
                    command += ["--wandb", "--wandb-run-name", label]
                    if wandb_project:
                        command += ["--wandb-project", str(wandb_project)]
                    if wandb_entity:
                        command += ["--wandb-entity", str(wandb_entity)]

                if no_digest:
                    command.append("--no-digest")

                resolved.append(
                    {
                        "benchmark": benchmark.get("id", "survival_v1"),
                        "scenario": scenario_id,
                        "arm": arm_id,
                        "seed": int(seed),
                        "label": label,
                        "ticks": int(scenario["ticks"]),
                        "width": int(scenario["width"]),
                        "height": int(scenario["height"]),
                        "start_hour": int(scenario["start_hour"]),
                        "no_llm": no_llm,
                        "command": command,
                    }
                )
    return resolved


def _write_commands_sh(path: Path, resolved_runs: list[dict[str, Any]]) -> None:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for run in resolved_runs:
        cmd = " ".join(shlex.quote(part) for part in run["command"])
        lines.append(f"# {run['label']}")
        lines.append(cmd)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        path.chmod(0o755)
    except OSError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runner dedicated to survival_v1 for Emerge")
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).with_name("survival_v1_manifest.yaml")),
        help="Ruta al manifest YAML (default: junto al script).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Ruta al root del repo de Emerge (default: directorio actual).",
    )
    parser.add_argument(
        "--seed-set",
        default="smoke",
        help="Seed set a ejecutar: smoke, dev o eval (default: smoke).",
    )
    parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=None,
        help="Limita a un escenario concreto. Repetible.",
    )
    parser.add_argument(
        "--arm",
        dest="arms",
        action="append",
        default=None,
        help="Limita a un brazo concreto. Repetible.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override del modelo a pasar a main.py. Si se omite, usa el default del repo.",
    )
    parser.add_argument("--wandb", action="store_true", help="Activa W&B en los runs.")
    parser.add_argument("--wandb-project", default=None, help="Proyecto W&B opcional.")
    parser.add_argument("--wandb-entity", default=None, help="Entidad W&B opcional.")
    parser.add_argument("--no-digest", action="store_true", help="Pasa --no-digest a main.py.")
    parser.add_argument(
        "--keep-persistence",
        action="store_true",
        help="No borra data/precedents_<seed>.json ni data/lineage_<seed>.json antes de cada run.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resuelve y escribe artefactos, pero no ejecuta.")
    parser.add_argument("--fail-fast", action="store_true", help="Detiene la sesión en el primer fallo.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    _ensure_repo_root(repo_root)

    manifest_path = Path(args.manifest).resolve()
    manifest = _load_yaml(manifest_path)
    defaults = manifest.get("defaults", {}) or {}
    output_root = repo_root / str(defaults.get("output_root", "data/benchmarks/survival_v1"))
    session_dir = output_root / f"session_{_now_utc()}"
    session_dir.mkdir(parents=True, exist_ok=True)

    resolved_runs = _resolve_runs(
        manifest=manifest,
        seed_set=args.seed_set,
        scenarios=args.scenarios,
        arms=args.arms,
        model_override=args.model,
        wandb=args.wandb,
        wandb_project=args.wandb_project,
        wandb_entity=args.wandb_entity,
        no_digest=args.no_digest,
    )

    _write_json(session_dir / "manifest_snapshot.json", manifest)
    _write_commands_sh(session_dir / "commands.sh", resolved_runs)

    dry_rows: list[dict[str, Any]] = []
    for run in resolved_runs:
        dry_rows.append(
            {
                "label": run["label"],
                "scenario": run["scenario"],
                "arm": run["arm"],
                "seed": run["seed"],
                "status": "DRY-RUN",
                "returncode": 0,
                "run_id": None,
                "run_dir": None,
                "survival_rate": None,
                "alive_auc_ratio": None,
                "oracle_success_rate": None,
                "parse_fail_rate": None,
                "tail20_mean_hunger": None,
                "tail20_mean_energy": None,
                "summary_path": None,
                "timeseries_path": None,
                "command": " ".join(shlex.quote(part) for part in run["command"]),
                "removed_persistence": "",
            }
        )

    if args.dry_run:
        _save_session_outputs(session_dir, manifest, resolved_runs, dry_rows, args.seed_set)
        print(f"[dry-run] sesión escrita en: {session_dir}")
        print(f"[dry-run] commands.sh: {session_dir / 'commands.sh'}")
        print(f"[dry-run] summary.md:  {session_dir / 'summary.md'}")
        return 0

    runs_root = repo_root / "data" / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    final_rows: list[dict[str, Any]] = []
    failures = 0

    for index, run in enumerate(resolved_runs, start=1):
        label = run["label"]
        cmd = run["command"]
        print(f"[{index}/{len(resolved_runs)}] {label}")
        print("  $ " + " ".join(shlex.quote(part) for part in cmd))

        removed = []
        if not args.keep_persistence:
            removed = _clean_persistence(repo_root, int(run["seed"]))
            if removed:
                print(f"  limpiado: {', '.join(removed)}")

        before = _snapshot_run_dirs(runs_root)
        result = subprocess.run(cmd, cwd=repo_root)
        time.sleep(0.2)
        after = _snapshot_run_dirs(runs_root)
        run_dir = _detect_new_run_dir(before, after, runs_root)

        row: dict[str, Any] = {
            "label": label,
            "scenario": run["scenario"],
            "arm": run["arm"],
            "seed": run["seed"],
            "status": "OK" if result.returncode == 0 else "FAILED",
            "returncode": int(result.returncode),
            "command": " ".join(shlex.quote(part) for part in cmd),
            "removed_persistence": ", ".join(removed),
        }

        if run_dir is not None and run_dir.exists():
            metrics = _read_metrics(run_dir)
            row.update(metrics)
        else:
            row.update(
                {
                    "run_id": None,
                    "run_dir": None,
                    "summary_path": None,
                    "timeseries_path": None,
                    "survival_rate": None,
                    "alive_auc_ratio": None,
                    "oracle_success_rate": None,
                    "parse_fail_rate": None,
                    "tail20_mean_hunger": None,
                    "tail20_mean_energy": None,
                }
            )

        final_rows.append(row)
        _save_session_outputs(session_dir, manifest, resolved_runs, final_rows, args.seed_set)

        if result.returncode != 0:
            failures += 1
            print(f"  fallo con exit code {result.returncode}")
            if args.fail_fast:
                break

        print()

    print(f"Sesión escrita en: {session_dir}")
    print(f"Resumen markdown: {session_dir / 'summary.md'}")
    print(f"Índice JSONL:      {session_dir / 'run_index.jsonl'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
