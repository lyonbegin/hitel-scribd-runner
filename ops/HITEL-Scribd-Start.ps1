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
        $folders += ([IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path))
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
    & $venvPy -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('playwright') else 1)"
    if ($LASTEXITCODE -ne 0) {
        & $venvPy -m pip install --disable-pip-version-check playwright==1.56.0
        if ($LASTEXITCODE -ne 0) { throw 'Playwright 설치 실패' }
    }
    Write-Host '[3/4] 이미 실행된 전용 Chrome에 연결합니다.'
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
        # Attach-only: never launch, close or modify a Chrome process here.
    }
    if (-not $cdp) {
        Write-Host "Chrome 진단 로그: $(Join-Path $work 'chrome-start.log')" -ForegroundColor Yellow
        Write-Host "마지막 연결 결과: $lastProbe"
        throw '1_Chrome_Start.ps1을 먼저 실행하고 Scribd에 로그인한 후 이 파일을 다시 실행하십시오.'
    }
    Write-Host "Chrome 연결 성공: $cdp" -ForegroundColor Green
    if ($env:HITEL_CDP_SELFTEST -eq '1') {
        Write-Host 'WINDOWS_REAL_CHROME_CDP_SELFTEST_OK'
        return
    }
    Write-Host ''
    Write-Host '열어 둔 HITEL Chrome에서 Scribd 로그인이 완료되었는지 확인하십시오.' -ForegroundColor Yellow
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
async def one_permitted_download_test(context, item, destination: Path, results_dir: Path):
    """Test one user's authorized PDF download with the actual Scribd modal DOM.

    Exact workflow: open supplied full URL; dismiss Continue anyway if shown;
    open Download modal if needed; confirm PDF; click the actual anchor
    <a data-e2e="modal-download-button">Download document</a>;
    handle a further Continue anyway if shown; verify a browser download and
    saved PDF on the Windows PC. No direct file URL is invented.
    """
    given_url = (
        "https://www.scribd.com/document/1061417751/"
        "%EB%82%B4%EA%B3%B5%EC%9D%98-%ED%9E%98-%EC%A4%911-1-2013-"
        "%EB%B9%84%EC%83%81-%EA%B5%90%EC%9E%AC-Black#"
    )
    target_url = given_url if item["document_id"] == "1061417751" else item["original_url"]
    result = {
        "document_id": item["document_id"],
        "attempted_url": target_url,
        "status": "not_started",
        "download_saved_on_pc": False,
        "initial_download_clicked": False,
        "continue_anyway_clicked": False,
        "final_download_anchor_clicked": False,
        "pdf_format_verified": False,
        "steps": [],
        "click_timeout_ms": 20000,
    }
    page = await context.new_page()
    download_future = asyncio.get_running_loop().create_future()

    def on_download(download):
        if not download_future.done():
            download_future.set_result(download)

    page.on("download", on_download)
    try:
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            result["steps"].append("full_user_url_opened")
        except Exception as exc:
            # A download may cause page navigation to abort.
            result["navigation_note"] = (type(exc).__name__ + ": " + str(exc))[:180]
        result["final_url"] = page.url

        modal_anchor = page.locator(
            '[role="dialog"][data-e2e="modal"] a[data-e2e="modal-download-button"]'
        )
        payment_button = page.get_by_role("button", name=re.compile(r"^Continue anyway$", re.I))

        async def is_visible(locator):
            try:
                return bool(await locator.count() and await locator.first.is_visible(timeout=600))
            except Exception:
                return False

        async def click_continue():
            if await is_visible(payment_button):
                await payment_button.first.click(timeout=20_000)
                result["continue_anyway_clicked"] = True
                result["steps"].append("payment_continue_anyway_clicked")
                return True
            return False

        async def click_pdf_modal_anchor():
            if not await is_visible(modal_anchor):
                return False
            # User-provided HTML shows role=combobox "PDF (4.96 MB)" and
            # a final clickable <a> rather than a <button>.
            modal = page.locator('[role="dialog"][data-e2e="modal"]').filter(
                has=page.locator('a[data-e2e="modal-download-button"]')
            ).first
            selector = modal.get_by_role("combobox")
            selected_format = ""
            if await selector.count():
                selected_format = (await selector.first.inner_text(timeout=2500)).strip()
            result["selected_format"] = selected_format
            if not re.search(r"^PDF\b", selected_format, re.I):
                result["status"] = "modal_format_not_pdf"
                result["steps"].append("download_modal_format_not_pdf")
                return False
            result["pdf_format_verified"] = True
            result["steps"].append("download_modal_pdf_verified")
            await modal_anchor.first.click(timeout=20_000)
            result["final_download_anchor_clicked"] = True
            result["steps"].append("modal_download_anchor_clicked")
            return True

        # Direct URL is used first, as requested; only the actual site UI
        # can start the browser download if navigation did not.
        initial_download_attempted = False
        modal_clicks = 0
        for _ in range(48):
            if download_future.done():
                break
            # Membership hold may appear before OR after the download dialog.
            if await click_continue():
                await page.wait_for_timeout(300)
                continue
            if await is_visible(modal_anchor):
                if result.get("status") == "modal_format_not_pdf":
                    break
                if modal_clicks < 2:
                    did_click = await click_pdf_modal_anchor()
                    if did_click:
                        modal_clicks += 1
                else:
                    result["steps"].append("download_modal_reappeared_twice_no_retry")
                    break
                await page.wait_for_timeout(450)
                continue
            if not initial_download_attempted:
                # When the supplied /document/ID/slug URL only loads a detail
                # page, the site's actual Download control is necessary to
                # open the modal. Avoid treating the URL as a direct file link.
                detail_button = page.get_by_role(
                    "button", name=re.compile(r"^Download$", re.I)
                )
                detail_link = page.get_by_role(
                    "link", name=re.compile(r"^Download$", re.I)
                )
                control = detail_button if await is_visible(detail_button) else detail_link
                if await is_visible(control):
                    await control.first.click(timeout=20_000)
                    initial_download_attempted = True
                    result["initial_download_clicked"] = True
                    result["steps"].append("detail_download_opens_modal")
                    await page.wait_for_timeout(350)
                    continue
            await page.wait_for_timeout(400)

        if not download_future.done() and result.get("status") != "modal_format_not_pdf":
            try:
                await asyncio.wait_for(asyncio.shield(download_future), timeout=10)
            except asyncio.TimeoutError:
                pass

        if download_future.done():
            download = download_future.result()
            failure = await download.failure()
            if failure:
                result["status"] = "browser_download_failed"
                result["download_failure"] = str(failure)[:250]
            else:
                destination.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^\w.\-가-힣]+", "_", download.suggested_filename)[:110]
                path = destination / (item["document_id"] + "_" + (safe or "document.pdf"))
                await download.save_as(path)
                size = path.stat().st_size
                with path.open("rb") as fp:
                    signature = fp.read(5)
                result["local_file_name"] = path.name
                result["file_size_bytes"] = size
                result["pdf_signature_valid"] = signature == b"%PDF-"
                result["download_saved_on_pc"] = size > 0 and signature == b"%PDF-"
                result["status"] = ("pdf_saved_on_pc" if result["download_saved_on_pc"]
                                    else "file_saved_but_pdf_not_verified")
                result["steps"].append("download_event_and_file_checked")
        elif result.get("status") != "modal_format_not_pdf":
            result["status"] = "no_download_event"
            result["steps"].append("no_browser_download_event")
            result["final_url"] = page.url
            result["final_modal_anchor_visible"] = await is_visible(modal_anchor)
            result["payment_continue_visible"] = await is_visible(payment_button)
            try:
                await page.screenshot(
                    path=str(results_dir / "one-download-modal-result.png"),
                    full_page=False, timeout=6000
                )
            except Exception:
                pass
    except Exception as exc:
        result["status"] = "download_test_exception"
        result["error"] = (type(exc).__name__ + ": " + str(exc))[:300]
    finally:
        page.remove_listener("download", on_download)
        await page.close()
    return result

async def one(ctx,r):
    diagnostics=work/"diagnostics"/r["document_id"]
    diagnostics.mkdir(parents=True,exist_ok=True)
    return await asyncio.wait_for(one_permitted_download_test(ctx,r,dest,diagnostics),timeout=145)
def existing_pdf_ids(folder, valid_ids):
    # Old engine saves ID_suggested_filename, which need not end in .pdf.
    # Trust actual local PDF bytes, not a successful log or filename extension.
    found=set()
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix.lower() in (".part",".crdownload",".tmp"):continue
        match=re.match(r"^(\d+)(?:_|\.|$)",path.name)
        if match and match.group(1) in valid_ids and pdf(path):
            found.add(match.group(1))
    return found

async def run_worker_pool(pending, worker, limit=10):
    # One consumer per slot; after its current item finishes, immediately
    # take the next unassigned item. No batch barrier.
    items=iter(enumerate(pending,1))
    async def slot():
        for index,row in items:
            await worker(row,index)
    await asyncio.gather(*(slot() for _ in range(min(limit,len(pending)))))

async def main():
    rows=load()
    existing=existing_pdf_ids(dest,{r["document_id"] for r in rows})
    pending=[r for r in rows if r["document_id"] not in existing]
    skipped=len(rows)-len(pending)
    print(f"전체 {len(rows)}건 / 기존 정상 PDF 제외 {skipped}건 / 남은 {len(pending)}건 / 동시 처리 10개",flush=True)
    print("기존 파일은 삭제하거나 다시 다운로드하지 않습니다.",flush=True)
    print("다운로드 권한이 확인된 문서만 진행합니다. Ctrl+C로 중지 후 다시 실행할 수 있습니다.",flush=True)
    if not pending:return
    async with async_playwright() as p:
        browser=await p.chromium.connect_over_cdp(cdp,timeout=15000)
        if not browser.contexts:raise RuntimeError("Chrome 로그인 창을 확인하십시오.")
        ctx=browser.contexts[0]
        ok=0;fail=0
        async def worker(r,index):
            nonlocal ok,fail
            started=time.monotonic()
            print(f"시작 {index}/{len(pending)} | 문서 {r['document_id']}",flush=True)
            try:
                detail=await one(ctx,r)
            except Exception as exc:
                detail={"status":"error:"+type(exc).__name__,"error":str(exc)[:300]}
            saved=(detail.get("status")=="pdf_saved_on_pc" and detail.get("pdf_signature_valid") is True and (detail.get("file_size_bytes") or 0)>0)
            ok+=saved;fail+=not saved
            emit({**detail,"document_id":r["document_id"],"decision":r["download_decision"],"success":ok,"failed":fail,"duration_seconds":round(time.monotonic()-started,2)})
            print(f"진행 {ok+fail}/{len(pending)} | 성공 {ok} | 미완료 {fail}",flush=True)
        await run_worker_pool(pending,worker,limit=10)
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
