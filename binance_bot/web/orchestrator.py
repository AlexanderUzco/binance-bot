"""PairOrchestrator — manages N TradingEngine instances as asyncio tasks."""

import asyncio
import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..config import AppConfig
from ..database import Database
from ..services.binance_client import BinanceClient
from ..strategies import STRATEGIES

logger = logging.getLogger("binance_bot.orchestrator")


@dataclass
class PairState:
    symbol: str
    config: AppConfig
    engine: Any = None
    task: asyncio.Task | None = None
    status: str = "stopped"  # stopped | running | error
    error: str | None = None
    started_at: float | None = None


class PairOrchestrator:
    """Spawn and manage multiple TradingEngine instances sharing one client and DB."""

    def __init__(self, base_config: AppConfig, db: Database, client: BinanceClient, pairs_config: list[dict]):
        self.base_config = base_config
        self.db = db
        self.client = client
        self.pairs: dict[str, PairState] = {}

        for pair in pairs_config:
            symbol = f"{pair['market1']}{pair['market2']}"
            cfg = self._build_pair_config(pair)
            self.pairs[symbol] = PairState(symbol=symbol, config=cfg)

    def _build_pair_config(self, pair: dict) -> AppConfig:
        """Clone base config and override trading params for this pair."""
        cfg = deepcopy(self.base_config)
        cfg.trading.market1 = pair["market1"]
        cfg.trading.market2 = pair["market2"]
        if "buy_order_amount" in pair:
            cfg.trading.buy_order_amount = pair["buy_order_amount"]
        return cfg

    async def start_pair(self, symbol: str) -> None:
        state = self.pairs.get(symbol)
        if not state:
            raise ValueError(f"Unknown pair: {symbol}")
        if state.status == "running":
            logger.warning(f"{symbol} already running")
            return

        # Lazy import to avoid circular deps
        from ..engine import TradingEngine

        strategy_name = "composite"
        # Check pairs config for strategy override
        for pair_cfg in self.pairs.values():
            if pair_cfg.symbol == symbol:
                # Use strategy from config if available
                break

        strategy_cls = STRATEGIES.get(strategy_name, STRATEGIES["composite"])
        strategy = strategy_cls(state.config.strategy, state.config.trading)

        engine = TradingEngine(state.config, strategy, client=self.client, db=self.db)
        engine._use_dashboard = False
        engine._register_signals = False

        state.engine = engine
        state.error = None
        state.status = "running"
        state.started_at = time.time()

        state.task = asyncio.create_task(self._run_engine(symbol, engine))
        logger.info(f"Started pair {symbol}")

    async def _run_engine(self, symbol: str, engine) -> None:
        """Wrapper that catches engine crashes and updates pair state."""
        try:
            await engine.start()
        except asyncio.CancelledError:
            logger.info(f"{symbol} engine cancelled")
        except Exception as e:
            logger.error(f"{symbol} engine crashed: {e}", exc_info=True)
            state = self.pairs.get(symbol)
            if state:
                state.status = "error"
                state.error = str(e)
                return
        state = self.pairs.get(symbol)
        if state and state.status != "error":
            state.status = "stopped"

    async def stop_pair(self, symbol: str) -> None:
        state = self.pairs.get(symbol)
        if not state:
            raise ValueError(f"Unknown pair: {symbol}")
        if state.status != "running":
            return

        if state.engine:
            await state.engine.stop("web_stop")
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass

        state.status = "stopped"
        state.engine = None
        state.task = None
        logger.info(f"Stopped pair {symbol}")

    async def get_pair_status(self, symbol: str) -> dict:
        state = self.pairs.get(symbol)
        if not state:
            return {}

        result = {
            "symbol": symbol,
            "market1": state.config.trading.market1,
            "market2": state.config.trading.market2,
            "status": state.status,
            "error": state.error,
            "strategy": "composite",
            "started_at": state.started_at,
            "current_price": 0.0,
            "open_positions": 0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        }

        try:
            if state.status == "running":
                result["current_price"] = await self.client.get_price(symbol)
            positions = await self.db.get_open_positions(symbol)
            result["open_positions"] = len(positions)

            stats = await self.db.get_stats(symbol)
            result["realized_pnl"] = stats.get("total_profit", 0.0)
            result["total_trades"] = stats.get("total_trades", 0)
            result["win_rate"] = stats.get("win_rate", 0.0)

            # Unrealized P&L
            if positions and result["current_price"] > 0:
                unrealized = sum(
                    (result["current_price"] - p["entry_price"]) * p["quantity"]
                    for p in positions
                )
                result["unrealized_pnl"] = round(unrealized, 4)
        except Exception as e:
            logger.debug(f"Error getting status for {symbol}: {e}")

        return result

    def get_pair_live_data(self, symbol: str) -> dict | None:
        """Get live operation data from a running engine."""
        state = self.pairs.get(symbol)
        if not state or not state.engine or state.status != "running":
            return None
        return state.engine.get_live_data()

    async def get_all_status(self) -> list[dict]:
        tasks = [self.get_pair_status(s) for s in self.pairs]
        return await asyncio.gather(*tasks)

    async def shutdown(self) -> None:
        """Stop all running engines."""
        for symbol, state in self.pairs.items():
            if state.status == "running":
                await self.stop_pair(symbol)
        logger.info("All pairs stopped")
