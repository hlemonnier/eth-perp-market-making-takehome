from dataclasses import replace

import pandas as pd
import pytest

from market_maker import cli
from market_maker.config import load_config
from market_maker.data_audit import AuditResult
from market_maker.metrics import MetricsBundle
from market_maker.reporting import _fee_sensitivity, build_markdown_report, round_trip_summary
from market_maker.simulator import BacktestResult


def result_with_overall(overall: pd.DataFrame) -> BacktestResult:
    metrics = MetricsBundle(
        overall=overall,
        daily=pd.DataFrame(),
        fill_stats=pd.DataFrame(),
        order_stats=pd.DataFrame(),
        inventory_stats=pd.DataFrame(),
        realized_spread=pd.DataFrame(),
    )
    return BacktestResult(
        equity_curve=pd.DataFrame(),
        fills=pd.DataFrame(),
        orders=pd.DataFrame(),
        metrics=metrics,
        final_liquidation_adjusted_equity=0.0,
    )


def result_with_metrics(overall: pd.DataFrame, realized_spread: pd.DataFrame) -> BacktestResult:
    metrics = MetricsBundle(
        overall=overall,
        daily=pd.DataFrame(),
        fill_stats=pd.DataFrame(),
        order_stats=pd.DataFrame(),
        inventory_stats=pd.DataFrame(),
        realized_spread=realized_spread,
    )
    return BacktestResult(
        equity_curve=pd.DataFrame(),
        fills=pd.DataFrame(),
        orders=pd.DataFrame(),
        metrics=metrics,
        final_liquidation_adjusted_equity=0.0,
    )


def audit_result() -> AuditResult:
    return AuditResult(
        tick_size=0.1,
        summary=pd.DataFrame([{"check": "tick_inference", "severity": "ok", "value": 0.1, "detail": "test"}]),
        warnings=[],
        spread_stats={"one_tick_or_less_pct": 80.0},
        depth_stats={"bid_depth_1_p50": 1.0, "ask_depth_1_p50": 1.0},
    )


def test_report_uses_selected_fill_model_text():
    config = load_config("config/default.yaml")
    config = replace(config, execution=replace(config.execution, fill_model="simple"))
    report = build_markdown_report(result_with_overall(pd.DataFrame()), audit_result(), config)

    assert "- Fill model: `simple`." in report
    assert "Official result uses the conservative queue-ahead fill model" not in report


def test_fee_sensitivity_estimates_fee_drag_from_turnover():
    overall = pd.DataFrame(
        [
            {
                "total_pnl": 10.0,
                "fees": 0.0,
                "turnover_usd": 10_000.0,
            }
        ]
    )

    sensitivity = _fee_sensitivity(overall)

    one_bp = sensitivity[sensitivity["maker_fee_bps"] == 1.0].iloc[0]
    half_bp = sensitivity[sensitivity["maker_fee_bps"] == 0.5].iloc[0]
    assert one_bp["estimated_fees"] == pytest.approx(1.0)
    assert one_bp["estimated_total_pnl"] == pytest.approx(9.0)
    assert half_bp["estimated_total_pnl"] == pytest.approx(9.5)


def test_report_does_not_call_positive_roundtrip_pnl_clean_spread_capture():
    config = load_config("config/default.yaml")
    overall = pd.DataFrame(
        [
            {
                "total_pnl": 13.0,
                "forced_flat_pnl": 12.5,
                "realized_trading_pnl": 10.0,
                "unrealized_trading_pnl": 0.5,
                "funding_pnl": 0.0,
                "total_fills": 5,
                "max_drawdown": 4.0,
            }
        ]
    )
    realized_spread = pd.DataFrame(
        [
            {"horizon_seconds": 1, "average_realized_spread": -0.2},
            {"horizon_seconds": 5, "average_realized_spread": -0.4},
        ]
    )

    report = build_markdown_report(result_with_metrics(overall, realized_spread), audit_result(), config)

    assert "stronger evidence of spread capture" not in report
    assert "Fill count is sparse" in report
    assert "do not interpret this as clean spread capture" in report


def test_round_trip_summary_reports_pnl_concentration():
    round_trips = pd.DataFrame(
        [
            {"roundtrip_pnl": 9.0, "holding_seconds": 36_000},
            {"roundtrip_pnl": 1.0, "holding_seconds": 60},
            {"roundtrip_pnl": -2.0, "holding_seconds": 30},
        ]
    )

    summary = round_trip_summary(round_trips).iloc[0]

    assert summary["closed_round_trips"] == 3
    assert summary["total_roundtrip_pnl"] == pytest.approx(8.0)
    assert summary["top_roundtrip_pnl_share_pct"] == pytest.approx(90.0)
    assert summary["max_holding_seconds"] == pytest.approx(36_000)


def test_comparison_diagnostics_flag_inventory_directional_and_negative_spread():
    metrics = MetricsBundle(
        overall=pd.DataFrame(
            [
                {
                    "total_pnl": 100.0,
                    "realized_trading_pnl": 1.0,
                    "unrealized_trading_pnl": 99.0,
                    "total_fills": 5,
                }
            ]
        ),
        daily=pd.DataFrame(),
        fill_stats=pd.DataFrame(),
        order_stats=pd.DataFrame(),
        inventory_stats=pd.DataFrame([{"pct_long": 0.0, "pct_short": 95.0}]),
        realized_spread=pd.DataFrame(
            [
                {"horizon_seconds": 1, "average_realized_spread": -0.2},
                {"horizon_seconds": 5, "average_realized_spread": -0.5},
            ]
        ),
    )
    result = BacktestResult(
        equity_curve=pd.DataFrame(),
        fills=pd.DataFrame(),
        orders=pd.DataFrame(),
        metrics=metrics,
        final_liquidation_adjusted_equity=0.0,
    )

    diagnostics = cli._comparison_diagnostics(result)

    assert diagnostics["sparse_fill_warning"] is True
    assert diagnostics["inventory_directional_warning"] is True
    assert diagnostics["negative_realized_spread_warning"] is True
    assert diagnostics["avg_realized_spread_1s"] == pytest.approx(-0.2)
    assert diagnostics["comparison_warnings"] == "sparse_fills;inventory_directional_pnl;negative_realized_spread"
