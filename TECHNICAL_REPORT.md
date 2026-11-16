# Equity Fundamental Engine - Technical Report

## Project Overview

Equity Fundamental Engine is a local stock research workspace with separate modules for:

- Analyzer
- Screener
- AI Analysis
- Risk Calculator
- Trade Journal

The main project acts as the central shell. The AI Analysis and Risk Calculator tools are integrated as separate applications, launched from the main interface without merging their code into the original engine.

## Main Application

### Frontend

The main frontend is built with:

- React 19
- Vite 8
- JavaScript JSX
- Tailwind CSS tooling
- Axios for API calls
- Chart.js and React Chart.js for charts
- Recharts for chart components
- lightweight-charts for market charts
- html2canvas and jsPDF for PDF export
- xlsx for Excel export

Main frontend files:

- `frontend/src/App.jsx`
- `frontend/src/index.css`
- `frontend/vite.config.js`

The UI is a single-page React app with workspace cards. It includes separate views for Analyzer, Screener, AI Analysis, and Risk Calculator.

### Backend

The main backend is built with:

- Python
- Flask
- Flask-CORS
- Pandas
- NumPy
- Requests
- yfinance

Main backend file:

- `app.py`

The backend serves:

- REST API endpoints
- React production build from `frontend/dist`
- Stock analysis data
- Screener queries
- Launcher endpoints for separate tools

Main local URL:

- `http://127.0.0.1:5000`

## Stock Analyzer

The Analyzer module uses:

- Google Sheets as the primary company fundamentals data source
- Yahoo Finance through `yfinance` as fallback and for live market data
- Pandas for parsing financial statements
- NumPy for numerical cleanup and calculations

Analyzer backend services:

- `services/google_sheets_service.py`
- `services/yf_services.py`
- `analysis/fundamentals.py`
- `analysis/technicals.py`
- `analysis/old_engine.py`

### Fundamental Metrics

The project calculates and displays metrics such as:

- Market capitalization
- Enterprise value
- P/E
- Forward P/E
- P/B
- EV/EBITDA
- Dividend yield
- ROE
- ROCE
- Net margin
- Operating margin
- Debt/equity
- EPS
- Book value per share
- Free cash flow
- Revenue growth CAGR
- PAT growth CAGR
- Net debt
- Net debt to EBITDA

### Technical Indicators

The technical analysis file uses Pandas calculations for:

- RSI
- MACD
- EMA 9
- EMA 15
- EMA 55
- SMA 20
- SMA 50
- SMA 200
- EMA crossover
- Trend from EMA slope
- Above/below 200 DMA
- 52-week high distance
- 1M, 3M, 6M, and 1Y returns
- OBV
- Volume

## Screener

The Screener module supports natural-language-style filter queries over stock fundamentals.

Backend services:

- `services/screener_local_service.py`
- `services/screener_parser.py`
- `services/screener_csv_importer.py`
- `services/local_db.py`

The screener can use:

- Google Sheets / Excel-style data
- Yahoo fallback metrics
- Local cache/database mode
- Cached JSONL metric files

Important cache files:

- `screener_metric_cache.jsonl`
- `screener_yahoo_metric_cache.jsonl`

Example supported filters include:

- Sales Growth
- Profit Growth
- ROE
- ROCE
- Debt to Equity
- Promoter Holding
- Market Capitalization
- P/E
- P/B
- EPS
- Free Cash Flow

## AI Analysis Module

The AI Analysis module is a separate project located at:

`C:\Users\ROHEET\Desktop\Projects\Stock-Market-Agent`

It is integrated into the main Equity Fundamental Engine through launcher endpoints and an embedded iframe view.

### AI Backend

The AI backend is built with:

- FastAPI
- Uvicorn
- Pydantic
- LangGraph
- LangChain Core
- httpx
- Pandas
- yfinance
- gspread
- python-dotenv

Main backend file:

- `Stock-Market-Agent/backend/app.py`

### AI Model

The AI project uses Groq's OpenAI-compatible chat completions API.

Default model settings in the source:

- Text model: `qwen/qwen3.6-27b`
- Vision model: `qwen/qwen3.6-27b`
- Max tokens: `1024`

Environment variables:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_VISION_MODEL`
- `GROQ_MAX_TOKENS`
- `FUNDAMENTALS_CONTEXT_CHARS`
- `HISTORY_MESSAGE_CHARS`
- `GOOGLE_APPLICATION_CREDENTIALS`

The AI backend sends requests to:

- `https://api.groq.com/openai/v1/chat/completions`

### AI Data Sources

The AI agent uses:

- Google Sheets fundamentals index
- Google Docs / spreadsheet exports
- Yahoo Finance technical data through `yfinance`
- User chat history
- Optional image/file attachments

### AI Frontend

The AI frontend is built with:

- React
- Vite
- lucide-react
- Recharts

The integrated ports are:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

Main integration endpoints in the main engine:

- `/api/ai-agent/start`
- `/api/ai-agent/status`

## Risk Calculator / RiskDesk

The Risk Calculator module uses the separate RiskDesk project located at:

`C:\Users\ROHEET\Desktop\Projects\riskdesk`

It is integrated as a separate app and opened from the Risk Calculator card.

### RiskDesk Frontend

RiskDesk frontend is built with:

- React 18
- TypeScript
- Vite 5
- Tailwind CSS
- shadcn-style components
- Base UI
- Framer Motion
- lucide-react
- Recharts
- Zustand
- jsPDF

Main frontend files:

- `riskdesk/src/App.tsx`
- `riskdesk/src/main.tsx`
- `riskdesk/src/components`
- `riskdesk/src/store`
- `riskdesk/src/data`

### RiskDesk Backend

RiskDesk backend is built with:

- FastAPI
- Uvicorn
- SQLAlchemy
- Pydantic
- pydantic-settings
- aiosqlite
- httpx
- reportlab
- python-dotenv

Main backend file:

- `riskdesk/backend/app/main.py`

RiskDesk backend includes routers for:

- Instruments
- Contracts
- Calculations
- Brokers
- Prices
- Trades

RiskDesk supports:

- Crypto risk calculations
- Forex risk calculations
- Indian equity calculations
- Indian futures calculations
- Indian options calculations
- Commodities calculations
- Broker charge calculations
- Trade history
- Portfolio exposure
- CSV/PDF export

Integrated ports:

- Backend: `http://127.0.0.1:8001`
- Frontend: `http://127.0.0.1:5174`

Main integration endpoints in the main engine:

- `/api/riskdesk/start`
- `/api/riskdesk/status`

## Launcher System

The project has local launcher scripts:

- `start.ps1`
- `stop.ps1`
- `start.cmd`
- `stop.cmd`

### Start Flow

Running:

```powershell
.\start
```

does the following:

1. Stops old Equity Fundamental Engine processes.
2. Checks Python imports.
3. Installs frontend dependencies if needed.
4. Builds the React frontend.
5. Starts Flask on port `5000`.
6. Opens `http://127.0.0.1:5000`.

### Stop Flow

Running:

```powershell
.\stop
```

stops:

- Main Equity Fundamental Engine on port `5000`
- AI agent backend on port `8000`
- AI agent frontend on port `5173`
- RiskDesk backend on port `8001`
- RiskDesk frontend on port `5174`

## Architecture Summary

The architecture is modular:

- Main Flask app is the central controller and API layer.
- Main React app is the workspace shell.
- Analyzer and Screener are native modules inside the main project.
- AI Analysis is a separate FastAPI + React app launched on demand.
- Risk Calculator is a separate FastAPI + React TypeScript app launched on demand.
- Separate tools are embedded with iframes to avoid disrupting the original engine.

## Key Technical Tools Used

### Languages

- Python
- JavaScript
- TypeScript
- HTML
- CSS

### Frontend Tools

- React
- Vite
- Tailwind CSS
- Chart.js
- Recharts
- lightweight-charts
- lucide-react
- Framer Motion
- Zustand

### Backend Tools

- Flask
- FastAPI
- Uvicorn
- Pandas
- NumPy
- SQLAlchemy
- Pydantic
- Requests
- httpx

### Financial / Market Data Tools

- yfinance
- Google Sheets export
- gspread
- Screener-style local metric cache
- Binance public API in RiskDesk price feed
- Forex demo price feed in RiskDesk

### AI Tools

- Groq API
- OpenAI-compatible chat completions endpoint
- Qwen model: `qwen/qwen3.6-27b`
- LangGraph orchestration
- LangChain Core message tooling

## Current Local URLs

| Module | URL |
|---|---|
| Equity Fundamental Engine | `http://127.0.0.1:5000` |
| AI Analysis frontend | `http://127.0.0.1:5173` |
| AI Analysis backend | `http://127.0.0.1:8000` |
| RiskDesk frontend | `http://127.0.0.1:5174` |
| RiskDesk backend | `http://127.0.0.1:8001` |

## Notes

- The AI and RiskDesk modules are intentionally kept as separate projects.
- The main engine starts them on demand through backend launcher APIs.
- This avoids breaking the existing Equity Fundamental Engine while still giving one unified interface.
- API keys such as `GROQ_API_KEY` and Google credentials are expected to stay server-side.
