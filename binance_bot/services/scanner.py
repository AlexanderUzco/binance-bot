"""Market scanner: analyzes multiple pairs and ranks them for trading."""

import asyncio
import logging
from dataclasses import dataclass

from .binance_client import BinanceClient
from .indicators import (
    calc_adx, calc_atr, calc_bollinger, calc_rsi,
    calc_volume_ratio, detect_regime,
)

logger = logging.getLogger("binance_bot.scanner")

# Top liquid USDT pairs to scan
DEFAULT_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "NEARUSDT", "SHIBUSDT", "LTCUSDT", "UNIUSDT",
    "ATOMUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    "BONKUSDT", "PEPEUSDT", "WIFUSDT", "INJUSDT", "FILUSDT",
]


@dataclass
class PairScore:
    symbol: str
    price: float
    regime: str
    adx: float
    rsi: float
    atr_pct: float  # volatility as % of price
    volume_ratio: float  # current vs avg volume
    volume_24h: float  # 24h quote volume in USDT
    spread_pct: float  # bid-ask spread %
    score: float  # composite score (higher = better for trading)
    strategy: str  # recommended strategy
    reason: str


async def scan_pairs(
    client: BinanceClient,
    pairs: list[str] | None = None,
    quote: str = "USDT",
    interval: str = "1m",
) -> list[PairScore]:
    """Scan multiple pairs and rank them by trading opportunity."""
    pairs = pairs or DEFAULT_PAIRS
    results: list[PairScore] = []

    # Fetch 24h tickers in bulk for volume data
    try:
        tickers_24h = {}
        for pair in pairs:
            try:
                t = await client.get_ticker_24h(pair)
                tickers_24h[pair] = t
            except Exception:
                continue
            await asyncio.sleep(0.1)  # Rate limit
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return []

    # Analyze each pair
    for symbol in pairs:
        try:
            ticker = tickers_24h.get(symbol)
            if not ticker:
                continue

            price = float(ticker.get("lastPrice", 0))
            volume_24h = float(ticker.get("quoteVolume", 0))

            # Skip low volume pairs (< $1M daily)
            if volume_24h < 1_000_000:
                continue

            # Get klines for technical analysis
            klines = await client.get_klines(symbol, interval, 150)
            if len(klines) < 50:
                continue

            closes = [k["close"] for k in klines]
            highs = [k["high"] for k in klines]
            lows = [k["low"] for k in klines]
            volumes = [k["volume"] for k in klines]

            # Indicators
            adx_result = calc_adx(highs, lows, closes)
            rsi_result = calc_rsi(closes)
            atr = calc_atr(highs, lows, closes)
            bb = calc_bollinger(closes)
            vol_ratio = calc_volume_ratio(volumes)
            regime = detect_regime(klines)

            adx_val = adx_result.adx if adx_result else 0
            rsi_val = rsi_result.value if rsi_result else 50
            atr_pct = (atr / price * 100) if atr and price > 0 else 0
            regime_name = regime.regime if regime else "unknown"

            # Bid-ask spread
            bid = float(ticker.get("bidPrice", 0))
            ask = float(ticker.get("askPrice", 0))
            spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 999

            # Score calculation
            score = _calculate_score(
                regime_name, adx_val, rsi_val, atr_pct,
                vol_ratio, volume_24h, spread_pct, bb, price,
            )

            # Recommend strategy
            strategy, reason = _recommend_strategy(
                regime_name, adx_val, rsi_val, atr_pct, bb, price,
            )

            results.append(PairScore(
                symbol=symbol,
                price=price,
                regime=regime_name,
                adx=round(adx_val, 1),
                rsi=round(rsi_val, 1),
                atr_pct=round(atr_pct, 3),
                volume_ratio=round(vol_ratio, 2),
                volume_24h=round(volume_24h, 0),
                spread_pct=round(spread_pct, 4),
                score=round(score, 1),
                strategy=strategy,
                reason=reason,
            ))

            await asyncio.sleep(0.15)  # Rate limit between pairs

        except Exception as e:
            logger.debug(f"Failed to analyze {symbol}: {e}")
            continue

    # Sort by score descending
    results.sort(key=lambda x: x.score, reverse=True)
    return results


def _calculate_score(
    regime: str, adx: float, rsi: float, atr_pct: float,
    vol_ratio: float, volume_24h: float, spread_pct: float,
    bb, price: float,
) -> float:
    """Calculate composite trading score (0-100)."""
    score = 50.0  # Base

    # Volume: higher is better (liquidity)
    if volume_24h > 100_000_000:
        score += 15
    elif volume_24h > 10_000_000:
        score += 10
    elif volume_24h > 1_000_000:
        score += 5

    # Current volume above average = more activity
    if vol_ratio > 2.0:
        score += 10
    elif vol_ratio > 1.3:
        score += 5

    # Spread: tighter is better
    if spread_pct < 0.02:
        score += 10
    elif spread_pct < 0.05:
        score += 5
    elif spread_pct > 0.2:
        score -= 15

    # Volatility (ATR%): sweet spot is 0.5-3%
    if 0.5 <= atr_pct <= 3.0:
        score += 10
    elif atr_pct > 5:
        score -= 5  # Too volatile

    # Regime-specific bonuses
    if regime == "ranging" and adx < 20:
        score += 10  # Great for grid
    elif regime == "trending_up" and adx > 30:
        score += 10  # Great for supertrend
    elif regime == "volatile_drop" and rsi < 30:
        score += 8  # DCA opportunity

    # RSI extremes = opportunity
    if rsi < 25 or rsi > 75:
        score += 5

    # Bollinger position
    if bb:
        if price < bb.lower:
            score += 5  # Potential bounce
        elif price > bb.upper:
            score += 3  # Momentum

    return max(0, min(100, score))


def _recommend_strategy(
    regime: str, adx: float, rsi: float, atr_pct: float,
    bb, price: float,
) -> tuple[str, str]:
    """Recommend strategy and explain why."""
    if regime == "volatile_drop" and rsi < 35:
        return "smart_dca", f"RSI={rsi:.0f} oversold + volatile drop, DCA to average in"

    if regime == "ranging" and adx < 25:
        return "grid", f"ADX={adx:.0f} ranging market, grid captures oscillations"

    if regime == "trending_up" and adx > 25:
        return "supertrend", f"ADX={adx:.0f} uptrend confirmed, ride the trend"

    if regime == "trending_down":
        return "hold", f"ADX={adx:.0f} downtrend, avoid new longs on spot"

    if bb and price < bb.lower and rsi < 40:
        return "smart_dca", f"Price below BB lower + RSI={rsi:.0f}, DCA opportunity"

    if adx < 20:
        return "grid", f"ADX={adx:.0f} very low trend, grid is safest"

    return "composite", f"Mixed signals (ADX={adx:.0f}, RSI={rsi:.0f}), let composite decide"


def format_scan_results(results: list[PairScore], top_n: int = 10) -> str:
    """Format scan results as a readable table."""
    if not results:
        return "No pairs analyzed"

    top = results[:top_n]

    lines = [
        f"{'Rank':<5} {'Pair':<12} {'Price':<12} {'Score':<7} {'Regime':<15} "
        f"{'ADX':<6} {'RSI':<6} {'ATR%':<7} {'Vol24h':<12} {'Strategy':<12} Reason",
        "-" * 130,
    ]

    for i, p in enumerate(top, 1):
        vol_str = f"${p.volume_24h/1e6:.1f}M" if p.volume_24h >= 1e6 else f"${p.volume_24h:,.0f}"

        # Color score
        if p.score >= 75:
            score_str = f"\033[92m{p.score}\033[0m"  # Green
        elif p.score >= 60:
            score_str = f"\033[93m{p.score}\033[0m"  # Yellow
        else:
            score_str = f"\033[91m{p.score}\033[0m"  # Red

        lines.append(
            f"  {i:<3} {p.symbol:<12} ${p.price:<10,.2f} {score_str:<16} {p.regime:<15} "
            f"{p.adx:<6} {p.rsi:<6} {p.atr_pct:<7} {vol_str:<12} {p.strategy:<12} {p.reason}"
        )

    # Top pick summary
    best = top[0]
    lines.append("")
    lines.append(f"Top pick: \033[1m{best.symbol}\033[0m (score {best.score}) → {best.strategy}")
    lines.append(f"  {best.reason}")

    return "\n".join(lines)
