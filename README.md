# SIP Tracker (India + US mutual funds)

Local Streamlit app to track SIPs and lump sums across Indian mutual funds and US mutual funds/ETFs.

## Run

```bash
./run.sh        # opens on http://localhost:8501  (PORT=8600 ./run.sh to change)
```

The app listens on 127.0.0.1 only (no login), so it is not reachable from other devices.
Data lives in `data/sip_tracker.db` (SQLite, owner-only permissions). Back it up by copying that file.

## Features

- **Funds**: search Indian schemes by name (AMFI via [mfapi.in](https://www.mfapi.in)), add US funds/ETFs by ticker (Yahoo Finance via `yfinance`).
- **SIPs**: monthly / weekly / quarterly schedules with start and optional end date. US funds can take an INR
  amount (converted at each date's USD/INR rate) with an estimated cost % (brokerage + FX markup, INDmoney ≈ 1%). Past and new installments are
  logged automatically using the NAV of the SIP date (next trading day on holidays). Stop / resume / delete SIPs.
- **Transactions**: add lump sums or redemptions; edit units/NAV to match your statement; deleted SIP
  installments are remembered as skipped and not regenerated.
- **Dashboard**: value, invested, gain, return %, XIRR per fund and for the whole portfolio; India and US sections
  in native currency plus a combined total in INR or USD (USD/INR from Yahoo `USDINR=X`, using the rate on each
  cashflow date for combined XIRR); charts for value vs invested, value by fund, allocation, India vs US;
  upcoming installments.
- **Import / Export**: CSV of transactions, holdings and SIPs. Import columns:
  `market,code,fund_name,date,type,amount,units,nav,note` (`units`, `nav`, `fund_name`, `note` optional).

Prices are cached in SQLite and refreshed every 6 hours, or on demand via **Refresh NAVs & sync SIPs**.
Works offline from the cache if the APIs are unreachable.

## Notes

- Auto-logged units are `amount / NAV` and ignore stamp duty (0.005% in India) or exit loads; edit them if you need exact
  statement numbers.
- Redemptions reduce invested cost proportionally (average-cost method).
