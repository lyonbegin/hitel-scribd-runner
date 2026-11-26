# Start only the dedicated local Chrome. Never close other browser processes.
$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'HITEL'
$work=Join-Path $root 'ScribdPC'
New-Item -ItemType Directory -Force -Path $work | Out-Null
function Get-HitelChrome([string]$dir) {
    @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($dir) -and $_.CommandLine -notmatch '--type=' })
}
function Test-CDP([int]$port) {
    try {
        $json = & curl.exe --noproxy '*' --silent --show-error --max-time 2 "http://127.0.0.1:$port/json/version" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        $v=$json | ConvertFrom-Json
        return ($v.Browser -like 'Chrome/*' -and $v.webSocketDebuggerUrl -like "ws://127.0.0.1:$port/*")
    } catch { return $false }
}
function Find-Port([string]$dir) {
    $owners=@(Get-HitelChrome $dir)
    if ($owners.Count -eq 0) { return 0 }
    if (@($owners | Where-Object { $_.CommandLine -match '--remote-debugging-port=9222(?:\s|$)' }).Count -gt 0) {
        if (Test-CDP 9222) { return 9222 }
    }
    $file=Join-Path $dir 'DevToolsActivePort'
    if ((Test-Path -LiteralPath $file) -and @($owners | Where-Object {$_.CommandLine -match '--remote-debugging-port=0(?:\s|$)'}).Count -gt 0) {
        $line=Get-Content -LiteralPath $file -TotalCount 1
        if ($line -match '^\d+$' -and [int]$line -ge 1024 -and [int]$line -le 65535 -and (Test-CDP ([int]$line))) { return [int]$line }
    }
    return 0
}
try {
    Write-Host '=== 1단계: HITEL 전용 Chrome 실행 ===' -ForegroundColor Cyan
    $candidates=@(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chrome=$candidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
    if (-not $chrome) { throw 'Google Chrome을 설치하십시오.' }
    $profiles=@((Join-Path $root 'ScribdCDPProfile'),(Join-Path $root 'ScribdCDPProfile-v3'))
    $port=0
    foreach ($dir in $profiles) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $port=Find-Port $dir
        if ($port -gt 0) { break }
        if (@(Get-HitelChrome $dir).Count -gt 0) { continue }
        $active=Join-Path $dir 'DevToolsActivePort'
        if (Test-Path -LiteralPath $active) { Remove-Item -LiteralPath $active -Force }
        $log=Join-Path $work 'chrome-start.log'
        $arguments=@('--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',('--user-data-dir="'+$dir+'"'),'--no-first-run','--no-default-browser-check','--enable-logging',('--log-file="'+$log+'"'),'https://www.scribd.com/')
        Start-Process -FilePath $chrome -ArgumentList $arguments | Out-Null
        for ($i=0;$i -lt 60;$i++) {
            Start-Sleep -Milliseconds 500
            $port=Find-Port $dir
            if ($port -gt 0) { break }
            if (($i+1)%10 -eq 0) { Write-Host 'Chrome 연결 확인 중...' }
        }
        if ($port -gt 0) { break }
    }
    if ($port -eq 0) { throw "Chrome CDP 연결 실패. HITEL 전용 Chrome 창만 닫고 다시 실행하십시오. 로그: $work\chrome-start.log" }
    Write-Host "Chrome 연결 성공: 127.0.0.1:$port" -ForegroundColor Green
    if ($env:HITEL_CDP_SELFTEST -eq '1') { Write-Host 'WINDOWS_CHROME_START_OK'; return }
    Write-Host 'Chrome에서 Scribd에 로그인하십시오. Chrome 창은 닫지 마십시오.' -ForegroundColor Yellow
    Read-Host '로그인 후 Enter를 누르십시오. 그 다음 2_Download_Start.ps1을 실행하십시오'
} catch {
    Write-Host ("오류: "+$_.Exception.Message) -ForegroundColor Red
    Write-Host $_.InvocationInfo.PositionMessage
    if ($env:HITEL_CDP_SELFTEST -eq '1') { throw }
    Read-Host '종료하려면 Enter를 누르십시오'
}
