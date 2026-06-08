from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DataConfig:
    data_dir: Path
    days: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionConfig:
    maker_fee_bps: float
    latency_ms: int
    fill_model: str
    funding_period_hours: float
    report_frequency: str
    cancel_latency_ms: int | None = None
    queue_depletion_fraction: float = 0.0
    force_flat_slippage_bps: float = 0.0
    stale_book_max_age_ms: float = 1000.0


@dataclass(frozen=True)
class StrategyConfig:
    alpha_micro: float
    alpha_flow: float
    funding_scale: float
    funding_target_frac: float
    theta_inv: float
    base_order_size_eth: float
    q_max: float
    max_quote_size_eth: float
    min_half_spread_ticks: int
    spread_mult: float
    vol_window_seconds: int
    quote_horizon_seconds: int
    k_vol: float
    k_adv: float
    pressure_stop: float
    w_book: float
    w_trade: float
    refresh_interval_seconds: int
    max_quote_age_seconds: int
    requote_bbo_ticks: int
    requote_delta_ticks: int
    funding_retarget_threshold: float
    pressure_markout_ticks: float = 0.0
    min_edge_ticks: float = 0.0
    latency_buffer_ticks: float = 0.0
    cancel_latency_buffer_ticks: float = 0.0


@dataclass(frozen=True)
class RiskConfig:
    max_drawdown_usd: float
    vol_widen_multiplier: float
    jump_ticks_stop: int
    cooldown_seconds: int
    eod_reduce_window_minutes: int
    min_economic_spread_ticks: int


@dataclass(frozen=True)
class AuditConfig:
    max_funding_staleness_seconds: int
    trade_alignment_tolerance_ticks: int
    tick_sample_size: int
    mid_jump_warn_ticks: float = 20.0
    stale_book_warn_ms: float = 1000.0
    one_tick_spread_warn_pct: float = 50.0
    funding_abs_warn_threshold: float = 0.01


@dataclass(frozen=True)
class BacktestConfig:
    data: DataConfig
    execution: ExecutionConfig
    strategy: StrategyConfig
    risk: RiskConfig
    audit: AuditConfig


def _require_section(raw: dict[str, Any], section: str) -> dict[str, Any]:
    value = raw.get(section)
    if not isinstance(value, dict):
        raise ValueError(f"Missing config section: {section}")
    return value


def load_config(path: str | Path = "config/default.yaml") -> BacktestConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text()) or {}

    data = _require_section(raw, "data")
    execution = _require_section(raw, "execution")
    strategy = _require_section(raw, "strategy")
    risk = _require_section(raw, "risk")
    audit = _require_section(raw, "audit")

    return BacktestConfig(
        data=DataConfig(
            data_dir=Path(data["data_dir"]),
            days=tuple(str(day) for day in data["days"]),
        ),
        execution=ExecutionConfig(**execution),
        strategy=StrategyConfig(**strategy),
        risk=RiskConfig(**risk),
        audit=AuditConfig(**audit),
    )
