# HITEL Universal AI — 외부 프로젝트 API 연동 개발자 가이드 (v0.2 — 이벤트 알림)

작성 기준: 2026-11-27 KST. 이 문서는 실제 GitHub Actions 백엔드 소스에 대응하는 계약이다. 다른 AI 또는 프로그램은 이 문서를 읽고 기존 엔진을 수정하지 않고 프로젝트를 등록하고 실행 상태 및 결과를 조회한다.

## 1. 접속 정보와 중요한 전제

| 항목 | 값 |
|---|---|
| 관리 화면 | https://lyonbegin.github.io/hitel-scribd-runner/ |
| API 기본 URL | https://api.github.com/repos/lyonbegin/hitel-scribd-runner |
| 작업 브랜치 | feature/hitel-universal-ai-ui-api-20261127 |
| 실행 workflow | universal-ai.yml |
| 엔진 | universal/engine.py |
| Watchdog | universal/watchdog.py |
| 이벤트 발행 및 전달 | universal/notifications.py |
| API 기술 계약 원문 | universal/API.md |

GitHub Pages는 정적 UI이고 GitHub Actions가 실행 백엔드이다. 독립적인 /api/projects 또는 /api/run HTTP 서버는 존재하지 않는다. 아래 GitHub REST 엔드포인트가 실제 외부 연동 API이다. 기존 HITEL AI 서버는 Actions 내부의 AI 전송 계층으로만 이용한다. 별도 상시 실행 서버를 만들 필요가 없다.

**공개 저장소 주의:** 현재 저장소는 public이다. 등록한 지시문, 목록, 결과, checkpoint 및 Git 기록이 공개될 수 있다. 공개 가능한 합성 데이터 또는 공개 사용 권한이 있는 자료만 등록한다. 비공개 자료·개인정보·인증정보는 절대로 이 저장소에 넣지 않는다. 비공개 업무는 동일 엔진과 workflow를 별도 private 저장소에 설치하고 권한 및 브랜치 설정을 검증해야 한다. 이 문서는 다중 사용자 격리나 비공개 데이터 저장을 보장하지 않는다.

## 2. 인증

사용자가 승인한 GitHub 연결 도구 또는 최소 권한 GitHub token을 이용한다. 대상 저장소에 Contents 읽기/쓰기, Actions 읽기/쓰기 권한이 필요하다. 별도 API 키가 공개 문서에 제공되는 것은 아니다. token은 실행 환경 변수 GH_TOKEN 등으로 전달하고 채팅, URL, 소스, 프로젝트 JSON, 로그, 공개 파일에 넣지 않는다.

HTTP 헤더:
- Authorization: Bearer <승인된 GitHub 토큰>
- Accept: application/vnd.github+json
- Content-Type: application/json
- X-GitHub-Api-Version: 2022-11-28

연결된 AI가 GitHub connector로 파일을 생성/읽을 수 있다면 같은 REST 계약을 해당 도구로 수행해도 된다. 해당 연결에 workflow dispatch 권한이 없을 경우 지원되는 인증 경로로 실행해야 하며 권한 없이 실행 성공이라고 보고하지 않는다.

## 3. 엔드포인트 전체 목록

아래 경로에는 기본 URL을 앞에 붙인다. {id}, {run_id}, {artifact_id}, {branch}는 실제 값으로 치환한다. 쿼리 ref/branch 값은 URL 인코딩한다.

| 메서드 | 경로 | 기능 / 성공 |
|---|---|---|
| GET | / | 저장소 접근/공개 여부, 200 |
| GET | /contents/universal/projects?ref={branch} | 프로젝트 목록, 200 |
| GET | /contents/universal/projects/{id}/project.json?ref={branch} | 설정 조회 및 blob SHA, 200 |
| PUT | /contents/universal/projects/{id}/project.json | 신규 등록 201 / 상태 변경 200 |
| POST | /actions/workflows/universal-ai.yml/dispatches | 명시적 실행, 통상 204 (실행 완료 아님) |
| GET | /actions/workflows/universal-ai.yml/runs?branch={branch}&per_page=20 | 해당 workflow 실행 목록, 200 |
| GET | /actions/runs/{run_id} | 실행 상태 및 conclusion, 200 |
| GET | /actions/runs/{run_id}/jobs | job/step 상태, 200 |
| GET | /actions/jobs/{job_id}/logs | GitHub 실행 로그 다운로드/리다이렉트 |
| GET | /contents/universal/state/{id}/state.json?ref={branch} | 업무별 checkpoint 및 결과, 200 |
| GET | /contents/universal/state/{id}/results.csv?ref={branch} | CSV 결과, 200 |
| GET | /contents/universal/state/{id}/events.json?ref={branch} | 진행 이벤트·전송 결과, 200 |
| GET | /actions/runs/{run_id}/artifacts | checkpoint artifact 목록, 200 |
| GET | /actions/artifacts/{artifact_id}/zip | artifact ZIP 다운로드/리다이렉트 |
| POST | /actions/runs/{run_id}/cancel | GitHub 실행 취소 요청, 통상 202 |

상태 조회와 결과는 GitHub Contents API의 content 필드(base64)를 UTF-8로 디코딩한다. CSV는 UTF-8 BOM 포함이다. 404는 해당 경로가 아직 생성되지 않았거나 권한이 없음을 의미할 수 있으므로 단순히 성공/실패로 단정하지 않는다.

## 4. 프로젝트 JSON — 모든 업무가 사용하는 입력 계약

실행 엔진에는 아래 JSON 하나를 등록한다. UI에서 지시문을 직접 작성하거나 CSV, TXT, JSON, JSONL 파일을 업로드하면 같은 구조로 변환된다. 외부 프로그램도 같은 JSON을 만든다.

```json
{
  "project_id": "catalog-demo-001",
  "command": "start",
  "provider": "mock",
  "task_id": "",
  "batch_size": 2,
  "prompt": "각 자료 제목을 읽고 category 및 reason을 반환하십시오.",
  "fields": {
    "category": "string",
    "reason": "string"
  },
  "records": [
    {"record_id": "1", "title": "공개 예제 자료 A"},
    {"record_id": "2", "title": "공개 예제 자료 B"}
  ]
}
```

| 필드 | 필수 규칙 |
|---|---|
| project_id | 영문 소문자로 시작, 영문 소문자/숫자/하이픈, 총 3~64자. 새 업무마다 고유 ID |
| command | start 또는 pause |
| provider | mock 또는 hitel |
| task_id | mock은 빈 문자열 가능. hitel은 새 승인 Task ID (기존 scribd-18109 사용 금지) |
| batch_size | 1~50 정수, 초기 시험 2~5 권장 |
| prompt | 비어 있지 않은 업무 지시문 |
| fields | 결과 열 이름: string / number / boolean. 최소 1개. key, record_id, status는 예약어 |
| records | 비어 있지 않은 객체 배열. 각 record_id는 중복 없는 문자열. 나머지 입력 열은 자유 |
| notifications | 선택: 외부 알림 채널, 이벤트 목록, heartbeat 주기. 상세 계약은 12절 |

현재 검증기는 JSON Schema 전체가 아닌 위 단순 타입 매핑을 사용한다. 입력의 record_id는 AI의 답변으로 덮어쓰지 않는다. 엔진이 A01, A02 등의 배치 키를 부여하고 정확한 순서, 행 수, 필드 및 타입을 검증한 뒤 원본 ID를 결합한다. 업무별 enum, 의미적 정확도, 제목 재대조 등은 현 버전에서 범용적으로 보장하지 않는다.

제한: 코드상 최대 100,000개 records이나 실제 단일 파일 API 및 저장소 크기 한계가 먼저 적용된다. UI는 개별 파일 700KB, 프로젝트 JSON 850KB 제한. 외부 API도 v0.1에서는 850KB 이하 UTF-8 JSON으로 운용 권장. 배치 최종 프롬프트는 24,000자 이하. 첨부 바이너리/PDF, XLSX 입력 및 출력, 자료 분할 매니페스트, 다중 워커 병렬 처리는 아직 미구현. 텍스트 참고자료는 공개 가능한 범위에서 records의 추가 속성 또는 prompt에 포함한다.

## 5. 외부 프로그램의 실행 순서

1. 프로젝트 ID를 새로 정한다. 기존 프로젝트 GET으로 충돌 여부를 확인한다. 기존 ID가 있으면 새로 등록하지 말고 기존 자료와 설정을 확인한다.
2. JSON을 UTF-8 바이트로 만든 다음 Base64 인코딩한다. PUT Contents의 body는 다음 구조다. branch를 생략하지 않는다.

```json
{
  "message": "Create HITEL project catalog-demo-001",
  "branch": "feature/hitel-universal-ai-ui-api-20261127",
  "content": "<프로젝트 JSON 전체의 Base64>"
}
```

3. PUT 성공 후 GitHub commit SHA를 저장한다. 사용자 인증으로 프로젝트 경로에 push되면 workflow가 자동 시작될 수 있다. 먼저 실행 목록을 조회한다. GitHub Actions 자체 GITHUB_TOKEN으로 생성한 commit은 일반 push workflow를 발생시키지 않을 수 있다.
4. 실행이 아직 확인되지 않으면 인덱싱 지연을 고려하여 재조회한다. 실행이 없음을 확인한 다음 명시적으로 1회 dispatch한다.

```json
{
  "ref": "feature/hitel-universal-ai-ui-api-20261127",
  "inputs": {
    "handoff": "external-catalog-demo-001",
    "depth": "0"
  }
}
```

5. dispatch 응답 204는 접수다. 실제 run ID를 조회한다. 전송 응답이 불확실하면 동일 run-name / handoff를 조회하고 무조건 다시 POST하지 않는다.
6. 프로젝트 state.json을 10~30초 간격으로 조회한다. workflow 성공만으로 해당 프로젝트의 완료를 판단하지 않는다. 여러 프로젝트가 한 workflow에서 처리될 수 있다.
7. state.status=complete와 검증 결과 건수 일치를 확인하고 results.csv를 다운로드한다. mock과 실제 AI 결과를 구별한다.
8. blocked 또는 watchdog 예산 소진 시 로그를 분석하고 운영자 판단을 받는다. 기존 결과를 삭제하거나 실패를 성공으로 바꾸지 않는다.

## 6. Python 실행 예제 (표준 라이브러리만 사용)

아래 예제는 공개 가능한 합성 데이터로 MOCK 프로젝트 등록, 진행 조회 및 결과 저장을 시험한다. GH_TOKEN 환경변수에는 본인이 승인한 권한 있는 토큰을 넣는다. 예제에서 실제 AI를 자동 활성화하지 않는다.

```python
import base64, json, os, time, uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from pathlib import Path

BASE = "https://api.github.com/repos/lyonbegin/hitel-scribd-runner"
BRANCH = "feature/hitel-universal-ai-ui-api-20261127"
REF = "?ref=" + quote(BRANCH, safe="")
TOKEN = os.environ["GH_TOKEN"]

def api(method, path, body=None):
    req = Request(BASE + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28"
        }, method=method)
    with urlopen(req, timeout=45) as response:
        raw = response.read()
        return json.loads(raw) if raw else None

def read_file(path):
    try:
        f = api("GET", path + REF)
    except HTTPError as exc:
        if exc.code == 404:
            return None, None
        raise
    if f.get("encoding") != "base64":
        raise RuntimeError("파일 인코딩 또는 크기 제한 확인 필요")
    return f, base64.b64decode(f["content"])

def register(project):
    path = "/contents/universal/projects/" + project["project_id"] + "/project.json"
    old, _ = read_file(path)
    if old is not None:
        raise RuntimeError("기존 프로젝트 ID: 덮어쓰기 금지")
    raw = json.dumps(project, ensure_ascii=False).encode("utf-8")
    if len(raw) > 850000:
        raise ValueError("v0.1 프로젝트 크기 제한")
    return api("PUT", path, {
        "message": "Create public synthetic HITEL project " + project["project_id"],
        "branch": BRANCH,
        "content": base64.b64encode(raw).decode("ascii")
    })["commit"]["sha"]

pid = "api-demo-" + uuid.uuid4().hex[:12]
project = {
    "project_id": pid, "command": "start", "provider": "mock",
    "task_id": "", "batch_size": 2,
    "prompt": "Classify synthetic sample items.",
    "fields": {"category": "string", "score": "number"},
    "records": [{"record_id": str(i), "text": "Synthetic item " + str(i)}
                for i in range(1, 4)]
}

# 신규 생성은 한 번만. 전송 오류 시 기존 파일 GET으로 확인하고 재등록 금지.
commit = register(project)
print("PROJECT", pid, "COMMIT", commit)

# 실행 목록 확인 (자동 push trigger가 없으면 별도 승인된 dispatch 필요)
runs_path = "/actions/workflows/universal-ai.yml/runs?" + urlencode({
    "branch": BRANCH, "per_page": 20
})
print([(r["id"], r["status"], r["head_sha"])
       for r in api("GET", runs_path)["workflow_runs"][:5]])

state_path = "/contents/universal/state/" + pid + "/state.json"
for _ in range(60):
    _, raw = read_file(state_path)
    if raw:
        state = json.loads(raw)
        print(state["status"], state.get("mock_completed", 0), "/", state["total"])
        if state["status"] == "blocked":
            raise RuntimeError("Blocked: " + str(state.get("error", "")))
        if state["status"] == "complete":
            assert state["provider"] == "mock"
            assert state["verified_ai_completed"] == 0
            assert state["mock_completed"] == len(project["records"])
            _, csv_bytes = read_file("/contents/universal/state/" + pid + "/results.csv")
            if csv_bytes is None:
                raise RuntimeError("CSV not found")
            Path(pid + ".csv").write_bytes(csv_bytes)
            break
    time.sleep(10)
else:
    print("현재 완료 미확인. 같은 project_id를 조회하십시오. 재등록하지 마십시오.")
```

이 예제는 복사 가능한 사용 예시이며 이 문서 작성 중 신규 프로젝트 실행 시험을 하지 않았다. 실제 운영 엔진의 기존 합성 데이터 시험 근거는 아래 10절에 있다.

## 7. 중지 / 재개 / 취소

설정 파일을 GET하여 blob sha 및 원본 JSON을 얻는다. command만 pause 또는 start로 변경하고 동일 파일에 PUT한다. body에 message, branch, content 및 기존 파일의 sha를 넣어 동시 수정 충돌을 막는다. 지시문, 입력, 필드, provider 변경 시 새 project_id를 사용한다. notifications와 command는 정의 해시에서 제외되어 기존 프로젝트 설정을 안전하게 변경할 수 있다. 알림 설정은 다음 Actions 실행부터 적용한다.

pause는 다음 폴링 또는 배치 진입 시 반영되는 협조적 중지다. 이미 완료되거나 전송된 AI 작업을 원격 취소하지 않는다. 엔진이 실행 중이 아닐 경우 state.json이 과거 상태로 남을 수 있으므로 project.command도 조회한다. blocked 상태는 pause/start만으로 자동 해제되지 않는다. GitHub run cancel은 GitHub 실행만 취소한다. 기존 제출은 먼저 조회·조정해야 한다.

## 8. 진행 상태와 성공 판정

| 상태/필드 | 의미 |
|---|---|
| ready / running | 준비 / 처리 중 |
| pending | 다음 조회·실행 필요 |
| paused | 협조적 중지 |
| blocked | 오류 또는 반복 무진전으로 중단 |
| complete | 해당 project의 모든 입력 처리 종료 |
| total | 입력 행 수 |
| verified_ai_completed | 실제 HITEL 응답 검증 건수 |
| mock_completed | 합성 시험 건수 |
| results | 원본 record_id + 결과 필드 배열 |
| definition_sha | command를 제외한 설정 SHA-256 |
| batches | 요청 식별자 및 배치별 검증 정보 |
| no_progress | 무진전 횟수 |
| error | 오류 설명 (존재하는 경우) |

실제 AI 완료 기준: provider=hitel, status=complete, verified_ai_completed=total, 결과 파일 및 record_id 일치. 이는 응답과 형식의 검증이지 모든 의미적 판정이 정답이라는 보증은 아니다. mock은 verified_ai_completed=0이며 실제 AI 완료로 계산하지 않는다.

Watchdog는 실행 종료 후 미완료 프로젝트를 확인하여 후속 Actions를 연결한다. 후속 깊이 제한 20, 반복 무진전 제한 3. 예약형 상시 watchdog는 설치하지 않았다. 인프라 오류/취소 시 자동 복구가 항상 보장되지는 않는다.

## 9. 실제 AI 연결의 조건

외부 프로그램이 provider=hitel로 등록할 수 있는 JSON 형식은 존재하지만, 등록만으로 AI가 실행되는 것은 아니다. 운영자가 저장소 HITEL_ALLOW_LIVE=true 및 새 Task ID에 대한 기존 HITEL 서버의 GitHub OIDC 생산자 권한, AI 계정/워커 연결을 승인해야 한다. 기존 종료된 Scribd Task ID를 재사용하지 않는다. 승인된 태스크의 서비스 제한을 존중한다. 이 프레임워크는 외부 호출자가 내부 인증을 대신 발급하거나 서버 승인 없이 AI를 실행하도록 제공하지 않는다.

신규 프로젝트마다 고유 project_id 및 승인된 task_id를 사용한다. 기존 엔진을 임의 수정하지 않는다. 실제 AI smoke 시험 2~5건에서 응답과 저장, 재개를 검증한 후 대량 입력으로 진행한다.

## 10. 실제 검증 근거

- 기존 18,088건 Scribd 성과 보존: https://github.com/lyonbegin/hitel-scribd-runner/tree/release/hitel-ai-batch-framework-20261127
- 범용 엔진 오프라인 회귀시험 7/7 및 watchdog 후속 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45907244721
- 후속 Actions 합성 자료 3건 / 2배치 및 종료: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45907281993
- 시험 결과 CSV: https://github.com/lyonbegin/hitel-scribd-runner/blob/feature/hitel-universal-ai-ui-api-20261127/universal/state/demo-mock-001/results.csv
- Pages 배포 성공: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45915626971
- Pages 배포 수정 커밋: 1cf74ee2bd56437f2c3a9b16d9c3c00aa42abd44

현재 검증된 것은 GitHub Actions 기반 mock 작업, 체크포인트, 자동 후속 실행, CSV 저장, Pages 배포 및 12절의 이벤트 발행 시험이다. 신규 실제 AI 서버 Task 연동, 브라우저 UI 전체 동작, 대용량 분할 처리, 기존 Scribd 워커 자동 재시작 기능 전체는 아직 검증·이식되지 않았다. 별도 REST 서버가 있는 것처럼 안내하지 않는다.

## 11. 다른 채팅의 AI에게 전달할 지시문

> 이 공개 API 연동 문서를 먼저 읽고 기존 HITEL Universal AI GitHub Actions 백엔드를 그대로 사용하십시오. 새로운 엔진, 서버, 워크플로를 임의로 만들거나 기존 Scribd 작업을 변경하지 마십시오. 제 업무의 입력자료를 고유 record_id가 있는 records로 구성하고, 지시문 prompt, 출력 fields, 배치 크기를 정의하십시오. 승인된 GitHub 연결 도구 또는 권한 있는 토큰을 사용하여 새 project_id로 프로젝트 JSON을 등록하십시오. 비공개 자료는 public 저장소에 올리지 마십시오. 기존 task 권한을 확인하고 실제 AI 연결이 승인되어 있을 때만 provider=hitel을 사용하십시오. 먼저 소량 시험 후 실제 Actions ID와 프로젝트 state를 조회하십시오. 검증된 응답만 성공으로 집계하고 중복 POST 및 기존 결과 삭제를 금지하십시오. 결과 CSV와 완료·미완료 건수, 로그 및 오류를 보고하십시오. 엔진이나 API 권한이 부족하면 그 사실을 명확히 보고하고 우회하지 마십시오.


## 12. 이벤트 기반 보고·웹훅 API (v0.2)

### 12.1 구조 및 ChatGPT Work 연결의 구분

GitHub Actions에서 실제 작업이 변할 때 이벤트를 생성한다. GitHub Pages가 백그라운드에서 AI를 실행하거나 알림을 보내는 구조가 아니다.

```text
프로젝트 등록/실행 -> GitHub Actions engine
  -> 상태 변화 또는 배치 검증, 활성 heartbeat
  -> events.json 및 state.json을 Git에 영속화
  -> 선택한 채널로 이벤트 전달 시도
     (none / github_pr / webhook)
  -> 전달 결과 영속화
  -> 승인된 수신기 또는 지원되는 ChatGPT Work 이벤트 트리거
  -> 사용자 알림 (수신 측의 별도 승인 및 동작 검증 필요)
```

ChatGPT Work는 공식적으로 지원되는 연결 앱의 활동(예: 승인된 GitHub 저장소의 PR 활동)에 반응하는 이벤트 기반 작업을 제공한다. 일반 ChatGPT 대화에 임의의 URL로 POST하여 직접 메시지를 삽입하는 공개 엔드포인트를 이 문서가 제공하는 것은 아니다. 현재 대화 환경에서는 이벤트 소스 조회가 404로 실패해 실제 ChatGPT 트리거를 생성하지 못했다. 임의의 수신 URL이나 대화 ID, 내부 ChatGPT API를 추측하여 사용하지 않는다.

공식 도움말:
- https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
- https://help.openai.com/en/articles/11487775-connected-apps-in-chatgpt
- https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex

### 12.2 프로젝트 설정: notifications

기존 project.json의 루트에 다음 선택 필드를 추가한다. 생략 시 외부 전송 없이 이벤트를 저장한다.

```json
{
  "notifications": {
    "channel": "github_pr",
    "pr_number": 123,
    "heartbeat_seconds": 60,
    "events": [
      "project.started",
      "request.prepared",
      "request.accepted",
      "batch.verified",
      "project.pending",
      "project.paused",
      "project.blocked",
      "project.completed",
      "heartbeat"
    ]
  }
}
```

위의 123은 예시 번호다. 실제 승인된 열린 PR 번호로 변경한다. 프로젝트 ID와 PR 번호를 혼동하지 않는다.

| 필드 | 값과 동작 |
|---|---|
| channel | none: 이벤트 기록만; github_pr: 승인 PR에 이벤트 댓글; webhook: 관리자 지정 HTTPS 수신기로 서명 POST |
| pr_number | github_pr 선택 시 양의 정수. 실제 열린 PR이며 관리자 allowlist에 포함되어야 함 |
| heartbeat_seconds | 30~3600초 정수, 기본 60 |
| events | 외부 전송할 이벤트 문자열 배열. 비워 두면 외부 전송 없음 |

기본 외부 전송 이벤트는 project.started, batch.verified, project.pending, project.paused, project.blocked, project.completed, heartbeat이다. request.prepared와 request.accepted는 필요 시 추가한다. 모든 이벤트의 기록은 외부 전송 필터와 별개다.

### 12.3 이벤트 발생 조건

| 이벤트 | 생성 조건 |
|---|---|
| project.started | 프로젝트 이벤트 상태 초기화 |
| request.prepared | 실제 AI 제출 전에 요청 식별자/attempted checkpoint 저장 |
| request.accepted | 서버 job_id/room_id 확보 |
| batch.verified | 검증된 결과 배열 길이가 증가함 |
| project.pending | 엔진 상태가 pending으로 변경 |
| project.paused | 엔진이 pause 상태를 관찰하고 checkpoint에 반영 |
| project.blocked | 검증 오류 또는 무진전 예산 초과 등으로 blocked 전환 |
| project.completed | 전체 결과 수가 입력 수에 도달하여 complete 전환 |
| heartbeat | 활성 처리 중 주기 도달 시 다음 폴링 확인에서 생성 |

Heartbeat는 실행 중 상태 조회 지점에서 확인하므로 정확한 실시간 타이머가 아니다. HTTP 호출, Git 저장, backoff, runner 종료에 따라 지연될 수 있다. GitHub Actions가 종료된 뒤 별도 일정으로 계속 발생하지 않는다. runner가 갑자기 취소되거나 초기 시험/checkout 자체가 실패할 경우 프로젝트 이벤트를 남기지 못할 수 있다. 이 경우 GitHub Actions Runs/Jobs API 또는 GitHub 자체 알림으로 확인한다. Watchdog handoff 결과는 별도 Actions 로그에 남으며 현 버전의 프로젝트 웹훅 이벤트에는 포함되지 않는다.

### 12.4 이벤트 조회 API

```http
GET https://api.github.com/repos/lyonbegin/hitel-scribd-runner/contents/universal/state/{project_id}/events.json?ref=feature%2Fhitel-universal-ai-ui-api-20261127
```

응답은 GitHub Contents JSON이다. content를 Base64 디코딩하여 다음과 같은 구조를 읽는다.

```json
{
  "schema": "hitel.progress.v1",
  "project_id": "demo-events-001",
  "events": [
    {
      "payload": {
        "schema": "hitel.progress.v1",
        "event_id": "<SHA-256 기반 고유 이벤트 ID>",
        "sequence": 2,
        "event": "batch.verified",
        "occurred_at": "<UTC ISO-8601>",
        "project_id": "demo-events-001",
        "provider": "mock",
        "status": "running",
        "total": 3,
        "verified_ai_completed": 0,
        "mock_completed": 2,
        "no_progress": 0,
        "run_id": "45920741445",
        "repository": "lyonbegin/hitel-scribd-runner",
        "branch": "feature/hitel-universal-ai-ui-api-20261127",
        "run_url": "https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45920741445"
      },
      "channel": "none",
      "pr_number": null,
      "delivery": "recorded"
    }
  ]
}
```

event_id를 이용하여 동일 이벤트의 중복 보고를 방지한다. 이벤트는 원본 자료, 프롬프트, AI 답변 전문, 인증 토큰을 포함하지 않는다. 공개 저장소의 프로젝트 이름과 진행 메타데이터는 공개됨을 전제로 한다. 최근 500개의 이벤트가 state.json 및 events.json에 보존된다. 전체 장기 이력은 Git 커밋과 각 실행 artifact를 별도로 보존해야 한다.

전송 상태: recorded(외부 발송 없음), pending(발송 대기), attempted(발송 시도 체크포인트), accepted(수신 HTTP 2xx), not_configured(승인된 대상/설정 없음), rejected_http_NNN(HTTP 오류), uncertain(연결 등으로 결과 불명). accepted는 HTTP 수신기 접수 성공이며 ChatGPT가 답변하거나 사용자에게 알림을 보냈다는 뜻이 아니다. 불확실한 전송을 자동으로 무조건 반복하지 않는다. 과거 이벤트는 자동 재발송하지 않는다.

### 12.5 ChatGPT Work 알림 연결 (GitHub PR 활동 이용)

1. ChatGPT에서 기존 GitHub 연결이 활성화되고 대상 저장소 권한이 있는지 확인한다. Work의 이벤트 트리거 설정을 이용할 수 있는 계정/환경이어야 한다.
2. 알림용으로 사용자가 승인한 열린 PR을 선택한다. 별도 PR이 필요하면 담당자가 명시적으로 생성하며, 업무 브랜치를 main에 병합하는 것이 목적은 아니다.
3. GitHub 저장소 Settings > Secrets and variables > Actions > Variables에서 HITEL_NOTIFY_PR_ALLOWLIST에 허용할 PR 번호를 쉼표로 구분해 등록한다. 외부 사용자가 임의 PR에 댓글을 게시하도록 허용하지 않는다.
4. 프로젝트의 notifications.channel=github_pr 및 pr_number를 지정한다. 관리 화면에서도 같은 필드를 입력할 수 있다.
5. 해당 업무를 시작한 ChatGPT Work 대화에서 아래 지시문으로 지원되는 GitHub PR 이벤트 기반 작업을 설정한다. Trigger/Condition/Prompt 및 알림 설정을 확인하고 필요 권한을 승인한다. 현재 ChatGPT가 실제로 지원하는 PR 이벤트 유형을 선택한다.

> 이 프로젝트의 GitHub 이벤트 기반 진행 보고 작업을 설정하십시오. 저장소 lyonbegin/hitel-scribd-runner, 승인된 PR 번호 [번호]의 지원되는 PR 활동을 트리거로 사용하십시오. HITEL progress event가 발생하면 event_id 중복을 제거하고 프로젝트 ID [ID]만 보고하십시오. GitHub events.json 및 state.json에서 실제 결과를 읽어 전체 건수, 검증 완료, 미완료, 진행률, 오류 및 run 링크를 사용자에게 한국어로 알림하십시오. project.completed 또는 project.blocked에서는 최종 상태를 별도로 보고하십시오. 다른 프로젝트를 변경하거나 재실행하지 마십시오.

6. 외부 전송이 승인된 합성 시험 프로젝트로 GitHub PR 댓글 게시, Work 이벤트 트리거 실제 발생, 사용자 알림 수신을 각각 검증한다. PR 댓글이 해당 계정의 지원 트리거에 해당하는지는 사전 확인이 필요하다. PR 활동에 대한 일반 지원만으로 특정 댓글 이벤트나 원래 대화의 자동 재개를 보장할 수 없다. 수신이 확인되지 않았다면 완료로 판단하지 않는다.

### 12.6 승인된 HTTPS 수신기 연결 (일반 Webhook 채널)

별도 웹훅 수신 서비스가 이미 승인·구성되어 있는 경우에만 사용한다. ChatGPT의 내부 대화 URL을 웹훅으로 넣지 않는다. 외부 HTTPS 수신기 없이 Actions와 Pages만으로는 임의의 HTTP 요청을 받는 상시 서버를 만들 수 없다.

GitHub Settings > Secrets and variables > Actions > Secrets에 HITEL_EVENT_WEBHOOK_URL, HITEL_EVENT_WEBHOOK_SECRET을 등록한다. URL은 HTTPS여야 하고 서명키가 있어야 한다. URL 및 서명키는 공개 project.json이나 Pages에 넣지 않는다. 리다이렉트는 허용하지 않는다. v0.2에서는 저장소 전체에 관리자 지정 단일 웹훅 수신기를 사용하며 수신기는 project_id로 승인된 구독에 분배한다. 수신기·구독 라우팅 서비스는 이 저장소에 구현되어 있지 않다.

```http
POST <관리자가 등록한 HTTPS webhook URL>
Content-Type: application/json
X-HITEL-Event-ID: <payload.event_id>
X-HITEL-Timestamp: <Unix epoch seconds>
X-HITEL-Signature: sha256=<hex HMAC-SHA256>
```

body는 12.4절 payload 객체 자체의 UTF-8 JSON이다. 서명은 HMAC-SHA256(secret, timestamp + "." + raw_request_body)로 검증한다. 수신 측은 시간 오차 제한(예: 5분), 고유 event_id의 지속적인 중복 제거, 프로젝트별 권한 확인을 수행한다. 검증 성공 후 수신 사실을 저장하고 2xx를 반환한다. 전송 측 2xx는 접수만 의미한다. 수신 측 사용자 알림과 별도 확인 응답은 현재 구현하지 않았다.

### 12.7 관리 화면 및 외부 API 적용 방법

관리 화면 https://lyonbegin.github.io/hitel-scribd-runner/ 의 프로젝트 입력에서 알림 전달 채널, PR 번호, Heartbeat 간격, 이벤트 목록을 설정한다. 기존 프로젝트의 알림 설정 변경은 프로젝트 JSON의 notifications만 갱신한다. "이벤트·전송 기록" 버튼은 최근 30개 이벤트를 표시하며 "알림 설정 변경"은 기존 프로젝트의 해당 설정을 저장한다. 변경은 다음 Actions 실행부터 반영되며 현재 실행 중인 프로세스의 설정을 실시간 변경하지는 않는다.

외부 프로그램은 같은 프로젝트 JSON을 Contents API에 PUT하고 events.json을 GET한다. 기존 프로젝트 수정 시 먼저 GET한 blob SHA를 PUT body에 포함한다. 모든 진행 보고는 event_id/sequence 기반으로 중복 제거하고 GitHub 로그와 checkpoint의 실제 완료 수치를 사용한다.

### 12.8 검증 근거 및 제한

- 새 이벤트 모듈: universal/notifications.py
- 회귀시험: universal/test_notifications.py
- 14개 시험 전체 통과 및 합성 프로젝트 실제 처리: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45920741445
- 실제 이벤트 목록: https://github.com/lyonbegin/hitel-scribd-runner/blob/feature/hitel-universal-ai-ui-api-20261127/universal/state/demo-events-001/events.json
- 관리 화면 갱신 배포: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45920728795

실제 Actions의 합성 자료 3건에서 project.started, 두 번의 batch.verified, project.completed가 Git에 저장되었고 verified_ai_completed=0으로 구분되었다. heartbeat 시간 판정, HMAC 서명, 발송 전 checkpoint 및 중복 방지, allowlist 차단은 오프라인 시험을 통과했다. 외부 HTTPS 수신기/PR 알림 실전 연결 및 ChatGPT 사용자 알림 수신은 미검증이다. 실제 AI task 연동도 기존 제한을 따른다.
