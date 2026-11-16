import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"
import html2canvas from "html2canvas"
import jsPDF from "jspdf"
import * as XLSX from "xlsx"
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement, PointElement,
  Tooltip, Legend, Filler, BarController, LineController,
} from "chart.js"
import { Bar, Line } from "react-chartjs-2"
import { createChart, CandlestickSeries, ColorType, CrosshairMode } from "lightweight-charts"
import { SectionBoundary } from "./ErrorBoundary"

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend, Filler, BarController, LineController)

const API = "http://127.0.0.1:5000"
const IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 })
const USD = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 })
const fmtDay = (ts) => new Date(ts * 1000).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" })

const RATIOS_GALLERY = {
  "Valuation": [
    "Market Capitalization",
    "Market Cap",
    "Price to Earning",
    "P/E",
    "Price to Book Value",
    "P/B",
    "Price to Sales",
    "P/S",
    "Price to Free Cash Flow",
    "P/FCF",
    "EV/EBITDA",
    "Enterprise Value",
    "EV",
    "Earnings Yield",
    "Dividend Yield"
  ],
  "Profitability": [
    "Return on Equity",
    "ROE",
    "Return on Capital Employed",
    "ROCE",
    "Return on Assets",
    "ROA",
    "Net Profit Margin",
    "Operating Profit Margin",
    "Gross Profit Margin",
    "EBITDA Margin",
    "Earnings Per Share",
    "EPS",
    "Book Value Per Share",
    "BVPS",
    "Dividend Per Share",
    "DPS"
  ],
  "Leverage & Debt": [
    "Debt",
    "Total Debt",
    "Debt to Equity",
    "D/E",
    "Interest Coverage Ratio",
    "Current Ratio",
    "Quick Ratio",
    "Cash Ratio"
  ],
  "Shareholding": [
    "Promoter Holding",
    "FII Holding",
    "Public Holding",
    "Pledged Percentage"
  ],
  "Income Statement": [
    "Sales",
    "Revenue",
    "Profit After Tax",
    "PAT",
    "Operating Profit",
    "EBITDA",
    "Gross Profit",
    "Profit Before Tax",
    "PBT"
  ],
  "Quarterly": [
    "Sales Latest Quarter",
    "Profit After Tax Latest Quarter",
    "YoY Quarterly Sales Growth",
    "YoY Quarterly Profit Growth",
    "QoQ Quarterly Sales Growth",
    "QoQ Quarterly Profit Growth"
  ],
  "Growth": [
    "Sales Growth",
    "Sales Growth 3Years",
    "Sales Growth 5Years",
    "Profit Growth",
    "Profit Growth 3Years",
    "Profit Growth 5Years",
    "Revenue Growth",
    "Revenue Growth 3Years",
    "Revenue Growth 5Years",
    "Earnings Growth"
  ],
  "Price & Technical": [
    "Current Price",
    "Price",
    "52 Week High",
    "52 Week Low",
    "52 Week Change",
    "Volume",
    "Average Volume",
    "Beta",
    "RSI",
    "MACD"
  ],
  "Cash Flow": [
    "Cash Flow From Operating",
    "Cash Flow From Investing",
    "Cash Flow From Financing",
    "Free Cash Flow",
    "FCF",
    "Cash and Cash Equivalents"
  ],
  "Balance Sheet": [
    "Total Assets",
    "Total Liabilities",
    "Shareholders Equity",
    "Inventory",
    "Accounts Receivable",
    "Accounts Payable"
  ],
  "Efficiency": [
    "Asset Turnover",
    "Inventory Turnover",
    "Receivables Turnover",
    "Working Capital",
    "Working Capital Turnover"
  ],
  "Dividends": [
    "Payout Ratio",
    "Dividend Payout Ratio"
  ],
  "Recent": [
    "Market Capitalization",
    "Price to Earning",
    "Price to Book Value",
    "Dividend Yield",
    "Return on Equity",
    "Return on Capital Employed",
    "EPS",
    "Debt",
    "Promoter Holding",
    "Sales",
    "Profit After Tax",
    "Sales Latest Quarter",
    "Profit After Tax Latest Quarter",
    "YoY Quarterly Sales Growth",
    "YoY Quarterly Profit Growth",
    "Current Price",
    "Earnings Yield",
    "Debt to Equity",
    "Current Ratio",
    "Interest Coverage Ratio",
    "Asset Turnover",
    "Working Capital"
  ],
  "Preceding": [
    "Sales Growth 3Years",
    "Profit Growth 3Years"
  ],
  "Historical": [
    "Sales Growth 5Years",
    "Profit Growth 5Years"
  ]
}

const clsx = (...a) => a.filter(Boolean).join(" ")

function fmt(v, opts = {}) {
  if (v == null || v === "" || (typeof v === "number" && !isFinite(v))) return "—"
  let n = typeof v === "string" ? parseFloat(v) : v
  if (isNaN(n)) return "—"
  const { prefix = "", suffix = "", indian, decimals } = opts
  let s
  if (indian) s = IN.format(n)
  else if (typeof decimals === "number") s = n.toFixed(decimals)
  else s = USD.format(n)
  return `${prefix}${s}${suffix}`
}

function fmtVal(v, suf = "") {
  if (v == null || v === "" || (typeof v === "number" && !isFinite(v))) return "—"
  const n = typeof v === "string" ? parseFloat(v) : v
  if (isNaN(n)) return "—"
  return `${IN.format(n)}${suf}`
}

function fmtPct(v) {
  if (v == null || v === "" || (typeof v === "number" && !isFinite(v))) return "—"
  const n = typeof v === "string" ? parseFloat(v) : v
  if (isNaN(n)) return "—"
  const s = n > 0 ? `+${n.toFixed(2)}` : n.toFixed(2)
  return `${s}%`
}

// ─────────────────────────────────────────────────────────
//  TICKER MARQUEE
// ─────────────────────────────────────────────────────────
function TickerMarquee() {
  const [items, setItems] = useState([
    { sym: "NIFTY50", price: 24280, chg: 0.42 },
    { sym: "SENSEX", price: 79850, chg: -0.18 },
    { sym: "SBIN", price: 949, chg: 1.25 },
    { sym: "HDFCBANK", price: 1680, chg: -0.55 },
    { sym: "INFY", price: 1620, chg: 0.88 },
    { sym: "RELIANCE", price: 3120, chg: -0.32 },
    { sym: "ICICIBANK", price: 1285, chg: 0.71 },
    { sym: "TCS", price: 3920, chg: -0.14 },
    { sym: "KOTAKBANK", price: 1850, chg: 0.25 },
    { sym: "AXISBANK", price: 1145, chg: -0.42 },
    { sym: "LT", price: 3750, chg: 0.63 },
    { sym: "BHARTIARTL", price: 1430, chg: 0.12 },
  ])

  useEffect(() => {
    async function fetchIndices() {
      try {
        const r = await axios.get(`${API}/api/price-history?symbol=NIFTY50&period=5d`, { timeout: 5000 })
        if (r.data?.data?.length > 0) {
          const d = r.data.data
          const last = d[d.length - 1]
          const prev = d.length > 1 ? d[d.length - 2] : d[0]
          const chg = prev.close ? ((last.close - prev.close) / prev.close * 100).toFixed(2) : 0
          setItems(prev => {
            const next = [...prev]
            next[0] = { ...next[0], price: last.close, chg: parseFloat(chg) }
            return next
          })
        }
      } catch {}
    }
    const int = setInterval(fetchIndices, 30000)
    fetchIndices()
    return () => clearInterval(int)
  }, [])

  const doubled = [...items, ...items, ...items]
  return (
    <div className="ticker-marquee">
      <div className="ticker-track">
        {doubled.map((it, i) => (
          <span key={i} className="ticker-item">
            <span className="ticker-sym">{it.sym}</span>
            <span className="ticker-price">{IN.format(it.price)}</span>
            <span className={it.chg >= 0 ? "ticker-chg-pos" : "ticker-chg-neg"}>
              {it.chg >= 0 ? "+" : ""}{it.chg.toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  GAUGE SVG
// ─────────────────────────────────────────────────────────
function RsiGauge({ rsi }) {
  const angle = rsi != null ? Math.max(0, Math.min(100, rsi)) / 100 : 0.5
  const deg = 180 * angle - 90
  const color = rsi >= 70 ? "var(--negative)" : rsi <= 30 ? "var(--positive)" : "var(--accent)"
  const label = rsi >= 70 ? "Overbought" : rsi <= 30 ? "Oversold" : "Neutral"
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "20px" }}>
      <svg width="240" height="160" viewBox="0 0 240 160" style={{ display: "block" }}>
        {/* Background arc */}
        <path d="M20 130 A100 100 0 0 1 220 130" fill="none" stroke="var(--border)" strokeWidth="18" strokeLinecap="round" />
        {/* Value arc */}
        <path d="M20 130 A100 100 0 0 1 220 130" fill="none" stroke={color} strokeWidth="18" strokeDasharray={`${angle * 314} 314`} strokeLinecap="round" />
        {/* Needle */}
        <line x1="120" y1="130" x2={120 + 85 * Math.cos((deg * Math.PI) / 180)} y2={130 + 85 * Math.sin((deg * Math.PI) / 180)} stroke={color} strokeWidth="3" strokeLinecap="round" />
        {/* Center dot */}
        <circle cx="120" cy="130" r="5" fill={color} />
        {/* RSI value */}
        <text x="120" y="85" textAnchor="middle" fill="var(--text)" fontFamily="'IBM Plex Mono',monospace" fontSize="36" fontWeight="700">{rsi != null ? rsi.toFixed(1) : "—"}</text>
        {/* Label */}
        <text x="120" y="110" textAnchor="middle" fill="var(--text-muted)" fontFamily="'IBM Plex Mono',monospace" fontSize="12" fontWeight="500">RSI</text>
        {/* Scale markers */}
        <text x="22" y="140" fill="var(--text-muted)" fontSize="10" fontFamily="'IBM Plex Mono',monospace">0</text>
        <text x="120" y="150" textAnchor="middle" fill="var(--text-muted)" fontSize="10" fontFamily="'IBM Plex Mono',monospace">50</text>
        <text x="218" y="140" textAnchor="end" fill="var(--text-muted)" fontSize="10" fontFamily="'IBM Plex Mono',monospace">100</text>
      </svg>
      <span style={{ fontSize: 12, color, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{label}</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  PRICE LINE CHART (Chart.js) — closing-price line from API OHLC
// ─────────────────────────────────────────────────────────
function PriceLineChart({ points }) {
  const chartData = useMemo(() => ({
    labels: points.map(p => fmtDay(p.time)),
    datasets: [{
      label: "Close",
      data: points.map(p => p.close),
      borderColor: "#00d4aa",
      backgroundColor: "rgba(0,212,170,0.08)",
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      pointHitRadius: 6,
      borderWidth: 2,
    }],
  }), [points])

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#0d1625",
        borderColor: "#1a2744",
        borderWidth: 1,
        titleColor: "#e2e8f0",
        bodyColor: "#e2e8f0",
        callbacks: { label: (ctx) => ` ${IN.format(ctx.parsed.y)}` },
      },
    },
    scales: {
      x: {
        ticks: { color: "#5b6f8c", maxTicksLimit: 8, maxRotation: 0 },
        grid: { color: "#1a2744" },
      },
      y: {
        ticks: { color: "#5b6f8c", callback: (v) => IN.format(v) },
        grid: { color: "#1a2744" },
      },
    },
  }), [])

  return <Line data={chartData} options={options} />
}

// ─────────────────────────────────────────────────────────
//  PRICE CHART — switchable Line (Chart.js) / Candlestick (Lightweight Charts)
// ─────────────────────────────────────────────────────────
function PriceChart({ symbol, data: apiData, mode, onModeChange }) {
  const container = useRef(null);
  const chartRef = useRef(null);

  const candles = useMemo(() => {
    const rows = apiData?.data || []
    const out = []
    for (const r of rows) {
      const open = Number(r.open)
      const high = Number(r.high)
      const low = Number(r.low)
      const close = Number(r.close)
      if (![open, high, low, close].every(Number.isFinite)) continue
      let t = r.time
      if (typeof t === "string") {
        const parsed = Date.parse(t)
        t = Number.isNaN(parsed) ? null : Math.floor(parsed / 1000)
      } else {
        t = Number(t)
      }
      if (!Number.isFinite(t) || t <= 0) continue
      out.push({ time: t, open, high, low, close })
    }
    out.sort((a, b) => a.time - b.time)
    const deduped = []
    for (const c of out) {
      if (deduped.length > 0 && deduped[deduped.length - 1].time === c.time) continue
      deduped.push(c)
    }
    return deduped
  }, [apiData])

  useEffect(() => {
    const el = container.current
    if (!el || candles.length === 0) return
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: "'IBM Plex Mono', monospace",
      },
      grid: {
        vertLines: { color: "rgba(26, 39, 68, 0.6)" },
        horzLines: { color: "rgba(26, 39, 68, 0.6)" },
      },
      rightPriceScale: { borderColor: "rgba(26, 39, 68, 1)" },
      timeScale: { borderColor: "rgba(26, 39, 68, 1)", timeVisible: false, rightOffset: 4 },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#3b82f6", labelBackgroundColor: "#2563eb" },
        horzLine: { color: "#3b82f6", labelBackgroundColor: "#2563eb" },
      },
      localization: { priceFormatter: (p) => IN.format(p) },
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      borderVisible: false,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    })

    series.setData(candles)
    chart.timeScale().fitContent()
    chartRef.current = chart

    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [candles, mode])

  const last = candles.length > 0 ? candles[candles.length - 1] : null
  const prev = candles.length > 1 ? candles[candles.length - 2] : null
  const chg = last && prev ? last.close - prev.close : 0
  const chgPct = last && prev && prev.close ? (chg / prev.close) * 100 : 0

  return (
    <div className="chart-section">
      <div className="chart-header">
        <div>
          <span className="chart-title">{symbol} Price Action</span>
          {last && <span style={{ marginLeft: 12, fontFamily: "'IBM Plex Mono',monospace", fontSize: 18, fontWeight: 600 }}>{IN.format(last.close)}</span>}
          {last && (
            <span className={chg >= 0 ? "ticker-chg-pos" : "ticker-chg-neg"} style={{ marginLeft: 8, fontSize: 13 }}>
              {chg >= 0 ? "▲" : "▼"} {chgPct.toFixed(2)}%
            </span>
          )}
        </div>
        <div className="chart-toggles">
          <button className={clsx("chart-toggle-btn", mode === "line" && "active")} onClick={() => onModeChange("line")}>Line</button>
          <button className={clsx("chart-toggle-btn", mode === "candlestick" && "active")} onClick={() => onModeChange("candlestick")}>Candlestick</button>
        </div>
      </div>
      <div className="price-chart-wrap" style={{ height: "500px", position: "relative" }}>
        {candles.length > 0 ? (
          mode === "candlestick" ? (
            <div ref={container} style={{ height: "100%", width: "100%" }}></div>
          ) : (
            <PriceLineChart points={candles} />
          )
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)" }}>
            {symbol ? "No price data available for this symbol" : "Select a company to view its chart"}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  FINANCIAL TABLE with TABS
// ─────────────────────────────────────────────────────────
function FinancialTables({ statements }) {
  const [tab, setTab] = useState("pnl")

  const tabs = useMemo(() => {
    const items = []
    if (statements?.annualPnl?.columns?.length) items.push({ key: "pnl", label: "P&L", table: statements.annualPnl })
    if (statements?.balanceSheet?.columns?.length) items.push({ key: "bs", label: "BALANCE SHEET", table: statements.balanceSheet })
    if (statements?.cashFlow?.columns?.length) items.push({ key: "cf", label: "CASH FLOW", table: statements.cashFlow })
    return items
  }, [statements])

  const active = tabs.find(t => t.key === tab) || tabs[0]
  if (!active) return null

  return (
    <div className="financials-section">
      <div className="fin-tabs">
        {tabs.map(t => (
          <button key={t.key} className={clsx("fin-tab", t.key === tab && "active")} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      <div className="fin-table-wrap">
        <table className="fin-table">
          <thead>
            <tr>
              <th>Metric</th>
              {active.table.columns.map(c => <th key={c}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {Object.entries(active.table.rows).map(([label, values], ri) => (
              <tr key={label} className={ri % 2 ? "alt-row" : ""}>
                <td>{label}</td>
                {values.map((v, vi) => (
                  <td key={vi} className={v < 0 ? "negative" : ""}>{fmtVal(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────
//  PEER TABLE
// ─────────────────────────────────────────────────────────
function PeerTable({ peers, currentSymbol }) {
  if (!peers?.length) return null
  return (
    <table className="peer-table">
      <thead>
        <tr><th>Ticker</th><th>Price (₹)</th><th>P/E</th><th>Mkt Cap (Cr)</th></tr>
      </thead>
      <tbody>
        {peers.map(p => (
          <tr key={p.ticker} className={p.ticker === currentSymbol ? "highlight-row" : ""}>
            <td>{p.ticker}</td>
            <td>{fmtVal(p.price)}</td>
            <td>{fmt(p.pe, { decimals: 1 })}</td>
            <td>{p.mktCap ? IN.format(p.mktCap / 1e7) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ─────────────────────────────────────────────────────────
//  MAIN APP
// ─────────────────────────────────────────────────────────
export default function App() {
  const [mode, setMode] = useState("home")        // home | loading | data | error | screener | screenerLoading | aiAgent
  const [query, setQuery] = useState("")
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [priceHist, setPriceHist] = useState(null)
  const [peers, setPeers] = useState(null)
  const [chartView, setChartView] = useState("annual")
  const [priceChartMode, setPriceChartMode] = useState("candlestick")   // "line" | "candlestick"
  const [finTab, setFinTab] = useState("pnl")
  const [homeView, setHomeView] = useState("cards")   // "cards" | "search"
  const exportRef = useRef(null)
  
  // Screener state
  const [screenerFilters, setScreenerFilters] = useState({
    market: "india",
    use_local_db: false,
    query: "",
    limit: 15,
    max_symbols: "all",
  })
  const [screenerResults, setScreenerResults] = useState(null)
  const [screenerError, setScreenerError] = useState(null)
  const [showRatioGallery, setShowRatioGallery] = useState(false)
  const [aiAgent, setAiAgent] = useState({
    status: "idle",
    message: "",
    url: "http://127.0.0.1:5173",
  })
  const [riskDesk, setRiskDesk] = useState({
    status: "idle",
    message: "",
    url: "http://127.0.0.1:5174",
  })
  const [tradeJournal, setTradeJournal] = useState({
    status: "idle",
    message: "",
    url: "http://127.0.0.1:4173",
  })

  // ── History helpers ──
  const goHome = () => {
    setMode("home")
    setData(null)
    setError(null)
    setQuery("")
    setPriceHist(null)
    setPeers(null)
    setHomeView("cards")
    setScreenerResults(null)
    setScreenerError(null)
    setAiAgent(prev => ({ ...prev, status: "idle", message: "" }))
    setRiskDesk(prev => ({ ...prev, status: "idle", message: "" }))
  }

  // ── search state ──
  const [searchResults, setSearchResults] = useState([])
  const [searchVal, setSearchVal] = useState("")
  const searchTimer = useRef(null)

  const handleSearch = useCallback((val) => {
    setSearchVal(val)
    clearTimeout(searchTimer.current)
    if (val.length < 2) { setSearchResults([]); return }
    searchTimer.current = setTimeout(async () => {
      try {
        const r = await axios.get(`${API}/api/search?q=${encodeURIComponent(val)}`)
        setSearchResults(r.data || [])
      } catch { setSearchResults([]) }
    }, 250)
  }, [])

  const selectResult = (res) => {
    setSearchResults([])
    setSearchVal(res.symbol || res.name || "")
    analyze(res.symbol || res.name)
  }

  // ── analyze ──
  const analyze = useCallback(async (val) => {
    const q = (val || searchVal).trim()
    if (!q) return
    console.log('ANALYZE: starting query=', q)
    setQuery(q)
    setMode("loading")
    setError(null)
    setData(null)
    setPriceHist(null)
    setPeers(null)
    try {
      console.log('ANALYZE: fetching analyze API...')
      const res = await axios.get(`${API}/api/analyze?q=${encodeURIComponent(q)}`)
      console.log('ANALYZE: got response, company=', res.data?.company?.name)
      if (res.data?.error) { console.log('ANALYZE: got error', res.data.error); setError(res.data.error); setMode("error"); return }
      setData(res.data)
      console.log('ANALYZE: data set, fetching price+peers...')

      // fetch price history
      const sym = (res.data.company?.ticker || q).toUpperCase()
      try {
        const [phRes, peerRes] = await Promise.all([
          axios.get(`${API}/api/price-history?symbol=${sym}&period=1y`, { timeout: 10000 }),
          axios.get(`${API}/api/peers?symbol=${sym}`, { timeout: 8000 }),
        ])
        if (phRes.data?.data) setPriceHist({ symbol: phRes.data.symbol, data: phRes.data.data })
        if (peerRes.data?.peers) setPeers(peerRes.data.peers)
      } catch {}

      setMode("data")
    } catch (e) {
      console.log('ANALYZE: OUTER catch triggered:', e?.message)
      setError(e.response?.data?.error || e.message || "Unknown error")
      setMode("error")
    }
  }, [searchVal])

  // ── PDF export ──
  const exportPdf = async () => {
    if (!exportRef.current) return
    try {
      const canvas = await html2canvas(exportRef.current, {
        backgroundColor: "#06090f",
        scale: 1.6,
      })
      const image = canvas.toDataURL("image/png")
      const pdf = new jsPDF("p", "mm", "a4")
      const pageWidth = 210
      const pageHeight = 297
      const imageHeight = (canvas.height * pageWidth) / canvas.width
      let remaining = imageHeight
      let position = 0

      pdf.addImage(image, "PNG", 0, position, pageWidth, imageHeight)
      remaining -= pageHeight

      while (remaining > 0) {
        position = remaining - imageHeight
        pdf.addPage()
        pdf.addImage(image, "PNG", 0, position, pageWidth, imageHeight)
        remaining -= pageHeight
      }
      pdf.save(`${(data?.company?.name || "analysis").replace(/[^a-z0-9]/gi, "_").toLowerCase()}_analysis.pdf`)
    } catch (e) {
      console.error("exportPdf failed:", e)
    }
  }

  // ── Excel export ──
  const exportExcel = () => {
    if (!data) return
    const wb = XLSX.utils.book_new()
    const addSheet = (name, table) => {
      const header = table.columns || []
      const rows = []
      for (const [k, v] of Object.entries(table.rows || {})) rows.push([k, ...v])
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([header, ...rows]), name)
    }
    if (data.statements?.annualPnl) addSheet("P&L", data.statements.annualPnl)
    if (data.statements?.balanceSheet) addSheet("Balance Sheet", data.statements.balanceSheet)
    if (data.statements?.cashFlow) addSheet("Cash Flow", data.statements.cashFlow)

    const summary = [
      ["Field", "Value"],
      ["Company", data.company?.name || ""],
      ["Price", data.price?.current],
      ["P/E (TTM)", data.valuation?.peTtm],
      ["ROE", data.derived?.roe],
      ["ROCE", data.derived?.roce],
      ["Timestamp", data.timestamp],
    ]
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(summary), "Summary")
    XLSX.writeFile(wb, `${(data.company?.name || "analysis").replace(/[^a-z0-9]/gi, "_").toLowerCase()}_analyser.xlsx`)
  }
  
  // ── add ratio to query ──
  const addRatioToQuery = (ratio) => {
    const existingQuery = screenerFilters.query.trim()
    const newLine = `${ratio} > `
    const newQuery = existingQuery 
      ? `${existingQuery}\n${newLine}` 
      : newLine
    setScreenerFilters(prev => ({ ...prev, query: newQuery }))
  }
  
  // ── run screener ──
  const runScreener = useCallback(async () => {
    setMode("screenerLoading")
    setScreenerError(null)
    try {
      const res = await axios.post(`${API}/api/screener`, screenerFilters, { timeout: 600000 })
      setScreenerResults(res.data)
      setMode("screener")
    } catch (e) {
      setScreenerError(e.response?.data?.error || e.message || "Failed to run screener")
      setMode("screener")
    }
  }, [screenerFilters])

  const openAiAgent = useCallback(async () => {
    setMode("aiAgent")
    setAiAgent(prev => ({ ...prev, status: "starting", message: "Starting AI analysis workspace..." }))
    try {
      const startRes = await axios.post(`${API}/api/ai-agent/start`, {}, { timeout: 12000 })
      const frontendUrl = startRes.data?.frontend_url || "http://127.0.0.1:5173"
      setAiAgent({ status: "starting", message: "Launching agent interface...", url: frontendUrl })

      for (let i = 0; i < 15; i += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        const statusRes = await axios.get(`${API}/api/ai-agent/status`, { timeout: 4000 })
        if (statusRes.data?.frontend_live) {
          setAiAgent({ status: "ready", message: "", url: statusRes.data.frontend_url || frontendUrl })
          return
        }
      }

      setAiAgent({
        status: "waiting",
        message: "The agent is still warming up. You can open it in a new tab while it finishes.",
        url: frontendUrl,
      })
    } catch (e) {
      setAiAgent({
        status: "error",
        message: e.response?.data?.message || e.message || "Could not start AI analysis workspace.",
        url: "http://127.0.0.1:5173",
      })
    }
  }, [])

  const openRiskDesk = useCallback(async () => {
    setMode("riskDesk")
    setRiskDesk(prev => ({ ...prev, status: "starting", message: "Starting RiskDesk workspace..." }))
    try {
      const startRes = await axios.post(`${API}/api/riskdesk/start`, {}, { timeout: 20000 })
      const frontendUrl = startRes.data?.frontend_url || "http://127.0.0.1:5174"
      setRiskDesk({ status: "starting", message: "Launching risk calculator interface...", url: frontendUrl })

      for (let i = 0; i < 18; i += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        const statusRes = await axios.get(`${API}/api/riskdesk/status`, { timeout: 4000 })
        if (statusRes.data?.frontend_live) {
          setRiskDesk({ status: "ready", message: "", url: statusRes.data.frontend_url || frontendUrl })
          return
        }
      }

      setRiskDesk({
        status: "waiting",
        message: "RiskDesk is still warming up. You can open it in a new tab while it finishes.",
        url: frontendUrl,
      })
    } catch (e) {
      setRiskDesk({
        status: "error",
        message: e.response?.data?.message || e.message || "Could not start RiskDesk.",
        url: "http://127.0.0.1:5174",
      })
    }
  }, [])

  const openTradeJournal = useCallback(async () => {
    setMode("tradeJournal")
    setTradeJournal(prev => ({ ...prev, status: "starting", message: "Starting Trade Journal workspace..." }))
    try {
      const startRes = await axios.post(`${API}/api/trade-journal/start`, {}, { timeout: 20000 })
      const frontendUrl = startRes.data?.frontend_url || "http://127.0.0.1:4173"
      setTradeJournal({ status: "starting", message: "Launching trading journal...", url: frontendUrl })

      for (let i = 0; i < 12; i += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        const statusRes = await axios.get(`${API}/api/trade-journal/status`, { timeout: 4000 })
        if (statusRes.data?.frontend_live) {
          setTradeJournal({ status: "ready", message: "", url: statusRes.data.frontend_url || frontendUrl })
          return
        }
      }

      setTradeJournal({
        status: "waiting",
        message: "The Trade Journal is still warming up. You can open it in a new tab while it finishes.",
        url: frontendUrl,
      })
    } catch (e) {
      setTradeJournal({
        status: "error",
        message: e.response?.data?.message || e.message || "Could not start the Trade Journal.",
        url: "http://127.0.0.1:4173",
      })
    }
  }, [])

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") goHome() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])

  // ── chart data from api ──
  const annualChart = data?.charts?.annual || []
  const quarterlyChart = data?.charts?.quarterly || []

  const revChartData = useMemo(() => {
    const src = chartView === "annual" ? annualChart : quarterlyChart
    return {
      labels: src.map(i => i.period),
      datasets: [
        { type: "bar", label: "Sales", data: src.map(i => i.sales), backgroundColor: "rgba(59,158,255,0.35)", borderColor: "#3b9eff", borderRadius: 2 },
        { type: "line", label: "Net Profit", data: src.map(i => i.netProfit), borderColor: "#00d4aa", backgroundColor: "#00d4aa", tension: 0.25, pointRadius: 2 },
        { type: "line", label: "Operating Profit", data: src.map(i => i.operatingProfit), borderColor: "#f59e0b", backgroundColor: "#f59e0b", tension: 0.25, pointRadius: 2 },
      ],
    }
  }, [annualChart, quarterlyChart, chartView])

  const marginChartData = useMemo(() => ({
    labels: annualChart.map(i => i.period),
    datasets: [
      { label: "Gross Margin %", data: annualChart.map(i => i.grossMargin), borderColor: "#f59e0b", tension: 0.28, pointRadius: 2 },
      { label: "Operating Margin %", data: annualChart.map(i => i.operatingMargin), borderColor: "#3b9eff", tension: 0.28, pointRadius: 2 },
      { label: "Net Margin %", data: annualChart.map(i => i.netMargin), borderColor: "#00d4aa", tension: 0.28, pointRadius: 2 },
    ],
  }), [annualChart])

  const chartOpts = (yLbl) => ({
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#5b6f8c", usePointStyle: true, boxWidth: 8 } },
      tooltip: { backgroundColor: "#0d1625", borderColor: "#1a2744", borderWidth: 1, titleColor: "#e2e8f0", bodyColor: "#e2e8f0" },
    },
    scales: {
      x: { ticks: { color: "#5b6f8c", maxTicksLimit: 8 }, grid: { color: "#1a2744" } },
      y: { ticks: { color: "#5b6f8c" }, grid: { color: "#1a2744" }, title: { display: true, text: yLbl, color: "#5b6f8c" } },
    },
  })

  /* ── HOME: WORKSPACE CARDS ── */
  if (mode === "home" && homeView === "cards") {
    const ICONS = {
      Analyzer: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 17V13"/><path d="M12 17V9"/><path d="M16 17V5"/>
        </svg>
      ),
      Screener: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
        </svg>
      ),
      "Risk Calculator": (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="10" y2="10"/><line x1="14" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="10" y2="14"/><line x1="14" y1="14" x2="16" y2="14"/><line x1="8" y1="18" x2="10" y2="18"/><line x1="14" y1="18" x2="16" y2="18"/>
        </svg>
      ),
      "Trade Journal": (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
      ),
      "AI Analysis": (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2v4"/><path d="M12 18v4"/><path d="M4.93 4.93l2.83 2.83"/><path d="M16.24 16.24l2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="M4.93 19.07l2.83-2.83"/><path d="M16.24 7.76l2.83-2.83"/><circle cx="12" cy="12" r="4"/><path d="M10.8 10.8h.01"/><path d="M13.2 10.8h.01"/><path d="M10.8 13.2h2.4"/>
        </svg>
      ),
    }
    const WORKSPACES = [
      { title: "Analyzer", status: "live", desc: "Deep-dive fundamental analysis for any NSE/BSE listed company. Price charts, ratios, financials & more.", action: () => setHomeView("search"), cta: "Open terminal" },
      { title: "Screener", status: "live", desc: "Filter thousands of stocks by custom fundamental criteria. Build your own quantitative screens.", action: () => setMode("screener"), cta: "Open terminal" },
      { title: "Risk Calculator", status: "live", desc: "Position sizing, risk/reward planning, and portfolio allocation tools.", action: openRiskDesk, cta: "Open terminal" },
      { title: "Trade Journal", status: "live", desc: "Log trades, track setups, review performance, and build discipline.", action: openTradeJournal, cta: "Open terminal" },
      { title: "AI Analysis", status: "live", desc: "Open your separate Stock Market Agent for conversational market analysis, fundamentals context, and chart-aware answers.", action: openAiAgent, cta: "Open AI", featured: true },
    ]
    return (
      <div className="home-page">
        <div className="home-top-logo">
          <div className="home-top-logo-icon">◆</div>
          EFE
        </div>
        <div className="home-hero fade-in">
          <div className="home-eyebrow">EQUITY FUNDAMENTAL ENGINE</div>
          <h1 className="home-title">Choose a workspace</h1>
          <p className="home-subtitle">Your institutional-grade equity research terminal. Select a module to get started.</p>
        </div>
        <div className="home-grid fade-in">
          {WORKSPACES.map((item) => (
            <button
              key={item.title}
              className={clsx("home-card", item.featured && "home-card-featured", item.disabled && "home-card-disabled")}
              onClick={item.disabled ? undefined : item.action}
              disabled={item.disabled}
            >
              <div className="home-card-header">
                <div className="home-card-title-row">
                  <div className={clsx("home-card-icon-wrap", item.disabled && "disabled-icon")}>
                    {ICONS[item.title]}
                  </div>
                  <span className="home-card-title">{item.title}</span>
                </div>
                <span className={clsx("home-chip", item.status === "live" ? "live" : "planned")}>
                  {item.status === "live" ? "LIVE" : "PLANNED"}
                </span>
              </div>
              <p>{item.desc}</p>
              <div className="home-card-cta">{item.cta} <span className="home-card-cta-arrow">→</span></div>
            </button>
          ))}
        </div>
      </div>
    )
  }

  /* ── HOME: ANALYZER SEARCH ── */
  if (mode === "aiAgent") {
    const isReady = aiAgent.status === "ready"
    return (
      <div className="ai-agent-page">
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">AI Analysis</span>
          </div>
          <div className="top-nav-right">
            <a className="top-nav-home-btn" href={aiAgent.url} target="_blank" rel="noreferrer">Open tab</a>
            <button className="top-nav-home-btn" onClick={goHome}>← Home</button>
          </div>
        </nav>
        {!isReady && (
          <div className="ai-agent-launch-panel fade-in">
            <div className="ai-agent-icon">AI</div>
            <h1>AI Analysis</h1>
            <p>{aiAgent.message || "Preparing the agent workspace..."}</p>
            {aiAgent.status === "error" && (
              <button className="ai-agent-retry" onClick={openAiAgent}>Retry launch</button>
            )}
          </div>
        )}
        {isReady && (
          <iframe
            className="ai-agent-frame"
            title="Stock Market Agent"
            src={aiAgent.url}
          />
        )}
      </div>
    )
  }

  if (mode === "riskDesk") {
    const isReady = riskDesk.status === "ready"
    return (
      <div className="ai-agent-page">
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">Risk Calculator</span>
          </div>
          <div className="top-nav-right">
            <a className="top-nav-home-btn" href={riskDesk.url} target="_blank" rel="noreferrer">Open tab</a>
            <button className="top-nav-home-btn" onClick={goHome}>← Home</button>
          </div>
        </nav>
        {!isReady && (
          <div className="ai-agent-launch-panel fade-in">
            <div className="ai-agent-icon">RC</div>
            <h1>Risk Calculator</h1>
            <p>{riskDesk.message || "Preparing RiskDesk workspace..."}</p>
            {riskDesk.status === "error" && (
              <button className="ai-agent-retry" onClick={openRiskDesk}>Retry launch</button>
            )}
          </div>
        )}
        {isReady && (
          <iframe
            className="ai-agent-frame"
            title="RiskDesk"
            src={riskDesk.url}
          />
        )}
      </div>
    )
  }

  if (mode === "tradeJournal") {
    const isReady = tradeJournal.status === "ready"
    return (
      <div className="ai-agent-page">
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">Trade Journal</span>
          </div>
          <div className="top-nav-right">
            <a className="top-nav-home-btn" href={tradeJournal.url} target="_blank" rel="noreferrer">Open tab</a>
            <button className="top-nav-home-btn" onClick={goHome}>← Home</button>
          </div>
        </nav>
        {!isReady && (
          <div className="ai-agent-launch-panel fade-in">
            <div className="ai-agent-icon">TJ</div>
            <h1>Trade Journal</h1>
            <p>{tradeJournal.message || "Preparing journal workspace..."}</p>
            {tradeJournal.status === "error" && (
              <button className="ai-agent-retry" onClick={openTradeJournal}>Retry launch</button>
            )}
          </div>
        )}
        {isReady && (
          <iframe
            className="ai-agent-frame"
            title="Trade Journal"
            src={tradeJournal.url}
          />
        )}
      </div>
    )
  }

  if (mode === "home" && homeView === "search") {
    return (
      <div className="analyzer-page">
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">Analyzer</span>
          </div>
          <div className="top-nav-right">
            <button className="top-nav-home-btn" onClick={goHome}>⌂ Home</button>
          </div>
        </nav>
        <div className="analyzer-hero fade-in">
          <h1 className="analyzer-title">Stock Analyzer</h1>
          <p className="analyzer-subtitle">Search any NSE/BSE listed company by name or ticker</p>
        </div>
        <div className="analyzer-search-wrap fade-in">
          <div className="analyzer-search-bar">
            <span className="analyzer-search-icon">🔍</span>
            <input
              className="analyzer-search-input"
              placeholder="Search by name or ticker (RELIANCE, HDFCBANK, TCS...)"
              value={searchVal}
              onChange={e => handleSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && analyze(searchVal)}
              autoFocus
            />
            <button className="analyzer-search-btn" onClick={() => analyze(searchVal)}>ANALYZE →</button>
          </div>
          {searchResults.length > 0 && (
            <div className="analyzer-dropdown">
              {searchResults.map((r, i) => (
                <button key={i} className="analyzer-dropdown-row" onClick={() => selectResult(r)}>
                  <span>{r.name || r.companyName || r.symbol}</span>
                  <span className="analyzer-dropdown-ticker">{r.symbol || ""}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="analyzer-footer fade-in">
          <div className="analyzer-recent">
            <span>Recently Analyzed</span>
            {["RELIANCE", "HDFCBANK", "INFY"].map(t => (
              <button key={t} className="analyzer-recent-chip" onClick={() => analyze(t)}>{t}</button>
            ))}
          </div>
          <button className="analyzer-back-link" onClick={() => setHomeView("cards")}>← Back to workspaces</button>
        </div>
      </div>
    )
  }

  if (mode === "loading") {
    return (
      <>
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">Analyzer</span>
          </div>
          <div className="top-nav-right">
            <button className="top-nav-home-btn" onClick={goHome}>⌂ Home</button>
          </div>
        </nav>
        <div className="loading-screen">
          <div className="loading-box fade-in">
            <div className="loading-title">Analysing <span style={{ color: "var(--accent)" }}>{query.toUpperCase()}</span></div>
            <div className="loading-line">fetching company fundamentals</div>
            <div className="loading-line">computing valuation ratios</div>
            <div className="loading-line">loading 1-year price history</div>
            <div className="loading-line">fetching peer comparison data</div>
            <div className="loading-line" style={{ color: "var(--accent)" }}><span className="loading-cursor">▋</span></div>
          </div>
        </div>
      </>
    )
  }

  if (mode === "screener" || mode === "screenerLoading") {
    return (
      <>
        <nav className="top-nav">
          <div className="top-nav-left">
            <div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div>
            <span className="top-nav-divider">›</span>
            <span className="top-nav-breadcrumb">Screener</span>
          </div>
          <div className="top-nav-right">
            <button className="top-nav-home-btn" onClick={goHome}>← Home</button>
          </div>
        </nav>
        <div className="screener-page">
          <div className="screener-eyebrow">SCREENER</div>
          <h1 className="screener-title">Filter Stocks by Fundamentals</h1>
          <p className="screener-subtitle">Write natural-language filter queries across thousands of Indian &amp; US stocks.</p>

          <div className="screener-controls">
            <div className="screener-control-card">
              <div className="screener-control-label">Market</div>
              <select className="screener-select" value={screenerFilters.market} onChange={e => setScreenerFilters(prev => ({ ...prev, market: e.target.value }))}>
                <option value="india">India (NSE)</option>
                <option value="us">US Markets</option>
                <option value="all">All Markets</option>
              </select>
            </div>
            <div className="screener-control-card">
              <div className="screener-control-label">Limit</div>
              <input type="number" className="screener-number-input" value={screenerFilters.limit} onChange={e => setScreenerFilters(prev => ({ ...prev, limit: Number(e.target.value) }))} />
            </div>
            <div className="screener-control-card">
              <div className="screener-control-label">Universe</div>
              <select className="screener-select" value={screenerFilters.max_symbols} onChange={e => setScreenerFilters(prev => ({ ...prev, max_symbols: e.target.value }))}>
                <option value="all">All master index</option>
                <option value="1000">First 1000</option>
                <option value="500">First 500</option>
                <option value="100">First 100</option>
                <option value="30">First 30</option>
              </select>
            </div>
            <div className="screener-control-card">
              <div className="screener-control-label">Data Source</div>
              <select className="screener-select" value={screenerFilters.use_local_db ? "true" : "false"} onChange={e => setScreenerFilters(prev => ({ ...prev, use_local_db: e.target.value === "true" }))}>
                <option value="false">Excel + Yahoo</option>
                <option value="true">Local Cache</option>
              </select>
            </div>
          </div>

          <div className="screener-query-card">
            <div className="screener-query-header">
              <div className="screener-query-label">Filter Query</div>
              <div className="screener-query-btns">
                <button className="btn-show-ratios" onClick={() => setShowRatioGallery(!showRatioGallery)}>
                  {showRatioGallery ? "Hide Ratios" : "Show All Ratios"}
                </button>
                <button className="btn-multibagger-teal" onClick={() => setScreenerFilters(prev => ({ ...prev, query: `Sales Growth > 15\nProfit Growth > 20\nReturn on Capital Employed > 20\nDebt to Equity < 0.5\nPromoter Holding > 50\nMarket Capitalization < 50000` }))}>
                  Multibagger ⚡
                </button>
              </div>
            </div>
            {showRatioGallery && (
              <div className="ratio-gallery">
                {Object.keys(RATIOS_GALLERY).map(category => (
                  <div key={category}>
                    <div className="ratio-category-label">{category}</div>
                    <div className="ratio-pills-row">
                      {RATIOS_GALLERY[category].map(ratio => (
                        <button key={ratio} className="ratio-pill" onClick={() => addRatioToQuery(ratio)}>{ratio}</button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <textarea
              className="screener-textarea"
              placeholder={`Sales Growth > 15\nProfit Growth > 20\nReturn on Capital Employed > 20`}
              value={screenerFilters.query}
              onChange={e => setScreenerFilters(prev => ({ ...prev, query: e.target.value }))}
            />
          </div>
          
          <button
            className="screener-run-btn"
            onClick={runScreener}
            disabled={mode === "screenerLoading"}
          >
            {mode === "screenerLoading" ? "⏳  RUNNING SCREENER..." : "RUN SCREENER →"}
          </button>
          
          {screenerError && (
            <div style={{ color: "var(--negative)", marginBottom: 16, fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>Error: {screenerError}</div>
          )}
          {screenerResults && screenerResults.results && screenerResults.results.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <div className="screener-results-bar">
                <span>Matched stocks</span>
                <span className="screener-count-badge">{screenerResults.count} results</span>
              </div>
              <table className="peer-table">
                <thead><tr><th>Ticker</th><th>Name</th><th>Price</th><th>Mkt Cap (Cr)</th><th>P/E</th><th>ROE (%)</th><th>ROCE (%)</th><th>D/E</th></tr></thead>
                <tbody>
                  {screenerResults.results.map((stock, i) => (
                    <tr key={stock.symbol || i}>
                      <td style={{ fontWeight: 700, cursor: "pointer", color: "var(--accent)" }} onClick={() => analyze(stock.symbol)}>{stock.symbol}</td>
                      <td style={{ cursor: "pointer" }} onClick={() => analyze(stock.symbol)}>{stock.name}</td>
                      <td>{fmtVal(stock.price)}</td>
                      <td>{fmtVal(stock.market_cap_cr)}</td>
                      <td>{fmt(stock.pe, { decimals: 1 })}</td>
                      <td>{fmt(stock.roe, { decimals: 1 })}</td>
                      <td>{fmt(stock.roce, { decimals: 1 })}</td>
                      <td>{fmt(stock.debt_to_equity, { decimals: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="screener-empty">
              <svg className="screener-empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3, margin: "0 auto 16px", display: "block" }}>
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
              </svg>
              <div className="screener-empty-text">
                {screenerResults && mode !== "screenerLoading"
                  ? (screenerResults.screen_meta?.unsupported_filters?.length ? `Unsupported: ${screenerResults.screen_meta.unsupported_filters.join(", ")}` : "No results found.")
                  : "No results yet. Run a screen to see matching stocks."}
              </div>
            </div>
          )}
        </div>
      </>
    )
  }
  
  if (mode === "error") {
    return (
      <>
        <nav className="top-nav">
          <div className="top-nav-left"><div className="top-nav-logo"><div className="top-nav-logo-icon">◆</div>EFE</div></div>
          <div className="top-nav-right"><button className="top-nav-home-btn" onClick={goHome}>⌂ Home</button></div>
        </nav>
        <div className="error-screen">
          <div className="error-box fade-in">
            <div className="error-icon">⚠️</div>
            <div className="error-text">{error}</div>
            <input className="search-input" placeholder="Try a different ticker..." value={searchVal} onChange={e => handleSearch(e.target.value)} onKeyDown={e => e.key === "Enter" && analyze(searchVal)} />
            <button className="search-btn" onClick={() => analyze(searchVal)}>↻ Retry</button>
            <button className="search-btn" onClick={goHome} style={{ borderColor: "var(--border)", color: "var(--text-muted)", background: "transparent" }}>← Home</button>
          </div>
        </div>
      </>
    )
  }

  const c = data?.company || {}
  const p = data?.price || {}
  const v = data?.valuation || {}
  const a = data?.analyst || {}
  const o = data?.ownership || {}
  const tech = data?.technicals || {}
  const ret = tech.returns || {}

  const metrics = data?.metricsGrid || []
  const currentSymbol = (c.ticker || c.symbol || query).toUpperCase()

  // ── safe helper for .toFixed — prevents crash on null/string ──
  const sf = (v, digits = 1) => {
    if (v == null) return 0
    const n = typeof v === "string" ? parseFloat(v) : v
    if (isNaN(n)) return 0
    return n
  }

  return (
    <div style={{ paddingTop: 52 }}>
      <nav className="fixed-nav">
        <div className="fixed-nav-logo"><div className="fixed-nav-logo-icon">◆</div>EFE</div>
        <span className="fixed-nav-sep">›</span>
        <span className="fixed-nav-section">Analyzer</span>
        <button className="fixed-nav-btn" onClick={goHome}>⌂ Home</button>
      </nav>
      <div ref={exportRef}>
      {/* 1. TICKER MARQUEE */}
      <SectionBoundary name="Marquee"><TickerMarquee /></SectionBoundary>

      {/* 2. HEADER RIBBON */}
      <SectionBoundary name="Header">
      <div className="header-ribbon">
        <div className="header-left">
          <span className="header-ticker">{currentSymbol} IN</span>
          <span className="header-divider" />
          <div>
            <div className="header-company">{c.name || currentSymbol}</div>
            <div className="header-sector">{c.sector || ""}{c.sector && c.industry ? " — " : ""}{c.industry || ""}</div>
          </div>
          <div className="exchange-toggle">
            <button className="exchange-btn active">NSE</button>
            <button className="exchange-btn">BSE</button>
          </div>
        </div>
        <div className="header-right">
          <div>
            <span className="header-price-large">{fmtVal(p.current, "")}</span>
            <span className={clsx("header-change", sf(p.change) >= 0 ? "ticker-chg-pos" : "ticker-chg-neg")} style={{ marginLeft: 8 }}>
              {sf(p.change) >= 0 ? "▲" : "▼"} {p.change != null ? IN.format(sf(p.change)) : ""} ({sf(p.changePct) >= 0 ? "+" : ""}{sf(p.changePct, 2).toFixed(2)}%)
            </span>
          </div>
          <div className="header-actions">
            <button className="header-btn" onClick={exportPdf}>PDF</button>
            <button className="header-btn" onClick={exportExcel}>XLSX</button>
            <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: "var(--text-muted)" }}>{data?.timestamp || ""}</span>
            <div className="live-dot" />
          </div>
        </div>
      </div>
      </SectionBoundary>

      {/* 3. QUICK STATS + 52-WEEK RANGE */}
      <SectionBoundary name="QuickStats">
      <div className="quick-stats">
        {[
          { label: "MKT CAP", value: fmtVal(v.marketCapCr, " Cr") },
          { label: "EV", value: fmtVal(v.enterpriseValueCr, " Cr") },
          { label: "P/E TTM", value: fmt(v.peTtm, { decimals: 1 }) },
          { label: "FWD P/E", value: fmt(v.forwardPe, { decimals: 1 }) },
          { label: "P/B", value: fmt(v.pb, { decimals: 1 }) },
          { label: "EV/EBITDA", value: fmt(v.evEbitda, { decimals: 1 }) },
          { label: "52W HI", value: fmtVal(p.weekHigh) },
          { label: "52W LO", value: fmtVal(p.weekLow) },
          { label: "DIV YIELD", value: fmt(v.dividendYield, { decimals: 2, suffix: "%" }) },
        ].map((s, i) => (
          <div key={i} className="quick-stat">
            <div className="quick-stat-label">{s.label}</div>
            <div className={clsx("quick-stat-value", s.label === "P/E TTM" && "accent")}>{s.value}</div>
          </div>
        ))}
      </div>
      <div className="range-belt">
        {(() => {
          const lo = p.weekLow || 0, hi = p.weekHigh || 0, cur = p.current || 0
          const range = hi - lo || 1
          const pct = ((cur - lo) / range * 100)
          return (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginBottom: 4 }}>
                <span>52W Range</span>
                <span style={{ color: "var(--accent)" }}>{fmtVal(cur)}</span>
              </div>
              <div className="range-track">
                <div className="range-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
                <div className="range-marker" style={{ left: `${Math.min(100, Math.max(0, pct))}%` }} />
              </div>
              <div className="range-labels">
                <span>{fmtVal(lo)}</span>
                <span>{fmtVal(hi)}</span>
              </div>
            </>
          )
        })()}
      </div>
      </SectionBoundary>

      {/* 4. PRICE CHART */}
      <SectionBoundary name="PriceChart"><PriceChart symbol={currentSymbol} data={priceHist} mode={priceChartMode} onModeChange={setPriceChartMode} /></SectionBoundary>

      {/* 5. MID SECTION — Metrics + Technicals */}
      <SectionBoundary name="MidSection">
      <div className="mid-section">
        <div className="mid-left">
          <div className="mid-title">Key Metrics</div>
          <div className="metrics-grid-2col">
            {metrics.slice(0, 12).map((m, i) => {
              const numVal = parseFloat(m.value)
              // Color-code: ROE/ROCE/margins positive is good; D/E lower is better
              const isRatio = !isNaN(numVal) && numVal > 0 && numVal < 100
              const formattedVal = fmt(m.value, isRatio ? { decimals: 2 } : { indian: true })
              const isPositive = !isNaN(numVal) && numVal > 0 && [
                "roe","roce","roa","net margin","operating margin","gross margin",
                "eps","cfo","fcf","revenue cagr","profit cagr","interest coverage"
              ].some(k => m.label?.toLowerCase().includes(k))
              const isNegativeMetric = !isNaN(numVal) && numVal < 0
              return (
                <div key={i} className="metric-card">
                  <div className="metric-card-label">{m.label}</div>
                  <div className={clsx(
                    "metric-card-value",
                    isNegativeMetric && "negative",
                    !isNegativeMetric && isPositive && "positive"
                  )}>{formattedVal}</div>
                </div>
              )
            })}
          </div>
        </div>
        <div className="mid-right">
          <div className="mid-title">Technicals</div>
          <div className="tech-gauge-wrap">
            <RsiGauge rsi={tech.rsi} />
          </div>
          <div className="tech-badge-grid">
            <div className={clsx("tech-badge", (tech.macdSignal || "").toLowerCase() === "bullish" ? "bullish" : (tech.macdSignal || "").toLowerCase() === "bearish" ? "bearish" : "neutral")}>
              {(tech.macdSignal || "MACD").toUpperCase()}
            </div>
            <div className={clsx("tech-badge", tech.above200Dma ? "bullish" : "bearish")}>
              {tech.above200Dma ? "ABOVE 200DMA" : "BELOW 200DMA"}
            </div>
            <div className="tech-badge neutral">1Y {ret && ret["1Y"] != null ? `${sf(ret["1Y"]) >= 0 ? "+" : ""}${sf(ret["1Y"], 2).toFixed(2)}%` : "—"}</div>
            <div className="tech-badge neutral">3M {ret && ret["3M"] != null ? `${sf(ret["3M"]) >= 0 ? "+" : ""}${sf(ret["3M"], 2).toFixed(2)}%` : "—"}</div>
            <div className="tech-badge neutral">1M {ret && ret["1M"] != null ? `${sf(ret["1M"]) >= 0 ? "+" : ""}${sf(ret["1M"], 2).toFixed(2)}%` : "—"}</div>
            <div className="tech-badge neutral">6M {ret && ret["6M"] != null ? `${sf(ret["6M"]) >= 0 ? "+" : ""}${sf(ret["6M"], 2).toFixed(2)}%` : "—"}</div>
            <div className="tech-badge neutral">52W {tech.from52WeekHighPct != null ? `${sf(tech.from52WeekHighPct) >= 0 ? "+" : ""}${sf(tech.from52WeekHighPct, 2).toFixed(2)}%` : "—"}</div>
            <div className={clsx("tech-badge", (tech.ema_crossover || "").toLowerCase() === "bullish" ? "bullish" : "bearish")}>
              {(tech.ema_crossover || "EMA CROSS").toUpperCase()}
            </div>
          </div>
          <div className="tech-footer">
            <span>50DMA: {fmtVal(tech.sma50)}</span>
            <span>100DMA: {fmtVal(tech.sma100)}</span>
            <span>200DMA: {fmtVal(tech.sma200)}</span>
          </div>
        </div>
      </div>
      </SectionBoundary>

      {/* 6. SECONDARY CHARTS */}
      <SectionBoundary name="Charts">
      <div className="secondary-charts">
        <div className="secondary-left">
          <div className="chart-header" style={{ marginBottom: 8 }}>
            <span className="chart-title">Revenue & Profit</span>
            <div className="chart-toggles">
              <button className={clsx("chart-toggle-btn", chartView === "annual" && "active")} onClick={() => setChartView("annual")}>Annual</button>
              <button className={clsx("chart-toggle-btn", chartView === "quarterly" && "active")} onClick={() => setChartView("quarterly")}>Quarterly</button>
            </div>
          </div>
          <div className="secondary-chart-wrap">
            {revChartData?.labels?.length > 0 && <Bar data={revChartData} options={{ ...chartOpts("INR Cr"), responsive: true, maintainAspectRatio: false }} />}
          </div>
        </div>
        <div className="secondary-right">
          <div className="chart-title" style={{ marginBottom: 8 }}>Margin Trend</div>
          <div className="secondary-chart-wrap">
            {marginChartData?.labels?.length > 0 && <Line data={marginChartData} options={{ ...chartOpts("%"), responsive: true, maintainAspectRatio: false }} />}
          </div>
        </div>
      </div>
      </SectionBoundary>

      {/* 7. FINANCIAL STATEMENTS */}
      <SectionBoundary name="FinancialTables"><FinancialTables statements={data?.statements} /></SectionBoundary>

      {/* 8. FOOTER — Ownership + Peers */}
      <SectionBoundary name="Ownership">
      <div className="footer-section">
        <div className="footer-left">
          <div className="footer-title">Promoter Holding</div>
          {o.promoter != null && (
            <div className="ownership-item">
              <div className="ownership-label"><span>Promoter</span><span>{sf(o.promoter, 1).toFixed(1)}%</span></div>
              <div className="ownership-bar-track"><div className="ownership-bar-fill own-promoter" style={{ width: `${sf(o.promoter)}%` }} /></div>
            </div>
          )}
          {o.fii != null && (
            <div className="ownership-item">
              <div className="ownership-label"><span>FII / FPI</span><span>{sf(o.fii, 1).toFixed(1)}%</span></div>
              <div className="ownership-bar-track"><div className="ownership-bar-fill own-fii" style={{ width: `${sf(o.fii)}%` }} /></div>
            </div>
          )}
          {o.public != null && (
            <div className="ownership-item">
              <div className="ownership-label"><span>Public / Other</span><span>{sf(o.public, 1).toFixed(1)}%</span></div>
              <div className="ownership-bar-track"><div className="ownership-bar-fill own-public" style={{ width: `${sf(o.public)}%` }} /></div>
            </div>
          )}
          {o.dii != null && (
            <div className="ownership-item">
              <div className="ownership-label"><span>DII</span><span>{sf(o.dii, 1).toFixed(1)}%</span></div>
              <div className="ownership-bar-track"><div className="ownership-bar-fill own-public" style={{ width: `${sf(o.dii)}%` }} /></div>
            </div>
          )}
          {!o.promoter && !o.fii && !o.public && (
            <div style={{ color: "var(--text-muted)", fontSize: 12 }}>No ownership data available</div>
          )}
        </div>
        <div className="footer-right">
          <div className="footer-title">Peer Comparison</div>
          <PeerTable peers={peers} currentSymbol={currentSymbol.replace(".NS", "")} />
        </div>
      </div>
      </SectionBoundary>

      <SectionBoundary name="Footer">
      <div className="page-footer">
        Data as of {data?.timestamp || "—"} | Source: Google Sheets + Yahoo Finance
      </div>
      </SectionBoundary>
    </div>
    </div>
  )
}
