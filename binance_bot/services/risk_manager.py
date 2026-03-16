"""Risk management: position sizing, circuit breakers, portfolio limits."""

import logging
import time

from ..config import RiskConfig, TradingConfig
from ..database import Database

logger = logging.getLogger("binance_bot.risk")


class RiskManager:
    """Enforces risk limits and calculates position sizes."""

    def __init__(self, config: RiskConfig, trading_config: TradingConfig, db: Database):
        self.config = config
        self.trading = trading_config
        self.db = db
        self._daily_loss = 0.0
        self._daily_reset_time = 0.0
        self._circuit_breaker_until = 0.0

    async def can_open_position(
        self, symbol: str, price: float, available_balance: float
    ) -> dict:
        """Check if a new position can be opened. Returns approval or denial with reason."""
        # Circuit breaker check
        if time.time() < self._circuit_breaker_until:
            remaining = int(self._circuit_breaker_until - time.time())
            return {"allowed": False, "reason": f"Circuit breaker active ({remaining}s remaining)"}

        # Max open positions check
        open_positions = await self.db.get_open_positions(symbol)
        if len(open_positions) >= self.config.max_open_orders:
            return {"allowed": False, "reason": f"Max open orders reached ({self.config.max_open_orders})"}

        # Position size limit
        order_value = self.trading.buy_order_amount * price
        max_value = available_balance * (self.config.max_position_pct / 100)
        if order_value > max_value:
            return {
                "allowed": False,
                "reason": f"Order value {order_value:.2f} exceeds max {max_value:.2f} "
                          f"({self.config.max_position_pct}% of {available_balance:.2f})"
            }

        # Min order value check
        if order_value < self.trading.min_price_transaction:
            return {
                "allowed": False,
                "reason": f"Order value {order_value:.4f} below minimum {self.trading.min_price_transaction}"
            }

        # Portfolio stop loss check
        stats = await self.db.get_stats(symbol)
        initial_balance = await self.db.get_state(f"initial_balance:{symbol}", available_balance)
        if isinstance(initial_balance, (int, float)) and initial_balance > 0:
            total_loss_pct = (stats["total_profit"] / initial_balance) * 100
            if total_loss_pct <= -self.config.stop_loss_bot:
                self._trigger_circuit_breaker(300)  # 5 min cooldown (was 10min)
                return {
                    "allowed": False,
                    "reason": f"Portfolio stop loss triggered: {total_loss_pct:.2f}% loss "
                              f"(limit: {self.config.stop_loss_bot}%)"
                }

        return {"allowed": True, "reason": "OK"}

    async def check_portfolio_limits(
        self, symbol: str, current_price: float, available_balance: float
    ) -> dict | None:
        """Check if portfolio-level TP/SL has been hit. Returns action if triggered."""
        initial_balance = await self.db.get_state(f"initial_balance:{symbol}", None)
        if initial_balance is None:
            return None

        # Get current portfolio value
        positions = await self.db.get_open_positions(symbol)
        total_qty = sum(p["quantity"] for p in positions)
        position_value = total_qty * current_price

        realized = await self.db.get_total_profit(symbol)
        total_pnl = position_value - sum(p["entry_price"] * p["quantity"] for p in positions) + realized
        total_pnl_pct = (total_pnl / float(initial_balance)) * 100

        # Take profit
        if self.config.take_profit_bot > 0 and total_pnl_pct >= self.config.take_profit_bot:
            return {
                "action": "take_profit",
                "pnl": round(total_pnl, 4),
                "pnl_pct": round(total_pnl_pct, 2),
                "message": f"Portfolio take profit: +{total_pnl_pct:.2f}% (target: {self.config.take_profit_bot}%)",
            }

        # Stop loss
        if self.config.stop_loss_bot > 0 and total_pnl_pct <= -self.config.stop_loss_bot:
            return {
                "action": "stop_loss",
                "pnl": round(total_pnl, 4),
                "pnl_pct": round(total_pnl_pct, 2),
                "message": f"Portfolio stop loss: {total_pnl_pct:.2f}% (limit: -{self.config.stop_loss_bot}%)",
            }

        return None

    def calculate_position_size(
        self, available_balance: float, price: float,
        atr: float | None = None, win_rate: float | None = None,
    ) -> float:
        """Calculate position size. Uses fixed amount from config, bounded by risk limits."""
        # Start with configured amount
        qty = self.trading.buy_order_amount

        # Cap at max position percentage
        max_value = available_balance * (self.config.max_position_pct / 100)
        max_qty = max_value / price if price > 0 else qty
        qty = min(qty, max_qty)

        # ATR-based adjustment: reduce size in high volatility
        if atr and price > 0:
            atr_pct = (atr / price) * 100
            if atr_pct > 5:  # Very high volatility
                qty *= 0.5
            elif atr_pct > 3:  # High volatility
                qty *= 0.7

        return qty

    def calculate_stop_loss(
        self, entry_price: float, stop_loss_pct: float, atr: float | None = None
    ) -> float:
        """Calculate stop loss price."""
        if atr:
            # ATR-based: 2x ATR below entry
            sl = entry_price - (2 * atr)
            # But don't exceed max stop loss percentage
            max_sl = entry_price * (1 - stop_loss_pct / 100)
            return max(sl, max_sl)
        return entry_price * (1 - stop_loss_pct / 100)

    def calculate_take_profit(
        self, entry_price: float, take_profit_pct: float
    ) -> float:
        """Calculate take profit price."""
        return entry_price * (1 + take_profit_pct / 100)

    def _trigger_circuit_breaker(self, seconds: int):
        self._circuit_breaker_until = time.time() + seconds
        logger.warning(f"Circuit breaker triggered for {seconds}s")

    def reset_daily(self):
        """Reset daily tracking counters."""
        self._daily_loss = 0.0
        self._daily_reset_time = time.time()
