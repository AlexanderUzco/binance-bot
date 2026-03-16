"""Position tracking and P&L management."""

import logging
import time

from ..database import Database
from .binance_client import BinanceClient

logger = logging.getLogger("binance_bot.positions")


class PositionManager:
    """Manages positions lifecycle: open, update, close, P&L tracking."""

    def __init__(self, db: Database, client: BinanceClient):
        self.db = db
        self.client = client

    async def open_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        sell_target: float | None,
        stop_loss: float | None,
        strategy: str,
        order_id: str | None = None,
    ) -> int:
        """Record a new open position."""
        pos_id = await self.db.create_position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            sell_target=sell_target,
            stop_loss=stop_loss,
            strategy=strategy,
            order_id=order_id,
        )
        logger.info(
            f"Position opened: {symbol} qty={quantity} entry={entry_price} "
            f"tp={sell_target} sl={stop_loss} strategy={strategy} id={pos_id}"
        )
        return pos_id

    async def close_position(
        self, position_id: int, exit_price: float, reason: str = "manual"
    ) -> dict:
        """Close a position and record the trade."""
        positions = await self.db.get_open_positions()
        pos = next((p for p in positions if p["id"] == position_id), None)
        if not pos:
            return {"error": f"Position {position_id} not found or already closed"}

        profit = (exit_price - pos["entry_price"]) * pos["quantity"]
        profit_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100

        await self.db.close_position(position_id, exit_price, profit)

        logger.info(
            f"Position closed: id={position_id} {pos['symbol']} "
            f"exit={exit_price} profit={profit:.4f} ({profit_pct:.2f}%) reason={reason}"
        )

        return {
            "position_id": position_id,
            "symbol": pos["symbol"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "quantity": pos["quantity"],
            "profit": round(profit, 4),
            "profit_pct": round(profit_pct, 2),
            "reason": reason,
        }

    async def get_open_positions(self, symbol: str | None = None) -> list[dict]:
        return await self.db.get_open_positions(symbol)

    async def update_trailing(self, position_id: int, **kwargs):
        """Update trailing fields (ma_check, sell_target, stop_loss)."""
        await self.db.update_position(position_id, **kwargs)

    async def check_exits(self, symbol: str, current_price: float) -> list[dict]:
        """Check all open positions for exit conditions. Returns list of triggered exits."""
        positions = await self.db.get_open_positions(symbol)
        exits = []

        for pos in positions:
            # Check stop loss
            if pos["stop_loss"] and current_price <= pos["stop_loss"]:
                exits.append({
                    "position": pos,
                    "reason": "stop_loss",
                    "trigger_price": pos["stop_loss"],
                    "current_price": current_price,
                })
                continue

            # Check take profit
            if pos["sell_target"] and current_price >= pos["sell_target"]:
                exits.append({
                    "position": pos,
                    "reason": "take_profit",
                    "trigger_price": pos["sell_target"],
                    "current_price": current_price,
                })

        return exits

    async def get_portfolio_value(self, symbol: str, current_price: float) -> dict:
        """Calculate current portfolio value and unrealized P&L."""
        positions = await self.db.get_open_positions(symbol)
        total_quantity = sum(p["quantity"] for p in positions)
        total_cost = sum(p["entry_price"] * p["quantity"] for p in positions)
        current_value = total_quantity * current_price
        unrealized_pnl = current_value - total_cost

        realized_pnl = await self.db.get_total_profit(symbol)

        return {
            "open_positions": len(positions),
            "total_quantity": round(total_quantity, 8),
            "total_cost": round(total_cost, 4),
            "current_value": round(current_value, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "realized_pnl": round(realized_pnl, 4),
            "total_pnl": round(unrealized_pnl + realized_pnl, 4),
        }
