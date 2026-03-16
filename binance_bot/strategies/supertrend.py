"""Supertrend strategy with ADX trend filter.

Supertrend is an ATR-based trend indicator that provides clear
buy/sell signals with built-in stop loss levels.

Entry:
  1. Supertrend flips bullish (primary signal)
  2. Price pulls back to within 0.3% of Supertrend line in uptrend (secondary)
Exit: price crosses below Supertrend line or trailing stop
ADX filter: only trade when there IS a trend (opposite of grid strategy).
"""

import logging

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import (
    calc_supertrend, calc_adx, calc_atr, calc_rsi,
)

logger = logging.getLogger("binance_bot.strategy.supertrend")

# Supertrend parameters
ST_PERIOD = 10
ST_MULTIPLIER = 2.5  # Reduced from 3.0 — tighter bands, faster signals
ADX_THRESHOLD = 22   # Reduced from 25 — catch weaker trends too
RSI_OVERBOUGHT = 78  # Slightly relaxed from 75

# Pullback entry: buy when price is within this % of the Supertrend line
PULLBACK_PROXIMITY_PCT = 0.3


class SupertrendStrategy(BaseStrategy):
    name = "supertrend"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._last_flip_price: float = 0.0

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

        st = calc_supertrend(highs, lows, closes, ST_PERIOD, ST_MULTIPLIER)
        adx = calc_adx(highs, lows, closes)
        rsi = calc_rsi(closes, self.config.rsi_period)
        atr = calc_atr(highs, lows, closes)

        if not st:
            return Signal(action="hold", price=current_price, reason="Insufficient data for Supertrend")

        # PRIMARY BUY: Supertrend flipped bullish + ADX confirms trend
        if st.flipped and st.direction == "up":
            if adx and adx.adx < ADX_THRESHOLD:
                return Signal(
                    action="hold", price=current_price,
                    reason=f"Supertrend flipped UP but ADX={adx.adx:.1f} < {ADX_THRESHOLD} (weak trend)",
                )

            if rsi and rsi.value > RSI_OVERBOUGHT:
                return Signal(
                    action="hold", price=current_price,
                    reason=f"Supertrend flipped UP but RSI={rsi.value} overbought",
                )

            stop_loss = st.value
            risk = current_price - stop_loss
            sell_target = current_price + (3 * risk) if risk > 0 else current_price * 1.03

            self._last_flip_price = current_price

            logger.info(
                f"[supertrend] BUY signal (flip): price={current_price}, "
                f"ST={st.value:.8f}, ADX={adx.adx if adx else 'N/A'}"
            )

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=sell_target,
                stop_loss=stop_loss,
                reason=f"Supertrend flip UP: ST={st.value:.8f}"
                       + (f", ADX={adx.adx:.1f}" if adx else "")
                       + (f", RSI={rsi.value}" if rsi else ""),
            )

        # SECONDARY BUY: Pullback entry in established uptrend
        # Price pulled back close to the Supertrend line without crossing it
        if (st.direction == "up"
                and not open_positions
                and not st.flipped
                and adx and adx.adx >= ADX_THRESHOLD):

            proximity = ((current_price - st.value) / st.value) * 100 if st.value > 0 else 999
            rsi_ok = not rsi or rsi.value < RSI_OVERBOUGHT

            if 0 < proximity <= PULLBACK_PROXIMITY_PCT and rsi_ok:
                stop_loss = st.value * 0.998  # Slightly below ST line
                risk = current_price - stop_loss
                sell_target = current_price + (2.5 * risk) if risk > 0 else current_price * 1.025

                logger.info(
                    f"[supertrend] BUY signal (pullback): price={current_price}, "
                    f"ST={st.value:.8f}, proximity={proximity:.2f}%, ADX={adx.adx:.1f}"
                )

                return Signal(
                    action="buy",
                    price=current_price,
                    quantity=self.trading.buy_order_amount,
                    sell_target=sell_target,
                    stop_loss=stop_loss,
                    reason=f"Supertrend pullback entry: proximity={proximity:.2f}%"
                           + (f", ADX={adx.adx:.1f}" if adx else "")
                           + (f", RSI={rsi.value}" if rsi else ""),
                )

        # SELL: Supertrend flipped bearish — exit all positions
        if st.flipped and st.direction == "down" and open_positions:
            logger.info(
                f"[supertrend] SELL signal (flip DOWN): price={current_price}, "
                f"ST={st.value:.8f}"
            )
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Supertrend flip DOWN: ST={st.value:.8f}",
                metadata={"position_ids": [p["id"] for p in open_positions]},
            )

        # Check individual position exits (SL/TP)
        sellable = []
        for pos in open_positions:
            if st.direction == "down" and current_price < st.value:
                sellable.append(pos)
            elif pos.get("stop_loss") and current_price <= pos["stop_loss"]:
                sellable.append(pos)
            elif pos.get("sell_target") and current_price >= pos["sell_target"]:
                sellable.append(pos)

        if sellable:
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Supertrend exit: {len(sellable)} positions (ST={st.value:.8f}, dir={st.direction})",
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        status = f"ST={st.value:.8f} dir={st.direction}"
        if adx:
            status += f", ADX={adx.adx:.1f}"
        if rsi:
            status += f", RSI={rsi.value}"

        return Signal(action="hold", price=current_price, reason=status)

    async def update_positions(
        self, symbol: str, current_price: float,
        klines: list[dict], positions: list[dict],
    ) -> list[dict]:
        """Update stop loss to Supertrend line (trailing stop)."""
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]

        st = calc_supertrend(highs, lows, closes, ST_PERIOD, ST_MULTIPLIER)
        if not st or st.direction != "up":
            return []

        updates = []
        for pos in positions:
            # Trail stop loss up to Supertrend line (only move up, never down)
            current_sl = pos.get("stop_loss", 0) or 0
            if st.value > current_sl:
                updates.append({
                    "id": pos["id"],
                    "stop_loss": st.value,
                })
                logger.debug(f"[supertrend] Trailing SL for #{pos['id']}: {current_sl:.8f} -> {st.value:.8f}")

        return updates
