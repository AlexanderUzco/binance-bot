"""Live terminal dashboard display."""

import os
import sys
import time
from datetime import datetime


# ANSI escape codes
CLEAR_SCREEN = "\033[2J"
MOVE_HOME = "\033[H"
CLEAR_LINE = "\033[K"
CLEAR_BELOW = "\033[J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"


class Dashboard:
    """Live terminal dashboard that updates in place."""

    def __init__(self, symbol: str, strategy: str, testnet: bool):
        self.symbol = symbol
        self.strategy = strategy
        self.testnet = testnet
        self.start_time = datetime.now()
        self._events: list[str] = []  # Recent events log (last 8)

    def start(self):
        """Initialize display."""
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.write(CLEAR_SCREEN)
        sys.stdout.flush()

    def stop(self):
        """Restore terminal."""
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def add_event(self, event: str):
        """Add an event to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._events.append(f"{DIM}{timestamp}{RESET} {event}")
        if len(self._events) > 8:
            self._events = self._events[-8:]

    def render(
        self,
        price: float,
        balance: float,
        quote_asset: str,
        pnl: float,
        realized_pnl: float,
        unrealized_pnl: float,
        positions: list[dict],
        regime: str,
        total_trades: int,
        win_rate: float,
    ):
        """Render the full dashboard."""
        now = datetime.now()
        uptime = now - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        lines = []

        # Header
        mode = f"{RED}TESTNET{RESET}" if self.testnet else f"{GREEN}LIVE{RESET}"
        lines.append(f"{MOVE_HOME}")
        lines.append(f"  {BOLD}{CYAN}BinBot{RESET} {DIM}v2{RESET}  |  {self.symbol}  |  {self.strategy}  |  {mode}")
        lines.append(f"  {DIM}Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}  |  Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}{RESET}")
        lines.append(f"  {DIM}{'─' * 70}{RESET}")

        # Price & P&L
        pnl_color = GREEN if pnl > 0 else RED if pnl < 0 else WHITE
        pnl_sign = "+" if pnl > 0 else ""
        lines.append(f"  {BOLD}Price:{RESET}   ${price:,.2f}           {BOLD}Balance:{RESET} {balance:,.2f} {quote_asset}")
        lines.append(f"  {BOLD}P&L:{RESET}     {pnl_color}{pnl_sign}${pnl:,.4f}{RESET}          {BOLD}Regime:{RESET}  {regime}")
        lines.append(f"  {DIM}Realized: {pnl_sign if realized_pnl >= 0 else ''}{realized_pnl:,.4f}  |  Unrealized: {'+'if unrealized_pnl >= 0 else ''}{unrealized_pnl:,.4f}{RESET}")
        lines.append(f"  {DIM}Trades: {total_trades}  |  Win rate: {win_rate:.1f}%{RESET}")
        lines.append(f"  {DIM}{'─' * 70}{RESET}")

        # Positions
        lines.append(f"  {BOLD}Positions ({len(positions)}){RESET}")
        if positions:
            lines.append(f"  {DIM}{'#':<4} {'Entry':>12} {'Current':>12} {'Qty':>12} {'P&L':>12} {'Strategy':<12}{RESET}")
            for pos in positions[:8]:  # Max 8 visible
                entry = pos["entry_price"]
                qty = pos["quantity"]
                pos_pnl = (price - entry) * qty
                pos_pct = ((price - entry) / entry) * 100 if entry > 0 else 0
                c = GREEN if pos_pnl >= 0 else RED
                sign = "+" if pos_pnl >= 0 else ""
                lines.append(
                    f"  {pos['id']:<4} "
                    f"${entry:>11,.2f} "
                    f"${price:>11,.2f} "
                    f"{qty:>12.5f} "
                    f"{c}{sign}${pos_pnl:>10,.4f}{RESET} "
                    f"{pos.get('strategy', ''):<12}"
                )
            if len(positions) > 8:
                lines.append(f"  {DIM}... and {len(positions) - 8} more{RESET}")
        else:
            lines.append(f"  {DIM}  No open positions{RESET}")

        lines.append(f"  {DIM}{'─' * 70}{RESET}")

        # Events log
        lines.append(f"  {BOLD}Events{RESET}")
        if self._events:
            for event in self._events:
                lines.append(f"  {event}")
        else:
            lines.append(f"  {DIM}  Waiting for activity...{RESET}")

        lines.append(f"  {DIM}{'─' * 70}{RESET}")
        lines.append(f"  {DIM}Ctrl+C to stop{RESET}")

        # Render: move home, write each line clearing remainder, clear below
        output = MOVE_HOME
        for line in lines:
            output += line + CLEAR_LINE + "\n"
        output += CLEAR_BELOW

        sys.stdout.write(output)
        sys.stdout.flush()
