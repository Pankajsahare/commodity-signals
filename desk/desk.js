/* Commodity Decision Desk — WordPress (Elementor HTML widget) मध्ये <div id="cdesk"></div> + हा script.
   Data: GitHub Pages वरचा encrypted JSON (AES-GCM). Passphrase फक्त तुझ्या browser मध्ये राहतो.
   Personal decision-support tool — not investment advice. */
(function () {
  "use strict";
  var me = document.currentScript;
  var BASE = (me && me.src) ? me.src.replace(/desk\.js.*$/, "") : "https://pankajsahare.github.io/commodity-signals/desk/";
  var PLAIN = !!window.CDESK_PLAIN || /[?&]plain=1/.test(location.search);  // फक्त testing/demo साठी
  var DATA = window.CDESK_DATA || (BASE + "data/");
  var root = document.getElementById("cdesk");
  if (!root) return;

  // ---------- Storage (try/catch: काही browsers मध्ये localStorage बंद असतं) ----------
  function sget(k, d) { try { var v = localStorage.getItem("cd_" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function sset(k, v) { try { localStorage.setItem("cd_" + k, JSON.stringify(v)); } catch (e) {} }
  function sdel(k) { try { localStorage.removeItem("cd_" + k); } catch (e) {} }

  var S = {
    summary: null, details: {}, tab: "overview", sector: "All", q: "",
    sort: sget("sort", { k: "score", d: -1 }), watch: sget("watch", []),
    set: sget("settings", { capital: 200000, risk: 1, relayUrl: "", relayToken: "" }),
    journal: sget("journal", []), pass: sget("pass", ""), keyCache: {}, err: null, chartTf: "D"
  };

  // ---------- Helpers ----------
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(n, d) { if (n == null || isNaN(n)) return "—"; d = d == null ? 2 : d; return Number(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function pct(n) { if (n == null) return '<span class="mut">—</span>'; return '<span class="' + (n >= 0 ? "up" : "dn") + '">' + (n >= 0 ? "▲ +" : "▼ ") + n.toFixed(2) + "%</span>"; }
  function ist(ts, opt) { return new Date(ts * 1000).toLocaleString("en-IN", Object.assign({ timeZone: "Asia/Kolkata" }, opt || { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })); }
  function $(sel) { return root.querySelector(sel); }
  function toast(msg) { var t = document.createElement("div"); t.className = "toast"; t.textContent = msg; root.appendChild(t); setTimeout(function () { t.remove(); }, 2600); }
  function rowOf(id) { return (S.summary.rows || []).filter(function (r) { return r.id === id; })[0]; }
  function isWatch(id) { return S.watch.indexOf(id) > -1; }

  // ---------- Crypto (WebCrypto) ----------
  function b64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function keyFor(salt) {
    if (S.keyCache[salt]) return Promise.resolve(S.keyCache[salt]);
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(S.pass), "PBKDF2", false, ["deriveKey"]).then(function (k) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(salt), iterations: 200000, hash: "SHA-256" }, k, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    }).then(function (k) { S.keyCache[salt] = k; return k; });
  }
  function decrypt(obj) {
    return keyFor(obj.salt).then(function (k) {
      return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(obj.iv) }, k, b64(obj.ct));
    }).then(function (buf) { return JSON.parse(new TextDecoder().decode(buf)); });
  }
  // network → decrypt; network fail झालं तर शेवटची cached copy (offline)
  function load(name) {
    var url = DATA + name + (PLAIN ? ".json" : ".enc") + "?ts=" + Date.now();
    return fetch(url, { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (txt) { sset("c_" + name, txt); return txt; })
      .catch(function (e) { var c = sget("c_" + name, null); if (c) { S.offline = true; return c; } throw e; })
      .then(function (txt) { var o = JSON.parse(txt); return PLAIN ? o : decrypt(o); });
  }

  // ---------- Render: shell ----------
  function skeleton() { root.innerHTML = '<div class="sk" style="height:40px"></div><div class="sk"></div><div class="sk"></div><div class="sk"></div><div class="sk"></div>'; }

  function lockScreen(msg) {
    root.innerHTML = '<div class="lock card"><h2>🔒 Commodity Desk</h2><p class="mut">Enter your desk passphrase. It stays only in this browser.</p>' +
      (msg ? '<div class="warnbox">' + esc(msg) + "</div>" : "") +
      '<input id="cdPass" type="password" placeholder="Passphrase" autocomplete="current-password"><br><br><button class="pri" id="cdUnlock">Unlock</button></div>';
    $("#cdUnlock").onclick = function () { S.pass = $("#cdPass").value; S.keyCache = {}; boot(); };
    $("#cdPass").onkeydown = function (e) { if (e.key === "Enter") $("#cdUnlock").click(); };
  }

  function header() {
    var s = S.summary, st = s.strip || {}, up = new Date(s.updatedAt), age = Math.round((Date.now() - up.getTime()) / 60000);
    return '<div class="hdr"><h2>Commodity Desk</h2>' +
      '<span class="chip"><span class="dot ' + (st.mcxOpen ? "on" : "") + '"></span>MCX ' + (st.mcxOpen ? "Open" : "Closed") + "</span>" +
      '<span class="chip"><span class="dot ' + (st.agriOpen ? "on" : "") + '"></span>Agri ' + (st.agriOpen ? "Open" : "Closed") + "</span>" +
      '<span class="chip">USD/INR ' + fmt(st.usdinr, 2) + "</span>" +
      (st.dxy ? '<span class="chip">DXY ' + fmt(st.dxy, 2) + "</span>" : "") +
      (st.goldSilver ? '<span class="chip">Gold/Silver ' + st.goldSilver + "</span>" : "") +
      '<span class="chip ' + (age > 20 ? "dn" : "") + '">Updated ' + (age < 1 ? "just now" : age + "m ago") + (S.offline ? " · offline" : "") + "</span>" +
      '<span class="sp"></span><button id="cdRef">↻</button><button id="cdSet">⚙</button></div>';
  }

  function tabs() {
    var t = [["overview", "Overview"], ["watch", "⭐ Watchlist"], ["calc", "Calculator"], ["journal", "Journal"], ["cal", "Calendar"]];
    return '<div class="tabs">' + t.map(function (x) { return '<button data-tab="' + x[0] + '" class="' + (S.tab === x[0] ? "on" : "") + '">' + x[1] + "</button>"; }).join("") + "</div>";
  }

  function render() {
    if (!S.summary) return;
    var body = { overview: overview, watch: watchTab, calc: calcTab, journal: journalTab, cal: calTab }[S.tab]();
    root.innerHTML = header() + tabs() + body +
      '<p class="mut" style="font-size:11px;margin-top:14px">Personal decision-support only — not investment advice. Intraday prices for global-linked commodities are COMEX/NYMEX futures converted to ₹ and calibrated to MCX where available; agri &amp; base-metal data is end-of-day from exchange bhavcopy. Margin figures are approximate — check with your broker.</p>';
    bind();
  }

  // ---------- Overview ----------
  function tfChips(tf) {
    var lab = { D: "D", H1: "1H", M15: "15m", M5: "5m" };
    return '<span class="tf">' + ["D", "H1", "M15", "M5"].map(function (k) {
      var v = tf ? tf[k] : null; if (v == null) return "";
      return '<i class="' + (v > 0 ? "u" : v < 0 ? "d" : "") + '">' + lab[k] + (v > 0 ? "▲" : v < 0 ? "▼" : "•") + "</i>";
    }).join("") + "</span>";
  }
  function freshTag(f) {
    if (!f) return '<span class="fresh">—</span>';
    var age = (Date.now() / 1000 - f.ts) / 60;
    if (f.type === "LIVE") return '<span class="fresh ' + (age > 20 ? "old" : "live") + '">LIVE ' + (age < 60 ? Math.round(age) + "m" : ist(f.ts, { hour: "2-digit", minute: "2-digit" })) + "</span>";
    return '<span class="fresh ' + (age > 60 * 30 ? "old" : "") + '">EOD ' + ist(f.ts, { day: "2-digit", month: "short" }) + "</span>";
  }
  function heatColor(p) {
    if (p == null) return "var(--card2)";
    var a = Math.min(Math.abs(p) / 3, 1) * 0.55 + 0.08;
    return p >= 0 ? "rgba(76,154,255," + a + ")" : "rgba(255,139,61," + a + ")";
  }
  function filtered(onlyWatch) {
    var q = S.q.toLowerCase();
    return S.summary.rows.filter(function (r) {
      if (r.nodata) return false;
      if (onlyWatch && !isWatch(r.id)) return false;
      if (S.sector !== "All" && r.sector !== S.sector) return false;
      return !q || (r.name + " " + r.id + " " + r.exch).toLowerCase().indexOf(q) > -1;
    });
  }
  function sorted(rows) {
    var k = S.sort.k, d = S.sort.d;
    return rows.slice().sort(function (a, b) {
      var x = k === "name" ? a.name : (k === "oi" ? ((a.oi || {}).oiChg) : a[k]), y = k === "name" ? b.name : (k === "oi" ? ((b.oi || {}).oiChg) : b[k]);
      if (x == null) return 1; if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * d;
    });
  }
  function listHTML(rows) {
    var cols = [["", ""], ["name", "Commodity"], ["price", "Price"], ["chgPct", "Chg"], ["", "Trend D/1H/15m/5m"], ["sig", "Signal"], ["score", "Score"], ["oi", "OI"], ["atrPct", "ATR%"], ["", "Data"]];
    var head = '<div class="li head">' + cols.map(function (c) { return '<span data-sort="' + c[0] + '">' + c[1] + (S.sort.k === c[0] && c[0] ? (S.sort.d > 0 ? " ↑" : " ↓") : "") + "</span>"; }).join("") + "</div>";
    if (!rows.length) return head + '<div class="card mut">No commodities match.</div>';
    return '<div class="list">' + head + sorted(rows).map(function (r) {
      if (r.nodata) return '<div class="li" data-id="' + r.id + '"><button class="star ' + (isWatch(r.id) ? "on" : "") + '" data-star="' + r.id + '">★</button><span><b>' + esc(r.name) + '</b> <span class="mut">' + r.exch + '</span></span><span class="m2 mut">' + esc(r.note || "No data") + "</span></div>";
      return '<div class="li" data-id="' + r.id + '"><button class="star ' + (isWatch(r.id) ? "on" : "") + '" data-star="' + r.id + '">★</button>' +
        '<span><b>' + esc(r.name) + '</b> <span class="mut" style="font-size:11px">' + r.exch + " · " + esc(r.unit) + "</span></span>" +
        "<span><b>" + fmt(r.price) + "</b></span><span>" + pct(r.chgPct) + "</span>" +
        '<span class="m2">' + tfChips(r.tf) + "</span>" +
        '<span><span class="badge b-' + r.sig + '">' + r.sig + "</span></span>" +
        '<span class="hm"><b>' + (r.score == null ? "—" : r.score) + "</b></span>" +
        '<span class="hm" style="font-size:12px">' + (r.oi ? esc(r.oi.label) + ' <span class="mut">' + (r.oi.oiChg >= 0 ? "+" : "") + r.oi.oiChg + "%</span>" : '<span class="mut">—</span>') + "</span>" +
        '<span class="hm">' + (r.atrPct == null ? "—" : r.atrPct + "%") + "</span>" +
        '<span class="hm">' + freshTag(r.fresh) + "</span></div>";
    }).join("") + "</div>";
  }
  function heatHTML(rows) {
    var secs = {};
    rows.forEach(function (r) { (secs[r.sector] = secs[r.sector] || []).push(r); });
    return Object.keys(secs).map(function (s) {
      return '<div class="sec">' + esc(s) + '</div><div class="heat">' + secs[s].map(function (r) {
        return '<div class="tile" data-id="' + r.id + '" style="background:' + heatColor(r.chgPct) + '"><b>' + esc(r.name) + "</b><span>" + (r.chgPct == null ? "—" : (r.chgPct >= 0 ? "▲" : "▼") + Math.abs(r.chgPct).toFixed(2) + "%") + "</span></div>";
      }).join("") + "</div>";
    }).join("");
  }
  function toolbar() {
    var secs = ["All"].concat(S.summary.rows.map(function (r) { return r.sector; }).filter(function (v, i, a) { return a.indexOf(v) === i; }));
    return '<div class="row" style="margin-bottom:10px"><input id="cdQ" placeholder="🔍 Search (e.g. jee, gold)" value="' + esc(S.q) + '" style="max-width:260px">' +
      secs.map(function (s) { return '<button data-sec="' + esc(s) + '" class="' + (S.sector === s ? "pri" : "") + '">' + esc(s) + "</button>"; }).join("") + "</div>";
  }
  function top3HTML() {
    var ids = S.summary.top3 || [];
    if (!ids.length) return '<div class="card mut" style="margin-bottom:12px">No strong setups right now — WAIT is also a position.</div>';
    return '<h3>Top setups</h3><div class="top3">' + ids.map(function (id) {
      var r = rowOf(id); if (!r) return "";
      return '<div class="card setup" data-id="' + id + '"><div class="row"><b>' + esc(r.name) + '</b><span class="sp"></span><span class="badge b-' + r.sig + '">' + r.sig + "</span></div>" +
        '<div class="row"><span class="sc">' + r.score + '</span><span class="mut">/100</span><span class="sp"></span>' + tfChips(r.tf) + "</div>" +
        '<div class="bar"><i style="width:' + r.score + '%"></i></div><div class="mut" style="font-size:12px;margin-top:6px">' +
        fmt(r.price) + " " + esc(r.unit) + " · OI " + esc((r.oi || {}).label || "—") + " · Reliability " + esc(r.reliab) + "</div></div>";
    }).join("") + "</div>";
  }
  function overview() {
    var rows = filtered(false);
    var ev = (S.summary.events || []).filter(function (e) { return e.t.slice(0, 10) === new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Kolkata" }); });
    return (ev.length ? '<div class="warnbox">⚠️ Today: ' + ev.map(function (e) { return esc(e.title) + " " + new Date(e.t).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }); }).join(" · ") + "</div>" : "") +
      top3HTML() + toolbar() + heatHTML(rows) + listHTML(rows) + hiddenNote();
  }
  function hiddenNote() {
    var h = S.summary.rows.filter(function (r) { return r.nodata; });
    return h.length ? '<p class="mut" style="font-size:12px;margin-top:8px">' + h.length + " MCX-only commodities hidden until their data arrives: " + h.map(function (r) { return esc(r.name); }).join(", ") + "</p>" : "";
  }
  function watchTab() {
    var rows = filtered(true);
    return toolbar() + (S.watch.length ? listHTML(rows) : '<div class="card mut">Tap ★ on any commodity to pin it here. Your watchlist opens first next time.</div>');
  }

  // ---------- Detail drawer ----------
  function openDetail(id) {
    var r = rowOf(id); if (!r || r.nodata) return;
    var ov = document.createElement("div"); ov.className = "ovl";
    ov.innerHTML = '<div class="drw"><div class="sk"></div><div class="sk" style="height:220px"></div></div>';
    ov.onclick = function (e) { if (e.target === ov) ov.remove(); };
    root.appendChild(ov);
    (S.details[id] ? Promise.resolve(S.details[id]) : load(id)).then(function (d) {
      S.details[id] = d; ov.querySelector(".drw").innerHTML = detailHTML(r, d); bindDetail(ov, r, d);
    }).catch(function (e) { ov.querySelector(".drw").innerHTML = '<div class="warnbox">Could not load detail: ' + esc(e.message) + "</div>"; });
  }
  function lotsTable(d, entry, sl, dir) {
    var dist = Math.abs(entry - sl), riskAmt = S.set.capital * S.set.risk / 100;
    return '<table><tr><th>Contract</th><th>Lots</th><th>Risk ₹</th><th>Margin ₹ (≈)</th></tr>' + d.lots.map(function (l) {
      var per = dist * l[1], n = per > 0 ? Math.floor(riskAmt / per) : 0, mg = entry * l[1] * d.marginPct / 100;
      return "<tr><td>" + esc(l[0]) + ' <span class="mut">' + esc(l[2]) + "</span></td><td>" + (n >= 1 ? "<b>" + n + "</b>" : '<span class="dn">0 (risk ₹' + fmt(per, 0) + ")</span>") +
        "</td><td>" + (n >= 1 ? fmt(n * per, 0) : "—") + "</td><td>" + fmt((n || 1) * mg, 0) + "</td></tr>";
    }).join("") + "</table>" + (d.verifyLot ? '<div class="mut" style="font-size:11px">⚠️ Lot size not verified — check contract specs on the exchange.</div>' : "");
  }
  function detailHTML(r, d) {
    var s = d.signal || {}, L = d.levels || {}, bt = d.bt || {};
    var lv = ["R3", "R2", "R1", "P", "S1", "S2", "S3"].map(function (k) { return '<div class="kv"><span>' + k + "</span><span>" + fmt(L[k]) + "</span></div>"; }).join("");
    var btRow = function (n, b) { return b && b.trades ? '<div class="kv"><span>' + n + "</span><span>" + b.trades + " trades · win " + b.winRate + "% · " + (b.netR >= 0 ? "+" : "") + b.netR + "R</span></div>" : '<div class="kv"><span>' + n + "</span><span>—</span></div>"; };
    var season = (d.season || []).map(function (m) {
      var v = m[1], h = v == null ? 2 : Math.min(Math.abs(v) * 8, 50) + 2;
      return '<div title="' + (v == null ? "" : v + "% (" + m[2] + " yrs)") + '"><i style="height:' + h + "px;background:" + (v == null ? "var(--line)" : v >= 0 ? "var(--up)" : "var(--dn)") + '"></i>' + "JFMAMJJASOND"[m[0] - 1] + "</div>";
    }).join("");
    var nextExp = (d.contracts || []).filter(function (c) { return c[0] >= new Date().toISOString().slice(0, 10); })[0];
    var entry = s.entry || r.price, sl = s.sl, tgt = s.tgt;
    var dir = s.sig === "SELL" ? -1 : 1;
    var slDefault = sl || (d.atr ? entry - dir * 1.5 * d.atr : null);
    return '<div class="row"><button id="cdClose">✕</button><h2 style="margin:0">' + esc(d.name) + '</h2><span class="mut">' + d.exch + " · " + esc(d.unit) + '</span><span class="sp"></span><button class="star ' + (isWatch(r.id) ? "on" : "") + '" data-star="' + r.id + '">★</button></div>' +
      '<div class="row" style="margin:6px 0 10px"><span style="font-size:26px;font-weight:800">' + fmt(r.price) + "</span>" + pct(r.chgPct) + freshTag(r.fresh) + "</div>" +
      '<div class="g2"><div class="card"><h3>Signal (' + (r.primary === "5m" ? "5-min" : "Daily") + ')</h3><div class="row"><span class="badge b-' + r.sig + '">' + r.sig + "</span><b>Score " + (r.score == null ? "—" : r.score) + "</b><span class=\"mut\">Reliability " + esc(r.reliab) + "</span></div>" +
      '<div style="margin:8px 0">' + tfChips(r.tf) + "</div>" +
      '<div class="kv"><span>Entry</span><span>' + fmt(entry) + '</span></div><div class="kv"><span>Stop-loss</span><span>' + fmt(sl) + '</span></div><div class="kv"><span>Target</span><span>' + fmt(tgt) + "</span></div>" +
      '<div class="kv"><span>RSI 14</span><span>' + (s.rsi == null ? "—" : s.rsi) + '</span></div><div class="kv"><span>EMA 9/21/200</span><span>' + fmt(s.e9) + " / " + fmt(s.e21) + " / " + fmt(s.e200) + '</span></div><div class="kv"><span>Daily ATR</span><span>' + fmt(d.atr) + "</span></div></div>" +
      '<div class="card"><h3>Levels (prev day)</h3>' + lv + '<div class="kv"><span>Prev High / Low</span><span>' + fmt(L.PDH) + " / " + fmt(L.PDL) + "</span></div></div></div>" +
      '<div class="card" style="margin-bottom:10px"><div class="row"><h3 style="margin:0">Chart</h3><span class="sp"></span><button data-ctf="D" class="' + (S.chartTf === "D" ? "pri" : "") + '">Daily</button>' + (d.intra && d.intra.length ? '<button data-ctf="I" class="' + (S.chartTf === "I" ? "pri" : "") + '">5-min</button>' : "") + (d.tv ? '<button id="cdTv">TradingView</button>' : "") + '</div><canvas id="cdChart" style="height:260px;margin-top:8px"></canvas><div id="cdTvBox"></div></div>' +
      '<div class="g2"><div class="card"><h3>Open interest</h3>' + (d.oi ? '<div class="kv"><span>Reading</span><span><b>' + esc(d.oi.label) + '</b></span></div><div class="kv"><span>OI change</span><span>' + d.oi.oiChg + "%</span></div>" : '<div class="mut">EOD exchange data not available.</div>') +
      (d.basis ? '<h3 style="margin-top:10px">Mandi basis (Agmarknet)</h3><div class="kv"><span>Spot median</span><span>' + fmt(d.basis.spot) + '</span></div><div class="kv"><span>Futures vs spot</span><span>' + d.basis.basisPct + "%</span></div>" : "") +
      (nextExp ? '<div class="kv"><span>Next expiry</span><span>' + nextExp[0] + "</span></div>" : "") + "</div>" +
      '<div class="card"><h3>Backtest &amp; seasonality</h3>' + btRow(r.primary === "5m" ? "5-min (5 days)" : "Daily", bt.primary) + (r.primary === "5m" ? btRow("Daily (history)", bt.daily) : "") +
      '<div class="season" style="margin-top:10px">' + season + '</div><div class="mut" style="font-size:11px">Avg monthly return by calendar month</div></div></div>' +
      '<div class="card" style="margin-bottom:10px"><h3>Position size (capital ₹' + fmt(S.set.capital, 0) + " · risk " + S.set.risk + '%)</h3>' + (slDefault ? lotsTable(d, entry, slDefault, dir) : '<div class="mut">Need a stop-loss to size.</div>') + "</div>" +
      '<div class="card chk"><h3>Pre-trade checklist</h3>' + ["Higher timeframe (Daily) agrees with trade direction", "No major event in next 30 min (EIA, CPI, Fed, expiry)", "Stop-loss beyond a level / ≥1× ATR", "Risk within my % limit", "Reward : risk ≥ 1.5", "Not a revenge / FOMO trade"].map(function (t, i) { return '<label><input type="checkbox" data-chk="' + i + '">' + t + "</label>"; }).join("") +
      '<div class="row" style="margin-top:8px"><select id="cdSide"><option' + (dir > 0 ? " selected" : "") + '>BUY</option><option' + (dir < 0 ? " selected" : "") + '>SELL</option></select><select id="cdCon">' + d.lots.map(function (l, i) { return '<option value="' + i + '">' + esc(l[0]) + "</option>"; }).join("") + '</select><input id="cdLots" type="number" min="1" value="1" style="max-width:80px"><button class="pri" id="cdLog" disabled>Log trade</button></div></div>';
  }
  function drawChart(cv, data, levels) {
    if (!cv || !data || !data.length) return;
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    var c = cv.getContext("2d"); c.scale(dpr, dpr);
    var d = data.slice(-90), lo = Infinity, hi = -Infinity;
    d.forEach(function (x) { lo = Math.min(lo, x[3]); hi = Math.max(hi, x[2]); });
    var pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
    var Y = function (v) { return h - 16 - (v - lo) / (hi - lo) * (h - 24); }, bw = w / d.length;
    c.font = "10px sans-serif";
    if (levels) ["R1", "P", "S1"].forEach(function (k) {
      var v = levels[k]; if (v == null || v < lo || v > hi) return;
      c.strokeStyle = "rgba(139,92,246,.6)"; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(0, Y(v)); c.lineTo(w, Y(v)); c.stroke(); c.setLineDash([]);
      c.fillStyle = "#8b97a7"; c.fillText(k + " " + fmt(v), 4, Y(v) - 3);
    });
    d.forEach(function (x, i) {
      var up = x[4] >= x[1], col = up ? "#4c9aff" : "#ff8b3d", cx = i * bw + bw / 2;
      c.strokeStyle = col; c.beginPath(); c.moveTo(cx, Y(x[2])); c.lineTo(cx, Y(x[3])); c.stroke();
      c.fillStyle = col; c.fillRect(cx - bw * 0.35, Math.min(Y(x[1]), Y(x[4])), Math.max(bw * 0.7, 1), Math.max(Math.abs(Y(x[1]) - Y(x[4])), 1));
    });
    [[20, "#e8edf3"], [50, "#f2c94c"]].forEach(function (e) {
      var n = e[0], k = 2 / (n + 1), cl = data.map(function (x) { return x[4]; }); if (cl.length < n) return;
      var v = cl.slice(0, n).reduce(function (a, b) { return a + b; }, 0) / n, ser = [];
      for (var i = n; i < cl.length; i++) { v = cl[i] * k + v * (1 - k); ser.push(v); }
      ser = ser.slice(-d.length); var off = d.length - ser.length;
      c.strokeStyle = e[1]; c.lineWidth = 1.2; c.beginPath();
      ser.forEach(function (v, i) { var x = (i + off) * bw + bw / 2; if (i) c.lineTo(x, Y(v)); else c.moveTo(x, Y(v)); }); c.stroke(); c.lineWidth = 1;
    });
    c.fillStyle = "#8b97a7"; c.fillText("EMA20 — white · EMA50 — yellow", w - 190, 12);
  }
  function bindDetail(ov, r, d) {
    ov.querySelector("#cdClose").onclick = function () { ov.remove(); };
    var draw = function () { drawChart(ov.querySelector("#cdChart"), S.chartTf === "I" ? d.intra : d.daily, S.chartTf === "D" || S.chartTf === "I" ? d.levels : null); };
    draw();
    ov.querySelectorAll("[data-ctf]").forEach(function (b) { b.onclick = function () { S.chartTf = b.getAttribute("data-ctf"); ov.querySelectorAll("[data-ctf]").forEach(function (x) { x.className = x === b ? "pri" : ""; }); draw(); }; });
    var tvb = ov.querySelector("#cdTv");
    if (tvb) tvb.onclick = function () {
      ov.querySelector("#cdTvBox").innerHTML = '<iframe style="height:420px;margin-top:8px" src="https://s.tradingview.com/widgetembed/?symbol=' + encodeURIComponent(d.tv) + '&interval=15&theme=dark&style=1&timezone=Asia%2FKolkata&withdateranges=1&hide_side_toolbar=0"></iframe>';
    };
    ov.querySelectorAll("[data-star]").forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); toggleStar(b.getAttribute("data-star")); b.classList.toggle("on"); }; });
    var chks = ov.querySelectorAll("[data-chk]"), log = ov.querySelector("#cdLog");
    chks.forEach(function (c) { c.onchange = function () { log.disabled = [].some.call(chks, function (x) { return !x.checked; }); }; });
    log.onclick = function () {
      var s = d.signal || {}, side = ov.querySelector("#cdSide").value, li = +ov.querySelector("#cdCon").value;
      var t = { id: Date.now().toString(36), date: new Date().toISOString(), commodity: d.name, cid: d.id, side: side,
        contract: d.lots[li][0], mult: d.lots[li][1], lots: +ov.querySelector("#cdLots").value || 1,
        entry: r.price, sl: s.sl || "", target: s.tgt || "", score: r.score, setup: (r.primary === "5m" ? "5m " : "D ") + r.sig, exitDate: "", exit: "", pnl: "", r: "", mistake: "", notes: "" };
      S.journal.unshift(t); saveJournal(t); toast("Trade logged in journal"); ov.remove();
    };
  }
  function toggleStar(id) {
    var i = S.watch.indexOf(id); if (i > -1) S.watch.splice(i, 1); else S.watch.push(id);
    sset("watch", S.watch);
  }

  // ---------- Calculator ----------
  function calcTab() {
    var rows = S.summary.rows.filter(function (r) { return !r.nodata; });
    var sel = S.calcId || (rows[0] || {}).id, r = rowOf(sel) || {};
    return '<div class="card"><h3>Position size &amp; margin calculator</h3><div class="g2">' +
      '<label>Commodity<select id="ccId">' + rows.map(function (x) { return '<option value="' + x.id + '"' + (x.id === sel ? " selected" : "") + ">" + esc(x.name) + "</option>"; }).join("") + "</select></label>" +
      '<label>Side<select id="ccSide"><option>BUY</option><option>SELL</option></select></label>' +
      '<label>Entry<input id="ccEntry" type="number" value="' + (r.price || "") + '"></label>' +
      '<label>Stop-loss<input id="ccSl" type="number" placeholder="required"></label>' +
      '<label>Target<input id="ccTgt" type="number" placeholder="optional"></label>' +
      '<label>Capital ₹<input id="ccCap" type="number" value="' + S.set.capital + '"></label>' +
      '<label>Risk per trade %<input id="ccRisk" type="number" step="0.1" value="' + S.set.risk + '"></label></div><div id="ccOut" class="mut">Enter a stop-loss to see lots, risk and margin.</div></div>';
  }
  function calcRun() {
    var id = $("#ccId").value, side = $("#ccSide").value === "SELL" ? -1 : 1, e = +$("#ccEntry").value, sl = +$("#ccSl").value, tg = +$("#ccTgt").value;
    var cap = +$("#ccCap").value || 0, rk = +$("#ccRisk").value || 0, out = $("#ccOut");
    S.calcId = id;
    var go = function (d) {
      if (!e || !sl) { out.innerHTML = "Enter a stop-loss to see lots, risk and margin."; return; }
      if ((e - sl) * side <= 0) { out.innerHTML = '<span class="dn">Stop-loss must be below entry for BUY / above entry for SELL.</span>'; return; }
      var dist = Math.abs(e - sl), riskAmt = cap * rk / 100, rr = tg ? Math.abs(tg - e) / dist : null;
      out.innerHTML = '<table style="margin-top:8px"><tr><th>Contract</th><th>Lots</th><th>Risk ₹</th><th>Reward ₹</th><th>Margin ₹ (≈)</th></tr>' + d.lots.map(function (l) {
        var per = dist * l[1], n = Math.floor(riskAmt / per);
        return "<tr><td>" + esc(l[0]) + ' <span class="mut">' + esc(l[2]) + "</span></td><td><b>" + n + "</b></td><td>" + (n ? fmt(n * per, 0) : '<span class="dn">1 lot = ' + fmt(per, 0) + "</span>") + "</td><td>" + (n && tg ? fmt(n * Math.abs(tg - e) * l[1], 0) : "—") + "</td><td>" + fmt(Math.max(n, 1) * e * l[1] * d.marginPct / 100, 0) + "</td></tr>";
      }).join("") + "</table>" + (rr ? '<p>Reward : risk = <b class="' + (rr >= 1.5 ? "up" : "dn") + '">' + rr.toFixed(2) + "</b>" + (rr < 1.5 ? " — below 1.5, consider skipping" : "") + "</p>" : "");
    };
    (S.details[id] ? Promise.resolve(S.details[id]) : load(id)).then(function (d) { S.details[id] = d; go(d); });
  }

  // ---------- Journal ----------
  function saveJournal(t) {
    sset("journal", S.journal);
    if (S.set.relayUrl && S.set.relayToken && t) {
      fetch(S.set.relayUrl, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify({ action: "upsert", token: S.set.relayToken, trade: t }) })
        .then(function (r) { return r.json(); }).then(function (j) { if (j.error) toast("Sheet sync: " + j.error); }).catch(function () { toast("Sheet sync failed — saved locally"); });
    }
  }
  function pullJournal() {
    if (!S.set.relayUrl || !S.set.relayToken) return Promise.resolve();
    return fetch(S.set.relayUrl + "?action=journal&token=" + encodeURIComponent(S.set.relayToken)).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.rows) return;
      var map = {}; S.journal.forEach(function (t) { map[t.id] = t; });
      j.rows.forEach(function (t) { var l = map[t.id]; if (!l || String(t.updatedAt || "") > String(l.updatedAt || "")) map[t.id] = t; });
      S.journal = Object.keys(map).map(function (k) { return map[k]; }).sort(function (a, b) { return String(b.date).localeCompare(String(a.date)); });
      sset("journal", S.journal);
    }).catch(function () {});
  }
  function journalTab() {
    var closed = S.journal.filter(function (t) { return t.exit !== "" && t.exit != null; }), open = S.journal.filter(function (t) { return t.exit === "" || t.exit == null; });
    var pnl = closed.map(function (t) { return +t.pnl || 0; }), wins = pnl.filter(function (p) { return p > 0; }).length;
    var rs = closed.map(function (t) { return +t.r; }).filter(function (x) { return !isNaN(x) && x !== 0; });
    var row = function (t, isOpen) {
      return "<tr><td>" + esc(String(t.date).slice(0, 10)) + "</td><td>" + esc(t.commodity) + ' <span class="mut">' + esc(t.contract) + "</span></td><td>" + esc(t.side) + " ×" + t.lots + "</td><td>" + fmt(+t.entry) + "</td><td>" + fmt(+t.sl) + "</td><td>" +
        (isOpen ? '<input data-exit="' + t.id + '" type="number" placeholder="Exit price" style="max-width:110px"><select data-mis="' + t.id + '" style="max-width:150px"><option value="">Mistake? (optional)</option><option>Entered early</option><option>Ignored SL</option><option>Event risk</option><option>Over-sized</option><option>FOMO / revenge</option><option>Exited early</option></select><button data-closet="' + t.id + '">Close</button>'
          : fmt(+t.exit) + ' · <b class="' + (+t.pnl >= 0 ? "up" : "dn") + '">₹' + fmt(+t.pnl, 0) + "</b> (" + (t.r === "" ? "—" : (+t.r).toFixed(2) + "R") + ")" + (t.mistake ? ' <span class="mut">' + esc(t.mistake) + "</span>" : "")) +
        '</td><td><button data-del="' + t.id + '">🗑</button></td></tr>';
    };
    return '<div class="g2"><div class="card"><h3>Stats (closed)</h3><div class="kv"><span>Trades</span><span>' + closed.length + '</span></div><div class="kv"><span>Win rate</span><span>' + (closed.length ? Math.round(wins * 100 / closed.length) + "%" : "—") + '</span></div><div class="kv"><span>Net P&amp;L</span><span class="' + (pnl.reduce(function (a, b) { return a + b; }, 0) >= 0 ? "up" : "dn") + '">₹' + fmt(pnl.reduce(function (a, b) { return a + b; }, 0), 0) + '</span></div><div class="kv"><span>Avg R</span><span>' + (rs.length ? (rs.reduce(function (a, b) { return a + b; }, 0) / rs.length).toFixed(2) : "—") + "</span></div></div>" +
      '<div class="card"><h3>Sync</h3><p class="mut" style="font-size:12.5px">' + (S.set.relayUrl ? "Google Sheet sync is ON." : "Saved in this browser only. Add the Relay URL + token in ⚙ Settings to sync with Google Sheet.") + '</p><div class="row"><button id="cdCsv">Export CSV</button>' + (S.set.relayUrl ? '<button id="cdPull">Pull from Sheet</button>' : "") + "</div></div></div>" +
      '<div class="card" style="margin-bottom:10px"><h3>Open trades</h3>' + (open.length ? '<table><tr><th>Date</th><th>Commodity</th><th>Side</th><th>Entry</th><th>SL</th><th>Exit</th><th></th></tr>' + open.map(function (t) { return row(t, true); }).join("") + "</table>" : '<div class="mut">No open trades. Log one from a commodity\'s detail panel (after the checklist).</div>') + "</div>" +
      '<div class="card"><h3>Closed trades</h3>' + (closed.length ? '<table><tr><th>Date</th><th>Commodity</th><th>Side</th><th>Entry</th><th>SL</th><th>Result</th><th></th></tr>' + closed.map(function (t) { return row(t, false); }).join("") + "</table>" : '<div class="mut">Nothing closed yet.</div>') + "</div>";
  }
  function csv() {
    var cols = ["date", "commodity", "contract", "side", "lots", "entry", "sl", "target", "exitDate", "exit", "pnl", "r", "score", "setup", "mistake", "notes"];
    var txt = cols.join(",") + "\n" + S.journal.map(function (t) { return cols.map(function (c) { return '"' + String(t[c] == null ? "" : t[c]).replace(/"/g, '""') + '"'; }).join(","); }).join("\n");
    var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([txt], { type: "text/csv" })); a.download = "commodity-journal.csv"; a.click();
  }

  // ---------- Calendar ----------
  function calTab() {
    var ev = S.summary.events || [], ex = S.summary.expiries || [];
    var tvcfg = encodeURIComponent(JSON.stringify({ colorTheme: "dark", isTransparent: true, width: "100%", height: "520", locale: "en", importanceFilter: "0,1", countryFilter: "us,in,cn,eu,gb,jp" }));
    return '<div class="g2"><div class="card"><h3>Next 7 days (commodity events)</h3>' + (ev.length ? ev.map(function (e) { return '<div class="kv"><span>' + new Date(e.t).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + "</span><span>" + (e.impact === "high" ? "🔴 " : "🟡 ") + esc(e.title) + "</span></div>"; }).join("") : '<div class="mut">None.</div>') + '<p class="mut" style="font-size:11px">EIA times auto-adjust for US daylight saving; US holidays can shift them by a day.</p></div>' +
      '<div class="card"><h3>Next expiry per commodity</h3>' + (ex.length ? ex.map(function (e) { return '<div class="kv"><span>' + esc(e.name) + ' <span class="mut">' + e.exch + "</span></span><span>" + e.exp + "</span></div>"; }).join("") : '<div class="mut">Available once exchange EOD data is loaded.</div>') + "</div></div>" +
      '<div class="card"><h3>Global economic calendar (CPI, Fed, jobs…)</h3><iframe style="height:540px;background:transparent" src="https://www.tradingview-widget.com/embed-widget/events/?locale=en#' + tvcfg + '"></iframe></div>';
  }

  // ---------- Settings ----------
  function settings() {
    var ov = document.createElement("div"); ov.className = "ovl";
    ov.innerHTML = '<div class="drw" style="width:min(440px,100%)"><div class="row"><h2 style="margin:0">Settings</h2><span class="sp"></span><button id="stX">✕</button></div><br>' +
      '<label>Capital ₹<input id="stCap" type="number" value="' + S.set.capital + '"></label><label>Risk per trade %<input id="stRisk" type="number" step="0.1" value="' + S.set.risk + '"></label>' +
      '<label>Relay URL (Google Apps Script — journal sync)<input id="stUrl" value="' + esc(S.set.relayUrl) + '" placeholder="https://script.google.com/macros/s/…/exec"></label>' +
      '<label>Relay token<input id="stTok" type="password" value="' + esc(S.set.relayToken) + '"></label>' +
      '<div class="row"><button class="pri" id="stSave">Save</button><button id="stLock">Lock desk</button><button id="stClr">Clear cache</button></div></div>';
    root.appendChild(ov);
    ov.querySelector("#stX").onclick = function () { ov.remove(); };
    ov.querySelector("#stSave").onclick = function () {
      S.set = { capital: +ov.querySelector("#stCap").value || 0, risk: +ov.querySelector("#stRisk").value || 1, relayUrl: ov.querySelector("#stUrl").value.trim(), relayToken: ov.querySelector("#stTok").value.trim() };
      sset("settings", S.set); ov.remove(); toast("Saved"); render(); pullJournal().then(render);
    };
    ov.querySelector("#stLock").onclick = function () { sdel("pass"); S.pass = ""; S.keyCache = {}; ov.remove(); lockScreen(); };
    ov.querySelector("#stClr").onclick = function () { Object.keys(localStorage).forEach(function (k) { if (k.indexOf("cd_c_") === 0) localStorage.removeItem(k); }); toast("Cache cleared"); };
  }

  // ---------- Events ----------
  function bind() {
    root.querySelectorAll("[data-tab]").forEach(function (b) { b.onclick = function () { S.tab = b.getAttribute("data-tab"); sset("tab", S.tab); render(); if (S.tab === "calc") calcRun(); }; });
    root.querySelectorAll("[data-id]").forEach(function (el) { el.onclick = function (e) { if (e.target.closest("[data-star]")) return; openDetail(el.getAttribute("data-id")); }; });
    root.querySelectorAll(".li [data-star]").forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); toggleStar(b.getAttribute("data-star")); render(); }; });
    root.querySelectorAll("[data-sec]").forEach(function (b) { b.onclick = function () { S.sector = b.getAttribute("data-sec"); render(); }; });
    root.querySelectorAll("[data-sort]").forEach(function (b) { var k = b.getAttribute("data-sort"); if (!k) return; b.onclick = function () { S.sort = { k: k, d: S.sort.k === k ? -S.sort.d : -1 }; sset("sort", S.sort); render(); }; });
    var q = $("#cdQ");
    if (q) q.oninput = function () {
      S.q = q.value; var pos = q.selectionStart; render(); var n = $("#cdQ"); n.focus(); n.setSelectionRange(pos, pos);
      var hits = filtered(S.tab === "watch"); if (hits.length === 1 && S.q.length >= 3) openDetail(hits[0].id);
    };
    $("#cdRef").onclick = function () { refresh(true); };
    $("#cdSet").onclick = settings;
    if (S.tab === "calc") ["#ccId", "#ccSide", "#ccEntry", "#ccSl", "#ccTgt", "#ccCap", "#ccRisk"].forEach(function (s) {
      $(s).oninput = $(s).onchange = function () { if (s === "#ccId") { var r = rowOf($("#ccId").value); $("#ccEntry").value = r ? r.price : ""; } calcRun(); };
    });
    if (S.tab === "journal") {
      root.querySelectorAll("[data-closet]").forEach(function (b) {
        b.onclick = function () {
          var id = b.getAttribute("data-closet"), t = S.journal.filter(function (x) { return x.id === id; })[0];
          var ex = +root.querySelector('[data-exit="' + id + '"]').value; if (!ex) { toast("Enter exit price"); return; }
          var dir = t.side === "SELL" ? -1 : 1, mult = +t.mult || ((S.details[t.cid] || {}).lots || [[0, 1]])[0][1];
          t.exit = ex; t.exitDate = new Date().toISOString(); t.pnl = Math.round((ex - t.entry) * dir * mult * t.lots);
          t.r = t.sl ? +(((ex - t.entry) * dir) / Math.abs(t.entry - t.sl)).toFixed(2) : "";
          t.mistake = root.querySelector('[data-mis="' + id + '"]').value; saveJournal(t); render();
        };
      });
      root.querySelectorAll("[data-del]").forEach(function (b) {
        b.onclick = function () {
          var id = b.getAttribute("data-del"); if (!confirm("Delete this trade?")) return;
          S.journal = S.journal.filter(function (x) { return x.id !== id; }); sset("journal", S.journal);
          if (S.set.relayUrl) fetch(S.set.relayUrl, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify({ action: "delete", token: S.set.relayToken, id: id }) }).catch(function () {});
          render();
        };
      });
      var c = $("#cdCsv"); if (c) c.onclick = csv;
      var p = $("#cdPull"); if (p) p.onclick = function () { pullJournal().then(function () { render(); toast("Synced"); }); };
    }
  }

  // ---------- Site header offset ----------
  // WordPress theme चा fixed/sticky header desk च्या वरच्या भागावर येतो → तेवढी जागा सोडतो
  function fixOffset() {
    var h = 0;
    [].forEach.call(document.querySelectorAll("body *"), function (el) {
      if (el === root || root.contains(el) || el.contains(root)) return;
      var cs = getComputedStyle(el);
      if ((cs.position === "fixed" || cs.position === "sticky") && cs.display !== "none" && cs.visibility !== "hidden") {
        var r = el.getBoundingClientRect();
        if (r.top <= 140 && r.bottom > 0 && r.height > 20 && r.height < 260 && r.width > window.innerWidth * 0.6) h = Math.max(h, r.bottom);
      }
    });
    root.style.scrollMarginTop = (h + 10) + "px";
    root.style.setProperty("--cd-top", h + "px");
    var top = root.getBoundingClientRect().top + window.scrollY;
    if (h && top < h + 8) root.style.marginTop = (h + 12 - top + (parseFloat(root.style.marginTop) || 0)) + "px";
  }
  setTimeout(fixOffset, 600); setTimeout(function () { root.style.marginTop = ""; fixOffset(); }, 2000); window.addEventListener("resize", function () { root.style.marginTop = ""; fixOffset(); });

  // ---------- Boot / refresh ----------
  function refresh(manual) {
    S.offline = false;
    return load("summary").then(function (s) { S.summary = s; S.details = {}; render(); if (manual) toast("Updated"); })
      .catch(function (e) { if (manual) toast("Refresh failed: " + e.message); });
  }
  function boot() {
    if (!PLAIN && !S.pass) { lockScreen(); return; }
    if (!(window.crypto && crypto.subtle)) { lockScreen("This browser does not support secure decryption (needs HTTPS)."); return; }
    skeleton();
    load("summary").then(function (s) {
      sset("pass", S.pass); S.summary = s;
      S.tab = S.watch.length ? sget("tab", "watch") : "overview";
      render(); pullJournal().then(function () { if (S.tab === "journal") render(); });
    }).catch(function (e) {
      if (e && e.name === "OperationError") { sdel("pass"); S.pass = ""; lockScreen("Wrong passphrase."); }
      else { root.innerHTML = '<div class="warnbox">Could not load desk data (' + esc(e.message || e) + "). The first data build may still be running — try again in a few minutes.</div>"; }
    });
  }
  boot();
  // दर 2 मिनिटाला refresh (tab दिसत असेल तेव्हाच; drawer उघडा असेल तर थांब)
  setInterval(function () { if (!document.hidden && S.summary && !root.querySelector(".ovl")) refresh(false); }, 120000);
})();
