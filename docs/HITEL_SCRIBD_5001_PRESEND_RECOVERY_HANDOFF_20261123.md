# HITEL Scribd 18,109 — 5,001~5,020 장애 복구 인수인계

작성: 2026-11-23. **전체 분류 작업은 중지 유지. 이 문서는 실행 허가가 아닙니다.**

## 1. 근거 및 현황

- 검증 완료 기준점: **5,000 / 18,109건**. [검증 저장 실행 44982635890](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44982635890), `HTTP_VERIFIED_BATCH 04981-05000 NEW 20 TOTAL_VERIFIED 5000`.
- 미완료: **5,001~5,020**, `job_769d8fbcaf034b8ebf5ca4e8d9ef3ce6`, 상태 `unknown`, `UPSTREAM_DELIVERY_UNKNOWN`, 전송 확인 및 응답 확인 `null`.
- [기존 분류 실패 44982742353](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44982742353): `web2api_local_request_started`까지만 보고, 최종 결과 없음.
- [기존 단독 Chrome 실행 44982380862](https://github.com/lyonbegin/procureflow/actions/runs/44982380862): `WEB2API_ADAPTER_HTTP_500_COMPOSER_NOT_FOUND`.
- HTTP 500이라는 사실만으로 무전송 증명이 되지는 않습니다. 과거 코드를 역추적한 결과, 본 건의 정확한 입력창 부재 예외는 `type_message` 또는 그 이전 readiness 단계에서 발생하며, **그 요청의 `click_send` 이전**입니다. 다른 job/Chrome 버전/HTTP 500에는 이를 일반화하지 않습니다.
- 지금도 서버의 기존 `unknown` 레코드는 그대로 유지하고, 어떤 AI 재전송도 하지 않았습니다.

## 2. 수정 소스 세 묶음

1. **공통 worker 및 Railway API** — [procureflow PR #74](https://github.com/lyonbegin/procureflow/pull/74), 브랜치 `fix/hitel-scribd-proof-recovery-20261123`.
   - `.github/scripts/w2a_patch_vendor_composer_20261120.py`: 기본 ChatGPT 경로에서 가시적 편집창을 재확인, 부재 시 `COMPOSER_PREFLIGHT_FAILED`를 보내고 전송 전에 중단. 과거에 실제 실패했던 `?model=auto` 대체 경로는 **기본 비활성** (`HITEL_SCRIBD_ALLOW_ALT_ROUTE=1`은 별도 무전송 실기동 검증 후에만).
   - `.github/scripts/hitel_room_tab_pool.py`: 비밀·질문 내용 없는 오류 단계 허용.
   - `.github/scripts/hitel_web2api_worker.py`: **로컬 POST 시작 이전** vendor event cursor 확보. 이 작업에서 `COMPOSER_PREFLIGHT_FAILED`를 보고, `TYPE_STARTED/SEND_DISPATCHED` 등의 신호가 전혀 없는 경우에만 `job.error / WEB2API_PRE_SEND_COMPOSER_NOT_FOUND`로 분류. 그 외 모든 HTTP 500은 기존대로 불확실 상태 보존.
   - `chatgpt-android-relay/web/hitel_recovery_policy.py`: 하나의 서버 권한 판정. 범용 `UPSTREAM_DELIVERY_UNKNOWN` 복구 금지. 정확한 과거 job ID + Chrome run 44982380862 + 오류문자열 + 저장 관찰값의 일치만 *예외적* 복구 후보로 인정. 신규 작업은 서명된 사전 오류 신호가 있어야 함.
   - `chatgpt-android-relay/web/task_worker_isolation.py`: 서버가 기존 요청/room/run/task를 대조하여 승인한 경우에만 `/recover`로 새 세대의 새 방과 요청을 **한 번** 생성. SQLite 복구 맵, old result, audit 보존. 응답 영수증 분실 후 GET/POST 동일 호출은 기존 복구 건만 반환.
2. **문제집 분류기** — [hitel-scribd-runner PR #5](https://github.com/lyonbegin/hitel-scribd-runner/pull/5), 브랜치 `fix/scribd-presend-proof-handoff-20261123`, 병합 대상 `feature/hitel-public-ai-batches-20261119`.
   - `tools/zocbo/hitel_scribd_http_continue.py`: 환경값 `HITEL_SCRIBD_PRESEND_RECOVERY=approved`일 때만 **해당 20건**의 기존 job에 대해 서명된 `/recover` POST를 호출. 승인 전, 다른 job, 응답이 있거나 전송 신호가 있는 경우 절대 호출하지 않음. 서버가 `pending`을 반환하면 기존 상태만 관찰. 승인 시 이전 request, old job, source, 새 room, 새 request를 감사 기록에 저장.
   - 기존 `completed/*.json`과 `Scribd_AI_분류결과.csv`의 5,000건은 절대 수정/덮어쓰지 않음. 결과 검증 전 완료 +20 금지.
3. **안전한 1회 실행 워크플로** — 문제집 `main` 대상 별도 PR [#6](https://github.com/lyonbegin/hitel-scribd-runner/pull/6) (PR 생성 확인 완료), 브랜치 `fix/scribd-manual-20-only-workflow-20261123`.
   - `.github/workflows/hitel-public-ai-corpus.yml`: 작업자 `push` 자동 시작 삭제. `workflow_dispatch`만 허용. `mode=smoke` 기본값에서 20건만 검증하고 종료(추가 20건 자동 체인 금지). `presend_recovery=blocked` 기본값, 별도 승인 시에만 `approved` 전달.
   - 기존 `mode=smoke`가 실제로 다음 20건 체인을 막지 못했던 결함도 수정함.
   - `.github/workflows/hitel-scribd-watchdog-five-min.yml`: 기존 cron·workflow_run 자동 재개·취소 경로를 제거하고 수동 읽기 전용 진단으로 교체. 워크플로가 생성되어도 결과를 재전송하거나 기존 작업자를 종료하지 않음.

## 3. 서버 권한 판정표

| 이전 상태 | 복구 판단 |
|---|---|
| 답변 검증 완료 / result_text 있음 | **거부** — 기존 결과를 사용 |
| 일반 HTTP 500, 임의 `UPSTREAM_DELIVERY_UNKNOWN` | **거부** — 전송 여부 불명 |
| `job_769d8fbcaf034b8ebf5ca4e8d9ef3ce6` + 과거 Chrome 실행 44982380862 + `COMPOSER_NOT_FOUND` + 이력 무전송/무응답 신호 확인 | **한정 승인 후보** — 기존 job과 source 검증 후 서명된 단회 `/recover` |
| 신규 job, 실제 vendor `COMPOSER_PREFLIGHT_FAILED` + 전송 시작 단계 없음 + 정확한 오류 코드 | **한정 승인 후보** |
| 기존 `WORKER_CONNECTION_LOST` | 별도 기존 '전송 불명 가능' 감사 정책, 무전송이라고 주장하지 않음 |
| 서버와 클라이언트 request_id/room_id 불일치 | **즉시 거부** |
| 이전 Chrome 세대가 아직 소유 중이거나 정상 응답 생성 중 | **대기**, 강제 재발송 금지 |

## 4. 오프라인 검증 결과

- 공통 PR #74: 정책 12개 + FastAPI/서명 WebSocket/SQLite 통합 15개 + 실제 worker 수신 루프 4개 + pinned vendor composer 7개 시험 통과. 추가 전체 통합 회귀시험은 PR Actions 실행 상태를 재확인하십시오.
- 분류기 PR #5: 복구 승인·차단·대상 일치·영수증 9개 시나리오 시험 통과.
- 수동 워크플로 PR #6: `mode=smoke` 단회 실행·cron 및 watchdog 자동 재실행 금지의 정적 시험 통과.
- 모든 시험은 비네트워크 또는 GitHub 저장소의 pinned vendor 소스에 대한 테스트이며, **실제 ChatGPT AI 질문을 전송하지 않았습니다.**

## 5. 시험과 운영 적용 순서

- PR #74의 `HITEL Scribd source-pinned pre-send recovery QA` 및 기존 전체 통합 회귀시험을 확인. 정책·API·서명 WebSocket + 가짜 owned tab 시험만 실행하며 실제 AI 요청을 보내지 않음.
- PR #5의 `Scribd 5001 source-proof recovery offline QA` 확인. 기본 재시작 금지, 잘못된 ID/긍정적인 전송 신호/잘못된 영수증 거부 시험.
- 별도 승인 전 **어느 PR도 운영 브랜치에 병합하거나 Chrome을 새로 띄우지 말 것**. 일단 현행 중지를 유지.
- 운영 허가 후 공통 서버 PR을 반영하고 실행 커밋을 실기동 확인. 분류기 PR #5를 **feature 브랜치**에 반영. PR #6을 **main**에 반영해야만 실제 workflow가 안전하게 실행됨. workflow의 checkout 소스는 `feature/hitel-public-ai-batches-20261119`임을 재확인.
- `GET /integrations/v1/public/jobs/job_769d8fbcaf034b8ebf5ca4e8d9ef3ce6` 읽기 전용 재확인: 결과가 이미 저장되어 있으면 **중단 후 해당 결과 회수**, new POST 금지.
- 전송 없는 Chrome 편집창 진단에서 실제 로그인, URL, 가시성, 편집 가능 상태를 시험. `?model=auto`는 성공이 입증된 경우에만 환경 설정 `1`로 임시 허용.
- 사용자 승인 이후 **한 번의 수동 작업**: `mode=smoke`, `presend_recovery=approved`. 기존 failed job에 대해 서버가 `202 pending`을 반환하면 작업 ID를 그대로 보존하고 **새로운 전용 Chrome 세대** 준비 후 같은 signed recovery만 재확인. `202 accepted`는 이전 ID의 결과를 확정하지 않으며, 새 작업을 별도 감사함.
- 5,001~5,020번 원본 문서 ID 20개, AI 응답 내용, `result_sha256`, `verified rows`, 현재 5,000건과 중복 없음, 보존 아티팩트를 검사. 확인되어야만 **5,020건 완료**라고 보고.
- 연속 실행(`mode=full`)은 5,020건 1회 검증이 완료되고 **사용자가 따로 승인한 다음에만** 전환.

## 6. 금지 사항

- `unknown` / `null` 자체를 '미전송'으로 해석하지 마십시오.
- 동일 요청이나 ChatGPT 대화방에 수동으로 새 질문을 보내지 마십시오.
- 원본 completed 체크포인트를 초기화하거나 5,000건을 다시 AI에 보내지 마십시오.
- 새 Chrome 실행을 일반적인 GitHub push/주기적 watchdog에 연계하지 마십시오.
- 다른 stock-a / stock-tv 작업자·탭·계정은 건드리지 마십시오.
- 비밀번호, 토큰, 쿠키, 프롬프트, 대화 원문을 GitHub 로그와 문서에 기록하지 마십시오.

### 완료 판정

**코드/오프라인 시험 완료**와 **실제 Chrome 및 20개 분류 완료**는 별도의 상태입니다. 후자를 검증하기 전에는 완전 복구라고 보고하지 마십시오.
## 7. 후속 코드 검토 및 실행 전 추가 차단 (2026-11-23)

[PR #6](https://github.com/lyonbegin/hitel-scribd-runner/pull/6)의 별도 브랜치 `fix/scribd-manual-20-only-workflow-20261123`를 강화하였습니다. 아직 병합하지 않았습니다.

- `mode=smoke`는 **정확히 5,000건 완료 + 5,001번 첫 미완료**를 강제합니다. 4,999건/5,001건/5,020건처럼 복원 기준점이 다르면 전송 전에 거부합니다.
- 반드시 아티팩트에 `http/05001-05020.json`이 존재해야 하며, **과거 job ID, request ID, room ID, 동일한 원본 20개 문서 ID**가 모두 일치해야 합니다. 이 감사 기록이 없다면 기존 장애 복구 대신 새 질문을 생성하지 않습니다.
- `mode=full`은 1~5,020번의 검증 완료가 확인된 이후에만 허용됩니다. 별도의 사용자 승인 조건은 계속 적용됩니다.
- 실제 워크플로의 사전 검사 Python을 추출하여 가상 체크포인트에 실행한 **오프라인 7개 시나리오**가 통과했습니다. [GitHub Actions #45196901955](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45196901955). 이 테스트는 서버·Chrome·ChatGPT에 요청하지 않습니다.
- 기존 Scribd 자체 5분 감시자는 **여전히 자동 시작 금지**, 진단 워크플로만 수동 조회입니다. 공통 Chrome 작업자 스케줄러와 동일시하지 마십시오.
- 기존 장애 작업 조회 결과는 여전히 `unknown`, 작업자 오프라인, 검증 응답 없음입니다. 공개 조회의 `error: null`은 원래 `unknown` 상태에서 내부 오류를 숨기는 뷰 동작이므로 복구 근거 유무를 판단하는 자료로 사용하지 마십시오. 실제 SQLite 내부 오류·관찰 기록은 병합/배포 후 승인된 서버 경로에서 대조해야 합니다.

**주의:** 오프라인 시험 성공은 라이브 복구 성공이 아닙니다. PR #74, #5, #6 미병합과 작업 중지 상태를 계속 유지하고, 사용자 허가 전 Chrome 입력창 진단·20건 재전송·5분 분류 감시자 활성화를 금지합니다.
