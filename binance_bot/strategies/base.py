"""Base strategy abstract class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..config import StrategyConfig, TradingConfig


@dataclass
class Signal:
    action: str  # "buy", "sell", "hold"
    price: float
    quantity: float | None = None
    sell_target: float | None = None
    stop_loss: float | None = None
    reason: str = ""
    metadata: dict | None = None


class BaseStrategy(ABC):
    """Abstract base for all trading strategies."""

    name: str = "base"

    def __init__(self, strategy_config: StrategyConfig, trading_config: TradingConfig):
        self.config = strategy_config
        self.trading = trading_config
        self._state: dict[str, Any] = {}

    @abstractmethod
    async def evaluate(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        open_positions: list[dict],
    ) -> Signal:
        """Evaluate market conditions and return a trading signal.

        Args:
            symbol: Trading pair (e.g. BONKUSDT)
            current_price: Current market price
            klines: Recent candlestick data
            open_positions: Currently open positions for this symbol

        Returns:
            Signal with action (buy/sell/hold), price, and optional targets
        """
        ...

    @abstractmethod
    async def update_positions(
        self,
        symbol: str,
        current_price: float,
        klines: list[dict],
        positions: list[dict],
    ) -> list[dict]:
        """Update trailing stops, MA checks, etc. for open positions.

        Returns list of position updates: [{"id": pos_id, "field": value, ...}]
        """
        ...

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any):
        self._state[key] = value
