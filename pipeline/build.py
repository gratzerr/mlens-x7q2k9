#!/usr/bin/env python3
"""Build the Portfolio Cockpit dashboard (single self-contained HTML).

Reads:
  portfolio.json      - snapshot from Parqet (value, gains, xirr, holdings)
  port_chart_ytd.json - YTD portfolio value time-series from Parqet
  research/<TICKER>.json - per-ticker news + catalysts + pulse (from research agents)

Writes:
  cockpit.html        - the dashboard (open directly or publish as Artifact)

Re-run daily after refreshing the source JSON to keep the dashboard current.
"""
import json, os, datetime, html

ROOT = os.path.dirname(os.path.abspath(__file__))

def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)

port = load("portfolio.json")
chart_ytd = load("port_chart_ytd.json")
try:
    pp = load("pp.json")
except Exception:
    pp = None

# Wire depot.xml-derived values (hourly-refreshed by pp_sync.py) into the snapshot:
# PP-exact returns (TTWROR/YTD/IZF - replaces ALL Parqet return figures),
# net cash (fully computed, EUR->USD) and the NVO option (Parqet doesn't track it).
if pp:
    try:
        fxr = list(load("fx_daily.json")["rates"].items())
        usd_per_eur = sorted(fxr)[-1][1]["USD"]
    except Exception:
        usd_per_eur = 1.14
    # PP-exact return engine values (verified vs PP app 2026-07-11)
    if pp.get("ttwrorSince2022") is not None:
        port["since2022"] = pp["ttwrorSince2022"]
    if pp.get("ttwrorYtd") is not None:
        port["ttwrorYtd"] = pp["ttwrorYtd"]
    if pp.get("izf") is not None:
        port["izf"] = pp["izf"]
    if pp.get("cashEur") is not None:
        cash_usd = round(pp["cashEur"] * usd_per_eur)
        port["cashValue"] = cash_usd
        for h in port["holdings"]:
            if h.get("assetType") == "cash":
                h["value"] = cash_usd
    nvo = next((x for x in pp.get("holdings", []) if "NVO" in (x.get("ticker") or "")), None)
    if nvo:
        for h in port["holdings"]:
            if h.get("assetType") == "option":
                h["price"] = nvo["price"]
                h["shares"] = nvo["shares"]
                h["value"] = round(nvo["shares"] * nvo["price"])
                if h.get("costPrice"):
                    h["unrealizedReturn"] = round((nvo["price"]/h["costPrice"]-1)*100, 1)
                    h["totalGainNet"] = round(h["value"] - nvo["shares"]*h["costPrice"])
    port["totalValue"] = sum(h["value"] for h in port["holdings"])

# ---- SEC CIK auto-resolution (so a NEWLY bought US ticker auto-gets instant SEC alerts) ----
def sec_cik_map(holdings):
    import subprocess, time
    f = os.path.join(ROOT, "sec_tickers.json")
    stale = (not os.path.exists(f)) or (time.time() - os.path.getmtime(f) > 7*86400)
    if stale:
        try:
            subprocess.run(["curl", "-s", "-m", "20", "-H",
                "User-Agent: PortfolioCockpit rafael.gratzer@gmail.com",
                "https://www.sec.gov/files/company_tickers.json", "-o", f], check=True)
            json.load(open(f))  # validate
        except Exception:
            pass
    try:
        raw = json.load(open(f))
    except Exception:
        return {}
    by_ticker = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in raw.values()}
    out = {}
    for h in holdings:
        if h.get("assetType") not in ("cash", "option"):
            cik = by_ticker.get((h["ticker"] or "").upper())
            if cik:
                out[h["ticker"]] = cik
    return out

sec_cik = sec_cik_map(port["holdings"])

research = {}
rdir = os.path.join(ROOT, "research")
for fn in os.listdir(rdir):
    if fn.endswith(".json"):
        r = json.load(open(os.path.join(rdir, fn), encoding="utf-8"))
        research[r["ticker"]] = r

# Live market data from Yahoo (fetched via browser). Map Yahoo symbol -> our ticker.
YMAP = {"PINK.V": "PINK"}
market = {}
ydir = os.path.join(ROOT, "yahoo")
if os.path.isdir(ydir):
    for fn in os.listdir(ydir):
        if fn.endswith(".json"):
            m = json.load(open(os.path.join(ydir, fn), encoding="utf-8"))
            tk = YMAP.get(m["symbol"], m["symbol"])
            market[tk] = m

# Yahoo symbol + news query per ticker (for the browser's live fetching)
YAHOO_SYM = {"PINK": "PINK.V"}
NEWS_QUERY = {
    "QURE": "uniQure", "WGS": "GeneDx", "CLPT": "ClearPoint Neuro",
    "NKTR": "Nektar Therapeutics", "DCTH": "Delcath", "NRXS": "Neuraxis",
    "PINK": "Perimeter Medical Imaging", "TENX": "Tenax Therapeutics",
}
# Currency of the live Yahoo quote (PINK.V trades in CAD; all others USD)
LIVE_CCY = {"PINK": "CAD"}

# ---- company logos: candidate URL chain per holding (client falls through on 404) ----
# FIRST choice: curated official logo from logos/<TICKER>.{png,jpg,svg} (scraped from the
# company's own website / TradingView), embedded as a data URI so it works everywhere
# (GitHub Pages AND the CSP-locked artifact). CDN chain only as fallback / for sold positions.
import base64
LOGO_DIR = os.path.join(ROOT, "logos")
def local_logo(tk):
    sym = tk.split()[0].upper().replace(".", "_")
    for ext in ("png", "jpg", "jpeg", "svg", "webp"):
        f = os.path.join(LOGO_DIR, f"{sym}.{ext}")
        if os.path.exists(f) and os.path.getsize(f) > 200:
            raw = open(f, "rb").read()
            mime = ("image/png" if raw[:4] == b"\x89PNG" else
                    "image/jpeg" if raw[:2] == b"\xff\xd8" else
                    "image/svg+xml" if raw.lstrip()[:1] == b"<" else "image/png")
            return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return None

# Parqet CDN covers nearly everything; overrides for the few it misses (micro caps).
LOGO_OVERRIDE = {
    "LXEO": ["https://www.lexeotx.com/wp-content/themes/lexeo/images/favicon.png"],
    "NRXS": ["https://www.google.com/s2/favicons?domain=neuraxis.com&sz=64"],
    "TENX": ["https://www.google.com/s2/favicons?domain=tenaxthera.com&sz=64"],   # Parqet logo is white-on-transparent (invisible)
    "NKTR": ["https://www.google.com/s2/favicons?domain=nektar.com&sz=64"],       # Parqet only has a generated "NE" letter tile
}
isin_by_ticker = {h["ticker"]: h["isin"] for h in (pp.get("holdings", []) if pp else [])
                  if h.get("isin")}
def logo_candidates(h):
    if h.get("assetType") == "cash":
        return []
    tk = h["ticker"]
    loc = local_logo(tk)
    if loc:
        return [loc]                        # curated official logo — no fallback needed
    if tk in LOGO_OVERRIDE:
        return LOGO_OVERRIDE[tk]
    out = []
    isin = isin_by_ticker.get(tk)
    if isin:
        out.append(f"https://assets.parqet.com/logos/isin/{isin}?format=png&size=64")
    sym = tk.split()[0].upper()            # "NVO $40C" -> NVO (option gets the Novo logo)
    out.append(f"https://assets.parqet.com/logos/symbol/{sym}?format=png&size=64")
    ir = (h.get("links") or {}).get("ir", "")
    if ir:
        dom = ir.split("//")[-1].split("/")[0]
        for pre in ("www.", "ir.", "investors.", "investor."):
            if dom.startswith(pre): dom = dom[len(pre):]
        out.append(f"https://www.google.com/s2/favicons?domain={dom}&sz=64")
    return out

# Attach research + market to each holding; compute allocation
total = port["totalValue"]
for h in port["holdings"]:
    h["alloc"] = round(100.0 * h["value"] / total, 1)
    h["logos"] = logo_candidates(h)
    if h["assetType"] != "cash":
        h["ySym"] = YAHOO_SYM.get(h["ticker"], h["ticker"])
        h["gquery"] = NEWS_QUERY.get(h["ticker"], h["name"])
        h["liveCcy"] = LIVE_CCY.get(h["ticker"], "USD")
    h["research"] = research.get(h["ticker"], {"news": [], "catalysts": [], "pulse": ""})
    m = market.get(h["ticker"])
    if m and m.get("price"):
        pc = m.get("prevClose") or m["price"]
        h["livePrice"] = m["price"]
        h["dayChange"] = round((m["price"] - pc) / pc * 100, 2) if pc else 0
        h["hi52"] = m.get("hi52"); h["lo52"] = m.get("lo52")
        h["spark"] = m.get("spark", [])
        if h.get("hi52") and h.get("lo52") and h["hi52"] > h["lo52"]:
            h["pos52"] = round((m["price"] - h["lo52"]) / (h["hi52"] - h["lo52"]) * 100, 1)

# Merge all upcoming catalysts across tickers for the timeline
merged = []
for h in port["holdings"]:
    for c in h["research"].get("catalysts", []):
        merged.append({**c, "ticker": h["ticker"]})

# Merge all news across tickers for the "Latest News" feed (newest first)
all_news = []
for h in port["holdings"]:
    for n in h["research"].get("news", []):
        all_news.append({**n, "ticker": h["ticker"]})
all_news.sort(key=lambda n: n.get("date", ""), reverse=True)

data = {
    "asOf": port["asOf"],
    "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "currency": port.get("currency", "EUR"),
    "portfolioId": port.get("portfolioId", "66e18c9426cf62020ccc7ee7"),
    "totalValue": total,
    "izf": port.get("izf", 0),
    "ttwror": port.get("ttwror", 0),
    "ttwrorYtd": port.get("ttwrorYtd", 0),
    "since2022": port.get("since2022"),
    "netGainUnrealized": port.get("netGainUnrealized", 0),
    "unrealizedReturn": port.get("unrealizedReturn", 0),
    "realizedAllTime": port.get("realizedAllTime", 0),
    # PP-exact capital gains (FIFO over depot.xml, USD at tx-date rates) — KPI tiles, not Parqet
    "ppRealizedUsd": pp.get("realizedUsd") if pp else None,
    "ppUnrealizedUsd": pp.get("unrealizedUsd") if pp else None,
    # PP net-worth curve (daily EUR value + cum TTWROR) — replaces Parqet's wrong chart
    "chartPP": pp.get("series", []) if pp else [],
    # every security ever traded (isin -> ticker/name) so sold positions render in Activities
    "secByIsin": {s["isin"]: {"tk": s["ticker"], "name": s["name"]}
                  for s in (pp.get("securities", []) if pp else [])},
    "isinByTicker": {h["ticker"]: h["isin"] for h in (pp.get("holdings", []) if pp else [])
                     if h.get("isin")},
    "cashValue": port["cashValue"],
    "cashPct": round(100.0 * port["cashValue"] / total, 1),
    "holdings": port["holdings"],
    "catalysts": merged,
    "latestNews": all_news,
    "pp": pp,
    "secCik": sec_cik,
    "social": (lambda: (json.load(open(os.path.join(ROOT, "social.json"), encoding="utf-8"))
                        if os.path.exists(os.path.join(ROOT, "social.json")) else {}))(),
}

DATA_JSON = json.dumps(data, ensure_ascii=True)

TEMPLATE = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
out = TEMPLATE.replace("/*__DATA__*/", DATA_JSON)
with open(os.path.join(ROOT, "cockpit.html"), "w", encoding="utf-8") as f:
    f.write(out)
print(f"Built cockpit.html  ({len(out):,} bytes)  as-of {data['asOf']}  holdings={len(data['holdings'])}")
