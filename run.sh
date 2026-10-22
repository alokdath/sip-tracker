#!/usr/bin/env bash
# Start the SIP tracker at http://localhost:8501
set -e
umask 077
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port "${PORT:-8501}" --server.headless true --browser.gatherUsageStats false
