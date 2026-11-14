# -*- coding: utf-8 -*-
# रोजचा सारांश data.json मधून वाचून Telegram वर पाठवतो (signal fetch_data.py ने आधीच काढलेला असतो).
# Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (repo Secrets मध्ये — code मध्ये कधीच नाही).
import json, os, urllib.request, urllib.parse


def main():
    with open("data.json", encoding="utf-8") as f:
        data = json.load(f)
    lines = ["📊 Commodity Daily Summary", ""]
    for key, c in data.get("commodities", {}).items():
        s = c.get("signal") or {}
        if not c.get("price"):
            lines.append("• %s: no data" % c.get("name", key))
            continue
        pc = c.get("prevClose")
        chg = "%+.2f%%" % ((c["price"] - pc) / pc * 100) if pc else "n/a"
        bt = s.get("backtest") or {}
        bt_txt = ("5d backtest %s trades, win %s%%" % (bt["trades"], bt["winRate"])) if bt.get("trades") else "5d backtest: no trades"
        lines.append("• %s: %s | ₹%.2f %s (%s vs prev session) | RSI %s | %s | src %s" %
                     (c["name"].upper(), s.get("sig", "WAIT"), c["price"], c["unit"], chg,
                      s.get("rsi", "—"), bt_txt, c.get("source")))
    lines += ["", "⚠️ Personal decision-support only, not investment advice.",
              "Updated: %s" % data.get("updatedAt")]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    body = urllib.parse.urlencode({"chat_id": chat, "text": "\n".join(lines)}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=body)
    with urllib.request.urlopen(req, timeout=15) as r:
        print("Telegram send status:", r.status)


if __name__ == "__main__":
    main()
