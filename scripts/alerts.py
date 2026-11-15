# -*- coding: utf-8 -*-
# Telegram कामं:
#   --alerts  : मजबूत signal (score ≥ 70, conf ≥ 4) आणि data बंद पडल्याचा health alert → तुझा private chat
#   --closing : रोजचा closing summary (फक्त भाव/OI, signals नाहीत) → public channel
#   --weekly  : journal मधून आठवड्याचा report (Google Sheet relay) → private chat
import argparse, datetime, json, os, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import IST, http_get, http_json, now_ist, read_json, write_json  # noqa: E402

STATE = "state/alerts.json"
SUMMARY = "_out/summary.json"


def tg(chat, text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok or not chat:
        print("Telegram skip (secret नाही)")
        return
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    http_get("https://api.telegram.org/bot%s/sendMessage" % tok, data=body, retries=1)


def fmt(v):
    return "—" if v is None else "{:,.2f}".format(v)


def alerts():
    s = read_json(SUMMARY)
    if not s:
        return
    st = read_json(STATE, {}) or {}
    sent = st.get("sent", {})
    now = now_ist()
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    msgs = []
    for r in s["rows"]:
        if r.get("nodata") or r["sig"] == "WAIT":
            continue
        tfs = [v for v in r["tf"].values() if v is not None]
        d = 1 if r["sig"] == "BUY" else -1
        if r["score"] >= 70 and r["conf"] >= 4 and r["reliab"] != "Low" and sum(1 for v in tfs if v == d) >= len(tfs) - 1:
            key = "%s:%s" % (r["id"], r["sig"])
            # एकाच signal चा alert दिवसातून एकदाच
            if sent.get(key) != now.date().isoformat():
                msgs.append("• %s %s @ %s %s | score %d | RSI %s | OI %s" % (
                    r["name"], r["sig"], fmt(r["price"]), r["unit"], r["score"], r.get("rsi"),
                    (r.get("oi") or {}).get("label", "—")))
                sent[key] = now.date().isoformat()
    if msgs:
        tg(chat, "🔔 Strong setups (personal use)\n" + "\n".join(msgs))
    # Health: market चालू असताना LIVE data 15 मिनिटांपेक्षा जुना
    if s["strip"].get("mcxOpen"):
        live = [r["fresh"]["ts"] for r in s["rows"] if (r.get("fresh") or {}).get("type") == "LIVE"]
        age = (now.timestamp() - max(live)) / 60 if live else 999
        if age > 15 and st.get("health") != now.strftime("%Y-%m-%dT%H"):
            tg(chat, "⚠️ Commodity desk: live data %d मिनिटांपासून update नाही. GitHub Actions तपास." % age)
            st["health"] = now.strftime("%Y-%m-%dT%H")
    st["sent"] = {k: v for k, v in sent.items() if v >= (now.date() - datetime.timedelta(days=3)).isoformat()}
    write_json(STATE, st)


def closing():
    s = read_json(SUMMARY)
    if not s:
        return
    by = {}
    for r in s["rows"]:
        if r.get("price") is not None:
            by.setdefault(r["sector"], []).append(r)
    lines = ["📊 Commodity Market Close — %s" % now_ist().strftime("%d %b %Y"), ""]
    for sec, rs in by.items():
        lines.append("▸ " + sec)
        for r in rs:
            ch = r.get("chgPct")
            oi = (r.get("oi") or {}).get("label")
            lines.append("  %s: %s %s (%s)%s" % (r["name"], fmt(r["price"]), r["unit"],
                                                 "—" if ch is None else "%+.2f%%" % ch, " · " + oi if oi else ""))
    ex = [e for e in s.get("expiries", []) if e["exp"] <= (now_ist().date() + datetime.timedelta(days=7)).isoformat()]
    if ex:
        lines += ["", "⏳ Expiries this week: " + ", ".join("%s %s" % (e["name"], e["exp"][5:]) for e in ex)]
    lines += ["", "Data: MCX/NCDEX bhavcopy & global futures. For information only, not a recommendation.",
              "https://www.advisor4u.in/"]
    tg(os.environ.get("TELEGRAM_CHANNEL_ID"), "\n".join(lines))


def weekly():
    url, tok = os.environ.get("MCX_RELAY_URL"), os.environ.get("RELAY_TOKEN", "")
    if not url:
        print("relay नाही — weekly skip")
        return
    js = http_json(url + "?" + urllib.parse.urlencode({"action": "journal", "token": tok}))
    if js.get("error"):
        print("relay error:", js["error"], "— Apps Script मधला RELAY_TOKEN आणि GitHub secret सारखे आहेत का तपास")
        return
    print("journal rows:", len(js.get("rows", [])))
    trades = js.get("rows", [])
    since = (now_ist() - datetime.timedelta(days=7)).date().isoformat()
    wk = [t for t in trades if str(t.get("exitDate", ""))[:10] >= since and t.get("pnl") not in (None, "")]
    if not wk:
        tg(os.environ.get("TELEGRAM_CHAT_ID"), "📒 Weekly journal: या आठवड्यात बंद झालेले trades नाहीत.")
        return
    pnl = [float(t["pnl"]) for t in wk]
    rs = [float(t["r"]) for t in wk if t.get("r") not in (None, "")]
    by = {}
    for t, p in zip(wk, pnl):
        by[t.get("commodity", "?")] = by.get(t.get("commodity", "?"), 0) + p
    worst = sorted(by.items(), key=lambda x: x[1])[:2]
    msg = ["📒 Weekly trading report",
           "Trades: %d | Win: %.0f%% | Net P&L: ₹%s" % (len(wk), sum(1 for p in pnl if p > 0) * 100 / len(wk), fmt(sum(pnl))),
           "Avg R: %s" % ("%.2f" % (sum(rs) / len(rs)) if rs else "—"),
           "सगळ्यात जास्त तोटा: " + ", ".join("%s ₹%s" % (k, fmt(v)) for k, v in worst)]
    reasons = {}
    for t in wk:
        if float(t["pnl"]) < 0 and t.get("mistake"):
            reasons[t["mistake"]] = reasons.get(t["mistake"], 0) + 1
    if reasons:
        msg.append("वारंवार चूक: " + ", ".join("%s (%d)" % kv for kv in sorted(reasons.items(), key=lambda x: -x[1])[:3]))
    tg(os.environ.get("TELEGRAM_CHAT_ID"), "\n".join(msg))


def check():
    # Bot चं नाव आणि channel मध्ये admin आहे का ते तपासतो (token print करत नाही)
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        print("TELEGRAM_BOT_TOKEN secret नाही")
        return
    api = "https://api.telegram.org/bot%s/" % tok
    me = http_json(api + "getMe")["result"]
    print("bot: @%s (id %s)" % (me["username"], me["id"]))
    # bot ला ज्यांनी message केला त्यांचे chat id (TELEGRAM_CHAT_ID भरण्यासाठी)
    try:
        ups = http_json(api + "getUpdates")["result"]
        seen = {}
        for u in ups:
            m = u.get("message") or u.get("channel_post") or {}
            c = m.get("chat") or {}
            if c:
                seen[c["id"]] = "%s %s" % (c.get("type"), c.get("username") or c.get("first_name") or c.get("title"))
        for k, v in seen.items():
            print("chat:", k, v)
    except Exception as e:  # noqa: BLE001
        print("getUpdates:", str(e)[:80])
    ch = os.environ.get("TELEGRAM_CHANNEL_ID")
    if ch:
        try:
            m = http_json(api + "getChatMember?" + urllib.parse.urlencode({"chat_id": ch, "user_id": me["id"]}))["result"]
            print("channel %s: status=%s can_post=%s" % (ch, m.get("status"), m.get("can_post_messages")))
        except Exception as e:  # noqa: BLE001
            body = e.read().decode()[:200] if hasattr(e, "read") else ""
            print("channel: not reachable (%s) %s — bot ला admin कर" % (str(e)[:60], body))
            print("channel id length:", len(ch), "starts:", ch[:4])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", action="store_true")
    ap.add_argument("--closing", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()
    if a.alerts:
        alerts()
    if a.closing:
        closing()
    if a.weekly:
        weekly()
