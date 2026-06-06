from dataclasses import replace

import pandas as pd
import pytest

from market_maker.config import load_config
from market_maker.data_audit import AuditResult
from market_maker.metrics import MetricsBundle
from market_maker.reporting import _fee_sensitivity, build_markdown_report
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
    two_bp = sensitivity[sensitivity["maker_fee_bps"] == 2.0].iloc[0]
    assert one_bp["estimated_fees"] == pytest.approx(1.0)
    assert one_bp["estimated_total_pnl"] == pytest.approx(9.0)
    assert two_bp["estimated_total_pnl"] == pytest.approx(8.0)
