# -*- coding: utf-8 -*-
# रोजचा (End-of-Day) official data: NCDEX bhavcopy (थेट) + MCX bhavcopy (Google Apps Script relay मधून).
# प्रत्येक commodity साठी hist/<id>.csv मध्ये सगळ्या contracts च्या ओळी जोडतो (append-only → git हलका).
# वापर:  python scripts/eod.py                 → आजचा (किंवा शेवटचा) दिवस
#        python scripts/eod.py --backfill 500  → मागचे 500 कामाचे दिवस (एकदाच)
import argparse, csv, datetime, io, json, os, statistics, sys, time, urllib.parse, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import IST, http_get, http_json, load_config, now_ist  # noqa: E402

HIST = os.environ.get("HIST_DIR", "hist")
NCDEX_UDIFF_START = datetime.date(2024, 7, 8)  # याआधीचं format वेगळं आहे


def ncdex_day(d):
    # NCDEX zip मधली जुन्या-format ची CSV (FO_ddmmyy_FINAL.csv) वाचतो → {symbol: [contract rows]}
    url = ("https://www.ncdex.com/markets/bhavcopy?file_type_both=final&type_both=bhavcopy&bhavcopy_for=both"
           "&filedate_both=%s&format_both=csv_file" % d.isoformat())
    b = http_get(url, {"Referer": "https://www.ncdex.com/markets/bhavcopy"}, timeout=40)
    if b[:2] != b"PK":
        return None  # सुट्टी / file नाही
    z = zipfile.ZipFile(io.BytesIO(b))
    names = [n for n in z.namelist() if n.upper().startswith("FO_")]
    if not names:
        return None
    out = {}
    for r in csv.reader(io.TextIOWrapper(z.open(names[0]), encoding="utf-8", errors="ignore")):
        if len(r) < 18 or not r[0].startswith("FUT"):
            continue
        try:
            m, dd, yy = r[2].split("/")
            exp = "%s-%02d-%02d" % (yy, int(m), int(dd))
            o, h, l, c = (float(r[i] or 0) for i in (8, 9, 10, 11))
            out.setdefault(r[1].strip(), []).append([exp, o, h, l, c, float(r[16] or 0), float(r[12] or 0)])
        except ValueError:
            continue
    return out


MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def mcx_day(d):
    # MCX GitHub servers ला block करतो (403) — म्हणून Google Apps Script relay (relay/Code.gs)
    url, tok = os.environ.get("MCX_RELAY_URL"), os.environ.get("RELAY_TOKEN", "")
    if not url:
        return None
    q = urllib.parse.urlencode({"action": "mcx", "date": d.strftime("%d/%m/%Y"), "token": tok})
    js = http_json(url + "?" + q, timeout=60)
    if (js or {}).get("error"):
        raise RuntimeError("relay: %s" % js["error"])  # 403 इ. → तारीख "done" mark होत नाही
    rows = (js or {}).get("Data") or []
    if not rows:
        return None
    out = {}
    for r in rows:
        if r.get("InstrumentName", "FUTCOM") != "FUTCOM":
            continue
        e = r.get("ExpiryDate", "")
        try:
            exp = "%s-%02d-%s" % (e[5:9], MON[e[2:5]], e[0:2])
        except KeyError:
            continue
        out.setdefault(r["Symbol"].strip(), []).append(
            [exp, r["Open"], r["High"], r["Low"], r["Close"], r.get("OpenInterest", 0), r.get("Volume", 0)])
    return out


def done_dates(exch):
    p = os.path.join(HIST, "_dates_%s.txt" % exch)
    if not os.path.exists(p):
        return set()
    with open(p) as f:
        return set(x.strip() for x in f if x.strip())


def mark_done(exch, d, status):
    with open(os.path.join(HIST, "_dates_%s.txt" % exch), "a") as f:
        f.write("%s %s\n" % (d.isoformat(), status))


def append_rows(cid, d, contracts):
    p = os.path.join(HIST, cid + ".csv")
    new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "exp", "o", "h", "l", "c", "oi", "vol"])
        for c in sorted(contracts):
            w.writerow([d.isoformat()] + c)


def run_day(d, cfg, fetchers):
    for exch, fn in fetchers.items():
        done = {x.split()[0] for x in done_dates(exch)}
        if d.isoformat() in done:
            continue
        try:
            data = fn(d)
        except Exception as e:  # noqa: BLE001
            print("  %s %s error: %s" % (exch, d, str(e)[:120]))
            continue  # network error → पुढच्या run मध्ये पुन्हा प्रयत्न
        if data is None:
            # आजची file अजून publish झाली नसेल → mark करत नाही (पुढच्या run मध्ये पुन्हा)
            if d < now_ist().date() and (exch == "NCDEX" or os.environ.get("MCX_RELAY_URL")):
                mark_done(exch, d, "nodata")
            continue
        n = 0
        for c in cfg["commodities"]:
            if c["exch"] == exch and c["sym"] in data:
                append_rows(c["id"], d, data[c["sym"]])
                n += 1
        mark_done(exch, d, "ok")
        print("  %s %s: %d commodities" % (exch, d, n))


def angel_eod(cfg):
    # Angel One SmartAPI (तुझं broker account) मधून MCX-only commodities चा daily data → hist/<id>.csv
    import angel
    if not angel.configured():
        print("  Angel secrets नाहीत — MCX skip")
        return
    items = [c for c in cfg["commodities"] if c["exch"] == "MCX" and not c.get("yahoo")]
    a = angel.Angel().login()
    cons = angel.mcx_contracts([c["sym"] for c in items])
    now = now_ist()
    today = now.date()
    tokmap = {}
    for c in items:
        lst = cons.get(c["sym"], [])[:3]
        tokmap[c["id"]] = lst
        if not lst:
            print("  Angel: %s (%s) contract सापडला नाही" % (c["id"], c["sym"]))
            continue
        p = os.path.join(HIST, c["id"] + ".csv")
        have = set()
        if os.path.exists(p):
            with open(p) as f:
                have = {(r["date"], r["exp"]) for r in csv.DictReader(f)}
        try:
            q = a.quotes([x["token"] for x in lst])
        except Exception as e:  # noqa: BLE001
            q = {}
            print("  Angel quote %s: %s" % (c["id"], str(e)[:80]))
        added = 0
        for x in lst:
            try:
                cs = a.candles(x["token"], "ONE_DAY", now - datetime.timedelta(days=400), now)
            except Exception as e:  # noqa: BLE001
                print("  Angel candles %s %s: %s" % (c["id"], x["exp"], str(e)[:80]))
                continue
            done_days = [datetime.datetime.fromtimestamp(r[0], IST).date() for r in cs]
            last_day = max([d for d in done_days if d < today], default=None)
            for r, d in zip(cs, done_days):
                if d >= today or (d.isoformat(), x["exp"]) in have:
                    continue
                # OI फक्त market बंद असताना (रात्री 00:50 run) शेवटच्या दिवसासाठी बरोबर असतो
                oi = float((q.get(str(x["token"])) or {}).get("opnInterest") or 0) if (d == last_day and now.hour < 9) else 0
                append_rows(c["id"], d, [[x["exp"], r[1], r[2], r[3], r[4], oi, r[5]]])
                have.add((d.isoformat(), x["exp"]))
                added += 1
        print("  Angel %s: +%d rows" % (c["id"], added))
    with open(os.path.join(HIST, "_angel_tokens.json"), "w") as f:
        json.dump(tokmap, f)


def agmark_basis(cfg):
    # data.gov.in (Agmarknet, official) mandi भाव → futures शी तुलना (basis). API key नसेल तर skip.
    key = os.environ.get("DATA_GOV_API_KEY")
    if not key:
        return
    out = {}
    for c in cfg["commodities"]:
        ag = c.get("agmark")
        if not ag:
            continue
        try:
            q = urllib.parse.urlencode({"api-key": key, "format": "json", "limit": 1000,
                                        "filters[commodity]": ag["name"]})
            recs = json.loads(http_get("https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?" + q,
                                       timeout=15, retries=0).decode()).get("records", [])
            prices = [float(r["modal_price"]) / ag["div"] for r in recs if r.get("modal_price")]
            if prices:
                out[c["id"]] = {"spot": round(statistics.median(prices), 2), "n": len(prices),
                                "date": max(r.get("arrival_date", "") for r in recs)}
        except Exception as e:  # noqa: BLE001
            # data.gov.in GitHub (परदेशी) servers ना अडवतो — एकदा fail झालं की बाकीचे पण होतील, म्हणून थांब
            print("  agmark %s: %s — बाकी skip" % (c["id"], str(e)[:100]))
            break
    if out:
        with open(os.path.join(HIST, "basis.json"), "w") as f:
            json.dump(out, f)
        print("  basis:", len(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(HIST, exist_ok=True)
    cfg = load_config()
    today = now_ist().date()
    # MCX bhavcopy cloud servers ना block → MCX-only commodities Angel One API मधून (angel_eod)
    fetchers = {"NCDEX": ncdex_day}
    if args.backfill:
        d, days = today, []
        while len(days) < args.backfill:
            d -= datetime.timedelta(days=1)
            if d.weekday() < 5:
                days.append(d)
        for d in reversed(days):
            if d < NCDEX_UDIFF_START:
                continue
            run_day(d, cfg, fetchers)
            time.sleep(0.4)  # exchange servers वर ताण नको
    # आज + मागचे 10 कामाचे दिवस (PC उशिरा चालू झाला तरी MCX data भरून निघतो)
    for back in range(14, -1, -1):
        d = today - datetime.timedelta(days=back)
        if d.weekday() < 5:
            run_day(d, cfg, fetchers)
    try:
        angel_eod(cfg)
    except Exception as e:  # noqa: BLE001
        print("  Angel EOD error:", str(e)[:150])
    agmark_basis(cfg)


if __name__ == "__main__":
    main()
