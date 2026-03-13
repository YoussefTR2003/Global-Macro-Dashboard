import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import plotly.express as px
import requests
import tradingeconomics as te
from newsapi import NewsApiClient


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
# API CONF
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

    for _, row in next_releases.iterrows():
        st.sidebar.write(f"• {row['date'].date()} — {row['name']}")

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
                progress=False
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
        df = df.sort_values("Daily Change %", ascending=False)

    return df


@st.cache_data(ttl=1800)
def get_government_rates():
    try:
        te_key = st.secrets.get("TE_API_KEY", "guest:guest")
        te.login(te_key)

        data = te.getMarketsData(marketsField="bond")
        df = pd.DataFrame(data)

        if df.empty:
            return pd.DataFrame()

        # debug once if needed
        # st.dataframe(df.head(30), use_container_width=True)

        df["Name"] = df["Name"].astype(str)

        keep_countries = [
            "United States",
            "Germany",
            "France",
            "Italy",
            "United Kingdom",
            "Japan"
        ]

        mask_country = df["Name"].str.contains("|".join(keep_countries), case=False, na=False)
        mask_10y = df["Name"].str.contains("10", case=False, na=False) | df["Symbol"].astype(str).str.contains("10Y", case=False, na=False)

        df = df[mask_country & mask_10y]

        if df.empty:
            return pd.DataFrame()

        df = df[["Name", "Last"]].rename(columns={"Last": "Yield"})
        df = df.dropna()
        df = df.reset_index(drop=True)

        return df

    except Exception as e:
        st.error(f"Government rates error: {e}")
        return pd.DataFrame()
def display_market_metrics(df, n_cols=4):

    if df.empty:
        st.warning("No data available.")
        return

    cols = st.columns(n_cols)

    for i, row in df.iterrows():
        cols[i % n_cols].metric(
            label=row["Name"],
            value=row["Last"],
            delta=f"{row['Daily Change %']}%"
        )


def get_market_news():

    try:

        response = newsapi.get_top_headlines(
            category="business",
            language="en",
            page_size=10
        )

        return response.get("articles", [])

    except:
        return []


def display_news(articles):

    if not articles:
        st.warning("No news retrieved.")
        return

    for article in articles:

        title = article.get("title")
        url = article.get("url")
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

fx_tickers = {
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CHF": "CHF=X"
}

commodities_tickers = {
    "Gold": "GC=F",
    "Brent": "BZ=F",
    "WTI": "CL=F",
    "Copper": "HG=F"
}


# =========================================================
# 1 MACRO DATA
# =========================================================

st.header("1) Macro Data")

macro_df = get_macro_data()
macro_df = macro_df.loc[str(macro_start_date):]

metric_col, chart_col = st.columns([1,2])

with metric_col:

    latest = macro_df[selected_macro].dropna()

    st.metric(
        selected_macro,
        round(latest.iloc[-1],2),
        round(((latest.iloc[-1]/latest.iloc[-2])-1)*100,2)
    )

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
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# 2 EQUITIES
# =========================================================

st.header("2) Major Equity Indices")

us_indices_df = get_market_snapshot(us_indices)
display_market_metrics(us_indices_df)


# =========================================================
# 3 FX & COMMODITIES
# =========================================================

st.header("3) FX & Commodities")

col1,col2 = st.columns(2)

with col1:
    fx_df = get_market_snapshot(fx_tickers)
    display_market_metrics(fx_df,2)

with col2:
    com_df = get_market_snapshot(commodities_tickers)
    display_market_metrics(com_df,2)


# =========================================================
# 4 GOVERNMENT RATES
# =========================================================

st.header("4) Government Rates")

gov_rates_df = get_government_rates()

if not gov_rates_df.empty:
    cols = st.columns(3)

    for i, row in gov_rates_df.iterrows():
        cols[i % 3].metric(
            label=row["Name"],
            value=f"{row['Yield']}%"
        )

    if show_tables:
        with st.expander("See government rates table"):
            st.dataframe(gov_rates_df, use_container_width="stretch")
else:
    st.warning("No government rate data available.")

# =========================================================
# 5 MARKET SENTIMENT
# =========================================================

st.header("5) Market Sentiment")

score = 0

spx = us_indices_df.loc[us_indices_df["Name"]=="S&P 500","Daily Change %"].values
vix = us_indices_df.loc[us_indices_df["Name"]=="VIX","Daily Change %"].values

if len(spx)>0 and spx[0] > 0:
    score += 1
else:
    score -= 1

if len(vix)>0 and vix[0] > 0:
    score -= 1
else:
    score += 1


if score >= 1:
    sentiment = "RISK ON"
elif score <= -1:
    sentiment = "RISK OFF"
else:
    sentiment = "NEUTRAL"

st.metric("Market Sentiment Score",score)
st.write(f"Market regime: **{sentiment}**")


# =========================================================
# 6 NEWS
# =========================================================

st.header("6) Important News")

articles = get_market_news()
display_news(articles)
