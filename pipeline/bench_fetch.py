#!/usr/bin/env python3
"""Fetch daily close series for the benchmark ETFs (SPY, QQQ, XBI, All-World).
Uses yfinance (handles Yahoo's cookie/crumb handshake — plain HTTP gets blocked).
Keeps the old bench.json entries on failure. Output: {SYM: [[date, close], ...]}."""
import json, os, warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "bench.json")
SYMS = ["SPY", "QQQ", "XBI", "VWCE.DE"]
SINCE = "2021-12-30"

def fetch(sym):
    import yfinance as yf
    d = yf.download(sym, start=SINCE, interval="1d", progress=False, auto_adjust=True)
    out = []
    closes = d["Close"][sym] if hasattr(d["Close"], "columns") else d["Close"]
    for idx, c in closes.items():
        if c == c:  # not NaN
            out.append([idx.strftime("%Y-%m-%d"), round(float(c), 4)])
    return out

def main():
    old = {}
    try: old = json.load(open(OUT))
    except Exception: pass
    res = {}
    for sym in SYMS:
        try:
            s = fetch(sym)
        except Exception as e:
            s = []
        if len(s) > 200:
            res[sym] = s
        elif sym in old and len(old[sym]) > 200:
            res[sym] = old[sym]; print(f"bench: {sym} fetch failed -> alte Serie behalten")
        else:
            print(f"bench: {sym} FAILED")
    json.dump(res, open(OUT, "w"))
    print("bench.json:", {k: len(v) for k, v in res.items()})

if __name__ == "__main__":
    main()
