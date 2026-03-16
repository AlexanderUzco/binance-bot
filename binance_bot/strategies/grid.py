"""Grid Trading strategy.

Places buy and sell orders at regular intervals within a price range.
Each completed buy-sell cycle captures the grid spacing as profit.

Uses geometric grid (% spacing) for better performance across price levels.
ADX filter: only active when market is ranging (ADX < 25).
Dynamic range: adjusts grid boundaries based on ATR.
"""

import json
import logging
import math

from .base import BaseStrategy, Signal
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import (
    calc_adx, calc_atr, calc_bollinger, calc_rsi,
)

logger = logging.getLogger("binance_bot.strategy.grid")


# Grid config defaults (can be overridden via StrategyConfig)
GRID_LEVELS = 10  # Number of grid lines
GRID_SPACING_PCT = 0.5  # % between each grid level (geometric)
ADX_THRESHOLD = 30  # Only pause grid when ADX > this (was 25 — allow weak trends)
REBALANCE_THRESHOLD = 0.7  # Rebalance grid when price uses 70% of range
GRID_STOP_LOSS_MULT = 3  # SL = N x grid spacing (e.g. 0.5% spacing → 1.5% SL)


class GridStrategy(BaseStrategy):
    name = "grid"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._grid_levels: list[float] = []
        self._grid_center: float = 0
        self._current_spacing: float = 0.0
        self._initialized = False
        self._paused_reason: str = ""

    def _build_grid(self, center_price: float, atr: float | None, num_levels: int = GRID_LEVELS) -> list[float]:
        """Build geometric grid levels around center price."""
        spacing_pct = getattr(self.config, 'grid_spacing_pct', GRID_SPACING_PCT) / 100

        # If ATR available, use it to determine spacing
        if atr and center_price > 0:
            atr_pct = atr / center_price
            # Spacing = max of configured spacing or 1.5x ATR%
            spacing_pct = max(spacing_pct, atr_pct * 1.5)

        self._current_spacing = spacing_pct

        levels = []
        half = num_levels // 2

        for i in range(-half, half + 1):
            level = center_price * (1 + spacing_pct) ** i
            levels.append(round(level, 8))

        return sorted(levels)

    def _find_grid_position(self, price: float) -> int:
        """Find which grid level the price is closest to (below)."""
        for i, level in enumerate(self._grid_levels):
            if price < level:
                return i - 1
        return len(self._grid_levels) - 1

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

        # ADX filter: only trade in ranging market
        adx = calc_adx(highs, lows, closes)
        if adx and adx.adx > ADX_THRESHOLD:
            if not self._paused_reason:
                self._paused_reason = f"ADX={adx.adx:.1f} > {ADX_THRESHOLD}"
                logger.info(f"[grid] Paused: {self._paused_reason}")
            return Signal(
                action="hold", price=current_price,
                reason=f"Grid paused: ADX {adx.adx:.1f} (trending market)",
            )
        self._paused_reason = ""

        atr = calc_atr(highs, lows, closes)

        # Initialize grid on first run
        if not self._initialized:
            self._grid_center = current_price
            self._grid_levels = self._build_grid(current_price, atr)
            self._initialized = True
            await self._save_grid_state()
            sl_pct = self._current_spacing * GRID_STOP_LOSS_MULT * 100
            logger.info(
                f"[grid] Initialized: center={current_price}, "
                f"levels={len(self._grid_levels)}, "
                f"range=[{self._grid_levels[0]:.8f} - {self._grid_levels[-1]:.8f}], "
                f"spacing={self._current_spacing*100:.2f}%, SL={sl_pct:.2f}% (x{GRID_STOP_LOSS_MULT})"
            )
            return Signal(action="hold", price=current_price, reason="Grid initialized")

        # Check if price is outside grid range — rebalance and look for entry
        if (current_price < self._grid_levels[0] or
                current_price > self._grid_levels[-1]):
            old_bottom = self._grid_levels[0] if self._grid_levels else 0
            self._grid_center = current_price
            self._grid_levels = self._build_grid(current_price, atr)
            await self._save_grid_state()
            sl_pct = self._current_spacing * GRID_STOP_LOSS_MULT * 100
            logger.info(
                f"[grid] Rebalanced: center={current_price}, "
                f"range=[{self._grid_levels[0]:.8f} - {self._grid_levels[-1]:.8f}], "
                f"spacing={self._current_spacing*100:.2f}%, SL={sl_pct:.2f}%"
            )
            # If price re-entered from below (bouncing), trigger a buy at the new grid bottom
            if current_price < self._grid_center and old_bottom > 0 and current_price > old_bottom:
                grid_pos = self._find_grid_position(current_price)
                self.set_state("last_grid_pos", grid_pos)
                sell_target = self._grid_levels[grid_pos + 1] if grid_pos + 1 < len(self._grid_levels) else current_price * 1.005
                stop_loss = current_price * (1 - self._current_spacing * GRID_STOP_LOSS_MULT)
                return Signal(
                    action="buy",
                    price=current_price,
                    quantity=self.trading.buy_order_amount,
                    sell_target=sell_target,
                    stop_loss=stop_loss,
                    reason=f"Grid buy on rebalance: price bounced into new grid at level {grid_pos}",
                    metadata={"grid_level": grid_pos, "grid_buy_level": current_price},
                )
            return Signal(action="hold", price=current_price, reason="Grid rebalanced")

        grid_pos = self._find_grid_position(current_price)
        prev_pos = self.get_state("last_grid_pos", grid_pos)

        # Price crossed DOWN through a grid level → BUY
        if grid_pos < prev_pos:
            self.set_state("last_grid_pos", grid_pos)
            buy_level = self._grid_levels[grid_pos] if grid_pos >= 0 else self._grid_levels[0]
            sell_target = self._grid_levels[grid_pos + 1] if grid_pos + 1 < len(self._grid_levels) else buy_level * 1.005

            stop_loss = current_price * (1 - self._current_spacing * GRID_STOP_LOSS_MULT)

            return Signal(
                action="buy",
                price=current_price,
                quantity=self.trading.buy_order_amount,
                sell_target=sell_target,
                stop_loss=stop_loss,
                reason=f"Grid buy: price crossed below level {grid_pos} ({buy_level:.8f}), SL={stop_loss:.8f}",
                metadata={"grid_level": grid_pos, "grid_buy_level": buy_level},
            )

        # Check positions for SELL: price crossed UP through sell target
        sellable = []
        for pos in open_positions:
            if pos.get("sell_target") and current_price >= pos["sell_target"]:
                sellable.append(pos)

        if sellable:
            self.set_state("last_grid_pos", grid_pos)
            return Signal(
                action="sell",
                price=current_price,
                reason=f"Grid sell: {len(sellable)} positions hit target",
                metadata={"position_ids": [p["id"] for p in sellable]},
            )

        self.set_state("last_grid_pos", grid_pos)
        return Signal(
            action="hold", price=current_price,
            reason=f"Grid pos={grid_pos}/{len(self._grid_levels)}, "
                   f"range=[{self._grid_levels[0]:.8f}-{self._grid_levels[-1]:.8f}]"
                   + (f", ADX={adx.adx:.1f}" if adx else ""),
        )

    async def update_positions(
        self, symbol: str, current_price: float,
        klines: list[dict], positions: list[dict],
    ) -> list[dict]:
        return []

    async def _save_grid_state(self):
        """Save grid state for recovery."""
        self.set_state("grid_levels", self._grid_levels)
        self.set_state("grid_center", self._grid_center)
