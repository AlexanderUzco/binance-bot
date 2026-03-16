"""Main trading engine - orchestrates strategies, execution, and risk management."""

import asyncio
import logging
import signal
import time
from typing import Any

from .config import AppConfig
from .database import Database
from .display import RESET, Dashboard
from .notifications import Notifier
from .services.binance_client import BinanceClient
from .services.indicators import detect_regime
from .services.order_executor import OrderExecutor
from .services.position_manager import PositionManager
from .services.risk_manager import RiskManager
from .strategies.base import BaseStrategy, Signal

logger = logging.getLogger("binance_bot.engine")


class TradingEngine:
    """Main event loop that coordinates all components."""

    def __init__(
        self, config: AppConfig, strategy: BaseStrategy,
        client: BinanceClient | None = None, db: Database | None = None,
    ):
        self.config = config
        self.strategy = strategy
        self.db = db or Database(config.db_path)
        self.client = client or BinanceClient(config.binance)
        self._owns_client = client is None
        self._owns_db = db is None
        self.positions = PositionManager(self.db, self.client)
        self.executor = OrderExecutor(self.client, self.db, self.positions)
        self.risk = RiskManager(config.risk, config.trading, self.db)
        self.notifier = Notifier(config.notification)
        self.dashboard: Dashboard | None = None
        self._running = False
        self._stopped = False
        self._stop_reason = ""
        self._use_dashboard = True
        self._use_websocket = True
        self._register_signals = True
        self._price_queue: asyncio.Queue[float] = asyncio.Queue()
        self._kline_buffer: list[dict] = []
        self._events: list[dict] = []
        self._max_events = 50
        self._start_time: float = 0.0
        self._last_price: float = 0.0
        self._last_balance: float = 0.0
        self._last_regime: str = "..."

    async def start(self):
        """Initialize all components and start the trading loop."""
        logger.info(f"Starting engine with strategy: {self.strategy.name}")
        logger.info(f"Symbol: {self.config.trading.symbol}")
        logger.info(f"Testnet: {self.config.binance.testnet}")

        # Connect
        await self.db.connect()
        await self.client.connect()

        # Store initial balance (per-symbol key for multi-pair support)
        balance = await self.client.get_balance(self.config.trading.market2)
        balance_key = f"initial_balance:{self.config.trading.symbol}"
        existing_initial = await self.db.get_state(balance_key)
        if existing_initial is None:
            await self.db.set_state(balance_key, balance)
            logger.info(f"Initial {self.config.trading.market2} balance: {balance}")

        # Load initial klines
        self._kline_buffer = await self.client.get_klines(
            self.config.trading.symbol, "1m", 150
        )
        logger.info(f"Loaded {len(self._kline_buffer)} initial klines")

        # Sell all on start if configured
        if self.config.trading.sell_all_on_start:
            positions = await self.positions.get_open_positions(self.config.trading.symbol)
            if positions:
                logger.info(f"Selling all {len(positions)} positions on start")
                await self.executor.sell_all_positions(
                    self.config.trading.symbol, reason="sell_all_on_start"
                )

        # Notify
        await self.notifier.notify(
            f"[BinBot] Started",
            f"Strategy: {self.strategy.name}\n"
            f"Symbol: {self.config.trading.symbol}\n"
            f"Balance: {balance} {self.config.trading.market2}",
        )

        self._running = True
        self._start_time = time.time()
        self._last_balance = balance
        self._add_event("start", f"Engine started | Balance: {balance:,.2f} {self.config.trading.market2}")

        # Start dashboard (replaces scrolling logs)
        if self._use_dashboard:
            self.dashboard = Dashboard(
                symbol=self.config.trading.symbol,
                strategy=self.strategy.name,
                testnet=self.config.binance.testnet,
            )
            self.dashboard.start()
            self.dashboard.add_event(f"Engine started | Balance: {balance:,.2f} {self.config.trading.market2}")

        # Setup graceful shutdown (skip in web/orchestrator mode)
        if self._register_signals:
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_event_loop().add_signal_handler(
                    sig, self._handle_shutdown_signal
                )

        # Run trading loop
        use_ws = self._use_websocket and self.config.binance.ws_available
        if not self.config.binance.ws_available and self._use_websocket:
            msg = "REST polling mode (testnet)"
            logger.info(msg)
            if self.dashboard:
                self.dashboard.add_event(msg)
        try:
            if use_ws:
                await self._run_websocket()
            else:
                await self._run_polling()
        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
            self._stop_reason = f"error: {e}"
        finally:
            await self.stop(self._stop_reason or "manual")

    def _add_event(self, event_type: str, message: str, data: dict | None = None):
        """Record an event for both the terminal dashboard and the web API."""
        from datetime import datetime
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "timestamp": time.time(),
            "type": event_type,
            "message": message,
            "data": data or {},
        }
        self._events.append(entry)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        # Also forward to terminal dashboard if active
        if self.dashboard:
            self.dashboard.add_event(message)

    def get_live_data(self) -> dict:
        """Return live operation data for the web dashboard."""
        uptime = 0
        if self._start_time > 0:
            uptime = int(time.time() - self._start_time)
        return {
            "running": self._running,
            "symbol": self.config.trading.symbol,
            "strategy": self.strategy.name,
            "price": self._last_price,
            "balance": self._last_balance,
            "regime": self._last_regime,
            "uptime": uptime,
            "tick_count": getattr(self, "_tick_count", 0),
            "events": list(self._events),
        }

    def _handle_shutdown_signal(self):
        """Handle SIGINT/SIGTERM: flag shutdown so the loop exits cleanly."""
        self._running = False
        self._stop_reason = "signal"

    async def _run_websocket(self):
        """Run with WebSocket price feed + periodic kline refresh."""
        symbol = self.config.trading.symbol

        # Start WebSocket in background
        ws_task = asyncio.create_task(
            self.client.kline_stream(symbol, "1m", self._on_kline)
        )

        # Main loop processes at configured interval
        interval = self.config.trading.sleep_time / 1000
        last_kline_refresh = time.time()

        while self._running:
            try:
                # Get latest price from buffer or REST fallback
                price = await self._get_current_price(symbol)
                if price <= 0:
                    await asyncio.sleep(1)
                    continue

                # Refresh full klines every 5 minutes
                if time.time() - last_kline_refresh > 300:
                    self._kline_buffer = await self.client.get_klines(symbol, "1m", 150)
                    last_kline_refresh = time.time()

                await self._tick(symbol, price)
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick error: {e}", exc_info=True)
                await asyncio.sleep(interval)

        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

    async def _run_polling(self):
        """Fallback: REST polling loop."""
        symbol = self.config.trading.symbol
        interval = self.config.trading.sleep_time / 1000

        while self._running:
            try:
                price = await self.client.get_price(symbol)
                self._kline_buffer = await self.client.get_klines(symbol, "1m", 150)
                await self._tick(symbol, price)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break  # Shutting down, ignore errors
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(interval)

    async def _tick(self, symbol: str, price: float):
        """Single iteration of the trading loop."""
        self._tick_count = getattr(self, '_tick_count', 0) + 1
        self._last_price = price

        # 1. Check portfolio-level risk limits
        balance = await self.client.get_balance(self.config.trading.market2)
        self._last_balance = balance
        risk_check = await self.risk.check_portfolio_limits(symbol, price, balance)
        if risk_check:
            msg = f"Portfolio limit: {risk_check['message']}"
            logger.warning(msg)
            self._add_event("risk", msg, risk_check)
            if self.config.trading.sell_all_on_close:
                await self.executor.sell_all_positions(symbol, reason=risk_check["action"])
            await self.notifier.notify(
                f"[BinBot] {risk_check['action'].upper()}",
                risk_check["message"],
            )
            await self.stop(risk_check["action"])
            return

        # 2. Process exits (SL/TP) for existing positions
        exit_results = await self.executor.process_exits(symbol, price)
        for result in exit_results:
            if result.get("success"):
                profit = result.get("profit", 0)
                color = "\033[92m" if profit >= 0 else "\033[91m"
                sign = "+" if profit >= 0 else ""
                trigger = result.get("trigger", "exit")
                self._add_event("sell", f"SELL {trigger} | qty={result.get('quantity', 0):.5f} | P&L: {sign}${profit:,.4f}", {
                    "side": "SELL", "trigger": trigger, "quantity": result.get("quantity", 0),
                    "fill_price": result.get("fill_price"), "profit": profit,
                })
                await self.notifier.notify_trade({
                    "side": "SELL",
                    "symbol": symbol,
                    "fill_price": result.get("fill_price"),
                    "quantity": result.get("quantity"),
                    "profit": profit,
                    "reason": trigger,
                })

        # 3. Get open positions
        open_positions = await self.positions.get_open_positions(symbol)

        # 4. Update position trailing data (MA checks, etc.)
        updates = await self.strategy.update_positions(
            symbol, price, self._kline_buffer, open_positions
        )
        for update in updates:
            pos_id = update.pop("id")
            await self.positions.update_trailing(pos_id, **update)

        # 5. Evaluate strategy for new signal
        sig = await self.strategy.evaluate(
            symbol, price, self._kline_buffer, open_positions
        )

        # 6. Execute signal
        if sig.action == "buy":
            approval = await self.risk.can_open_position(symbol, price, balance)
            if not approval["allowed"]:
                logger.debug(f"Buy blocked: {approval['reason']}")
                return

            qty = sig.quantity or self.risk.calculate_position_size(balance, price)
            strategy_name = (sig.metadata or {}).get("source_strategy", self.strategy.name)
            result = await self.executor.execute_buy(
                symbol=symbol,
                quantity=qty,
                sell_target=sig.sell_target,
                stop_loss=sig.stop_loss,
                strategy=strategy_name,
            )
            if result.get("success"):
                logger.info(f"BUY signal executed: {sig.reason}")
                self._add_event("buy", f"BUY ${result['fill_price']:,.2f} | qty={result['fill_quantity']:.5f} | {strategy_name} | {sig.reason}", {
                    "side": "BUY", "fill_price": result["fill_price"],
                    "quantity": result["fill_quantity"], "strategy": strategy_name, "reason": sig.reason,
                })
                await self.notifier.notify_trade({
                    "side": "BUY",
                    "symbol": symbol,
                    "fill_price": result["fill_price"],
                    "quantity": result["fill_quantity"],
                    "reason": sig.reason,
                })

        elif sig.action == "sell":
            position_ids = (sig.metadata or {}).get("position_ids", [])
            for pos_id in position_ids:
                pos = next((p for p in open_positions if p["id"] == pos_id), None)
                if pos:
                    result = await self.executor.execute_sell(
                        symbol=symbol,
                        position_id=pos_id,
                        quantity=pos["quantity"],
                        reason=sig.reason,
                    )
                    if result.get("success"):
                        profit = result.get("profit", 0)
                        sign = "+" if profit >= 0 else ""
                        self._add_event("sell", f"SELL ${result['fill_price']:,.2f} | P&L: {sign}${profit:,.4f} | {sig.reason}", {
                            "side": "SELL", "fill_price": result["fill_price"],
                            "quantity": pos["quantity"], "profit": profit, "reason": sig.reason,
                        })
                        await self.notifier.notify_trade({
                            "side": "SELL",
                            "symbol": symbol,
                            "fill_price": result["fill_price"],
                            "quantity": pos["quantity"],
                            "profit": profit,
                            "reason": sig.reason,
                        })

        # 7. Detect regime (for web and dashboard)
        if self._tick_count % 10 == 0:
            try:
                regime = detect_regime(self._kline_buffer)
                if regime:
                    self._last_regime = regime.regime
            except Exception:
                pass

        # 8. Render dashboard or periodic log
        if self.dashboard:
            await self._render_dashboard(symbol, price, balance, open_positions)
        elif self._tick_count % 30 == 0:
            portfolio = await self.positions.get_portfolio_value(symbol, price)
            pnl = portfolio["total_pnl"]
            if pnl > 0:
                pnl_str = f"\033[92m+${pnl:,.2f}\033[0m"
            elif pnl < 0:
                pnl_str = f"\033[91m-${abs(pnl):,.2f}\033[0m"
            else:
                pnl_str = f"${pnl:,.2f}"
            logger.info(
                f"[status] {symbol} ${price:,.2f} | P&L: {pnl_str} | "
                f"balance: {balance:,.2f} {self.config.trading.market2} | "
                f"positions: {len(open_positions)}"
            )

    async def _render_dashboard(
        self, symbol: str, price: float, balance: float, positions: list[dict]
    ):
        """Gather data and render the dashboard."""
        portfolio = await self.positions.get_portfolio_value(symbol, price)
        stats = await self.db.get_stats(symbol)

        # Detect current regime
        regime_name = "..."
        try:
            regime = detect_regime(self._kline_buffer)
            if regime:
                regime_name = regime.regime
        except Exception:
            pass
        self._last_regime = regime_name

        self.dashboard.render(
            price=price,
            balance=balance,
            quote_asset=self.config.trading.market2,
            pnl=portfolio["total_pnl"],
            realized_pnl=portfolio["realized_pnl"],
            unrealized_pnl=portfolio["unrealized_pnl"],
            positions=positions,
            regime=regime_name,
            total_trades=stats.get("total_trades", 0),
            win_rate=stats.get("win_rate", 0.0),
        )

    async def _on_kline(self, kline: dict):
        """WebSocket kline callback - updates buffer."""
        if kline.get("is_closed"):
            # Append closed kline to buffer
            self._kline_buffer.append({
                "open": kline["open"],
                "high": kline["high"],
                "low": kline["low"],
                "close": kline["close"],
                "volume": kline["volume"],
                "open_time": kline["open_time"],
                "close_time": kline["close_time"],
            })
            # Keep buffer at 150 candles
            if len(self._kline_buffer) > 200:
                self._kline_buffer = self._kline_buffer[-150:]
        else:
            # Update last candle with live data
            if self._kline_buffer:
                self._kline_buffer[-1] = {
                    **self._kline_buffer[-1],
                    "high": max(self._kline_buffer[-1].get("high", 0), kline["high"]),
                    "low": min(self._kline_buffer[-1].get("low", float("inf")), kline["low"]),
                    "close": kline["close"],
                    "volume": kline["volume"],
                }

        # Push price for consumers
        try:
            self._price_queue.put_nowait(kline["close"])
        except asyncio.QueueFull:
            pass

    async def _get_current_price(self, symbol: str) -> float:
        """Get price from WS queue or REST fallback."""
        try:
            # Drain queue, take latest
            price = 0.0
            while not self._price_queue.empty():
                price = self._price_queue.get_nowait()
            if price > 0:
                return price
        except asyncio.QueueEmpty:
            pass

        # REST fallback
        try:
            return await self.client.get_price(symbol)
        except Exception:
            return 0.0

    async def stop(self, reason: str = "manual"):
        """Graceful shutdown."""
        if self._stopped:
            return
        self._stopped = True
        self._running = False

        # Restore terminal before logging shutdown messages
        if self.dashboard:
            self.dashboard.stop()
            self.dashboard = None

        logger.info(f"Stopping engine: {reason}")

        # Give the polling/ws loop time to exit cleanly
        await asyncio.sleep(0.5)

        # Sell all on close if configured
        if self.config.trading.sell_all_on_close and reason != "sell_all_on_start":
            try:
                positions = await self.positions.get_open_positions(self.config.trading.symbol)
                if positions:
                    logger.info(f"Selling {len(positions)} positions on close")
                    await self.executor.sell_all_positions(
                        self.config.trading.symbol, reason=f"shutdown_{reason}"
                    )
            except Exception as e:
                logger.error(f"Failed to sell on close: {e}")

        # Send shutdown notification
        try:
            stats = await self.db.get_stats(self.config.trading.symbol)
            await self.notifier.notify_shutdown(reason, stats)
        except Exception:
            pass

        # Cleanup (only close resources we own)
        if self._owns_client:
            try:
                await self.client.close()
            except Exception:
                pass
        if self._owns_db:
            try:
                await self.db.close()
            except Exception:
                pass
        logger.info("Engine stopped")

    async def get_status(self) -> dict:
        """Get current engine status."""
        symbol = self.config.trading.symbol
        try:
            price = await self.client.get_price(symbol)
        except Exception:
            price = 0

        positions = await self.positions.get_open_positions(symbol)
        stats = await self.db.get_stats(symbol)
        balance = await self.client.get_balance(self.config.trading.market2)
        portfolio = await self.positions.get_portfolio_value(symbol, price)

        return {
            "running": self._running,
            "strategy": self.strategy.name,
            "symbol": symbol,
            "current_price": price,
            "balance": balance,
            "open_positions": len(positions),
            "portfolio": portfolio,
            "stats": stats,
        }
