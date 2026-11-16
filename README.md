# Equity Fundamental Engine

**A local-first equity research terminal for NSE/BSE investors.** Combine deep fundamental analysis, quantitative screening, AI-assisted research, position risk sizing, and trade journaling inside one unified workspace — instead of juggling spreadsheets, broker tabs, and half a dozen websites.

> Built for retail investors, finance students, and quantitative learners who want institutional-style research without an institutional budget.

---

## Why this project

Most retail research workflows are fragmented: fundamentals on one site, charts on another, a spreadsheet for screening, a calculator for position sizing, and a notebook for trade reviews. **Equity Fundamental Engine brings the whole research loop into a single, fast, local application.**

- **One workspace, five tools** — analyze, screen, research with AI, size risk, and journal trades without losing context.
- **Fundamentals-first** — ratios, growth, ownership, financial statements, and technical context in one structured view.
- **Explainable by design** — every metric comes from a visible data source (Google Sheets, NSE, Yahoo Finance), not a black box.
- **Local and private** — runs on your machine; your trades and notes stay in your browser/device.
- **Export-ready** — generate PDF research reports and Excel workbooks in one click.

---

## Modules at a glance

| Module | What it does | Status |
|---|---|---|
| **Analyzer** | Deep-dive fundamental + technical analysis for any NSE/BSE stock | Live |
| **Screener** | Filter thousands of stocks with natural-language-style fundamental queries | Live |
| **AI Analysis** | Conversational, chart-aware market research agent | Optional companion app |
| **Risk Calculator** | Position sizing, risk/reward, and broker-charge planning (RiskDesk) | Optional companion app |
| **Trade Journal** | Log trades, track setups, and review performance (Arc) | Bundled & live |

> AI Analysis and Risk Calculator are intentionally kept as **separate applications** and launched on demand through the main shell. The Analyzer, Screener, and bundled Trade Journal run standalone.

---

## Feature highlights

### Analyzer
- Company overview: sector, industry, market cap, P/E, dividend yield
- Fundamental quality checks: ROE, ROCE, revenue/profit CAGR, operating margin
- Safety checks: debt/equity, interest coverage, cash-flow strength
- Valuation: P/E, P/B, EV/EBITDA, earnings yield
- Indian ownership data: promoter and FII holding
- Five-year income statement, balance sheet, and cash-flow tables
- Technical context: RSI, MACD, moving averages, trend, 52-week range, relative strength vs NIFTY
- Peer comparison and price history charts
- One-click **PDF** and **Excel** export

### Screener
- Natural-language-style filter queries over fundamental metrics
- Supports Google Sheets / Excel-style datasets and a local cached database
- Yahoo Finance fallback metrics for gaps
- Preset screens plus a browsable ratio gallery
- Local metric cache for fast, repeatable screening

### AI Analysis (optional companion)
- Conversational research over fundamentals and technical context
- Chart-aware and file/image-aware responses
- Groq-served LLM with LangGraph orchestration

### Risk Calculator — RiskDesk (optional companion)
- Position sizing and risk/reward planning
- Indian equity, futures, options, commodities, crypto, and forex support
- Broker-charge calculations, trade history, and portfolio exposure
- CSV/PDF export

### Trade Journal — Arc (bundled)
- Log trades, setups, and journal entries
- Strategy playbooks and performance review
- Import/export backups and configurable workspace settings
- Data stored in the browser via `localStorage`

---

## Architecture

The project uses a **modular shell** architecture: a Flask backend and React frontend act as the central workspace, while specialized tools run as separate services and are embedded when opened.

```
┌──────────────────────────────────────────────────────────────┐
│                    React workspace (Vite)                     │
│   Analyzer · Screener · AI Analysis · Risk · Trade Journal    │
└───────────────────────────────┬──────────────────────────────┘
                                │  REST API
┌───────────────────────────────▼──────────────────────────────┐
│                      Flask backend (app.py)                    │
│  Analyzer · Screener · Launcher APIs · Static SPA hosting      │
└───────┬──────────────┬───────────────┬───────────────┬────────┘
        │              │               │               │
  Google Sheets     yfinance          NSE          Companion apps
   (primary)        (fallback)      (universe)   AI Agent · RiskDesk
```

- The main Flask app is the controller and API layer.
- The React app is the workspace shell.
- Analyzer and Screener are native modules.
- AI Analysis and Risk Calculator are started on demand and embedded via iframes.

---

## Tech stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, Vite 8, JavaScript/JSX, Tailwind CSS, Chart.js, Recharts, lightweight-charts, Axios |
| **Export** | html2canvas, jsPDF, SheetJS (xlsx) |
| **Backend** | Python, Flask, Flask-CORS, Pandas, NumPy, Requests |
| **Market data** | yfinance, Google Sheets exports, NSE index data |
| **Companion apps** | FastAPI, Uvicorn, SQLAlchemy, LangGraph, Groq API |

---

## Getting started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** and npm
- Windows (the launcher scripts are PowerShell/CMD based); manual startup works cross-platform

### Install

```bash
git clone https://github.com/RP0905/Equity-Fundamental-Engine.git
cd Equity-Fundamental-Engine

# backend dependencies
pip install flask flask-cors yfinance pandas numpy requests beautifulsoup4 lxml

# frontend dependencies
cd frontend
npm install
npm run build
cd ..
```

### Run

On Windows, the launcher handles everything (dependency checks, frontend build, server start):

```powershell
.\start        # or: .\start.cmd
.\stop         # stop all services
```

Open **http://127.0.0.1:5000** and pick a workspace.

### Manual start

```bash
python app.py
```

The Flask server serves the built React app from `frontend/dist` and exposes the REST API.

---

## Companion applications (optional)

The **AI Analysis** and **Risk Calculator** cards expect their projects to be available as siblings of this repo:

```
Desktop/
├── EquityFundamentalEngine - Original/   # this repo
└── Projects/
    ├── Stock-Market-Agent/                # AI Analysis
    └── riskdesk/                          # Risk Calculator
```

The shell exposes launcher endpoints that start these services on demand:

| Module | Backend | Frontend |
|---|---|---|
| AI Analysis | `http://127.0.0.1:8000` | `http://127.0.0.1:5173` |
| Risk Calculator | `http://127.0.0.1:8001` | `http://127.0.0.1:5174` |
| Trade Journal | — | `http://127.0.0.1:4173` |

If the companion folders are absent, the Analyzer, Screener, and Trade Journal still run normally.

---

## Project structure

```
Equity-Fundamental-Engine/
├── app.py                     # Flask app, REST API, launcher endpoints
├── analysis/                  # Fundamental & technical analysis engines
│   ├── fundamentals.py
│   ├── technicals.py
│   └── old_engine.py
├── services/                  # Data + screener services
│   ├── google_sheets_service.py
│   ├── yf_services.py
│   ├── nse_service.py
│   ├── screener_*.py
│   └── local_db.py
├── frontend/                  # React workspace shell
│   ├── src/App.jsx
│   └── public/
├── Trade Journal/             # Arc trading journal (bundled app)
│   ├── src/
│   └── scripts/serve.mjs
├── templates/                 # Legacy Jinja template view
├── utils/                     # Formatting helpers
├── start.ps1 / start.cmd      # Launchers
└── stop.ps1 / stop.cmd
```

---

## API reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/search` | GET | Search companies by name/ticker |
| `/api/analyze` | GET | Full fundamental analysis payload |
| `/api/price-history` | GET | Historical price data for charts |
| `/api/peers` | GET | Peer comparison |
| `/api/screener` | POST | Run a fundamental screen |
| `/api/screener/db-status` | GET | Local screener database status |
| `/api/screener/sync` | POST | Sync screener universe/metrics |
| `/api/screener/import-csv` | POST | Import screener data from CSV |
| `/api/ai-agent/start` | POST | Launch the AI Analysis companion |
| `/api/ai-agent/status` | GET | AI Analysis health check |
| `/api/riskdesk/start` | POST | Launch the Risk Calculator companion |
| `/api/riskdesk/status` | GET | Risk Calculator health check |
| `/api/trade-journal/start` | POST | Launch the bundled Trade Journal |
| `/api/trade-journal/status` | GET | Trade Journal health check |

---

## Data sources & design notes

- **Google Sheets** is the primary fundamentals source for the Analyzer and Screener.
- **Yahoo Finance (`yfinance`)** provides fallback fundamentals, live prices, and technical data.
- **NSE universe data** powers market-wide screening.
- Screener metric caches are local JSONL files and are excluded from version control.
- Trade Journal entries are stored in the browser via `localStorage`; the journal backend keeps an optional local trade file.
- API keys and credentials (for example `GROQ_API_KEY`) stay server-side and are never committed.

---

## Roadmap

- [ ] Portfolio-level tracking and P&L aggregation
- [ ] Automated test coverage for analyzer and screener
- [ ] Docker-based one-command setup
- [ ] Cross-platform launcher scripts
- [ ] Saved watchlists and custom alerts

---

## Disclaimer

This project is for **educational and research purposes only**. It does not constitute financial, investment, or trading advice. Always verify data independently before making investment decisions.
