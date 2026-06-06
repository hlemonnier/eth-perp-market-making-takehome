from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class MetricsBundle:
    overall: pd.DataFrame
    daily: pd.DataFrame
    fill_stats: pd.DataFrame
    order_stats: pd.DataFrame
    inventory_stats: pd.DataFrame
    realized_spread: pd.DataFrame


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    drawdown = equity - equity.cummax()
    return float(-drawdown.min())


def sharpe_like_1m(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty:
        return 0.0
    curve = equity_curve.set_index("timestamp").sort_index()
    resampled = curve["equity"].resample("1min").last().ffill()
    pnl = resampled.diff().dropna()
    if len(pnl) < 2 or pnl.std(ddof=1) == 0:
        return 0.0
    return float(np.sqrt(1440.0) * pnl.mean() / pnl.std(ddof=1))


def daily_summary(equity_curve: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame()
    curve = equity_curve.copy()
    curve["date"] = curve["timestamp"].dt.date.astype(str)
    rows = []
    previous_end = 0.0
    previous_realized = 0.0
    previous_unrealized = 0.0
    previous_funding = 0.0
    previous_fees = 0.0
    for date, day in curve.groupby("date", sort=True):
        day_fills = fills[fills["timestamp"].dt.date.astype(str) == date] if not fills.empty else pd.DataFrame()
        start_equity = previous_end
        end_equity = float(day["equity"].iloc[-1])
        end_realized = float(day["realized_trading_pnl"].iloc[-1])
        end_unrealized = float(day["unrealized_trading_pnl"].iloc[-1])
        end_funding = float(day["funding_pnl"].iloc[-1])
        end_fees = float(day["fees"].iloc[-1])
        previous_end = end_equity
        rows.append(
            {
                "date": date,
                "starting_equity": start_equity,
                "ending_equity": end_equity,
                "daily_pnl": end_equity - start_equity,
                "daily_realized_trading_pnl": end_realized - previous_realized,
                "daily_unrealized_trading_pnl_change": end_unrealized - previous_unrealized,
                "daily_funding_pnl": end_funding - previous_funding,
                "daily_fees": end_fees - previous_fees,
                "ending_realized_trading_pnl": end_realized,
                "ending_unrealized_trading_pnl": end_unrealized,
                "ending_funding_pnl": end_funding,
                "ending_fees": end_fees,
                "bid_fills": int((day_fills["side"] == "bid").sum()) if not day_fills.empty else 0,
                "ask_fills": int((day_fills["side"] == "ask").sum()) if not day_fills.empty else 0,
                "bid_volume_eth": float(day_fills.loc[day_fills["side"] == "bid", "quantity"].sum()) if not day_fills.empty else 0.0,
                "ask_volume_eth": float(day_fills.loc[day_fills["side"] == "ask", "quantity"].sum()) if not day_fills.empty else 0.0,
                "average_inventory": float(day["inventory"].mean()),
                "max_abs_inventory": float(day["inventory"].abs().max()),
                "max_drawdown": max_drawdown(day["equity"]),
            }
        )
        previous_realized = end_realized
        previous_unrealized = end_unrealized
        previous_funding = end_funding
        previous_fees = end_fees
    return pd.DataFrame(rows)


def realized_spread_stats(fills: pd.DataFrame, equity_curve: pd.DataFrame) -> pd.DataFrame:
    if fills.empty or equity_curve.empty:
        return pd.DataFrame()
    curve = equity_curve[["timestamp", "mid"]].dropna().sort_values("timestamp")
    rows = []
    for horizon in [1, 5, 30]:
        future = curve.copy()
        future["lookup_time"] = future["timestamp"]
        fill_lookup = fills.copy()
        fill_lookup["lookup_time"] = fill_lookup["timestamp"] + pd.Timedelta(seconds=horizon)
        aligned = pd.merge_asof(
            fill_lookup.sort_values("lookup_time"),
            future[["lookup_time", "mid"]].sort_values("lookup_time"),
            on="lookup_time",
            direction="forward",
        )
        if aligned.empty:
            continue
        aligned = aligned.dropna(subset=["mid", "mid_at_fill"])
        if aligned.empty:
            continue
        sell = aligned["side"] == "ask"
        realized = np.where(sell, aligned["price"] - aligned["mid"], aligned["mid"] - aligned["price"])
        toxicity = np.where(sell, aligned["mid"] - aligned["mid_at_fill"], aligned["mid_at_fill"] - aligned["mid"])
        rows.append(
            {
                "horizon_seconds": horizon,
                "average_realized_spread": float(np.nanmean(realized)),
                "average_toxicity": float(np.nanmean(toxicity)),
            }
        )
    return pd.DataFrame(rows)


def summarize_metrics(
    equity_curve: pd.DataFrame,
    fills: pd.DataFrame,
    orders: pd.DataFrame,
    final_liquidation_adjusted_equity: float,
    event_max_drawdown_loss: float | None = None,
) -> MetricsBundle:
    if equity_curve.empty:
        empty = pd.DataFrame()
        return MetricsBundle(empty, empty, empty, empty, empty, empty)

    final = equity_curve.iloc[-1]
    total_fill_volume = float(fills["quantity"].sum()) if not fills.empty else 0.0
    turnover = float((fills["quantity"] * fills["price"]).sum()) if not fills.empty else 0.0
    overall = pd.DataFrame(
        [
            {
                "total_pnl": float(final["equity"]),
                "realized_trading_pnl": float(final["realized_trading_pnl"]),
                "unrealized_trading_pnl": float(final["unrealized_trading_pnl"]),
                "funding_pnl": float(final["funding_pnl"]),
                "fees": float(final["fees"]),
                "liquidation_adjusted_pnl": final_liquidation_adjusted_equity,
                "total_fills": int(len(fills)),
                "fill_volume_eth": total_fill_volume,
                "turnover_usd": turnover,
                "max_inventory": float(equity_curve["inventory"].max()),
                "min_inventory": float(equity_curve["inventory"].min()),
                "mean_abs_inventory": float(equity_curve["inventory"].abs().mean()),
                "max_drawdown": float(event_max_drawdown_loss) if event_max_drawdown_loss is not None else max_drawdown(equity_curve["equity"]),
                "sampled_1m_max_drawdown": max_drawdown(equity_curve["equity"]),
                "sharpe_like_1m": sharpe_like_1m(equity_curve),
                "pnl_per_turnover": float(final["equity"] / turnover) if turnover else 0.0,
                "pnl_per_eth": float(final["equity"] / total_fill_volume) if total_fill_volume else 0.0,
            }
        ]
    )

    if fills.empty:
        fill_stats = pd.DataFrame()
    else:
        passive_edge = np.where(
            fills["side"] == "ask",
            fills["price"] - fills["mid_at_fill"],
            fills["mid_at_fill"] - fills["price"],
        )
        fill_stats = pd.DataFrame(
            [
                {
                    "fill_count": int(len(fills)),
                    "fill_volume_eth": total_fill_volume,
                    "bid_fills": int((fills["side"] == "bid").sum()),
                    "ask_fills": int((fills["side"] == "ask").sum()),
                    "mean_fill_size": float(fills["quantity"].mean()),
                    "median_fill_size": float(fills["quantity"].median()),
                    "average_fill_notional": float((fills["quantity"] * fills["price"]).mean()),
                    "average_passive_edge_to_mid": float(np.nanmean(passive_edge)),
                }
            ]
        )

    order_stats = summarize_orders(orders, fills)

    inventory = equity_curve["inventory"]
    inventory_stats = pd.DataFrame(
        [
            {
                "mean_inventory": float(inventory.mean()),
                "mean_abs_inventory": float(inventory.abs().mean()),
                "std_inventory": float(inventory.std(ddof=1)) if len(inventory) > 1 else 0.0,
                "min_inventory": float(inventory.min()),
                "max_inventory": float(inventory.max()),
                "pct_long": float((inventory > 0).mean() * 100.0),
                "pct_short": float((inventory < 0).mean() * 100.0),
                "pct_flat": float((inventory.abs() <= 1e-12).mean() * 100.0),
            }
        ]
    )

    return MetricsBundle(
        overall=overall,
        daily=daily_summary(equity_curve, fills),
        fill_stats=fill_stats,
        order_stats=order_stats,
        inventory_stats=inventory_stats,
        realized_spread=realized_spread_stats(fills, equity_curve),
    )


def summarize_orders(orders: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            [
                {
                    "placed_orders": 0,
                    "cancelled_orders": 0,
                    "resized_orders": 0,
                    "fill_to_order_ratio": 0.0,
                    "average_quote_lifetime_seconds": 0.0,
                    "pct_orders_cancelled_before_active": 0.0,
                }
            ]
        )

    placed = orders[orders["event"] == "placed"].copy()
    cancelled = orders[orders["event"] == "cancelled"].copy()
    resized = orders[orders["event"] == "resized"]
    fill_count = len(fills)
    fill_to_order_ratio = fill_count / len(placed) if len(placed) else 0.0

    lifetimes: list[float] = []
    cancelled_before_active = 0
    if not placed.empty and not cancelled.empty:
        placed_by_id = placed.drop_duplicates("order_id").set_index("order_id")
        for _, cancel in cancelled.iterrows():
            order_id = cancel["order_id"]
            if order_id not in placed_by_id.index:
                continue
            created = pd.Timestamp(placed_by_id.loc[order_id, "timestamp"])
            active_time = pd.Timestamp(placed_by_id.loc[order_id, "active_time"])
            cancelled_at = pd.Timestamp(cancel["timestamp"])
            lifetimes.append(max(0.0, (cancelled_at - created).total_seconds()))
            if cancelled_at < active_time:
                cancelled_before_active += 1

    return pd.DataFrame(
        [
            {
                "placed_orders": int(len(placed)),
                "cancelled_orders": int(len(cancelled)),
                "resized_orders": int(len(resized)),
                "fill_to_order_ratio": float(fill_to_order_ratio),
                "average_quote_lifetime_seconds": float(np.mean(lifetimes)) if lifetimes else 0.0,
                "pct_orders_cancelled_before_active": float(cancelled_before_active / len(cancelled) * 100.0) if len(cancelled) else 0.0,
            }
        ]
    )
