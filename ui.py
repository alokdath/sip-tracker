"""Presentation helpers: theme CSS, formatting and HTML components (rendered via st.html, so `$` is never parsed as LaTeX)."""
import html
import re

import pandas as pd

SYM = {"INR": "₹", "USD": "$"}
PALETTE = ["#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#64748B"]
CAT_COLORS = {
    "Large cap": "#4F46E5", "Mid cap": "#0EA5E9", "Small cap": "#8B5CF6", "Flexi cap": "#14B8A6",
    "International": "#EC4899", "US equity": "#F97316", "Gold": "#F59E0B", "Arbitrage": "#64748B", "Other": "#94A3B8",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp, .stMarkdown, button, input, select, textarea { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }
.stApp { background: #F6F7FB; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, .stDeployButton, [data-testid="stToolbarActions"] { visibility: hidden; }

/* sidebar */
section[data-testid="stSidebar"] { background: #0F172A; }
section[data-testid="stSidebar"] * { color: #CBD5E1; }
section[data-testid="stSidebar"] .brand { display:flex; align-items:center; gap:.6rem; margin:.2rem 0 1.4rem; }
section[data-testid="stSidebar"] .brand .logo { width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg,#6366F1,#8B5CF6); color:#fff; font-weight:800; font-size:1rem; }
section[data-testid="stSidebar"] .brand .name { font-weight:700; font-size:1.1rem; color:#F8FAFC; line-height:1.1; }
section[data-testid="stSidebar"] .brand .sub { font-size:.72rem; color:#64748B; }
section[data-testid="stSidebar"] .navlabel { font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#64748B; margin:.4rem 0 .3rem; }
section[data-testid="stSidebar"] .stElementContainer:has(.stRadio), section[data-testid="stSidebar"] .stRadio, section[data-testid="stSidebar"] [role="radiogroup"] { width:100%; }
section[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] [role="radiogroup"] label { padding:.55rem .75rem; border-radius:10px; width:100%; margin:0; transition: background .15s; }
section[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#1E293B; }
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:#1E293B; box-shadow: inset 3px 0 0 #818CF8; }
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color:#F8FAFC; font-weight:600; }
section[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display:none; }
section[data-testid="stSidebar"] [role="radiogroup"] label p { font-size:.92rem; }
section[data-testid="stSidebar"] .st-key-ccy [role="radiogroup"] { flex-direction:row; flex-wrap:nowrap; background:#1E293B; padding:4px; border-radius:12px; gap:4px; }
section[data-testid="stSidebar"] .st-key-ccy [role="radiogroup"] label { justify-content:center; padding:.4rem .5rem; flex:1; }
section[data-testid="stSidebar"] .st-key-ccy [role="radiogroup"] label:has(input:checked) { background:#6366F1; box-shadow:none; }
section[data-testid="stSidebar"] [role="radiogroup"] label { display:flex; }
section[data-testid="stSidebar"] .stButton button { background:#6366F1; border:0; color:#fff; border-radius:10px; font-weight:600; }
section[data-testid="stSidebar"] .stButton button:hover { background:#4F46E5; color:#fff; }
section[data-testid="stSidebar"] .stButton button p { color:#fff; }
section[data-testid="stSidebar"] .fxbox { margin-top:1rem; padding:.75rem .9rem; border-radius:12px; background:#1E293B; font-size:.8rem; }
section[data-testid="stSidebar"] .fxbox b { color:#F8FAFC; font-size:1rem; }

/* page header */
.ph { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:1.25rem; }
.ph h1 { font-size:1.75rem; font-weight:800; color:#0F172A; margin:0; padding:0; letter-spacing:-.02em; }
.ph .sub { color:#64748B; font-size:.9rem; margin-top:.25rem; }
.ph .tag { background:#EEF2FF; color:#4338CA; padding:.35rem .7rem; border-radius:999px; font-size:.78rem; font-weight:600; }

/* cards */
.grid { display:grid; gap:16px; }
.g-hero { grid-template-columns: 1.6fr 1fr 1fr 1fr 1fr; }
.g-2 { grid-template-columns: 1fr 1fr; }
@media (max-width: 1100px) { .g-hero { grid-template-columns: 1fr 1fr; } .g-hero .hero { grid-column: span 2; } .g-2 { grid-template-columns: 1fr; } }
.card { background:#fff; border:1px solid #E8EBF2; border-radius:16px; padding:18px 20px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.card .lbl { font-size:.75rem; font-weight:600; color:#64748B; text-transform:uppercase; letter-spacing:.06em; }
.card .val { font-size:1.55rem; font-weight:700; color:#0F172A; margin-top:.35rem; letter-spacing:-.02em; white-space:nowrap; }
.card .foot { font-size:.82rem; color:#64748B; margin-top:.35rem; }
.hero { background: linear-gradient(135deg,#4F46E5 0%,#7C3AED 60%,#9333EA 100%); border:0; color:#fff; position:relative; overflow:hidden; }
.hero:after { content:""; position:absolute; right:-60px; top:-60px; width:220px; height:220px; border-radius:50%; background:rgba(255,255,255,.08); }
.hero .lbl { color:rgba(255,255,255,.75); }
.hero .val { color:#fff; font-size:2.2rem; font-weight:800; }
.hero .foot { color:rgba(255,255,255,.85); }
.chip { display:inline-flex; align-items:center; gap:4px; padding:.18rem .55rem; border-radius:999px; font-size:.78rem; font-weight:600; white-space:nowrap; }
.up { background:#DCFCE7; color:#15803D; } .down { background:#FEE2E2; color:#B91C1C; } .flat { background:#F1F5F9; color:#475569; }
.hero .chip.up { background:rgba(220,252,231,.95); } .hero .chip.down { background:rgba(254,226,226,.95); }
.pos { color:#15803D; } .neg { color:#B91C1C; }

/* market cards */
.mkt { display:flex; flex-direction:column; gap:12px; }
.mkt .top { display:flex; justify-content:space-between; align-items:center; }
.mkt .flag { font-size:1.4rem; margin-right:.5rem; }
.mkt .ttl { font-weight:700; color:#0F172A; font-size:1rem; display:flex; align-items:center; }
.mkt .row { display:flex; gap:28px; }
.mkt .row div span { display:block; font-size:.72rem; color:#64748B; text-transform:uppercase; letter-spacing:.05em; font-weight:600; }
.mkt .row div b { font-size:1.15rem; color:#0F172A; font-weight:700; }
.bar { height:8px; background:#EEF2F7; border-radius:999px; overflow:hidden; }
.bar > i { display:block; height:100%; border-radius:999px; }

/* section titles */
.st { display:flex; align-items:center; justify-content:space-between; margin:1.8rem 0 .75rem; }
.st h3 { font-size:1.05rem; font-weight:700; color:#0F172A; margin:0; padding:0; }
.st .note { font-size:.8rem; color:#64748B; }

/* holdings table */
.tbl { width:100%; border-collapse:separate; border-spacing:0; background:#fff; border:1px solid #E8EBF2; border-radius:16px; overflow:hidden; }
.tbl th { background:#F8FAFC; color:#64748B; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; font-weight:600; text-align:right; padding:12px 16px; border-bottom:1px solid #E8EBF2; }
.tbl th:first-child, .tbl td:first-child { text-align:left; }
.tbl td { padding:14px 16px; border-bottom:1px solid #F1F5F9; text-align:right; font-size:.9rem; color:#0F172A; font-variant-numeric: tabular-nums; vertical-align:middle; }
.tbl tr:last-child td { border-bottom:0; }
.tbl tr:hover td { background:#FAFBFF; }
.tbl .fn { font-weight:600; color:#0F172A; }
.tbl .meta { font-size:.75rem; color:#94A3B8; margin-top:3px; display:flex; gap:6px; align-items:center; }
.tbl .sub { font-size:.75rem; color:#94A3B8; display:block; margin-top:2px; }
.tbl tfoot td { background:#F8FAFC; font-weight:700; }
.pill { display:inline-block; padding:.1rem .5rem; border-radius:6px; font-size:.68rem; font-weight:600; color:#fff; }
.alloc { display:flex; align-items:center; gap:8px; justify-content:flex-end; }
.alloc .bar { width:70px; }
.muted { color:#94A3B8; font-size:.8rem; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; }
.badge-sip { background:#EEF2FF; color:#4338CA; padding:.1rem .45rem; border-radius:6px; font-size:.68rem; font-weight:600; }
.badge-stop { background:#F1F5F9; color:#64748B; padding:.1rem .45rem; border-radius:6px; font-size:.68rem; font-weight:600; }

/* upcoming sips */
.ups { display:grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap:12px; }
.up-card { background:#fff; border:1px solid #E8EBF2; border-radius:14px; padding:14px 16px; display:flex; gap:14px; align-items:center; }
.cal { width:48px; min-width:48px; border-radius:10px; overflow:hidden; text-align:center; border:1px solid #E0E7FF; }
.cal .m { background:#6366F1; color:#fff; font-size:.65rem; font-weight:700; text-transform:uppercase; padding:2px 0; }
.cal .d { font-size:1.15rem; font-weight:800; color:#0F172A; padding:3px 0; }
.up-card .f { font-weight:600; font-size:.85rem; color:#0F172A; line-height:1.25; }
.up-card .a { font-size:.8rem; color:#64748B; margin-top:2px; }

/* sip cards (Funds & SIPs page) */
.sipc .f { font-weight:700; color:#0F172A; font-size:.95rem; }
.sipc .m { color:#64748B; font-size:.82rem; margin-top:3px; display:flex; gap:14px; flex-wrap:wrap; }
.sipc .m b { color:#0F172A; font-weight:600; }

/* streamlit widgets polish */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sipc) { background:#fff; border-radius:14px; border-color:#E8EBF2 !important; box-shadow:0 1px 2px rgba(16,24,40,.04); }
div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] { gap:.6rem; }
div[data-testid="stExpander"], div[data-testid="stForm"] { background:#fff; border:1px solid #E8EBF2 !important; border-radius:16px; }
.stTabs [data-baseweb="tab-list"] { gap:6px; border-bottom:1px solid #E8EBF2; }
.stTabs [data-baseweb="tab"] { padding:.5rem 1rem; border-radius:10px 10px 0 0; font-weight:600; }
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { border:1px solid #E8EBF2; border-radius:14px; overflow:hidden; background:#fff; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"], .stDownloadButton button { border-radius:10px; font-weight:600; }
.stButton button[kind="primary"], .stFormSubmitButton button { background:#4F46E5; border-color:#4F46E5; }
.js-plotly-plot .plotly .modebar { display:none !important; }
div[data-testid="stPlotlyChart"] { background:#fff; border:1px solid #E8EBF2; border-radius:16px; padding:8px 8px 0; }
</style>
"""

_PLAN_RE = re.compile(
    r"\s*[-–(]?\s*(direct|dir)\b.*$|\s*-\s*growth.*$|\s*\(erstwhile.*?\)", re.IGNORECASE
)


def short_name(name):
    s = _PLAN_RE.sub("", name).strip(" -")
    return s or name


def category(name, market):
    n = name.lower()
    if market == "US":
        return "US equity"
    for keys, cat in [
        (("arbitrage",), "Arbitrage"), (("gold",), "Gold"), (("small cap", "smallcap"), "Small cap"),
        (("midcap", "mid cap"), "Mid cap"), (("flexi",), "Flexi cap"),
        (("taiwan", "global", "nasdaq", "us equity", "international", "overseas"), "International"),
        (("large cap", "bluechip", "nifty 50", "sensex", "large & mid"), "Large cap"),
    ]:
        if any(k in n for k in keys):
            return cat
    return "Other"


def _indian_group(n):
    s = f"{abs(n):.0f}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(i - 2, 0):i] for i in range(len(head), 0, -2)][::-1])
        s = f"{head},{tail}"
    return s


def money(v, ccy, compact=False, decimals=None):
    if v is None or pd.isna(v):
        return "—"
    sym = "&#36;" if ccy == "USD" else "₹"
    sign = "−" if v < 0 else ""
    a = abs(v)
    if compact:
        if ccy == "INR":
            if a >= 1e7:
                return f"{sign}{sym}{a / 1e7:.2f} Cr"
            if a >= 1e5:
                return f"{sign}{sym}{a / 1e5:.2f} L"
        elif a >= 1e6:
            return f"{sign}{sym}{a / 1e6:.2f}M"
        elif a >= 1e4:
            return f"{sign}{sym}{a / 1e3:.1f}K"
    if decimals is None:
        decimals = 2 if a < 1000 else 0
    if ccy == "INR" and decimals == 0:
        return f"{sign}{sym}{_indian_group(a)}"
    return f"{sign}{sym}{a:,.{decimals}f}"


def plain_money(v, ccy):
    """For non-HTML widgets (st.button labels, st.success, etc.)."""
    return money(v, ccy).replace("&#36;", "\\$")


def pct(v, signed=True):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def chip(v, text=None):
    if v is None or pd.isna(v):
        return '<span class="chip flat">—</span>'
    cls = "up" if v > 0.005 else "down" if v < -0.005 else "flat"
    arrow = "▲" if cls == "up" else "▼" if cls == "down" else "•"
    return f'<span class="chip {cls}">{arrow} {text or pct(v)}</span>'


def signed_cls(v):
    return "" if v is None or pd.isna(v) else ("pos" if v > 0 else "neg" if v < 0 else "")


def esc(s):
    return html.escape(str(s))


def page_header(title, subtitle="", tag=""):
    t = f'<span class="tag">{tag}</span>' if tag else ""
    return f'<div class="ph"><div><h1>{esc(title)}</h1><div class="sub">{subtitle}</div></div>{t}</div>'


def section(title, note=""):
    return f'<div class="st"><h3>{esc(title)}</h3><span class="note">{note}</span></div>'


def plotly_layout(fig, height=360, title=None, legend=True):
    fig.update_layout(
        template="plotly_white",
        height=height,
        title=dict(text=f"<b>{title}</b>" if title else None, font=dict(size=14, color="#0F172A"), x=0.02, y=0.96),
        font=dict(family="Inter, system-ui, sans-serif", color="#475569", size=12),
        margin=dict(l=10, r=10, t=50 if title else 10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None, font=dict(size=11)),
        hoverlabel=dict(bgcolor="#0F172A", font_color="#fff", bordercolor="#0F172A", font_family="Inter"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#E2E8F0", title=None)
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, title=None)
    return fig
