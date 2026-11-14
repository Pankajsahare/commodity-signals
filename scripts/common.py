# -*- coding: utf-8 -*-
# सगळ्या scripts साठी common helpers: HTTP, वेळ (IST), config, Yahoo chart.
import json, os, time, ssl, datetime, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
CTX = ssl.create_default_context()


def http_get(url, headers=None, timeout=25, retries=2, data=None):
    # छोट्या network glitch साठी 2 वेळा पुन्हा प्रयत्न
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def http_json(url, headers=None, timeout=25):
    return json.loads(http_get(url, headers, timeout).decode("utf-8", "ignore"))


def load_config():
    with open(os.path.join(ROOT, "config", "commodities.json"), encoding="utf-8") as f:
        return json.load(f)


def now_ist():
    return datetime.datetime.now(IST)


def yahoo_chart(sym, interval, rng):
    # Yahoo chart API (अनधिकृत) → [[ts, o, h, l, c, v], ...]
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=%s&range=%s" % (
        urllib.parse.quote(sym), interval, rng)
    res = http_json(url)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res.get("timestamp") or []):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append([t, o, h, l, c, q.get("volume", [0] * (i + 1))[i] or 0])
    return out, res["meta"]


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default
