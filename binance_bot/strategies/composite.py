"""Composite strategy: auto-switches between strategies based on market regime.

- Ranging market (ADX < threshold)  ->  Grid Trading
- Volatile drop (RSI < 40 + below BB)  ->  Smart DCA
- Trending up (ADX > threshold, +DI > -DI)  ->  Supertrend
- Trending down (ADX > threshold, -DI > +DI)  ->  Smart DCA (buy dips)

Each sub-strategy manages its own positions. The composite engine routes
new signals to the appropriate strategy but lets existing positions be
managed by whatever strategy opened them.
"""

import logging

from .base import BaseStrategy, Signal
from .grid import GridStrategy
from .smart_dca import SmartDCAStrategy
from .supertrend import SupertrendStrategy
from ..config import StrategyConfig, TradingConfig
from ..services.indicators import detect_regime

logger = logging.getLogger("binance_bot.strategy.composite")

# Minimum candles a regime must persist before acting on regime-shift protection
_REGIME_STABILITY_CANDLES = 3


class CompositeStrategy(BaseStrategy):
    name = "composite"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        super().__init__(strategy_config, trading_config)
        self._grid = GridStrategy(strategy_config, trading_config)
        self._dca = SmartDCAStrategy(strategy_config, trading_config)
        self._supertrend = SupertrendStrategy(strategy_config, trading_config)
        self._current_regime = "unknown"
        self._regime_candle_count = 0
        self._active_strategy: BaseStrategy | None = None

    def _select_strategy(self, regime: str) -> BaseStrategy | None:
        """Select strategy based on market regime."""
        if regime == "ranging":
            return self._grid
        elif regime == "volatile_drop":
            return self._dca
        elif regime == "trending_up":
            return self._supertrend
        elif regime == "trending_down":
            # In downtrend on spot: use DCA to buy dips (instead of doing nothing)
            return self._dca
        return None

    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        # Detect regime
        regime = detect_regime(klines)
        if not regime:
            return Signal(action="hold", price=current_price, reason="Insufficient data for regime detection")

        # Track regime stability
        if regime.regime != self._current_regime:
            selected = self._select_strategy(regime.regime)
            strat_label = selected.name if selected else "none"
            logger.info(
                f"[composite] Regime change: {self._current_regime} -> {regime.regime} "
                f"(ADX={regime.adx.adx if regime.adx else 'N/A'}, conf={regime.confidence}) "
                f"| strategy={strat_label}, open_positions={len(open_positions)}"
            )
            self._current_regime = regime.regime
            self._regime_candle_count = 0
        else:
            self._regime_candle_count += 1

        # Select strategy for new entries
        strategy = self._select_strategy(regime.regime)

        # If positions are open, let their original strategy manage exits
        # Group positions by strategy
        positions_by_strategy: dict[str, list[dict]] = {}
        for pos in open_positions:
            strat_name = pos.get("strategy", "unknown")
            positions_by_strategy.setdefault(strat_name, []).append(pos)

        # Regime shift protection for grid: only close if regime has been
        # stable for N candles AND positions are in loss.
        # This prevents force-closing on brief ADX spikes.
        if (regime.regime == "trending_down"
                and positions_by_strategy.get("grid")
                and self._regime_candle_count >= _REGIME_STABILITY_CANDLES):
            grid_positions = positions_by_strategy["grid"]
            # Only force-close grid positions that are in loss
            losing_positions = [
                p for p in grid_positions
                if current_price < p.get("entry_price", current_price)
            ]
            if losing_positions:
                logger.warning(
                    f"[composite] Stable trending_down ({self._regime_candle_count} candles): "
                    f"closing {len(losing_positions)} losing grid positions"
                )
                return Signal(
                    action="sell",
                    price=current_price,
                    reason=f"[grid] Regime shift protection: closing {len(losing_positions)} losing positions",
                    metadata={
                        "position_ids": [p["id"] for p in losing_positions],
                        "source_strategy": "grid",
                        "close_reason": "regime_shift",
                    },
                )

        # Check exits for ALL open positions (regardless of current regime)
        for strat_name, positions in positions_by_strategy.items():
            mgr = self._get_strategy_by_name(strat_name)
            if mgr:
                sig = await mgr.evaluate(symbol, current_price, klines, positions)
                if sig.action == "sell":
                    sig.reason = f"[{strat_name}] {sig.reason}"
                    return sig

        # No exits triggered — evaluate current strategy for new entry
        if strategy is None:
            return Signal(
                action="hold", price=current_price,
                reason=f"Regime: {regime.regime} (no strategy active)"
                       + (f", ADX={regime.adx.adx}" if regime.adx else ""),
            )

        # Only pass positions that belong to the current strategy
        own_positions = positions_by_strategy.get(strategy.name, [])
        sig = await strategy.evaluate(symbol, current_price, klines, own_positions)

        # Tag signal with strategy name for position tracking
        if sig.action != "hold":
            sig.reason = f"[{strategy.name}] {sig.reason}"
            sig.metadata = sig.metadata or {}
            sig.metadata["source_strategy"] = strategy.name

        return sig

    async def update_positions(
        self, symbol: str, current_price: float,
        klines: list[dict], positions: list[dict],
    ) -> list[dict]:
        """Update trailing data for all open positions."""
        all_updates = []

        # Group by strategy and delegate
        positions_by_strategy: dict[str, list[dict]] = {}
        for pos in positions:
            strat_name = pos.get("strategy", "unknown")
            positions_by_strategy.setdefault(strat_name, []).append(pos)

        for strat_name, strat_positions in positions_by_strategy.items():
            mgr = self._get_strategy_by_name(strat_name)
            if mgr:
                updates = await mgr.update_positions(
                    symbol, current_price, klines, strat_positions
                )
                all_updates.extend(updates)

        return all_updates

    def _get_strategy_by_name(self, name: str) -> BaseStrategy | None:
        mapping = {
            "grid": self._grid,
            "smart_dca": self._dca,
            "supertrend": self._supertrend,
        }
        return mapping.get(name)
