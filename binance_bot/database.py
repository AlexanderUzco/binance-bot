"""SQLite database for state persistence with WAL mode."""

import aiosqlite
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'long',
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    sell_target REAL,
    stop_loss REAL,
    ma_check REAL,
    status TEXT NOT NULL DEFAULT 'open',
    strategy TEXT NOT NULL,
    order_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    closed_at REAL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    type TEXT NOT NULL,
    price REAL,
    quantity REAL NOT NULL,
    status TEXT NOT NULL,
    binance_order_id TEXT,
    strategy TEXT,
    position_id INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    quantity REAL NOT NULL,
    profit REAL NOT NULL,
    profit_pct REAL NOT NULL,
    strategy TEXT NOT NULL,
    position_id INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("Database not connected")
        return self._db

    # -- Positions --

    async def create_position(
        self, symbol: str, entry_price: float, quantity: float,
        sell_target: float | None, stop_loss: float | None,
        strategy: str, order_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        now = time.time()
        cursor = await self.db.execute(
            """INSERT INTO positions
            (symbol, entry_price, quantity, sell_target, stop_loss, strategy,
             order_id, metadata, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (symbol, entry_price, quantity, sell_target, stop_loss,
             strategy, order_id, json.dumps(metadata or {}), now, now),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get_open_positions(self, symbol: str | None = None) -> list[dict]:
        if symbol:
            cursor = await self.db.execute(
                "SELECT * FROM positions WHERE status='open' AND symbol=?", (symbol,)
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM positions WHERE status='open'"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_position(self, position_id: int, **kwargs):
        kwargs["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values())
        vals.append(position_id)
        await self.db.execute(
            f"UPDATE positions SET {sets} WHERE id=?", vals
        )
        await self.db.commit()

    async def close_position(self, position_id: int, exit_price: float, profit: float):
        now = time.time()
        await self.db.execute(
            """UPDATE positions SET status='closed', updated_at=?, closed_at=?
            WHERE id=?""",
            (now, now, position_id),
        )

        # Get position data for trade record
        cursor = await self.db.execute(
            "SELECT * FROM positions WHERE id=?", (position_id,)
        )
        pos = dict(await cursor.fetchone())

        profit_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100

        await self.db.execute(
            """INSERT INTO trades
            (symbol, side, entry_price, exit_price, quantity, profit, profit_pct,
             strategy, position_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pos["symbol"], pos["side"], pos["entry_price"], exit_price,
             pos["quantity"], profit, profit_pct, pos["strategy"], position_id, now),
        )
        await self.db.commit()

    # -- Orders --

    async def log_order(
        self, symbol: str, side: str, order_type: str, price: float | None,
        quantity: float, status: str, binance_order_id: str | None = None,
        strategy: str | None = None, position_id: int | None = None,
        metadata: dict | None = None,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO orders
            (symbol, side, type, price, quantity, status, binance_order_id,
             strategy, position_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, side, order_type, price, quantity, status,
             binance_order_id, strategy, position_id,
             json.dumps(metadata or {}), time.time()),
        )
        await self.db.commit()
        return cursor.lastrowid

    # -- Trades --

    async def get_trades(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        if symbol:
            cursor = await self.db.execute(
                "SELECT * FROM trades WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
                (symbol, limit),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [dict(r) for r in await cursor.fetchall()]

    async def get_total_profit(self, symbol: str | None = None) -> float:
        if symbol:
            cursor = await self.db.execute(
                "SELECT COALESCE(SUM(profit), 0) FROM trades WHERE symbol=?",
                (symbol,),
            )
        else:
            cursor = await self.db.execute(
                "SELECT COALESCE(SUM(profit), 0) FROM trades"
            )
        row = await cursor.fetchone()
        return row[0]

    # -- Bot State (key-value) --

    async def get_state(self, key: str, default: Any = None) -> Any:
        cursor = await self.db.execute(
            "SELECT value FROM bot_state WHERE key=?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    async def set_state(self, key: str, value: Any):
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await self.db.execute(
            """INSERT INTO bot_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?""",
            (key, serialized, time.time(), serialized, time.time()),
        )
        await self.db.commit()

    # -- Stats --

    async def get_stats(self, symbol: str | None = None) -> dict:
        trades = await self.get_trades(symbol, limit=1000)
        if not trades:
            return {
                "total_trades": 0, "winning": 0, "losing": 0,
                "win_rate": 0, "total_profit": 0, "avg_profit_pct": 0,
            }

        winning = [t for t in trades if t["profit"] > 0]
        losing = [t for t in trades if t["profit"] <= 0]
        total_profit = sum(t["profit"] for t in trades)
        avg_pct = sum(t["profit_pct"] for t in trades) / len(trades)

        return {
            "total_trades": len(trades),
            "winning": len(winning),
            "losing": len(losing),
            "win_rate": len(winning) / len(trades) * 100 if trades else 0,
            "total_profit": round(total_profit, 4),
            "avg_profit_pct": round(avg_pct, 4),
        }
