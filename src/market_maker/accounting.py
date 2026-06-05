from __future__ import annotations

from dataclasses import dataclass

from market_maker.orders import Fill


EPS = 1e-12


@dataclass
class AccountingState:
    maker_fee_bps: float = 0.0
    cash: float = 0.0
    inventory: float = 0.0
    average_entry_price: float = 0.0
    realized_trading_pnl: float = 0.0
    funding_pnl: float = 0.0
    fees_paid: float = 0.0

    @property
    def maker_fee_rate(self) -> float:
        return self.maker_fee_bps / 10_000.0

    def apply_fill(self, fill: Fill) -> None:
        signed_qty = fill.signed_quantity
        old_inventory = self.inventory
        fill_price = fill.price

        self.cash -= signed_qty * fill_price
        self.fees_paid += abs(signed_qty) * fill_price * self.maker_fee_rate

        if abs(old_inventory) <= EPS:
            self.inventory = signed_qty
            self.average_entry_price = fill_price if abs(self.inventory) > EPS else 0.0
            return

        same_direction = old_inventory * signed_qty > 0
        if same_direction:
            new_inventory = old_inventory + signed_qty
            self.average_entry_price = (
                abs(old_inventory) * self.average_entry_price + abs(signed_qty) * fill_price
            ) / abs(new_inventory)
            self.inventory = new_inventory
            return

        close_qty = min(abs(old_inventory), abs(signed_qty))
        if old_inventory > 0:
            self.realized_trading_pnl += close_qty * (fill_price - self.average_entry_price)
        else:
            self.realized_trading_pnl += close_qty * (self.average_entry_price - fill_price)

        new_inventory = old_inventory + signed_qty
        self.inventory = new_inventory
        if abs(new_inventory) <= EPS:
            self.inventory = 0.0
            self.average_entry_price = 0.0
        elif old_inventory * new_inventory > 0:
            # Partially reduced but did not flip.
            pass
        else:
            # The fill crossed through flat; residual inventory starts at the fill price.
            self.average_entry_price = fill_price

    def accrue_funding(
        self,
        elapsed_seconds: float,
        mark_price: float,
        funding_rate: float,
        funding_period_hours: float,
    ) -> float:
        if elapsed_seconds <= 0 or abs(self.inventory) <= EPS:
            return 0.0
        period_seconds = funding_period_hours * 3600.0
        delta = -self.inventory * mark_price * funding_rate * (elapsed_seconds / period_seconds)
        self.funding_pnl += delta
        return delta

    def unrealized_trading_pnl(self, mark_price: float) -> float:
        if self.inventory > EPS:
            return self.inventory * (mark_price - self.average_entry_price)
        if self.inventory < -EPS:
            return abs(self.inventory) * (self.average_entry_price - mark_price)
        return 0.0

    def equity(self, mark_price: float) -> float:
        return self.cash + self.inventory * mark_price + self.funding_pnl - self.fees_paid

    def liquidation_adjusted_equity(self, best_bid: float, best_ask: float) -> float:
        if self.inventory > EPS:
            mark = best_bid
        elif self.inventory < -EPS:
            mark = best_ask
        else:
            mark = 0.0
        inventory_value = 0.0 if abs(self.inventory) <= EPS else self.inventory * mark
        return self.cash + inventory_value + self.funding_pnl - self.fees_paid
