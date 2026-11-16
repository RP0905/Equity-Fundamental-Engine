from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[1] / ".cache" / "equity_engine.db"


def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_name TEXT,
                symbol TEXT NOT NULL UNIQUE,
                screener_url TEXT,
                source TEXT DEFAULT 'screener.in',
                last_synced_at TEXT,
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS raw_data (
                symbol TEXT PRIMARY KEY,
                current_price REAL,
                market_cap REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                dividend_yield REAL,
                roe REAL,
                roce REAL,
                face_value REAL,
                revenue REAL,
                net_profit REAL,
                sales_latest_quarter REAL,
                pat_latest_quarter REAL,
                qtr_sales_growth_yoy REAL,
                qtr_profit_growth_yoy REAL,
                sales_growth_3y REAL,
                sales_growth_5y REAL,
                profit_growth_3y REAL,
                profit_growth_5y REAL,
                avg_roe_3y REAL,
                avg_roe_5y REAL,
                ebitda REAL,
                operating_profit REAL,
                total_assets REAL,
                total_liabilities REAL,
                equity REAL,
                reserves REAL,
                borrowings REAL,
                cash_flow REAL,
                capex REAL,
                promoter_holding REAL,
                fii_holding REAL,
                dii_holding REAL,
                public_holding REAL,
                current_assets REAL,
                current_liabilities REAL,
                interest_expense REAL,
                roa REAL,
                net_profit_margin REAL,
                opm REAL,
                gross_margin REAL,
                ebitda_margin REAL,
                eps REAL,
                bvps REAL,
                dps REAL,
                pledged_percentage REAL,
                gross_profit REAL,
                pbt REAL,
                qtr_sales_growth_qoq REAL,
                qtr_profit_growth_qoq REAL,
                week_high_52 REAL,
                week_low_52 REAL,
                week_change_52 REAL,
                volume REAL,
                avg_volume REAL,
                beta REAL,
                cash_flow_operating REAL,
                cash_flow_investing REAL,
                cash_flow_financing REAL,
                free_cash_flow REAL,
                cash REAL,
                inventory REAL,
                receivables REAL,
                payables REAL,
                price_to_sales REAL,
                price_to_fcf REAL,
                ev_ebitda REAL,
                enterprise_value REAL,
                payout_ratio REAL,
                dividend_growth REAL,
                results_period TEXT,
                shareholding_period TEXT,
                statement_source TEXT,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS computed_metrics (
                symbol TEXT PRIMARY KEY,
                earnings_yield REAL,
                debt_to_equity REAL,
                current_ratio REAL,
                quick_ratio REAL,
                cash_ratio REAL,
                interest_coverage REAL,
                asset_turnover REAL,
                inventory_turnover REAL,
                receivables_turnover REAL,
                working_capital REAL,
                working_capital_turnover REAL,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS technical_data (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                price REAL,
                rsi REAL,
                macd REAL,
                ema_20 REAL,
                ema_50 REAL,
                ema_200 REAL,
                last_updated TEXT,
                PRIMARY KEY (symbol, timeframe)
            );

            CREATE TABLE IF NOT EXISTS statement_items (
                symbol TEXT NOT NULL,
                statement_type TEXT NOT NULL,
                period_type TEXT NOT NULL,
                period_label TEXT NOT NULL,
                display_order INTEGER NOT NULL DEFAULT 0,
                metric TEXT NOT NULL,
                value REAL,
                raw_value TEXT,
                last_updated TEXT,
                PRIMARY KEY (symbol, statement_type, period_type, period_label, metric)
            );

            CREATE TABLE IF NOT EXISTS shareholding_pattern (
                symbol TEXT NOT NULL,
                period_label TEXT NOT NULL,
                promoter_holding REAL,
                fii_holding REAL,
                dii_holding REAL,
                public_holding REAL,
                last_updated TEXT,
                PRIMARY KEY (symbol, period_label)
            );

            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_path TEXT,
                row_count INTEGER NOT NULL DEFAULT 0,
                imported_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_raw_data_market_cap ON raw_data(market_cap);
            CREATE INDEX IF NOT EXISTS idx_raw_data_roe ON raw_data(roe);
            CREATE INDEX IF NOT EXISTS idx_raw_data_pe_ratio ON raw_data(pe_ratio);
            CREATE INDEX IF NOT EXISTS idx_computed_debt_to_equity ON computed_metrics(debt_to_equity);
            """
        )

        _ensure_columns(
            cur,
            "raw_data",
            {
                "sales_latest_quarter": "REAL",
                "pat_latest_quarter": "REAL",
                "qtr_sales_growth_yoy": "REAL",
                "qtr_profit_growth_yoy": "REAL",
                "sales_growth_3y": "REAL",
                "sales_growth_5y": "REAL",
                "profit_growth_3y": "REAL",
                "profit_growth_5y": "REAL",
                "avg_roe_3y": "REAL",
                "avg_roe_5y": "REAL",
                "roa": "REAL",
                "net_profit_margin": "REAL",
                "opm": "REAL",
                "gross_margin": "REAL",
                "ebitda_margin": "REAL",
                "eps": "REAL",
                "bvps": "REAL",
                "dps": "REAL",
                "pledged_percentage": "REAL",
                "gross_profit": "REAL",
                "pbt": "REAL",
                "qtr_sales_growth_qoq": "REAL",
                "qtr_profit_growth_qoq": "REAL",
                "week_high_52": "REAL",
                "week_low_52": "REAL",
                "week_change_52": "REAL",
                "volume": "REAL",
                "avg_volume": "REAL",
                "beta": "REAL",
                "cash_flow_operating": "REAL",
                "cash_flow_investing": "REAL",
                "cash_flow_financing": "REAL",
                "free_cash_flow": "REAL",
                "cash": "REAL",
                "inventory": "REAL",
                "receivables": "REAL",
                "payables": "REAL",
                "price_to_sales": "REAL",
                "price_to_fcf": "REAL",
                "ev_ebitda": "REAL",
                "enterprise_value": "REAL",
                "payout_ratio": "REAL",
                "dividend_growth": "REAL",
            },
        )
        _ensure_columns(
            cur,
            "computed_metrics",
            {
                "quick_ratio": "REAL",
                "cash_ratio": "REAL",
                "inventory_turnover": "REAL",
                "receivables_turnover": "REAL",
                "working_capital_turnover": "REAL",
            },
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(cur, table_name, columns):
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column, column_type in columns.items():
        if column in existing:
            continue
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {column_type}")
