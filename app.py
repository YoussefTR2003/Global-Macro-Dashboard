import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import plotly.express as px
import requests
import tradingeconomics as te
from newsapi import NewsApiClient
import plotly.express as px


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Macro Pulse Dashboard",
    layout="wide"
)

st.title("Macro Pulse Dashboard")
st.caption("Macro data, major equity indices, key stocks, and important market/geopolitical news")


# =========================================================
# API CONFIG
# =========================================================

fred = Fred(api_key=st.secrets["FRED_API_KEY"])
newsapi = NewsApiClient(api_key=st.secrets["NEWSAPI_KEY"])


# =========================================================
# SIDEBAR
# =========================================================

@st.cache_data(ttl=3600)
def get_fred_release_calendar():
    api_key = st.secrets["FRED_API_KEY"]

    releases_url = "https://api.stlouisfed.org/fred/releases"
    dates_url = "https://api.stlouisfed.org/fred/releases/dates"

    base_params = {
        "api_key": api_key,
        "file_type": "json"
    }

    try:
        releases_resp = requests.get(releases_url, params=base_params, timeout=10)
        dates_resp = requests.get(
            dates_url,
            params={**base_params, "include_release_dates_with_no_data": "false"},
            timeout=10
        )

        releases_data = releases_resp.json().get("releases", [])
        dates_data = dates_resp.json().get("release_dates", [])

        releases_df = pd.DataFrame(releases_data)
        dates_df = pd.DataFrame(dates_data)

        if releases_df.empty or dates_df.empty:
            return pd.DataFrame()

        releases_df = releases_df[["id", "name"]].rename(columns={"id": "release_id"})
        dates_df["release_id"] = pd.to_numeric(dates_df["release_id"], errors="coerce")

        calendar_df = dates_df.merge(releases_df, on="release_id", how="left")
        calendar_df["date"] = pd.to_datetime(calendar_df["date"], errors="coerce")

        return calendar_df.sort_values("date")

    except Exception:
        return pd.DataFrame()


st.sidebar.header("Dashboard Settings")

st.sidebar.image("assets/Image.jpg", width=120)
st.sidebar.markdown("**Youssef Triki**")
st.sidebar.caption("EDHEC Business School — MSc Finance")

st.sidebar.subheader("Upcoming Economic Releases")

calendar_df = get_fred_release_calendar()

if not calendar_df.empty:
    today = pd.Timestamp.today().normalize()

    next_releases = (
        calendar_df[calendar_df["date"] >= today]
        .dropna(subset=["name"])
        .sort_values("date")
        .head(5)
    )

    if not next_releases.empty:
        for _, row in next_releases.iterrows():
            st.sidebar.write(f"• {row['date'].date()} — {row['name']}")
    else:
        st.sidebar.caption("No upcoming releases found.")
else:
    st.sidebar.caption("Calendar unavailable.")

macro_start_date = st.sidebar.date_input(
    "Macro start date",
    value=pd.to_datetime("2018-01-01")
)

selected_macro = st.sidebar.selectbox(
    "Select macro indicator",
    [
        "Inflation YoY",
        "Inflation MoM",
        "Unemployment Rate",
        "Fed Funds Rate",
        "US 10Y Yield"
    ]
)

show_tables = st.sidebar.checkbox("Show detailed tables", value=True)


# =========================================================
# DATA FUNCTIONS
# =========================================================
@st.cache_data(ttl=1800)
def get_fx_correlation_matrix(fx_tickers, period="6mo"):

    prices = pd.DataFrame()

    for name, ticker in fx_tickers.items():

        data = yf.download(
            ticker,
            period=period,
            interval="1d",
            progress=False
        )

        if not data.empty:
            prices[name] = data["Close"]

    if prices.shape[1] < 2:
        return pd.DataFrame()

    returns = prices.pct_change().dropna()

    return returns.corr()
@st.cache_data(ttl=3600)
def get_macro_data():
    cpi = fred.get_series("CPIAUCSL").to_frame("CPI")
    unrate = fred.get_series("UNRATE").to_frame("Unemployment Rate")
    fedfunds = fred.get_series("FEDFUNDS").to_frame("Fed Funds Rate")
    dgs10 = fred.get_series("DGS10").to_frame("US 10Y Yield")

    dgs10 = dgs10.resample("MS").mean()

    macro = pd.concat([cpi, unrate, fedfunds, dgs10], axis=1)

    macro["Inflation YoY"] = macro["CPI"].pct_change(12) * 100
    macro["Inflation MoM"] = macro["CPI"].pct_change(1) * 100

    macro = macro.sort_index()

    return macro


@st.cache_data(ttl=1800)
def get_market_snapshot(tickers_dict):
    rows = []

    for label, ticker in tickers_dict.items():
        try:
            hist = yf.download(
                ticker,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False
            )

            if hist.empty or len(hist) < 2:
                continue

            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            change = ((last_close / prev_close) - 1) * 100

            rows.append({
                "Name": label,
                "Last": round(last_close, 2),
                "Daily Change %": round(change, 2)
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Daily Change %", ascending=False).reset_index(drop=True)

    return df


@st.cache_data(ttl=1800)
def get_major_10y_yields_fred():
    series_map = {
        "US 10Y": "IRLTLT01USM156N",
        "Germany 10Y": "IRLTLT01DEM156N",
        "France 10Y": "IRLTLT01FRM156N",
        "Italy 10Y": "IRLTLT01ITM156N",
        "UK 10Y": "IRLTLT01GBM156N",
        "Japan 10Y": "IRLTLT01JPM156N",
        "Canada 10Y": "IRLTLT01CAM156N",
        "Spain": "IRLTLT01ESM156N",
    }

    rows = []

    for label, series_id in series_map.items():
        try:
            s = fred.get_series(series_id).dropna()
            if len(s) == 0:
                continue

            last_val = float(s.iloc[-1])
            prev_val = float(s.iloc[-2]) if len(s) >= 2 else None

            rows.append({
                "Name": label,
                "Yield": round(last_val, 3),
                "Delta": round(last_val - prev_val, 3) if prev_val is not None else None
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def display_market_metrics(df, n_cols=4, is_yield=False):
    if df.empty:
        st.warning("No data available.")
        return

    cols = st.columns(n_cols)

    for i, row in df.iterrows():
        value = row["Last"]

        if isinstance(value, (int, float)):
            if is_yield:
                value = f"{value:.3f}%"
            else:
                value = f"{value:.2f}"

        delta = row.get("Daily Change %", None)
        delta_text = None if pd.isna(delta) else f"{delta}%"

        cols[i % n_cols].metric(
            label=row["Name"],
            value=value,
            delta=delta_text
        )


def get_market_news():
    try:
        response = newsapi.get_top_headlines(
            category="business",
            language="en",
            page_size=10
        )
        return response.get("articles", [])
    except Exception:
        return []


def display_news(articles):
    if not articles:
        st.warning("No news retrieved.")
        return

    for article in articles:
        title = article.get("title", "No title")
        url = article.get("url", "#")
        source = article.get("source", {}).get("name", "")
        date = article.get("publishedAt", "")

        st.markdown(f"• **[{title}]({url})**  \n{source} — {date}")


# =========================================================
# TICKERS
# =========================================================

us_indices = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    "VIX": "^VIX"

}
eu_indices = {
    "Euro Stoxx 50": "^STOXX50E",
    "STOXX Europe 600": "^STOXX",
    "CAC 40": "^FCHI",
    "DAX": "^GDAXI",
    "FTSE 100": "^FTSE",
    "IBEX 35": "^IBEX",
    "FTSE MIB": "FTSEMIB.MI",
    "SMI (Switzerland)": "^SSMI",
}
asian_indices = {
    "Nikkei 225": "^N225",
    "TOPIX": "^TOPX",
    "Hang Seng": "^HSI",
    "Shanghai Composite": "000001.SS",
    "Shenzhen Composite": "399001.SZ",
    "CSI 300": "000300.SS",
    "KOSPI": "^KS11",
    "ASX 200": "^AXJO",
    "Nifty 50": "^NSEI",
    "Sensex": "^BSESN"
}

fx_tickers = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
}

commodities_tickers = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Brent Crude": "BZ=F",
    "WTI Crude": "CL=F",
    "Copper": "HG=F",
    "Natural Gas": "NG=F",
    "Platinum": "PL=F"
}
crypto_tickers = {
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
    "Solana": "SOL-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD"
}

# =========================================================
# 1) MACRO DATA
# =========================================================

st.header("1) Macro Data")

macro_df = get_macro_data()
macro_df = macro_df.loc[str(macro_start_date):].copy()

metric_col, chart_col = st.columns([1, 2])

with metric_col:
    latest = macro_df[selected_macro].dropna()

    if len(latest) >= 2:
        latest_value = round(latest.iloc[-1], 2)
        delta_pct = round(((latest.iloc[-1] / latest.iloc[-2]) - 1) * 100, 2) if latest.iloc[-2] != 0 else None

        st.metric(
            label=selected_macro,
            value=f"{latest_value}",
            delta=f"{delta_pct}%" if delta_pct is not None else None
        )

    if show_tables:
        with st.expander("See latest macro table"):
            st.dataframe(macro_df.tail(18), width="stretch")

with chart_col:
    plot_df = macro_df[[selected_macro]].dropna().reset_index()
    plot_df.columns = ["Date", "Value"]

    fig = px.line(
        plot_df,
        x="Date",
        y="Value",
        title=f"{selected_macro} over time"
    )

    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, width="stretch")


# =========================================================
# 2) EQUITIES
# =========================================================

st.header("2) Major Equity Indices")
us_indices_df = get_market_snapshot(us_indices)
display_market_metrics(us_indices_df, n_cols=4)


selected_region = st.radio(
    "Choose region",
    ["US", "Europe", "Asia"],
    horizontal=True
)

if selected_region == "US":
    indices_df = get_market_snapshot(us_indices)
elif selected_region == "Europe":
    indices_df = get_market_snapshot(eu_indices)
else:
    indices_df = get_market_snapshot(asian_indices)

display_market_metrics(indices_df, n_cols=4, is_yield=False)

if show_tables:
    with st.expander(f"See {selected_region} equity indices table"):
        st.dataframe(indices_df, width="stretch")

# =========================================================
# 3) FX & COMMODITIES
# =========================================================

com_df = get_market_snapshot(commodities_tickers)
col1, col2 = st.columns(2)

with col1:
    st.subheader("FX")
    fx_df = get_market_snapshot(fx_tickers)
    display_market_metrics(fx_df, n_cols=2, is_yield=False)

    if show_tables:
        with st.expander("See FX table"):
            st.dataframe(fx_df, width="stretch")

with col2:
    st.subheader("Commodities")
    com_df = get_market_snapshot(commodities_tickers)
    display_market_metrics(com_df, n_cols=2, is_yield=False)

    if show_tables:
        with st.expander("See commodities table"):
            st.dataframe(com_df, width="stretch")
st.header("FX Correlation Heatmap")

fx_corr = get_fx_correlation_matrix(fx_tickers)

if not fx_corr.empty:

    fig = px.imshow(
        fx_corr,
        text_auto=True,
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        title="FX Daily Return Correlation"
    )

    st.plotly_chart(fig, width="stretch")

else:
    st.warning("FX correlation data unavailable.")

# =========================================================
# 4) CRYPTO
# =========================================================


st.header("4) Crypto Markets")

crypto_df = get_market_snapshot(crypto_tickers)

display_market_metrics(crypto_df, n_cols=4, is_yield=False)

if show_tables:
    with st.expander("See crypto table"):
        st.dataframe(crypto_df, width="stretch")


# =========================================================
# 4) GOVERNMENT RATES
# =========================================================
st.header("5) Government Rates")

rates_df = get_major_10y_yields_fred()

if not rates_df.empty:
    cols = st.columns(4)

    for i, row in rates_df.iterrows():
        delta_text = None if pd.isna(row["Delta"]) else f"{row['Delta']:+.3f}"

        cols[i % 4].metric(
            label=row["Name"],
            value=f"{row['Yield']:.3f}%",
            delta=delta_text
        )

    if show_tables:
        with st.expander("See government rates table"):
            st.dataframe(rates_df, width="stretch")
else:
    st.warning("No government rate data available.")
# =========================================================
# 5) MARKET SENTIMENT
# =========================================================
st.header("6) Market Sentiment")

score = 0

# Extract market moves
spx = us_indices_df.loc[us_indices_df["Name"] == "S&P 500", "Daily Change %"].values
vix = us_indices_df.loc[us_indices_df["Name"] == "VIX", "Daily Change %"].values
gold = com_df.loc[com_df["Name"] == "Gold", "Daily Change %"].values
brent = com_df.loc[com_df["Name"] == "Brent Crude", "Daily Change %"].values


# Equity signal
if len(spx) > 0 and spx[0] > 0:
    score += 1
else:
    score -= 1


# Volatility signal
if len(vix) > 0 and vix[0] > 0:
    score -= 1
else:
    score += 1


# Safe haven signal
if len(gold) > 0 and gold[0] > 0.5:
    score -= 1


# Oil shock signal
if len(brent) > 0 and brent[0] > 1:
    score -= 1


# Regime classification
if score >= 2:
    sentiment = "RISK ON"
elif score <= -1:
    sentiment = "RISK OFF"
else:
    sentiment = "NEUTRAL"


st.metric("Market Sentiment Score", score)
st.write(f"Market regime: **{sentiment}**")
# =========================================================
# 6) NEWS
# =========================================================

st.header("7) Important News")

articles = get_market_news()
display_news(articles)
