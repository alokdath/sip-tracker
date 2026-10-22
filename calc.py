"""SIP schedule generation, holdings, XIRR and portfolio time series."""
import calendar
import datetime as dt

import pandas as pd

import db
import prices

# ---------------- schedule ----------------


def _add_months(d, months, day):
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(day, calendar.monthrange(y, m)[1]))


def sip_dates(frequency, day, start, end=None, upto=None):
    """Scheduled installment dates from start through min(end, upto)."""
    start = pd.Timestamp(start).date()
    stop = min(d for d in [pd.Timestamp(end).date() if end else None, upto or dt.date.today()] if d)
    out = []
    if frequency == "weekly":
        d = start + dt.timedelta(days=(int(day) - start.weekday()) % 7)
        while d <= stop:
            out.append(d)
            d += dt.timedelta(days=7)
    else:
        step = 1 if frequency == "monthly" else 3
        d = _add_months(start, 0, int(day))
        if d < start:
            d = _add_months(start, 1, int(day))
        k = 0
        while True:
            cur = _add_months(d.replace(day=1), k * step, int(day))
            if cur > stop:
                break
            out.append(cur)
            k += 1
    return out


def next_sip_date(frequency, day, start, end=None):
    today = dt.date.today()
    future = sip_dates(frequency, day, start, end, upto=today + dt.timedelta(days=120))
    future = [d for d in future if d > today]
    return future[0] if future else None


def sync_sip_installments():
    """Create BUY transactions for every due SIP installment whose NAV is published. Returns count added."""
    added = 0
    s = db.sips()
    for _, sip in s.iterrows():
        dates = sip_dates(sip.frequency, sip.day, sip.start_date, sip.end_date)
        existing = db.sip_txn_dates(sip.id) | db.sip_skips(sip.id)
        todo = [d for d in dates if str(d) not in existing]
        if not todo:
            continue
        series = prices.history(prices.fund_key(sip.market, sip.code))
        fx = fx_series() if sip.sip_currency != sip.currency else None
        for d in todo:
            _, nav = prices.price_on_or_after(series, d)
            if nav is None:
                continue  # NAV not yet available; retried on next sync
            amount, note = sip.amount, "SIP"
            if fx is not None:
                _, rate = prices.price_on_or_before(fx, d)
                if rate is None:
                    continue
                amount = convert(sip.amount, sip.sip_currency, sip.currency, d, fx)
                note = f"SIP {SYM_CCY[sip.sip_currency]}{sip.amount:,.0f} @ USDINR {rate:.2f}"
            units = amount * (1 - (sip.fee_pct or 0) / 100) / nav
            if sip.fee_pct:
                note += f", est. {sip.fee_pct:g}% cost"
            db.add_txn(sip.fund_id, d, "BUY", amount, units, nav, sip_id=int(sip.id), note=note)
            added += 1
    return added


SYM_CCY = {"INR": "₹", "USD": "$"}


# ---------------- XIRR ----------------


def xirr(cashflows):
    """cashflows: list of (date, amount); investments negative, value/redemptions positive."""
    cfs = [(pd.Timestamp(d).date(), float(a)) for d, a in cashflows if a]
    if len(cfs) < 2 or all(a >= 0 for _, a in cfs) or all(a <= 0 for _, a in cfs):
        return None
    t0 = min(d for d, _ in cfs)
    yrs = [((d - t0).days / 365.0, a) for d, a in cfs]
    if max(t for t, _ in yrs) < 1 / 365:
        return None

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in yrs)

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return mid


# ---------------- FX ----------------


def fx_series():
    return prices.history(prices.FX_CODE)


def convert(amount, currency, base, date, fx):
    """Convert amount from currency to base using USDINR rate on/before date."""
    if currency == base or amount is None:
        return amount
    _, rate = prices.price_on_or_before(fx, date)
    if rate is None:
        _, rate = prices.latest(fx)
    if rate is None:
        return None
    return amount * rate if currency == "USD" else amount / rate


# ---------------- holdings ----------------


def holdings(base="INR"):
    """Per-fund summary plus portfolio totals in base currency."""
    f = db.funds()
    t = db.transactions()
    fx = fx_series()
    today = dt.date.today()
    rows, all_cfs = [], []
    for _, fund in f.iterrows():
        ft = t[t.fund_id == fund.id].sort_values("date")
        series = prices.history(prices.fund_key(fund.market, fund.code))
        nav_date, nav = prices.latest(series)
        units = cost = 0.0
        cfs = []
        for _, x in ft.iterrows():
            d = pd.Timestamp(x.date).date()
            if x.type == "BUY":
                units += x.units
                cost += x.amount
                cfs.append((d, -x.amount))
                all_cfs.append((d, -convert(x.amount, fund.currency, base, d, fx)))
            else:
                if units > 0:
                    cost -= cost * min(x.units / units, 1)
                units -= x.units
                cfs.append((d, x.amount))
                all_cfs.append((d, convert(x.amount, fund.currency, base, d, fx)))
        value = units * nav if nav is not None else None
        if value:
            cfs.append((today, value))
        r = xirr(cfs)
        value_base = convert(value, fund.currency, base, today, fx) if value is not None else None
        cost_base = sum(
            convert(x.amount, fund.currency, base, pd.Timestamp(x.date).date(), fx) * (1 if x.type == "BUY" else -1)
            for _, x in ft.iterrows()
        ) if not ft.empty else 0.0
        rows.append(
            {
                "fund_id": fund.id,
                "Fund": fund["name"],
                "Market": fund.market,
                "Code": fund.code,
                "Ccy": fund.currency,
                "Installments": int((ft.type == "BUY").sum()),
                "First buy": pd.Timestamp(ft.date.min()).date() if not ft.empty else None,
                "Units": units,
                "NAV": nav,
                "NAV date": nav_date,
                "Invested": cost,
                "Value": value,
                "Gain": (value - cost) if value is not None else None,
                "Return %": ((value - cost) / cost * 100) if value is not None and cost else None,
                "XIRR %": r * 100 if r is not None else None,
                f"Net invested ({base})": cost_base,
                f"Value ({base})": value_base,
            }
        )
    df = pd.DataFrame(rows)
    total_value = df[f"Value ({base})"].fillna(0).sum() if not df.empty else 0.0
    total_net = df[f"Net invested ({base})"].fillna(0).sum() if not df.empty else 0.0
    if total_value:
        all_cfs.append((today, total_value))
    pr = xirr(all_cfs)
    totals = {
        "value": total_value,
        "net_invested": total_net,
        "gain": total_value - total_net,
        "return_pct": (total_value - total_net) / total_net * 100 if total_net else None,
        "xirr_pct": pr * 100 if pr is not None else None,
        "usdinr": prices.latest(fx)[1],
    }
    return df, totals


def value_timeseries(base="INR", freq="W-FRI"):
    """Portfolio market value vs cumulative net investment over time, in base currency."""
    f = db.funds()
    t = db.transactions()
    if t.empty:
        return pd.DataFrame(), pd.DataFrame()
    fx = fx_series()
    start = pd.Timestamp(t.date.min())
    idx = pd.date_range(start, pd.Timestamp.today().normalize(), freq=freq)
    idx = idx.union([pd.Timestamp.today().normalize()])
    fx_s = pd.Series(fx.values, index=pd.to_datetime(fx.index)) if not fx.empty else None

    def to_base(s, ccy):
        if ccy == base or fx_s is None:
            return s
        rate = fx_s.reindex(s.index.union(fx_s.index)).ffill().bfill().reindex(s.index)
        return s * rate if ccy == "USD" else s / rate

    value_total = pd.Series(0.0, index=idx)
    invested_total = pd.Series(0.0, index=idx)
    per_fund = {}
    for _, fund in f.iterrows():
        ft = t[t.fund_id == fund.id].copy()
        if ft.empty:
            continue
        ft["d"] = pd.to_datetime(ft.date)
        ft["su"] = ft.units.where(ft.type == "BUY", -ft.units)
        ft["sa"] = ft.amount.where(ft.type == "BUY", -ft.amount)
        units = ft.groupby("d").su.sum().cumsum()
        units = units.reindex(units.index.union(idx)).ffill().fillna(0).reindex(idx)
        series = prices.history(prices.fund_key(fund.market, fund.code))
        if series.empty:
            continue
        ps = pd.Series(series.values, index=pd.to_datetime(series.index))
        ps = ps.reindex(ps.index.union(idx)).ffill().reindex(idx)
        val = to_base((units * ps).fillna(0), fund.currency)
        inv_by_day = ft.groupby("d").sa.sum()
        inv_base = to_base(inv_by_day, fund.currency).cumsum()
        inv = inv_base.reindex(inv_base.index.union(idx)).ffill().fillna(0).reindex(idx)
        value_total += val
        invested_total += inv
        per_fund[fund["name"]] = val
    out = pd.DataFrame({"Value": value_total, "Net invested": invested_total})
    return out, pd.DataFrame(per_fund)
