"""Async Binance client with REST + WebSocket support."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Callable

import httpx
import websockets

from ..config import BinanceConfig

logger = logging.getLogger("binance_bot.client")


class BinanceClient:
    """Async Binance API client with HMAC-SHA256 signing and WebSocket streams."""

    def __init__(self, config: BinanceConfig):
        self.config = config
        self._http: httpx.AsyncClient | None = None
        self._ws_connections: dict[str, Any] = {}
        self._exchange_info: dict[str, Any] = {}

    async def connect(self):
        self._http = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"X-MBX-APIKEY": self.config.api_key},
            timeout=30.0,
        )
        logger.info(f"Binance client connected ({'testnet' if self.config.testnet else 'production'})")

    async def close(self):
        if self._http:
            await self._http.aclose()
        for key, ws in list(self._ws_connections.items()):
            if hasattr(ws, 'close'):
                await ws.close()
        self._ws_connections.clear()

    def _sign(self, params: dict) -> str:
        """Build signed query string with timestamp and HMAC-SHA256 signature."""
        params["timestamp"] = int(time.time() * 1000)
        # Convert all values to strings to ensure consistent serialization
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(
            self.config.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return f"{query}&signature={signature}"

    async def _public(self, method: str, path: str, params: dict | None = None) -> dict:
        resp = await self._http.request(method, path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def _signed(self, method: str, path: str, params: dict | None = None) -> dict:
        # Build the exact query string we sign, and send it as raw string
        # This prevents httpx from re-serializing params differently
        query_string = self._sign(dict(params or {}))
        url = f"{path}?{query_string}"
        resp = await self._http.request(method, url)
        if resp.status_code >= 400:
            try:
                error_body = resp.json()
                logger.error(f"Binance API error: {resp.status_code} {error_body}")
            except Exception:
                logger.error(f"Binance API error: {resp.status_code} {resp.text}")
            resp.raise_for_status()
        return resp.json()

    # -- Market Data --

    async def get_price(self, symbol: str) -> float:
        data = await self._public("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])

    async def get_ticker_24h(self, symbol: str) -> dict:
        return await self._public("GET", "/api/v3/ticker/24hr", {"symbol": symbol})

    async def get_klines(
        self, symbol: str, interval: str = "1m", limit: int = 150
    ) -> list[dict]:
        data = await self._public(
            "GET", "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        return [
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            }
            for k in data
        ]

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        return await self._public(
            "GET", "/api/v3/depth", {"symbol": symbol, "limit": limit}
        )

    async def get_exchange_info(self, symbol: str) -> dict:
        """Get symbol trading rules (lot size, price filter, etc)."""
        if symbol not in self._exchange_info:
            data = await self._public(
                "GET", "/api/v3/exchangeInfo", {"symbol": symbol}
            )
            if data.get("symbols"):
                self._exchange_info[symbol] = data["symbols"][0]
        return self._exchange_info.get(symbol, {})

    def get_lot_size(self, exchange_info: dict) -> dict:
        """Extract LOT_SIZE filter from exchange info."""
        for f in exchange_info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                return {
                    "min_qty": float(f["minQty"]),
                    "max_qty": float(f["maxQty"]),
                    "step_size": float(f["stepSize"]),
                }
        return {"min_qty": 0, "max_qty": 0, "step_size": 0}

    def get_price_filter(self, exchange_info: dict) -> dict:
        """Extract PRICE_FILTER from exchange info."""
        for f in exchange_info.get("filters", []):
            if f["filterType"] == "PRICE_FILTER":
                return {
                    "min_price": float(f["minPrice"]),
                    "max_price": float(f["maxPrice"]),
                    "tick_size": float(f["tickSize"]),
                }
        return {"min_price": 0, "max_price": 0, "tick_size": 0}

    def round_quantity(self, quantity: float, step_size: float) -> float:
        """Round quantity to valid step size (handles floating point)."""
        if step_size == 0:
            return quantity
        from decimal import Decimal, ROUND_DOWN
        d_qty = Decimal(str(quantity))
        d_step = Decimal(str(step_size))
        return float((d_qty / d_step).to_integral_value(rounding=ROUND_DOWN) * d_step)

    def round_price(self, price: float, tick_size: float) -> float:
        """Round price to valid tick size (handles floating point)."""
        if tick_size == 0:
            return price
        from decimal import Decimal, ROUND_DOWN
        d_price = Decimal(str(price))
        d_tick = Decimal(str(tick_size))
        return float((d_price / d_tick).to_integral_value(rounding=ROUND_DOWN) * d_tick)

    # -- Account --

    async def get_balances(self, hide_zero: bool = True) -> list[dict]:
        data = await self._signed("GET", "/api/v3/account")
        balances = []
        for b in data.get("balances", []):
            free = float(b["free"])
            locked = float(b["locked"])
            if hide_zero and free == 0 and locked == 0:
                continue
            balances.append({
                "asset": b["asset"],
                "free": free,
                "locked": locked,
                "total": free + locked,
            })
        return balances

    async def get_balance(self, asset: str) -> float:
        balances = await self.get_balances(hide_zero=False)
        for b in balances:
            if b["asset"] == asset:
                return b["free"]
        return 0.0

    # -- Orders --

    async def market_buy(self, symbol: str, quantity: float) -> dict:
        """Place a market buy order."""
        info = await self.get_exchange_info(symbol)
        lot = self.get_lot_size(info)
        qty = self.round_quantity(quantity, lot["step_size"])

        result = await self._signed("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": qty,
        })
        logger.info(f"Market BUY {symbol}: qty={qty}, orderId={result.get('orderId')}")
        return result

    async def market_sell(self, symbol: str, quantity: float) -> dict:
        """Place a market sell order."""
        info = await self.get_exchange_info(symbol)
        lot = self.get_lot_size(info)
        qty = self.round_quantity(quantity, lot["step_size"])

        result = await self._signed("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty,
        })
        logger.info(f"Market SELL {symbol}: qty={qty}, orderId={result.get('orderId')}")
        return result

    async def limit_buy(self, symbol: str, quantity: float, price: float) -> dict:
        """Place a limit buy order."""
        info = await self.get_exchange_info(symbol)
        lot = self.get_lot_size(info)
        pf = self.get_price_filter(info)
        qty = self.round_quantity(quantity, lot["step_size"])
        px = self.round_price(price, pf["tick_size"])

        result = await self._signed("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": qty,
            "price": px,
        })
        logger.info(f"Limit BUY {symbol}: qty={qty}, price={px}, orderId={result.get('orderId')}")
        return result

    async def limit_sell(self, symbol: str, quantity: float, price: float) -> dict:
        """Place a limit sell order."""
        info = await self.get_exchange_info(symbol)
        lot = self.get_lot_size(info)
        pf = self.get_price_filter(info)
        qty = self.round_quantity(quantity, lot["step_size"])
        px = self.round_price(price, pf["tick_size"])

        result = await self._signed("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": qty,
            "price": px,
        })
        logger.info(f"Limit SELL {symbol}: qty={qty}, price={px}, orderId={result.get('orderId')}")
        return result

    async def cancel_order(self, symbol: str, order_id: int) -> dict:
        return await self._signed("DELETE", "/api/v3/order", {
            "symbol": symbol,
            "orderId": order_id,
        })

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._signed("GET", "/api/v3/openOrders", params)

    async def get_order_history(self, symbol: str, limit: int = 50) -> list[dict]:
        return await self._signed("GET", "/api/v3/allOrders", {
            "symbol": symbol, "limit": limit,
        })

    # -- WebSocket --

    async def kline_stream(
        self, symbol: str, interval: str, callback: Callable[[dict], Any],
    ):
        """Connect to kline/candlestick WebSocket stream."""
        stream = f"{symbol.lower()}@kline_{interval}"
        url = f"{self.config.ws_url}/{stream}"
        logger.info(f"Connecting to WebSocket: {stream}")

        while True:
            try:
                async with websockets.connect(url) as ws:
                    self._ws_connections[stream] = ws
                    async for msg in ws:
                        data = json.loads(msg)
                        kline = data.get("k", {})
                        parsed = {
                            "symbol": kline.get("s"),
                            "interval": kline.get("i"),
                            "open": float(kline.get("o", 0)),
                            "high": float(kline.get("h", 0)),
                            "low": float(kline.get("l", 0)),
                            "close": float(kline.get("c", 0)),
                            "volume": float(kline.get("v", 0)),
                            "is_closed": kline.get("x", False),
                            "open_time": kline.get("t"),
                            "close_time": kline.get("T"),
                        }
                        await callback(parsed)
            except websockets.ConnectionClosed:
                logger.warning(f"WebSocket {stream} disconnected, reconnecting...")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"WebSocket {stream} error: {e}, reconnecting...")
                await asyncio.sleep(5)

    async def ticker_stream(
        self, symbol: str, callback: Callable[[dict], Any],
    ):
        """Connect to individual symbol ticker stream for real-time price."""
        stream = f"{symbol.lower()}@ticker"
        url = f"{self.config.ws_url}/{stream}"

        while True:
            try:
                async with websockets.connect(url) as ws:
                    self._ws_connections[stream] = ws
                    async for msg in ws:
                        data = json.loads(msg)
                        parsed = {
                            "symbol": data.get("s"),
                            "price": float(data.get("c", 0)),
                            "change_pct": float(data.get("P", 0)),
                            "volume": float(data.get("v", 0)),
                            "high": float(data.get("h", 0)),
                            "low": float(data.get("l", 0)),
                        }
                        await callback(parsed)
            except websockets.ConnectionClosed:
                logger.warning(f"WebSocket {stream} disconnected, reconnecting...")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"WebSocket {stream} error: {e}, reconnecting...")
                await asyncio.sleep(5)

    def get_fill_price(self, order_result: dict) -> float:
        """Extract actual fill price from order result."""
        fills = order_result.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
            return total_cost / total_qty if total_qty > 0 else 0
        # Fallback
        qty = float(order_result.get("executedQty", 0))
        quote = float(order_result.get("cummulativeQuoteQty", 0))
        return quote / qty if qty > 0 else 0

    def get_fill_quantity(self, order_result: dict) -> float:
        """Extract actual filled quantity minus commission."""
        fills = order_result.get("fills", [])
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            # Subtract commission if paid in base asset
            for f in fills:
                if f.get("commissionAsset") == order_result.get("symbol", "")[:len(f.get("commissionAsset", ""))]:
                    total_qty -= float(f.get("commission", 0))
            return total_qty
        return float(order_result.get("executedQty", 0))
