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

WATCH_OUT = os.path.join(ROOT, "watch.json")
def watch_syms():
    try:
        return [s.strip().upper() for s in
                json.load(open(os.path.join(ROOT, "site_state.json"))).get("watchlist", []) if s.strip()]
    except Exception:
        return []

WATCH_META = os.path.join(ROOT, "watch_meta.json")
def _fast_meta(sym):
    """Fundamentals for the watchlist row (Seeking-Alpha-style columns)."""
    import yfinance as yf
    fi = yf.Ticker(sym).fast_info
    def g(k):
        try:
            v = fi[k]
            return round(float(v), 4) if v is not None else None
        except Exception:
            return None
    return {"mcap": g("market_cap"), "vol": g("last_volume"),
            "avgVol": g("three_month_average_volume"), "shares": g("shares"),
            "hi52": g("year_high"), "lo52": g("year_low")}

def fetch_watch(missing_only):
    """Watchlist quotes live in their own file so they never show up as benchmark chips."""
    old = {}
    try: old = json.load(open(WATCH_OUT))
    except Exception: pass
    meta = {}
    try: meta = json.load(open(WATCH_META))
    except Exception: pass
    want = watch_syms()
    syms = want
    if missing_only:
        syms = [s for s in want if len(old.get(s, [])) < 20]
        if not syms: return
    res = {k: v for k, v in old.items() if k in want}   # drop removed tickers
    meta = {k: v for k, v in meta.items() if k in want}
    for sym in syms:
        try: s = fetch(sym)
        except Exception: s = []
        if len(s) > 20: res[sym] = s
        elif sym in old and len(old[sym]) > 20: res[sym] = old[sym]
        else: print(f"watch: {sym} FAILED")
        try: meta[sym] = _fast_meta(sym)
        except Exception: pass
    json.dump(res, open(WATCH_OUT, "w"))
    json.dump(meta, open(WATCH_META, "w"))
    if res: print("watch.json:", {k: len(v) for k, v in res.items()})

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
    fetch_watch(os.environ.get("MISSING_ONLY") == "1")
