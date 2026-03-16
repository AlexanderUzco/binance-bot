"""Compute chart series for TradingView Lightweight Charts."""

from ..services.indicators import (
    ema,
    calc_bollinger,
    calc_rsi,
    calc_adx,
    calc_supertrend,
)


def compute_chart_data(klines: list[dict], trades: list[dict]) -> dict:
    """Build all series from raw klines + trades for the frontend.

    Returns dict with: candles, volume, ema9, ema21, bb_upper, bb_lower,
    supertrend, rsi, adx, plus_di, minus_di, markers.
    """
    if not klines:
        return {}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    # --- Candles & Volume ---
    candles = []
    volume = []
    for k in klines:
        t = int(k["open_time"]) // 1000  # ms -> s
        candles.append({
            "time": t,
            "open": k["open"],
            "high": k["high"],
            "low": k["low"],
            "close": k["close"],
        })
        is_green = k["close"] >= k["open"]
        volume.append({
            "time": t,
            "value": k["volume"],
            "color": "rgba(63,185,80,0.3)" if is_green else "rgba(248,81,73,0.3)",
        })

    # --- EMAs (full series, aligned to candle times) ---
    ema9_vals = ema(closes, 9)
    ema21_vals = ema(closes, 21)

    # ema() returns len(values) - period + 1 items, starting at index period-1
    ema9_series = [
        {"time": candles[i + 8]["time"], "value": round(v, 8)}
        for i, v in enumerate(ema9_vals)
    ]
    ema21_series = [
        {"time": candles[i + 20]["time"], "value": round(v, 8)}
        for i, v in enumerate(ema21_vals)
    ]

    # --- Bollinger Bands (rolling from index 19) ---
    bb_upper = []
    bb_lower = []
    for i in range(19, len(closes)):
        bb = calc_bollinger(closes[:i + 1], period=20)
        if bb:
            t = candles[i]["time"]
            bb_upper.append({"time": t, "value": bb.upper})
            bb_lower.append({"time": t, "value": bb.lower})

    # --- Supertrend (rolling, needs period*2+1 = 21 min) ---
    supertrend_series = []
    min_st = 22  # calc_supertrend needs period+2 min (period=10)
    for i in range(min_st, len(closes)):
        st = calc_supertrend(highs[:i + 1], lows[:i + 1], closes[:i + 1])
        if st:
            supertrend_series.append({
                "time": candles[i]["time"],
                "value": round(st.value, 8),
                "direction": st.direction,
            })

    # --- RSI (rolling, needs period+1 = 15 min) ---
    rsi_series = []
    for i in range(14, len(closes)):
        r = calc_rsi(closes[:i + 1])
        if r:
            rsi_series.append({"time": candles[i]["time"], "value": r.value})

    # --- ADX / +DI / -DI (rolling, needs period*2+1 = 29 min) ---
    adx_series = []
    plus_di_series = []
    minus_di_series = []
    min_adx = 29
    for i in range(min_adx, len(closes)):
        a = calc_adx(highs[:i + 1], lows[:i + 1], closes[:i + 1])
        if a:
            t = candles[i]["time"]
            adx_series.append({"time": t, "value": a.adx})
            plus_di_series.append({"time": t, "value": a.plus_di})
            minus_di_series.append({"time": t, "value": a.minus_di})

    # --- Trade markers ---
    markers = _build_markers(trades, klines)

    return {
        "candles": candles,
        "volume": volume,
        "ema9": ema9_series,
        "ema21": ema21_series,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "supertrend": supertrend_series,
        "rsi": rsi_series,
        "adx": adx_series,
        "plus_di": plus_di_series,
        "minus_di": minus_di_series,
        "markers": markers,
    }


def _build_markers(trades: list[dict], klines: list[dict]) -> list[dict]:
    """Map DB trades to LW Charts markers (arrows on the price chart)."""
    if not trades or not klines:
        return []

    # Time range of visible klines
    t_start = int(klines[0]["open_time"]) // 1000
    t_end = int(klines[-1]["open_time"]) // 1000

    markers = []
    for tr in trades:
        ts = int(tr["created_at"])  # already unix seconds
        if ts < t_start or ts > t_end:
            continue

        # Snap to nearest candle time (floor to minute)
        candle_time = ts - (ts % 60)

        is_buy = tr["side"].upper() == "BUY"
        markers.append({
            "time": candle_time,
            "position": "belowBar" if is_buy else "aboveBar",
            "color": "#3fb950" if is_buy else "#f85149",
            "shape": "arrowUp" if is_buy else "arrowDown",
            "text": f"{'B' if is_buy else 'S'} {tr.get('profit_pct', 0):+.1f}%",
        })

    # LW Charts requires markers sorted by time
    markers.sort(key=lambda m: m["time"])
    return markers
