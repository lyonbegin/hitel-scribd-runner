# HITEL: run interactively on the Windows PC. No credentials are collected.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$root = Join-Path $env:LOCALAPPDATA 'HITEL'
$work = Join-Path $root 'ScribdPC'
$profile = Join-Path $root 'ScribdCDPProfile'
$downloads = Join-Path $root 'ScribdDownloads'
New-Item -ItemType Directory -Force -Path $work,$profile,$downloads | Out-Null
try {
    Write-Host '=== HITEL Scribd PC 다운로드 ===' -ForegroundColor Cyan
    # PowerShell hosts that evaluate pasted text may not define PSScriptRoot.
    # Never pass an empty path to Join-Path. Accept only the pinned queue.
    $queue = $null
    $folders = @()
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) { $folders += $PSScriptRoot }
    if (-not [string]::IsNullOrWhiteSpace($MyInvocation.MyCommand.Path)) {
        $folders += (Split-Path -LiteralPath $MyInvocation.MyCommand.Path -Parent)
    }
    $location = (Get-Location).ProviderPath
    if (-not [string]::IsNullOrWhiteSpace($location)) { $folders += $location }
    $folders += $work
    foreach ($folder in ($folders | Select-Object -Unique)) {
        if ([string]::IsNullOrWhiteSpace($folder)) { continue }
        $candidate = Join-Path $folder 'download_queue.csv'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if ((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() -eq '07533a58ab96ab4e31cc53f7d6ad9d4a83f3c390e99c0a399b0cfaa7aa00b6f6') {
                $queue = $candidate; break
            }
        }
    }
    if (-not $queue) {
        Write-Host '목록 파일 위치를 자동으로 찾지 못했습니다. 파일 선택 창에서 압축을 푼 download_queue.csv를 선택하십시오.' -ForegroundColor Yellow
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'HITEL 다운로드 목록 선택'
        $dialog.Filter = 'Download queue (download_queue.csv)|download_queue.csv|CSV (*.csv)|*.csv'
        $dialog.CheckFileExists = $true
        $dialog.Multiselect = $false
        $dialog.InitialDirectory = [Environment]::GetFolderPath('Desktop')
        try {
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $queue = $dialog.FileName }
        } finally { $dialog.Dispose() }
        if ([string]::IsNullOrWhiteSpace($queue)) { throw '목록 선택이 취소되었습니다. ZIP 압축 해제 후 다시 실행하십시오.' }
    }
    Write-Host "목록 파일: $queue"
    $hash = (Get-FileHash -LiteralPath $queue -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne '07533a58ab96ab4e31cc53f7d6ad9d4a83f3c390e99c0a399b0cfaa7aa00b6f6') { throw '목록 파일 검증 실패. 원본 ZIP을 다시 압축 해제하십시오.' }
    $cachedQueue = Join-Path $work 'download_queue.csv'
    if ([IO.Path]::GetFullPath($queue) -ne [IO.Path]::GetFullPath($cachedQueue)) { Copy-Item -LiteralPath $queue -Destination $cachedQueue -Force }
    $queue = $cachedQueue
    Write-Host '[1/4] 목록 확인: 7,210건 (대상 1,725 / 판본검토 5,485)'
    $py = $null
    $pyArgs = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; print(sys.version)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = 'py'; $pyArgs = @('-3') }
    }
    if (-not $py -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c "import sys; print(sys.version)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = 'python' }
    }
    if (-not $py) {
        Write-Host 'Python이 설치되어 있지 않습니다. Python 공식 설치 화면을 열겠습니다.'
        Start-Process 'https://www.python.org/downloads/windows/'
        Read-Host 'Python을 설치하신 후 Enter를 누르십시오. 설치 시 Add Python to PATH를 선택하십시오'
        $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
        if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py'; $pyArgs = @('-3') }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = 'python' }
        else { throw 'Python이 아직 확인되지 않습니다. 설치 후 이 파일을 다시 실행하십시오.' }
    }
    Write-Host '[2/4] Python 실행 환경 확인 및 준비'
    $venv = Join-Path $work 'venv'
    $venvPy = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPy)) {
        & $py @pyArgs -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 환경 생성 실패' }
    }
    & $venvPy -m pip show playwright | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $venvPy -m pip install --disable-pip-version-check playwright==1.56.0
        if ($LASTEXITCODE -ne 0) { throw 'Playwright 설치 실패' }
    }
    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chrome = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $chrome) {
        Start-Process 'https://www.google.com/chrome/'
        Read-Host 'Chrome을 설치한 후 Enter를 누르십시오'
        $chrome = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $chrome) { throw 'Chrome 설치를 확인할 수 없습니다.' }
    }
    Write-Host '[3/4] 전용 Chrome을 시작합니다.'
    # Probe CDP via Python with proxies explicitly disabled. A GUI window alone
    # is not proof of a live DevTools endpoint.
    $probeFile = Join-Path $work 'cdp-probe.py'
    $probeSource = @'
import json,sys,urllib.request
from urllib.parse import urlparse
url=sys.argv[1]
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url+"/json/version",timeout=2) as f:
        v=json.load(f)
    ws=urlparse(v.get("webSocketDebuggerUrl",""))
    if not v.get("Browser","").startswith("Chrome/") or ws.scheme!="ws" or ws.hostname not in ("localhost","127.0.0.1","::1") or ws.port!=urlparse(url).port:
        raise ValueError("Invalid local Chrome CDP response")
    print("CDP_READY "+url,flush=True)
except Exception as exc:
    print(type(exc).__name__+": "+str(exc),flush=True)
    sys.exit(1)
'@
    [IO.File]::WriteAllText($probeFile,$probeSource,(New-Object System.Text.UTF8Encoding($false)))
    $env:NO_PROXY = 'localhost,127.0.0.1,::1'
    $env:no_proxy = $env:NO_PROXY
    function Test-HitelCdp([string]$url) {
        $script:lastProbe = (& $venvPy $probeFile $url | Out-String).Trim()
        return ($LASTEXITCODE -eq 0)
    }
    function Get-HitelChrome([string]$dir) {
        @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
          Where-Object { $_.CommandLine -and $_.CommandLine.Contains($dir) -and $_.CommandLine -notmatch '--type=' })
    }
    $cdp = $null
    $lastProbe = ''
    $profiles = @($profile,(Join-Path $root 'ScribdCDPProfile-v3'))
    foreach ($dir in $profiles) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $owners = @(Get-HitelChrome $dir)
        # Reuse an existing HITEL session only after checking its ownership.
        if (@($owners | Where-Object {$_.CommandLine -match '--remote-debugging-port=9222(?:\s|$)'}).Count -gt 0) {
            if (Test-HitelCdp 'http://127.0.0.1:9222') { $cdp='http://127.0.0.1:9222'; break }
        }
        $activePort = Join-Path $dir 'DevToolsActivePort'
        if ($owners.Count -gt 0) {
            if ((Test-Path $activePort) -and @($owners | Where-Object {$_.CommandLine -match '--remote-debugging-port=0(?:\s|$)'}).Count -gt 0) {
                $portLine = Get-Content -LiteralPath $activePort -TotalCount 1
                if ($portLine -match '^\d+$' -and [int]$portLine -ge 1024 -and [int]$portLine -le 65535) {
                    $candidate = "http://127.0.0.1:$portLine"
                    if (Test-HitelCdp $candidate) { $cdp=$candidate; break }
                }
            }
            Write-Host "기존 HITEL Chrome이 연결 불가능한 상태입니다. 다른 전용 프로필을 확인합니다: $dir" -ForegroundColor Yellow
            continue
        }
        # Port 0 avoids collisions with other Chrome processes. Chrome records
        # its actual loopback port in DevToolsActivePort in the dedicated profile.
        if (Test-Path -LiteralPath $activePort) { Remove-Item -LiteralPath $activePort -Force }
        $chromeLog = Join-Path $work 'chrome-start.log'
        $arguments = @('--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',('--user-data-dir="' + $dir + '"'),'--no-first-run','--no-default-browser-check','--enable-logging',('--log-file="' + $chromeLog + '"'),'https://www.scribd.com/')
        Start-Process -FilePath $chrome -ArgumentList $arguments | Out-Null
        for ($i=0; $i -lt 60; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-Path -LiteralPath $activePort) {
                $portLine = Get-Content -LiteralPath $activePort -TotalCount 1 -ErrorAction SilentlyContinue
                if ($portLine -match '^\d+$' -and [int]$portLine -ge 1024 -and [int]$portLine -le 65535) {
                    $candidate = "http://127.0.0.1:$portLine"
                    if (Test-HitelCdp $candidate) { $cdp=$candidate; break }
                }
            }
            if (($i+1)%10 -eq 0) { Write-Host "Chrome 연결 확인 중... $($i+1)/60" }
        }
        if ($cdp) { break }
        Write-Host "연결 실패: $dir / $lastProbe" -ForegroundColor Yellow
    }
    if (-not $cdp) {
        Write-Host "Chrome 진단 로그: $(Join-Path $work 'chrome-start.log')" -ForegroundColor Yellow
        Write-Host "마지막 연결 결과: $lastProbe"
        throw '전용 Chrome의 CDP 포트를 확인할 수 없습니다. HITEL 전용 Chrome 창만 닫은 후 다시 실행하십시오.'
    }
    Write-Host "Chrome 연결 성공: $cdp" -ForegroundColor Green
    if ($env:HITEL_CDP_SELFTEST -eq '1') {
        Write-Host 'WINDOWS_REAL_CHROME_CDP_SELFTEST_OK'
        return
    }
    Write-Host ''
    Write-Host '지금 열린 HITEL 전용 Chrome에서 Scribd에 로그인하십시오.' -ForegroundColor Yellow
    Write-Host '본인에게 다운로드 권한이 있는 문서만 처리합니다. 유료 결제나 접근 제한은 자동으로 진행하지 않습니다.'
    Read-Host '로그인 및 다운로드 권한 확인이 끝나면 Enter를 누르십시오'
    $engine = Join-Path $work 'download.py'
    $source = @'
import asyncio,csv,json,re,sys,os,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

queue, dest, work = map(Path, sys.argv[1:4])
cdp = sys.argv[4]
u=urlparse(cdp)
if u.scheme!="http" or u.hostname!="127.0.0.1" or not u.port:raise ValueError("Local CDP required")
dest.mkdir(parents=True,exist_ok=True)
log=work/"download-results.jsonl"
blocked=re.compile(r"captcha|verify you are human|client challenge|checking your browser|security verification|access denied|membership is on hold|problem with your last payment|credit card information is invalid",re.I)
async def visible(loc):
    try:return await loc.count()>0 and await loc.first.is_visible()
    except Exception:return False
def pdf(p):
    try:
        with p.open("rb") as f:return f.read(5)==b"%PDF-"
    except OSError:return False
def emit(obj):
    with log.open("a",encoding="utf-8") as f:
        f.write(json.dumps(obj,ensure_ascii=False)+"\n");f.flush()
    print(json.dumps(obj,ensure_ascii=False),flush=True)
def load():
    with queue.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    seen=set()
    for r in rows:
        d=r["document_id"];u=urlparse(r["original_url"])
        if (not d.isdecimal() or d in seen or r["download_decision"] not in ("대상","판본검토")
            or u.scheme!="https" or u.netloc.lower() not in ("scribd.com","www.scribd.com")
            or not re.match(r"^/document/"+re.escape(d)+r"(?:/|$)",u.path)):
            raise ValueError("목록 검증 실패: "+d)
        seen.add(d)
    if len(rows)!=7210:raise ValueError("목록 건수 불일치")
    return rows
async def one(ctx,r):
    d=r["document_id"];page=await ctx.new_page();future=asyncio.get_running_loop().create_future()
    def on_download(x):
        if not future.done():future.set_result(x)
    page.on("download",on_download)
    try:
        await page.goto(r["original_url"],wait_until="domcontentloaded",timeout=35000)
        clicked=False;confirmed=False
        end=time.monotonic()+65
        while time.monotonic()<end:
            body=await page.locator("body").inner_text(timeout=5000)
            if blocked.search(body) or await visible(page.get_by_role("button",name=re.compile(r"^Continue anyway$",re.I))):
                return "access_or_payment_check"
            if future.done():break
            modal=page.locator('[role="dialog"][data-e2e="modal"]').filter(has=page.locator('a[data-e2e="modal-download-button"]'))
            anchor=modal.locator('a[data-e2e="modal-download-button"]')
            if not confirmed and await visible(anchor):
                box=modal.first.get_by_role("combobox")
                if not await visible(box) or not re.match(r"^PDF\b",(await box.first.inner_text(timeout=2500)).strip(),re.I):
                    return "pdf_format_unavailable"
                await anchor.first.click(timeout=20000)
                confirmed=True
            elif not clicked and not confirmed:
                b=page.get_by_role("button",name=re.compile(r"^Download$",re.I))
                if not await visible(b):b=page.get_by_role("link",name=re.compile(r"^Download$",re.I))
                if await visible(b):
                    await b.first.click(timeout=20000);clicked=True
            await asyncio.sleep(.6)
        if not future.done():return "no_download"
        dl=future.result()
        if await dl.failure():return "browser_download_failed"
        name=re.sub(r"[^\w.\-가-힣]+","_",dl.suggested_filename)[:100]
        final=dest/(d+"_"+(name or "document.pdf"))
        if final.suffix.lower()!=".pdf":final=final.with_suffix(".pdf")
        temp=final.with_suffix(".part")
        await dl.save_as(temp)
        if not pdf(temp):
            temp.unlink(missing_ok=True);return "invalid_pdf"
        os.replace(temp,final)
        return "saved"
    except Exception as e:
        return "error:"+type(e).__name__
    finally:
        await page.close()
async def main():
    rows=load()
    existing={p.name.split("_",1)[0] for p in dest.glob("*.pdf") if pdf(p)}
    pending=[r for r in rows if r["document_id"] not in existing]
    print(f"전체 {len(rows)}건 / 기존 PDF {len(rows)-len(pending)}건 / 남은 {len(pending)}건",flush=True)
    print("다운로드 권한이 확인된 문서만 진행합니다. Ctrl+C로 중지 후 다시 실행할 수 있습니다.",flush=True)
    if not pending:return
    async with async_playwright() as p:
        browser=await p.chromium.connect_over_cdp(cdp,timeout=15000)
        if not browser.contexts:raise RuntimeError("Chrome 로그인 창을 확인하십시오.")
        ctx=browser.contexts[0]
        ok=0;fail=0
        for offset in range(0,len(pending),5):
            batch=pending[offset:offset+5]
            results=await asyncio.gather(*(one(ctx,r) for r in batch),return_exceptions=True)
            stop=False
            for r,res in zip(batch,results):
                status=res if isinstance(res,str) else "error:"+type(res).__name__
                ok+=status=="saved";fail+=status!="saved"
                emit({"document_id":r["document_id"],"decision":r["download_decision"],"status":status,"success":ok,"failed":fail})
                if status=="access_or_payment_check":stop=True
            print(f"진행 {min(offset+len(batch),len(pending))}/{len(pending)} | 성공 {ok} | 미완료 {fail}",flush=True)
            if stop:
                print("접근 또는 결제 확인이 필요합니다. 사이트의 안내를 확인하신 후 다시 실행하십시오.",flush=True)
                return
            await asyncio.sleep(2)
        print(f"이번 실행 완료: 저장 {ok}건, 미완료 {fail}건. 미완료는 다음 실행에서 다시 확인합니다.",flush=True)
if __name__=="__main__":
    asyncio.run(main())
'@
    [IO.File]::WriteAllText($engine,$source,(New-Object System.Text.UTF8Encoding($false)))
    Write-Host '[4/4] 다운로드 실행' -ForegroundColor Green
    & $venvPy $engine $queue $downloads $work $cdp
    if ($LASTEXITCODE -ne 0) { throw "다운로드 프로그램 종료 코드 $LASTEXITCODE" }
} catch {
    Write-Host ("오류: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ("오류 위치: " + $_.InvocationInfo.PositionMessage) -ForegroundColor Yellow
    Write-Host ("오류 코드: " + $_.FullyQualifiedErrorId) -ForegroundColor Yellow
    if ($env:HITEL_CDP_SELFTEST -eq '1') { throw }
} finally {
    Write-Host "PDF 저장 폴더: $downloads"
    Write-Host "실행 기록: $work\download-results.jsonl"
    if ($env:HITEL_CDP_SELFTEST -ne '1') { Read-Host '종료하려면 Enter를 누르십시오' }
}
