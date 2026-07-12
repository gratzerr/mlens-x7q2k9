#!/usr/bin/env python3
"""Fetch daily close series for the benchmark ETFs (SPY, QQQ, XBI, All-World).
Uses yfinance (handles Yahoo's cookie/crumb handshake — plain HTTP gets blocked).
Keeps the old bench.json entries on failure. Output: {SYM: [[date, close], ...]}."""
import json, os, warnings
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "bench.json")
BASE = ["SPY", "QQQ", "VWCE.DE"]
def all_syms():
    syms = list(BASE)
    try:
        extra = json.load(open(os.path.join(ROOT, "site_state.json"))).get("benchmarks", [])
        for s in extra:
            s = s.strip().upper()
            if s and s not in syms: syms.append(s)
    except Exception: pass
    return syms
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
    # MISSING_ONLY=1: fast path for the minute loop — only fetch symbols the
    # owner just added that have no series yet (new benchmark lands within a minute)
    missing_only = os.environ.get("MISSING_ONLY") == "1"
    syms = all_syms()
    if missing_only:
        syms = [s for s in syms if len(old.get(s, [])) < 20]
        if not syms:
            return
    res = dict(old) if missing_only else {}
    for sym in syms:
        try:
            s = fetch(sym)
        except Exception as e:
            s = []
        if len(s) > 20:  # >20 not >200: newly listed tickers have short histories
            res[sym] = s
        elif sym in old and len(old[sym]) > 20:
            res[sym] = old[sym]; print(f"bench: {sym} fetch failed -> alte Serie behalten")
        else:
            print(f"bench: {sym} FAILED")
    json.dump(res, open(OUT, "w"))
    print("bench.json:", {k: len(v) for k, v in res.items()})

if __name__ == "__main__":
    main()
