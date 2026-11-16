from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import json
import numpy as np
import pandas as pd
import requests
import os
import subprocess
from pathlib import Path
import re
import threading

# â”€â”€ Google Sheets services (primary data source) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from services.google_sheets_service import build_sheet_payload, search_master_index
from services.screener_csv_importer import import_screener_csv
from services.screener_local_service import (
    get_local_screener_status,
    run_local_screener,
    sync_screener_symbol,
    sync_screener_universe,
)

# â”€â”€ yfinance services (fallback) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from services.yf_services import get_stock_data
from analysis.technicals import get_technicals
from analysis.old_engine import get_old_data
from analysis.fundamentals import get_fundamentals

import yfinance as yf

app = Flask(__name__, static_folder=None)
CORS(app)
SPREADSHEET_METRIC_CACHE_PATH = Path(__file__).resolve().parent / "screener_metric_cache.jsonl"
YAHOO_METRIC_CACHE_PATH = Path(__file__).resolve().parent / "screener_yahoo_metric_cache.jsonl"
AI_AGENT_ROOT = Path(__file__).resolve().parent.parent / "Projects" / "Stock-Market-Agent"
AI_AGENT_BACKEND = "http://127.0.0.1:8000"
AI_AGENT_FRONTEND = "http://127.0.0.1:5173"
AI_AGENT_PROCESSES = []
RISKDESK_ROOT = Path(__file__).resolve().parent.parent / "Projects" / "riskdesk"
RISKDESK_BACKEND = "http://127.0.0.1:8001"
RISKDESK_FRONTEND = "http://127.0.0.1:5174"
RISKDESK_PROCESSES = []
TRADE_JOURNAL_ROOT = Path(__file__).resolve().parent / "Trade Journal"
TRADE_JOURNAL_FRONTEND = "http://127.0.0.1:4173"
TRADE_JOURNAL_PROCESSES = []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def sanitize_json(value):
    """Recursively sanitize a JSON-serialisable structure, converting
    numpy types to plain Python types and filtering NaN / Inf."""
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json(item) for item in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
    return value


def _url_is_live(url, timeout=1.5):
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code < 500
    except Exception:
        return False


def _start_hidden_process(args, cwd, log_name, env=None, log_root=AI_AGENT_ROOT):
    log_path = log_root / log_name
    log_file = open(log_path, "a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    AI_AGENT_PROCESSES.append((process, log_file))
    return process


def _start_ai_agent_servers():
    if not AI_AGENT_ROOT.exists():
        return False, f"AI project folder not found: {AI_AGENT_ROOT}"

    backend_dir = AI_AGENT_ROOT / "backend"
    frontend_dir = AI_AGENT_ROOT / "frontend"
    python_exe = AI_AGENT_ROOT / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        return False, f"AI agent virtual environment not found: {python_exe}"
    if not (frontend_dir / "package.json").exists():
        return False, f"AI agent frontend package.json not found: {frontend_dir}"

    backend_live = _url_is_live(f"{AI_AGENT_BACKEND}/docs")
    frontend_live = _url_is_live(AI_AGENT_FRONTEND)

    if not backend_live:
        _start_hidden_process(
            [str(python_exe), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
            backend_dir,
            "ai-agent-backend.log",
        )

    if not frontend_live:
        env = os.environ.copy()
        env["VITE_API_BASE"] = AI_AGENT_BACKEND
        _start_hidden_process(
            ["cmd.exe", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
            frontend_dir,
            "ai-agent-frontend.log",
            env=env,
        )

    return True, "AI agent launch requested."


def _start_riskdesk_servers():
    if not RISKDESK_ROOT.exists():
        return False, f"RiskDesk project folder not found: {RISKDESK_ROOT}"

    backend_dir = RISKDESK_ROOT / "backend"
    frontend_dir = RISKDESK_ROOT
    if not (backend_dir / "app" / "main.py").exists():
        return False, f"RiskDesk backend was not found: {backend_dir}"
    if not (frontend_dir / "package.json").exists():
        return False, f"RiskDesk frontend package.json not found: {frontend_dir}"

    python_exe = (subprocess.check_output(["where", "python"], text=True).splitlines() or ["python"])[0].strip()

    backend_live = _url_is_live(f"{RISKDESK_BACKEND}/health")
    frontend_live = _url_is_live(RISKDESK_FRONTEND)

    if not backend_live:
        dependency_check = subprocess.run(
            [python_exe, "-c", "import fastapi, uvicorn, sqlalchemy, pydantic_settings, aiosqlite"],
            cwd=str(backend_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if dependency_check.returncode != 0:
            install_result = subprocess.run(
                [python_exe, "-m", "pip", "install", "-r", str(backend_dir / "requirements.txt")],
                cwd=str(backend_dir),
            )
            if install_result.returncode != 0:
                return False, "RiskDesk backend dependency installation failed."

        env = os.environ.copy()
        env["CORS_ORIGINS"] = f"http://localhost:5174,http://127.0.0.1:5174"
        process = _start_hidden_process(
            [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
            backend_dir,
            "riskdesk-backend.log",
            env=env,
            log_root=RISKDESK_ROOT,
        )
        RISKDESK_PROCESSES.append(process)

    if not frontend_live:
        if not (frontend_dir / "node_modules").exists():
            install_result = subprocess.run(["cmd.exe", "/c", "npm", "install"], cwd=str(frontend_dir))
            if install_result.returncode != 0:
                return False, "RiskDesk frontend dependency installation failed."

        env = os.environ.copy()
        env["VITE_API_BASE"] = RISKDESK_BACKEND
        process = _start_hidden_process(
            ["cmd.exe", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5174"],
            frontend_dir,
            "riskdesk-frontend.log",
            env=env,
            log_root=RISKDESK_ROOT,
        )
        RISKDESK_PROCESSES.append(process)

    return True, "RiskDesk launch requested."


def _find_node_executable():
    bundled = Path(os.environ.get("USERPROFILE", "")) / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if bundled.exists():
        return str(bundled)
    try:
        return (subprocess.check_output(["where", "node"], text=True).splitlines() or ["node"])[0].strip()
    except Exception:
        return "node"


def _start_trade_journal_servers():
    if not TRADE_JOURNAL_ROOT.exists():
        return False, f"Trade Journal project folder not found: {TRADE_JOURNAL_ROOT}"

    server_script = TRADE_JOURNAL_ROOT / "scripts" / "serve.mjs"
    if not server_script.exists():
        return False, f"Trade Journal server script not found: {server_script}"

    if _url_is_live(TRADE_JOURNAL_FRONTEND):
        return True, "Trade Journal is already running."

    node_exe = _find_node_executable()
    process = _start_hidden_process(
        [node_exe, str(server_script)],
        TRADE_JOURNAL_ROOT,
        "trade-journal.log",
        log_root=TRADE_JOURNAL_ROOT,
    )
    TRADE_JOURNAL_PROCESSES.append(process)

    return True, "Trade Journal launch requested."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  BLOOMBERG-FRONTEND API  (Google Sheets primary)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/search", methods=["GET"])
def search():
    """Search the master index (Google Sheets)."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    try:
        return jsonify(search_master_index(query))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/analyze", methods=["GET"])
def analyze():
    """Full analysis payload consumed by the Bloomberg-style frontend.

    Uses the Google Sheets service as the primary data source (via
    ``build_sheet_payload``) and falls back to yahoo-finance data when
    sheet data is unavailable.
    """
    query = (
        request.args.get("ticker", "").strip()
        or request.args.get("q", "").strip()
    )
    if not query:
        return jsonify({"error": "No company name provided"}), 400

    try:
        payload = build_sheet_payload(query, get_stock_data, get_technicals)
        if not payload:
            return jsonify({"error": "TICKER NOT FOUND IN INDEX"}), 404
        return jsonify(sanitize_json(payload))
    except Exception as exc:
        import traceback
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


@app.route("/api/price-history", methods=["GET"])
def price_history():
    """OHLCV price history for the candlestick/line chart."""
    symbol = request.args.get("symbol", "").strip().upper()
    period = request.args.get("period", "1y")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    # Map well-known indices to the correct yfinance ticker
    INDEX_MAP = {
        "NIFTY50": "^NSEI",
        "NIFTY": "^NSEI",
        "SENSEX": "^BSESN",
        "BANKNIFTY": "^NSEBANK",
    }
    yf_symbol = INDEX_MAP.get(symbol)
    if yf_symbol is None:
        yf_symbol = symbol

    try:
        stock = yf.Ticker(yf_symbol)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            return jsonify({"error": "No data"}), 404
        records = []
        for _unused, row in df.iterrows():
            ts_seconds = int(row.name.timestamp()) if hasattr(row.name, "timestamp") else 0
            records.append({
                "time": ts_seconds,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return jsonify({"symbol": yf_symbol, "data": records})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/peers", methods=["GET"])
def peers():
    """Return peer comparison data for a given symbol."""
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        peers_raw = info.get("peerSymbols", []) or ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]
        peer_list = []
        for ps in peers_raw[:8]:
            try:
                ps_str = ps.strip().upper()
                pstock = yf.Ticker(ps_str)
                pinfo = pstock.info or {}
                peer_list.append({
                    "ticker": ps_str.replace(".NS", ""),
                    "price": pinfo.get("currentPrice") or pinfo.get("regularMarketPrice"),
                    "pe": pinfo.get("trailingPE"),
                    "mktCap": pinfo.get("marketCap"),
                })
            except Exception:
                continue
        return jsonify({"peers": peer_list})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/screener", methods=["POST"])
def screener():
    """Screen stocks using the Excel/Google-Sheets pipeline by default."""
    try:
        filters = request.get_json(silent=True) or {}
        print("=== Screener received filters ===")
        print(filters)
        
        use_local = filters.get("use_local_db", False)
        if use_local:
            print("[screener] Using LOCAL DB engine")
            out = run_local_screener(filters)
        else:
            print("[screener] Using EXCEL + YAHOO engine")
            out = run_google_sheets_screener(filters)
            
        print("=== Screener out ===")
        results = out.get("results", [])
        count = out.get("count", len(results))
        print(f"Count: {count}")
        print(f"Results: {len(results)}")

        return jsonify({
            "count": count,
            "results": results,
            "screen_meta": out.get("meta", {}),
        })
    except Exception as exc:
        import traceback
        print("=== Screener ERROR ===")
        print(str(exc))
        print(traceback.format_exc())
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


@app.route("/api/screener/db-status", methods=["GET"])
def screener_db_status():
    """Check local screener DB status."""
    try:
        return jsonify(get_local_screener_status())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/screener/sync", methods=["POST"])
def screener_sync():
    """Sync one or many symbols into the local screener DB."""
    try:
        payload = request.get_json(silent=True) or {}
        symbol = (payload.get("symbol") or "").strip().upper()
        limit = payload.get("limit")
        include_technicals = bool(payload.get("include_technicals", False))

        if symbol:
            result = sync_screener_symbol(symbol, include_technicals=include_technicals)
            return jsonify({"ok": True, "symbol": symbol, "stock": result["stock"]})

        result = sync_screener_universe(limit=limit, include_technicals=include_technicals)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/screener/import-csv", methods=["POST"])
def screener_import_csv():
    """Import screener CSV export into local DB."""
    try:
        payload = request.get_json(silent=True) or {}
        csv_path = (payload.get("csv_path") or "").strip()
        if not csv_path:
            return jsonify({"error": "csv_path is required"}), 400
        result = import_screener_csv(csv_path)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ai-agent/status", methods=["GET"])
def ai_agent_status():
    """Report whether the separate Stock-Market-Agent app is reachable."""
    return jsonify({
        "backend_url": AI_AGENT_BACKEND,
        "frontend_url": AI_AGENT_FRONTEND,
        "backend_live": _url_is_live(f"{AI_AGENT_BACKEND}/docs"),
        "frontend_live": _url_is_live(AI_AGENT_FRONTEND),
        "project_path": str(AI_AGENT_ROOT),
    })


@app.route("/api/ai-agent/start", methods=["POST"])
def ai_agent_start():
    """Start the separate Stock-Market-Agent without merging it into EFE."""
    ok, message = _start_ai_agent_servers()
    status_code = 202 if ok else 500
    return jsonify({
        "ok": ok,
        "message": message,
        "backend_url": AI_AGENT_BACKEND,
        "frontend_url": AI_AGENT_FRONTEND,
    }), status_code


@app.route("/api/riskdesk/status", methods=["GET"])
def riskdesk_status():
    """Report whether the separate RiskDesk app is reachable."""
    return jsonify({
        "backend_url": RISKDESK_BACKEND,
        "frontend_url": RISKDESK_FRONTEND,
        "backend_live": _url_is_live(f"{RISKDESK_BACKEND}/health"),
        "frontend_live": _url_is_live(RISKDESK_FRONTEND),
        "project_path": str(RISKDESK_ROOT),
    })


@app.route("/api/riskdesk/start", methods=["POST"])
def riskdesk_start():
    """Start the separate RiskDesk app without merging it into EFE."""
    ok, message = _start_riskdesk_servers()
    status_code = 202 if ok else 500
    return jsonify({
        "ok": ok,
        "message": message,
        "backend_url": RISKDESK_BACKEND,
        "frontend_url": RISKDESK_FRONTEND,
    }), status_code


@app.route("/api/trade-journal/status", methods=["GET"])
def trade_journal_status():
    """Report whether the separate Trade Journal app is reachable."""
    return jsonify({
        "frontend_url": TRADE_JOURNAL_FRONTEND,
        "frontend_live": _url_is_live(TRADE_JOURNAL_FRONTEND),
        "project_path": str(TRADE_JOURNAL_ROOT),
    })


@app.route("/api/trade-journal/start", methods=["POST"])
def trade_journal_start():
    """Start the separate Trade Journal app without merging it into EFE."""
    ok, message = _start_trade_journal_servers()
    status_code = 202 if ok else 500
    return jsonify({
        "ok": ok,
        "message": message,
        "frontend_url": TRADE_JOURNAL_FRONTEND,
    }), status_code


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  LEGACY ROUTES  (old template-based / yfinance views)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/analyze-view", methods=["GET", "POST"])
def analyze_view():
    """Server-rendered analysis page (Jinja2 template).

    Intended as a convenience / debugging view only.  The primary
    frontend is the React SPA served via the static routes below.
    """
    if request.method == "GET":
        return render_template("index.html", ticker="", data=None, error=None, request=None)

    ticker = request.form.get("ticker", "").strip().upper()
    if not ticker:
        return render_template("index.html", ticker="", data=None, error="Please enter a ticker symbol.", request=request)

    try:
        stock_data = get_stock_data(ticker)
        analysis = get_old_data(stock_data, ticker)
        if not analysis or "error" in analysis:
            error_msg = analysis.get("error", "No data returned from yfinance.")
            return render_template("index.html", ticker=ticker, data=None, error=error_msg, request=request)

        fundamentals = analysis.get("fundamentals", {})
        ratios = analysis.get("ratios", {})
        pros_cons = analysis.get("pros_cons", {"pros": [], "cons": []})
        pe = ratios.get("PE Ratio (TTM)", None)

        # â”€â”€ convert dataframes to serialisable dicts â”€â”€
        df_income = stock_data.get("income_stmt", pd.DataFrame())
        df_balance = stock_data.get("balance_sheet", pd.DataFrame())
        df_cashflow = stock_data.get("cashflow", pd.DataFrame())

        income_data = df_to_json(df_income, max_cols=5)
        balance_data = df_to_json(df_balance, max_cols=5)
        cashflow_data = df_to_json(df_cashflow, max_cols=5)

        return render_template(
            "index.html",
            ticker=ticker,
            data={
                "name": stock_data.get("info", {}).get("longName", ticker),
                "price": stock_data.get("info", {}).get("currentPrice", None),
                "industry": stock_data.get("info", {}).get("industry", "N/A"),
                "sector": stock_data.get("info", {}).get("sector", "N/A"),
                "fundamentals": fundamentals,
                "ratios": ratios,
                "pros_cons": pros_cons,
                "pe": pe,
                "income_data": income_data,
                "balance_data": balance_data,
                "cashflow_data": cashflow_data,
            },
            error=None,
            request=request,
        )
    except Exception as exc:
        return render_template("index.html", ticker=ticker, data=None, error=str(exc), request=request)


# â”€â”€ helpers used by the /analyze-view route â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def safe_val(val):
    if val is None:
        return None
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return None
    return val


def _latest(vals):
    if not vals or len(vals) == 0:
        return None
    return vals[-1]


def _normalize_filter_label(value):
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


UNAVAILABLE_SCREENER_LABELS = {
    "dii holding",
    "earnings growth 3years",
    "earnings growth 5years",
    "reserves",
    "dividend growth rate",
    "average return on equity 3years",
    "average roe 3years",
    "average return on equity 5years",
    "average roe 5years",
}


def _metric_lookup(metrics, label):
    normalized = _normalize_filter_label(label)
    if normalized in metrics:
        return normalized, metrics[normalized]
    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    for key, value in metrics.items():
        if re.sub(r"[^a-z0-9]+", "", key) == compact:
            return key, value
    return normalized, None


def _compare_metric(actual, operator, target):
    if actual is None:
        return False
    try:
        actual = float(actual)
        target = float(target)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(actual) or not np.isfinite(target):
        return False
    if operator == ">":
        return actual > target
    if operator == ">=":
        return actual >= target
    if operator == "<":
        return actual < target
    if operator == "<=":
        return actual <= target
    if operator == "=":
        return abs(actual - target) < 0.001
    return False


def _safe_metric_num(value):
    try:
        if value is None:
            return None
        value = float(value)
        if not np.isfinite(value):
            return None
        return value
    except (TypeError, ValueError):
        return None


def _pct_from_yahoo(value):
    value = _safe_metric_num(value)
    if value is None:
        return None
    return round(value * 100, 4) if abs(value) <= 1 else value


def _dividend_yield_from_yahoo(value):
    value = _safe_metric_num(value)
    if value is None:
        return None
    return round(value * 100, 4) if abs(value) <= 0.2 else value


def _cr_from_yahoo(value):
    value = _safe_metric_num(value)
    return None if value is None else round(value / 1e7, 4)


def _normalize_de_ratio(value):
    value = _safe_metric_num(value)
    if value is None:
        return None
    return value / 100 if abs(value) > 10 else value


def _df_latest(df, row_name):
    try:
        if df is None or df.empty or row_name not in df.index:
            return None
        series = df.loc[row_name].dropna()
        if series.empty:
            return None
        return _safe_metric_num(series.iloc[0])
    except Exception:
        return None


def _df_growth(df, row_name, periods=4):
    try:
        if df is None or df.empty or row_name not in df.index:
            return None
        series = df.loc[row_name].dropna()
        if len(series) <= periods:
            return None
        latest = _safe_metric_num(series.iloc[0])
        previous = _safe_metric_num(series.iloc[periods])
        if latest is None or previous in (None, 0):
            return None
        return round(((latest / previous) - 1) * 100, 4)
    except Exception:
        return None


def _macd_value(hist):
    try:
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        close = hist["Close"].astype(float)
        if len(close) < 26:
            return None
        macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        return _safe_metric_num(macd_line.iloc[-1])
    except Exception:
        return None


def _rsi_value(hist):
    try:
        from analysis.technicals import calculate_rsi
        if hist is None or hist.empty or len(hist) < 20:
            return None
        rsi = calculate_rsi(hist).iloc[-1]
        return _safe_metric_num(rsi)
    except Exception:
        return None


def _parse_max_symbols(raw_value, default=30):
    if raw_value in (None, ""):
        return default
    text = str(raw_value).strip().lower()
    if text in {"all", "full", "master", "master_index", "0", "*"}:
        return None
    try:
        parsed = int(float(text))
    except (TypeError, ValueError):
        return default
    return None if parsed <= 0 else parsed


def _load_spreadsheet_metric_cache(master_index):
    if not SPREADSHEET_METRIC_CACHE_PATH.exists():
        return []
    by_name = {}
    with SPREADSHEET_METRIC_CACHE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = row.get("name")
            metrics = row.get("metrics")
            if name and isinstance(metrics, dict):
                by_name[name] = row
    ordered = []
    for entry in master_index:
        cached = by_name.get(entry["name"])
        if cached:
            ordered.append(cached)
    return ordered


def _load_yahoo_metric_cache():
    if not YAHOO_METRIC_CACHE_PATH.exists():
        return {}
    rows = {}
    with YAHOO_METRIC_CACHE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = row.get("name")
            metrics = row.get("metrics")
            if name and isinstance(metrics, dict):
                rows[name] = row
    return rows


def _append_yahoo_metric_cache(row):
    with YAHOO_METRIC_CACHE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _is_transient_yahoo_error(row):
    error = str((row or {}).get("error") or "").lower()
    return (
        "too many requests" in error
        or "rate limit" in error
        or "invalid crumb" in error
        or "failed to resolve" in error
        or "connection" in error
        or "timeout" in error
    )


def _json_safe_metrics(metrics):
    return {key: _safe_metric_num(value) for key, value in metrics.items()}


def _yahoo_metrics_for_stock(name, company_name=None):
    from services.google_sheets_service import _resolve_yahoo_symbol

    try:
        yahoo_symbol = _resolve_yahoo_symbol(name, company_name or name)
    except Exception as exc:
        return {"name": name, "yahoo_symbol": None, "metrics": {}, "error": str(exc)[:200]}
    if not yahoo_symbol:
        return {"name": name, "yahoo_symbol": None, "metrics": {}, "error": "symbol_not_resolved"}

    try:
        bundle = get_stock_data(yahoo_symbol)
    except Exception as exc:
        return {"name": name, "yahoo_symbol": yahoo_symbol, "metrics": {}, "error": str(exc)[:200]}

    info = bundle.get("info") or {}
    financials = bundle.get("financials")
    balance = bundle.get("balance_sheet")
    cashflow = bundle.get("cashflow")
    quarterly = bundle.get("quarterly_financials")
    hist = bundle.get("history")

    current_price = _safe_metric_num(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _safe_metric_num(info.get("marketCap"))
    market_cap_cr = _cr_from_yahoo(market_cap)
    enterprise_value = _safe_metric_num(info.get("enterpriseValue"))
    enterprise_value_cr = _cr_from_yahoo(enterprise_value)
    total_revenue = _safe_metric_num(info.get("totalRevenue"))
    free_cashflow = _safe_metric_num(info.get("freeCashflow"))
    trailing_pe = _safe_metric_num(info.get("trailingPE"))
    dividend_yield = _dividend_yield_from_yahoo(info.get("dividendYield"))
    promoter = _pct_from_yahoo(info.get("heldPercentInsiders"))
    fii = _pct_from_yahoo(info.get("heldPercentInstitutions"))
    public = None
    if promoter is not None or fii is not None:
        public = max(0, 100 - (promoter or 0) - (fii or 0))

    sales_latest_q = _df_latest(quarterly, "Total Revenue")
    pat_latest_q = _df_latest(quarterly, "Net Income")
    cash = _df_latest(balance, "Cash And Cash Equivalents")
    total_assets = _df_latest(balance, "Total Assets")
    total_liabilities = _df_latest(balance, "Total Liabilities Net Minority Interest")
    equity = _df_latest(balance, "Common Stock Equity")
    inventory = _df_latest(balance, "Inventory")
    receivables = _df_latest(balance, "Accounts Receivable")
    payables = _df_latest(balance, "Accounts Payable")
    current_assets = _df_latest(balance, "Current Assets")
    current_liabilities = _df_latest(balance, "Current Liabilities")
    cfo = _df_latest(cashflow, "Operating Cash Flow")
    cfi = _df_latest(cashflow, "Investing Cash Flow")
    cff = _df_latest(cashflow, "Financing Cash Flow")
    net_profit = _df_latest(financials, "Net Income")
    gross_profit = _df_latest(financials, "Gross Profit")
    pbt = _df_latest(financials, "Pretax Income")
    ebitda = _df_latest(financials, "EBITDA")
    operating_profit = _df_latest(financials, "Operating Income")
    dividends_paid = _df_latest(cashflow, "Cash Dividends Paid")

    avg_volume = _safe_metric_num(info.get("averageVolume") or info.get("averageDailyVolume10Day"))
    latest_volume = None
    if hist is not None and not hist.empty and "Volume" in hist.columns:
        latest_volume = _safe_metric_num(hist["Volume"].iloc[-1])

    metrics = {
        "market capitalization": market_cap_cr,
        "market cap": market_cap_cr,
        "current price": current_price,
        "price": current_price,
        "price to earning": trailing_pe,
        "price to earnings": trailing_pe,
        "p/e": trailing_pe,
        "pe": trailing_pe,
        "price to book value": _safe_metric_num(info.get("priceToBook")),
        "price to book": _safe_metric_num(info.get("priceToBook")),
        "p/b": _safe_metric_num(info.get("priceToBook")),
        "pb": _safe_metric_num(info.get("priceToBook")),
        "price to sales": _safe_metric_num(info.get("priceToSalesTrailing12Months")) or ((market_cap / total_revenue) if market_cap and total_revenue else None),
        "p/s": _safe_metric_num(info.get("priceToSalesTrailing12Months")) or ((market_cap / total_revenue) if market_cap and total_revenue else None),
        "price to free cash flow": _safe_metric_num(info.get("priceToFreeCashflows")) or ((market_cap / free_cashflow) if market_cap and free_cashflow else None),
        "p/fcf": _safe_metric_num(info.get("priceToFreeCashflows")) or ((market_cap / free_cashflow) if market_cap and free_cashflow else None),
        "ev/ebitda": _safe_metric_num(info.get("enterpriseToEbitda")),
        "enterprise value to ebitda": _safe_metric_num(info.get("enterpriseToEbitda")),
        "enterprise value": enterprise_value_cr,
        "ev": enterprise_value_cr,
        "earnings yield": (100 / trailing_pe) if trailing_pe and trailing_pe > 0 else None,
        "dividend yield": dividend_yield,
        "return on equity": _pct_from_yahoo(info.get("returnOnEquity")),
        "roe": _pct_from_yahoo(info.get("returnOnEquity")),
        "return on assets": _pct_from_yahoo(info.get("returnOnAssets")),
        "roa": _pct_from_yahoo(info.get("returnOnAssets")),
        "net profit margin": _pct_from_yahoo(info.get("profitMargins")),
        "operating profit margin": _pct_from_yahoo(info.get("operatingMargins")),
        "operating margin": _pct_from_yahoo(info.get("operatingMargins")),
        "opm": _pct_from_yahoo(info.get("operatingMargins")),
        "gross profit margin": _pct_from_yahoo(info.get("grossMargins")),
        "ebitda margin": _pct_from_yahoo(info.get("ebitdaMargins")),
        "earnings per share": _safe_metric_num(info.get("trailingEps")),
        "eps": _safe_metric_num(info.get("trailingEps")),
        "book value per share": _safe_metric_num(info.get("bookValue")),
        "bvps": _safe_metric_num(info.get("bookValue")),
        "dividend per share": _safe_metric_num(info.get("dividendRate")),
        "dps": _safe_metric_num(info.get("dividendRate")),
        "debt": _cr_from_yahoo(info.get("totalDebt")),
        "total debt": _cr_from_yahoo(info.get("totalDebt")),
        "debt to equity": _normalize_de_ratio(info.get("debtToEquity")),
        "d/e": _normalize_de_ratio(info.get("debtToEquity")),
        "current ratio": _safe_metric_num(info.get("currentRatio")) or ((current_assets / current_liabilities) if current_assets and current_liabilities else None),
        "quick ratio": _safe_metric_num(info.get("quickRatio")),
        "cash ratio": (cash / current_liabilities) if cash and current_liabilities else None,
        "promoter holding": promoter,
        "fii holding": fii,
        "dii holding": None,
        "public holding": public,
        "pledged percentage": None,
        "sales": _cr_from_yahoo(total_revenue),
        "revenue": _cr_from_yahoo(total_revenue),
        "profit after tax": _cr_from_yahoo(net_profit),
        "pat": _cr_from_yahoo(net_profit),
        "net profit": _cr_from_yahoo(net_profit),
        "operating profit": _cr_from_yahoo(operating_profit),
        "ebitda": _cr_from_yahoo(ebitda),
        "gross profit": _cr_from_yahoo(gross_profit),
        "profit before tax": _cr_from_yahoo(pbt),
        "pbt": _cr_from_yahoo(pbt),
        "sales latest quarter": _cr_from_yahoo(sales_latest_q),
        "profit after tax latest quarter": _cr_from_yahoo(pat_latest_q),
        "yoy quarterly sales growth": _df_growth(quarterly, "Total Revenue", periods=4),
        "yoy quarterly profit growth": _df_growth(quarterly, "Net Income", periods=4),
        "qoq quarterly sales growth": _df_growth(quarterly, "Total Revenue", periods=1),
        "qoq quarterly profit growth": _df_growth(quarterly, "Net Income", periods=1),
        "revenue growth": _pct_from_yahoo(info.get("revenueGrowth")),
        "earnings growth": _pct_from_yahoo(info.get("earningsGrowth")),
        "earnings growth 3years": None,
        "earnings growth 5years": None,
        "52 week high": _safe_metric_num(info.get("fiftyTwoWeekHigh")),
        "52 week low": _safe_metric_num(info.get("fiftyTwoWeekLow")),
        "52 week change": _pct_from_yahoo(info.get("52WeekChange")),
        "volume": latest_volume,
        "average volume": avg_volume,
        "beta": _safe_metric_num(info.get("beta")),
        "rsi": _rsi_value(hist),
        "macd": _macd_value(hist),
        "cash flow from operating": _cr_from_yahoo(cfo),
        "cash flow from investing": _cr_from_yahoo(cfi),
        "cash flow from financing": _cr_from_yahoo(cff),
        "free cash flow": _cr_from_yahoo(free_cashflow) or _cr_from_yahoo(_df_latest(cashflow, "Free Cash Flow")),
        "fcf": _cr_from_yahoo(free_cashflow) or _cr_from_yahoo(_df_latest(cashflow, "Free Cash Flow")),
        "cash and cash equivalents": _cr_from_yahoo(cash),
        "total assets": _cr_from_yahoo(total_assets),
        "total liabilities": _cr_from_yahoo(total_liabilities),
        "shareholders equity": _cr_from_yahoo(equity),
        "reserves": None,
        "inventory": _cr_from_yahoo(inventory),
        "accounts receivable": _cr_from_yahoo(receivables),
        "accounts payable": _cr_from_yahoo(payables),
        "asset turnover": (total_revenue / total_assets) if total_revenue and total_assets else None,
        "inventory turnover": (total_revenue / inventory) if total_revenue and inventory else None,
        "receivables turnover": (total_revenue / receivables) if total_revenue and receivables else None,
        "working capital": _cr_from_yahoo(current_assets - current_liabilities) if current_assets is not None and current_liabilities is not None else None,
        "working capital turnover": (total_revenue / (current_assets - current_liabilities)) if total_revenue and current_assets is not None and current_liabilities is not None and (current_assets - current_liabilities) else None,
        "payout ratio": _pct_from_yahoo(info.get("payoutRatio")) or ((abs(dividends_paid) / net_profit) * 100 if dividends_paid and net_profit else None),
        "dividend payout ratio": _pct_from_yahoo(info.get("payoutRatio")) or ((abs(dividends_paid) / net_profit) * 100 if dividends_paid and net_profit else None),
        "dividend growth rate": None,
        "average return on equity 3years": None,
        "average roe 3years": None,
        "average return on equity 5years": None,
        "average roe 5years": None,
    }
    return {
        "name": name,
        "yahoo_symbol": yahoo_symbol,
        "metrics": _json_safe_metrics(metrics),
        "error": None,
    }


def _get_yahoo_metrics_for_row(row, yahoo_cache, cache_lock=None):
    name = row.get("name")
    if not name:
        return {}
    if cache_lock:
        with cache_lock:
            cached = yahoo_cache.get(name)
    else:
        cached = yahoo_cache.get(name)
    if cached is not None:
        return cached.get("metrics", {})
    fetched = _yahoo_metrics_for_stock(name, name)
    if cache_lock:
        with cache_lock:
            if name not in yahoo_cache:
                if not _is_transient_yahoo_error(fetched):
                    yahoo_cache[name] = fetched
                    _append_yahoo_metric_cache(fetched)
            else:
                fetched = yahoo_cache[name]
    else:
        if not _is_transient_yahoo_error(fetched):
            yahoo_cache[name] = fetched
            _append_yahoo_metric_cache(fetched)
    return fetched.get("metrics", {})


def _result_from_metric_cache(row):
    metrics = row.get("metrics", {})
    return {
        "symbol": row.get("symbol") or (row.get("name") or "").replace(" ", ""),
        "name": row.get("name"),
        "sheetUrl": None,
        "price": metrics.get("current price") or metrics.get("price"),
        "market_cap_cr": metrics.get("market capitalization") or metrics.get("market cap"),
        "pe": metrics.get("pe") or metrics.get("p/e") or metrics.get("price to earning"),
        "roe": metrics.get("roe") or metrics.get("return on equity"),
        "roce": metrics.get("roce") or metrics.get("return on capital employed"),
        "debt_to_equity": metrics.get("debt to equity") or metrics.get("d/e"),
        "yahoo_symbol": None,
    }


def _screen_cached_metric_rows(rows, filter_rules, strict_missing_metrics=True, use_yahoo_fallback=True):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    missing_metric_counts = {}
    rule_fail_counts = {}
    yahoo_cache = _load_yahoo_metric_cache() if use_yahoo_fallback else {}
    yahoo_fill_counts = {}
    yahoo_miss_counts = {}
    stats_lock = threading.Lock()
    cache_lock = threading.Lock()

    def evaluate_row(row):
        local_missing = {}
        local_fails = {}
        local_yahoo_fills = {}
        local_yahoo_misses = {}
        metrics = row.get("metrics", {})
        for rule in filter_rules:
            key, metric_value = _metric_lookup(metrics, rule["label"])
            if metric_value is None:
                yahoo_value = None
                if use_yahoo_fallback:
                    yahoo_metrics = _get_yahoo_metrics_for_row(row, yahoo_cache, cache_lock=cache_lock)
                    _, yahoo_value = _metric_lookup(yahoo_metrics, rule["label"])
                if yahoo_value is not None:
                    metrics[key] = yahoo_value
                    metric_value = yahoo_value
                    local_yahoo_fills[key] = local_yahoo_fills.get(key, 0) + 1
                else:
                    local_missing[key] = local_missing.get(key, 0) + 1
                    if use_yahoo_fallback:
                        local_yahoo_misses[key] = local_yahoo_misses.get(key, 0) + 1
                    if strict_missing_metrics:
                        return None, local_missing, local_fails, local_yahoo_fills, local_yahoo_misses
                    continue
            if not _compare_metric(metric_value, rule["operator"], rule["value"]):
                local_fails[key] = local_fails.get(key, 0) + 1
                return None, local_missing, local_fails, local_yahoo_fills, local_yahoo_misses
        return _result_from_metric_cache(row), local_missing, local_fails, local_yahoo_fills, local_yahoo_misses

    def merge_counts(target, source):
        for key, value in source.items():
            target[key] = target.get(key, 0) + value

    workers = min(3, max(2, len(rows) // 1000 or 2))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(evaluate_row, row) for row in rows]
        for future in as_completed(futures):
            result, local_missing, local_fails, local_yahoo_fills, local_yahoo_misses = future.result()
            with stats_lock:
                merge_counts(missing_metric_counts, local_missing)
                merge_counts(rule_fail_counts, local_fails)
                merge_counts(yahoo_fill_counts, local_yahoo_fills)
                merge_counts(yahoo_miss_counts, local_yahoo_misses)
                if result:
                    results.append(result)
    return results, missing_metric_counts, rule_fail_counts, yahoo_fill_counts, yahoo_miss_counts


def run_google_sheets_screener(filters: dict):
    from services.google_sheets_service import (
        load_master_index,
        _load_workbook,
        _parse_data_sheet,
        _parse_profit_loss_sheet,
        _calculate_fundamentals,
        _resolve_yahoo_symbol,
        _safe_float,
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed

    query = (filters.get("query") or "").strip()
    result_limit = int(filters.get("limit") or 15)
    max_symbols_raw = filters.get("max_symbols")
    max_symbols = _parse_max_symbols(max_symbols_raw, default=30)
    enrich_yahoo = bool(filters.get("enrich_yahoo", False))
    workers = min(16, max(2, int(filters.get("parallel_workers", 8) or 8)))
    strict_missing_metrics = bool(filters.get("strict_missing_metrics", True))
    scan_label = "all" if max_symbols is None else max_symbols
    print(f"[screener] query: '{query}', result_limit: {result_limit}, max_symbols: {scan_label}, enrich_yahoo: {enrich_yahoo}")

    # Parse query into filters
    filter_rules = []
    unsupported_filters = []
    if query:
        for line in [part.strip() for part in re.split(r"\n|\band\b", query, flags=re.IGNORECASE) if part.strip()]:
            line_lower = line.lower()
            # Detect operator
            op = None
            if ">=" in line:
                op = ">="
            elif "<=" in line:
                op = "<="
            elif ">" in line:
                op = ">"
            elif "<" in line:
                op = "<"
            elif "=" in line:
                op = "="
            
            if not op:
                print(f"[screener] No operator found in line: '{line}'")
                continue
            
            label_part, value_part = line.split(op, 1)
            label = label_part.strip()
            normalized_label = _normalize_filter_label(label)
            if normalized_label in UNAVAILABLE_SCREENER_LABELS:
                unsupported_filters.append(label)
                continue
            value = _safe_float(value_part.strip())
            print(f"[screener] Rule: label='{label}', op='{op}', value_str='{value_part.strip()}', value={value}")
            if value is None:
                continue
            
            filter_rules.append({
                "label": normalized_label,
                "operator": op,
                "value": value,
            })
    print(f"[screener] Filter rules: {filter_rules}")
    if unsupported_filters:
        return {
            "results": [],
            "count": 0,
            "meta": {
                "source": "spreadsheet_metric_cache",
                "unsupported_filters": unsupported_filters,
                "message": "These screener filters are not available from spreadsheet or Yahoo fallback.",
                "filter_rules": filter_rules,
            },
        }
    
    master_index = load_master_index()
    if max_symbols is None or max_symbols > 100:
        cached_rows = _load_spreadsheet_metric_cache(master_index)
        if cached_rows:
            rows_to_scan = cached_rows if max_symbols is None else cached_rows[:max_symbols]
            results, missing_metric_counts, rule_fail_counts, yahoo_fill_counts, yahoo_miss_counts = _screen_cached_metric_rows(
                rows_to_scan,
                filter_rules,
                strict_missing_metrics=strict_missing_metrics,
                use_yahoo_fallback=bool(filters.get("yahoo_fallback", True)),
            )
            results.sort(key=lambda row: (row.get("market_cap_cr") is None, -(row.get("market_cap_cr") or 0)))
            trimmed = results[:max(1, min(result_limit, 5000))]
            return {
                "results": trimmed,
                "count": len(trimmed),
                "meta": {
                    "source": "spreadsheet_metric_cache",
                    "master_universe_count": len(master_index),
                    "symbols_evaluated": len(rows_to_scan),
                    "matches_before_limit": len(results),
                    "matches_returned": len(trimmed),
                    "fetch_failures": max(0, len(master_index if max_symbols is None else master_index[:max_symbols]) - len(rows_to_scan)),
                    "cache_path": str(SPREADSHEET_METRIC_CACHE_PATH),
                    "cache_rows": len(cached_rows),
                    "enrich_yahoo": False,
                    "yahoo_fallback": bool(filters.get("yahoo_fallback", True)),
                    "yahoo_fill_counts": yahoo_fill_counts,
                    "yahoo_miss_counts": yahoo_miss_counts,
                    "yahoo_cache_path": str(YAHOO_METRIC_CACHE_PATH),
                    "parallel_workers": 0,
                    "max_symbols": scan_label,
                    "filter_rules": filter_rules,
                    "strict_missing_metrics": strict_missing_metrics,
                    "missing_metric_counts": missing_metric_counts,
                    "rule_fail_counts": rule_fail_counts,
                },
            }
    candidates = master_index[:max_symbols] if max_symbols else master_index
    missing_metric_counts = {}
    rule_fail_counts = {}
    yahoo_fill_counts = {}
    yahoo_miss_counts = {}
    use_yahoo_fallback = bool(filters.get("yahoo_fallback", True))
    yahoo_cache = _load_yahoo_metric_cache() if use_yahoo_fallback else {}
    stats_lock = threading.Lock()
    
    def process_entry(entry):
        import signal, threading
        try:
            # Per-stock timeout: skip any sheet that takes > 15 s to download
            result_holder = [None]
            error_holder = [None]
            def _fetch():
                try:
                    result_holder[0] = _load_workbook(entry["sheet_id"])
                except Exception as exc:
                    error_holder[0] = exc
            t = threading.Thread(target=_fetch, daemon=True)
            t.start()
            t.join(timeout=15)
            if t.is_alive() or error_holder[0] is not None:
                print(f"[screener] TIMEOUT/ERROR loading sheet for {entry['name']}: {error_holder[0]}")
                return None
            workbook = result_holder[0]
            if workbook is None:
                return None
            data_sheet = _parse_data_sheet(workbook["Data Sheet"])
            _, pnl_rows = _parse_profit_loss_sheet(workbook["Profit & Loss"])
            calculated = _calculate_fundamentals(data_sheet, pnl_rows)

            # Extract all possible metrics
            metrics = {
                # Valuation
                "market capitalization": data_sheet["market_cap_cr"],
                "market cap": data_sheet["market_cap_cr"],
                "current price": data_sheet["current_price"],
                "price": data_sheet["current_price"],
                
                # Profitability
                "roe": _latest(calculated["roe"]),
                "return on equity": _latest(calculated["roe"]),
                "roce": _latest(calculated["roce"]),
                "return on capital employed": _latest(calculated["roce"]),
                "net margin": _latest(calculated["net_margin"]),
                "net profit margin": _latest(calculated["net_margin"]),
                "operating margin": _latest(calculated["operating_margin"]),
                "opm": _latest(calculated["operating_margin"]),
                
                # Leverage
                "debt to equity": _latest(calculated["debt_to_equity"]),
                "debt/equity": _latest(calculated["debt_to_equity"]),
                "d/e": _latest(calculated["debt_to_equity"]),
                "interest coverage": _latest(calculated["interest_coverage"]),
                "interest coverage ratio": _latest(calculated["interest_coverage"]),
                
                # Growth
                "sales growth 3y": calculated["revenue_cagr_3y"],
                "sales growth 3years": calculated["revenue_cagr_3y"],
                "sales growth 5y": calculated["revenue_cagr_5y"],
                "sales growth 5years": calculated["revenue_cagr_5y"],
                "profit growth 3y": calculated["profit_cagr_3y"],
                "profit growth 3years": calculated["profit_cagr_3y"],
                "profit growth 5y": calculated["profit_cagr_5y"],
                "profit growth 5years": calculated["profit_cagr_5y"],
                "revenue growth 3y": calculated["revenue_cagr_3y"],
                "revenue growth 3years": calculated["revenue_cagr_3y"],
                "revenue growth 5y": calculated["revenue_cagr_5y"],
                "revenue growth 5years": calculated["revenue_cagr_5y"],
                "sales growth": calculated["revenue_cagr_3y"],
                "profit growth": calculated["profit_cagr_3y"],
                
                # Per share
                "eps": _latest(calculated["eps"]),
                "book value per share": _latest(calculated["book_value_per_share"]),
                "bvps": _latest(calculated["book_value_per_share"]),
                
                # Income statement
                "sales": _latest(calculated["sales"]),
                "revenue": _latest(calculated["sales"]),
                "net profit": _latest(calculated["net_profit"]),
                "pat": _latest(calculated["net_profit"]),
                "operating profit": _latest(calculated["operating_profit"]),
                "ebitda": _latest(calculated["operating_profit"]),
                
                # Balance sheet
                "total assets": _latest(calculated["total_assets"]),
                "borrowings": _latest(calculated["borrowings"]),
                "debt": _latest(calculated["borrowings"]),
                
                # Cash flow
                "cfo": _latest(calculated["cfo"]),
                "cash from operations": _latest(calculated["cfo"]),
                "cash flow from operating": _latest(calculated["cfo"]),
                "fcf": _latest(calculated["fcf"]),
                "free cash flow": _latest(calculated["fcf"]),
                
                # Shareholding
                "promoter holding": data_sheet.get("promoter_holding"),
                "pledged percentage": data_sheet.get("pledged_percentage", 0),
                
                # Efficiency
                "asset turnover": _latest(calculated["asset_turnover"]) if "asset_turnover" in calculated else None,
                "working capital": _latest(calculated["working_capital"]) if "working_capital" in calculated else None,
            }

            # Add some computed PE/PB if possible
            latest_eps = _latest(calculated["eps"])
            latest_bvps = _latest(calculated["book_value_per_share"])
            if data_sheet["current_price"] and latest_eps and latest_eps > 0:
                metrics["pe"] = data_sheet["current_price"] / latest_eps
                metrics["price to earning"] = data_sheet["current_price"] / latest_eps
                metrics["price to earnings"] = data_sheet["current_price"] / latest_eps
                metrics["p/e"] = data_sheet["current_price"] / latest_eps
            
            if data_sheet["current_price"] and latest_bvps and latest_bvps > 0:
                metrics["pb"] = data_sheet["current_price"] / latest_bvps
                metrics["price to book"] = data_sheet["current_price"] / latest_bvps
                metrics["price to book value"] = data_sheet["current_price"] / latest_bvps
                metrics["p/b"] = data_sheet["current_price"] / latest_bvps

            # Debug: log key metrics for every stock being evaluated
            print(f"[screener] {entry['name']}: market_cap_cr={data_sheet['market_cap_cr']!r}, price={data_sheet['current_price']!r}")

            # Apply filter rules
            passes = True
            for rule_idx, rule in enumerate(filter_rules):
                key, metric_value = _metric_lookup(metrics, rule["label"])
                if metric_value is None:
                    yahoo_value = None
                    if use_yahoo_fallback:
                        with stats_lock:
                            yahoo_metrics = _get_yahoo_metrics_for_row({"name": entry["name"]}, yahoo_cache)
                        _, yahoo_value = _metric_lookup(yahoo_metrics, rule["label"])
                    if yahoo_value is not None:
                        metrics[key] = yahoo_value
                        metric_value = yahoo_value
                        with stats_lock:
                            yahoo_fill_counts[key] = yahoo_fill_counts.get(key, 0) + 1
                        print(f"[screener]   rule '{key}' filled from Yahoo for {entry['name']}: {yahoo_value!r}")
                    else:
                        with stats_lock:
                            missing_metric_counts[key] = missing_metric_counts.get(key, 0) + 1
                            if use_yahoo_fallback:
                                yahoo_miss_counts[key] = yahoo_miss_counts.get(key, 0) + 1
                        print(f"[screener]   rule '{key}' missing for {entry['name']}")
                        if strict_missing_metrics:
                            passes = False
                            break
                        continue

                op = rule["operator"]
                target = rule["value"]
                rule_pass = _compare_metric(metric_value, op, target)

                print(f"[screener]   rule '{key}' {op} {target}: metric={metric_value!r} -> {'PASS' if rule_pass else 'FAIL'}")
                if not rule_pass:
                    with stats_lock:
                        rule_fail_counts[key] = rule_fail_counts.get(key, 0) + 1
                    passes = False
                    break
            
            if passes:
                return {
                    "symbol": entry["name"].replace(" ", ""),
                    "name": entry["name"],
                    "sheetUrl": entry["url"],
                    "price": data_sheet["current_price"],
                    "market_cap_cr": data_sheet["market_cap_cr"],
                    "pe": metrics.get("pe"),
                    "roe": _latest(calculated["roe"]),
                    "roce": _latest(calculated["roce"]),
                    "debt_to_equity": _latest(calculated["debt_to_equity"]),
                    "company_name": data_sheet["company_name"],
                    "yahoo_symbol": None,
                }
        except Exception as e:
            print(f"Error processing {entry['name']}: {e}")
        return None

    results = []
    fetch_failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_entry, entry) for entry in candidates]
        for f in as_completed(futures):
            try:
                res = f.result()
            except Exception:
                fetch_failures += 1
                continue
            if res:
                results.append(res)

    results.sort(key=lambda row: (row.get("market_cap_cr") is None, -(row.get("market_cap_cr") or 0)))
    trimmed = results[:max(1, min(result_limit, 500))]
    yahoo_enriched = 0
    for row in trimmed:
        if not enrich_yahoo:
            row["yahoo_symbol"] = None
            row.pop("company_name", None)
            continue
        yahoo_symbol = _resolve_yahoo_symbol(row["name"], row.get("company_name") or row["name"])
        row["yahoo_symbol"] = yahoo_symbol
        if not yahoo_symbol:
            row.pop("company_name", None)
            continue
        try:
            yahoo_bundle = get_stock_data(yahoo_symbol)
            yahoo_info = yahoo_bundle.get("info", {}) if yahoo_bundle else {}
        except Exception:
            yahoo_info = {}
        live_price = yahoo_info.get("currentPrice") or yahoo_info.get("regularMarketPrice")
        market_cap_live = yahoo_info.get("marketCap")
        if live_price is not None:
            row["price"] = live_price
        if market_cap_live:
            row["market_cap_cr"] = round(market_cap_live / 1e7, 2)
        if yahoo_info.get("trailingPE") is not None:
            row["pe"] = yahoo_info.get("trailingPE")
        yahoo_enriched += 1
        row.pop("company_name", None)
    return {
        "results": trimmed,
        "count": len(trimmed),
        "meta": {
            "source": "excel_url_primary_yahoo_optional",
            "master_universe_count": len(master_index),
            "symbols_evaluated": len(candidates),
            "matches_before_limit": len(results),
            "matches_returned": len(trimmed),
            "fetch_failures": fetch_failures,
            "yahoo_enriched": yahoo_enriched,
            "enrich_yahoo": enrich_yahoo,
            "yahoo_fallback": use_yahoo_fallback,
            "yahoo_fill_counts": yahoo_fill_counts,
            "yahoo_miss_counts": yahoo_miss_counts,
            "yahoo_cache_path": str(YAHOO_METRIC_CACHE_PATH),
            "parallel_workers": workers,
            "max_symbols": scan_label,
            "filter_rules": filter_rules,
            "strict_missing_metrics": strict_missing_metrics,
            "missing_metric_counts": missing_metric_counts,
            "rule_fail_counts": rule_fail_counts,
        },
    }


def df_to_json(df, max_cols=6, quarterly=False):
    """Convert a pandas DataFrame to a JSON-serialisable dict."""
    if df is None or df.empty:
        return {"columns": [], "rows": {}}
    try:
        if quarterly:
            df = df.iloc[:, :max_cols]
        else:
            year_cols = [c for c in df.columns if hasattr(c, "year") and c.year >= 2019]
            if len(year_cols) >= 3:
                df = df[year_cols]
            df = df.iloc[:, :max_cols]

        columns = []
        for c in df.columns:
            try:
                if hasattr(c, "strftime"):
                    columns.append(c.strftime("%Y-%m-%d"))
                else:
                    columns.append(str(c))
            except Exception:
                columns.append(str(c))

        rows = {}
        for idx in df.index:
            label = str(idx).replace("_", " ").replace("  ", " ").strip()
            vals = []
            for v in df.loc[idx].values:
                try:
                    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                        vals.append(None)
                    elif isinstance(v, (int, float)):
                        vals.append(round(float(v), 2))
                    else:
                        vals.append(v)
                except Exception:
                    vals.append(None)
            rows[label] = vals
        return {"columns": columns, "rows": {}}
    except Exception:
        return {"columns": [], "rows": {}}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  STATIC FILE SERVING (React SPA)
@app.route("/api/log-error", methods=["POST"])
def log_frontend_error():
    payload = request.get_json(silent=True) or {}
    msg = payload.get("message", "?")
    stack = payload.get("stack", "")
    print(f"\n{'='*60}")
    print(f"  FRONTEND ERROR: {msg}")
    if stack:
        for line in stack.split("\n")[:15]:
            print(f"    {line}")
    print(f"{'='*60}\n")
    # Also write to file so we can read it from a background process
    try:
        with open("frontend_error.log", "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"  FRONTEND ERROR: {msg}\n")
            if stack:
                for line in stack.split("\n")[:20]:
                    f.write(f"    {line}\n")
            f.write(f"{'='*60}\n")
    except:
        pass
    return jsonify({"ok": True})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/")
def serve_index():
    return send_from_directory("frontend/dist", "index.html")


@app.route("/assets/<path:path>")
def serve_assets(path):
    return send_from_directory("frontend/dist/assets", path)


@app.route("/<path:path>", methods=["GET"])
def serve_spa_fallback(path):
    """Catch-all SPA fallback â€” every non-API GET returns index.html
    so client-side routing works inside the React app."""
    if path.startswith("api/") or path.startswith("analyze-view"):
        return jsonify({"error": "Not found"}), 404
    filepath = os.path.join("frontend", "dist", path)
    if os.path.isfile(filepath):
        return send_from_directory("frontend/dist", path)
    return send_from_directory("frontend/dist", "index.html")


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, threaded=True, port=5000)
