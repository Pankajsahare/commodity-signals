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

function mcxSheet_() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sh = ss.getSheetByName('MCX') || ss.insertSheet('MCX');
  if (sh.getLastRow() === 0) { sh.appendRow(['date', 'rows_json', 'uploadedAt']); sh.getRange('A:A').setNumberFormat('@'); }
  return sh;
}

function mcxRow_(iso) {
  var sh = mcxSheet_();
  if (sh.getLastRow() < 2) return null;
  var f = sh.getRange(2, 1, sh.getLastRow() - 1, 1).createTextFinder(iso).matchEntireCell(true).findNext();
  return f ? sh.getRange(f.getRow(), 1, 1, 3).getDisplayValues()[0] : null;
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
    // date = dd/MM/yyyy → तुझ्या PC ने upload केलेला MCX bhavcopy (MCX cloud servers ना block करतो)
    var d = String(p.date || '').split('/');
    var iso = d.length === 3 ? d[2] + '-' + d[1] + '-' + d[0] : '';
    var row = mcxRow_(iso);
    if (!row) return json_({ error: 'not uploaded yet' });
    var arr = JSON.parse(row[1]);
    return json_({ Data: arr.map(function (a) {
      return { InstrumentName: 'FUTCOM', Symbol: a[0], ExpiryDate: a[1], Open: a[2], High: a[3], Low: a[4],
               Close: a[5], OpenInterest: a[6], Volume: a[7] };
    }) });
  }
  if (p.action === 'mcx_dates') {
    var sh = mcxSheet_();
    var v = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 1).getDisplayValues() : [];
    return json_({ dates: v.map(function (r) { return r[0]; }) });
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
    if (body.action === 'mcx_put') {
      // PC uploader: {date:'yyyy-mm-dd', rows:[[sym,exp,o,h,l,c,oi,vol],...]}
      var ms = mcxSheet_();
      var iso = String(body.date);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return json_({ error: 'bad date' });
      var payload = JSON.stringify(body.rows || []);
      var f = ms.getLastRow() > 1 ? ms.getRange(2, 1, ms.getLastRow() - 1, 1).createTextFinder(iso).matchEntireCell(true).findNext() : null;
      if (f) ms.getRange(f.getRow(), 2, 1, 2).setValues([[payload, new Date().toISOString()]]);
      else ms.appendRow([iso, payload, new Date().toISOString()]);
      return json_({ ok: true, rows: (body.rows || []).length });
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

// Editor मधून एकदा Run कर → Google परवानगी (authorize) मागेल; MCX relay चालतो का ते Execution log मध्ये दिसेल
// (15 Nov 2026 test: MCX ने Google servers पण block केले — 403. Journal sync चालतो.)
function testRelay() {
  var res = UrlFetchApp.fetch('https://www.mcxindia.com/market-data/bhavcopy/GetDateWiseBhavCopy?InstrumentName=FUTCOM&fromDate=' + encodeURIComponent('13/11/2026'),
    { muteHttpExceptions: true, headers: { 'Content-Type': 'application/json', 'Referer': 'https://www.mcxindia.com/market-data/bhavcopy', 'X-Requested-With': 'XMLHttpRequest' } });
  Logger.log('MCX status ' + res.getResponseCode() + ', bytes ' + res.getContentText().length);
  Logger.log('Journal rows: ' + readJournal_().length);
}

// ===== GitHub desk-build ला दर 5 मिनिटाला सुरू करणं (GitHub चे cron उशिरा चालतात / वगळतात) =====
// Setup: Script Properties मध्ये GH_PAT = fine-grained token (फक्त commodity-signals repo, Actions: Read and write)
//        मग editor मधून एकदा setupDispatchTrigger() Run कर.
function dispatchDesk() {
  var p = Utilities.formatDate(new Date(), 'Asia/Kolkata', 'u HH:mm').split(' ');  // u: 1=सोमवार … 7=रविवार
  var day = Number(p[0]), hm = p[1];
  if (day > 5 || hm < '08:55') return;  // शनिवार/रविवार आणि सकाळी 8:55 आधी नाही (MCX 23:55 पर्यंत)
  var pat = PropertiesService.getScriptProperties().getProperty('GH_PAT');
  if (!pat) return;
  UrlFetchApp.fetch('https://api.github.com/repos/Pankajsahare/commodity-signals/actions/workflows/desk-build.yml/dispatches', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + pat, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify({ ref: 'main' })
  });
}

function setupDispatchTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'dispatchDesk') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('dispatchDesk').timeBased().everyMinutes(5).create();
}
