"""Trading strategies."""

from .base import BaseStrategy
from .price_action import PriceActionStrategy
from .bollinger import BollingerStrategy
from .bollinger_ma import BollingerMAStrategy
from .ema_crossover import EMACrossoverStrategy
from .grid import GridStrategy
from .smart_dca import SmartDCAStrategy
from .supertrend import SupertrendStrategy
from .composite import CompositeStrategy

STRATEGIES = {
    "price_action": PriceActionStrategy,
    "bollinger": BollingerStrategy,
    "bollinger_ma": BollingerMAStrategy,
    "ema_crossover": EMACrossoverStrategy,
    "grid": GridStrategy,
    "smart_dca": SmartDCAStrategy,
    "supertrend": SupertrendStrategy,
    "composite": CompositeStrategy,
}

__all__ = [
    "BaseStrategy",
    "PriceActionStrategy",
    "BollingerStrategy",
    "BollingerMAStrategy",
    "EMACrossoverStrategy",
    "GridStrategy",
    "SmartDCAStrategy",
    "SupertrendStrategy",
    "CompositeStrategy",
    "STRATEGIES",
]
