"""EMA Crossover strategy - new addition.

Entry: fast EMA crosses above slow EMA (golden cross) with trend confirmation
Exit: fast EMA crosses below slow EMA (death cross) or stop loss
Uses EMA 9/21 for signals, EMA 50 for trend filter.
"""

import logging

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import ema, calc_rsi, calc_atr

logger = logging.getLogger("binance_bot.strategy.ema_crossover")


class EMACrossoverStrategy(BaseStrategy):
    name = "ema_crossover"

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

        # Calculate EMAs
        fast_ema = ema(closes, self.config.ema_fast)
        slow_ema = ema(closes, self.config.ema_slow)
        trend_ema = ema(closes, self.config.ema_trend)

        if len(fast_ema) < 3 or len(slow_ema) < 3 or not trend_ema:
            return Signal(action="hold", price=current_price, reason="Insufficient data for EMAs")

        # Current and previous values
        fast_now = fast_ema[-1]
        fast_prev = fast_ema[-2]
        slow_now = slow_ema[-1]
        slow_prev = slow_ema[-2]
        trend_now = trend_ema[-1]

        # Detect crossover
        golden_cross = fast_prev <= slow_prev and fast_now > slow_now
        death_cross = fast_prev >= slow_prev and fast_now < slow_now

        # Trend filter: only trade in direction of trend
        uptrend = current_price > trend_now

        # RSI for confirmation
        rsi = calc_rsi(closes, self.config.rsi_period)
        atr = calc_atr(highs, lows, closes)

        # BUY: golden cross in uptrend
        if golden_cross and uptrend:
            if rsi and rsi.value > 75:
                return Signal(
                    action="hold", price=current_price,
                    reason=f"Golden cross but RSI overbought ({rsi.value})",
                )

            # ATR-based stop loss (2x ATR)
            stop_loss = current_price - (2 * atr) if atr else current_price * 0.97
            # Take profit at 3x risk (3:1 R:R)
            risk = current_price - stop_loss
            sell_target = current_price + (3 * risk)

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=sell_target,
                stop_loss=stop_loss,
                reason=f"Golden cross: EMA{self.config.ema_fast}={fast_now:.8f} > "
                       f"EMA{self.config.ema_slow}={slow_now:.8f}, trend UP"
                       + (f", RSI={rsi.value}" if rsi else "")
                       + (f", ATR={atr}" if atr else ""),
            )

        # SELL: death cross or stop loss
        if death_cross and open_positions:
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Death cross: EMA{self.config.ema_fast} < EMA{self.config.ema_slow}",
                metadata={"position_ids": [p["id"] for p in open_positions]},
            )

        # Check individual position exits
        sellable = [
            p for p in open_positions
            if (p.get("sell_target") and current_price >= p["sell_target"])
            or (p.get("stop_loss") and current_price <= p["stop_loss"])
        ]
        if sellable:
            return Signal(
                action="sell",
                price=current_price,
                reason=f"{len(sellable)} positions hit TP/SL",
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        spread = ((fast_now - slow_now) / slow_now) * 100 if slow_now else 0
        return Signal(
            action="hold", price=current_price,
            reason=f"EMA{self.config.ema_fast}={fast_now:.8f} "
                   f"EMA{self.config.ema_slow}={slow_now:.8f} "
                   f"spread={spread:.3f}%"
                   + (f", RSI={rsi.value}" if rsi else ""),
        )

    async def update_positions(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        positions: list[dict],
    ) -> list[dict]:
        # EMA crossover uses fixed TP/SL, no trailing
        return []
