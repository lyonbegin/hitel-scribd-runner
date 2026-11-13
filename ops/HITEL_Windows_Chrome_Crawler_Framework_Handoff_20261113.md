# HITEL 원격 Windows 크롤링 실행 프레임워크 — 구현·운영·개발 인계서

> **기준일:** 2026-11-13  
> **근거:** GitHub 저장소 `lyonbegin/hitel-scribd-runner`의 현재 `main` 소스 및 검증된 GitHub Actions 실행 로그  
> **성격:** 교재 목록 보고서가 아니라 **GitHub Actions → 사용자 Windows PC → 실제 Chrome → 수집 결과 → 원격 검증·복구** 실행 체계에 관한 재개발 인계서  
> **중요:** 이 문서는 확인된 실제 구현과 **차기 범용화 개발 제안**을 구별합니다. 이미 수집한 데이터의 재크롤링을 지시하지 않습니다.

## 1. 한 장 요약

**구현된 동작:** GitHub Actions 워크플로를 시작하면, GitHub에 등록된 Windows self-hosted runner가 사용자 PC에서 작업을 수신합니다. PowerShell이 GitHub의 Python 크롤러를 가져오고, Playwright가 **설치된 Google Chrome을 눈에 보이는 모드(`headless=False`)로 실행**합니다. 동일 Chrome 브라우저 컨텍스트 안에서 **10개의 비동기 페이지 작업**을 수행하며, 각 문서의 URL·제목·상태·스크린샷을 `results.csv`, `summary.json`, `<문서ID>.png`로 기록합니다. 오류가 나면 문서 단위 재시도·시간 제한·배치별 브라우저 재시작을 적용합니다. GitHub Actions에서 실행 단계·작업 상태·로그·아티팩트를 원격 확인할 수 있습니다.

**실제 증빙:** 2026-11-13 성공 실행 [43415200492](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492)에서 10건 사전시험이 `success`로 끝난 뒤 본 수집이 실행되었습니다. 최종 로그는 2,623건 대기열 중 기존 1,670건 제외, 953건의 누적 신규 방문 기록, 잔여 미방문 0건, 공개 미리보기 판정 693건을 보고했습니다. **이 값은 PDF 전체 다운로드 실적이나 6,137건 전체 목록의 완전성을 의미하지 않습니다.**

**구현되지 않은 동작:** 다양한 웹사이트를 설정만으로 수집하는 범용 플러그인, PC 화면을 외부에서 직접 보는 실시간 원격 화면, 범용 검색 엔진·자동 사이트 탐색, 공용 중앙 DB, 100% 확실한 GUI 가시성 증명, 결과물을 Drive에 자동 적재하는 범용 파이프라인은 아직 구현·검증되지 않았습니다.

## 2. 전체 연결 구조

```text
[관리자 / 다음 ChatGPT 세션]
    │ ① GitHub 저장소의 코드·워크플로 수정 또는 Actions 수동 실행
    ▼
[GitHub Repository + GitHub Actions (클라우드 컨트롤 플레인)]
    │ workflow_dispatch / workflow 파일 push
    ├─ [GitHub-hosted Ubuntu] publish-run-pointer
    │      └─ ops/latest_scribd_run.json 에 run_id · 링크 기록
    │
    └─ [self-hosted Windows] audit 작업 큐
               │ ② 온라인 Windows runner가 job 수신
               ▼
       [사용자 PC / C:\actions-runner / run.cmd]
               │ ③ PowerShell → Git clone/fetch → Python/Playwright 검증
               │ ④ 10건 Chrome 사전시험 → 통과한 경우만 본 작업
               ▼
       [설치된 Google Chrome / Playwright 비헤드리스]
               │ 10개 페이지 작업, URL 접근·DOM 검사·스크린샷
               │ 문서 단위 제한시간 / 재시도 / 80건당 브라우저 재시작
               ▼
       [Windows runner 작업 디렉터리]
               ├─ results.csv (문서별 지속 체크포인트)
               ├─ summary.json (집계·중단 사유)
               └─ <document_id>.png (보이는 화면만 캡처)
               │ ⑤ Actions 로그 및 아티팩트 업로드
               ▼
       [GitHub Actions 로그 + 아티팩트]
               │ ⑥ 원격 상태/실패 단계/수집 건수 점검
               ▼
       [엑셀 통합 / 별도 백업 / 아티팩트 정리]
```

**책임 분리:** GitHub는 **명령·코드·작업상태**의 출처이고, 사용자 Windows PC는 **Chrome 실행과 실제 네트워크 접근**의 실행 환경입니다. GitHub-hosted Ubuntu는 단순한 실행번호 기록과 같은 컨트롤 작업을 맡습니다. ChatGPT가 직접 PC 데스크톱을 실시간 제어하거나 볼 수 있다는 뜻이 아닙니다.

## 3. 소스 위치와 기능 맵 (현재 GitHub의 실제 구현)

기준 저장소: <https://github.com/lyonbegin/hitel-scribd-runner>

| 경로 | 실제 역할 |
|---|---|
| `.github/workflows/scribd-remaining-10tabs.yml` | **현재 주요 오케스트레이터.** Windows GUI 세션 검사 → 소스 가져오기 → Playwright 확인 → self-test/dry-run → 10건 사전시험 → 전체 크롤링 → 요약 출력 → 결과 업로드 |
| `tools/zocbo/scribd_10tabs_remaining.py` | **실제 브라우저 엔진.** ID 대기열, 이미 방문한 ID 제외, 10개 동시 작업, Playwright, DOM 판정, PNG, 시간 제한·재시도·체크포인트 |
| `tools/zocbo/remaining_unclassified_2623_ids.txt` | 2,623건 감사 완료 대기열. **Scribd 전용 데이터**이며 다른 프로젝트에 그대로 사용 금지 |
| `tools/zocbo/attempted_*.csv` / `*.txt` | 실행 간 **중복 방문 방지**를 위한 방문 ID 체크포인트 |
| `ops/latest_scribd_run.json` | **최근 워크플로 실행번호 포인터.** `workflow_started` 값은 최종 성공 상태가 아니므로 Actions에서 실제 status/conclusion 조회 필수 |
| `.github/workflows/scribd-windows-preview.yml` | 이전 3건 Chrome 접근 사전검사 방식의 구현 사례 |
| `.github/workflows/scribd-814-batches.yml` | 이전 50건 단위 순차 매트릭스 작업 구현 사례. 현재 기본 본작업으로 쓰지 않음 |
| `.github/workflows/scribd-remaining-2623-firstpage.yml` | 이전 2,623건 공개 미리보기 분할 수집 방식 참고 |
| `.github/workflows/stop-active-scribd.yml` | 실행 중인 Scribd 관련 Actions 취소 용도(다른 작업을 함부로 취소하지 않도록 범위 제한) |
| `.github/workflows/scribd-cleanup-artifacts.yml` | **이미 백업된 특정 38개 아티팩트 ID 삭제**에 사용. 범용 삭제기로 재사용 금지 |
| `ops/scribd-image-inventory-20261113.md` | 이미지 수집 품질, 미리보기 오분류, 불필요한 재수집 방지에 관한 감사 기록 |

### 실제 사용한 구성 요소

- OS/작업 관리자: Windows + **GitHub Actions self-hosted runner** (`DESKTOP-3239E35`, 이전 로그상 식별명).
- 진입점: 기존 러너 디렉터리의 `C:\actions-runner\run.cmd`.
- 워크플로 shell: `powershell`; 저장소 동기화: `git clone` 또는 `git fetch`/`git reset`.
- 실행언어: Python 3; 브라우저 자동화: `playwright==1.56.0` 확인/설치.
- 브라우저: `playwright.chromium.launch(channel="chrome", headless=False)` (CLI에서 `--headless`를 사용하지 않은 경우).
- 결과 형식: UTF-8 CSV, JSON, PNG; GitHub Actions job log·artifact.
- GitHub 연동 권한: 본작업 `contents: write`, `actions: read`; 단순 방문에는 권한 최소화 재설계 권장.

## 4. Windows PC와 GitHub 러너를 연결하는 법

### 4-1. PC 준비 (최초 구성 시)

1. Windows 사용자 계정으로 **데스크톱에 실제 로그인**합니다. 일반 Chrome 창 표시가 목적이라면 Session 0 Windows 서비스 방식은 피합니다.
2. Google Chrome, Git, Python 3 및 실행 가능한 Playwright Python 패키지를 준비합니다.
3. GitHub 저장소의 **Settings → Actions → Runners**에서 Windows self-hosted runner를 등록합니다. *최초 등록 명령과 인증 토큰은 해당 페이지가 제공하는 최신 명령을 사용합니다.* 토큰을 문서·커밋에 기록하지 않습니다.
4. 기존 등록이 살아 있다면 다시 등록할 필요 없이 다음 명령으로 수동 실행합니다.

```powershell
cd C:\actions-runner
.\run.cmd
```

정상 접속 메시지: `Connected to GitHub` → `Listening for Jobs`. **창을 닫거나 `Ctrl+C`를 누르면 수동 러너는 종료됩니다.** PC 절전·재부팅·인터넷 단절 시 실행이 중단될 수 있습니다.

### 4-2. 러너 연결 충돌 복구

오류 예: `A session for this runner already exists` / `Runner connect error: Conflict`.

```powershell
# 기존 러너 프로세스 및 GUI 세션 확인
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -in @('Runner.Listener.exe','Runner.Worker.exe') } |
  Select-Object Name,ProcessId,ParentProcessId,SessionId,CommandLine |
  Format-List

# Windows 서비스 등록 여부 별도 확인
Get-Service 'actions.runner.*' -ErrorAction SilentlyContinue |
  Select-Object Name,Status
```

동일 러너를 **두 창에서 동시에 시작하지 않습니다.** 기존 러너가 정상으로 보이면 두 번째 `run.cmd`만 중지합니다. 기존 작업이 진행 중일 때 Listener/Worker를 무조건 강제 종료하면 작업이 유실될 수 있습니다. 기존 러너가 완전히 종료된 것을 확인한 뒤 **단 한 개**의 PowerShell에서 `run.cmd`를 재실행합니다. `Get-Service` 결과가 비어 있다는 사실만으로 기존 일반 프로세스가 없다고 단정할 수 없습니다.

### 4-3. GUI 확인의 한계

현 워크플로는 `(Get-Process -Id $PID).SessionId`가 0이면 실행을 막습니다. **이 조건 통과만으로 PC 모니터에 Chrome이 실제로 보였다는 보증은 아닙니다.** RDP 잠금·다른 사용자 세션·창 최소화 등의 상태를 별도로 검증할 필요가 있습니다. Chrome이 현재 안 보인다는 사실도, 이미 job이 정상 종료되어 브라우저가 닫힌 경우와 실제 실행 실패를 구분해서 판단해야 합니다.

## 5. GitHub Actions 실행 순서 (검증된 주요 워크플로)

1. **시작:** Actions 메뉴의 `scribd-remaining-10tabs.yml`에서 `Run workflow` 실행, 또는 해당 워크플로 YAML 자체를 `main`에 push하면 자동 시작.
2. **실행번호 등록:** Ubuntu job `publish-run-pointer`가 `ops/latest_scribd_run.json`을 갱신. 다음 채팅에서도 작업번호와 링크를 회수할 수 있게 하는 장치.
3. **Windows job 할당:** `runs-on: [self-hosted, Windows]`, `audit` job이 온라인 러너를 기다림. 러너 오프라인이면 시작되지 않음.
4. **화면 세션 사전 검사:** 현재 PowerShell 프로세스 SessionId 확인, Session 0이면 실패 처리.
5. **소스 배포:** 기존 `src/.git`이 있으면 `git fetch/reset`, 없으면 `git clone`. 이전 `actions/checkout`에서 Windows EBUSY/잠금 문제가 있어 변경한 방식.
6. **환경 확인:** Python 3에 Playwright 1.56.0 존재 여부 확인·필요 시 설치.
7. **실행 전 검증:** `py_compile`, `--self-test`, `--dry-run`으로 문법·체크포인트·대기열·watchdog 검증.
8. **실제 사이트 10건 사전시험:** Chrome 10탭으로 새 문서 10건 처리; 이전 CSV와 비교해 **이번에 신규 처리된 10건**을 별도 집계.
9. **사전시험 합격 기준(현재 코드):** 신규 고유 ID 정확히 10건, `preview_visible` 7건 이상, `timeout/error/blocked` 0건. 합격하지 못하면 **전체 수집 실행하지 않음**. 이 기준은 향후 사이트별로 재설계 필요.
10. **본작업:** `--tabs 10`, `--batch-size 80`, `--document-timeout 80`, `--batch-timeout 1200`, `--retries 1`. 배치 사이에 Chrome을 재실행.
11. **항상 출력·백업:** 성공·실패와 무관하게 요약을 출력하고 `results.csv`, `summary.json` 체크포인트를 업로드. 과거 코드에는 모든 PNG도 자동 업로드하는 단계가 있어 저장공간을 크게 차지했음.

### 직접 실행 예제 (Windows PC에서 저장소를 이미 받은 경우)

```powershell
cd C:\path\to\hitel-scribd-runner
py -3 -m py_compile tools\zocbo\scribd_10tabs_remaining.py
py -3 tools\zocbo\scribd_10tabs_remaining.py --self-test
py -3 tools\zocbo\scribd_10tabs_remaining.py --dry-run
# 주의: 아래는 Scribd 전용 대기열과 체크포인트가 있을 때만 유효함
py -3 tools\zocbo\scribd_10tabs_remaining.py --limit 10 --tabs 10
```

**중요:** 현 스크립트는 인자 없이 실행하면 특정 Scribd 데이터 경로를 참조하고, `--tabs` 값을 10으로 강제합니다. **범용 크롤러로 그대로 복사하지 않습니다.** 실행 경로/워크스페이스/대기열을 먼저 변경해야 합니다.

## 6. 실제 Python 엔진의 동작 원리

### 6-1. 대기열과 중복 제외

- ID 목록(`*.txt`, 또는 압축된 `*.zlib64`)을 `read_ids()`로 읽고 숫자 형식·중복·예상 건수를 확인합니다.
- 과거 실행 체크포인트는 `prior_ids()`로 합집합 처리합니다.
- 현재 `results.csv`가 있으면 `csv_rows()`로 기존 결과를 재사용합니다.
- `error`, `timeout`은 완료로 보지 않고 재작업 대상으로 다시 큐에 넣습니다. `preview_visible`, `loaded_no_preview`, `unexpected_redirect`, `http_error` 등은 **방문 판정**으로 다음 실행에서 제외할 수 있지만, 이는 교재 정보 수집 성공과 다릅니다.
- 결과를 문서 ID 기준으로 사전/사후 중복 제거합니다. 장기적으로는 상태별 재처리 정책을 중앙 DB로 옮기는 것이 안전합니다.

### 6-2. 10개의 독립 페이지 처리

- `asyncio.Queue`에 대상 ID를 넣고 `asyncio.create_task(worker(n))` 10개를 띄웁니다.
- `playwright.chromium.launch(channel="chrome", headless=args.headless)`로 설치된 Chrome 1개 프로세스/컨텍스트를 시작합니다.
- worker별로 `context.new_page()` → URL 이동 → 검사 → `page.close()`를 수행합니다. **10개의 별도 Chrome 프로세스를 띄우는 방식이 아니라 10개의 병렬 페이지 작업**입니다.
- `context.new_page` 20초, browser launch 45초, browser context 생성 25초, 페이지 작업 기본 80초, 페이지 close 5초, 배치 전체 기본 1,200초의 제한을 적용합니다.
- 기본 80개 ID마다 컨텍스트와 브라우저를 닫고 다시 띄워 장시간 실행의 누적 자원 문제를 완화합니다.

### 6-3. 사이트 판정 / 화면 캡처

- URL 예: `https://www.scribd.com/document/<문서ID>`.
- `page.goto(wait_until="domcontentloaded", timeout=30000)` 후 짧게 대기합니다.
- 제목은 `page.locator("title").first.text_content(timeout=1800)`, 헤더는 `h1`, 본문은 `body.inner_text(timeout=4500)`로 제한시간 안에서 수집합니다. 과거 무한 대기에 가까운 `page.title()` 정지 문제를 해결하려고 제한시간을 명시했습니다.
- 캡차/사이트 차단 문구 감지 → `blocked`; HTTP 400 이상 → `http_error`; `/document/`를 벗어난 이동 → `unexpected_redirect`; 문서 페이지를 열었지만 선택자 미검출 → `loaded_no_preview`; 지정된 canvas/page 선택자 표시 → `preview_visible`.
- 현재 선택자는 Scribd DOM 전용이며, **선택자가 보이지 않는다고 이미지까지 비어 있다는 의미는 아닙니다**. 기존 이미지 감사에서 오분류 사례가 확인됨.
- PNG는 `page.screenshot(full_page=False, animations="disabled")`: **해당 시점에 화면에 보이는 범위만 캡처**합니다. 전체 PDF의 모든 페이지를 받은 것이 아닙니다.
- CAPTCHA를 우회하거나 유료 문서를 무단 다운로드하는 기능은 없습니다. 사이트별 약관·공개 범위·저작권 준수가 전제입니다.

### 6-4. 장애 감지·자동 복구

- `bounded()`는 `asyncio.wait`로 각 작업의 최대 대기 시간을 제한합니다. 기본 오류/시간 초과는 문서당 1회 추가 시도(`--retries 1`).
- 한 배치에서 `blocked` 3건 감지 시 사이트 전체 접근 장애로 중지합니다.
- `TargetClosedError` 등 브라우저 연결 종료를 감지하면 해당 배치를 중단하고 복구 가능한 체크포인트를 남깁니다.
- 배치 watchdog(기본 1,200초)에 걸리면 작업을 취소하고 `BATCH_WATCHDOG_TIMEOUT` 로그를 남깁니다.
- `results.csv`는 **문서 1건 완료마다 임시 파일에 쓴 뒤 `os.replace()`**로 원자적으로 갱신합니다. 전체 작업이 중단되어도 이전에 완료된 항목을 재사용하려는 설계입니다.
- 단, PC 강제 종료/디스크 오류/작업 디렉터리 삭제를 가로막지는 못합니다. 종료 시 `if: always()` 결과 업로드도 네트워크·디스크 오류로 실패할 수 있으므로 **외부 체크포인트 원격 보관을 강화해야 합니다**.

## 7. 로그와 결과를 원격에서 확인하는 방법

### 7-1. 확인 기준

- `ops/latest_scribd_run.json`의 `run_id`를 읽습니다. 파일의 `status: workflow_started`는 시작 기록에 불과합니다.
- 다음 링크의 해당 실행에서 `jobs.audit.status` 및 `jobs.audit.conclusion`을 조회합니다.
- `Get jobs` → `Get job steps` → **실패/진행 중인 정확한 단계** 확인 → 종료 후 `Get job logs`로 원인 분석합니다.
- `PREVIEW_RESULT` 한 줄은 문서 하나의 처리 결과, `FINAL_REVIEW_SUMMARY`는 누적 결과입니다.
- GitHub Actions의 job `success`는 **파이썬 프로세스가 정상 완료되었다는 뜻**이지 문서별 미리보기 또는 전체 콘텐츠 확보 성공의 증거가 아닙니다.

### 7-2. 주요 로그 문자열

| 로그 키 | 해석 및 대응 |
|---|---|
| `Connected to GitHub` / `Listening for Jobs` | 러너 대기, 현재 크롤링 수행 여부와는 별개 |
| `GUI_PREFLIGHT` | Windows GUI SessionId 검사 통과 여부. 눈으로 보이는 Chrome 증명은 아님 |
| `QUEUE total=... excluded_previous=... eligible_new=...` | 전체 입력과 중복 제외·신규 처리 대상 수 |
| `SELF_TEST_OK` | 체크포인트 I/O·중복 제외·async timeout 자체시험 통과 |
| `PROBE_LIMIT selected=10` | 사전시험으로 ID 10개 선택 |
| `SMOKE_TEST_RESULT` | 이번 신규 10개 처리 성적, 본수집 게이트 결정 |
| `PREVIEW_RESULT` | ID별 상태 / 탭 번호 / 누적 수행수 |
| `RETRY` | 특정 ID 재시도; 예외 유형 로그도 확인 |
| `REQUEUE_PRIOR_FAILURES` | 이전 오류/시간초과 항목 재실행 대상으로 복원 |
| `STOP_SITE_CHALLENGE` | 사이트 접근 차단, 즉시 전체 작업 중단 |
| `BATCH_WATCHDOG_TIMEOUT` | 페이지/worker 정지로 배치 최대 시간 초과 |
| `BROWSER_FAILURE` | 브라우저 시작 또는 전체 컨텍스트 장애 |
| `FINAL_REVIEW_SUMMARY` | 누적 건수·상태별 분포·잔여수·종료 이유 |

### 7-3. 실증된 장애와 해결

| 사건 | 관측 사실 | 반영한 조치 |
|---|---|---|
| 러너 중복 연결 | 새 `run.cmd`에서 `A session for this runner already exists`, `Conflict` | Listener 중복 상태 확인 후 하나만 실행. 기존 등록 재설치 불필요 |
| 10탭 작업 장시간 정지 | 제목 조회(`page.title()`) 등 비한정 대기·종료 때 `TargetClosedError` | 제목 조회를 짧은 locator timeout으로 변경, 문서/배치 watchdog과 브라우저 재시작 적용 |
| Chrome이 뜨지 않음 | 브라우저 전에 366MB 과거 아티팩트 복원 단계에 막힘 | 대용량 사전 다운로드 제거, 저장소 내 방문 ID 체크포인트를 직접 사용 |
| 10건 시험 1건 오류 | 실행 43414135287에서 9/10 미리보기, 1 오류 | 전체 작업 중단 후 예외 원인 로깅·선택자 처리 수정 |
| 누적 CSV를 이번 10건으로 오판 | 실행 43414811324에서 사전시험 결과가 총 20행이 되어 검증식 실패 | 사전시험 전 안정 상태 ID 목록을 저장하고 **이번 신규 10건만** 채점 |
| 검증 후 대량 수집 | 실행 43415200492에서 smoke `success` → audit `success` | 실행번호·아티팩트·최종 CSV 로그로 성공 범위 확인 |
| Actions 저장공간 급증 | 대량 PNG를 매번 artifact로 업로드해 확인된 38개 아티팩트 약 1.12GB | 이미지·CSV·엑셀 별도 보관 후 해당 38개 아티팩트 삭제; 대량 PNG 기본 업로드 폐지 필요 |

## 8. 최종 결과 파일, 스토리지와 백업·삭제

### 8-1. 문서별 CSV 컬럼 (현재 엔진)

```text
document_id,source_url,final_url,status,http_status,
page_title,heading,preview_visible,body_excerpt,screenshot,error,utc
```

- 예: `document_id`는 대상 고유 ID. 다른 사이트에선 `{site}:{native_id}` 같은 복합 식별자 권장.
- `status`는 **방문/페이지 인식** 상태. 별도의 `content_verified`, `catalog_classified`, `ocr_verified` 지표를 두는 것이 바람직.
- `screenshot`에는 작업 디렉터리 안의 파일 경로가 저장되므로 클라우드에서 그 경로 그대로 이미지를 열 수 있는 것은 아닙니다.
- `summary.json`은 `queue_total`, `previously_attempted_excluded`, `eligible_new_total`, `newly_attempted`, `remaining_new`, `preview_visible_new`, `status_counts`, `stop_reason` 등을 포함합니다.

### 8-2. 실제 저장과 정리 현황

- 실행 [43415200492](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492)은 최종 `audit`가 `completed/success`였습니다.
- 당시 ZIP은 GitHub Actions 저장공간을 소비했습니다. 별도 보관 후 기존 특정 38개 아티팩트는 삭제되어, **현재 과거 아티팩트 다운로드 링크는 작동하지 않습니다**. 향후 문서는 `Actions 실행 로그`를 증빙으로 삼고, 이미지·CSV 원본은 별도 저장소에 보관합니다.
- 2026-11-13 백업 위치: ChatGPT 파일 보관함 `/Scribd_수집백업_2026-11-13` — 분석 엑셀, 원본 CSV ZIP, PNG 보관 ZIP 6개. **이 경로는 Google Drive가 아닙니다.**
- 반복 실행할수록 PNG를 GitHub artifact에 14일 보관하면 비용/공간이 증가합니다. **기본은 CSV/JSON만 업로드**하고, PNG는 필요할 때만 분리 보관하거나 용량 제한/보존 정책 적용.
- 삭제 전 반드시 별도 백업의 파일 수·문서 ID·ZIP CRC/해시와 접근 가능 여부를 검증하고, 삭제는 확인된 artifact ID만 정확히 지정합니다. 절대로 전체 저장소·다른 작업의 아티팩트를 일괄 삭제하지 않습니다.

## 9. 다른 사이트에서도 쓰기 위한 범용화 설계 (제안·미구현)

아래는 이미 있는 **Windows 원격 브라우저 실행 엔진을 공통 제품으로 만드는 다음 개발 범위**입니다. 실제로 범용 동작이 완성되었다고 단정하면 안 됩니다.

### 9-1. 권장 모듈 분리

| 모듈 | 인터페이스 / 책임 | 현재 상황 |
|---|---|---|
| `controller` | GitHub Actions 실행 요청, 작업번호 기록, 상태 수집, 작업 취소 | Scribd 전용 YAML로 부분 구현 |
| `runner-agent` | Windows 환경 확인, Chrome 시작, GUI 세션 진단, 하트비트 | self-hosted runner + PowerShell로 부분 구현 |
| `job-schema` | `job_id`, `site`, `seed_file`, `mode`, `limit`, `max_tabs`, `timeout`, `checkpoint`, `output` | 공통 스키마 미구현 |
| `site-adapter` | 사이트별 URL 생성, DOM 선택자, 페이지 분류, 페이징/검색, 수집 허용범위 | Scribd 전용 로직만 구현 |
| `browser-pool` | Chrome/context/page worker, 동시성, 재시도, 브라우저 재생성 | 10개 페이지 작업과 batch recycle 구현 |
| `checkpoint-store` | `job_id + site + item_id` 기준 재실행·완료·오류 기록, 중복 방지 | 로컬 CSV+ID 파일 부분 구현 |
| `observability` | 구조화 로그, 실행번호, PC/브라우저 식별, 단계별 ETA가 아닌 상태·오류 원인 | Actions 로그와 포인터 파일 부분 구현 |
| `quality-gate` | 소량 실사이트 시험 → 성공률·오류율 점검 → 자동/수동 본작업 | Scribd 전용 10건 게이트 구현 |
| `exporter` | 통합 CSV/JSON/Excel/이미지 백업, 목적지별 업로드 | 일부 수동 통합; 공용 모듈 미구현 |
| `storage-policy` | 이미지 중복 제거, 보존일, 저장용량 제한, 백업 확인 후 삭제 | 과거 수동 정리만 수행 |

### 9-2. 사이트별 설정 예시 (설계 예시, 현재 코드에서 바로 실행되지 않음)

```yaml
job_id: example-20261113-001
site: example-public-site
mode: public_metadata_only
seed_file: seeds/example_ids.csv
runner_labels: [self-hosted, Windows]
browser:
  engine: chrome
  headless: false
  max_tabs: 10
  batch_size: 80
  per_item_timeout_sec: 80
  retry_count: 1
quality_gate:
  sample_size: 10
  minimum_success_rate: 0.8
checkpoint:
  key: [site, item_id]
output:
  csv: true
  json: true
  screenshots: failure_only
  artifact_retention_days: 7
  max_artifact_mb: 25
```

**보안/법적 한계:** 로그인 우회·유료 데이터 무단 취득·CAPTCHA 우회·사이트의 접근 통제를 회피하는 기능으로 확장하지 않습니다. 대상 사이트의 허용 범위와 이용약관을 검토해야 합니다. 웹사이트별 요청 속도·robots 및 서버 부하 관리도 별도 설계가 필요합니다.

### 9-3. 다음 개발 우선순위

1. **사이트 독립화:** Scribd 전용 URL/ID/선택자를 `site-adapter`로 추출하고, Chrome 및 checkpoint 엔진은 공통 모듈로 보존.
2. **실제 화면 가시성 검증:** SessionId 외에 Windows 현재 active console session, Chrome PID/창 제목, 실행 전후 화면 증빙(개인정보 비노출)을 로그로 남김. '브라우저 창이 실제 보였다'는 사실은 추정하지 않음.
3. **작업 상태 저장:** `ops/latest...json`의 시작시점 기록만으로는 부족하므로 단계별 상태/마지막 진행시각/최종 conclusion까지 갱신하고 stale heartbeat를 감지.
4. **작업 분리 및 개입:** `smoke`와 `bulk`를 별도 job으로 분리, 확실한 성공 기준/승인 정책을 도입, `stop`과 `resume` API 제공. 사이트 차단 시 즉시 중지.
5. **범용 checkpoint DB:** 로컬 파일뿐 아니라 외부 저장소의 직전 완료 위치를 확인해 PC 재부팅·러너 교체 후에도 이어 하기.
6. **스토리지 최적화:** 기본 결과는 CSV/JSON, PNG는 오류·표본 중심. 기존 이미지 재사용·중복 탐지와 용량 상한 적용.
7. **결과 품질 분리:** 방문 완료, 화면 표시, 제목 확보, 목표 자료인지, 정규화 완료, 원문 전체 확보 여부를 별개 컬럼으로 저장.
8. **결과물 단순화:** 관리 화면/엑셀 기본 열은 `자료명 | URL | 구분 | 학년 | 학기 | 과목 | 유형`, 기술 로그는 별도 보관.
9. **재현성·보안:** 실행 시 커밋 SHA 고정, 최소 권한, 자격증명 비공개, 데이터 출처와 라이선스 정책 기록.

## 10. 재개발 시 요구되는 검증 시나리오

| 시나리오 | 성공 판정 |
|---|---|
| 러너 온라인/오프라인 | 온라인이면 job 받음; 오프라인이면 `queued`로 상태 공개, 처리했다고 오인하지 않음 |
| GUI Chrome 실행 | Chrome PID, 실제 대화형 세션, 브라우저 창 확인 증빙 모두 일치 |
| 샘플 3→10건 | 10건 각각 URL, 상태, 제목, 실패 이유, 필요시 PNG 저장 확인 |
| 브라우저 페이지 한 개 무응답 | 문서 제한시간 후 정확한 ID와 오류 로그, 다른 worker는 계속 진행 |
| Browser/Context 강제 종료 | `TargetClosedError` 감지, 진행 중이던 ID 보류, 기록된 작업은 중복 처리 방지 |
| 네트워크 단절/PC 절전 | 마지막 checkpoint 보존 및 자동/수동 재시작 후 재개 검증 |
| 동일 실행 중복 요청 | `concurrency` 및 작업 ID로 중복 실행 차단 또는 안전한 큐잉 |
| CAPTCHA/접근 차단 | 차단 탐지 후 자동 중지, 우회 시도 없음 |
| CSV에 누적 이전 결과 포함 | 신규 10건만 smoke 채점, 이전 10건과 혼합하지 않음 |
| PNG 선택자 오탐/미탐 | 이미지 실물 확인과 DOM 신호를 분리 기록, 미리보기 미탐으로 자동 재수집하지 않음 |
| 업로드 실패/디스크 부족 | 결과 보존/오류 표시, 대량 PNG 업로드 중단, 복구 경로 문서화 |
| 보관 아티팩트 삭제 | 외부 백업 검증 → 정확한 대상 ID만 삭제 → Actions에서 0건 확인 |

## 11. 다음 채팅 첫 지시문 — 그대로 사용 가능

> **HITEL Windows PC 원격 Chrome 크롤링 프레임워크 개발을 이어서 진행하십시오.**
>
> 기준 저장소는 `https://github.com/lyonbegin/hitel-scribd-runner`이며, 가장 먼저 `ops/HITEL_Windows_Chrome_Crawler_Framework_Handoff_20261113.md`, `.github/workflows/scribd-remaining-10tabs.yml`, `tools/zocbo/scribd_10tabs_remaining.py`의 실제 현재 코드를 읽으십시오.
>
> 목표는 Scribd 교재를 추가 수집하는 것이 아니라, **GitHub Actions → Windows self-hosted runner → 실제 대화형 Chrome → 다중 탭 크롤링 → 상태 로그/체크포인트 → 결과 저장 및 오류 복구** 구조를 *사이트에 독립적인 재사용 프레임워크*로 분리하는 것입니다. 기존 작동한 소스의 함수 내용을 우선 재사용하고, 검증되지 않은 독자 구현으로 대체하지 마십시오.
>
> 시작 순서: (1) 현재 구현과 미구현의 경계 확인 (2) 범용 job schema / site adapter / browser-pool / checkpoint-store 인터페이스 도출 (3) 실제 Windows GUI Chrome 3건 → 10건 → 제한된 배치 시험 (4) 오류 발생 시 로그·원인·복구 검증 (5) 테스트 통과 후에만 본 작업. 대용량 PNG의 GitHub 자동 업로드는 기본 비활성화하며 CSV/JSON 위주로 저장하십시오.
>
> **중요:** PC 화면을 실제로 확인하지 못했으면 확인했다고 말하지 마십시오. GitHub Actions `success`와 문서 내용 확보 성공은 구분하십시오. 기존 Scribd 6,137건 또는 2,623건 데이터를 임의로 재크롤링하지 마십시오. 사용자의 추가 승인이 없는 유료/비공개 자료 접근이나 접근통제 우회는 하지 마십시오. 결과는 실제 실행번호, 단계별 로그, 파일 증빙으로 보고하십시오.

## 12. 원본 근거 링크

- 저장소: <https://github.com/lyonbegin/hitel-scribd-runner>
- 핵심 워크플로: <https://github.com/lyonbegin/hitel-scribd-runner/blob/main/.github/workflows/scribd-remaining-10tabs.yml>
- Playwright 원본 엔진: <https://github.com/lyonbegin/hitel-scribd-runner/blob/main/tools/zocbo/scribd_10tabs_remaining.py>
- 실행번호 포인터: <https://github.com/lyonbegin/hitel-scribd-runner/blob/main/ops/latest_scribd_run.json>
- 최종 검증 성공 실행: <https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43415200492>
- 기존 첫 실패·9/10 시험 실행: <https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43414135287>
- 누적 CSV 검증식 실패 실행: <https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43414811324>
- 이미지 품질 감사: <https://github.com/lyonbegin/hitel-scribd-runner/blob/main/ops/scribd-image-inventory-20261113.md>

---

**최종 결론:** 검증된 재사용 가능 요소는 **GitHub 클라우드에서 사용자 Windows PC 작업을 원격 호출하고, 설치된 Chrome을 Playwright로 제어하고, 다중 탭·타임아웃·체크포인트·로그로 수집을 운영하는 실행 방식**입니다. **다른 사이트 전용 로직까지 이미 범용화되어 있다고 주장하지 않습니다.** 다음 개발은 이 실제 구현을 기준으로 사이트 종속성을 걷어내는 작업부터 시작합니다.