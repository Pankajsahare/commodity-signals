/**
 * Commodity Desk Relay (Google Apps Script)
 * 1) MCX bhavcopy relay — MCX GitHub servers ला block करतो, Google चे servers चालतात (best-effort, अनधिकृत endpoint)
 * 2) Trade Journal — Google Sheet मध्ये साठवण (phone + laptop sync), आणि weekly report साठी वाचन
 *
 * Setup: Project Settings → Script properties → RELAY_TOKEN = (तुझा random token)
 * Deploy: Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone
 */
var SHEET_NAME = 'Journal';
// Journal ची Google Sheet (Commodity Journal) — standalone script असल्यामुळे ID ने उघडतो
var SHEET_ID = '10kX_y2-z0jHduzdetgTvh7GEY4RqZQiTX8_Q-PRYeCk';
var COLS = ['id', 'date', 'commodity', 'side', 'contract', 'lots', 'entry', 'sl', 'target', 'exitDate', 'exit',
            'pnl', 'r', 'score', 'setup', 'mistake', 'notes', 'updatedAt', 'mult', 'cid'];

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function authorized_(tok) {
  var want = PropertiesService.getScriptProperties().getProperty('RELAY_TOKEN');
  return want && tok === want;
}

function sheet_() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) sh.appendRow(COLS);
  return sh;
}

function readJournal_() {
  var sh = sheet_();
  var v = sh.getDataRange().getValues();
  var head = v.shift();
  return v.filter(function (r) { return r[0]; }).map(function (r) {
    var o = {};
    head.forEach(function (h, i) { o[h] = r[i] instanceof Date ? r[i].toISOString() : r[i]; });
    return o;
  });
}

function doGet(e) {
  var p = e.parameter || {};
  if (!authorized_(p.token)) return json_({ error: 'unauthorized' });
  if (p.action === 'mcx') {
    // date = dd/MM/yyyy
    var url = 'https://www.mcxindia.com/market-data/bhavcopy/GetDateWiseBhavCopy?InstrumentName=FUTCOM&fromDate=' +
              encodeURIComponent(p.date);
    var res = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: { 'Content-Type': 'application/json', 'Referer': 'https://www.mcxindia.com/market-data/bhavcopy',
                 'X-Requested-With': 'XMLHttpRequest',
                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36' }
    });
    if (res.getResponseCode() !== 200) return json_({ error: 'mcx ' + res.getResponseCode() });
    return ContentService.createTextOutput(res.getContentText()).setMimeType(ContentService.MimeType.JSON);
  }
  if (p.action === 'journal') return json_({ rows: readJournal_() });
  return json_({ ok: true });
}

function doPost(e) {
  var body = JSON.parse(e.postData.contents || '{}');
  if (!authorized_(body.token)) return json_({ error: 'unauthorized' });
  var sh = sheet_();
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var ids = sh.getRange(1, 1, Math.max(sh.getLastRow(), 1), 1).getValues().map(function (r) { return String(r[0]); });
    if (body.action === 'upsert') {
      var t = body.trade; t.updatedAt = new Date().toISOString();
      var row = COLS.map(function (c) { return t[c] === undefined ? '' : t[c]; });
      var i = ids.indexOf(String(t.id));
      if (i > 0) sh.getRange(i + 1, 1, 1, COLS.length).setValues([row]); else sh.appendRow(row);
      return json_({ ok: true });
    }
    if (body.action === 'delete') {
      var j = ids.indexOf(String(body.id));
      if (j > 0) sh.deleteRow(j + 1);
      return json_({ ok: true });
    }
  } finally {
    lock.releaseLock();
  }
  return json_({ error: 'unknown action' });
}
