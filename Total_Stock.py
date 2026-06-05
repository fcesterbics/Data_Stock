import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone
from scipy.stats import linregress
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyarrow as pa
import pyarrow.parquet as pq
import time
import os

# ─────────────────────────────────────────────
# 1. CONFIG
# ─────────────────────────────────────────────
tickers = pd.read_csv("Tickers.csv")["ticker"].dropna().tolist()

PRICES_FILE     = "Actual_Stock.parquet"
HISTORICAL_FILE = "stock_fundamentals_history.parquet"
TICKERS_FILE    = "Tickers.csv"
MAX_WORKERS     = 10
MAX_RETRIES     = 2
MICROCAP_THRESHOLD = 300_000_000

HISTORICAL_ATTRIBUTES = [
    "shortName", "sector", "industry",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
    "returnOnEquity", "profitMargins", "operatingMargins",
    "revenueGrowth", "earningsGrowth",
    "debtToEquity", "currentRatio", "freeCashflow",
    "ebitda", "totalRevenue", "netIncome", "totalDebt",
    "mostRecentQuarter",
]

ATTRIBUTES = [
    "shortName", "sector", "industry",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
    "returnOnEquity", "profitMargins", "operatingMargins",
    "revenueGrowth", "earningsGrowth",
    "debtToEquity", "currentRatio", "freeCashflow",
    "fiftyDayAverage", "twoHundredDayAverage",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "beta", "marketCap", "dividendYield",
    "mostRecentQuarter"
]

# ─────────────────────────────────────────────
# 2. FUNCIONES PARQUET
# ─────────────────────────────────────────────
def save_parquet_pbi(df_wide, filepath):
    df_long = (
        df_wide.reset_index()
        .melt(id_vars="Date", var_name="Ticker", value_name="Value")
    )
    df_long["Date"]  = pd.to_datetime(df_long["Date"]).dt.strftime("%Y-%m-%d")
    df_long          = df_long.dropna(subset=["Value"])
    df_long["Key"]   = df_long["Date"] + "_" + df_long["Ticker"]
    df_long          = df_long.drop_duplicates(subset=["Key"])
    df_long          = df_long.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    df_long["Value"] = pd.to_numeric(df_long["Value"], errors="coerce").astype("float64")

    schema = pa.schema([
        pa.field("Date",   pa.string()),
        pa.field("Ticker", pa.string()),
        pa.field("Value",  pa.float64()),
        pa.field("Key",    pa.string()),
    ])
    table = pa.Table.from_pandas(df_long, schema=schema, preserve_index=False)
    pq.write_table(table, filepath, compression="gzip",
                   use_deprecated_int96_timestamps=False,
                   write_statistics=True, data_page_version="1.0")
    return df_long

def read_parquet_prices(filepath):
    df = pd.read_parquet(filepath)
    if "Ticker" in df.columns and "Value" in df.columns:
        df_wide              = df.pivot_table(index="Date", columns="Ticker",
                                              values="Value", aggfunc="last")
        df_wide.columns.name = None
        df_wide.index        = pd.to_datetime(df_wide.index)
        df_wide.index.name   = "Date"
        return df_wide.sort_index()
    if "Date" in df.columns:
        df.index = pd.to_datetime(df["Date"])
        df       = df.drop(columns=["Date"])
    else:
        df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df.sort_index()

# ─────────────────────────────────────────────
# 3. PRECIOS (últimos 6 meses)
# ─────────────────────────────────────────────
print("📥 Descargando precios...")
prices = yf.download(tickers, period="6mo", progress=False)["Close"]
if isinstance(prices, pd.Series):
    prices = prices.to_frame(name=tickers[0])
last_price = prices.iloc[-1]
print(f"   ✅ {len(prices)} fechas | {prices.shape[1]} tickers")

# ─────────────────────────────────────────────
# 4. FUNDAMENTALES — DESCARGA PARALELA CON RETRY
# ─────────────────────────────────────────────
def fetch_ticker_info(t, retries=MAX_RETRIES):
    for attempt in range(retries + 1):
        try:
            info = yf.Ticker(t).info
            if info and (info.get("regularMarketPrice") is not None
                         or info.get("trailingPE") is not None):
                return t, info, None
            return t, info, "empty_response"
        except Exception as e:
            if attempt < retries:
                time.sleep(1 * (attempt + 1))
                continue
            return t, None, str(e)

print(f"\n🔄 Descargando fundamentales ({len(tickers)} tickers, {MAX_WORKERS} hilos)...")

data          = {}
new_hist_rows = []
failed        = []
fetch_date    = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

if os.path.exists(HISTORICAL_FILE):
    df_hist       = pd.read_parquet(HISTORICAL_FILE)
    existing_keys = set(zip(df_hist["ticker"], df_hist["report_date"]))
else:
    df_hist       = pd.DataFrame()
    existing_keys = set()

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(fetch_ticker_info, t): t for t in tickers}
    for i, future in enumerate(as_completed(futures), 1):
        t, info, error = future.result()

        if error or info is None:
            failed.append(t)
            continue

        data[t] = {a: info.get(a) for a in ATTRIBUTES}

        report_ts = info.get("mostRecentQuarter")
        if report_ts:
            report_date = datetime.fromtimestamp(report_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if (t, report_date) not in existing_keys:
                row = {"ticker": t, "report_date": report_date, "fetch_date": fetch_date}
                for attr in HISTORICAL_ATTRIBUTES:
                    if attr != "mostRecentQuarter":
                        row[attr] = info.get(attr)
                new_hist_rows.append(row)
                existing_keys.add((t, report_date))

        if i % 50 == 0:
            print(f"   {i}/{len(tickers)} tickers procesados...")

print(f"   ✅ {len(data)} OK | ⚠  {len(failed)} fallidos")

# ─────────────────────────────────────────────
# 5. ELIMINAR TICKERS FALLIDOS DE Tickers.csv
# ─────────────────────────────────────────────
if failed:
    print(f"\n🗑  Eliminando {len(failed)} tickers fallidos de {TICKERS_FILE}...")
    print(f"   Eliminados: {failed}")
    df_tickers_original = pd.read_csv(TICKERS_FILE)
    df_tickers_clean    = df_tickers_original[
        ~df_tickers_original["ticker"].isin(failed)
    ]
    df_tickers_clean.to_csv(TICKERS_FILE, index=False)
    print(f"   ✅ {TICKERS_FILE} actualizado: "
          f"{len(df_tickers_original)} → {len(df_tickers_clean)} tickers")

# ─────────────────────────────────────────────
# 6. GUARDAR HISTÓRICO DE FUNDAMENTALES
# ─────────────────────────────────────────────
if new_hist_rows:
    df_new = pd.DataFrame(new_hist_rows)
    if df_hist.empty:
        df_updated = df_new
    else:
        df_updated = pd.concat([df_hist, df_new], ignore_index=True)
    df_updated = df_updated.sort_values(["ticker", "report_date"]).reset_index(drop=True)
    df_updated.to_parquet(HISTORICAL_FILE, index=False)
    print(f"\n📚 Histórico actualizado: +{len(new_hist_rows)} registros | "
          f"{df_updated['ticker'].nunique()} tickers | "
          f"{len(df_updated)} filas totales")
else:
    print("\n✅ Histórico sin cambios — no hubo nuevos reportes trimestrales.")

# ─────────────────────────────────────────────
# 7. DATAFRAME SCREENER — CONVERSIÓN NUMÉRICA EXPLÍCITA
# ─────────────────────────────────────────────
df = pd.DataFrame.from_dict(data, orient="index").reset_index()
df.rename(columns={"index": "ticker"}, inplace=True)

# Columnas que deben ser string
STR_COLS = ["ticker", "shortName", "sector", "industry"]

# Forzar conversión numérica en todas las demás columnas
for col in df.columns:
    if col not in STR_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ─────────────────────────────────────────────
# 8. FEATURES DE PRECIO Y TÉCNICOS
# ─────────────────────────────────────────────
df["lastPrice"]      = pd.to_numeric(df["ticker"].map(last_price), errors="coerce")
df["priceVs50dMA"]   = df["lastPrice"] / df["fiftyDayAverage"]      - 1
df["priceVs200dMA"]  = df["lastPrice"] / df["twoHundredDayAverage"] - 1
df["priceVs52wHigh"] = df["lastPrice"] / df["fiftyTwoWeekHigh"]     - 1
df["priceVs52wLow"]  = df["lastPrice"] / df["fiftyTwoWeekLow"]      - 1
df["position52w"]    = (
    (df["lastPrice"] - df["fiftyTwoWeekLow"]) /
    (df["fiftyTwoWeekHigh"] - df["fiftyTwoWeekLow"])
).clip(0, 1)

# ─────────────────────────────────────────────
# 9. FILTRO DE LIQUIDEZ POR MARKET CAP
# ─────────────────────────────────────────────
df["liquidity_flag"] = df["marketCap"] < MICROCAP_THRESHOLD
n_microcap           = df["liquidity_flag"].sum()
if n_microcap > 0:
    print(f"\n⚠  {n_microcap} microcaps detectados (< $300M) — penalización aplicada.")

# ─────────────────────────────────────────────
# 10. KPIs HISTÓRICOS AMPLIADOS
# ─────────────────────────────────────────────
def compute_full_stats(values, periods_per_year=4):
    """
    Calcula estadísticas completas para una serie fundamental trimestral.

    Retorna:
      trend       — pendiente normalizada por la media (% por trimestre)
      r2          — R² de la regresión (0-1, calidad/predictibilidad del trend)
      cagr        — tasa de crecimiento anualizada compuesta
      last_qoq    — último cambio trimestral (%)
      acceleration — si el crecimiento se está acelerando (2ª mitad vs 1ª mitad)
    """
    values = values.dropna().reset_index(drop=True)
    n      = len(values)

    out = dict(trend=np.nan, r2=np.nan, cagr=np.nan,
               last_qoq=np.nan, acceleration=np.nan)

    if n < 2:
        return out

    # Último cambio QoQ
    v_prev = values.iloc[-2]
    v_last = values.iloc[-1]
    if v_prev != 0 and not np.isnan(v_prev):
        out["last_qoq"] = (v_last - v_prev) / abs(v_prev)

    if n < 3:
        return out

    x                               = np.arange(n)
    slope, _, r_val, _, _           = linregress(x, values)
    mean_val                        = values.abs().mean()
    out["r2"]                       = r_val ** 2
    if mean_val != 0:
        out["trend"] = slope / mean_val

    # CAGR
    v_first = values.iloc[0]
    years   = (n - 1) / periods_per_year
    if v_first > 0 and v_last > 0 and years > 0:
        out["cagr"] = (v_last / v_first) ** (1 / years) - 1

    # Aceleración: pendiente 2ª mitad vs 1ª mitad
    if n >= 6:
        mid    = n // 2
        s1, *_ = linregress(np.arange(mid),       values.iloc[:mid])
        s2, *_ = linregress(np.arange(n - mid),   values.iloc[mid:])
        if mean_val != 0:
            out["acceleration"] = (s2 - s1) / abs(mean_val)

    return out

def compute_consistency(values):
    """Estabilidad de resultados: inverso del coeficiente de variación."""
    values = values.dropna()
    if len(values) < 3:
        return np.nan
    mean_val = values.mean()
    std_val  = values.std()
    if mean_val == 0 or np.isnan(mean_val):
        return np.nan
    return 1 / (1 + std_val / abs(mean_val))

# Métricas históricas a analizar: (columna_parquet, prefijo_kpi)
HIST_METRICS = [
    ("totalRevenue",     "revenue"),
    ("ebitda",           "ebitda"),
    ("operatingMargins", "margin"),
    ("totalDebt",        "debt"),
    ("freeCashflow",     "fcf"),
    ("netIncome",        "earnings"),
    ("returnOnEquity",   "roe"),
]

# KPIs generados automáticamente por cada métrica:
# {prefix}_trend | {prefix}_r2 | {prefix}_cagr | {prefix}_qoq | {prefix}_accel
# + earnings_consistency (solo para netIncome)

all_trend_kpis = []
for _, prefix in HIST_METRICS:
    for suffix in ["trend", "r2", "cagr", "qoq", "accel"]:
        all_trend_kpis.append(f"{prefix}_{suffix}")
all_trend_kpis.append("earnings_consistency")

if os.path.exists(HISTORICAL_FILE):
    df_fund_hist = pd.read_parquet(HISTORICAL_FILE)
    df_fund_hist["report_date"] = pd.to_datetime(df_fund_hist["report_date"])
    df_fund_hist = df_fund_hist.sort_values(["ticker", "report_date"])
    df_fund_hist = df_fund_hist.groupby("ticker").tail(8)   # últimos 8 trimestres

    trend_results = {}
    for ticker, group in df_fund_hist.groupby("ticker"):
        row = {}
        for col, prefix in HIST_METRICS:
            if col not in group.columns:
                for suffix in ["trend", "r2", "cagr", "qoq", "accel"]:
                    row[f"{prefix}_{suffix}"] = np.nan
                continue
            stats = compute_full_stats(group[col])
            row[f"{prefix}_trend"] = stats["trend"]
            row[f"{prefix}_r2"]    = stats["r2"]
            row[f"{prefix}_cagr"]  = stats["cagr"]
            row[f"{prefix}_qoq"]   = stats["last_qoq"]
            row[f"{prefix}_accel"] = stats["acceleration"]

        row["earnings_consistency"] = compute_consistency(
            group["netIncome"] if "netIncome" in group.columns
            else pd.Series(dtype=float)
        )
        trend_results[ticker] = row

    df_trends = pd.DataFrame.from_dict(trend_results, orient="index").reset_index()
    df_trends.rename(columns={"index": "ticker"}, inplace=True)

    # Conversión numérica explícita
    for col in df_trends.columns:
        if col != "ticker":
            df_trends[col] = pd.to_numeric(df_trends[col], errors="coerce")

    df       = df.merge(df_trends, on="ticker", how="left")
    n_hist   = df_trends.drop(columns="ticker").notna().any(axis=1).sum()
    print(f"\n📈 KPIs históricos calculados para {n_hist} tickers "
          f"({len(HIST_METRICS) * 5 + 1} KPIs por ticker).")
else:
    for kpi in all_trend_kpis:
        df[kpi] = np.nan
    print("\n⚠  Sin histórico aún — KPIs de evolución en NaN.")

# ─────────────────────────────────────────────
# 11. WINSORIZATION + IMPUTACIÓN
# ─────────────────────────────────────────────
def winsorize(s):
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() < 10:
        return s
    return s.clip(s.quantile(0.05), s.quantile(0.95))

def impute(df, col):
    s = pd.to_numeric(df[col], errors="coerce").copy()
    industry_med = df.groupby("industry")[col].transform(
        lambda x: pd.to_numeric(x, errors="coerce").median()
        if pd.to_numeric(x, errors="coerce").notna().sum() >= 3 else np.nan
    )
    sector_med = df.groupby("sector")[col].transform(
        lambda x: pd.to_numeric(x, errors="coerce").median()
        if pd.to_numeric(x, errors="coerce").notna().sum() >= 3 else np.nan
    )
    global_med = s.median()
    s = s.fillna(industry_med).fillna(sector_med).fillna(global_med)
    return pd.to_numeric(s, errors="coerce")

# ─────────────────────────────────────────────
# 12. SCORING CONFIG
# ─────────────────────────────────────────────
#
#  Cada categoría: { métrica: (inverse, peso_interno), "weight": peso_global }
#  inverse=True  → menor valor es mejor
#  inverse=False → mayor valor es mejor
#  Suma de weights = 1.00 ✅
#
CONFIG = {
    "valuation": {
        "trailingPE":         (True,  0.25),
        "forwardPE":          (True,  0.25),
        "priceToBook":        (True,  0.25),
        "enterpriseToEbitda": (True,  0.25),
        "weight": 0.16
    },
    "profitability": {
        "returnOnEquity":   (False, 0.4),
        "profitMargins":    (False, 0.3),
        "operatingMargins": (False, 0.3),
        "weight": 0.16
    },
    "growth": {
        "revenueGrowth":  (False, 0.5),
        "earningsGrowth": (False, 0.5),
        "weight": 0.12
    },
    "financial": {
        "debtToEquity": (True,  0.5),
        "currentRatio": (False, 0.5),
        "weight": 0.12
    },
    "momentum": {
        "priceVs50dMA":   (False, 0.30),
        "priceVs200dMA":  (False, 0.30),
        "priceVs52wHigh": (False, 0.20),
        "position52w":    (False, 0.20),
        "weight": 0.14
    },
    "fundamental_momentum": {
        # Tendencias (qué dirección)
        "revenue_trend":  (False, 0.15),
        "ebitda_trend":   (False, 0.15),
        "margin_trend":   (False, 0.10),
        "debt_trend":     (True,  0.10),
        "fcf_trend":      (False, 0.08),
        "roe_trend":      (False, 0.07),
        # Calidad del trend (qué tan predecible)
        "revenue_r2":     (False, 0.08),
        "ebitda_r2":      (False, 0.07),
        # Crecimiento estructural
        "revenue_cagr":   (False, 0.08),
        "ebitda_cagr":    (False, 0.05),
        # Aceleración reciente
        "revenue_accel":  (False, 0.04),
        "margin_accel":   (False, 0.03),
        # Estabilidad
        "earnings_consistency": (False, 0.00),  # en penalización, no scoring
        "weight": 0.24
    },
    "income": {
        "dividendYield": (False, 1.00),
        "weight": 0.06
    }
}
# 0.16+0.16+0.12+0.12+0.14+0.24+0.06 = 1.00 ✅

# ─────────────────────────────────────────────
# 13. SCORING POR SECTOR
# ─────────────────────────────────────────────
def score(series, inverse):
    series = pd.to_numeric(series, errors="coerce")
    series = winsorize(series)
    r      = series.rank(pct=True, na_option="keep")
    if inverse:
        r = 1 - r
    return (r * 10).clip(0, 10)

all_metrics = []

for cat, cfg in CONFIG.items():
    cat_score = pd.Series(0.0, index=df.index)
    total_w   = 0.0

    for k, v in cfg.items():
        if k == "weight":
            continue
        inverse, w = v
        if k not in df.columns:
            continue

        # Imputar y asegurar tipo numérico
        df[k] = impute(df, k)

        # Score relativo dentro del sector
        s = df.groupby("sector")[k].transform(lambda x: score(x, inverse))
        s = pd.to_numeric(s, errors="coerce")

        df[f"score_{k}"] = s
        cat_score        = cat_score.add(s * w, fill_value=0)
        total_w         += w

        if k not in all_metrics:
            all_metrics.append(k)

    df[f"score_{cat}"] = (
        pd.to_numeric(cat_score, errors="coerce") / total_w
        if total_w > 0 else np.nan
    )

# ─────────────────────────────────────────────
# 14. SCORE FINAL
# ─────────────────────────────────────────────
cat_scores   = []
total_weight = 0.0

for cat, cfg in CONFIG.items():
    col = f"score_{cat}"
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        cat_scores.append(s * cfg["weight"])
        total_weight += cfg["weight"]

df["score_FINAL"] = pd.to_numeric(
    sum(cat_scores) / total_weight, errors="coerce"
)

# ─────────────────────────────────────────────
# 15. PENALIZACIÓN POR DATOS FALTANTES + MICROCAP
# ─────────────────────────────────────────────
valid        = df[all_metrics].apply(pd.to_numeric, errors="coerce").notna().sum(axis=1)
completeness = valid / len(all_metrics)
penalty      = completeness.clip(lower=0.3)

df["data_completeness"]  = (completeness * 100).round(1)   # % para el reporte
df["score_FINAL_adj"]    = pd.to_numeric(
    df["score_FINAL"] * (0.7 + 0.3 * penalty), errors="coerce"
)

# Penalización adicional microcaps
df.loc[df["liquidity_flag"], "score_FINAL_adj"] = (
    df.loc[df["liquidity_flag"], "score_FINAL_adj"] * 0.85
)

# ─────────────────────────────────────────────
# 16. RANKING + LABEL
# ─────────────────────────────────────────────
df["rank"] = df["score_FINAL_adj"].rank(ascending=False, method="min").astype(int)

def label(x):
    if pd.isna(x):    return "Sin datos"
    if x >= 8:        return "Excelente"
    if x >= 6.5:      return "Buena"
    if x >= 5:        return "Neutral"
    if x >= 3:        return "Débil"
    return "Evitar"

df["rating"] = df["score_FINAL_adj"].apply(label)

# ─────────────────────────────────────────────
# 17. OUTPUT SCREENER DIARIO
# ─────────────────────────────────────────────
df.drop(columns=["mostRecentQuarter"], inplace=True, errors="ignore")

output_cols = [
    "ticker", "shortName", "sector", "industry",
    "rank", "score_FINAL_adj", "rating", "data_completeness",
    "score_valuation", "score_profitability", "score_growth",
    "score_financial", "score_momentum", "score_fundamental_momentum", "score_income",
    "revenue_trend", "ebitda_trend", "margin_trend",
    "debt_trend", "fcf_trend", "earnings_consistency",
    "revenue_r2", "ebitda_r2", "revenue_cagr", "ebitda_cagr",
    "revenue_qoq", "ebitda_qoq", "revenue_accel", "margin_accel",
    "lastPrice", "priceVs50dMA", "priceVs200dMA",
    "priceVs52wHigh", "priceVs52wLow", "position52w",
    "beta", "marketCap", "dividendYield", "liquidity_flag",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
    "returnOnEquity", "profitMargins", "operatingMargins",
    "revenueGrowth", "earningsGrowth",
    "debtToEquity", "currentRatio", "freeCashflow",
]

output_cols = [c for c in output_cols if c in df.columns]

# Snapshot actual (sobreescribe) — para PBI "estado de hoy"
df[output_cols].to_csv("Stock_Screener_PRO.csv", index=False)
print("✅ Stock_Screener_PRO.csv actualizado.")

# ─────────────────────────────────────────────
# 17B. HISTÓRICO DEL SCREENER — append con fecha
# ─────────────────────────────────────────────
SCREENER_HISTORY_FILE = "Stock_Screener_History.parquet"

df_snapshot                = df[output_cols].copy()
df_snapshot["snapshot_date"] = fetch_date

if os.path.exists(SCREENER_HISTORY_FILE):
    df_hist_screener = pd.read_parquet(SCREENER_HISTORY_FILE)

    # Si ya existe un snapshot de hoy, lo reemplaza
    df_hist_screener = df_hist_screener[
        df_hist_screener["snapshot_date"] != fetch_date
    ]
    df_hist_screener = pd.concat(
        [df_hist_screener, df_snapshot], ignore_index=True
    )
else:
    df_hist_screener = df_snapshot

df_hist_screener = df_hist_screener.sort_values(
    ["snapshot_date", "rank"]
).reset_index(drop=True)

df_hist_screener.to_parquet(SCREENER_HISTORY_FILE, index=False)

n_fechas = df_hist_screener["snapshot_date"].nunique()
print(f"📅 Stock_Screener_History.parquet actualizado: "
      f"{n_fechas} días | "
      f"{df_hist_screener['snapshot_date'].min()} → "
      f"{df_hist_screener['snapshot_date'].max()}")

# ─────────────────────────────────────────────
# 18. APPEND DIARIO → Actual_Stock.parquet
# ─────────────────────────────────────────────
if os.path.exists(PRICES_FILE):
    df_existente = read_parquet_prices(PRICES_FILE)
    start_date   = df_existente.index.min().strftime("%Y-%m-%d")

    # Tickers nuevos → descargar histórico completo automáticamente
    new_tickers = [t for t in tickers if t not in df_existente.columns]

    if new_tickers:
        print(f"\n🆕 {len(new_tickers)} tickers nuevos detectados: {new_tickers}")
        print(f"   Descargando histórico completo desde {start_date}...")
        try:
            prices_new = yf.download(new_tickers, start=start_date, progress=False)["Close"]
            if isinstance(prices_new, pd.Series):
                prices_new = prices_new.to_frame(name=new_tickers[0])

            todas_cols   = df_existente.columns.union(prices_new.columns)
            df_existente = df_existente.reindex(columns=todas_cols)

            fechas_solo_new = prices_new.index.difference(df_existente.index)
            if len(fechas_solo_new) > 0:
                df_existente = pd.concat([
                    df_existente,
                    prices_new.loc[fechas_solo_new].reindex(columns=todas_cols)
                ]).sort_index()

            fechas_overlap = prices_new.index.intersection(df_existente.index)
            for col in prices_new.columns:
                df_existente.loc[fechas_overlap, col] = (
                    prices_new.loc[fechas_overlap, col].values
                )
            print(f"   ✅ Histórico incorporado para {len(new_tickers)} tickers nuevos.")

        except Exception as e:
            print(f"   ⚠  Error descargando histórico de nuevos tickers: {e}")

    # Fechas nuevas (6 meses) para todos los tickers
    todas_cols    = df_existente.columns.union(prices.columns)
    df_existente  = df_existente.reindex(columns=todas_cols)
    fechas_nuevas = prices.index.difference(df_existente.index)

    if len(fechas_nuevas) > 0:
        df_nuevas = prices.loc[fechas_nuevas].reindex(columns=todas_cols)
        df_final  = pd.concat([df_existente, df_nuevas]).sort_index()
        print(f"\n📈 {len(fechas_nuevas)} fechas nuevas agregadas.")
    else:
        df_final = df_existente
        print("\n✅ Sin fechas nuevas — parquet ya al día.")

    df_long = save_parquet_pbi(df_final, PRICES_FILE)

else:
    df_long = save_parquet_pbi(prices, PRICES_FILE)
    print(f"\n📊 Parquet creado desde cero: {len(prices)} filas.")

print(f"💾 Parquet guardado: {len(df_long):,} filas | "
      f"{df_long['Ticker'].nunique()} tickers | "
      f"{df_long['Date'].min()} → {df_long['Date'].max()}")

# ─────────────────────────────────────────────
# 19. RESUMEN CONSOLA
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("🏆 TOP 15 — RANKING FINAL")
print("="*60)
top15 = df.sort_values("rank")[
    ["rank", "ticker", "shortName", "score_FINAL_adj",
     "rating", "data_completeness",
     "score_valuation", "score_profitability",
     "score_momentum", "score_fundamental_momentum"]
].head(15)
print(top15.to_string(index=False))

print(f"\n📊 Distribución de ratings:")
print(df["rating"].value_counts().to_string())

print(f"\n📐 Completeness promedio de datos: "
      f"{df['data_completeness'].mean():.1f}%")
