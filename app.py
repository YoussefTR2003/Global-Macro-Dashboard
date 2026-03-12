import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
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
# FRED CONFIG
# =========================================================
fred = Fred(api_key=st.secrets["FRED_API_KEY"])

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.header("Dashboard Settings")

st.sidebar.image("assets/Image.jpg", width=120)
st.sidebar.markdown("**Youssef Triki**")
st.sidebar.caption("EDHEC Business School — MSc Finance")

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

news_source = st.sidebar.selectbox(
    "News source ticker",
    ["^GSPC", "^NDX", "^TNX", "CL=F", "GC=F", "EURUSD=X", "AAPL", "MSFT", "NVDA"]
)

# =========================================================
# HELPERS
# =========================================================
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
                auto_adjust=False,
                progress=False
            )

            if hist.empty or len(hist) < 2:
                continue

            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            daily_change_pct = ((last_close / prev_close) - 1) * 100

            rows.append({
                "Name": label,
                "Ticker": ticker,
                "Last": round(last_close, 2),
                "Daily Change %": round(daily_change_pct, 2)
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("Daily Change %", ascending=False).reset_index(drop=True)

    return df


@st.cache_data(ttl=1800)
def get_news_for_ticker(ticker):
    try:
        tk = yf.Ticker(ticker)
        news = tk.get_news()
        return news if news else []
    except Exception:
        return []


def is_geopolitical(title):
    keywords = [
        "iran", "israel", "war", "military", "missile", "conflict",
        "sanctions", "oil", "strait", "hormuz", "middle east", "attack",
        "ceasefire", "russia", "ukraine", "china", "taiwan", "tariff",
        "geopolitical", "troops", "bomb", "strike"
    ]
    title_lower = title.lower()
    return any(word in title_lower for word in keywords)


def display_market_metrics(df, n_cols=4):
    if df.empty:
        st.warning("No market data available.")
        return

    cols = st.columns(n_cols)

    for i, row in df.iterrows():
        cols[i % n_cols].metric(
            label=row["Name"],
            value=f'{row["Last"]}',
            delta=f'{row["Daily Change %"]}%'
        )


def display_news_cards(news_items, max_items=12):
    if not news_items:
        st.warning("No news retrieved.")
        return

    for item in news_items[:max_items]:
        title = item.get("title", "No title")
        publisher = item.get("publisher", "Unknown source")
        link = item.get("link", "")
        related = item.get("relatedTickers", [])

        if is_geopolitical(title):
            st.markdown(
                f"""
                <div style='padding:12px; border-left:6px solid red; background-color:#ffe6e6; margin-bottom:12px; border-radius:6px;'>
                    <b>{title}</b><br>
                    <span style='font-size: 13px;'><i>{publisher}</i></span><br>
                    <span style='font-size: 13px;'>Related tickers: {related}</span><br>
                    <a href='{link}' target='_blank'>Open article</a>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""
                <div style='padding:12px; border-left:6px solid #999; background-color:#f7f7f7; margin-bottom:12px; border-radius:6px;'>
                    <b>{title}</b><br>
                    <span style='font-size: 13px;'><i>{publisher}</i></span><br>
                    <span style='font-size: 13px;'>Related tickers: {related}</span><br>
                    <a href='{link}' target='_blank'>Open article</a>
                </div>
                """,
                unsafe_allow_html=True
            )

import requests

def get_gnews_titles(query="finance OR economy OR geopolitics", max_items=10):
    api_key = st.secrets.get("GNEWS_API_KEY", None)

    if api_key is None:
        st.error("GNEWS_API_KEY not found in Streamlit secrets.")
        return []

    url = "https://gnews.io/api/v4/search"

    params = {
        "q": query,
        "lang": "en",
        "max": max_items,
        "apikey": api_key
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return data.get("articles", [])
    except Exception as e:
        st.error(f"GNews request failed: {e}")
        return []


def display_gnews_titles(articles):
    if not articles:
        st.warning("No news retrieved.")
        return

    for article in articles:
        title = article.get("title", "No title")
        url = article.get("url", "#")
        source = article.get("source", {}).get("name", "Unknown source")
        date = article.get("publishedAt", "")

        if is_geopolitical(title):
            st.markdown(f"🔴 **[{title}]({url})**  \n{source} — {date}")
        else:
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

us_stocks = {
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "Nvidia": "NVDA",
    "Amazon": "AMZN",
    "Google": "GOOGL",
    "Meta": "META",
    "Tesla": "TSLA",
    "JPMorgan": "JPM",
    "Goldman Sachs": "GS",
    "Morgan Stanley": "MS",
    "Bank of America": "BAC",
    "BlackRock": "BLK"
}

eu_indices = {
    "Euro Stoxx 50": "^STOXX50E",
    "STOXX 600": "^STOXX",
    "CAC 40": "^FCHI",
    "DAX": "^GDAXI",
    "FTSE 100": "^FTSE",
    "IBEX 35": "^IBEX",
    "SMI": "^SSMI",
    "FTSE MIB": "FTSEMIB.MI"
}

eu_stocks = {
    "LVMH": "MC.PA",
    "Hermes": "RMS.PA",
    "Airbus": "AIR.PA",
    "ASML": "ASML.AS",
    "SAP": "SAP.DE",
    "Siemens": "SIE.DE",
    "Nestle": "NESN.SW",
    "Roche": "ROG.SW",
    "Shell": "SHEL.L",
    "TotalEnergies": "TTE.PA",
    "Novo Nordisk": "NOVO-B.CO"
}

asia_indices = {
    "Nikkei 225": "^N225",
    "TOPIX": "^TOPX",
    "Hang Seng": "^HSI",
    "Shanghai Composite": "000001.SS",
    "Shenzhen": "399001.SZ",
    "CSI 300": "000300.SS",
    "KOSPI": "^KS11",
    "ASX 200": "^AXJO"
}

asia_stocks = {
    "Toyota": "7203.T",
    "Sony": "6758.T",
    "SoftBank": "9984.T",
    "Alibaba": "9988.HK",
    "Tencent": "0700.HK",
    "Samsung Elec": "005930.KS",
    "TSMC": "2330.TW",
    "BYD": "1211.HK"
}
fx_tickers = {
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CHF": "CHF=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CNH": "CNH=X"
}

commodities_tickers = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Brent": "BZ=F",
    "WTI": "CL=F",
    "Copper": "HG=F",
    "Natural Gas": "NG=F"
}

# =========================================================
# 1) MACRO DATA
# =========================================================
st.header("1) Macro Data")

macro_df = get_macro_data()
macro_df = macro_df.loc[str(macro_start_date):].copy()

metric_col, chart_col = st.columns([1, 2])

with metric_col:
    st.subheader("Latest Macro Snapshot")

    latest_series = macro_df[selected_macro].dropna()
    latest_value = latest_series.iloc[-1]
    previous_value = latest_series.iloc[-2]

    delta_pct = ((latest_value / previous_value) - 1) * 100 if previous_value != 0 else 0

    st.metric(
        label=selected_macro,
        value=f"{latest_value:.2f}",
        delta=f"{delta_pct:.2f}%"
    )

    if show_tables:
        with st.expander("See latest macro table"):
            st.dataframe(macro_df.tail(18), use_container_width=True)

with chart_col:
    st.subheader(f"{selected_macro} Evolution")

    plot_df = macro_df[[selected_macro]].dropna().reset_index()
    plot_df.columns = ["Date", "Value"]

    fig = px.line(
        plot_df,
        x="Date",
        y="Value",
        title=f"{selected_macro} over time"
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# 2) EQUITIES & INDICES
# =========================================================
st.header("2) Equities & Major Indices")

tab_us, tab_eu, tab_asia = st.tabs(["US", "Europe", "Asia"])

with tab_us:
    st.subheader("US Major Indices")
    us_indices_df = get_market_snapshot(us_indices)
    display_market_metrics(us_indices_df, n_cols=4)

    if show_tables:
        with st.expander("See US indices table"):
            st.dataframe(us_indices_df, use_container_width=True)

    st.subheader("US Major Stocks")
    us_stocks_df = get_market_snapshot(us_stocks)
    display_market_metrics(us_stocks_df, n_cols=4)

    if show_tables:
        with st.expander("See US stocks table"):
            st.dataframe(us_stocks_df, use_container_width=True)

with tab_eu:
    st.subheader("European Major Indices")
    eu_indices_df = get_market_snapshot(eu_indices)
    display_market_metrics(eu_indices_df, n_cols=4)

    if show_tables:
        with st.expander("See European indices table"):
            st.dataframe(eu_indices_df, use_container_width=True)

    st.subheader("European Major Stocks")
    eu_stocks_df = get_market_snapshot(eu_stocks)
    display_market_metrics(eu_stocks_df, n_cols=4)

    if show_tables:
        with st.expander("See European stocks table"):
            st.dataframe(eu_stocks_df, use_container_width=True)

with tab_asia:
    st.subheader("Asian Major Indices")
    asia_indices_df = get_market_snapshot(asia_indices)
    display_market_metrics(asia_indices_df, n_cols=4)

    if show_tables:
        with st.expander("See Asian indices table"):
            st.dataframe(asia_indices_df, use_container_width=True)

    st.subheader("Asian Major Stocks")
    asia_stocks_df = get_market_snapshot(asia_stocks)
    display_market_metrics(asia_stocks_df, n_cols=4)

    if show_tables:
        with st.expander("See Asian stocks table"):
            st.dataframe(asia_stocks_df, use_container_width=True)
# =========================================================
# 3) FX & COMMODITIES
# =========================================================
st.header("3) FX & Commodities")

col_fx, col_com = st.columns(2)

with col_fx:
    st.subheader("FX")
    fx_df = get_market_snapshot(fx_tickers)
    display_market_metrics(fx_df, n_cols=2)

    if show_tables:
        with st.expander("See FX table"):
            st.dataframe(fx_df, use_container_width=True)

with col_com:
    st.subheader("Commodities")
    commodities_df = get_market_snapshot(commodities_tickers)
    display_market_metrics(commodities_df, n_cols=2)

    if show_tables:
        with st.expander("See commodities table"):
            st.dataframe(commodities_df, use_container_width=True)


# =========================================================
# IMPORTANT NEWS

# =========================================================

# =========================================================
# 4) MARKET SENTIMENT
# =========================================================

st.header("4) Market Sentiment")

score = 0

spx = us_indices_df.loc[us_indices_df["Name"]=="S&P 500","Daily Change %"].values
vix = us_indices_df.loc[us_indices_df["Name"]=="VIX","Daily Change %"].values
gold = commodities_df.loc[commodities_df["Name"]=="Gold","Daily Change %"].values
brent = commodities_df.loc[commodities_df["Name"]=="Brent","Daily Change %"].values

if len(spx)>0 and spx[0] > 0:
    score += 1
else:
    score -= 1

if len(vix)>0 and vix[0] > 0:
    score -= 1
else:
    score += 1

if len(gold)>0 and gold[0] > 0.5:
    score -= 1

if len(brent)>0 and brent[0] > 1:
    score -= 1


if score >= 2:
    sentiment = "RISK ON"
    color = "green"
elif score <= -1:
    sentiment = "RISK OFF"
    color = "red"
else:
    sentiment = "NEUTRAL"
    color = "orange"

st.markdown(
    f"<h2 style='color:{color}; text-align:center'>{sentiment}</h2>",
    unsafe_allow_html=True
)

st.caption(f"Sentiment score: {score}")
st.header("5) Important News")

articles = get_gnews_titles()

display_gnews_titles(articles)
