import pandas as pd

def calculate_rsi(data, period=14):
    delta = data["Close"].diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def get_technicals(hist):
    df = hist.copy()

    if df.empty or len(df) < 20:
        return {"error": "Not enough data"}

    # EMA calculations
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA15"] = df["Close"].ewm(span=15).mean()
    df["EMA55"] = df["Close"].ewm(span=55).mean()

    # RSI
    df["RSI"] = calculate_rsi(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    result = {}

    # RSI
    rsi = latest["RSI"]
    result["rsi"] = round(rsi, 2)

    if rsi > 70:
        result["rsi_status"] = "Overbought"
    elif rsi < 30:
        result["rsi_status"] = "Oversold"
    else:
        result["rsi_status"] = "Neutral"

    # EMA crossover (9 & 15)
    if prev["EMA9"] < prev["EMA15"] and latest["EMA9"] > latest["EMA15"]:
        result["ema_crossover"] = "Bullish Crossover"
    elif prev["EMA9"] > prev["EMA15"] and latest["EMA9"] < latest["EMA15"]:
        result["ema_crossover"] = "Bearish Crossover"
    else:
        result["ema_crossover"] = "No Crossover"

    # Price vs EMA55
    if latest["Close"] > latest["EMA55"]:
        result["price_vs_ema55"] = "Above EMA55"
    else:
        result["price_vs_ema55"] = "Below EMA55"

    return result