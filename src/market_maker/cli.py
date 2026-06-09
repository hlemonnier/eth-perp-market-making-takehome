from __future__ import annotations

import argparse
import gc
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

from market_maker.config import BacktestConfig, load_config
from market_maker.data_audit import run_audit, run_audit_by_day, write_audit_outputs
from market_maker.data_loader import load_market_data, load_market_data_sample
from market_maker.reporting import round_trip_diagnostics, round_trip_summary, write_outputs
from market_maker.simulator import Simulator

DEFAULT_CORE_SAMPLE_ROWS = 5_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETH perpetual market-making audit and backtest.")
    parser.add_argument("command", choices=["audit", "backtest", "run", "robustness", "ablations", "event-ordering", "reproduce"], help="Command to execute.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to YAML config.")
    parser.add_argument("--data-dir", default=None, help="Override data directory.")
    parser.add_argument("--output-dir", default="reports/baseline", help="Output directory.")
    parser.add_argument("--fill-model", choices=["simple", "conservative_queue", "partial_queue", "calibrated_queue"], default=None, help="Override fill model.")
    parser.add_argument("--maker-fee-bps", type=float, default=None, help="Override maker fee in basis points.")
    parser.add_argument("--cancel-latency-ms", type=int, default=None, help="Override cancel latency.")
    parser.add_argument("--queue-depletion-fraction", type=float, default=None, help="Override queue depletion fraction for partial/calibrated queue models.")
    parser.add_argument("--funding-target-frac", type=float, default=None, help="Override funding inventory target strength.")
    parser.add_argument("--pressure-stop", type=float, default=None, help="Override adverse-pressure side stop threshold.")
    parser.add_argument("--min-half-spread-ticks", type=int, default=None, help="Override minimum quote half-spread in ticks.")
    parser.add_argument("--suite-size", choices=["smoke", "core", "full_core", "full", "standard"], default="core", help="Robustness/reproduce suite breadth.")
    parser.add_argument("--smoke-rows", type=int, default=1_000, help="Orderbook rows to load for smoke reproducibility suites.")
    parser.add_argument("--sample-rows", type=int, default=DEFAULT_CORE_SAMPLE_ROWS, help="Orderbook rows to load for sample/core reproducibility suites.")
    parser.add_argument("--allow-audit-errors", action="store_true", help="Run the backtest even when audit checks fail.")
    return parser.parse_args()


def override_config(config: BacktestConfig, args: argparse.Namespace) -> BacktestConfig:
    data = config.data
    execution = config.execution
    strategy = config.strategy
    if args.data_dir is not None:
        data = replace(data, data_dir=Path(args.data_dir))
    if getattr(args, "fill_model", None) is not None:
        execution = replace(execution, fill_model=args.fill_model)
    if getattr(args, "maker_fee_bps", None) is not None:
        execution = replace(execution, maker_fee_bps=args.maker_fee_bps)
    if getattr(args, "cancel_latency_ms", None) is not None:
        execution = replace(execution, cancel_latency_ms=args.cancel_latency_ms)
    if getattr(args, "queue_depletion_fraction", None) is not None:
        execution = replace(execution, queue_depletion_fraction=args.queue_depletion_fraction)
    if getattr(args, "funding_target_frac", None) is not None:
        strategy = replace(strategy, funding_target_frac=args.funding_target_frac)
    if getattr(args, "pressure_stop", None) is not None:
        strategy = replace(strategy, pressure_stop=args.pressure_stop)
    if getattr(args, "min_half_spread_ticks", None) is not None:
        strategy = replace(strategy, min_half_spread_ticks=args.min_half_spread_ticks)
    return replace(config, data=data, execution=execution, strategy=strategy)


def run_command(args: argparse.Namespace) -> None:
    config = override_config(load_config(args.config), args)
    suite_size = _normalize_suite_size(getattr(args, "suite_size", "core"))
    output_dir = Path(args.output_dir)
    if args.command == "audit":
        audit = run_audit_by_day(config.data.data_dir, config.data.days, config.audit)
        write_audit_outputs(audit, output_dir)
        print(f"Audit complete: passed={audit.passed}, tick_size={audit.tick_size}, output_dir={output_dir}")
        return
    if args.command == "ablations" and suite_size == "full_core":
        audit = run_audit_by_day(config.data.data_dir, config.data.days, config.audit)
        write_audit_outputs(audit, output_dir)
        results = run_ablation_suite_by_day(config, audit, output_dir, dataset_scope="full_dataset_by_day", suite_size=suite_size)
        results.to_csv(output_dir.with_suffix(".csv"), index=False)
        print(results.to_string(index=False))
        print(f"Ablation suite complete: output_dir={output_dir}")
        return
    if args.command in {"robustness", "ablations", "event-ordering", "reproduce"} and suite_size == "smoke":
        market_data = load_market_data_sample(config.data.data_dir, config.data.days, max_orderbook_rows=getattr(args, "smoke_rows", 1_000))
        dataset_scope = f"smoke_{getattr(args, 'smoke_rows', 1_000)}_rows"
    elif args.command in {"robustness", "ablations", "event-ordering", "reproduce"} and suite_size == "core":
        market_data = load_market_data_sample(config.data.data_dir, config.data.days, max_orderbook_rows=getattr(args, "sample_rows", DEFAULT_CORE_SAMPLE_ROWS))
        dataset_scope = f"sample_{getattr(args, 'sample_rows', DEFAULT_CORE_SAMPLE_ROWS)}_rows"
    else:
        market_data = load_market_data(config.data.data_dir, config.data.days)
        dataset_scope = "full_dataset"
    if dataset_scope == "full_dataset":
        audit = run_audit_by_day(config.data.data_dir, config.data.days, config.audit)
    else:
        audit = run_audit(market_data, config.audit)
    write_audit_outputs(audit, output_dir)

    if not audit.passed and not getattr(args, "allow_audit_errors", False):
        raise SystemExit(f"Audit failed; refusing to run backtest. Review {output_dir / 'audit_summary.csv'} or pass --allow-audit-errors.")

    if args.command == "robustness":
        results = run_robustness_suite(config, market_data, audit, output_dir, suite_size=suite_size, dataset_scope=dataset_scope)
        print(results.to_string(index=False))
        print(f"Robustness suite complete: output_dir={output_dir}")
        return

    if args.command == "ablations":
        results = run_ablation_suite(config, market_data, audit, output_dir, dataset_scope=dataset_scope, suite_size=suite_size)
        if suite_size == "full_core":
            results.to_csv(output_dir.with_suffix(".csv"), index=False)
        print(results.to_string(index=False))
        print(f"Ablation suite complete: output_dir={output_dir}")
        return

    if args.command == "event-ordering":
        results = run_event_ordering_sensitivity(config, market_data, audit, output_dir, dataset_scope=dataset_scope)
        print(results.to_string(index=False))
        print(f"Event-ordering sensitivity complete: output_dir={output_dir}")
        return

    if args.command == "reproduce":
        run_reproduce_suite(config, market_data, audit, output_dir, suite_size=suite_size, dataset_scope=dataset_scope)
        print(f"Reproduce suite complete: output_dir={output_dir}")
        return

    simulator = Simulator(market_data, config, audit.tick_size)
    result = simulator.run()
    write_outputs(result, audit, config, output_dir)
    if not result.metrics.overall.empty:
        print(result.metrics.overall.to_string(index=False))
    print(f"Backtest complete: output_dir={output_dir}")


def run_single_backtest(config: BacktestConfig, market_data, audit, output_dir: Path) -> dict[str, object]:
    simulator = Simulator(market_data, config, audit.tick_size)
    result = simulator.run()
    write_outputs(result, audit, config, output_dir)
    row: dict[str, object] = {}
    if not result.metrics.overall.empty:
        row.update(result.metrics.overall.iloc[0].to_dict())
    row.update(_comparison_diagnostics(result))
    row.update(
        {
            "fill_model": config.execution.fill_model,
            "maker_fee_bps": config.execution.maker_fee_bps,
            "cancel_latency_ms": config.execution.cancel_latency_ms if config.execution.cancel_latency_ms is not None else config.execution.latency_ms,
            "queue_depletion_fraction": config.execution.queue_depletion_fraction,
            "pressure_stop": config.strategy.pressure_stop,
            "min_half_spread_ticks": config.strategy.min_half_spread_ticks,
            "funding_target_frac": config.strategy.funding_target_frac,
            "output_dir": str(output_dir),
        }
    )
    return row


def _comparison_diagnostics(result) -> dict[str, object]:
    if result.metrics.overall.empty:
        return {}
    overall = result.metrics.overall.iloc[0]
    realized = float(overall.get("realized_trading_pnl", 0.0))
    unrealized = float(overall.get("unrealized_trading_pnl", 0.0))
    total = float(overall.get("total_pnl", 0.0))
    fills = int(float(overall.get("total_fills", 0.0)))
    inventory = result.metrics.inventory_stats.iloc[0] if not result.metrics.inventory_stats.empty else {}
    pct_long = float(inventory.get("pct_long", 0.0)) if hasattr(inventory, "get") else 0.0
    pct_short = float(inventory.get("pct_short", 0.0)) if hasattr(inventory, "get") else 0.0
    spread_by_horizon = _realized_spread_by_horizon(result.metrics.realized_spread)
    realized_spreads = [value for value in spread_by_horizon.values() if pd.notna(value)]
    sparse_fill_warning = fills <= 10
    inventory_directional_warning = (
        abs(unrealized) > max(abs(realized) * 3.0, 1.0)
        or pct_long > 75.0
        or pct_short > 75.0
    )
    negative_realized_spread_warning = any(float(value) < 0.0 for value in realized_spreads)
    order_stats = result.metrics.order_stats.iloc[0] if not result.metrics.order_stats.empty else {}
    round_trip_stats = round_trip_summary(round_trip_diagnostics(result.fills)).iloc[0].to_dict()
    warnings = []
    if sparse_fill_warning:
        warnings.append("sparse_fills")
    if inventory_directional_warning:
        warnings.append("inventory_directional_pnl")
    if negative_realized_spread_warning:
        warnings.append("negative_realized_spread")
    return {
        "avg_realized_spread_1s": spread_by_horizon.get(1.0),
        "avg_realized_spread_5s": spread_by_horizon.get(5.0),
        "avg_realized_spread_30s": spread_by_horizon.get(30.0),
        "pct_long": pct_long,
        "pct_short": pct_short,
        "inventory_pnl_share_abs": abs(unrealized) / max(abs(total), 1e-12),
        "sparse_fill_warning": sparse_fill_warning,
        "inventory_directional_warning": inventory_directional_warning,
        "negative_realized_spread_warning": negative_realized_spread_warning,
        "comparison_warnings": ";".join(warnings) if warnings else "none",
        "placed_orders": int(float(order_stats.get("placed_orders", 0.0))) if hasattr(order_stats, "get") else 0,
        "placed_orders_per_hour": float(order_stats.get("placed_orders_per_hour", 0.0)) if hasattr(order_stats, "get") else 0.0,
        "top_roundtrip_pnl_share_pct": float(round_trip_stats.get("top_roundtrip_pnl_share_pct", 0.0)),
        "top_abs_roundtrip_pnl_share_pct": float(round_trip_stats.get("top_abs_roundtrip_pnl_share_pct", 0.0)),
        "max_holding_seconds": float(round_trip_stats.get("max_holding_seconds", 0.0)),
    }


def _realized_spread_by_horizon(realized_spread: pd.DataFrame) -> dict[float, float]:
    if realized_spread.empty or not {"horizon_seconds", "average_realized_spread"}.issubset(realized_spread.columns):
        return {}
    table = realized_spread[["horizon_seconds", "average_realized_spread"]].copy()
    table["horizon_seconds"] = pd.to_numeric(table["horizon_seconds"], errors="coerce")
    table["average_realized_spread"] = pd.to_numeric(table["average_realized_spread"], errors="coerce")
    return {
        float(row["horizon_seconds"]): float(row["average_realized_spread"])
        for _, row in table.dropna().iterrows()
    }


def run_robustness_suite(
    config: BacktestConfig,
    market_data,
    audit,
    output_dir: Path,
    suite_size: str = "core",
    dataset_scope: str = "unknown",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    if suite_size == "smoke":
        variants = [
            ("baseline", config),
            ("simple_fill", replace(config, execution=replace(config.execution, fill_model="simple"))),
            ("partial_queue_0.50", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.50))),
            ("pressure_filter_off", replace(config, strategy=replace(config.strategy, pressure_stop=999.0, k_adv=0.0))),
        ]
    elif suite_size == "core":
        variants = _core_robustness_variants(config)
    elif suite_size == "full_core":
        variants = _full_core_robustness_variants(config)
    else:
        variants = []
        pressure_values = [0.25, 0.50, 0.75]
        queue_values = [0.0, 0.25, 0.5, 0.75]
        cancel_values = [0, 100, 250, 500]
        fee_values = [-0.5, 0.0, 0.5, 1.0]
        spread_values = [1, 2, 3]
        for run_index, (pressure_stop, queue_depletion, cancel_latency, fee, min_ticks) in enumerate(
            product(pressure_values, queue_values, cancel_values, fee_values, spread_values)
        ):
            cfg = replace(
                config,
                execution=replace(
                    config.execution,
                    fill_model="partial_queue",
                    queue_depletion_fraction=float(queue_depletion),
                    cancel_latency_ms=int(cancel_latency),
                    maker_fee_bps=float(fee),
                ),
                strategy=replace(
                    config.strategy,
                    pressure_stop=float(pressure_stop),
                    min_half_spread_ticks=int(min_ticks),
                ),
            )
            variants.append((f"full_grid_{run_index:03d}", cfg))

    rows = []
    for run_index, (variant, cfg) in enumerate(variants):
        print(f"[robustness] {run_index + 1}/{len(variants)} {variant}", flush=True)
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row: dict[str, object] = {}
        if not result.metrics.overall.empty:
            row.update(result.metrics.overall.iloc[0].to_dict())
        row.update(
            {
                "run": run_index,
                "variant": variant,
                "dataset_scope": dataset_scope,
                "fill_model": cfg.execution.fill_model,
                "pressure_stop": cfg.strategy.pressure_stop,
                "queue_depletion_fraction": cfg.execution.queue_depletion_fraction,
                "cancel_latency_ms": cfg.execution.cancel_latency_ms if cfg.execution.cancel_latency_ms is not None else cfg.execution.latency_ms,
                "maker_fee_bps": cfg.execution.maker_fee_bps,
                "min_half_spread_ticks": cfg.strategy.min_half_spread_ticks,
            }
        )
        rows.append(row)
        output_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_dir / "grid_results.csv", index=False)
        del result
        gc.collect()
    results = pd.DataFrame(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "grid_results.csv", index=False)
    if not results.empty:
        pivot = results.pivot_table(
            index="queue_depletion_fraction",
            columns="cancel_latency_ms",
            values="total_pnl",
            aggfunc="mean",
        )
        pivot.to_csv(output_dir / "pnl_by_queue_depletion_cancel_latency.csv")
    return results


def run_ablation_suite(
    config: BacktestConfig,
    market_data,
    audit,
    output_dir: Path,
    dataset_scope: str = "unknown",
    suite_size: str = "core",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = _ablation_variants(config, suite_size)
    rows = []
    for run_index, (name, cfg) in enumerate(variants):
        print(f"[ablations] {run_index + 1}/{len(variants)} {name}", flush=True)
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
        row["variant"] = name
        row["dataset_scope"] = dataset_scope
        rows.append(row)
    results = pd.DataFrame(rows)
    results.to_csv(output_dir / "ablation_results.csv", index=False)
    return results


def run_ablation_suite_by_day(
    config: BacktestConfig,
    audit,
    output_dir: Path,
    dataset_scope: str = "full_dataset_by_day",
    suite_size: str = "full_core",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = _ablation_variants(config, suite_size)
    day_rows: list[dict[str, object]] = []
    for variant_index, (name, cfg) in enumerate(variants):
        for day_index, day in enumerate(config.data.days):
            print(f"[ablations] {variant_index + 1}/{len(variants)} {name} day {day_index + 1}/{len(config.data.days)} {day}", flush=True)
            day_data = load_market_data(config.data.data_dir, [day])
            result = Simulator(day_data, cfg, audit.tick_size).run()
            row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
            row["variant"] = name
            row["day"] = str(day)
            row["dataset_scope"] = dataset_scope
            day_rows.append(row)
            pd.DataFrame(day_rows).to_csv(output_dir / "ablation_day_results.csv", index=False)
            del result, day_data
            gc.collect()
    day_results = pd.DataFrame(day_rows)
    results = _aggregate_ablation_day_results(day_results)
    results.to_csv(output_dir / "ablation_results.csv", index=False)
    return results


def _aggregate_ablation_day_results(day_results: pd.DataFrame) -> pd.DataFrame:
    if day_results.empty:
        return day_results
    additive = [
        "total_pnl",
        "realized_trading_pnl",
        "unrealized_trading_pnl",
        "realized_roundtrip_pnl",
        "inventory_mtm_pnl",
        "funding_pnl",
        "fees",
        "liquidation_adjusted_pnl",
        "forced_flat_pnl",
        "liquidation_cost",
        "final_liquidation_cost",
        "forced_flat_cost",
        "total_fills",
        "fill_volume_eth",
        "turnover_usd",
    ]
    max_cols = ["max_inventory", "max_drawdown", "sampled_1m_max_drawdown"]
    min_cols = ["min_inventory"]
    rows = []
    for variant, group in day_results.groupby("variant", sort=False):
        row: dict[str, object] = {
            "variant": variant,
            "dataset_scope": "full_dataset_by_day",
            "aggregation": "sum_of_independent_daily_runs",
            "days": ",".join(str(day) for day in group["day"].tolist()),
        }
        for column in additive:
            if column in group.columns:
                row[column] = float(pd.to_numeric(group[column], errors="coerce").fillna(0.0).sum())
        for column in max_cols:
            if column in group.columns:
                values = pd.to_numeric(group[column], errors="coerce").dropna()
                row[column] = float(values.max()) if not values.empty else 0.0
        for column in min_cols:
            if column in group.columns:
                values = pd.to_numeric(group[column], errors="coerce").dropna()
                row[column] = float(values.min()) if not values.empty else 0.0
        row["pnl_per_turnover"] = row["total_pnl"] / row["turnover_usd"] if row.get("turnover_usd") else 0.0
        row["pnl_per_eth"] = row["total_pnl"] / row["fill_volume_eth"] if row.get("fill_volume_eth") else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def run_reproduce_suite(config: BacktestConfig, market_data, audit, output_dir: Path, suite_size: str = "core", dataset_scope: str = "unknown") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dataset_scope(market_data, output_dir, suite_size, dataset_scope)
    write_audit_outputs(audit, output_dir / "audit")
    baseline = run_single_backtest(config, market_data, audit, output_dir / "baseline")
    simple_cfg = replace(config, execution=replace(config.execution, fill_model="simple"))
    simple = run_single_backtest(simple_cfg, market_data, audit, output_dir / "simple_fill")
    no_funding_cfg = replace(config, strategy=replace(config.strategy, funding_target_frac=0.0))
    no_funding = run_single_backtest(no_funding_cfg, market_data, audit, output_dir / "funding_disabled")
    comparison = pd.DataFrame(
        [
            {"variant": "baseline", **baseline},
            {"variant": "simple_fill", **simple},
            {"variant": "funding_disabled", **no_funding},
        ]
    )
    comparison.insert(0, "dataset_scope", dataset_scope)
    comparison.to_csv(output_dir / "fill_model_comparison.csv", index=False)
    event_ordering = run_event_ordering_sensitivity(config, market_data, audit, output_dir, dataset_scope=dataset_scope)
    if suite_size == "smoke":
        robustness = run_robustness_suite(config, market_data, audit, output_dir / "robustness_smoke", suite_size=suite_size, dataset_scope=dataset_scope)
        write_reproduce_summary(output_dir, suite_size, dataset_scope, comparison, event_ordering, robustness=robustness)
        return
    run_sensitivity_suites(config, market_data, audit, output_dir, dataset_scope=dataset_scope)
    ablations = run_ablation_suite(config, market_data, audit, output_dir / "ablations", dataset_scope=dataset_scope, suite_size=suite_size)
    ablations.to_csv(output_dir / "ablations_core.csv", index=False)
    robustness = run_robustness_suite(config, market_data, audit, output_dir / "robustness", suite_size=suite_size, dataset_scope=dataset_scope)
    write_reproduce_summary(output_dir, suite_size, dataset_scope, comparison, event_ordering, ablations=ablations, robustness=robustness)


def write_reproduce_summary(
    output_dir: Path,
    suite_size: str,
    dataset_scope: str,
    comparison: pd.DataFrame,
    event_ordering: pd.DataFrame,
    ablations: pd.DataFrame | None = None,
    robustness: pd.DataFrame | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ETH Perpetual Market-Making Reproduce Summary",
        "",
        "This is an aggregate workflow report. Variant-specific backtest reports live under `baseline/`, `simple_fill/`, and `funding_disabled/`.",
        "",
        "## Scope",
        "",
        f"- Suite size: `{suite_size}`.",
        f"- Dataset scope: `{dataset_scope}`.",
        "",
        "## Fill Model Comparison",
        "",
        _markdown_table(comparison),
        "",
        "## Event Ordering Sensitivity",
        "",
        _markdown_table(event_ordering),
    ]
    if ablations is not None:
        lines += [
            "",
            "## Ablations",
            "",
            _markdown_table(ablations),
        ]
    if robustness is not None:
        lines += [
            "",
            "## Robustness",
            "",
            _markdown_table(robustness),
        ]
    lines += [
        "",
        "## Interpretation",
        "",
        "Treat positive PnL as a diagnostic result, not a proven live edge. Sparse fills, negative short-horizon realized spread, high inventory-directional exposure, and partial-queue/fee failures are surfaced in the CSV warning columns when present.",
        "",
    ]
    (output_dir / "final_report.md").write_text("\n".join(lines))


def _markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    shown = df.head(max_rows).copy()
    headers = list(shown.columns)
    rows = [[_format_cell(row[col]) for col in headers] for _, row in shown.iterrows()]
    table = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    table.extend("| " + " | ".join(row) + " |" for row in rows)
    if len(df) > max_rows:
        table.append(f"\n_Only first {max_rows} of {len(df)} rows shown._")
    return "\n".join(table)


def _format_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def run_event_ordering_sensitivity(
    config: BacktestConfig,
    market_data,
    audit,
    output_dir: Path,
    dataset_scope: str = "unknown",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for policy in ["trade_before_book", "book_before_trade"]:
        print(f"[event-ordering] {policy}", flush=True)
        result = Simulator(market_data, config, audit.tick_size, same_timestamp_policy=policy).run()
        row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
        row.update(
            {
                "variant": policy,
                "same_timestamp_policy": policy,
                "dataset_scope": dataset_scope,
                "trades_with_same_timestamp_book_pct": audit.event_ordering_stats.get("trades_with_same_timestamp_book_pct", 0.0),
                "book_updates_with_same_timestamp_trade_pct": audit.event_ordering_stats.get("book_updates_with_same_timestamp_trade_pct", 0.0),
            }
        )
        rows.append(row)
    results = pd.DataFrame(rows)
    results.to_csv(output_dir / "event_ordering_sensitivity.csv", index=False)
    results.to_csv(output_dir / "event_ordering_policy_sensitivity.csv", index=False)
    return results


def write_dataset_scope(market_data, output_dir: Path, suite_size: str, dataset_scope: str) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_days = []
    if "_source_day" in market_data.orderbook.columns:
        source_days = sorted(str(day) for day in market_data.orderbook["_source_day"].dropna().unique())
    table = pd.DataFrame(
        [
            {
                "suite_size": suite_size,
                "dataset_scope": dataset_scope,
                "orderbook_rows": int(len(market_data.orderbook)),
                "trade_rows": int(len(market_data.trades)),
                "funding_rows": int(len(market_data.fundings)),
                "source_days": ",".join(source_days),
            }
        ]
    )
    table.to_csv(output_dir / "run_scope.csv", index=False)
    return table


def run_sensitivity_suites(config: BacktestConfig, market_data, audit, output_dir: Path, dataset_scope: str = "unknown") -> None:
    queue_variants = [
        ("conservative_queue", replace(config, execution=replace(config.execution, fill_model="conservative_queue", queue_depletion_fraction=0.0))),
        ("partial_queue_0.25", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.25))),
        ("partial_queue_0.50", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.50))),
        ("partial_queue_1.00", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=1.00))),
        ("simple", replace(config, execution=replace(config.execution, fill_model="simple"))),
    ]
    latency_variants = [
        (f"cancel_latency_{latency_ms}", replace(config, execution=replace(config.execution, cancel_latency_ms=latency_ms)))
        for latency_ms in (0, 250, 500)
    ]
    fee_variants = [
        (f"fee_{fee_bps:g}bps", replace(config, execution=replace(config.execution, maker_fee_bps=fee_bps)))
        for fee_bps in (0.0, 0.5, 1.0)
    ]
    _write_variant_table(queue_variants, market_data, audit, output_dir / "queue_sensitivity", "queue_sensitivity.csv", dataset_scope)
    _write_variant_table(latency_variants, market_data, audit, output_dir / "latency_sensitivity", "latency_sensitivity.csv", dataset_scope)
    _write_variant_table(fee_variants, market_data, audit, output_dir / "fee_sensitivity", "fee_sensitivity.csv", dataset_scope)


def _write_variant_table(
    variants: list[tuple[str, BacktestConfig]],
    market_data,
    audit,
    output_dir: Path,
    filename: str,
    dataset_scope: str = "unknown",
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for run_index, (name, cfg) in enumerate(variants):
        print(f"[sensitivity] {output_dir.name} {run_index + 1}/{len(variants)} {name}", flush=True)
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
        row.update(
            {
                "variant": name,
                "dataset_scope": dataset_scope,
                "fill_model": cfg.execution.fill_model,
                "queue_depletion_fraction": cfg.execution.queue_depletion_fraction,
                "cancel_latency_ms": cfg.execution.cancel_latency_ms if cfg.execution.cancel_latency_ms is not None else cfg.execution.latency_ms,
                "maker_fee_bps": cfg.execution.maker_fee_bps,
            }
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(output_dir / filename, index=False)
    return table


def _core_robustness_variants(config: BacktestConfig) -> list[tuple[str, BacktestConfig]]:
    variants: list[tuple[str, BacktestConfig]] = [
        ("baseline", config),
        ("simple_fill", replace(config, execution=replace(config.execution, fill_model="simple"))),
        ("partial_queue_0.25", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.25))),
        ("partial_queue_0.50", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.50))),
    ]
    variants.extend(
        (f"cancel_latency_{latency_ms}", replace(config, execution=replace(config.execution, cancel_latency_ms=latency_ms)))
        for latency_ms in (0, 500)
    )
    variants.extend(
        (f"fee_{fee_bps:g}bps", replace(config, execution=replace(config.execution, maker_fee_bps=fee_bps)))
        for fee_bps in (0.0, 1.0)
    )
    variants.append(("pressure_filter_off", replace(config, strategy=replace(config.strategy, pressure_stop=999.0, k_adv=0.0))))
    return variants


def _full_core_robustness_variants(config: BacktestConfig) -> list[tuple[str, BacktestConfig]]:
    return [
        ("baseline", config),
        ("simple_fill", replace(config, execution=replace(config.execution, fill_model="simple"))),
        ("partial_queue_0.25", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.25))),
        ("partial_queue_0.50", replace(config, execution=replace(config.execution, fill_model="partial_queue", queue_depletion_fraction=0.50))),
        ("cancel_latency_0", replace(config, execution=replace(config.execution, cancel_latency_ms=0))),
        ("cancel_latency_500", replace(config, execution=replace(config.execution, cancel_latency_ms=500))),
        ("pressure_filter_off", replace(config, strategy=replace(config.strategy, pressure_stop=999.0, k_adv=0.0))),
        ("fee_0bps", replace(config, execution=replace(config.execution, maker_fee_bps=0.0))),
        ("fee_1bps", replace(config, execution=replace(config.execution, maker_fee_bps=1.0))),
    ]


def _ablation_variants(config: BacktestConfig, suite_size: str = "core") -> list[tuple[str, BacktestConfig]]:
    core = [
        ("full", config),
        ("no_pressure_filter", replace(config, strategy=replace(config.strategy, pressure_stop=999.0, k_adv=0.0))),
        ("no_microprice_alpha", replace(config, strategy=replace(config.strategy, alpha_micro=0.0))),
        ("no_inventory_skew", replace(config, strategy=replace(config.strategy, theta_inv=0.0))),
        ("no_funding_target", replace(config, strategy=replace(config.strategy, funding_target_frac=0.0))),
    ]
    if suite_size in {"smoke", "core", "full_core"}:
        return core
    return [
        *core,
        ("no_trade_flow_alpha", replace(config, strategy=replace(config.strategy, alpha_flow=0.0, w_trade=0.0))),
        ("no_volatility_widening", replace(config, strategy=replace(config.strategy, k_vol=0.0), risk=replace(config.risk, vol_widen_multiplier=1.0))),
        ("no_eod_reduce_only", replace(config, risk=replace(config.risk, eod_reduce_window_minutes=0))),
    ]


def _normalize_suite_size(value: str) -> str:
    return "core" if value == "standard" else value


def main() -> None:
    run_command(parse_args())


if __name__ == "__main__":
    main()
