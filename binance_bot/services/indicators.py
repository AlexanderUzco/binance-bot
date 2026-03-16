"""Pure Python technical indicators (no numpy/pandas dependency)."""

from dataclasses import dataclass


@dataclass
class BollingerBands:
    upper: float
    middle: float
    lower: float
    percent_b: float  # (price - lower) / (upper - lower)


@dataclass
class MACD:
    macd_line: float
    signal_line: float
    histogram: float


@dataclass
class RSIResult:
    value: float
    zone: str  # "oversold", "overbought", "neutral"


def ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for i in range(period, len(values)):
        result.append((values[i] - result[-1]) * multiplier + result[-1])
    return result


def sma(values: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    if len(values) < period:
        return []
    result = []
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def calc_rsi(closes: list[float], period: int = 14) -> RSIResult | None:
    """RSI using Wilder's smoothing method."""
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    if len(gains) < period:
        return None

    # Initial average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's smoothing
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    zone = "neutral"
    if rsi <= 30:
        zone = "oversold"
    elif rsi >= 70:
        zone = "overbought"

    return RSIResult(value=round(rsi, 2), zone=zone)


def calc_bollinger(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> BollingerBands | None:
    """Bollinger Bands calculation."""
    if len(closes) < period:
        return None

    recent = closes[-period:]
    middle = sum(recent) / period

    variance = sum((x - middle) ** 2 for x in recent) / period
    std = variance ** 0.5

    upper = middle + std_dev * std
    lower = middle - std_dev * std

    current_price = closes[-1]
    band_width = upper - lower
    percent_b = (current_price - lower) / band_width if band_width > 0 else 0.5

    return BollingerBands(
        upper=round(upper, 8),
        middle=round(middle, 8),
        lower=round(lower, 8),
        percent_b=round(percent_b, 4),
    )


def calc_macd(
    closes: list[float],
    fast: int = 12, slow: int = 26, signal: int = 9,
) -> MACD | None:
    """MACD calculation."""
    if len(closes) < slow + signal:
        return None

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    # Align lengths
    offset = len(ema_fast) - len(ema_slow)
    ema_fast = ema_fast[offset:]

    macd_line_values = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_values = ema(macd_line_values, signal)

    if not signal_values:
        return None

    macd_val = macd_line_values[-1]
    signal_val = signal_values[-1]

    return MACD(
        macd_line=round(macd_val, 8),
        signal_line=round(signal_val, 8),
        histogram=round(macd_val - signal_val, 8),
    )


def calc_emas(closes: list[float], periods: list[int] | None = None) -> dict[int, float]:
    """Calculate multiple EMAs."""
    if periods is None:
        periods = [9, 21, 50, 200]

    result = {}
    for p in periods:
        values = ema(closes, p)
        if values:
            result[p] = round(values[-1], 8)
    return result


def calc_volume_ratio(volumes: list[float], period: int = 20) -> float:
    """Current volume vs average volume ratio."""
    if len(volumes) < period + 1:
        return 1.0
    avg = sum(volumes[-period - 1:-1]) / period
    return round(volumes[-1] / avg, 2) if avg > 0 else 1.0


def find_support_resistance(
    highs: list[float], lows: list[float], lookback: int = 20
) -> dict:
    """Find support and resistance levels using local min/max."""
    if len(highs) < lookback or len(lows) < lookback:
        return {"support": [], "resistance": []}

    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # Find local peaks (resistance)
    resistance = []
    for i in range(1, len(recent_highs) - 1):
        if recent_highs[i] > recent_highs[i - 1] and recent_highs[i] > recent_highs[i + 1]:
            resistance.append(round(recent_highs[i], 8))

    # Find local troughs (support)
    support = []
    for i in range(1, len(recent_lows) - 1):
        if recent_lows[i] < recent_lows[i - 1] and recent_lows[i] < recent_lows[i + 1]:
            support.append(round(recent_lows[i], 8))

    # Sort and deduplicate (within 0.1% of each other)
    resistance = sorted(set(resistance), reverse=True)[:5]
    support = sorted(set(support))[:5]

    return {"support": support, "resistance": resistance}


def calc_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> float | None:
    """Average True Range."""
    if len(highs) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Wilder's smoothing for ATR
    atr = sum(true_ranges[:period]) / period
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period

    return round(atr, 8)


@dataclass
class ADXResult:
    adx: float
    plus_di: float
    minus_di: float
    trend_strength: str  # "none", "weak", "strong", "very_strong"


def calc_adx(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> ADXResult | None:
    """Average Directional Index with +DI/-DI."""
    if len(highs) < period * 2 + 1:
        return None

    # Calculate +DM, -DM, TR
    plus_dm_list = []
    minus_dm_list = []
    tr_list = []

    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
        minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
        tr_list.append(tr)

    if len(tr_list) < period:
        return None

    # Wilder's smoothing for +DM, -DM, TR
    smooth_plus_dm = sum(plus_dm_list[:period])
    smooth_minus_dm = sum(minus_dm_list[:period])
    smooth_tr = sum(tr_list[:period])

    dx_list = []

    for i in range(period, len(tr_list)):
        smooth_plus_dm = smooth_plus_dm - (smooth_plus_dm / period) + plus_dm_list[i]
        smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / period) + minus_dm_list[i]
        smooth_tr = smooth_tr - (smooth_tr / period) + tr_list[i]

        plus_di = (smooth_plus_dm / smooth_tr) * 100 if smooth_tr > 0 else 0
        minus_di = (smooth_minus_dm / smooth_tr) * 100 if smooth_tr > 0 else 0

        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
        dx_list.append(dx)

    if len(dx_list) < period:
        return None

    # ADX = smoothed DX
    adx = sum(dx_list[:period]) / period
    for i in range(period, len(dx_list)):
        adx = (adx * (period - 1) + dx_list[i]) / period

    # Final +DI/-DI
    final_plus_di = (smooth_plus_dm / smooth_tr) * 100 if smooth_tr > 0 else 0
    final_minus_di = (smooth_minus_dm / smooth_tr) * 100 if smooth_tr > 0 else 0

    if adx < 20:
        strength = "none"
    elif adx < 25:
        strength = "weak"
    elif adx < 50:
        strength = "strong"
    else:
        strength = "very_strong"

    return ADXResult(
        adx=round(adx, 2),
        plus_di=round(final_plus_di, 2),
        minus_di=round(final_minus_di, 2),
        trend_strength=strength,
    )


@dataclass
class SupertrendResult:
    value: float
    direction: str  # "up" (bullish) or "down" (bearish)
    flipped: bool  # True if direction changed on this candle


def calc_supertrend(
    highs: list[float], lows: list[float], closes: list[float],
    period: int = 10, multiplier: float = 3.0,
) -> SupertrendResult | None:
    """Supertrend indicator."""
    atr = calc_atr(highs, lows, closes, period)
    if atr is None or len(closes) < period + 2:
        return None

    # Calculate for last few candles to detect flip
    # We need at least 2 values to detect direction change
    results = []
    prev_upper = 0.0
    prev_lower = 0.0
    prev_direction = "up"
    prev_supertrend = 0.0

    for i in range(period, len(closes)):
        hl2 = (highs[i] + lows[i]) / 2

        # Recalculate ATR for this position (simplified: use global ATR)
        basic_upper = hl2 + multiplier * atr
        basic_lower = hl2 - multiplier * atr

        # Final upper band: min of current and previous (if previous was valid)
        if prev_upper > 0:
            final_upper = min(basic_upper, prev_upper) if closes[i - 1] <= prev_upper else basic_upper
        else:
            final_upper = basic_upper

        # Final lower band: max of current and previous
        if prev_lower > 0:
            final_lower = max(basic_lower, prev_lower) if closes[i - 1] >= prev_lower else basic_lower
        else:
            final_lower = basic_lower

        # Direction
        if prev_supertrend == prev_upper:
            direction = "up" if closes[i] > final_upper else "down"
        else:
            direction = "down" if closes[i] < final_lower else "up"

        supertrend = final_lower if direction == "up" else final_upper
        flipped = direction != prev_direction and prev_direction != ""

        prev_upper = final_upper
        prev_lower = final_lower
        prev_direction = direction
        prev_supertrend = supertrend

        results.append((supertrend, direction, flipped))

    if not results:
        return None

    last = results[-1]
    prev = results[-2] if len(results) > 1 else results[-1]

    return SupertrendResult(
        value=round(last[0], 8),
        direction=last[1],
        flipped=last[1] != prev[1],
    )


@dataclass
class MarketRegime:
    regime: str  # "ranging", "trending_up", "trending_down", "volatile_drop"
    adx: ADXResult | None
    bollinger: BollingerBands | None
    atr_pct: float  # ATR as % of price
    confidence: float  # 0-1
    rsi: RSIResult | None = None


# Hysteresis thresholds to prevent regime flipping on ADX oscillation
_ADX_TRENDING_ENTER = 28  # ADX must exceed this to switch TO trending
_ADX_TRENDING_EXIT = 22   # ADX must drop below this to switch back to ranging
_last_regime: str = "ranging"


def detect_regime(klines: list[dict]) -> MarketRegime | None:
    """Detect current market regime to select appropriate strategy.

    Uses hysteresis on ADX to prevent rapid regime flipping when ADX
    oscillates around a single threshold.
    """
    global _last_regime

    if not klines or len(klines) < 50:
        return None

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    price = closes[-1]

    adx = calc_adx(highs, lows, closes)
    bb = calc_bollinger(closes)
    atr = calc_atr(highs, lows, closes)
    rsi = calc_rsi(closes)

    atr_pct = (atr / price) * 100 if atr and price > 0 else 0

    # Decision logic
    if adx is None:
        _last_regime = "ranging"
        return MarketRegime("ranging", adx, bb, atr_pct, 0.3, rsi)

    # Volatile drop: price below BB lower + RSI oversold + elevated ATR
    # Relaxed: RSI < 40 (was 35) and ATR > 1.5% (was 2%)
    if (bb and price < bb.lower
            and rsi and rsi.value < 40
            and atr_pct > 1.5):
        confidence = min(1.0, (40 - rsi.value) / 25 + (atr_pct - 1.5) / 3)
        _last_regime = "volatile_drop"
        return MarketRegime("volatile_drop", adx, bb, atr_pct, round(confidence, 2), rsi)

    # Hysteresis for trending vs ranging:
    # - If currently ranging, need ADX > _ADX_TRENDING_ENTER to switch to trending
    # - If currently trending, need ADX < _ADX_TRENDING_EXIT to switch back to ranging
    was_trending = _last_regime in ("trending_up", "trending_down")

    if was_trending:
        is_trending = adx.adx > _ADX_TRENDING_EXIT
    else:
        is_trending = adx.adx > _ADX_TRENDING_ENTER

    if is_trending:
        if adx.plus_di > adx.minus_di:
            confidence = min(1.0, (adx.adx - 20) / 30)
            _last_regime = "trending_up"
            return MarketRegime("trending_up", adx, bb, atr_pct, round(confidence, 2), rsi)
        else:
            confidence = min(1.0, (adx.adx - 20) / 30)
            _last_regime = "trending_down"
            return MarketRegime("trending_down", adx, bb, atr_pct, round(confidence, 2), rsi)

    # Ranging
    confidence = min(1.0, (_ADX_TRENDING_ENTER - adx.adx) / 15)
    _last_regime = "ranging"
    return MarketRegime("ranging", adx, bb, atr_pct, round(confidence, 2), rsi)


@dataclass
class FullAnalysis:
    rsi: RSIResult | None
    bollinger: BollingerBands | None
    macd: MACD | None
    emas: dict[int, float]
    volume_ratio: float
    atr: float | None
    adx: ADXResult | None
    supertrend: SupertrendResult | None
    regime: MarketRegime | None
    support_resistance: dict
    current_price: float


def full_analysis(klines: list[dict]) -> FullAnalysis | None:
    """Run all indicators on kline data."""
    if not klines or len(klines) < 50:
        return None

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    regime = detect_regime(klines)
    rsi = calc_rsi(closes)

    return FullAnalysis(
        rsi=rsi,
        bollinger=calc_bollinger(closes),
        macd=calc_macd(closes),
        emas=calc_emas(closes),
        volume_ratio=calc_volume_ratio(volumes),
        atr=calc_atr(highs, lows, closes),
        adx=calc_adx(highs, lows, closes),
        supertrend=calc_supertrend(highs, lows, closes),
        regime=regime,
        support_resistance=find_support_resistance(highs, lows),
        current_price=closes[-1],
    )
