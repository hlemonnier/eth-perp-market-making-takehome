from __future__ import annotations

import numpy as np
import pandas as pd

from market_maker.config import load_config
from market_maker.data_loader import load_market_data


def main() -> None:
    cfg = load_config("config/default.yaml")
    data = load_market_data(cfg.data.data_dir, cfg.data.days)
    book = data.orderbook[
        ["datetime", "bid_price_1", "ask_price_1", "bid_qty_1", "ask_qty_1", "_source_day"]
    ].copy()
    book["mid"] = (book["bid_price_1"] + book["ask_price_1"]) / 2.0
    book["imbalance"] = (book["bid_qty_1"] - book["ask_qty_1"]) / (book["bid_qty_1"] + book["ask_qty_1"])
    book = book.sort_values("datetime")

    rows = []
    for horizon_seconds in [1, 5, 30]:
        lookup = book[["datetime", "mid"]].rename(columns={"datetime": "future_time", "mid": "future_mid"})
        left = book[["datetime", "mid", "imbalance", "_source_day"]].copy()
        left["future_time"] = left["datetime"] + pd.Timedelta(seconds=horizon_seconds)
        aligned = pd.merge_asof(
            left.sort_values("future_time"),
            lookup.sort_values("future_time"),
            on="future_time",
            direction="forward",
        ).dropna(subset=["future_mid"])
        aligned["signed_move"] = np.sign(aligned["imbalance"]) * (aligned["future_mid"] - aligned["mid"])
        selected = aligned[aligned["imbalance"].abs() >= 0.5]
        day_means = selected.groupby("_source_day")["signed_move"].mean()
        rows.append(
            {
                "horizon_seconds": horizon_seconds,
                "rows": int(len(selected)),
                "mean_signed_move": float(selected["signed_move"].mean()),
                "hit_rate": float((selected["signed_move"] > 0).mean()),
                **{f"{day}_mean": float(day_means.get(day, 0.0)) for day in cfg.data.days},
            }
        )

    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
