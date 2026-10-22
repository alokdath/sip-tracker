import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "data" / "sip_tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('IN', 'US')),
    code TEXT NOT NULL,              -- AMFI scheme code (IN) or ticker (US)
    currency TEXT NOT NULL CHECK (currency IN ('INR', 'USD')),
    UNIQUE (market, code)
);
CREATE TABLE IF NOT EXISTS sips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES funds(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('monthly', 'weekly', 'quarterly')),
    day INTEGER NOT NULL,            -- day of month (monthly/quarterly) or weekday 0=Mon (weekly)
    start_date TEXT NOT NULL,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES funds(id) ON DELETE CASCADE,
    sip_id INTEGER REFERENCES sips(id) ON DELETE SET NULL,
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('BUY', 'SELL')),
    amount REAL NOT NULL,            -- always positive, in fund currency
    units REAL NOT NULL,             -- always positive
    nav REAL NOT NULL,
    note TEXT,
    UNIQUE (sip_id, date)
);
CREATE TABLE IF NOT EXISTS sip_skips (       -- installments the user deleted; don't regenerate
    sip_id INTEGER NOT NULL REFERENCES sips(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    PRIMARY KEY (sip_id, date)
);
CREATE TABLE IF NOT EXISTS prices (
    code TEXT NOT NULL,              -- market:code, e.g. IN:122639, US:VTI, FX:USDINR
    date TEXT NOT NULL,
    price REAL NOT NULL,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS price_fetch_log (
    code TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(sips)")}
        if "amount_currency" not in cols:  # INR SIP into a USD fund, converted at each date's FX rate
            c.execute("ALTER TABLE sips ADD COLUMN amount_currency TEXT")
        if "fee_pct" not in cols:  # estimated brokerage + FX markup deducted before units are bought
            c.execute("ALTER TABLE sips ADD COLUMN fee_pct REAL NOT NULL DEFAULT 0")


def query_df(sql, params=()):
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def execute(sql, params=()):
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def executemany(sql, rows):
    with conn() as c:
        c.executemany(sql, rows)


# ---- funds ----
def add_fund(name, market, code, currency):
    return execute(
        "INSERT INTO funds (name, market, code, currency) VALUES (?, ?, ?, ?)",
        (name, market, str(code), currency),
    )


def funds():
    return query_df("SELECT * FROM funds ORDER BY market, name")


def delete_fund(fund_id):
    execute("DELETE FROM funds WHERE id = ?", (fund_id,))


# ---- sips ----
def add_sip(fund_id, amount, frequency, day, start_date, end_date=None, amount_currency=None, fee_pct=0.0):
    return execute(
        """INSERT INTO sips (fund_id, amount, frequency, day, start_date, end_date, amount_currency, fee_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (fund_id, amount, frequency, day, str(start_date), str(end_date) if end_date else None,
         amount_currency, fee_pct or 0.0),
    )


def sips():
    return query_df(
        """SELECT s.*, f.name AS fund, f.market, f.code, f.currency,
                  COALESCE(s.amount_currency, f.currency) AS sip_currency
           FROM sips s JOIN funds f ON f.id = s.fund_id ORDER BY f.name, s.start_date"""
    )


def set_sip_active(sip_id, active, end_date=None):
    execute(
        "UPDATE sips SET active = ?, end_date = COALESCE(?, end_date) WHERE id = ?",
        (int(active), str(end_date) if end_date else None, sip_id),
    )


def delete_sip(sip_id):
    execute("DELETE FROM sips WHERE id = ?", (sip_id,))


# ---- transactions ----
def add_txn(fund_id, date, ttype, amount, units, nav, sip_id=None, note=None):
    return execute(
        """INSERT OR IGNORE INTO transactions (fund_id, sip_id, date, type, amount, units, nav, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (fund_id, sip_id, str(date), ttype, abs(amount), abs(units), nav, note),
    )


def transactions():
    return query_df(
        """SELECT t.*, f.name AS fund, f.market, f.currency
           FROM transactions t JOIN funds f ON f.id = t.fund_id ORDER BY t.date, t.id"""
    )


def update_txn(txn_id, date, ttype, amount, units, nav, note):
    execute(
        "UPDATE transactions SET date=?, type=?, amount=?, units=?, nav=?, note=? WHERE id=?",
        (str(date), ttype, abs(amount), abs(units), nav, note, txn_id),
    )


def delete_txns(ids):
    with conn() as c:
        for i in ids:
            row = c.execute("SELECT sip_id, date FROM transactions WHERE id = ?", (int(i),)).fetchone()
            if row and row[0] is not None:
                c.execute("INSERT OR IGNORE INTO sip_skips (sip_id, date) VALUES (?, ?)", row)
            c.execute("DELETE FROM transactions WHERE id = ?", (int(i),))


def sip_skips(sip_id):
    df = query_df("SELECT date FROM sip_skips WHERE sip_id = ?", (sip_id,))
    return set(df["date"])


def sip_txn_dates(sip_id):
    df = query_df("SELECT date FROM transactions WHERE sip_id = ?", (sip_id,))
    return set(df["date"])


# ---- price cache ----
def save_prices(code, series):
    executemany(
        "INSERT OR REPLACE INTO prices (code, date, price) VALUES (?, ?, ?)",
        [(code, str(d), float(p)) for d, p in series.items()],
    )


def load_prices(code):
    df = query_df("SELECT date, price FROM prices WHERE code = ? ORDER BY date", (code,))
    if df.empty:
        return pd.Series(dtype=float)
    return pd.Series(df["price"].values, index=pd.to_datetime(df["date"]).dt.date)


def last_fetched(code):
    df = query_df("SELECT fetched_at FROM price_fetch_log WHERE code = ?", (code,))
    return None if df.empty else pd.Timestamp(df.iloc[0, 0])


def mark_fetched(code):
    execute(
        "INSERT OR REPLACE INTO price_fetch_log (code, fetched_at) VALUES (?, ?)",
        (code, pd.Timestamp.now().isoformat()),
    )
