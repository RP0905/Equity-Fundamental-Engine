import pandas as pd
import numpy as np
from utils.formatters import format_percent


def calculate_rsi(data, period=14):
    delta = data["Close"].diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_macd(data):
    """Compute MACD line, signal line, and return the crossover signal."""
    ema12 = data["Close"].ewm(span=12).mean()
    ema26 = data["Close"].ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()

    if len(data) < 2:
        return "Neutral"

    prev_macd = macd_line.iloc[-2]
    prev_signal = signal_line.iloc[-2]
    curr_macd = macd_line.iloc[-1]
    curr_signal = signal_line.iloc[-1]

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return "Bullish"
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        return "Bearish"
    else:
        return "Neutral"


def calculate_obv(data):
    """On-Balance Volume."""
    obv = [0]
    for i in range(1, len(data)):
        if data["Close"].iloc[i] > data["Close"].iloc[i - 1]:
            obv.append(obv[-1] + data["Volume"].iloc[i])
        elif data["Close"].iloc[i] < data["Close"].iloc[i - 1]:
            obv.append(obv[-1] - data["Volume"].iloc[i])
        else:
            obv.append(obv[-1])
    return obv[-1]


def get_technicals(hist):
    df = hist.copy()

    if df.empty or len(df) < 20:
        return {"error": "Not enough data"}

    # EMA calculations
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA15"] = df["Close"].ewm(span=15).mean()
    df["EMA55"] = df["Close"].ewm(span=55).mean()

    # SMA calculations
    df["SMA20"] = df["Close"].rolling(window=20).mean()
    df["SMA50"] = df["Close"].rolling(window=50).mean()
    df["SMA200"] = df["Close"].rolling(window=200).mean()

    # RSI
    df["RSI"] = calculate_rsi(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    result = {}

    # ── RSI ──────────────────────────────────────────────────────────────
    rsi = latest["RSI"]
    result["rsi"] = round(rsi, 2)

    if rsi > 70:
        result["rsi_status"] = "Overbought"
    elif rsi < 30:
        result["rsi_status"] = "Oversold"
    else:
        result["rsi_status"] = "Neutral"

    # ── EMA crossover (9 & 15) ──────────────────────────────────────────
    if prev["EMA9"] < prev["EMA15"] and latest["EMA9"] > latest["EMA15"]:
        result["ema_crossover"] = "Bullish Crossover"
    elif prev["EMA9"] > prev["EMA15"] and latest["EMA9"] < latest["EMA15"]:
        result["ema_crossover"] = "Bearish Crossover"
    else:
        result["ema_crossover"] = "No Crossover"

    # ── Price vs EMA55 ──────────────────────────────────────────────────
    if latest["Close"] > latest["EMA55"]:
        result["price_vs_ema55"] = "Above EMA55"
    else:
        result["price_vs_ema55"] = "Below EMA55"

    # ── Trend using EMA slope ────────────────────────────────────────────
    ema55_slope = df["EMA55"].iloc[-1] - df["EMA55"].iloc[-5]
    if ema55_slope > 0:
        result["trend"] = "Uptrend"
    else:
        result["trend"] = "Downtrend"

    # ── MACD ─────────────────────────────────────────────────────────────
    result["macdSignal"] = calculate_macd(df)

    # ── 200 DMA (above/below) ────────────────────────────────────────────
    above_200dma = None
    if not np.isnan(latest.get("SMA200", np.nan)):
        above_200dma = bool(latest["Close"] > latest["SMA200"])
    result["above200Dma"] = above_200dma

    # ── From 52-week high percentage ────────────────────────────────────
    if len(df) >= 252:
        year_high = df["Close"].tail(252).max()
    else:
        year_high = df["Close"].max()
    if year_high > 0:
        result["from52WeekHighPct"] = round(((latest["Close"] - year_high) / year_high) * 100, 2)
    else:
        result["from52WeekHighPct"] = 0.0

    # ── Relative returns (1M, 3M, 6M, 1Y) ────────────────────────────────
    returns = {}
    periods = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}

    for label, days in periods.items():
        if len(df) >= days:
            old_close = df["Close"].iloc[-days]
            if old_close > 0:
                returns[label] = round(((latest["Close"] - old_close) / old_close) * 100, 2)
            else:
                returns[label] = None
        else:
            returns[label] = None
    result["returns"] = returns

    # ── SMAs ─────────────────────────────────────────────────────────────
    result["sma20"] = round(latest["SMA20"], 2) if not np.isnan(latest.get("SMA20", np.nan)) else None
    result["sma50"] = round(latest["SMA50"], 2) if not np.isnan(latest.get("SMA50", np.nan)) else None
    result["sma200"] = round(latest["SMA200"], 2) if not np.isnan(latest.get("SMA200", np.nan)) else None

    # ── OBV (On-Balance Volume) ─────────────────────────────────────────
    result["obv"] = calculate_obv(df)

    # ── Volume (latest) ──────────────────────────────────────────────────
    result["volume"] = int(latest["Volume"]) if not np.isnan(latest.get("Volume", np.nan)) else None

    # ── Keep existing keys for backward compat ──────────────────────────
    result["ema_crossover"] = result.get("ema_crossover", "No Crossover")
    result["price_vs_ema55"] = result.get("price_vs_ema55", "Below EMA55")
    result["trend"] = result.get("trend", "Neutral")

    return result