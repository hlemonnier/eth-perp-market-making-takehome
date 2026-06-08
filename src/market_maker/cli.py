from __future__ import annotations

import argparse
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

from market_maker.config import BacktestConfig, load_config
from market_maker.data_audit import run_audit, write_audit_outputs
from market_maker.data_loader import load_market_data
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
    parser.add_argument("--suite-size", choices=["smoke", "standard"], default="standard", help="Robustness/reproduce suite breadth.")
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
        results = run_robustness_suite(config, market_data, audit, output_dir, suite_size=getattr(args, "suite_size", "standard"))
        print(results.to_string(index=False))
        print(f"Robustness suite complete: output_dir={output_dir}")
        return

    if args.command == "ablations":
        results = run_ablation_suite(config, market_data, audit, output_dir)
        print(results.to_string(index=False))
        print(f"Ablation suite complete: output_dir={output_dir}")
        return

    if args.command == "reproduce":
        run_reproduce_suite(config, market_data, audit, output_dir, suite_size=getattr(args, "suite_size", "standard"))
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


def run_robustness_suite(config: BacktestConfig, market_data, audit, output_dir: Path, suite_size: str = "standard") -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    if suite_size == "smoke":
        pressure_values = [config.strategy.pressure_stop]
        queue_values = [0.0, 0.5]
        cancel_values = [0, config.execution.cancel_latency_ms if config.execution.cancel_latency_ms is not None else config.execution.latency_ms]
        fee_values = [config.execution.maker_fee_bps]
        spread_values = [config.strategy.min_half_spread_ticks]
    else:
        pressure_values = [0.25, 0.50, 0.75]
        queue_values = [0.0, 0.25, 0.5, 0.75]
        cancel_values = [0, 100, 250, 500]
        fee_values = [-0.5, 0.0, 0.5, 1.0]
        spread_values = [1, 2, 3]

    rows = []
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
        result = Simulator(market_data, cfg, audit.tick_size).run()
        row: dict[str, object] = {}
        if not result.metrics.overall.empty:
            row.update(result.metrics.overall.iloc[0].to_dict())
        row.update(
            {
                "run": run_index,
                "pressure_stop": pressure_stop,
                "queue_depletion_fraction": queue_depletion,
                "cancel_latency_ms": cancel_latency,
                "maker_fee_bps": fee,
                "min_half_spread_ticks": min_ticks,
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
        row = run_single_backtest(cfg, market_data, audit, output_dir / name)
        row["variant"] = name
        rows.append(row)
    results = pd.DataFrame(rows)
    results.to_csv(output_dir / "results.csv", index=False)
    return results


def run_reproduce_suite(config: BacktestConfig, market_data, audit, output_dir: Path, suite_size: str = "standard") -> None:
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
    run_ablation_suite(config, market_data, audit, output_dir / "ablations")
    run_robustness_suite(config, market_data, audit, output_dir / "robustness", suite_size=suite_size)


def main() -> None:
    run_command(parse_args())


if __name__ == "__main__":
    main()
