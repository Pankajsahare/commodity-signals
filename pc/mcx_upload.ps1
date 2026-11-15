# MCX Bhavcopy Uploader — तुझ्या PC वरून (घरचं internet MCX block करत नाही)
# काय करतो: मागच्या कामाच्या दिवसांचा MCX FUTCOM bhavcopy घेतो → Google Apps Script relay ला पाठवतो
#           → GitHub Actions (eod) तिथून वाचून Commodity Desk मध्ये भरतो.
# Scheduled Task: रात्री 12:30 नंतर PC पहिल्यांदा चालू/login झाला की एकदा चालतो (दिवसातून एकदाच).
param([int]$Days = 12, [switch]$Force)
$ErrorActionPreference = 'Stop'
$dir   = Join-Path $env:LOCALAPPDATA 'CommodityDesk'
$log   = Join-Path $dir 'upload.log'
$stamp = Join-Path $dir 'last_ok.txt'
function Log($m) { "$(Get-Date -Format s)  $m" | Add-Content -Path $log -Encoding UTF8 }

# आज आधीच यशस्वी झालं असेल तर पुन्हा नको
if (-not $Force -and (Test-Path $stamp)) {
  $last = [datetime]::Parse((Get-Content $stamp -Raw).Trim())
  if ($last -ge (Get-Date).Date) { exit 0 }
}

try {
  $cfg = Get-Content (Join-Path $dir 'config.json') -Raw | ConvertFrom-Json
  $sec = $cfg.token | ConvertTo-SecureString
  $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'

  # Internet नसेल (PC नुकताच चालू झाला) तर 2 मिनिटं थांबून पाहतो
  for ($i = 0; $i -lt 8; $i++) {
    try { Invoke-WebRequest 'https://www.google.com' -UseBasicParsing -TimeoutSec 10 | Out-Null; break } catch { Start-Sleep 15 }
  }

  # MCX साठी आधी page उघडून cookies घेतो (browser सारखं)
  $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  Invoke-WebRequest 'https://www.mcxindia.com/market-data/bhavcopy' -WebSession $s -UserAgent $ua -UseBasicParsing -TimeoutSec 40 | Out-Null

  $have = (Invoke-RestMethod ($cfg.relay + '?action=mcx_dates&token=' + [uri]::EscapeDataString($token)) -TimeoutSec 60).dates
  $done = 0; $n = 0; $d = (Get-Date).Date
  while ($n -lt $Days) {
    $d = $d.AddDays(-1)
    if ($d.DayOfWeek -eq 'Saturday' -or $d.DayOfWeek -eq 'Sunday') { continue }
    $n++
    $iso = $d.ToString('yyyy-MM-dd')
    if ($have -contains $iso) { continue }
    $q = [uri]::EscapeDataString($d.ToString('dd/MM/yyyy'))
    $r = Invoke-RestMethod ("https://www.mcxindia.com/market-data/bhavcopy/GetDateWiseBhavCopy?InstrumentName=FUTCOM&fromDate=" + $q) `
          -WebSession $s -UserAgent $ua -ContentType 'application/json' -TimeoutSec 60 `
          -Headers @{ 'Referer' = 'https://www.mcxindia.com/market-data/bhavcopy'; 'X-Requested-With' = 'XMLHttpRequest' }
    $rows = @()
    foreach ($x in @($r.Data)) {
      if ($x.InstrumentName -ne 'FUTCOM' -or [double]$x.Close -le 0) { continue }
      $rows += ,@($x.Symbol.Trim(), $x.ExpiryDate, $x.Open, $x.High, $x.Low, $x.Close, $x.OpenInterest, $x.Volume)
    }
    # सुट्टीचा दिवस = रिकामी list (relay वर "data नाही" म्हणून नोंद होते)
    $body = @{ action = 'mcx_put'; token = $token; date = $iso; rows = $rows } | ConvertTo-Json -Depth 5 -Compress
    $res = Invoke-RestMethod $cfg.relay -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'text/plain; charset=utf-8' -TimeoutSec 90
    if ($res.error) { throw "relay: $($res.error)" }
    Log "uploaded $iso ($($rows.Count) contracts)"
    $done++
    Start-Sleep -Milliseconds 800
  }
  (Get-Date).ToString('s') | Set-Content $stamp
  Log "OK — $done new day(s)"
} catch {
  Log ("ERROR: " + $_.Exception.Message)
  exit 1
}
