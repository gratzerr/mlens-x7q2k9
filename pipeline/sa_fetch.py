#!/usr/bin/env python3
"""Multi-year analyst estimates via RapidAPI "Seeking Alpha Finance" (Tipsters).
Writes sa_estimates.json {TK:{eps:[[label,est,yoyPct,None,low,high,n]],rev:[...]},_ts}.

Call discipline (Basic plan = 500 req/month HARD limit):
  - weekly full refresh of holdings+watchlist+saReq (7d gate via in-file _ts)
  - tickers missing from the file are fetched any cycle (on-demand research adds)
  - sa_budget.json counts every HTTP call; hard stop at MAX_CALLS_PER_MONTH
Without RAPIDAPI_KEY in the env the script exits silently (seed data stays)."""
import json, os, time, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "sa_estimates.json")
IDS = os.path.join(ROOT, "sa_ids.json")          # SYM -> SA ticker_id (static, cached forever)
BUDGET = os.path.join(ROOT, "sa_budget.json")    # {"month":"YYYY-MM","used":N}
DEBUG_RAW = os.path.join(ROOT, "sa_api_raw.json")  # last unparseable payload, for diagnosis
HOST = "seeking-alpha-finance.p.rapidapi.com"
MAX_CALLS_PER_MONTH = 400                        # head-room under the 500 hard limit
REFRESH_DAYS = 7
ALIAS = {"PINK.V": "PYNKF"}                      # portfolio symbol -> SA symbol

def _budget_left():
    m = datetime.datetime.utcnow().strftime("%Y-%m")
    b = {"month": m, "used": 0}
    try:
        j = json.load(open(BUDGET))
        if j.get("month") == m: b = j
    except Exception: pass
    return b, MAX_CALLS_PER_MONTH - b.get("used", 0)

def _spend(b, n=1):
    b["used"] = b.get("used", 0) + n
    json.dump(b, open(BUDGET, "w"))

def _get(path, params, key):
    import requests
    r = requests.get(f"https://{HOST}{path}", params=params, timeout=20,
                     headers={"x-rapidapi-host": HOST, "x-rapidapi-key": key})
    r.raise_for_status()
    return r.json()

def wanted():
    out = []
    try:
        for h in json.load(open(os.path.join(ROOT, "pp.json"))).get("holdings", []):
            tk = (h.get("ticker") or "").strip().upper()
            if tk and len(tk) <= 10 and tk not in out: out.append(tk)
    except Exception: pass
    try:
        st = json.load(open(os.path.join(ROOT, "site_state.json")))
        for s in st.get("watchlist", []) + st.get("saReq", []):
            s = s.strip().upper()
            if s and len(s) <= 10 and s not in out: out.append(s)
    except Exception: pass
    return out

def ticker_id(sym, ids, b, key):
    if sym in ids: return ids[sym]
    _, left = _budget_left()
    j = _get("/v1/search/searches", {"query": sym}, key); _spend(b)
    # scan the payload for a symbol entry matching `sym` with a numeric id
    def scan(o):
        if isinstance(o, dict):
            name = str(o.get("name") or o.get("slug") or o.get("symbol") or "").upper()
            oid = o.get("id")
            typ = str(o.get("type") or "").lower()
            if name == sym.upper() and oid is not None and ("symbol" in typ or "ticker" in typ or typ == ""):
                try: return int(oid)
                except (TypeError, ValueError): pass
            for v in o.values():
                r = scan(v)
                if r: return r
        elif isinstance(o, list):
            for v in o:
                r = scan(v)
                if r: return r
        return None
    tid = scan(j)
    if tid:
        ids[sym] = tid
        json.dump(ids, open(IDS, "w"))
    else:
        print(f"sa_fetch: no ticker_id for {sym}")
    return tid

def parse_estimates(j):
    """Shape-tolerant: collect (metric, fiscalyear, value) from nested payloads where
    leaf objects carry a period/fiscalyear plus a data item value."""
    rows = {}   # (metric, year) -> value
    def leaf_val(o):
        for k in ("dataitemvalue", "value", "actual", "consensus"):
            if k in o and isinstance(o[k], (int, float, str)):
                try: return float(o[k])
                except (TypeError, ValueError): return None
        return None
    def year_of(o):
        p = o.get("period") if isinstance(o.get("period"), dict) else o
        for k in ("fiscalyear", "fiscal_year", "calendaryear", "year"):
            y = p.get(k)
            try:
                y = int(y)
                if 2000 < y < 2100: return y
            except (TypeError, ValueError): pass
        return None
    def ptype_ok(o):
        p = o.get("period") if isinstance(o.get("period"), dict) else o
        t = str(p.get("periodtypeid") or p.get("period_type") or "").lower()
        return (not t) or ("annual" in t) or (t == "fy")
    def walk(o, metric):
        if isinstance(o, dict):
            y, v = year_of(o), leaf_val(o)
            if y and v is not None and ptype_ok(o):
                rows.setdefault((metric, y), v)
                return
            for k, v2 in o.items():
                nk = metric if (str(k).lstrip("-").isdigit() or k in ("period", "data", "attributes", "estimates")) else str(k)
                walk(v2, nk)
        elif isinstance(o, list):
            for v2 in o: walk(v2, metric)
    walk(j, "")
    def series(*pats):
        out = {}
        for (m, y), v in rows.items():
            ml = m.lower()
            if any(p in ml for p in pats): out[y] = v
        return out
    def table(mean, low, high, num):
        years = sorted(mean)
        t, prev = [], None
        for y in years:
            est = mean[y]
            yoy = None
            if prev not in (None, 0): yoy = round((est / prev - 1) * 100, 2)
            prev = est
            n = num.get(y)
            t.append(["Dec %d" % y, est, yoy, None, low.get(y), high.get(y),
                      int(n) if n is not None else None])
        return t
    eps = table(series("eps_normalized_consensus_mean", "eps_consensus_mean", "eps_mean"),
                series("eps_normalized_consensus_low", "eps_consensus_low", "eps_low"),
                series("eps_normalized_consensus_high", "eps_consensus_high", "eps_high"),
                series("eps_normalized_num_of_estimates", "eps_num"))
    rev = table(series("revenue_consensus_mean", "revenue_mean"),
                series("revenue_consensus_low", "revenue_low"),
                series("revenue_consensus_high", "revenue_high"),
                series("revenue_num_of_estimates", "revenue_num"))
    return eps, rev

def main():
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not key: return
    cur = {}
    try: cur = json.load(open(OUT))
    except Exception: pass
    want = wanted()
    ts = cur.get("_ts", 0)
    stale = time.time() - ts > REFRESH_DAYS * 86400
    todo = want if stale else [t for t in want if t not in cur]
    if not todo: return
    b, left = _budget_left()
    if left <= 2:
        print("sa_fetch: monthly call budget exhausted — skipping"); return
    ids = {}
    try: ids = json.load(open(IDS))
    except Exception: pass
    changed = False
    for tk in todo:
        b, left = _budget_left()
        if left <= 2: print("sa_fetch: budget stop"); break
        sa_sym = ALIAS.get(tk, tk)
        try:
            tid = ticker_id(sa_sym, ids, b, key)
            if not tid: continue
            j = _get("/v1/symbols/estimated/estimates",
                     {"estimates_type": "symbol_summary", "ticker_id": tid}, key); _spend(b)
            eps, rev = parse_estimates(j)
            if eps or rev:
                cur[tk] = {"eps": eps, "rev": rev}
                if tk in ALIAS: cur[ALIAS[tk]] = cur[tk]
                changed = True
                print(f"sa_fetch: {tk} eps={len(eps)} rev={len(rev)}")
            else:
                json.dump({tk: j}, open(DEBUG_RAW, "w"))
                print(f"sa_fetch: {tk} UNPARSEABLE payload -> sa_api_raw.json (old data kept)")
        except Exception as e:
            print(f"sa_fetch: {tk} failed: {e}")
        time.sleep(0.3)   # stay under 5 req/s
    if changed or stale:
        cur["_ts"] = int(time.time())
        json.dump(cur, open(OUT, "w"), separators=(",", ":"))
        print(f"sa_estimates.json: {len([k for k in cur if not k.startswith('_')])} tickers")

if __name__ == "__main__":
    main()
