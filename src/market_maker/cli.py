from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from market_maker.config import BacktestConfig, DataConfig, ExecutionConfig, load_config
from market_maker.data_audit import run_audit, write_audit_outputs
from market_maker.data_loader import load_market_data
from market_maker.reporting import write_outputs
from market_maker.simulator import Simulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETH perpetual market-making audit and backtest.")
    parser.add_argument("command", choices=["audit", "backtest", "run"], help="Command to execute.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to YAML config.")
    parser.add_argument("--data-dir", default=None, help="Override data directory.")
    parser.add_argument("--output-dir", default="reports/baseline", help="Output directory.")
    parser.add_argument("--fill-model", choices=["simple", "conservative_queue"], default=None, help="Override fill model.")
    parser.add_argument("--allow-audit-errors", action="store_true", help="Run the backtest even when audit checks fail.")
    return parser.parse_args()


def override_config(config: BacktestConfig, args: argparse.Namespace) -> BacktestConfig:
    data = config.data
    execution = config.execution
    if args.data_dir is not None:
        data = replace(data, data_dir=Path(args.data_dir))
    if args.fill_model is not None:
        execution = replace(execution, fill_model=args.fill_model)
    return replace(config, data=data, execution=execution)


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

    simulator = Simulator(market_data, config, audit.tick_size)
    result = simulator.run()
    write_outputs(result, audit, config, output_dir)
    if not result.metrics.overall.empty:
        print(result.metrics.overall.to_string(index=False))
    print(f"Backtest complete: output_dir={output_dir}")


def main() -> None:
    run_command(parse_args())


if __name__ == "__main__":
    main()
