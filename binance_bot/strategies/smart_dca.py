"""Smart DCA (Dollar Cost Averaging) with Safety Orders.

Inspired by 3Commas DCA bots. Places a base order, then safety orders
at increasing intervals below. Each safety order is larger than the previous,
lowering the average entry. Take profit from the averaged entry price.

Entry trigger: RSI oversold OR price below BB lower band (relaxed from AND).
Safety orders: stepped % below base, with volume scaling.
Hard stop loss to prevent catastrophic loss (this is NOT pure Martingale).
"""

import logging

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import calc_rsi, calc_bollinger, calc_atr

logger = logging.getLogger("binance_bot.strategy.smart_dca")

# DCA config defaults
MAX_SAFETY_ORDERS = 4     # Increased from 3 — more averaging depth
SAFETY_ORDER_STEP_PCT = 1.2  # Slightly tighter spacing (was 1.5%)
SAFETY_ORDER_VOLUME_SCALE = 1.5  # Each SO is 1.5x the previous
TAKE_PROFIT_PCT = 1.2     # Slightly tighter TP (was 1.5%) — close faster
STOP_LOSS_PCT = 5.0       # Hard stop loss % below averaged entry
RSI_ENTRY_THRESHOLD = 45  # RSI below this to start (was 35 — much more permissive)


class SmartDCAStrategy(BaseStrategy):
    name = "smart_dca"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._deal_active = False
        self._safety_orders_placed = 0
        self._averaged_entry = 0.0
        self._total_quantity = 0.0
        self._total_cost = 0.0
        self._next_so_price = 0.0

    def _calc_next_safety_order(self, base_price: float, so_number: int) -> dict:
        """Calculate price and quantity for the next safety order."""
        cumulative_pct = 0
        for i in range(1, so_number + 1):
            cumulative_pct += SAFETY_ORDER_STEP_PCT * (1.2 ** (i - 1))

        price = base_price * (1 - cumulative_pct / 100)
        quantity = self.trading.buy_order_amount * (SAFETY_ORDER_VOLUME_SCALE ** so_number)

        return {"price": price, "quantity": quantity}

    def _update_averaged_entry(self, fill_price: float, fill_qty: float):
        """Recalculate averaged entry after a new fill."""
        self._total_cost += fill_price * fill_qty
        self._total_quantity += fill_qty
        self._averaged_entry = self._total_cost / self._total_quantity if self._total_quantity > 0 else fill_price

    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]

        rsi = calc_rsi(closes, self.config.rsi_period)
        bb = calc_bollinger(closes)

        # If no deal active, look for entry
        if not self._deal_active and not open_positions:
            # Entry conditions: RSI oversold OR price at/below BB lower
            # (relaxed from AND — either condition is enough)
            rsi_ok = rsi and rsi.value < RSI_ENTRY_THRESHOLD
            bb_ok = bb and current_price <= bb.lower

            if rsi_ok or bb_ok:
                # Start a new DCA deal
                self._deal_active = True
                self._safety_orders_placed = 0
                self._total_cost = 0
                self._total_quantity = 0
                self._averaged_entry = 0

                # Calculate first safety order trigger
                so1 = self._calc_next_safety_order(current_price, 1)
                self._next_so_price = so1["price"]

                entry_reasons = []
                if rsi_ok:
                    entry_reasons.append(f"RSI={rsi.value}")
                if bb_ok:
                    entry_reasons.append(f"price <= BB lower ({bb.lower:.8f})")

                logger.info(
                    f"[dca] Starting deal: base_price={current_price}, "
                    f"{', '.join(entry_reasons)}, next_SO={self._next_so_price:.8f} | "
                    f"params: TP={TAKE_PROFIT_PCT}%, SL={STOP_LOSS_PCT}%, "
                    f"max_SO={MAX_SAFETY_ORDERS}, SO_step={SAFETY_ORDER_STEP_PCT}%, "
                    f"vol_scale={SAFETY_ORDER_VOLUME_SCALE}x"
                )

                return Signal(
                    action="buy",
                    price=current_price,
                    quantity=self.trading.buy_order_amount,
                    sell_target=None,  # Set after fill
                    stop_loss=None,  # Set after averaged entry calc
                    reason=f"DCA base order: {', '.join(entry_reasons)}",
                    metadata={"dca_type": "base_order"},
                )

            reason_parts = []
            if rsi:
                reason_parts.append(f"RSI={rsi.value}")
            if bb:
                reason_parts.append(f"BB_lower={bb.lower:.8f}")
            return Signal(
                action="hold", price=current_price,
                reason=f"Waiting for entry: {', '.join(reason_parts)}",
            )

        # Deal active — manage it
        if self._deal_active or open_positions:
            # Rebuild state from positions if needed
            if open_positions and not self._deal_active:
                self._deal_active = True
                self._total_cost = sum(p["entry_price"] * p["quantity"] for p in open_positions)
                self._total_quantity = sum(p["quantity"] for p in open_positions)
                self._averaged_entry = self._total_cost / self._total_quantity if self._total_quantity > 0 else current_price
                self._safety_orders_placed = max(0, len(open_positions) - 1)

            # Update averaged entry from actual positions
            if open_positions:
                self._total_cost = sum(p["entry_price"] * p["quantity"] for p in open_positions)
                self._total_quantity = sum(p["quantity"] for p in open_positions)
                self._averaged_entry = self._total_cost / self._total_quantity

            # Check take profit
            tp_price = self._averaged_entry * (1 + TAKE_PROFIT_PCT / 100)
            if current_price >= tp_price and open_positions:
                self._deal_active = False
                profit_pct = ((current_price - self._averaged_entry) / self._averaged_entry) * 100
                logger.info(
                    f"[dca] Take profit: avg_entry={self._averaged_entry:.8f}, "
                    f"exit={current_price}, profit={profit_pct:.2f}%"
                )
                return Signal(
                    action="sell",
                    price=current_price,
                    reason=f"DCA take profit: +{profit_pct:.2f}% (avg_entry={self._averaged_entry:.8f})",
                    metadata={"position_ids": [p["id"] for p in open_positions]},
                )

            # Check hard stop loss
            sl_price = self._averaged_entry * (1 - STOP_LOSS_PCT / 100)
            if current_price <= sl_price and open_positions:
                self._deal_active = False
                loss_pct = ((current_price - self._averaged_entry) / self._averaged_entry) * 100
                logger.warning(
                    f"[dca] Stop loss: avg_entry={self._averaged_entry:.8f}, "
                    f"exit={current_price}, loss={loss_pct:.2f}%"
                )
                return Signal(
                    action="sell",
                    price=current_price,
                    reason=f"DCA stop loss: {loss_pct:.2f}% (avg_entry={self._averaged_entry:.8f})",
                    metadata={"position_ids": [p["id"] for p in open_positions]},
                )

            # Check safety order trigger
            if (self._safety_orders_placed < MAX_SAFETY_ORDERS
                    and self._next_so_price > 0
                    and current_price <= self._next_so_price):
                self._safety_orders_placed += 1
                so = self._calc_next_safety_order(
                    open_positions[0]["entry_price"] if open_positions else current_price,
                    self._safety_orders_placed + 1,
                )
                self._next_so_price = so["price"]

                logger.info(
                    f"[dca] Safety order #{self._safety_orders_placed}: "
                    f"price={current_price}, next_SO={self._next_so_price:.8f}"
                )

                return Signal(
                    action="buy",
                    price=current_price,
                    quantity=so["quantity"],
                    sell_target=None,
                    stop_loss=None,
                    reason=f"DCA safety order #{self._safety_orders_placed} at {current_price:.8f}",
                    metadata={"dca_type": f"safety_order_{self._safety_orders_placed}"},
                )

            return Signal(
                action="hold", price=current_price,
                reason=f"DCA active: avg={self._averaged_entry:.8f}, "
                       f"TP={tp_price:.8f}, SL={sl_price:.8f}, "
                       f"SO={self._safety_orders_placed}/{MAX_SAFETY_ORDERS}, "
                       f"next_SO={self._next_so_price:.8f}"
                       + (f", RSI={rsi.value}" if rsi else ""),
            )

        return Signal(action="hold", price=current_price, reason="No conditions met")

    async def update_positions(
        self, symbol: str, current_price: float,
        klines: list[dict], positions: list[dict],
    ) -> list[dict]:
        # DCA manages positions through evaluate(), no trailing needed
        return []
