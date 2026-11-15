# -*- coding: utf-8 -*-
# Angel One SmartAPI (तुझ्या स्वतःच्या broker account मधून अधिकृत MCX data) — फक्त data calls, orders नाहीत.
# Secrets: ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET (GitHub Secrets मध्ये)
import base64, datetime, hmac, json, os, struct, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import IST, UA, http_get  # noqa: E402

BASE = "https://apiconnect.angelone.in"
MASTER = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def configured():
    return all(os.environ.get(k) for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"))


def totp(secret):
    # Google-Authenticator सारखा 6 अंकी code (RFC 6238) — standard library ने
    s = secret.replace(" ", "").upper()
    key = base64.b32decode(s + "=" * ((8 - len(s) % 8) % 8))
    h = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), "sha1").digest()
    o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)


class Angel:
    def __init__(self):
        self.key = os.environ["ANGEL_API_KEY"]
        self.jwt = None

    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER",
             "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
             "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": self.key, "User-Agent": UA}
        if self.jwt:
            h["Authorization"] = "Bearer " + self.jwt
        return h

    def _post(self, path, body, retries=2):
        last = None
        for i in range(retries + 1):
            try:
                req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=self._headers())
                with urllib.request.urlopen(req, timeout=30) as r:
                    js = json.loads(r.read().decode())
                if js.get("status") is False or js.get("success") is False:
                    raise RuntimeError("%s %s" % (js.get("errorcode") or js.get("errorCode"), js.get("message")))
                return js.get("data")
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5 * (i + 1))  # rate limit (AB1021/403) साठी थांबून पुन्हा
        raise last

    def login(self):
        # दिवसभर एकच token (Angel रात्री 12 ला logout करतो) → दर 5 मिनिटाला नवीन login नको (rate-limit)
        cached = _load_token()
        if cached:
            self.jwt = cached
            return self
        d = self._post("/rest/auth/angelbroking/user/v1/loginByPassword", {
            "clientcode": os.environ["ANGEL_CLIENT_CODE"], "password": os.environ["ANGEL_PIN"],
            "totp": totp(os.environ["ANGEL_TOTP_SECRET"])}, retries=0)
        self.jwt = d["jwtToken"]
        _save_token(self.jwt)
        return self

    def candles(self, token, interval, start, end):
        # [[epoch, o, h, l, c, v], ...]
        d = self._post("/rest/secure/angelbroking/historical/v1/getCandleData", {
            "exchange": "MCX", "symboltoken": str(token), "interval": interval,
            "fromdate": start.strftime("%Y-%m-%d %H:%M"), "todate": end.strftime("%Y-%m-%d %H:%M")}) or []
        out = []
        for r in d:
            t = int(datetime.datetime.fromisoformat(r[0]).timestamp())
            out.append([t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0)])
        time.sleep(0.4)
        return out

    def quotes(self, tokens):
        # LTP + OI (FULL mode), 50 tokens पर्यंत एका call मध्ये
        out = {}
        for i in range(0, len(tokens), 50):
            d = self._post("/rest/secure/angelbroking/market/v1/quote/",
                           {"mode": "FULL", "exchangeTokens": {"MCX": [str(t) for t in tokens[i:i + 50]]}}) or {}
            for q in d.get("fetched", []):
                out[str(q.get("symbolToken"))] = q
        return out


def mcx_contracts(names):
    # Scrip master मधून चालू FUTCOM contracts: {name: [{token, exp, symbol, lot}] (expiry नुसार)}
    data = json.loads(http_get(MASTER, timeout=120).decode())
    today = datetime.datetime.now(IST).date().isoformat()
    out = {n: [] for n in names}
    for r in data:
        if r.get("exch_seg") != "MCX" or r.get("instrumenttype") != "FUTCOM" or r.get("name") not in out:
            continue
        e = r.get("expiry", "")
        try:
            exp = "%s-%02d-%s" % (e[5:9], MON[e[2:5].upper()], e[0:2])
        except KeyError:
            continue
        if exp >= today:
            out[r["name"]].append({"token": r["token"], "exp": exp, "symbol": r.get("symbol"), "lot": r.get("lotsize")})
    for n in out:
        out[n].sort(key=lambda x: x["exp"])
    return out


TOKEN_FILE = "state/angel_token.json"


def _cipher():
    # Token encrypt करूनच cache मध्ये: key = SHA256(TOTP secret + PIN) (secrets फक्त workflow कडे असतात)
    import hashlib
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = hashlib.sha256((os.environ["ANGEL_TOTP_SECRET"] + "|" + os.environ["ANGEL_PIN"]).encode()).digest()
    return AESGCM(k)


def _load_token():
    try:
        with open(TOKEN_FILE) as f:
            js = json.load(f)
        if js.get("day") != datetime.datetime.now(IST).date().isoformat():
            return None
        return _cipher().decrypt(base64.b64decode(js["iv"]), base64.b64decode(js["ct"]), None).decode()
    except Exception:  # noqa: BLE001
        return None


def _save_token(tok):
    try:
        iv = os.urandom(12)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({"day": datetime.datetime.now(IST).date().isoformat(),
                       "iv": base64.b64encode(iv).decode(),
                       "ct": base64.b64encode(_cipher().encrypt(iv, tok.encode(), None)).decode()}, f)
    except Exception as e:  # noqa: BLE001
        print("  warn: token cache", str(e)[:80])
