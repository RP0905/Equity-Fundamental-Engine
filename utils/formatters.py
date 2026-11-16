import pandas as pd

def calculate_cagr(series):
    series = series.dropna()
    if len(series) < 2:
        return None

    start = series.iloc[-1]
    end = series.iloc[0]
    years = len(series) - 1

    if start <= 0:
        return None

    return (end / start) ** (1 / years) - 1


def format_crore(value):
    if value is None or not isinstance(value, (int, float)):
        return "N/A"
    return f"₹ {value / 1e7:,.2f} Cr"


def format_percent(value):
    if value is None:
        return "N/A"
    return f"{value:.2f}%"