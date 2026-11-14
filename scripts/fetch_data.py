# -*- coding: utf-8 -*-
# MCX commodities चे भाव fetch करून data.json तयार करतो (signal + backtest सकट).
# Sources (दोन्ही अनधिकृत — कधीही बदलू/बंद होऊ शकतात, म्हणून fallback chain):
#   (1) Yahoo Finance COMEX/NYMEX futures → ₹ मध्ये रूपांतर (मुख्य history)
#   (2) MCX website चा internal endpoint → मिळाला तर संपूर्ण history त्या भावाशी calibrate
import json, os, re, ssl, sys, urllib.request, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signals import analyse  # noqa: E402

# perUnit: Yahoo unit → आपला unit (troy ounce → gram = 31.1035)
# mcxDiv: MCX quote unit → आपला unit (Gold प्रति 10g, Silver प्रति kg)
# premium: MCX नसेल तेव्हा अंदाजे import duty (bullion ~6%); crude/NG ला duty नाही
# lots: MCX contracts (मोठ्यापासून लहान) — position size साठी
SYMBOLS = {
    "GOLD": {"name": "Gold", "yahoo": "GC=F", "mcx": "GOLD", "unit": "INR/g", "perUnit": 31.1035,
             "mcxDiv": 10, "premium": 1.06,
             "lots": [["Gold", 1000, "1 kg"], ["Gold Mini", 100, "100 g"], ["Gold Guinea", 8, "8 g"], ["Gold Petal", 1, "1 g"]]},
    "SILVER": {"name": "Silver", "yahoo": "SI=F", "mcx": "SILVER", "unit": "INR/g", "perUnit": 31.1035,
               "mcxDiv": 1000, "premium": 1.06,
               "lots": [["Silver", 30000, "30 kg"], ["Silver Mini", 5000, "5 kg"], ["Silver Micro", 1000, "1 kg"]]},
    "CRUDEOIL": {"name": "Crude Oil", "yahoo": "CL=F", "mcx": "CRUDEOIL", "unit": "INR/barrel", "perUnit": 1,
                 "mcxDiv": 1, "premium": 1.0,
                 "lots": [["Crude Oil", 100, "100 bbl"], ["Crude Oil Mini", 10, "10 bbl"]]},
    "NATGAS": {"name": "Natural Gas", "yahoo": "NG=F", "mcx": "NATURALGAS", "unit": "INR/mmBtu", "perUnit": 1,
               "mcxDiv": 1, "premium": 1.0,
               "lots": [["Natural Gas", 1250, "1,250 mmBtu"], ["Natural Gas Mini", 250, "250 mmBtu"]]},
}
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
CTX = ssl.create_default_context()
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
USDINR_DEFAULT = 94.0  # सगळे sources fail झाले तरच (वेळोवेळी update कर)


def http_json(url, data=None, timeout=15, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode())


def get_usdinr():
    # USD→INR: Yahoo → open.er-api.com → default
    try:
        d = http_json("https://query1.finance.yahoo.com/v8/finance/chart/INR=X?interval=1d&range=1d")
        return round(float(d["chart"]["result"][0]["meta"]["regularMarketPrice"]), 4), "yahoo"
    except Exception:
        pass
    try:
        d = http_json("https://open.er-api.com/v6/latest/USD")
        return round(float(d["rates"]["INR"]), 4), "er-api"
    except Exception:
        return USDINR_DEFAULT, "default"


def fetch_yahoo(sym):
    # 5-minute candles, 5 दिवसांची history
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=5m&range=5d" % sym
    res = http_json(url)["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    hist = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        hist.append([t, o, h, l, c])
    return float(res["meta"]["regularMarketPrice"]), hist


def fetch_mcx_spot():
    # MCX internal market-watch (best-effort). काहीही चुकलं तर {}.
    try:
        req = urllib.request.Request(
            "https://www.mcxindia.com/backpage.aspx/GetMarketWatch", data=b"{}",
            headers={**HEADERS, "Content-Type": "application/json; charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
            text = r.read().decode("utf-8", "ignore")
        out = {}
        for key, cfg in SYMBOLS.items():
            # नाव quotes मध्ये exact match → GOLDM/SILVERM सारखे mini contracts चुकून match होऊ नयेत
            m = re.search(r'"' + cfg["mcx"] + r'"' + r".{0,400}?\"(?:lastPrice|LastRate|LTP|last_rate)\"\s*:\s*\"?([0-9,.]+)\"?",
                          text, re.I | re.S)
            if m:
                out[key] = float(m.group(1).replace(",", "")) / cfg["mcxDiv"]
        return out
    except Exception:
        return {}


def prev_session_close(hist):
    # आजचं MCX session 09:00 IST ला सुरू होतं; त्याआधीची शेवटची close = मागचा close
    if not hist:
        return None
    last = datetime.datetime.fromtimestamp(hist[-1][0], IST)
    start = last.replace(hour=9, minute=0, second=0, microsecond=0)
    if last < start:
        start -= datetime.timedelta(days=1)
    cut = start.timestamp()
    prev = [r[4] for r in hist if r[0] < cut]
    return prev[-1] if prev else None


def main():
    usdinr, fx_src = get_usdinr()
    mcx = fetch_mcx_spot()
    out = {"updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "usdinr": usdinr, "usdinrSource": fx_src, "commodities": {}}
    for key, cfg in SYMBOLS.items():
        entry = {"name": cfg["name"], "unit": cfg["unit"], "lots": cfg["lots"],
                 "price": None, "prevClose": None, "history": [], "signal": None}
        try:
            price, hist = fetch_yahoo(cfg["yahoo"])
            base = usdinr / cfg["perUnit"]
            raw_last = price * base
            # Calibration: MCX भाव मिळाला आणि तो योग्य range मध्ये असेल तर संपूर्ण history त्याच प्रमाणात scale
            # (त्यामुळे chart मध्ये उडी येत नाही). नाहीतर अंदाजे duty premium.
            f, src = cfg["premium"], "comex-est" + ("+duty" if cfg["premium"] != 1 else "")
            if key in mcx and raw_last:
                ratio = mcx[key] / raw_last
                if 0.85 < ratio < 1.25:
                    f, src = ratio, "mcx-calibrated"
            m = base * f
            hist = [[t, round(o * m, 4), round(h * m, 4), round(l * m, 4), round(c * m, 4)]
                    for t, o, h, l, c in hist]
            entry["price"] = round(price * m, 4)
            entry["prevClose"] = prev_session_close(hist)
            entry["history"] = hist[-400:]  # dashboard साठी पुरेसे; file हलकी राहते
            entry["signal"] = analyse(hist, entry["price"])
        except Exception as e:
            src = "error:" + str(e)[:80]
        entry["source"] = src
        out["commodities"][key] = entry
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("data.json written:", {k: (v["price"], v["source"], (v["signal"] or {}).get("sig"))
                                 for k, v in out["commodities"].items()})


if __name__ == "__main__":
    main()
