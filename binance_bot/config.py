"""Configuration loading from .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class BinanceConfig:
    api_key: str
    api_secret: str
    testnet: bool = False

    @property
    def base_url(self) -> str:
        if self.testnet:
            return "https://testnet.binance.vision"
        return "https://api.binance.com"

    @property
    def ws_url(self) -> str:
        if self.testnet:
            return "wss://testnet.binance.vision/ws"
        return "wss://stream.binance.com:9443/ws"

    @property
    def ws_available(self) -> bool:
        # Binance testnet does not support WebSocket streams
        return not self.testnet


@dataclass
class TradingConfig:
    market1: str = "BONK"
    market2: str = "USDT"
    buy_order_amount: float = 50000
    min_price_transaction: float = 1.0
    sleep_time: int = 2000  # ms
    sell_all_on_start: bool = False
    sell_all_on_close: bool = False

    @property
    def symbol(self) -> str:
        return f"{self.market1}{self.market2}"


@dataclass
class StrategyConfig:
    # Base strategy
    price_percent: float = 0.5

    # Bollinger Bands
    bollinger_period: int = 20
    bollinger_percent_buy: float = 0.1
    bollinger_percent_sell: float = 0.5
    bollinger_stop_loss: float = 0.2

    # Bollinger MA
    bollinger_ma_stop_loss: float = 0.2
    ma_trailing_increment: float = 0.2  # %
    ma_cooldown_minutes: int = 10

    # RSI
    apply_rsi: bool = True
    rsi_period: int = 14
    rsi_support: float = 30.0
    rsi_resistance: float = 70.0

    # EMA Crossover
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50


@dataclass
class RiskConfig:
    stop_loss_bot: float = 10.0  # % total portfolio loss to shut down (was 3%)
    take_profit_bot: float = 10.0  # % total portfolio gain to shut down (was 3%)
    max_open_orders: int = 15  # increased from 10 — DCA needs multiple positions
    max_position_pct: float = 30.0  # max % of portfolio per position


@dataclass
class NotificationConfig:
    email_enabled: bool = False
    email_to: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class AppConfig:
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    db_path: Path = field(default_factory=lambda: Path("./data/bot.db"))


def load_config(env_path: str | None = None) -> AppConfig:
    """Load configuration from .env file."""
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    binance = BinanceConfig(
        api_key=os.getenv("APIKEY", ""),
        api_secret=os.getenv("SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "false").lower() == "true",
    )

    trading = TradingConfig(
        market1=os.getenv("MARKET1", "BONK"),
        market2=os.getenv("MARKET2", "USDT"),
        buy_order_amount=float(os.getenv("BUY_ORDER_AMOUNT", "50000")),
        min_price_transaction=float(os.getenv("MIN_PRICE_TRANSACTION", "1")),
        sleep_time=int(os.getenv("SLEEP_TIME", "2000")),
        sell_all_on_start=os.getenv("SELL_ALL_ON_START", "false").lower() == "true",
        sell_all_on_close=os.getenv("SELL_ALL_ON_CLOSE", "false").lower() == "true",
    )

    strategy = StrategyConfig(
        price_percent=float(os.getenv("PRICE_PERCENT", "0.5")),
        bollinger_percent_buy=float(os.getenv("BOLLINGER_BANDS_PERCENT_BUY", "0")),
        bollinger_percent_sell=float(os.getenv("BOLLINGER_BANDS_PERCENT_SELL", "0.5")),
        bollinger_stop_loss=float(os.getenv("BOLLINGER_BANDS_STOP_LOSS_ORDER", "0")),
        bollinger_ma_stop_loss=float(os.getenv("BOLLIINGER_MA_STOP_LOSS", "0")),
        apply_rsi=os.getenv("APPLY_RSI", "false").lower() == "true",
        rsi_support=float(os.getenv("RSI_SUPPORT", "30")),
        rsi_resistance=float(os.getenv("RSI_RESISTANCE", "70")),
    )

    risk = RiskConfig(
        stop_loss_bot=float(os.getenv("STOP_LOSS_BOT", "3")),
        take_profit_bot=float(os.getenv("TAKE_PROFIT_BOT", "3")),
        max_open_orders=int(os.getenv("MAX_OPEN_ORDERS", "10")),
        max_position_pct=float(os.getenv("MAX_POSITION_PCT", "30")),
    )

    notification = NotificationConfig(
        email_enabled=os.getenv("EMAIL_ENABLED", "false").lower() == "true",
        email_to=os.getenv("EMAIL_TO", ""),
        telegram_enabled=bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        binance=binance,
        trading=trading,
        strategy=strategy,
        risk=risk,
        notification=notification,
        data_dir=data_dir,
        db_path=data_dir / "bot.db",
    )
