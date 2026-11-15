# Commodity Desk — MCX uploader install (एकदाच चालवायचं)
# PowerShell मध्ये हा एकच command:
#   irm https://raw.githubusercontent.com/Pankajsahare/commodity-signals/main/pc/install.ps1 | iex
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:LOCALAPPDATA 'CommodityDesk'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$raw = 'https://raw.githubusercontent.com/Pankajsahare/commodity-signals/main/pc/mcx_upload.ps1'
Invoke-WebRequest $raw -OutFile (Join-Path $dir 'mcx_upload.ps1') -UseBasicParsing

Write-Host ''
Write-Host 'Relay token टाक (Apps Script मधला RELAY_TOKEN). टाइप करताना दिसणार नाही — फक्त या PC वर encrypted साठवला जातो.' -ForegroundColor Yellow
$tok = Read-Host 'Relay token' -AsSecureString
@{ relay = 'https://script.google.com/macros/s/AKfycbyK9zQLVbZB7IbdxEMaRz4NfGsZzANWJ-i3TpROOVoW_VLHjrLSknpmtAxbzlb_EPiifA/exec';
   token = ($tok | ConvertFrom-SecureString) } | ConvertTo-Json | Set-Content (Join-Path $dir 'config.json') -Encoding UTF8

# Task: रोज 00:30 + login वेळी; PC बंद असेल तर पुढच्या वेळी चालू झाल्यावर लगेच (StartWhenAvailable)
$ps = Join-Path $dir 'mcx_upload.ps1'
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ps`""
$trig    = @((New-ScheduledTaskTrigger -Daily -At '00:30'), (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME))
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'CommodityDesk MCX Upload' -Action $action -Trigger $trig -Settings $set -Description 'MCX bhavcopy → Commodity Desk (advisor4u)' -Force | Out-Null
Write-Host 'Scheduled task तयार: "CommodityDesk MCX Upload"' -ForegroundColor Green

Write-Host 'आता पहिल्यांदा मागच्या ~250 दिवसांचा MCX data पाठवतोय (10-20 मिनिटं लागतील, window बंद करू नको)...' -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ps -Days 250 -Force
Get-Content (Join-Path $dir 'upload.log') -Tail 5
Write-Host 'झालं. शेवटची ओळ "OK" असेल तर सगळं बरोबर आहे. Claude ला "uploader done" कळव.' -ForegroundColor Green
