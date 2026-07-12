#!/usr/bin/env python3
"""Fetch daily close series for the benchmark ETFs (SPY, QQQ, XBI, All-World).
Primary: Yahoo v8 chart (works from GitHub runners). Fallback: stooq CSV.
Keeps the old bench.json on total failure. Output: {SYM: [[date, close], ...]}."""
import json, os, subprocess, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "bench.json")
SYMS = {"SPY": "spy.us", "QQQ": "qqq.us", "XBI": "xbi.us", "VWCE.DE": "vwce.de"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
SINCE = "2021-12-30"

def yahoo(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d"
    r = subprocess.run(["curl", "-s", "-m", "25", "-H", f"User-Agent: {UA}", url],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    res = j["chart"]["result"][0]
    ts = res["timestamp"]; cl = res["indicators"]["quote"][0]["close"]
    out = []
    for t, c in zip(ts, cl):
        if c is None: continue
        d = datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        if d >= SINCE: out.append([d, round(c, 4)])
    return out

def stooq(code):
    url = f"https://stooq.com/q/d/l/?s={code}&i=d"
    r = subprocess.run(["curl", "-s", "-m", "25", "-H", f"User-Agent: {UA}", url],
                       capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5 and p[0] >= SINCE:
            try: out.append([p[0], round(float(p[4]), 4)])
            except ValueError: pass
    return out

def main():
    old = {}
    try: old = json.load(open(OUT))
    except Exception: pass
    res = {}
    for sym, code in SYMS.items():
        series = []
        for fn, arg in ((yahoo, sym), (stooq, code)):
            try:
                series = fn(arg)
                if len(series) > 200: break
            except Exception: series = []
        if len(series) > 200:
            res[sym] = series
        elif sym in old:
            res[sym] = old[sym]; print(f"bench: {sym} fetch failed -> alte Serie behalten")
        else:
            print(f"bench: {sym} FAILED (keine Daten)")
    json.dump(res, open(OUT, "w"))
    print("bench.json:", {k: len(v) for k, v in res.items()})

if __name__ == "__main__":
    main()
