import datetime as dt
import io

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import calc
import db
import prices
import ui
from ui import money, pct, chip, esc

st.set_page_config(page_title="SIP Tracker", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
db.init()
st.markdown(ui.CSS, unsafe_allow_html=True)

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FREQ_MULT = {"monthly": 1, "weekly": 52 / 12, "quarterly": 1 / 3}
PAGES = {"Dashboard": "◧  Dashboard", "Funds & SIPs": "⟳  Funds & SIPs", "Transactions": "☰  Transactions",
         "Import / Export": "⇅  Import / Export"}


# ---------------- sidebar ----------------
with st.sidebar:
    st.html('<div class="brand"><div class="logo">S</div><div><div class="name">SIP Tracker</div>'
            '<div class="sub">India · US mutual funds</div></div></div><div class="navlabel">Menu</div>')
    page = st.radio("Navigation", list(PAGES), format_func=PAGES.get, label_visibility="collapsed")
    st.html('<div class="navlabel" style="margin-top:1.2rem">Display currency</div>')
    base = st.radio("Base currency", ["INR", "USD"], horizontal=True, label_visibility="collapsed", key="ccy",
                    format_func=lambda c: {"INR": "₹ INR", "USD": "US$ USD"}[c])
    st.write("")
    refresh = st.button("↻  Refresh NAVs & sync", width="stretch")

if refresh:
    with st.spinner("Fetching latest NAVs…"):
        for _, r in db.funds().iterrows():
            prices.history(prices.fund_key(r.market, r.code), force=True)
        prices.history(prices.FX_CODE, force=True)
        n = calc.sync_sip_installments()
    st.toast(f"Prices refreshed · {n} new SIP installment(s) logged", icon="✅")

if "synced" not in st.session_state:
    with st.spinner("Syncing SIP installments…"):
        st.session_state.synced = calc.sync_sip_installments()

fx = calc.fx_series()
fx_date, fx_rate = prices.latest(fx)
with st.sidebar:
    st.html(f'<div class="fxbox">USD / INR<br><b>{fx_rate:,.2f}</b>'
            f'<div style="color:#64748B;margin-top:2px">as of {fx_date:%d %b %Y}</div></div>' if fx_rate else
            '<div class="fxbox">USD / INR unavailable</div>')


def sip_label(r):
    when = f"every {WEEKDAYS[r.day]}" if r.frequency == "weekly" else f"{ordinal(r.day)} of {'month' if r.frequency == 'monthly' else 'quarter'}"
    return when


def ordinal(n):
    n = int(n)
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ---------------- Dashboard ----------------
def dashboard():
    h, tot = calc.holdings(base)
    if h.empty:
        st.html(ui.page_header("Portfolio", "Add your first fund under Funds & SIPs to get started."))
        return
    s = db.sips()
    active = s[s.active == 1].copy()
    today = dt.date.today()

    h["Short"] = h.Fund.map(ui.short_name)
    h["Category"] = [ui.category(n, m) for n, m in zip(h.Fund, h.Market)]
    vb, ib = f"Value ({base})", f"Net invested ({base})"
    total = h[vb].fillna(0).sum()
    h["Weight"] = h[vb].fillna(0) / total * 100 if total else 0
    sip_funds = set(active.fund_id)

    nav_dates = [d for d in h["NAV date"] if d is not None]
    asof = max(nav_dates) if nav_dates else today
    st.html(ui.page_header("Portfolio", f"NAVs as of {asof:%d %b %Y} · values in {base}",
                           f"{len(h)} funds · {len(active)} active SIPs"))

    # --- KPI row
    monthly = sum((calc.convert(r.amount * FREQ_MULT[r.frequency], r.sip_currency, base, today, fx) or 0)
                  for _, r in active.iterrows())
    nexts = [(calc.next_sip_date(r.frequency, r.day, r.start_date, r.end_date), r) for _, r in active.iterrows()]
    nexts = sorted([x for x in nexts if x[0]], key=lambda x: x[0])
    nd = nexts[0][0] if nexts else None
    nd_amt = sum(calc.convert(r.amount, r.sip_currency, base, today, fx) or 0 for d, r in nexts if d == nd)
    xirr = tot["xirr_pct"]
    st.html(f"""
<div class="grid g-hero">
  <div class="card hero"><div class="lbl">Current value</div><div class="val">{money(tot['value'], base)}</div>
    <div class="foot">{chip(tot['return_pct'], f"{money(tot['gain'], base)} · {pct(tot['return_pct'])}")}&nbsp; overall gain</div></div>
  <div class="card"><div class="lbl">Invested</div><div class="val">{money(tot['net_invested'], base, compact=True)}</div>
    <div class="foot">net of redemptions</div></div>
  <div class="card"><div class="lbl">XIRR</div><div class="val {ui.signed_cls(xirr)}">{pct(xirr)}</div>
    <div class="foot">annualised, money-weighted</div></div>
  <div class="card"><div class="lbl">Monthly SIP</div><div class="val">{money(monthly, base, compact=True)}</div>
    <div class="foot">{len(active)} active SIPs</div></div>
  <div class="card"><div class="lbl">Next SIP</div><div class="val">{f"{nd:%d %b}" if nd else "—"}</div>
    <div class="foot">{f"{money(nd_amt, base, compact=True)} · in {(nd - today).days} days" if nd else "no active SIPs"}</div></div>
</div>""")

    # --- market split
    cards = []
    for market, flag, label, ccy in [("IN", "🇮🇳", "India", "INR"), ("US", "🇺🇸", "United States", "USD")]:
        m = h[h.Market == market]
        if m.empty:
            continue
        inv, val = m.Invested.sum(), m.Value.fillna(0).sum()
        ret = (val - inv) / inv * 100 if inv else None
        share = m[vb].fillna(0).sum() / total * 100 if total else 0
        msip = active[active.market == market]
        msip_amt = sum(r.amount * FREQ_MULT[r.frequency] for _, r in msip.iterrows())
        msip_ccy = msip.sip_currency.iloc[0] if not msip.empty else ccy
        color = "#4F46E5" if market == "IN" else "#F97316"
        cards.append(f"""
<div class="card mkt">
  <div class="top"><div class="ttl"><span class="flag">{flag}</span>{label}</div>{chip(ret)}</div>
  <div class="row">
    <div><span>Value</span><b>{money(val, ccy)}</b></div>
    <div><span>Invested</span><b>{money(inv, ccy)}</b></div>
    <div><span>Gain</span><b class="{ui.signed_cls(val - inv)}">{money(val - inv, ccy)}</b></div>
    <div><span>SIP / month</span><b>{money(msip_amt, msip_ccy, compact=True) if msip_amt else "—"}</b></div>
  </div>
  <div><div class="bar"><i style="width:{share:.1f}%;background:{color}"></i></div>
  <div class="foot" style="margin-top:6px">{share:.1f}% of portfolio · {len(m)} funds</div></div>
</div>""")
    st.html(f'<div class="grid g-2" style="margin-top:16px">{"".join(cards)}</div>')

    # --- charts
    st.html(ui.section("Performance & allocation"))
    ts, per_fund = calc.value_timeseries(base)
    c1, c2 = st.columns([1.75, 1], gap="medium")
    if not ts.empty:
        div, suf = (1e5, " L") if base == "INR" else (1e3, "K")
        hover = "%{y:,.2f}" + suf
        fig = go.Figure()
        fig.add_scatter(x=ts.index, y=ts["Value"] / div, name="Market value", mode="lines", hovertemplate=hover,
                        line=dict(color="#4F46E5", width=2.5), fill="tozeroy", fillcolor="rgba(79,70,229,.10)")
        fig.add_scatter(x=ts.index, y=ts["Net invested"] / div, name="Invested", mode="lines", hovertemplate=hover,
                        line=dict(color="#94A3B8", width=2, dash="dot"))
        ui.plotly_layout(fig, 380, "Value vs invested")
        fig.update_yaxes(tickprefix=ui.SYM[base], ticksuffix=suf)
        fig.update_layout(hovermode="x unified")
        c1.plotly_chart(fig, config={"displayModeBar": False})
    cat = h.groupby("Category")[vb].sum().sort_values(ascending=False)
    cat = cat[cat > 0]
    if not cat.empty:
        fig = go.Figure(go.Pie(labels=cat.index, values=cat.values, hole=0.68, sort=False,
                               marker=dict(colors=[ui.CAT_COLORS.get(c, "#94A3B8") for c in cat.index],
                                           line=dict(color="#fff", width=2)),
                               textinfo="none", hovertemplate="%{label}<br>%{percent}<extra></extra>"))
        ui.plotly_layout(fig, 380, "Asset mix", legend=True)
        fig.update_layout(legend=dict(orientation="v", x=1.0, xanchor="left", y=0.5, yanchor="middle"),
                          annotations=[dict(text=f"<b>{len(cat)}</b><br><span style='font-size:11px;color:#64748B'>categories</span>",
                                            showarrow=False, font=dict(size=20, color="#0F172A"))])
        c2.plotly_chart(fig, config={"displayModeBar": False})

    # --- holdings
    for market, label, ccy in [("IN", "India holdings", "INR"), ("US", "US holdings", "USD")]:
        m = h[h.Market == market].sort_values(vb, ascending=False)
        if m.empty:
            continue
        rows = []
        for _, r in m.iterrows():
            color = ui.CAT_COLORS.get(r.Category, "#94A3B8")
            status = '<span class="badge-sip">SIP active</span>' if r.fund_id in sip_funds else '<span class="badge-stop">Holding</span>'
            nav_txt = f"NAV {money(r.NAV, ccy, decimals=2)}" if r.NAV is not None and not pd.isna(r.NAV) else ""
            young = r["First buy"] is not None and (today - r["First buy"]).days < 365
            xirr_cell = ('<span class="muted" title="XIRR annualises short-period returns and is misleading under a year">&lt;1 yr</span>'
                         if young else f'<span class="{ui.signed_cls(r["XIRR %"])}">{pct(r["XIRR %"])}</span>')
            rows.append(f"""
<tr>
 <td><div class="fn">{esc(r.Short)}</div>
   <div class="meta"><span class="pill" style="background:{color}">{r.Category}</span>{status}<span>{nav_txt}</span></div></td>
 <td>{money(r.Invested, ccy)}<span class="sub">{r.Installments} buys · {r.Units:,.3f} units</span></td>
 <td><b>{money(r.Value, ccy)}</b></td>
 <td><span class="{ui.signed_cls(r.Gain)}">{money(r.Gain, ccy)}</span><span class="sub">{pct(r['Return %'])}</span></td>
 <td>{xirr_cell}</td>
 <td><div class="alloc"><div class="bar"><i style="width:{min(r.Weight * 2, 100):.1f}%;background:{color}"></i></div>{r.Weight:.1f}%</div></td>
</tr>""")
        inv, val = m.Invested.sum(), m.Value.fillna(0).sum()
        st.html(ui.section(label, f"{len(m)} funds · values in {ccy}") + f"""
<table class="tbl">
 <thead><tr><th>Fund</th><th>Invested</th><th>Current value</th><th>Gain</th><th>XIRR</th><th>Weight</th></tr></thead>
 <tbody>{''.join(rows)}</tbody>
 <tfoot><tr><td>Total</td><td>{money(inv, ccy)}</td><td>{money(val, ccy)}</td>
   <td><span class="{ui.signed_cls(val - inv)}">{money(val - inv, ccy)}</span><span class="sub">{pct((val - inv) / inv * 100 if inv else None)}</span></td>
   <td></td><td>{m.Weight.sum():.1f}%</td></tr></tfoot>
</table>""")

    # --- upcoming
    if nexts:
        items = []
        for d, r in nexts:
            items.append(f"""
<div class="up-card"><div class="cal"><div class="m">{d:%b}</div><div class="d">{d.day}</div></div>
 <div><div class="f">{esc(ui.short_name(r.fund))}</div>
 <div class="a">{money(r.amount, r.sip_currency)} · {"today" if d == today else f"in {(d - today).days} days"}</div></div></div>""")
        st.html(ui.section("Upcoming SIP installments", f"{money(monthly, base)} per month") + f'<div class="ups">{"".join(items)}</div>')


# ---------------- Funds & SIPs ----------------
def funds_page():
    st.html(ui.page_header("Funds & SIPs", "Manage your schemes and recurring investments"))
    t2, t1, t3 = st.tabs(["SIPs", "Add fund", "All funds"])

    with t1:
        market = st.radio("Market", ["India (AMFI)", "US (ticker)"], horizontal=True)
        if market.startswith("India"):
            q = st.text_input("Search fund name", placeholder="e.g. parag parikh flexi cap direct growth")
            if q:
                try:
                    res = prices.search_india(q)
                except Exception as e:
                    st.error(f"Search failed: {e}")
                    res = []
                if res:
                    opts = {f"{r['schemeName']} ({r['schemeCode']})": r for r in res[:50]}
                    pick = st.selectbox("Select scheme", list(opts))
                    if st.button("Add fund", type="primary"):
                        r = opts[pick]
                        try:
                            db.add_fund(r["schemeName"], "IN", r["schemeCode"], "INR")
                            st.success(f"Added {r['schemeName']}")
                        except Exception as e:
                            st.error(f"Could not add: {e}")
                elif q:
                    st.warning("No matches.")
        else:
            tk = st.text_input("Ticker", placeholder="e.g. VFIAX, FXAIX, VTI, VOO").strip().upper()
            if tk and st.button("Look up & add", type="primary"):
                with st.spinner("Looking up…"):
                    info = prices.lookup_us(tk)
                if not info:
                    st.error("Ticker not found on Yahoo Finance.")
                else:
                    try:
                        db.add_fund(info["name"], "US", info["ticker"], "USD")
                        st.success(f"Added {info['name']} ({info['ticker']})")
                    except Exception as e:
                        st.error(f"Could not add: {e}")

    f = db.funds()
    with t2:
        if f.empty:
            st.info("Add a fund first.")
        else:
            with st.expander("＋  Create a new SIP"), st.form("add_sip", clear_on_submit=True):
                labels = {f"{r['name']} [{r.market}]": r for _, r in f.iterrows()}
                c = st.columns([3, 1, 1, 1, 1, 1])
                fl = c[0].selectbox("Fund", list(labels))
                amount = c[1].number_input("Amount", min_value=1.0, value=5000.0, step=500.0)
                amt_ccy = c[2].selectbox("Amount currency", ["Fund currency", "INR"],
                                         help="Pick INR for US funds bought with rupees (e.g. INDmoney); "
                                              "converted to USD at each date's USD/INR rate.")
                fee = c[3].number_input("Est. cost %", min_value=0.0, max_value=5.0, value=0.0, step=0.25,
                                        help="Brokerage + FX markup deducted before units are bought (INDmoney ≈ 1%).")
                freq = c[4].selectbox("Frequency", ["monthly", "weekly", "quarterly"])
                day = c[5].number_input("Day of month (1-31) / weekday (0=Mon)", min_value=0, max_value=31, value=5)
                c2 = st.columns(2)
                start = c2[0].date_input("Start date", value=dt.date.today().replace(day=1), min_value=dt.date(1990, 1, 1))
                has_end = c2[1].checkbox("Has end date")
                end = c2[1].date_input("End date", value=dt.date.today() + dt.timedelta(days=365 * 5)) if has_end else None
                st.caption("Past installments are back-filled automatically using the historical NAV of each date "
                           "(next trading day if a holiday). Edit units in **Transactions** to match your statement.")
                if st.form_submit_button("Create SIP", type="primary"):
                    fund = labels[fl]
                    if freq == "weekly" and day > 6:
                        st.error("For weekly SIPs, day must be 0 (Mon) – 6 (Sun).")
                    elif freq != "weekly" and day < 1:
                        st.error("Day of month must be 1–31.")
                    else:
                        sip_ccy = None if amt_ccy == "Fund currency" or fund.currency == amt_ccy else amt_ccy
                        db.add_sip(int(fund.id), amount, freq, int(day), start, end, sip_ccy, fee)
                        with st.spinner("Back-filling installments…"):
                            n = calc.sync_sip_installments()
                        st.success(f"SIP created; {n} installment(s) logged.")

            s = db.sips().sort_values(["active", "fund"], ascending=[False, True])
            if not s.empty:
                st.html(ui.section("Your SIPs", f"{int(s.active.sum())} active · {int((s.active == 0).sum())} stopped"))
                today = dt.date.today()
                for _, r in s.iterrows():
                    nd = calc.next_sip_date(r.frequency, r.day, r.start_date, r.end_date) if r.active else None
                    color = ui.CAT_COLORS.get(ui.category(r.fund, r.market), "#94A3B8")
                    status = ('<span class="badge-sip">Active</span>' if r.active else '<span class="badge-stop">Stopped</span>')
                    fx_note = f" → {r.currency} at daily FX" if r.sip_currency != r.currency else ""
                    fee_note = f"<span>Est. cost <b>{r.fee_pct:g}%</b></span>" if r.fee_pct else ""
                    nxt = f"{nd:%d %b %Y} <span style='color:#94A3B8'>({(nd - today).days}d)</span>" if nd else "—"
                    with st.container(border=True):
                        c = st.columns([6, 1, 1], vertical_alignment="center")
                        c[0].html(f"""
<div class="sipc"><div class="f"><span class="dot" style="background:{color};margin-right:8px"></span>{esc(ui.short_name(r.fund))}
 &nbsp;{status}&nbsp;<span style="color:#94A3B8;font-weight:500;font-size:.75rem">{r.market}</span></div>
 <div class="m"><span><b>{money(r.amount, r.sip_currency)}</b> {r.frequency}{fx_note}</span>
  <span>on the <b>{sip_label(r)}</b></span>
  <span>Since <b>{pd.Timestamp(r.start_date):%d %b %Y}</b>{f" until <b>{pd.Timestamp(r.end_date):%d %b %Y}</b>" if r.end_date else ""}</span>
  <span>Next <b>{nxt}</b></span>{fee_note}</div></div>""")
                        if r.active:
                            if c[1].button("Stop", key=f"stop{r.id}", help="Stop SIP from today (keeps history)", width="stretch"):
                                db.set_sip_active(r.id, False, dt.date.today())
                                st.rerun()
                        elif c[1].button("Resume", key=f"res{r.id}", width="stretch"):
                            db.execute("UPDATE sips SET active = 1, end_date = NULL WHERE id = ?", (int(r.id),))
                            calc.sync_sip_installments()
                            st.rerun()
                        if c[2].button("Delete", key=f"del{r.id}", width="stretch",
                                       help="Delete SIP (installments remain as manual transactions)"):
                            db.delete_sip(r.id)
                            st.rerun()

    with t3:
        if f.empty:
            st.info("No funds yet.")
        else:
            st.dataframe(f.drop(columns=["id"]), hide_index=True, width="stretch")
            names = {f"{r['name']} [{r.market}]": r.id for _, r in f.iterrows()}
            d = st.selectbox("Delete fund (removes its SIPs and transactions)", ["—"] + list(names))
            if d != "—" and st.button("Delete fund", type="secondary"):
                db.delete_fund(int(names[d]))
                st.rerun()


# ---------------- Transactions ----------------
def transactions_page():
    st.html(ui.page_header("Transactions", "Every purchase and redemption across your funds"))
    f = db.funds()
    if f.empty:
        st.info("Add a fund first.")
        return

    with st.expander("＋  Add lump sum, redemption or manual installment"):
        with st.form("add_txn", clear_on_submit=True):
            labels = {f"{r['name']} [{r.market}]": r for _, r in f.iterrows()}
            c = st.columns([3, 1, 1])
            fl = c[0].selectbox("Fund", list(labels))
            ttype = c[1].selectbox("Type", ["BUY", "SELL"])
            date = c[2].date_input("Date", value=dt.date.today(), min_value=dt.date(1990, 1, 1))
            c = st.columns(3)
            amount = c[0].number_input("Amount", min_value=0.0, step=100.0)
            nav = c[1].number_input("NAV (0 = auto from history)", min_value=0.0, format="%.4f")
            units = c[2].number_input("Units (0 = amount / NAV)", min_value=0.0, format="%.4f")
            note = st.text_input("Note")
            if st.form_submit_button("Add", type="primary"):
                fund = labels[fl]
                if not nav:
                    _, nav = prices.price_on_or_after(prices.history(prices.fund_key(fund.market, fund.code)), date)
                if not nav:
                    st.error("NAV not available for that date; enter it manually.")
                elif not amount and not units:
                    st.error("Enter amount or units.")
                else:
                    units = units or amount / nav
                    amount = amount or units * nav
                    db.add_txn(int(fund.id), date, ttype, amount, units, nav, note=note or None)
                    st.success("Added.")

    t = db.transactions()
    if t.empty:
        st.info("No transactions yet.")
        return
    c = st.columns(3)
    ff = c[0].multiselect("Filter funds", sorted(t.fund.unique()))
    if ff:
        t = t[t.fund.isin(ff)]
    view = t[["id", "date", "fund", "type", "amount", "units", "nav", "currency", "note"]].copy()
    view["date"] = pd.to_datetime(view["date"]).dt.date
    view.insert(0, "delete", False)
    st.caption("Edit cells to match your statement (e.g. units after stamp duty), tick rows to delete, then Save. "
               "Deleted SIP installments won't be regenerated.")
    edited = st.data_editor(
        view.sort_values("date", ascending=False),
        hide_index=True,
        width="stretch",
        disabled=["id", "fund", "currency"],
        column_config={
            "delete": st.column_config.CheckboxColumn("🗑"),
            "type": st.column_config.SelectboxColumn(options=["BUY", "SELL"]),
            "units": st.column_config.NumberColumn(format="%.4f"),
            "nav": st.column_config.NumberColumn(format="%.4f"),
            "amount": st.column_config.NumberColumn(format="%.2f"),
        },
        key="txn_editor",
    )
    if st.button("💾 Save changes", type="primary"):
        orig = view.set_index("id")
        dels = edited[edited.delete].id.tolist()
        changed = 0
        for _, r in edited[~edited.delete].iterrows():
            o = orig.loc[r.id]
            if any(str(o[k]) != str(r[k]) for k in ["date", "type", "amount", "units", "nav", "note"]):
                db.update_txn(int(r.id), r.date, r.type, r.amount, r.units, r.nav, r.note if pd.notna(r.note) else None)
                changed += 1
        if dels:
            db.delete_txns(dels)
        st.success(f"Updated {changed}, deleted {len(dels)}.")
        st.rerun()


# ---------------- Import / Export ----------------
IMPORT_COLS = ["market", "code", "fund_name", "date", "type", "amount", "units", "nav", "note"]


def io_page():
    st.html(ui.page_header("Import / Export", "Move data in and out as CSV"))
    c1, c2 = st.columns(2)
    with c1:
        st.html(ui.section("Export"))
        t = db.transactions()
        if not t.empty:
            f = db.funds().set_index("id")
            out = t.assign(code=t.fund_id.map(f.code), fund_name=t.fund)[IMPORT_COLS]
            st.download_button("⬇️ Transactions CSV", out.to_csv(index=False), "sip_transactions.csv", "text/csv")
        h, _ = calc.holdings(base)
        if not h.empty:
            st.download_button("⬇️ Holdings CSV", h.drop(columns=["fund_id"]).to_csv(index=False), "sip_holdings.csv", "text/csv")
        s = db.sips()
        if not s.empty:
            st.download_button("⬇️ SIPs CSV", s.drop(columns=["id", "fund_id"]).to_csv(index=False), "sip_schedules.csv", "text/csv")
        if t.empty:
            st.info("Nothing to export yet.")

    with c2:
        st.html(ui.section("Import transactions"))
        st.markdown(
            "CSV columns: `market` (IN/US), `code` (AMFI scheme code or ticker), `fund_name` (optional), "
            "`date` (YYYY-MM-DD), `type` (BUY/SELL), `amount`, `units` (optional), `nav` (optional), `note` (optional). "
            "Missing NAV is looked up from history; missing funds are created."
        )
        tmpl = pd.DataFrame(
            [["IN", "122639", "Parag Parikh Flexi Cap Fund - Direct Plan - Growth", "2024-01-05", "BUY", 5000, "", "", ""],
             ["US", "VTI", "Vanguard Total Stock Market ETF", "2024-01-05", "BUY", 200, "", "", ""]],
            columns=IMPORT_COLS,
        )
        st.download_button("Template CSV", tmpl.to_csv(index=False), "import_template.csv", "text/csv")
        up = st.file_uploader("Upload CSV", type="csv")
        if up is not None:
            df = pd.read_csv(io.BytesIO(up.getvalue()), dtype={"code": str})
            df.columns = [c.strip().lower() for c in df.columns]
            missing = {"market", "code", "date", "type", "amount"} - set(df.columns)
            if missing:
                st.error(f"Missing columns: {', '.join(sorted(missing))}")
                return
            st.dataframe(df.head(20), hide_index=True, width="stretch")
            if st.button(f"Import {len(df)} rows", type="primary"):
                ok, errs = 0, []
                for i, r in df.iterrows():
                    try:
                        ok += _import_row(r)
                    except Exception as e:
                        errs.append(f"Row {i + 2}: {e}")
                st.success(f"Imported {ok} row(s).")
                for e in errs[:20]:
                    st.warning(e)


def _import_row(r):
    market = str(r.market).strip().upper()
    if market not in ("IN", "US"):
        raise ValueError("market must be IN or US")
    code = str(r.code).strip().upper() if market == "US" else str(r.code).strip()
    f = db.funds()
    m = f[(f.market == market) & (f.code == code)]
    if m.empty:
        name = r.get("fund_name")
        if not isinstance(name, str) or not name.strip():
            name = code
        fund_id = db.add_fund(name.strip(), market, code, "INR" if market == "IN" else "USD")
    else:
        fund_id = int(m.iloc[0].id)
    date = pd.Timestamp(r.date).date()
    ttype = str(r.type).strip().upper()
    if ttype not in ("BUY", "SELL"):
        raise ValueError("type must be BUY or SELL")
    amount = float(r.amount) if pd.notna(r.get("amount")) and r.get("amount") != "" else 0.0
    units = float(r.units) if "units" in r and pd.notna(r.units) and r.units != "" else 0.0
    nav = float(r.nav) if "nav" in r and pd.notna(r.nav) and r.nav != "" else 0.0
    if not nav:
        _, nav = prices.price_on_or_after(prices.history(prices.fund_key(market, code)), date)
        if not nav:
            raise ValueError(f"no NAV available for {code} on {date}")
    units = units or amount / nav
    amount = amount or units * nav
    note = r.get("note") if isinstance(r.get("note"), str) else "import"
    db.add_txn(fund_id, date, ttype, amount, units, nav, note=note)
    return 1


{"Dashboard": dashboard, "Funds & SIPs": funds_page, "Transactions": transactions_page, "Import / Export": io_page}[page]()
