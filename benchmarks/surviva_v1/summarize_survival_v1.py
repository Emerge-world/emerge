#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
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


def _format_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_sin filas_"

    widths: dict[str, int] = {}
    for col in columns:
        widths[col] = max(
            len(col),
            max(len("" if row.get(col) is None else str(row.get(col))) for row in rows),
        )

    def fmt(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    header = "| " + " | ".join(col.ljust(widths[col]) for col in columns) + " |"
    sep = "| " + " | ".join("-" * widths[col] for col in columns) + " |"
    body = [
        "| " + " | ".join(fmt(row.get(col)).ljust(widths[col]) for col in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _read_metrics(run_dir: Path) -> dict[str, Any]:
    meta = _load_json(run_dir / "meta.json", default={}) or {}
    summary = _load_json(run_dir / "metrics" / "summary.json", default={}) or {}
    timeseries = _load_jsonl(run_dir / "metrics" / "timeseries.jsonl")

    initial_count = (summary.get("agents") or {}).get("initial_count", 0) or 0
    final_survivors = (summary.get("agents") or {}).get("final_survivors", []) or []

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
        "survival_rate": (summary.get("agents") or {}).get("survival_rate"),
        "oracle_success_rate": (summary.get("actions") or {}).get("oracle_success_rate"),
        "parse_fail_rate": (summary.get("actions") or {}).get("parse_fail_rate"),
        "alive_auc_ratio": alive_auc_ratio,
        "tail20_mean_hunger": tail20_mean_hunger,
        "tail20_mean_energy": tail20_mean_energy,
        "initial_count": initial_count,
        "final_survivors_count": len(final_survivors),
        "deaths": (summary.get("agents") or {}).get("deaths"),
        "total_ticks": summary.get("total_ticks"),
        "summary_path": str(run_dir / "metrics" / "summary.json"),
        "timeseries_path": str(run_dir / "metrics" / "timeseries.jsonl"),
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "OK":
            continue
        groups.setdefault((str(row["scenario"]), str(row["arm"])), []).append(row)

    aggregate: list[dict[str, Any]] = []
    for (scenario, arm), bucket in sorted(groups.items()):
        aggregate.append(
            {
                "scenario": scenario,
                "arm": arm,
                "n_runs": len(bucket),
                "survival_rate_mean": _mean([row.get("survival_rate") for row in bucket]),
                "alive_auc_ratio_mean": _mean([row.get("alive_auc_ratio") for row in bucket]),
                "oracle_success_rate_mean": _mean([row.get("oracle_success_rate") for row in bucket]),
                "parse_fail_rate_median": _median([row.get("parse_fail_rate") for row in bucket]),
                "tail20_mean_hunger_mean": _mean([row.get("tail20_mean_hunger") for row in bucket]),
                "tail20_mean_energy_mean": _mean([row.get("tail20_mean_energy") for row in bucket]),
            }
        )
    return aggregate


def _evaluate_criteria(
    manifest: dict[str, Any],
    seed_set: str | None,
    raw_rows: list[dict[str, Any]],
    aggregate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    criteria = manifest.get("success_criteria", []) or []
    agg_lookup = {(row["scenario"], row["arm"]): row for row in aggregate_rows}
    out: list[dict[str, Any]] = []

    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        when_seed_set = criterion.get("when_seed_set")
        if seed_set and when_seed_set and when_seed_set != seed_set:
            continue

        cid = str(criterion.get("id", "criterion"))
        metric = str(criterion.get("metric", ""))
        description = str(criterion.get("description", ""))
        threshold = float(criterion.get("threshold", 0.0))

        if "compare" in criterion:
            for scenario in sorted({row["scenario"] for row in aggregate_rows}):
                full_row = agg_lookup.get((scenario, "full"))
                base_row = agg_lookup.get((scenario, "no_llm"))
                if not full_row or not base_row:
                    out.append(
                        {
                            "criterion_id": cid,
                            "scenario": scenario,
                            "status": "SKIP",
                            "description": description,
                            "observed": None,
                            "threshold": threshold,
                            "reason": "missing full/no_llm",
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
                out.append(
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
        relevant = [row for row in raw_rows if row.get("status") == "OK" and row.get("arm") == arm]
        values = [row.get(metric) for row in relevant]
        observed = _median(values) if values else None
        passed = None
        if observed is not None:
            if op == "<=":
                passed = observed <= threshold
            elif op == ">=":
                passed = observed >= threshold
        out.append(
            {
                "criterion_id": cid,
                "scenario": "*",
                "status": "PASS" if passed else ("FAIL" if passed is False else "SKIP"),
                "description": description,
                "observed": observed,
                "threshold": threshold,
                "reason": f"median({metric}) {op} {threshold}",
            }
        )
    return out


def _build_markdown(manifest: dict[str, Any], session_name: str, raw_rows: list[dict[str, Any]], aggregate_rows: list[dict[str, Any]], criteria_rows: list[dict[str, Any]], seed_set: str | None) -> str:
    lines: list[str] = []
    lines.append(f"# survival_v1 — resumen reconstruido: {session_name}")
    lines.append("")
    if seed_set:
        lines.append(f"- Seed set inferido: `{seed_set}`")
    lines.append(f"- Runs en índice: `{len(raw_rows)}`")
    lines.append(f"- Runs OK: `{sum(1 for row in raw_rows if row.get('status') == 'OK')}`")
    lines.append("")

    lines.append("## Runs")
    lines.append("")
    lines.append(
        _format_table(
            raw_rows,
            [
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
            ],
        )
    )
    lines.append("")
    lines.append("## Agregado por escenario y brazo")
    lines.append("")
    lines.append(
        _format_table(
            aggregate_rows,
            [
                "scenario",
                "arm",
                "n_runs",
                "survival_rate_mean",
                "alive_auc_ratio_mean",
                "oracle_success_rate_mean",
                "parse_fail_rate_median",
                "tail20_mean_hunger_mean",
                "tail20_mean_energy_mean",
            ],
        )
    )
    lines.append("")
    if criteria_rows:
        lines.append("## Criterios de éxito")
        lines.append("")
        lines.append(
            _format_table(
                criteria_rows,
                ["criterion_id", "scenario", "status", "observed", "threshold", "reason"],
            )
        )
        lines.append("")
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild summary files for a survival_v1 session")
    parser.add_argument("session_dir", help="Ruta a data/benchmarks/survival_v1/session_<timestamp>")
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).with_name("survival_v1_manifest.yaml")),
        help="Ruta al manifest YAML (default: junto al script).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dir = Path(args.session_dir).resolve()
    if not session_dir.exists():
        raise SystemExit(f"Session dir no encontrado: {session_dir}")

    manifest = _load_yaml(Path(args.manifest).resolve())
    rows = _load_jsonl(session_dir / "run_index.jsonl")
    if not rows:
        raise SystemExit(f"No hay run_index.jsonl o está vacío en: {session_dir}")

    rebuilt_rows: list[dict[str, Any]] = []
    for row in rows:
        rebuilt = dict(row)
        run_dir = row.get("run_dir")
        if run_dir and Path(run_dir).exists() and row.get("status") == "OK":
            rebuilt.update(_read_metrics(Path(run_dir)))
        rebuilt_rows.append(rebuilt)

    aggregate_rows = _aggregate_rows(rebuilt_rows)
    seed_set = None
    if rows:
        # best-effort: if every seed belongs to the same configured seed set, expose it
        configured = manifest.get("seed_sets", {}) or {}
        executed_seeds = {int(row["seed"]) for row in rebuilt_rows if row.get("seed") is not None}
        for name, values in configured.items():
            if executed_seeds and executed_seeds.issubset(set(int(v) for v in values)):
                seed_set = name
                break

    criteria_rows = _evaluate_criteria(manifest, seed_set, rebuilt_rows, aggregate_rows)
    markdown = _build_markdown(manifest, session_dir.name, rebuilt_rows, aggregate_rows, criteria_rows, seed_set)

    (session_dir / "summary.md").write_text(markdown, encoding="utf-8")
    _write_csv(session_dir / "summary.csv", rebuilt_rows)
    (session_dir / "aggregate.json").write_text(json.dumps(aggregate_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (session_dir / "criteria.json").write_text(json.dumps(criteria_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Resumen reconstruido en: {session_dir / 'summary.md'}")
    print(f"CSV reconstruido en:     {session_dir / 'summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
