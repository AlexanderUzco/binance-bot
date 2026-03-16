"""Bollinger Bands strategy with optional RSI filter.

Entry: price below lower band (adjusted by PERCENT_BUY)
Exit: price above lower band (adjusted by PERCENT_SELL)
RSI filter: skip buy if RSI > support, skip sell if RSI < resistance
"""

import logging

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import calc_bollinger, calc_rsi

logger = logging.getLogger("binance_bot.strategy.bollinger")


class BollingerStrategy(BaseStrategy):
    name = "bollinger"

    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        closes = [k["close"] for k in klines]

        # Calculate Bollinger Bands
        bb = calc_bollinger(closes, period=self.config.bollinger_period)
        if not bb:
            return Signal(action="hold", price=current_price, reason="Insufficient data for Bollinger")

        # Calculate RSI if enabled
        rsi = None
        if self.config.apply_rsi:
            rsi = calc_rsi(closes, period=self.config.rsi_period)

        # Buy target: lower band adjusted by percent_buy
        buy_target = bb.lower - (bb.lower * self.config.bollinger_percent_buy / 100)

        # BUY condition: price below lower band and below buy target
        if current_price < bb.lower and current_price <= buy_target:
            # RSI filter: skip if RSI too high (not oversold enough)
            if rsi and self.config.apply_rsi and rsi.value > self.config.rsi_support:
                return Signal(
                    action="hold", price=current_price,
                    reason=f"Below BB lower but RSI {rsi.value} > support {self.config.rsi_support}",
                )

            # Calculate sell target
            sell_target = bb.lower + (bb.lower * self.config.bollinger_percent_sell / 100)
            stop_loss = None
            if self.config.bollinger_stop_loss > 0:
                stop_loss = current_price * (1 - self.config.bollinger_stop_loss / 100)

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=sell_target,
                stop_loss=stop_loss,
                reason=f"Price {current_price:.8f} < BB lower {bb.lower:.8f}"
                       + (f", RSI {rsi.value}" if rsi else ""),
            )

        # SELL condition: check open positions
        sellable = []
        for pos in open_positions:
            if not pos.get("sell_target"):
                continue

            if current_price > pos["sell_target"]:
                # RSI filter: skip if RSI too low (still has upside)
                if rsi and self.config.apply_rsi and rsi.value < self.config.rsi_resistance:
                    continue
                sellable.append(pos)

        if sellable:
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Price above sell target, {len(sellable)} positions"
                       + (f", RSI {rsi.value}" if rsi else ""),
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        return Signal(
            action="hold", price=current_price,
            reason=f"BB: lower={bb.lower:.8f} mid={bb.middle:.8f} upper={bb.upper:.8f}"
                   + (f", RSI={rsi.value}" if rsi else ""),
        )

    async def update_positions(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        positions: list[dict],
    ) -> list[dict]:
        # Standard bollinger doesn't use trailing - fixed targets
        return []
