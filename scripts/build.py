# -*- coding: utf-8 -*-
# Dashboard data तयार करतो: summary + प्रत्येक commodity ची detail (encrypt करून) + public snapshot (signals शिवाय).
# Input: hist/*.csv (EOD, eod.py) + Yahoo intraday/daily. Output: _site/desk/data/*.enc, _site/snapshot.json, _out/*.json
import argparse, base64, csv, datetime, json, os, statistics, sys
from collections import defaultdict
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import IST, load_config, now_ist, read_json, write_json, yahoo_chart  # noqa: E402
from signals import analyse, atr_series, ema_series, rsi_series  # noqa: E402

HIST = os.environ.get("HIST_DIR", "hist")
SITE, OUT = "_site", "_out"
NY = ZoneInfo("America/New_York")


# ---------- History (EOD) ----------
def load_hist(cid):
    # hist/<id>.csv → तारखेनुसार contracts; मग जास्त OI चा contract = active, roll वर back-adjust
    p = os.path.join(HIST, cid + ".csv")
    if not os.path.exists(p):
        return None
    days = defaultdict(dict)
    with open(p) as f:
        for r in csv.DictReader(f):
            days[r["date"]][r["exp"]] = [float(r[k]) for k in ("o", "h", "l", "c", "oi", "vol")]
    dates = sorted(days)
    rows, act = [], []
    for d in dates:
        cons = {e: v for e, v in days[d].items() if v[3] > 0}
        if not cons:
            continue
        live = {e: v for e, v in cons.items() if e >= d} or cons
        e = max(live, key=lambda k: (live[k][4], -int(k.replace("-", ""))))
        if live[e][4] == 0:
            e = min(live)  # OI नसेल तर सगळ्यात जवळचा expiry
        o, h, l, c, oi, vol = live[e]
        if o == 0 or h == 0 or l == 0:
            o = h = l = c
        rows.append([d, o, h, l, c, sum(v[4] for v in cons.values()), vol, e])
        act.append(e)
    # roll adjustment: active contract बदलला की आधीच्या सगळ्या भावांना ratio लावतो (chart मध्ये उडी नको)
    factor = 1.0
    adj = [r[:] for r in rows]
    for i in range(len(rows) - 1, 0, -1):
        if act[i] != act[i - 1]:
            prev = days[rows[i - 1][0]]
            if act[i] in prev and prev[act[i]][3] > 0 and rows[i - 1][4] > 0:
                factor *= prev[act[i]][3] / rows[i - 1][4]
        if factor != 1.0:
            for k in (1, 2, 3, 4):
                adj[i - 1][k] = rows[i - 1][k] * factor
    last_d = dates[-1] if dates else None
    contracts = sorted([[e] + v for e, v in days[last_d].items()]) if last_d else []
    return {"rows": adj, "raw": rows, "contracts": contracts, "lastDate": last_d}


def day_ts(d):
    return int(datetime.datetime.fromisoformat(d).replace(tzinfo=IST).timestamp())


def ydaily(res):
    # Yahoo daily: exchange च्या स्वतःच्या तारखेनुसार (gmtoffset) — आणि एकाच दिवसाच्या duplicate (live) ओळी काढून शेवटची ठेव
    rows, meta = res
    by = {}
    for r in rows:
        by[trade_date(r[0], meta)] = r
    return [[day_ts(d)] + by[d][1:] for d in sorted(by)]


def trade_date(t, meta):
    # Futures चा trading day: exchange वेळ + 6 तास (संध्याकाळी 6 ET ला पुढचा दिवस सुरू होतो)
    off = (meta or {}).get("gmtoffset", 0)
    return datetime.datetime.utcfromtimestamp(t + off + 6 * 3600).date().isoformat()


# ---------- Indicators ----------
def trend(candles):
    # +1 = वर, -1 = खाली, 0 = गोंधळ; None = पुरेसा data नाही
    closes = [c[4] for c in candles]
    if len(closes) < 50:
        return None
    e9, e21, e50 = (ema_series(closes, n)[-1] for n in (9, 21, 50))
    if e9 > e21 and closes[-1] > e50:
        return 1
    if e9 < e21 and closes[-1] < e50:
        return -1
    return 0


def resample(candles, sec):
    out = []
    for c in candles:
        b = c[0] - c[0] % sec
        if out and out[-1][0] == b:
            o = out[-1]
            o[2], o[3], o[4] = max(o[2], c[2]), min(o[3], c[3]), c[4]
            o[5] += c[5] if len(c) > 5 else 0
        else:
            out.append([b, c[1], c[2], c[3], c[4], c[5] if len(c) > 5 else 0])
    return out


def pivots(h, l, c):
    p = (h + l + c) / 3
    r = lambda v: round(v, 2)  # noqa: E731
    return {"P": r(p), "R1": r(2 * p - l), "S1": r(2 * p - h), "R2": r(p + h - l), "S2": r(p - (h - l)),
            "R3": r(h + 2 * (p - l)), "S3": r(l - 2 * (h - p)), "PDH": r(h), "PDL": r(l), "PDC": r(c)}


def oi_label(raw):
    # शेवटच्या 2 दिवसांचा भाव बदल + एकूण OI बदल → buildup चा अर्थ
    if not raw or len(raw) < 2:
        return None
    a, b = raw[-2], raw[-1]
    if a[5] <= 0:
        return None
    pc = (b[4] - a[4]) / a[4] * 100 if (a[7] == b[7] and a[4]) else None
    oc = (b[5] - a[5]) / a[5] * 100
    if pc is None:
        return {"label": "Rollover", "oiChg": round(oc, 1)}
    lab = ("Long buildup" if oc > 0 else "Short covering") if pc > 0 else ("Short buildup" if oc > 0 else "Long unwinding")
    return {"label": lab, "oiChg": round(oc, 1), "pxChg": round(pc, 2)}


def seasonality(daily_rows):
    # प्रत्येक महिन्याचा सरासरी % बदल (महिन्याचा शेवटचा close → पुढचा)
    last = {}
    for r in daily_rows:
        d = datetime.datetime.fromtimestamp(r[0], IST)
        last[(d.year, d.month)] = r[4]
    keys = sorted(last)
    rets = defaultdict(list)
    for i in range(1, len(keys)):
        rets[keys[i][1]].append((last[keys[i]] / last[keys[i - 1]] - 1) * 100)
    return [[m, round(statistics.mean(rets[m]), 2) if rets[m] else None, len(rets[m])] for m in range(1, 13)]


def reliability(bt):
    if not bt or not bt.get("trades"):
        return "n/a"
    if bt["trades"] >= 5 and bt["netR"] < 0:
        return "Low"
    if bt["trades"] >= 8 and bt["netR"] > 0 and (bt["winRate"] or 0) >= 38:
        return "High"
    return "Medium"


# ---------- Events / sessions ----------
def us_time_to_ist(d, hh, mm):
    return datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).astimezone(IST)


def build_events(now, expiries):
    ev = []
    for i in range(0, 8):
        d = (now + datetime.timedelta(days=i)).date()
        if d.weekday() == 2:
            ev.append({"t": us_time_to_ist(d, 10, 30).isoformat(), "title": "EIA Crude Inventory", "ids": ["CRUDEOIL"], "impact": "high"})
        if d.weekday() == 3:
            ev.append({"t": us_time_to_ist(d, 10, 30).isoformat(), "title": "EIA Natural Gas Storage", "ids": ["NATURALGAS"], "impact": "high"})
    for x in expiries:
        dd = datetime.date.fromisoformat(x["exp"])
        if 0 <= (dd - now.date()).days <= 7:
            ev.append({"t": datetime.datetime(dd.year, dd.month, dd.day, 17, 0, tzinfo=IST).isoformat(),
                       "title": "%s expiry (%s)" % (x["name"], x["exch"]), "ids": [x["id"]], "impact": "medium"})
    return sorted(ev, key=lambda e: e["t"])


def session_open(now, kind, holidays):
    # holidays = {तारीख: "full" | "morning" | "evening"}
    if now.weekday() >= 5:
        return False
    hol = holidays.get(now.date().isoformat()) if isinstance(holidays, dict) else None
    t = now.hour * 60 + now.minute
    morning = 9 * 60 <= t < 17 * 60
    if hol == "full" or (hol == "morning" and morning) or (hol == "evening" and not morning):
        return False
    if kind == "agri":
        return morning
    winter = datetime.datetime.now(NY).dst() == datetime.timedelta(0)
    return 9 * 60 <= t <= (23 * 60 + (55 if winter else 30))


# ---------- Score ----------
def score(row, events_today):
    d = {"BUY": 1, "SELL": -1}.get(row["sig"], 0)
    tfs = [v for v in row["tf"].values() if v is not None]
    if not d:
        return round(min(40, abs(sum(tfs)) / max(len(tfs), 1) * 40))
    s = (sum(1 for v in tfs if v == d) / max(len(tfs), 1)) * 40 + row["conf"] / 5 * 20
    oi = (row.get("oi") or {}).get("label")
    good = ("Long buildup", "Short covering") if d > 0 else ("Short buildup", "Long unwinding")
    s += 15 if oi in good else (7 if oi in (None, "Rollover") else 0)
    r = row.get("rsi") or 50
    s += 10 if (d > 0 and r < 65) or (d < 0 and r > 35) else 4
    s += {"High": 10, "Medium": 6, "n/a": 5, "Low": 0}[row["reliab"]]
    if row["id"] in events_today:
        s -= 10
    return max(0, min(100, round(s)))


# ---------- Encryption ----------
def encryptor(passphrase):
    # AES-256-GCM, key = PBKDF2-SHA256(passphrase, salt, 200k) — browser मध्ये WebCrypto ने उघडतो
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    salt = os.urandom(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000).derive(passphrase.encode())
    aes = AESGCM(key)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731

    def enc(obj):
        iv = os.urandom(12)
        ct = aes.encrypt(iv, json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode(), None)
        return {"v": 1, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}
    return enc


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plain", action="store_true", help="local test: encrypt न करता")
    args = ap.parse_args()
    cfg = load_config()
    now = now_ist()
    hol = {k: v for k, v in (cfg.get("holidays") or {}).items() if not k.startswith("_")}

    def safe(fn, *a):
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001
            print("  warn:", fn.__name__, a[:1], str(e)[:120])
            return None

    fx = safe(yahoo_chart, "INR=X", "1d", "2y")
    fx_map = {datetime.datetime.fromtimestamp(r[0], IST).date().isoformat(): r[4] for r in (ydaily(fx) if fx else [])}
    usdinr = fx[1]["regularMarketPrice"] if fx else (list(fx_map.values())[-1] if fx_map else 94.0)
    dxy = safe(yahoo_chart, "DX-Y.NYB", "1d", "5d")
    strip = {"usdinr": round(usdinr, 3), "dxy": round(dxy[1]["regularMarketPrice"], 2) if dxy else None}
    gs = {}

    # Angel One (MCX-only commodities चा intraday) — secrets असतील तरच
    ang, angel_tokens = None, read_json(os.path.join(HIST, "_angel_tokens.json"), {}) or {}
    try:
        import angel
        if angel.configured() and angel_tokens:
            ang = angel.Angel().login()
    except Exception as e:  # noqa: BLE001
        print("  warn: Angel login", str(e)[:120])

    rows, details, snap, expiries = [], {}, [], []
    for c in cfg["commodities"]:
        cid = c["id"]
        h = load_hist(cid)
        daily, intra5, fresh, factor, src, pub = [], [], None, None, [], None
        imeta = {"gmtoffset": 19800 - 6 * 3600}  # intraday trading-day: default IST तारीख (Angel/MCX)
        if h and h["rows"]:
            daily = [[day_ts(r[0]), r[1], r[2], r[3], r[4], r[6]] for r in h["rows"]]
            src.append("Angel One MCX EOD" if c["exch"] == "MCX" else c["exch"] + " bhavcopy")
            fresh = {"type": "EOD", "ts": day_ts(h["lastDate"]) + 17 * 3600}
            nx = [x for x in h["contracts"] if x[0] >= now.date().isoformat()]
            if nx:
                expiries.append({"id": cid, "name": c["name"], "exch": c["exch"], "exp": min(x[0] for x in nx)})
        if c.get("yahoo"):
            yd = safe(yahoo_chart, c["yahoo"], "1d", "2y")
            ymo = safe(yahoo_chart, c["yahoo"], "1mo", "10y")
            y5 = safe(yahoo_chart, c["yahoo"], "5m", "5d")
            if c["id"] in ("GOLD", "SILVER") and y5:
                gs[c["id"]] = y5[1]["regularMarketPrice"]
            if yd:
                conv = lambda t, v: v * c["conv"] * fx_map.get(  # noqa: E731
                    datetime.datetime.fromtimestamp(t, IST).date().isoformat(), usdinr)
                ydc = [[r[0], conv(r[0], r[1]), conv(r[0], r[2]), conv(r[0], r[3]), conv(r[0], r[4]), r[5]] for r in ydaily(yd)]
                factor = c.get("premium", 1.0)
                if h and h["rows"]:
                    # Calibration: MCX close / त्याच दिवशीचा Yahoo ₹ close
                    m = {datetime.datetime.fromtimestamp(r[0], IST).date().isoformat(): r[4] for r in ydc}
                    ld = h["lastDate"]
                    cand = [k for k in m if k <= ld]
                    if cand and m[max(cand)]:
                        f = h["raw"][-1][4] / m[max(cand)]
                        if 0.8 < f < 1.3:
                            factor = f
                if not daily or len(daily) < 220:
                    daily = [[r[0]] + [v * factor for v in r[1:5]] + [r[5]] for r in ydc]
                    src.append("Yahoo %s daily (₹, MCX-calibrated)" % c["yahoo"] if factor != c.get("premium", 1.0) else "Yahoo %s (₹ est.)" % c["yahoo"])
            if y5:
                imeta = y5[1]
                k = usdinr * c["conv"] * (factor or c.get("premium", 1.0))
                intra5 = [[r[0], r[1] * k, r[2] * k, r[3] * k, r[4] * k, r[5]] for r in y5[0]]
                if intra5:
                    fresh = {"type": "LIVE", "ts": intra5[-1][0]}
                    src.append("Yahoo intraday")
        if ang and angel_tokens.get(cid):
            # Active contract: जवळचा expiry; expiry 5 दिवसांत असेल तर पुढचा
            lst = angel_tokens[cid]
            act = lst[0]
            if len(lst) > 1 and (datetime.date.fromisoformat(act["exp"]) - now.date()).days <= 5:
                act = lst[1]
            try:
                a5 = ang.candles(act["token"], "FIVE_MINUTE", now - datetime.timedelta(days=6), now)
                if a5:
                    intra5, imeta = a5, {"gmtoffset": 19800 - 6 * 3600}
                    fresh = {"type": "LIVE", "ts": a5[-1][0]}
                    src = [x for x in src if x != "Yahoo intraday"] + ["Angel One MCX 5m %s" % act["exp"]]
            except Exception as e:  # noqa: BLE001
                print("  warn: Angel 5m", cid, str(e)[:100])
        if not daily:
            rows.append({"id": cid, "name": c["name"], "sector": c["sector"], "exch": c["exch"], "unit": c["unit"],
                         "price": None, "nodata": True, "note": "Waiting for Angel One data" if c["exch"] == "MCX" else "no data"})
            continue

        # आजची intraday candle daily मध्ये जोडतो (EOD येईपर्यंत Daily trend ताजा राहतो)
        prev_daily = daily[:]
        if intra5:
            last_d = datetime.datetime.fromtimestamp(daily[-1][0], IST).date().isoformat()
            today_c = [x for x in intra5 if trade_date(x[0], imeta) > last_d]
            if today_c:
                daily = daily + [[day_ts(trade_date(today_c[-1][0], imeta)),
                                  today_c[0][1], max(x[2] for x in today_c), min(x[3] for x in today_c), today_c[-1][4],
                                  sum(x[5] for x in today_c)]]
        price = intra5[-1][4] if intra5 else daily[-1][4]
        prev_close = prev_daily[-1][4] if len(daily) > len(prev_daily) else (prev_daily[-2][4] if len(prev_daily) > 1 else None)
        ref = prev_daily[-1] if len(daily) > len(prev_daily) else (prev_daily[-2] if len(prev_daily) > 1 else prev_daily[-1])
        h1 = resample(intra5, 3600) if intra5 else []
        m15 = resample(intra5, 900) if intra5 else []
        tf = {"D": trend(daily), "H1": trend(h1) if h1 else None, "M15": trend(m15) if m15 else None,
              "M5": trend(intra5) if intra5 else None}
        primary = intra5 if len(intra5) >= 220 else daily
        sig = analyse(primary, price) or {"sig": "WAIT", "conf": 0}
        dsig = analyse(daily, price) if primary is not daily else sig
        bt_d = (dsig or {}).get("backtest")
        bt_p = sig.get("backtest")
        rel = reliability(bt_p) if primary is daily else (
            "Low" if "Low" in (reliability(bt_p), reliability(bt_d)) else reliability(bt_d))
        atr = atr_series(daily)[-1] if len(daily) > 15 else None
        rsi_d = rsi_series([x[4] for x in daily])[-1] if len(daily) > 15 else None
        oi = oi_label(h["raw"]) if h else None
        season = seasonality(ymo[0] if (c.get("yahoo") and ymo) else daily)
        row = {"id": cid, "name": c["name"], "sector": c["sector"], "exch": c["exch"], "unit": c["unit"],
               "price": round(price, 2), "prevClose": round(prev_close, 2) if prev_close else None,
               "chgPct": round((price / prev_close - 1) * 100, 2) if prev_close else None,
               "tf": tf, "sig": sig["sig"], "conf": sig.get("conf", 0), "rsi": sig.get("rsi"),
               "primary": "5m" if primary is intra5 else "D", "oi": oi, "reliab": rel,
               "atrPct": round(atr / price * 100, 2) if atr else None, "pivot": pivots(ref[2], ref[3], ref[4])["P"],
               "fresh": fresh, "src": " + ".join(src), "verifyLot": c.get("verifyLot", False)}
        rows.append(row)
        # Public snapshot: फक्त NCDEX (official public bhavcopy). MCX भाव broker data / अंदाज → फक्त private desk
        if c["exch"] == "NCDEX":
            snap.append({k: row[k] for k in ("id", "name", "sector", "exch", "unit", "price", "chgPct", "fresh")})
        details[cid] = {"id": cid, "name": c["name"], "unit": c["unit"], "exch": c["exch"], "lots": c["lots"],
                        "marginPct": c["marginPct"], "tv": c.get("tv"), "verifyLot": c.get("verifyLot", False),
                        "signal": {k: v for k, v in sig.items() if k != "backtest"}, "dailyRsi": rsi_d,
                        "levels": pivots(ref[2], ref[3], ref[4]), "atr": round(atr, 2) if atr else None,
                        "daily": [[r[0]] + [round(v, 2) for v in r[1:5]] for r in daily[-150:]],
                        "intra": [[r[0]] + [round(v, 2) for v in r[1:5]] for r in intra5[-160:]],
                        "season": season, "bt": {"primary": bt_p, "daily": bt_d}, "oi": oi,
                        "oiHist": [[r[0], round(r[4], 2), r[5]] for r in (h["raw"][-20:] if h else [])],
                        "contracts": h["contracts"] if h else [], "src": row["src"]}

    # Basis (Agmarknet)
    basis = read_json(os.path.join(HIST, "basis.json"), {}) or {}
    for r in rows:
        b = basis.get(r["id"])
        if b and r.get("price"):
            details[r["id"]]["basis"] = dict(b, basisPct=round((r["price"] / b["spot"] - 1) * 100, 2))

    events = build_events(now, expiries)
    today_ids = {i for e in events if e["t"][:10] == now.date().isoformat() for i in e["ids"]}
    for r in rows:
        if not r.get("nodata"):
            r["score"] = score(r, today_ids)
    ranked = sorted([r for r in rows if not r.get("nodata") and r["sig"] != "WAIT"], key=lambda r: -r["score"])
    if "GOLD" in gs and "SILVER" in gs and gs["SILVER"]:
        strip["goldSilver"] = round(gs["GOLD"] / gs["SILVER"], 1)
    strip["mcxOpen"] = session_open(now, "intl", hol)
    strip["agriOpen"] = session_open(now, "agri", hol)
    summary = {"updatedAt": now.isoformat(), "strip": strip, "rows": rows,
               "top3": [r["id"] for r in ranked[:3]], "events": events,
               "expiries": sorted(expiries, key=lambda x: x["exp"])}

    write_json(os.path.join(OUT, "summary.json"), summary)
    write_json(os.path.join(SITE, "snapshot.json"),
               {"updatedAt": now.isoformat(), "usdinr": strip["usdinr"], "rows": snap,
                "expiries": [e for e in summary["expiries"] if e["exch"] == "NCDEX"]})
    pw = os.environ.get("DESK_PASSPHRASE")
    if args.plain:
        write_json(os.path.join(SITE, "desk", "data", "summary.json"), summary)
        for cid, d in details.items():
            write_json(os.path.join(SITE, "desk", "data", cid + ".json"), d)
    elif pw:
        enc = encryptor(pw)
        write_json(os.path.join(SITE, "desk", "data", "summary.enc"), enc(summary))
        for cid, d in details.items():
            write_json(os.path.join(SITE, "desk", "data", cid + ".enc"), enc(d))
    else:
        print("⚠️ DESK_PASSPHRASE secret नाही — private data publish केला नाही (फक्त public snapshot).")
    print("built:", len(rows), "rows; top3:", summary["top3"])
    # Diagnostics (भाव नाहीत — repo public आहे): data किती मिनिटं जुना
    ages = {r["id"]: round((now.timestamp() - r["fresh"]["ts"]) / 60) for r in rows
            if (r.get("fresh") or {}).get("type") == "LIVE"}
    print("live age (min):", ages, "| mcxOpen:", strip["mcxOpen"])


if __name__ == "__main__":
    main()
