# -*- coding: utf-8 -*-
# Signal logic एकाच ठिकाणी — fetch_data.py (dashboard साठी) आणि telegram_summary.py दोघेही हेच वापरतात.
# Rule: EMA 9/21 crossover + RSI 14 + EMA 200 trend filter; SL = 1.5×ATR, Target = 3×ATR.


def ema_series(vals, n):
    # प्रत्येक candle वरचा EMA (पहिल्या n-1 जागी None)
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_series(closes, n=14):
    # Wilder RSI, प्रत्येक candle साठी
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    ag, al = g / n, l / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr_series(hist, n=14):
    # Average True Range (साधी सरासरी, मागच्या n candles ची)
    out = [None] * len(hist)
    trs = [None]
    for i in range(1, len(hist)):
        hi, lo, pc = hist[i][2], hist[i][3], hist[i - 1][4]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    for i in range(n, len(hist)):
        out[i] = sum(trs[i - n + 1:i + 1]) / n
    return out


def classify(close, e9, e21, e200, r):
    # एका candle साठी BUY/SELL/WAIT + confidence (1-5)
    if None in (e9, e21, e200, r):
        return "WAIT", 0
    up = e9 > e21
    if up and r < 70 and close > e200:
        conf = 4 if r > 55 else 3
        if r > 60 and e9 > e21 * 1.002:
            conf = 5
        return "BUY", conf
    if (not up) and r > 30 and close < e200:
        conf = 4 if r < 45 else 3
        if r < 40 and e9 < e21 * 0.998:
            conf = 5
        return "SELL", conf
    return "WAIT", 1


def analyse(hist, price=None):
    # शेवटच्या candle वरचा signal + backtest एकत्र
    closes = [r[4] for r in hist]
    e9, e21, e200 = ema_series(closes, 9), ema_series(closes, 21), ema_series(closes, 200)
    rs, at = rsi_series(closes), atr_series(hist)
    if not closes:
        return None
    i = len(closes) - 1
    sig, conf = classify(closes[i], e9[i], e21[i], e200[i], rs[i])
    if e200[i] is None or at[i] is None:
        return {"sig": "WAIT", "conf": 0, "note": "not enough history"}
    entry = price if price is not None else closes[i]
    a = at[i]
    sl = entry - 1.5 * a if sig == "BUY" else (entry + 1.5 * a if sig == "SELL" else None)
    tgt = entry + 3 * a if sig == "BUY" else (entry - 3 * a if sig == "SELL" else None)
    rnd = lambda v: None if v is None else round(v, 4)
    return {"sig": sig, "conf": conf, "entry": rnd(entry), "sl": rnd(sl), "tgt": rnd(tgt),
            "rsi": round(rs[i], 2), "e9": rnd(e9[i]), "e21": rnd(e21[i]), "e200": rnd(e200[i]),
            "atr": rnd(a), "up": e9[i] > e21[i],
            "backtest": backtest(hist, closes, e9, e21, e200, rs, at)}


def backtest(hist, closes, e9, e21, e200, rs, at):
    # साधा backtest: नवीन BUY/SELL आला की entry (close वर), SL/Target पैकी आधी जे लागेल ते.
    # एकाच candle मध्ये दोन्ही लागले तर loss धरतो (conservative).
    trades = wins = 0
    net_r = 0.0
    i, n, prev = 200, len(closes), "WAIT"
    while i < n - 1:
        sig, _ = classify(closes[i], e9[i], e21[i], e200[i], rs[i])
        if sig in ("BUY", "SELL") and sig != prev and at[i]:
            entry, a = closes[i], at[i]
            sl = entry - 1.5 * a if sig == "BUY" else entry + 1.5 * a
            tgt = entry + 3 * a if sig == "BUY" else entry - 3 * a
            j, result = i + 1, None
            while j < n:
                hi, lo = hist[j][2], hist[j][3]
                hit_sl = lo <= sl if sig == "BUY" else hi >= sl
                hit_tg = hi >= tgt if sig == "BUY" else lo <= tgt
                if hit_sl:
                    result = -1.0
                    break
                if hit_tg:
                    result = 2.0
                    break
                j += 1
            if result is None:  # अजून चालू trade — मोजत नाही
                break
            trades += 1
            wins += result > 0
            net_r += result
            prev, i = sig, j
            continue
        prev = sig
        i += 1
    return {"trades": trades, "winRate": round(wins * 100.0 / trades, 1) if trades else None,
            "netR": round(net_r, 1)}
