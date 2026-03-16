"""CLI interface for the trading bot."""

import argparse
import asyncio
import logging
import sys

from .config import load_config
from .engine import TradingEngine
from .strategies import STRATEGIES


def setup_logging(level: str = "INFO", log_file: str | None = None, dashboard: bool = False):
    handlers = []

    if dashboard:
        # Dashboard mode: only log to file (stdout is used by the dashboard)
        if not log_file:
            log_file = "binbot.log"
        handlers.append(logging.FileHandler(log_file))
    else:
        handlers.append(logging.StreamHandler(sys.stdout))
        if log_file:
            handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="Binance Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategies:
  composite      Auto-switches between strategies based on market regime (recommended)
  grid           Grid trading for ranging markets (ADX < 25)
  smart_dca      Smart DCA with safety orders for dips (RSI + BB trigger)
  supertrend     Supertrend trend following (ADX > 25 filter)
  price_action   Price % change (original base strategy)
  bollinger      Bollinger Bands with optional RSI filter
  bollinger_ma   Bollinger Bands + MA trailing stop
  ema_crossover  EMA 9/21 crossover with trend filter

Examples:
  python -m binance_bot run --strategy bollinger_ma
  python -m binance_bot run --strategy ema_crossover --env .env.testnet
  python -m binance_bot status
  python -m binance_bot stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Start the trading bot")
    run_parser.add_argument(
        "--strategy", "-s",
        choices=list(STRATEGIES.keys()),
        default="composite",
        help="Trading strategy (default: composite)",
    )
    run_parser.add_argument(
        "--env", "-e",
        default=None,
        help="Path to .env file (default: .env in current dir)",
    )
    run_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    run_parser.add_argument(
        "--log-file",
        default=None,
        help="Log to file in addition to stdout",
    )
    run_parser.add_argument(
        "--no-websocket",
        action="store_true",
        help="Use REST polling instead of WebSocket",
    )
    run_parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable live dashboard, use scrolling logs instead",
    )

    # Status command
    subparsers.add_parser("status", help="Show bot status")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show trading statistics")
    stats_parser.add_argument("--env", "-e", default=None)

    # Positions command
    pos_parser = subparsers.add_parser("positions", help="Show open positions")
    pos_parser.add_argument("--env", "-e", default=None)

    # Trades command
    trades_parser = subparsers.add_parser("trades", help="Show trade history")
    trades_parser.add_argument("--limit", "-n", type=int, default=20)
    trades_parser.add_argument("--env", "-e", default=None)

    # Web command
    web_parser = subparsers.add_parser("web", help="Start web dashboard")
    web_parser.add_argument("--host", default="0.0.0.0")
    web_parser.add_argument("--port", type=int, default=8080)
    web_parser.add_argument("--env", "-e", default=None)
    web_parser.add_argument("--pairs", default=None, help="Path to pairs.json")
    web_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        use_dashboard = not args.no_dashboard
        setup_logging(args.log_level, args.log_file, dashboard=use_dashboard)
        config = load_config(args.env)

        strategy_cls = STRATEGIES[args.strategy]
        strategy = strategy_cls(config.strategy, config.trading)

        engine = TradingEngine(config, strategy)
        if args.no_websocket:
            engine._use_websocket = False
        if args.no_dashboard:
            engine._use_dashboard = False

        try:
            asyncio.run(engine.start())
        except KeyboardInterrupt:
            pass  # Shutdown already handled by signal handler

    elif args.command == "status":
        _show_status(args)

    elif args.command == "stats":
        _show_stats(args)

    elif args.command == "positions":
        _show_positions(args)

    elif args.command == "trades":
        _show_trades(args)

    elif args.command == "web":
        _start_web(args)


def _show_status(args):
    """Show current bot status from database."""
    config = load_config(getattr(args, "env", None))

    async def _run():
        from .database import Database
        db = Database(config.db_path)
        await db.connect()

        positions = await db.get_open_positions()
        stats = await db.get_stats()
        initial = await db.get_state(f"initial_balance:{config.trading.symbol}", "N/A")

        print(f"Symbol: {config.trading.symbol}")
        print(f"Initial balance: {initial}")
        print(f"Open positions: {len(positions)}")
        print(f"Total trades: {stats['total_trades']}")
        print(f"Win rate: {stats['win_rate']:.1f}%")
        print(f"Total profit: {stats['total_profit']}")
        await db.close()

    asyncio.run(_run())


def _show_stats(args):
    config = load_config(getattr(args, "env", None))

    async def _run():
        from .database import Database
        db = Database(config.db_path)
        await db.connect()
        stats = await db.get_stats()

        print(f"--- Trading Stats ({config.trading.symbol}) ---")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        await db.close()

    asyncio.run(_run())


def _show_positions(args):
    config = load_config(getattr(args, "env", None))

    async def _run():
        from .database import Database
        db = Database(config.db_path)
        await db.connect()
        positions = await db.get_open_positions()

        if not positions:
            print("No open positions")
            return

        print(f"--- Open Positions ({config.trading.symbol}) ---")
        for p in positions:
            print(
                f"  #{p['id']} | entry={p['entry_price']} qty={p['quantity']} "
                f"tp={p['sell_target']} sl={p['stop_loss']} strategy={p['strategy']}"
            )
        await db.close()

    asyncio.run(_run())


def _show_trades(args):
    config = load_config(getattr(args, "env", None))

    async def _run():
        from .database import Database
        db = Database(config.db_path)
        await db.connect()
        trades = await db.get_trades(limit=args.limit)

        if not trades:
            print("No trades yet")
            return

        print(f"--- Last {len(trades)} Trades ---")
        for t in trades:
            pnl = f"+{t['profit']}" if t['profit'] > 0 else str(t['profit'])
            print(
                f"  {t['side']} {t['symbol']} | "
                f"entry={t['entry_price']} exit={t['exit_price']} "
                f"qty={t['quantity']} P&L={pnl} ({t['profit_pct']:.2f}%) "
                f"strategy={t['strategy']}"
            )
        await db.close()

    asyncio.run(_run())


def _start_web(args):
    """Start the web dashboard."""
    import uvicorn

    setup_logging(args.log_level)
    from .web.app import create_app

    app = create_app(env_path=args.env, pairs_path=args.pairs)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
