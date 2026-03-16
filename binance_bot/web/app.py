"""FastAPI application — SSR dashboard for multi-pair trading."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import load_config
from ..database import Database
from ..services.binance_client import BinanceClient
from .chart_data import compute_chart_data
from .orchestrator import PairOrchestrator

logger = logging.getLogger("binance_bot.web")

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def load_pairs(pairs_path: Path | None = None) -> list[dict]:
    """Load pairs configuration from pairs.json."""
    if pairs_path is None:
        pairs_path = Path("pairs.json")
    if not pairs_path.exists():
        logger.warning(f"pairs.json not found at {pairs_path}, using empty config")
        return []
    with open(pairs_path) as f:
        data = json.load(f)
    return [p for p in data.get("pairs", []) if p.get("enabled", True)]


def create_app(env_path: str | None = None, pairs_path: str | None = None) -> FastAPI:
    """Factory that creates the FastAPI app with lifespan."""

    config = load_config(env_path)
    pairs = load_pairs(Path(pairs_path) if pairs_path else None)

    db = Database(config.db_path)
    client = BinanceClient(config.binance)
    orchestrator = PairOrchestrator(config, db, client, pairs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        await client.connect()
        logger.info(f"Web dashboard started — {len(pairs)} pairs configured")
        yield
        await orchestrator.shutdown()
        await client.close()
        await db.close()
        logger.info("Web dashboard stopped")

    app = FastAPI(title="BinBot Dashboard", lifespan=lifespan)
    app.state.orchestrator = orchestrator
    app.state.db = db
    app.state.client = client
    app.state.config = config

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # -- Helpers --

    def _orch(request: Request) -> PairOrchestrator:
        return request.app.state.orchestrator

    # -- Full pages --

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        orch = _orch(request)
        statuses = await orch.get_all_status()
        balance = 0.0
        try:
            balance = await client.get_balance(config.trading.market2)
        except Exception:
            pass
        total_pnl = sum(s.get("realized_pnl", 0) + s.get("unrealized_pnl", 0) for s in statuses)
        active_count = sum(1 for s in statuses if s["status"] == "running")
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "pairs": statuses,
            "balance": balance,
            "quote_asset": config.trading.market2,
            "total_pnl": total_pnl,
            "active_count": active_count,
            "total_count": len(statuses),
        })

    @app.get("/pair/{symbol}", response_class=HTMLResponse)
    async def pair_detail(request: Request, symbol: str):
        orch = _orch(request)
        status = await orch.get_pair_status(symbol)
        positions = await db.get_open_positions(symbol)
        trades = await db.get_trades(symbol, limit=20)
        stats = await db.get_stats(symbol)

        # Enrich positions with current unrealized P&L
        price = status.get("current_price", 0)
        for p in positions:
            if price > 0:
                p["unrealized_pnl"] = round((price - p["entry_price"]) * p["quantity"], 4)
                p["unrealized_pct"] = round(((price - p["entry_price"]) / p["entry_price"]) * 100, 2)
            else:
                p["unrealized_pnl"] = 0
                p["unrealized_pct"] = 0

        # Live engine data
        live = orch.get_pair_live_data(symbol)
        if live is None:
            live = {"running": False, "symbol": symbol, "events": [], "regime": "—",
                    "price": 0, "balance": 0, "uptime": 0, "tick_count": 0, "strategy": "—"}
        h, rem = divmod(live["uptime"], 3600)
        m, s = divmod(rem, 60)
        live["uptime_fmt"] = f"{h:02d}:{m:02d}:{s:02d}"

        return templates.TemplateResponse("pair.html", {
            "request": request,
            "pair": status,
            "positions": positions,
            "trades": trades,
            "stats": stats,
            "live": live,
        })

    # -- HTMX partials --

    @app.get("/partials/pair-cards", response_class=HTMLResponse)
    async def partial_pair_cards(request: Request):
        orch = _orch(request)
        statuses = await orch.get_all_status()
        return templates.TemplateResponse("partials/pair_cards.html", {
            "request": request,
            "pairs": statuses,
        })

    @app.get("/partials/pair/{symbol}/positions", response_class=HTMLResponse)
    async def partial_positions(request: Request, symbol: str):
        orch = _orch(request)
        status = await orch.get_pair_status(symbol)
        positions = await db.get_open_positions(symbol)
        price = status.get("current_price", 0)
        for p in positions:
            if price > 0:
                p["unrealized_pnl"] = round((price - p["entry_price"]) * p["quantity"], 4)
                p["unrealized_pct"] = round(((price - p["entry_price"]) / p["entry_price"]) * 100, 2)
            else:
                p["unrealized_pnl"] = 0
                p["unrealized_pct"] = 0
        return templates.TemplateResponse("partials/positions.html", {
            "request": request,
            "positions": positions,
            "symbol": symbol,
        })

    @app.get("/partials/pair/{symbol}/trades", response_class=HTMLResponse)
    async def partial_trades(request: Request, symbol: str):
        trades = await db.get_trades(symbol, limit=20)
        return templates.TemplateResponse("partials/trades.html", {
            "request": request,
            "trades": trades,
            "symbol": symbol,
        })

    @app.get("/partials/pair/{symbol}/live", response_class=HTMLResponse)
    async def partial_live(request: Request, symbol: str):
        orch = _orch(request)
        live = orch.get_pair_live_data(symbol)
        if live is None:
            live = {"running": False, "symbol": symbol, "events": [], "regime": "—",
                    "price": 0, "balance": 0, "uptime": 0, "tick_count": 0, "strategy": "—"}
        # Format uptime
        h, rem = divmod(live["uptime"], 3600)
        m, s = divmod(rem, 60)
        live["uptime_fmt"] = f"{h:02d}:{m:02d}:{s:02d}"
        return templates.TemplateResponse("partials/live_operation.html", {
            "request": request,
            "live": live,
        })

    @app.get("/partials/account-summary", response_class=HTMLResponse)
    async def partial_account_summary(request: Request):
        orch = _orch(request)
        statuses = await orch.get_all_status()
        balance = 0.0
        try:
            balance = await client.get_balance(config.trading.market2)
        except Exception:
            pass
        total_pnl = sum(s.get("realized_pnl", 0) + s.get("unrealized_pnl", 0) for s in statuses)
        active_count = sum(1 for s in statuses if s["status"] == "running")
        return templates.TemplateResponse("partials/account_summary.html", {
            "request": request,
            "balance": balance,
            "quote_asset": config.trading.market2,
            "total_pnl": total_pnl,
            "active_count": active_count,
            "total_count": len(statuses),
        })

    # -- API --

    @app.get("/api/pair/{symbol}/chart-data")
    async def chart_data(request: Request, symbol: str):
        orch = _orch(request)
        state = orch.pairs.get(symbol)

        # Get klines: prefer engine buffer, fallback to REST
        klines = []
        if state and state.engine and state.status == "running":
            klines = list(state.engine._kline_buffer)
        if not klines:
            try:
                klines = await client.get_klines(symbol, "1m", 150)
            except Exception as e:
                logger.error(f"Failed to fetch klines for {symbol}: {e}")
                return JSONResponse({"error": "no data"}, status_code=503)

        # Get trades within visible range
        trades = []
        if klines:
            try:
                all_trades = await db.get_trades(symbol, limit=50)
                t_start = int(klines[0]["open_time"]) / 1000
                t_end = int(klines[-1]["open_time"]) / 1000
                trades = [
                    t for t in all_trades
                    if t_start <= t["created_at"] <= t_end
                ]
            except Exception:
                pass

        return JSONResponse(compute_chart_data(klines, trades))

    # -- Actions --

    @app.post("/pair/{symbol}/start", response_class=HTMLResponse)
    async def start_pair(request: Request, symbol: str):
        orch = _orch(request)
        try:
            await orch.start_pair(symbol)
        except Exception as e:
            logger.error(f"Failed to start {symbol}: {e}")
        status = await orch.get_pair_status(symbol)
        return templates.TemplateResponse("partials/pair_card.html", {
            "request": request,
            "pair": status,
        })

    @app.post("/pair/{symbol}/stop", response_class=HTMLResponse)
    async def stop_pair(request: Request, symbol: str):
        orch = _orch(request)
        try:
            await orch.stop_pair(symbol)
        except Exception as e:
            logger.error(f"Failed to stop {symbol}: {e}")
        status = await orch.get_pair_status(symbol)
        return templates.TemplateResponse("partials/pair_card.html", {
            "request": request,
            "pair": status,
        })

    return app
