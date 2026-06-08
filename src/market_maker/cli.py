from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

from market_maker.config import BacktestConfig, load_config
from market_maker.data_audit import run_audit, write_audit_outputs
from market_maker.data_loader import load_market_data, load_market_data_sample
from market_maker.reporting import write_outputs
from market_maker.simulator import Simulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETH perpetual market-making audit and backtest.")
    parser.add_argument("command", choices=["audit", "backtest", "run", "robustness", "ablations", "reproduce"], help="Command to execute.")
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
    parser.add_argument("--suite-size", choices=["smoke", "core", "full", "standard"], default="core", help="Robustness/reproduce suite breadth.")
    parser.add_argument("--smoke-rows", type=int, default=50_000, help="Orderbook rows to load for smoke/core reproducibility suites.")
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
    if args.command in {"robustness", "ablations", "reproduce"} and suite_size in {"smoke", "core"}:
        market_data = load_market_data_sample(config.data.data_dir, config.data.days, max_orderbook_rows=getattr(args, "smoke_rows", 50_000))
    else:
        market_data = load_market_data(config.data.data_dir, config.data.days)
    audit = run_audit(market_data, config.audit)
    output_dir = Path(args.output_dir)
    write_audit_outputs(audit, output_dir)

    if args.command == "audit":
        print(f"Audit complete: passed={audit.passed}, tick_size={audit.tick_size}, output_dir={output_dir}")
        return

    if not audit.passed and not getattr(args, "allow_audit_errors", False):
        raise SystemExit(f"Audit failed; refusing to run backtest. Review {output_dir / 'audit_summary.csv'} or pass --allow-audit-errors.")

    if args.command == "robustness":
        results = run_robustness_suite(config, market_data, audit, output_dir, suite_size=suite_size)
        print(results.to_string(index=False))
        print(f"Robustness suite complete: output_dir={output_dir}")
        return

    if args.command == "ablations":
        results = run_ablation_suite(config, market_data, audit, output_dir)
        print(results.to_string(index=False))
        print(f"Ablation suite complete: output_dir={output_dir}")
        return

    if args.command == "reproduce":
        run_reproduce_suite(config, market_data, audit, output_dir, suite_size=suite_size)
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


def run_robustness_suite(config: BacktestConfig, market_data, audit, output_dir: Path, suite_size: str = "core") -> pd.DataFrame:
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
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row: dict[str, object] = {}
        if not result.metrics.overall.empty:
            row.update(result.metrics.overall.iloc[0].to_dict())
        row.update(
            {
                "run": run_index,
                "variant": variant,
                "fill_model": cfg.execution.fill_model,
                "pressure_stop": cfg.strategy.pressure_stop,
                "queue_depletion_fraction": cfg.execution.queue_depletion_fraction,
                "cancel_latency_ms": cfg.execution.cancel_latency_ms if cfg.execution.cancel_latency_ms is not None else cfg.execution.latency_ms,
                "maker_fee_bps": cfg.execution.maker_fee_bps,
                "min_half_spread_ticks": cfg.strategy.min_half_spread_ticks,
            }
        )
        rows.append(row)
    results = pd.DataFrame(rows)
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


def run_ablation_suite(config: BacktestConfig, market_data, audit, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = {
        "full": config,
        "no_pressure_filter": replace(config, strategy=replace(config.strategy, pressure_stop=999.0, k_adv=0.0)),
        "no_microprice_alpha": replace(config, strategy=replace(config.strategy, alpha_micro=0.0)),
        "no_trade_flow_alpha": replace(config, strategy=replace(config.strategy, alpha_flow=0.0, w_trade=0.0)),
        "no_inventory_skew": replace(config, strategy=replace(config.strategy, theta_inv=0.0)),
        "no_funding_target": replace(config, strategy=replace(config.strategy, funding_target_frac=0.0)),
        "no_volatility_widening": replace(config, strategy=replace(config.strategy, k_vol=0.0), risk=replace(config.risk, vol_widen_multiplier=1.0)),
        "no_eod_reduce_only": replace(config, risk=replace(config.risk, eod_reduce_window_minutes=0)),
    }
    rows = []
    for name, cfg in variants.items():
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
        row["variant"] = name
        rows.append(row)
    results = pd.DataFrame(rows)
    results.to_csv(output_dir / "ablation_results.csv", index=False)
    return results


def run_reproduce_suite(config: BacktestConfig, market_data, audit, output_dir: Path, suite_size: str = "core") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
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
    comparison.to_csv(output_dir / "fill_model_comparison.csv", index=False)
    run_sensitivity_suites(config, market_data, audit, output_dir)
    run_ablation_suite(config, market_data, audit, output_dir / "ablations")
    run_robustness_suite(config, market_data, audit, output_dir / "robustness", suite_size=suite_size)


def run_sensitivity_suites(config: BacktestConfig, market_data, audit, output_dir: Path) -> None:
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
    _write_variant_table(queue_variants, market_data, audit, output_dir / "queue_sensitivity", "queue_sensitivity.csv")
    _write_variant_table(latency_variants, market_data, audit, output_dir / "latency_sensitivity", "latency_sensitivity.csv")
    _write_variant_table(fee_variants, market_data, audit, output_dir / "fee_sensitivity", "fee_sensitivity.csv")


def _write_variant_table(variants: list[tuple[str, BacktestConfig]], market_data, audit, output_dir: Path, filename: str) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, cfg in variants:
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
        row.update(
            {
                "variant": name,
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


def _normalize_suite_size(value: str) -> str:
    return "core" if value == "standard" else value


def main() -> None:
    run_command(parse_args())


if __name__ == "__main__":
    main()
