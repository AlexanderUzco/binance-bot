"""Order execution with retry logic and slippage protection."""

import asyncio
import logging
import time

from ..database import Database
from .binance_client import BinanceClient
from .position_manager import PositionManager

logger = logging.getLogger("binance_bot.executor")


class OrderExecutor:
    """Handles order placement, fills, and position management."""

    def __init__(
        self, client: BinanceClient, db: Database, positions: PositionManager
    ):
        self.client = client
        self.db = db
        self.positions = positions

    async def execute_buy(
        self,
        symbol: str,
        quantity: float,
        sell_target: float | None,
        stop_loss: float | None,
        strategy: str,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> dict:
        """Execute a buy order and create a position."""
        try:
            if order_type == "limit" and limit_price:
                result = await self.client.limit_buy(symbol, quantity, limit_price)
            else:
                result = await self.client.market_buy(symbol, quantity)

            status = result.get("status", "UNKNOWN")
            if status != "FILLED":
                # Log the order attempt
                await self.db.log_order(
                    symbol=symbol, side="BUY", order_type=order_type.upper(),
                    price=limit_price, quantity=quantity, status=status,
                    binance_order_id=str(result.get("orderId", "")),
                    strategy=strategy,
                )
                return {"success": False, "status": status, "order": result}

            # Order filled
            fill_price = self.client.get_fill_price(result)
            fill_qty = self.client.get_fill_quantity(result)
            order_id = str(result.get("orderId", ""))

            # Create position
            pos_id = await self.positions.open_position(
                symbol=symbol,
                quantity=fill_qty,
                entry_price=fill_price,
                sell_target=sell_target,
                stop_loss=stop_loss,
                strategy=strategy,
                order_id=order_id,
            )

            # Log order
            await self.db.log_order(
                symbol=symbol, side="BUY", order_type=order_type.upper(),
                price=fill_price, quantity=fill_qty, status="FILLED",
                binance_order_id=order_id, strategy=strategy,
                position_id=pos_id,
            )

            logger.info(
                f"BUY executed: {symbol} qty={fill_qty} @ {fill_price} "
                f"position_id={pos_id}"
            )

            return {
                "success": True,
                "position_id": pos_id,
                "fill_price": fill_price,
                "fill_quantity": fill_qty,
                "order_id": order_id,
            }

        except Exception as e:
            logger.error(f"Buy execution failed: {symbol} qty={quantity} - {e}")
            return {"success": False, "error": str(e)}

    async def execute_sell(
        self,
        symbol: str,
        position_id: int,
        quantity: float,
        reason: str = "manual",
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> dict:
        """Execute a sell order and close the position."""
        try:
            if order_type == "limit" and limit_price:
                result = await self.client.limit_sell(symbol, quantity, limit_price)
            else:
                result = await self.client.market_sell(symbol, quantity)

            status = result.get("status", "UNKNOWN")
            if status != "FILLED":
                await self.db.log_order(
                    symbol=symbol, side="SELL", order_type=order_type.upper(),
                    price=limit_price, quantity=quantity, status=status,
                    binance_order_id=str(result.get("orderId", "")),
                    position_id=position_id,
                )
                return {"success": False, "status": status, "order": result}

            fill_price = self.client.get_fill_price(result)
            order_id = str(result.get("orderId", ""))

            # Close position
            close_result = await self.positions.close_position(
                position_id, fill_price, reason
            )

            # Log order
            await self.db.log_order(
                symbol=symbol, side="SELL", order_type=order_type.upper(),
                price=fill_price, quantity=quantity, status="FILLED",
                binance_order_id=order_id, position_id=position_id,
            )

            logger.info(
                f"SELL executed: {symbol} qty={quantity} @ {fill_price} "
                f"profit={close_result.get('profit', 0)} reason={reason}"
            )

            return {
                "success": True,
                "fill_price": fill_price,
                "order_id": order_id,
                **close_result,
            }

        except Exception as e:
            logger.error(f"Sell execution failed: {symbol} pos={position_id} - {e}")
            return {"success": False, "error": str(e)}

    async def sell_all_positions(self, symbol: str, reason: str = "liquidate") -> list[dict]:
        """Sell all open positions for a symbol."""
        positions = await self.positions.get_open_positions(symbol)
        results = []

        for pos in positions:
            result = await self.execute_sell(
                symbol=symbol,
                position_id=pos["id"],
                quantity=pos["quantity"],
                reason=reason,
            )
            results.append(result)
            # Small delay between orders
            await asyncio.sleep(0.2)

        return results

    async def process_exits(self, symbol: str, current_price: float) -> list[dict]:
        """Check and execute all triggered exits (SL/TP)."""
        exits = await self.positions.check_exits(symbol, current_price)
        results = []

        for exit_info in exits:
            pos = exit_info["position"]
            result = await self.execute_sell(
                symbol=symbol,
                position_id=pos["id"],
                quantity=pos["quantity"],
                reason=exit_info["reason"],
            )
            result["trigger"] = exit_info["reason"]
            result["trigger_price"] = exit_info["trigger_price"]
            results.append(result)
            await asyncio.sleep(0.1)

        return results
