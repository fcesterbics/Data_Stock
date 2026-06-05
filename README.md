# 📈 Stock Screener PRO — Automated Financial Intelligence System

## About This Project

This repository contains a fully automated Python-based system for collecting,
processing, scoring, and historizing financial data on stocks tracked via a
custom ticker list. The system runs daily via GitHub Actions and produces
ready-to-use datasets for Power BI reporting.

The core output is a **quantitative ranking of assets** based on 7 analytical
dimensions: valuation, profitability, growth, financial health, price momentum,
fundamental momentum (historical trend analysis), and income.

---

## 📁 Repository Contents

### Input Files

| File | Description |
|---|---|
| `Tickers.csv` | Master list of ticker symbols used as input. Automatically cleaned: tickers that consistently fail data retrieval are removed on each run. |

### Output Files

| File | Description |
|---|---|
| `Stock_Screener_PRO.csv` | Daily snapshot of all tickers with scores, rankings, ratings, and 35+ fundamental KPIs. Overwritten on each run. |
| `Actual_Stock.parquet` | Long-format historical price database (Date · Ticker · Value · Key). Append-only: new dates are added daily, never overwritten. Power BI compatible. |
| `stock_fundamentals_history.parquet` | Quarterly fundamental history per ticker (EBITDA, Revenue, Margins, Debt, FCF, etc.). Append-only: new entries added only when a new earnings report is detected via `mostRecentQuarter`. |

### Scripts

| File | Description |
|---|---|
| `Total_Stock.py` | Main daily script. See full description below. |

---

## 🧠 How Total_Stock.py Works

The script executes the following pipeline on every run:

### 1 · Price Download
Downloads the last 6 months of daily Close Prices for all tickers via
`yfinance`. Used for momentum features and to append new trading days to
`Actual_Stock.parquet`.

### 2 · Parallel Fundamentals Download
Fetches financial fundamentals for all tickers simultaneously using
`ThreadPoolExecutor` (10 parallel threads). Each ticker is retried up to
2 times with exponential backoff before being marked as failed.

**Tickers that fail after all retries are automatically removed from
`Tickers.csv`** to keep the dataset clean and consistent.

Attributes retrieved per ticker include:
- Valuation: `trailingPE`, `forwardPE`, `priceToBook`, `enterpriseToEbitda`
- Profitability: `returnOnEquity`, `profitMargins`, `operatingMargins`
- Growth: `revenueGrowth`, `earningsGrowth`
- Financial health: `debtToEquity`, `currentRatio`, `freeCashflow`
- Technical: `fiftyDayAverage`, `twoHundredDayAverage`, `fiftyTwoWeekHigh/Low`
- Other: `beta`, `marketCap`, `dividendYield`

### 3 · Fundamental History (Quarterly Append)
For each ticker, the script checks the `mostRecentQuarter` timestamp from
yfinance. If a new quarter is detected that is not yet in
`stock_fundamentals_history.parquet`, a new row is appended with the full
set of fundamental values at that point in time.

This builds an **auditable quarterly fundamental history** for every ticker,
enabling trend analysis across earnings cycles (~4 updates/year per ticker).

### 4 · Historical KPI Computation (35+ KPIs)
For each of 7 fundamental metrics (Revenue, EBITDA, Operating Margins,
Total Debt, Free Cash Flow, Net Income, Return on Equity), the script
computes 5 statistical indicators using the last 8 quarters of history:

| Suffix | Description |
|---|---|
| `_trend` | Normalized regression slope (% change per quarter) |
| `_r2` | R² of the regression — how predictable/consistent the trend is (0–1) |
| `_cagr` | Compound Annual Growth Rate (annualized) |
| `_qoq` | Last quarter-over-quarter percentage change |
| `_accel` | Acceleration — whether growth is speeding up (2nd half vs 1st half slope) |

Plus `earnings_consistency` (inverse coefficient of variation of net income).

These KPIs are used both in the scoring model and exported to the CSV for
use in Power BI reports.

### 5 · Scoring Model (7 Categories)
Each ticker receives a composite score from 0 to 10, built from 7 weighted
categories scored relative to sector peers (percentile ranking):

| Category | Weight | Key Metrics |
|---|---|---|
| Valuation | 16% | PE, PB, EV/EBITDA |
| Profitability | 16% | ROE, Net Margin, Operating Margin |
| Growth | 12% | Revenue Growth, Earnings Growth |
| Financial Health | 12% | Debt/Equity, Current Ratio |
| Price Momentum | 14% | vs 50/200d MA, 52-week position |
| Fundamental Momentum | 24% | Historical trends, R², CAGR, acceleration |
| Income | 6% | Dividend Yield |

**Design principles:**
- All scoring is done within sector groups (apples-to-apples comparison)
- Winsorization (5th–95th percentile) removes outlier distortion
- Hierarchical imputation (industry → sector → global median) handles missing data
- A completeness penalty reduces scores for tickers with insufficient data
- Microcaps (market cap < $300M) receive an additional 15% penalty

### 6 · Ranking & Rating
Tickers are ranked globally by `score_FINAL_adj` and assigned a qualitative
rating:

| Score | Rating |
|---|---|
| ≥ 8.0 | Excelente |
| ≥ 6.5 | Buena |
| ≥ 5.0 | Neutral |
| ≥ 3.0 | Débil |
| < 3.0 | Evitar |

### 7 · Price History Management
`Actual_Stock.parquet` is maintained as a long-format table optimized for
Power BI:

| Column | Description |
|---|---|
| `Date` | Trading date (YYYY-MM-DD string) |
| `Ticker` | Asset symbol |
| `Value` | Adjusted close price |
| `Key` | `Date_Ticker` — unique row identifier, prevents duplicates |

**New tickers in `Tickers.csv` are automatically backfilled**: when a ticker
is detected that is not yet in the parquet, the script downloads its full
available price history (from the earliest date in the existing database)
before appending new data.

The file is saved with Power BI-compatible settings: gzip compression,
Parquet data page version 1.0, explicit float64 types.

---

## ⚙ Automation with GitHub Actions

### Steps

1. Check out the repository
2. Set up Python 3.12
3. Install dependencies: `yfinance pandas numpy scipy pyarrow`
4. Execute `Total_Stock.py`
5. Commit and push all updated files to the repository

---

## 📊 Power BI Integration

`Actual_Stock.parquet` and `Stock_Screener_PRO.csv` are consumed directly
in Power BI via web URL (GitHub raw).

**Recommended M query for Parquet files:**


```m

let
    Url    = "https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/Actual_Stock.parquet",
    Binary = Binary.Buffer(Web.Contents(Url)),
    Result = Parquet.Document(Binary)
in
    Result

yfinance
pandas
numpy
scipy
pyarrow

Tickers.csv  ──────────────────────────────────────────────────┐
                                                               │
              ┌── yfinance (6mo prices) ──────────────────────▶│
              │                                                 │
              └── yfinance (fundamentals, parallel) ──────────▶│
                         │                                      │
                         ▼                                      ▼
          stock_fundamentals_history.parquet      Actual_Stock.parquet
          (append-only, quarterly)                (append-only, daily)
                         │                                      │
                         ▼                                      │
              Historical KPI Engine                             │
              (trend · r² · cagr · qoq · accel)                │
                         │                                      │
                         ▼                                      │
              Scoring Model (7 categories)                      │
                         │                                      │
                         ▼                                      │
              Stock_Screener_PRO.csv ◀──────────────────────────┘
              (overwrite daily)

                         │
                         ▼
                    Power BI Report

```

The workflow runs automatically every day at **16:00 UTC** and can also be
triggered manually.
```
