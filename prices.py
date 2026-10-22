"""Price sources: mfapi.in (India MF NAVs), Yahoo Finance via yfinance (US funds/ETFs, USD/INR FX)."""
import bisect
import datetime as dt
import re

import pandas as pd
import requests

import db

MFAPI = "https://api.mfapi.in/mf"
AMFI_NAVALL = "https://www.amfiindia.com/spages/NAVAll.txt"
ISIN_RE = re.compile(r"^IN[FE][0-9A-Z]{9}$")
FX_CODE = "FX:USDINR"
CACHE_HOURS = 6
_isin_map = {}


def resolve_isin(isin):
    """Map an Indian MF ISIN (growth or reinvestment) to its AMFI scheme code."""
    if not _isin_map:
        r = requests.get(AMFI_NAVALL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) >= 3 and parts[0].strip().isdigit():
                for i in parts[1:3]:
                    i = i.strip()
                    if ISIN_RE.match(i):
                        _isin_map[i] = parts[0].strip()
    return _isin_map.get(isin.strip().upper())


def search_india(query):
    r = requests.get(f"{MFAPI}/search", params={"q": query}, timeout=15)
    r.raise_for_status()
    return r.json()  # [{schemeCode, schemeName}]


def lookup_us(ticker):
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    name = info.get("longName") or info.get("shortName")
    if not name:
        hist = t.history(period="5d")
        if hist.empty:
            return None
        name = ticker.upper()
    return {"ticker": ticker.upper(), "name": name, "currency": info.get("currency", "USD")}


def _fetch_india(code):
    if ISIN_RE.match(code):
        scheme = resolve_isin(code)
        if not scheme:
            raise ValueError(f"ISIN {code} not found in AMFI NAVAll.txt")
        code = scheme
    r = requests.get(f"{MFAPI}/{code}", timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    s = pd.Series(
        {dt.datetime.strptime(d["date"], "%d-%m-%Y").date(): float(d["nav"]) for d in data if d.get("nav")}
    )
    return s.sort_index()


def _fetch_yahoo(ticker):
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="max", auto_adjust=False)
    if hist.empty:
        return pd.Series(dtype=float)
    s = hist["Close"].dropna()
    s.index = [d.date() for d in s.index]
    return s


def history(key, force=False):
    """key is 'IN:<scheme code>', 'US:<ticker>' or FX_CODE. Returns date-indexed Series, cached in SQLite."""
    last = db.last_fetched(key)
    stale = force or last is None or (pd.Timestamp.now() - last) > pd.Timedelta(hours=CACHE_HOURS)
    if stale:
        market, code = key.split(":", 1)
        try:
            if market == "IN":
                s = _fetch_india(code)
            elif market == "FX":
                s = _fetch_yahoo("USDINR=X")
            else:
                s = _fetch_yahoo(code)
            if not s.empty:
                db.save_prices(key, s)
                db.mark_fetched(key)
        except Exception as e:  # offline or API error: fall back to cache
            print(f"[prices] fetch failed for {key}: {e}")
    return db.load_prices(key)


def price_on_or_after(series, date):
    """NAV applicable to an investment on `date` (next trading day if holiday). None if not yet published."""
    if series.empty:
        return None, None
    idx = list(series.index)
    i = bisect.bisect_left(idx, date)
    if i >= len(idx):
        return None, None
    return idx[i], float(series.iloc[i])


def price_on_or_before(series, date):
    if series.empty:
        return None, None
    idx = list(series.index)
    i = bisect.bisect_right(idx, date) - 1
    if i < 0:
        return None, None
    return idx[i], float(series.iloc[i])


def latest(series):
    if series.empty:
        return None, None
    return series.index[-1], float(series.iloc[-1])


def fund_key(market, code):
    return f"{market}:{code}"
