# -*- coding: utf-8 -*-
# रोजचा सारांश data.json मधून वाचून Telegram वर पाठवतो.
# Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (repo Secrets मध्ये — code मध्ये कधीच नाही).
import json, os, urllib.request, urllib.parse

def ema(vals, n):
    if len(vals) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e

def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def signal(closes):
    e9, e21 = ema(closes, 9), ema(closes, 21)
    r = rsi(closes)
    if e9 is None or e21 is None or r is None:
        return "WAIT", r
    if e9 > e21 and r < 70:
        return "BUY", r
    if e9 < e21 and r > 30:
        return "SELL", r
    return "WAIT", r

def main():
    with open("data.json", encoding="utf-8") as f:
        data = json.load(f)
    lines = ["📊 Commodity Daily Summary", ""]
    for key, c in data.get("commodities", {}).items():
        closes = [row[4] for row in c.get("history", [])]
        if not closes or not c.get("price"):
            lines.append("• %s: no data" % c.get("name", key))
            continue
        sig, r = signal(closes)
        prev = closes[-2] if len(closes) > 1 else closes[-1]
        chg = (c["price"] - prev) / prev * 100 if prev else 0
        lines.append("• %s (%s): %s | ₹%.2f %s (%+.2f%%) | RSI %.1f" %
                     (c["name"].upper(), key, sig, c["price"], c["unit"], chg, r or 0))
    lines += ["", "⚠️ Decision-support only, not investment advice.",
              "Updated: %s" % data.get("updatedAt")]
    msg = "\n".join(lines)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    body = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=15) as r:
        print("Telegram send status:", r.status)

if __name__ == "__main__":
    main()
