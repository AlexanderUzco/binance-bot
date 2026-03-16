"""Price action strategy - original base strategy from TS bot.

Entry: price drops by PRICE_PERCENT from start_price
Exit: price rises by PRICE_PERCENT, sells positions where price >= sell_target
"""

import logging

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig

logger = logging.getLogger("binance_bot.strategy.price_action")


class PriceActionStrategy(BaseStrategy):
    name = "price_action"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._start_price: float | None = None

    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        # Initialize start price
        if self._start_price is None:
            self._start_price = current_price
            logger.info(f"[{self.name}] Start price set: {current_price}")
            return Signal(action="hold", price=current_price, reason="initializing")

        # Calculate percentage change from start price
        if self._start_price == 0:
            return Signal(action="hold", price=current_price, reason="start_price is zero")

        pct_change = ((current_price - self._start_price) / self._start_price) * 100

        # BUY: price dropped by PRICE_PERCENT
        if current_price < self._start_price and abs(pct_change) >= self.config.price_percent:
            sell_target = current_price * (1 + self.config.price_percent / 100)
            stop_loss = current_price * (1 - self.config.bollinger_stop_loss / 100) if self.config.bollinger_stop_loss > 0 else None

            # Reset start price after buy
            self._start_price = current_price

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=sell_target,
                stop_loss=stop_loss,
                reason=f"Price dropped {pct_change:.2f}% from {self._start_price:.8f}",
            )

        # SELL: check positions where current price >= sell_target
        sellable = [p for p in open_positions if p.get("sell_target") and current_price >= p["sell_target"]]
        if sellable:
            self._start_price = current_price
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Price rose to target, {len(sellable)} positions to close",
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        return Signal(action="hold", price=current_price, reason=f"Change: {pct_change:.2f}%")

    async def update_positions(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        positions: list[dict],
    ) -> list[dict]:
        # Price action doesn't use trailing - positions have fixed targets
        return []
