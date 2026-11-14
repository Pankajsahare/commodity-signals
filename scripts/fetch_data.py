# -*- coding: utf-8 -*-
# MCX चे commodity भाव fetch करून data.json तयार करतो.
# Sources: (1) MCX चा internal endpoint (best-effort, unofficial), (2) Yahoo Finance fallback (unofficial).
# हे दोन्ही अनधिकृत आहेत — कधीही बदलू/बंद होऊ शकतात; त्यामुळे fallback chain ठेवली आहे.
import json, re, ssl, urllib.request, datetime

SYMBOLS = {
    "GOLD":     {"name": "Gold",        "yahoo": "GC=F", "mcx": "GOLD",       "unit": "INR/g",      "contractUnits": 1000},
    "SILVER":   {"name": "Silver",      "yahoo": "SI=F", "mcx": "SILVER",     "unit": "INR/g",      "contractUnits": 30000},
    "CRUDEOIL": {"name": "Crude Oil",   "yahoo": "CL=F", "mcx": "CRUDEOIL",   "unit": "INR/barrel", "contractUnits": 100},
    "NATGAS":   {"name": "Natural Gas", "yahoo": "NG=F", "mcx": "NATURALGAS", "unit": "INR/mmBtu",  "contractUnits": 1250},
}
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
CTX = ssl.create_default_context()

def http_json(url, data=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode())

def get_usdinr():
    # USD→INR rate (Yahoo, unofficial); fail झाल्यास अंदाजे default
    try:
        d = http_json("https://query1.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=1d")
        return round(float(d["chart"]["result"][0]["meta"]["regularMarketPrice"]), 4)
    except Exception:
        return 84.5

def fetch_yahoo(sym):
    # Yahoo chart API — 5-minute candles, 5 days history (unofficial)
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=5m&range=5d" % sym
    res = http_json(url)["chart"]["result"][0]
    meta = res["meta"]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    hist = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        hist.append([t, round(o, 4), round(h, 4), round(l, 4), round(c, 4)])
    return float(meta["regularMarketPrice"]), hist

def fetch_mcx_spot():
    # MCX website चा internal market-watch endpoint (best-effort, unofficial).
    # Response format बदलू शकतो — त्यामुळे lenient regex scan; काहीही चुकलं तर None.
    try:
        body = json.dumps({}).encode()
        req = urllib.request.Request(
            "https://www.mcxindia.com/backpage.aspx/GetMarketWatch",
            data=body, headers={**HEADERS, "Content-Type": "application/json; charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
            text = r.read().decode("utf-8", "ignore")
        out = {}
        for key, cfg in SYMBOLS.items():
            m = re.search(cfg["mcx"] + r".{0,400}?\"(?:lastPrice|LastRate|LTP|last_rate)\"\s*:\s*\"?([0-9,.]+)\"?", text, re.I | re.S)
            if m:
                out[key] = float(m.group(1).replace(",", ""))
        return out or None
    except Exception:
        return None

def main():
    usdinr = get_usdinr()
    mcx_spot = fetch_mcx_spot() or {}
    out = {"updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "usdinr": usdinr, "source": {}, "commodities": {}}
    for key, cfg in SYMBOLS.items():
        price, hist, src = None, [], "yahoo:" + cfg["yahoo"]
        try:
            price, hist = fetch_yahoo(cfg["yahoo"])
            # USD-quoted contracts → INR मध्ये रूपांतर (MCX INR मध्ये trade होतो)
            price = price * usdinr
            hist = [[t, round(o * usdinr, 4), round(h * usdinr, 4), round(l * usdinr, 4), round(c * usdinr, 4)]
                    for t, o, h, l, c in hist]
        except Exception as e:
            src = "error:" + str(e)[:80]
        # MCX चा actual spot मिळाला तर तोच वापर (अधिक अचूक)
        if key in mcx_spot:
            price = mcx_spot[key]
            src = "mcx-internal"
        if hist and price is not None:
            hist[-1][4] = round(price, 4)  # शेवटची candle current price ने update
        out["commodities"][key] = {"name": cfg["name"], "unit": cfg["unit"],
                                   "contractUnits": cfg["contractUnits"],
                                   "price": round(price, 4) if price is not None else None,
                                   "history": hist, "source": src}
        out["source"][key] = src
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("data.json written:", {k: v["price"] for k, v in out["commodities"].items()})

if __name__ == "__main__":
    main()
