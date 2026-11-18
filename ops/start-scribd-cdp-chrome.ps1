# Launch Google Chrome independently of Playwright and preserve one local Scribd profile.
# Run INTERACTIVELY on the Windows account that owns the Actions runner.
# NEVER expose the Chrome DevTools Protocol port over the public Internet.
param([ValidateRange(1024,65535)][int]$Port = 9222)
$ErrorActionPreference = 'Stop'
$profile = Join-Path $env:LOCALAPPDATA 'HITEL\ScribdCDPProfile'
$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw 'Google Chrome is not installed for this Windows account.' }
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$endpoint = "http://127.0.0.1:$Port/json/version"
$existing = $null
try { $existing = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2 } catch {}
if ($existing) {
    # Identify the independently launched dedicated-profile Chrome without
    # relying on DevToolsActivePort, which is not present in every Chrome build.
    $running = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.Contains("--remote-debugging-port=$Port") -and
            $_.CommandLine.Contains($profile)
        })
    if ($running.Count -eq 0) {
        throw "Port $Port is in use, but it does not belong to a verifiable HITEL profile Chrome process."
    }
    Write-Host "HITEL_CDP_ALREADY_RUNNING port=$Port profile=$profile"
    Write-Host 'Use this existing Chrome window and sign into Scribd if needed.'
    exit 0
}
$arguments = @(
    "--remote-debugging-port=$Port",
    '--remote-debugging-address=127.0.0.1',
    ('--user-data-dir="' + $profile + '"'),
    '--no-first-run',
    'https://www.scribd.com/'
)
Start-Process -FilePath $chrome -ArgumentList $arguments | Out-Null
$ready = $false
for ($i=0; $i -lt 25; $i++) {
    Start-Sleep -Milliseconds 400
    try {
        $response = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
        if ($response.Browser -like 'Chrome/*') { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    throw "Chrome did not expose local DevTools endpoint at 127.0.0.1:$Port. Check the Chrome window."
}
Write-Host "HITEL_CDP_READY http://127.0.0.1:$Port (localhost only)"
Write-Host "HITEL_PROFILE_LOCAL_ONLY $profile"
Write-Host 'Sign into www.scribd.com in THIS Chrome window before running the GitHub Actions inspection.'
Write-Host 'Keep the Chrome window open while Actions attaches. The profile persists after Chrome closes.'
