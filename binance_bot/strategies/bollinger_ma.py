"""Bollinger Bands + MA trailing strategy.

Entry: same as Bollinger (price below lower band)
Exit: MA trailing stop, hard stop loss, or middle band cross
Trailing: once price crosses middle band, tracks with 0.2% increments
"""

import logging
import time

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import calc_bollinger, calc_rsi

logger = logging.getLogger("binance_bot.strategy.bollinger_ma")


class BollingerMAStrategy(BaseStrategy):
    name = "bollinger_ma"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._sl_cooldown_until: float = 0

    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        closes = [k["close"] for k in klines]

        bb = calc_bollinger(closes, period=self.config.bollinger_period)
        if not bb:
            return Signal(action="hold", price=current_price, reason="Insufficient data")

        rsi = None
        if self.config.apply_rsi:
            rsi = calc_rsi(closes, period=self.config.rsi_period)

        # Check stop loss cooldown
        if time.time() < self._sl_cooldown_until:
            remaining = int(self._sl_cooldown_until - time.time())
            return Signal(
                action="hold", price=current_price,
                reason=f"Stop loss cooldown ({remaining}s remaining)",
            )

        # BUY: price below lower band
        buy_target = bb.lower - (bb.lower * self.config.bollinger_percent_buy / 100)

        if current_price < bb.lower and current_price <= buy_target:
            if rsi and self.config.apply_rsi and rsi.value > self.config.rsi_support:
                return Signal(
                    action="hold", price=current_price,
                    reason=f"Below BB but RSI {rsi.value} > {self.config.rsi_support}",
                )

            # Hard stop loss
            stop_loss = current_price * (1 - self.config.bollinger_stop_loss / 100)

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=None,  # No fixed target, MA trailing handles exit
                stop_loss=stop_loss,
                reason=f"Price {current_price:.8f} < BB lower {bb.lower:.8f}",
                metadata={"ma_check": None},  # Will be set when price crosses middle
            )

        # SELL checks for open positions
        sellable = []
        for pos in open_positions:
            sell_reason = self._check_sell_conditions(pos, current_price, bb)
            if sell_reason:
                sellable.append(pos)
                if sell_reason == "hard_stop_loss" or sell_reason == "ma_stop_loss":
                    self._sl_cooldown_until = time.time() + (self.config.ma_cooldown_minutes * 60)
                    logger.info(f"Stop loss cooldown activated: {self.config.ma_cooldown_minutes}min")

        if sellable:
            return Signal(
                action="sell",
                price=current_price,
                reason=f"{len(sellable)} positions triggered for exit",
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        return Signal(
            action="hold", price=current_price,
            reason=f"BB: L={bb.lower:.8f} M={bb.middle:.8f} U={bb.upper:.8f}",
        )

    def _check_sell_conditions(
        self, position: dict, current_price: float, bb
    ) -> str | None:
        """Check all exit conditions for a position. Returns reason or None."""
        import json

        metadata = position.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        ma_check = metadata.get("ma_check") or position.get("ma_check")

        # 1. Hard stop loss
        if position.get("stop_loss") and current_price <= position["stop_loss"]:
            return "hard_stop_loss"

        # 2. MA stop loss (if ma_check is set and MA SL configured)
        if ma_check and self.config.bollinger_ma_stop_loss > 0:
            ma_sl = ma_check * (1 - self.config.bollinger_ma_stop_loss / 100)
            if current_price <= ma_sl:
                return "ma_stop_loss"

        # 3. MA below middle band (trailing exit)
        if ma_check and ma_check <= bb.middle:
            return "ma_trailing_exit"

        return None

    async def update_positions(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        positions: list[dict],
    ) -> list[dict]:
        """Update MA trailing checks for open positions."""
        closes = [k["close"] for k in klines]
        bb = calc_bollinger(closes, period=self.config.bollinger_period)
        if not bb:
            return []

        updates = []
        for pos in positions:
            import json
            metadata = pos.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            ma_check = metadata.get("ma_check") or pos.get("ma_check")

            # Initialize ma_check when price crosses above middle band
            if ma_check is None and current_price > bb.middle:
                ma_check = current_price
                metadata["ma_check"] = ma_check
                updates.append({
                    "id": pos["id"],
                    "ma_check": ma_check,
                    "metadata": json.dumps(metadata),
                })
                logger.info(f"MA check initialized for position {pos['id']}: {ma_check}")

            # Increment ma_check by 0.2% trailing
            elif ma_check and current_price > ma_check:
                increment = ma_check * (self.config.ma_trailing_increment / 100)
                new_ma = ma_check + increment
                if current_price > new_ma:
                    metadata["ma_check"] = current_price
                    updates.append({
                        "id": pos["id"],
                        "ma_check": current_price,
                        "metadata": json.dumps(metadata),
                    })
                    logger.debug(f"MA check updated for position {pos['id']}: {ma_check} -> {current_price}")

        return updates
