#!/usr/bin/env python3
"""Brand colour per ticker, read out of the company's own logo.

The chips in News / Social / Catalysts should carry the company's colour, not a
colour invented from the ticker string. So we look at the logo pixels once, take
its dominant chromatic hue, and store two variants (light and dark theme) that are
forced to a readable lightness — a logo's own tone is often far too pale or too dark
to sit on a card as text.

Results are cached in logo_colors.json keyed by the logo source, so the minute loop
never re-downloads: only a NEW ticker (or a changed logo file) costs one request.
"""
import base64, colorsys, json, os, re, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "logo_colors.json")
LOGO_DIR = os.path.join(ROOT, "logos")

# a logo whose pixels are only black/white/grey (wordmarks, Uber-style marks) has no
# hue to borrow — those get the app's own ink-blue instead of a random tint
NEUTRAL = {"l": "hsl(215 30% 32%)", "d": "hsl(215 35% 74%)"}


def _load():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _from_svg(raw):
    """SVGs carry their colours as text — no rasterizer needed."""
    txt = raw.decode("utf-8", "replace")
    votes = {}
    for m in re.finditer(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", txt):
        votes[_hex_to_rgb(m.group(0))] = votes.get(_hex_to_rgb(m.group(0)), 0) + 1
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", txt):
        rgb = tuple(int(x) for x in m.groups())
        votes[rgb] = votes.get(rgb, 0) + 1
    return _pick([(rgb, n) for rgb, n in votes.items()])


def _from_raster(raw):
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im.thumbnail((48, 48))
    votes = {}
    for r, g, b, a in im.getdata():
        if a < 128:
            continue
        votes[(r, g, b)] = votes.get((r, g, b), 0) + 1
    return _pick(list(votes.items()))


def _pick(votes):
    """Winner = most 'present' hue: pixel count weighted by how colourful it is, so a
    large pale background never beats the small saturated mark that carries the brand."""
    if not votes:
        return None
    bins = {}
    for (r, g, b), n in votes:
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < 0.18 or l < 0.08 or l > 0.94:
            continue                       # greys, near-black, near-white: no usable hue
        key = int(h * 360) // 12           # 12° buckets: shades of one brand tone merge
        acc = bins.setdefault(key, [0.0, 0.0, 0.0])
        w = n * s
        acc[0] += w
        acc[1] += h * w
        acc[2] += s * w
    if not bins:
        return NEUTRAL
    best = max(bins.values(), key=lambda a: a[0])
    hue = (best[1] / best[0]) * 360
    sat = best[2] / best[0]
    lo = max(38, min(72, round(sat * 100)))          # light theme: dark text on a tint
    hi = max(45, min(85, round(sat * 100 * 1.1)))    # dark theme: bright text on a shade
    return {"l": f"hsl({hue:.0f} {lo}% 31%)", "d": f"hsl({hue:.0f} {hi}% 71%)"}


def _local(tk):
    sym = tk.split()[0].upper().replace(".", "_")
    for ext in ("png", "jpg", "jpeg", "svg", "webp"):
        f = os.path.join(LOGO_DIR, f"{sym}.{ext}")
        if os.path.exists(f) and os.path.getsize(f) > 200:
            return f, open(f, "rb").read()
    return None, None


def _fetch(url):
    if url.startswith("data:"):
        try:
            return base64.b64decode(url.split(",", 1)[1])
        except Exception:
            return None
    r = subprocess.run(["curl", "-sL", "-m", "12", url], capture_output=True)
    raw = r.stdout
    return raw if raw and len(raw) > 200 else None


def _extract(raw):
    if raw.lstrip()[:1] == b"<":
        return _from_svg(raw)
    try:
        return _from_raster(raw)
    except Exception:
        return None


def colors_for(tickers, candidates):
    """tickers -> {tk: {l,d}}. `candidates` returns the logo URL chain for a ticker.
    Cache key is the logo source, so replacing a logo file recolours that chip."""
    cache = _load()
    out, dirty = {}, False
    for tk in sorted({t for t in tickers if t}):
        path, raw = _local(tk)
        src = f"file:{os.path.basename(path)}:{len(raw)}" if path else (candidates(tk) or [""])[0]
        if not src:
            continue
        hit = cache.get(tk)
        if hit and hit.get("src") == src:
            if hit.get("l"):
                out[tk] = {"l": hit["l"], "d": hit["d"]}
            continue
        if raw is None:
            raw = _fetch(src)
        col = _extract(raw) if raw else None
        cache[tk] = {"src": src, **(col or {})}      # remember misses too: no retry storm
        dirty = True
        if col:
            out[tk] = col
    if dirty:
        json.dump(cache, open(CACHE, "w"), indent=1, sort_keys=True)
    return out


if __name__ == "__main__":
    import sys
    tks = sys.argv[1:] or [f.split(".")[0] for f in os.listdir(LOGO_DIR)]
    for tk, col in colors_for(tks, lambda t: []).items():
        print(f"{tk:6s} {col['l']:24s} {col['d']}")
