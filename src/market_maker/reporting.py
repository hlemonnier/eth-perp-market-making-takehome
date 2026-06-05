from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from market_maker.config import BacktestConfig
from market_maker.data_audit import AuditResult
from market_maker.simulator import BacktestResult


def write_outputs(
    result: BacktestResult,
    audit: AuditResult,
    config: BacktestConfig,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plots = output / "plots"
    plots.mkdir(exist_ok=True)

    result.equity_curve.to_csv(output / "equity_curve.csv", index=False)
    result.fills.to_csv(output / "fills.csv", index=False)
    result.orders.to_csv(output / "orders.csv", index=False)
    result.metrics.overall.to_csv(output / "summary.csv", index=False)
    result.metrics.daily.to_csv(output / "daily_pnl.csv", index=False)
    result.metrics.fill_stats.to_csv(output / "fill_stats.csv", index=False)
    result.metrics.inventory_stats.to_csv(output / "inventory_stats.csv", index=False)
    result.metrics.realized_spread.to_csv(output / "realized_spread.csv", index=False)

    _plot_equity(result.equity_curve, plots / "equity_curve.png")
    _plot_inventory(result.equity_curve, plots / "inventory.png")
    _plot_spread_histogram(result.equity_curve, plots / "spread_histogram.png")
    _plot_funding_inventory(result.equity_curve, plots / "funding_inventory.png")
    _plot_fills(result.equity_curve, result.fills, plots / "fills_on_mid.png")

    report = build_markdown_report(result, audit, config)
    (output / "final_report.md").write_text(report)


def build_markdown_report(result: BacktestResult, audit: AuditResult, config: BacktestConfig) -> str:
    overall = result.metrics.overall.iloc[0].to_dict() if not result.metrics.overall.empty else {}
    interpretation = _interpretation(overall)
    lines = [
        "# ETH Perpetual Market-Making Backtest",
        "",
        "## Assumptions",
        "",
        "- Strategy is maker-only and keeps at most one bid and one ask live.",
        "- Official result uses the conservative queue-ahead fill model.",
        f"- Maker fee assumption: `{config.execution.maker_fee_bps}` bps.",
        f"- Latency assumption: `{config.execution.latency_ms}` ms.",
        f"- Funding accrual uses latest known funding over `{config.execution.funding_period_hours}` hour periods.",
        f"- Inferred tick size: `{audit.tick_size}`.",
        "- End inventory is marked to mid for baseline PnL and to bid/ask for liquidation-adjusted sensitivity.",
        "",
        "## Audit Summary",
        "",
        f"- Audit passed: `{audit.passed}`.",
        f"- Warning checks: `{', '.join(audit.warnings) if audit.warnings else 'none'}`.",
        "",
        "## Strategy",
        "",
        "Fair value combines mid, microprice, and past-only trade imbalance. Quotes use adaptive half-distance, inventory-skewed reservation price, funding target inventory, adverse-pressure side stops, volatility cooldown, and end-of-day reduce-only behavior.",
        "",
        "## Results",
        "",
    ]
    if overall:
        for key, value in overall.items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No equity results produced.")
    lines += [
        "",
        "## Daily PnL",
        "",
        _markdown_table(result.metrics.daily),
        "",
        "## Fill Statistics",
        "",
        _markdown_table(result.metrics.fill_stats),
        "",
        "## Inventory Statistics",
        "",
        _markdown_table(result.metrics.inventory_stats),
        "",
        "## Realized Spread and Adverse Selection",
        "",
        _markdown_table(result.metrics.realized_spread),
        "",
        "## Conclusion",
        "",
        interpretation,
        "",
        "",
        "## Output Files",
        "",
        "- `audit_summary.csv`, `spread_stats.csv`, `depth_stats.csv`",
        "- `summary.csv`, `daily_pnl.csv`, `fills.csv`, `orders.csv`, `equity_curve.csv`",
        "- `fill_stats.csv`, `inventory_stats.csv`, `realized_spread.csv`",
        "- `plots/equity_curve.png`, `plots/inventory.png`, `plots/spread_histogram.png`, `plots/fills_on_mid.png`, `plots/funding_inventory.png`",
        "",
        "## Interpretation Discipline",
        "",
        "Use the PnL decomposition rather than total PnL alone. Positive realized trading PnL with controlled inventory and limited adverse selection is stronger evidence of market-making quality than mark-to-market gains from residual inventory.",
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    shown = df.head(max_rows).copy()
    headers = list(shown.columns)
    rows = []
    for _, row in shown.iterrows():
        rows.append([_format_cell(row[col]) for col in headers])
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    suffix = []
    if len(df) > max_rows:
        suffix.append(f"\n_Showing {max_rows} of {len(df)} rows._")
    return "\n".join([header_line, separator, *body, *suffix])


def _format_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _interpretation(overall: dict[str, object]) -> str:
    if not overall:
        return "No backtest result was produced."
    total = float(overall.get("total_pnl", 0.0))
    realized = float(overall.get("realized_trading_pnl", 0.0))
    unrealized = float(overall.get("unrealized_trading_pnl", 0.0))
    funding = float(overall.get("funding_pnl", 0.0))
    fills = int(float(overall.get("total_fills", 0.0)))
    drawdown = float(overall.get("max_drawdown", 0.0))
    parts = [
        f"The run finished with total PnL `{total:.4f}` USD, realized trading PnL `{realized:.4f}` USD, unrealized trading PnL `{unrealized:.4f}` USD, and funding PnL `{funding:.4f}` USD.",
        f"The strategy generated `{fills}` fills and max drawdown `{drawdown:.4f}` USD under the selected fill model.",
    ]
    if abs(unrealized) > max(abs(realized) * 3.0, 1.0):
        parts.append(
            "Most reported PnL is mark-to-market inventory PnL rather than realized spread capture, so the result should be treated as a conservative simulator validation, not proof of robust market-making edge."
        )
    elif realized > 0:
        parts.append("Realized trading PnL is positive, which is stronger evidence of spread capture than total PnL alone.")
    else:
        parts.append("Realized trading PnL is not positive, so adverse selection and quote placement need further work before calling the strategy profitable.")
    return " ".join(parts)


def _plot_equity(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity["timestamp"], equity["equity"], linewidth=1)
    ax.set_title("Equity Curve")
    ax.set_ylabel("USD")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_inventory(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity["timestamp"], equity["inventory"], linewidth=1)
    ax.set_title("Inventory")
    ax.set_ylabel("ETH")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_spread_histogram(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    equity["spread"].dropna().hist(ax=ax, bins=80)
    ax.set_title("Spread Distribution")
    ax.set_xlabel("USD")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_funding_inventory(equity: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(equity["timestamp"], equity["inventory"], linewidth=1, label="Inventory")
    ax1.set_ylabel("Inventory ETH")
    ax2 = ax1.twinx()
    ax2.plot(equity["timestamp"], equity["funding_rate"], linewidth=0.8, color="tab:orange", label="Funding")
    ax2.set_ylabel("Funding rate")
    ax1.set_title("Funding Rate and Inventory")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_fills(equity: pd.DataFrame, fills: pd.DataFrame, path: Path) -> None:
    if equity.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    sampled = equity.iloc[:: max(1, len(equity) // 50_000)]
    ax.plot(sampled["timestamp"], sampled["mid"], linewidth=0.8, label="Mid")
    if not fills.empty:
        bids = fills[fills["side"] == "bid"]
        asks = fills[fills["side"] == "ask"]
        ax.scatter(bids["timestamp"], bids["price"], s=8, label="Buy fills", alpha=0.7)
        ax.scatter(asks["timestamp"], asks["price"], s=8, label="Sell fills", alpha=0.7)
    ax.set_title("Fills on Mid Price")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
