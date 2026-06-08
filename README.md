# ETH Perpetual Market-Making Research Framework

This project is an event-driven ETH perpetual market-making research framework. It is not framed as proof that a toy strategy is live-tradable. The objective is to show where a top-of-book imbalance strategy survives realistic assumptions, where it fails, and how those assumptions change the result.

## Data

The included dataset covers ETH perpetual order book, trades, and funding rows for 2026-03-19 through 2026-03-21 under `data/`.

## Simulator Design

The simulator processes book, trade, and funding events in timestamp order. Orders follow a stricter lifecycle: pending new, live, pending cancel, cancelled, or filled. Placement latency and cancel latency are both modeled, so stale quotes can still be filled before a cancel becomes effective. A stale-book guard cancels quotes and blocks new quoting when the latest book mark is too old.

## Strategy Model

The strategy combines microprice, trade-flow imbalance, inventory skew, funding target inventory, volatility widening, and adverse-pressure controls. Pressure is treated as an adverse markout estimate: it suppresses toxic bid or ask sides rather than pretending imbalance is a large directional alpha signal.

## Fill Models

The project supports `simple`, `conservative_queue`, `partial_queue`, and `calibrated_queue`. The partial/calibrated queue model uses trade volume plus a configurable fraction of visible queue reduction at the order level.

## Accounting And Risk

Reports include mid-marked PnL, liquidation-adjusted PnL, forced-flat PnL, realized trading PnL, inventory MTM, funding PnL, fees, drawdown, fill diagnostics, order lifetimes, and cancellation reasons. The default fee assumption is non-zero.

## Reproduce

Run the bounded smoke workflow. It compiles, tests, and uses the first 50,000 order book rows from the first day so it finishes quickly:

```bash
make smoke
```

Run the core workflow. It uses the bounded sample plus robustness, ablation, queue, latency, and fee sensitivity outputs:

```bash
make reproduce
```

Run only the core robustness grid:

```bash
mm-backtest robustness --suite-size core --output-dir reports/robustness
```

The robustness grid writes `grid_results.csv` and a PnL pivot by queue depletion and cancel latency. `--suite-size full` is available for a much heavier exhaustive grid, but it is not the default submission workflow.

## Known Limitations

The strategy remains a research prototype. Passive fill quality is highly sensitive to queue assumptions, cancel latency, and fees. Simple-fill results are an aggressive adverse-selection stress, not a flattering upper bound.
