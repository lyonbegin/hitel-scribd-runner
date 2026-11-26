# HITEL AI 대량 작업 프레임워크 — 최종 인계 및 재사용 매뉴얼

기준일: 2026-11-27 (KST) · 상태: Scribd 작업 마감, 재사용용 소스 보존
이 문서는 실제 운영 소스와 완료 로그를 기준으로 작성하였다. 새 업무용 범용 엔진이 이미 구현되었다는 뜻은 아니다.

## 1. 최종 성과 및 고정된 기준 소스

| 항목 | 값 |
|---|---|
| 원본 | 18,109건 (원본 ID 중복 없음, 원본 SHA-256 검사) |
| 검증 완료 | 18,088건 (99.884%) |
| 사용자 승인 제외 | 21건: 원본 행 번호 9134, 11895~11914 |
| 마지막 확인된 보존 결과 | [실행 45894625973](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45894625973) |
| 결과 ZIP | [artifact 15153017293](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45894625973/artifacts/15153017293), 5,148,803 bytes |
| ZIP SHA-256 (GitHub 메타데이터) | c4174f39ba87f42f9b408e10e97dbe9aac223e8f9f5781d0ab6ed353aee23b1f |
| 결과 ZIP 만료 | 2027-02-25 05:56 KST |
| 실제 생산자 기준 | feature/hitel-public-ai-batches-20261119 @ [8383a649](https://github.com/lyonbegin/hitel-scribd-runner/commit/8383a649b190d147f3580d6adcaeb8422d483c32) |
| 운영 워크플로 (마감 직전 실행 기준) | main @ [0ab60d85](https://github.com/lyonbegin/hitel-scribd-runner/commit/0ab60d852c39797d2ad37c1a14744cf9296d354d) |
| 마감 커밋 | main @ [6b126b15](https://github.com/lyonbegin/hitel-scribd-runner/commit/6b126b15efa774fc8c0bab017a18ad6a5fd6eb89) |
| 원본 CSV SHA-256 (코드 고정값) | c9ac45f833dd30a002cffac64cb3ced763ed4eb18b0e121c4ab00b935a9b82e3 |

**주의:** 결과 CSV는 원본 18,109행을 유지하고 미검증 행은 미처리로 표시한다. 18,088건만 분류 성공이다. 21건은 실패를 성공으로 변경한 것이 아니라 사용자 승인으로 작업 범위에서 제외한 것이다. Artifact는 보관기한 전에 별도로 백업할 것. 이 문서 작성 시 ZIP 자체를 새로 다운로드·재검증하지 않았으며 GitHub 로그와 artifact 메타데이터를 확인했다.

## 2. 실제 운영 아키텍처

```text
운영자 명시적 workflow_dispatch (main)
  -> worker_ready: handoff 중복 확인 / isolated task 상태 조회
  -> ai: 생산자 feature 브랜치 checkout / 원본 CSV 조립·SHA 검증
  -> 이전 artifact checkpoint 복원 / 기존 verified 결과 검사
  -> 최대 20건 범위 선택 / AI 질의 작성 / 요청 상태 영속화
  -> 승인된 HITEL task-bound HTTP 제출 / 동일 요청·job 상태 조회
  -> 실제 응답 완성 및 결과 검증 / 원본 ID와 매핑
  -> completed JSON + CSV + status.json / checkpoint artifact 업로드
  -> 검증 진전 확인 후 다음 workflow_dispatch (parent별 handoff token)
  -> 실패 시 checkpoint 유지 / 제한된 재조정·재시도 / 운영자 종료
```

- AI가 제목을 판단한다. Python은 교육 분류를 정규식으로 대체하지 않고 전송·검증·누적을 담당한다.
- 실행기와 AI 세션의 수명은 분리되어 있다. GitHub runner가 종료되어도 완료된 결과 및 요청 식별자는 checkpoint에서 복구한다. 브라우저 세션/워커가 항상 살아 있다는 보장은 없다.
- 최종 운영은 서명된 task 격리 HTTP 방식이다. 초기 공용 HTTP 및 WS 방식은 이력·회귀시험용이다. 서로 다른 업무에 동일 task/room/output을 공유하지 않는다.
- HTTP 200, job 생성, 응답 문자열 일부만으로 성공 처리하지 않는다. 완료 상태, 응답 무결성 및 데이터 검증을 함께 적용한다.
- 본 저장소는 생산자 측이다. HITEL 서버와 워커의 새 task 등록·권한 부여는 서버 측 담당자가 별도로 수행해야 한다. 권한 없는 세션 사용이나 서비스 한도 회피는 허용하지 않는다.

## 3. 파일별 역할과 재사용 범위

| 상대 경로 (tools/zocbo/) | 실제 역할 | 새 업무 적용 |
|---|---|---|
| hitel_scribd_http_continue.py | 1회 배치 실행, immutable request_id, 상태 조회, 장애 조정, 완료 누적 | 핵심 참조; Scribd 상수와 특수 복구 분리 |
| hitel_public_named_rooms_corpus.py | title_prompt, validated_rows, read_completed_result, save, output_file | 질의·검증·내보내기 교체, 영속화 참조 |
| hitel_scribd_supervisor.py | A01 등 짧은 키, 원본 제목 대조, 응답 검증, scope 분할 | 새 스키마·도메인 검증으로 교체 |
| hitel_scribd_ws_continue.py | SOURCE_SHA, load_verified, next_batch, 이전 WS 이력 | 입력/체크포인트 검증 원리만 참조 |
| hitel_dispatch_next_verified.py | parent run 기반 token, 실제 child 검색, 204 중복 POST 금지, 5xx 조회 후 제한 재시도 | workflow명·ref·prefix·inputs 교체 |
| hitel_public_ai_batch_classifier.py | 초기 공개 API 묶음 분류 및 dry-run | 과거 구현; 최종 운영 엔진과 혼용 금지 |
| hitel_scribd_watchdog*.py / test_hitel_*.py | 감시·장애 회귀시험 | 테스트/상태 감시 원리 참조 |
| ../../data/raw_18109/part_*.csv | 원본 데이터 조각 | 새 승인된 입력으로 교체 |
| ../../docs/reference/hitel-public-ai-corpus.closed.yml | main 마감 워크플로 원문 사본 | 참고 전용, 실행 위치에 두지 않음 |

실제 워크플로는 main의 .github/workflows/hitel-public-ai-corpus.yml이다. 최종 보존 브랜치는 생산자 소스 기준으로 만들어졌고 main의 마감 워크플로를 docs/reference 아래에 복사했다. 기존 과거 워크플로도 보존되어 있으므로 새 업무 브랜치에서 무심코 활성화하지 말 것.

## 4. 상태 및 데이터 계약

- 입력: 원본 순번, 안정적인 record_id, AI에 필요한 텍스트, 필요 시 원문 링크. 원본 순서/중복/해시 검증. 개인정보 및 비밀은 최소화.
- 프롬프트: 명시적 스키마 버전, 항목별 짧은 키와 원본 텍스트, 분류 규칙, 허용 값, 불확실성 표기, JSON만 반환하라는 지시.
- 검증: 응답 행 수, 키/제목 일치, 필수 필드, enum, 원본 ID 매핑, 중복 확인. 실제 supervisor는 NFC 정규화 후 제목을 대조하고 원본 ID는 AI가 아닌 입력에서 복원한다.
- 요청 식별: task_id + scope/record 범위 + prompt digest 기반 request_id. 같은 request_id로 불확실한 제출을 새 질의로 반복하지 않는다. 기존 job/room을 먼저 조회한다.
- 완료: 검증된 completed/*.json만 성공 합계에 포함. 원본 ID/링크는 변경하지 않는다.
- 보존: http/, jobs/, supervisor/, completed/, skipped/ (미검증), supervisor-reconcile.json 및 status.json, Scribd_AI_분류결과.csv 등. 일부 폴더는 역사적 실행 단계에서 생성된다.
- 실패: 미검증 기록을 결과에 조작하여 삽입하지 않는다. 마지막 21건과 같이 운영자 승인으로 제외 시 별도 목록·사유·마감 수치 기록.

## 5. 다른 AI 작업 시작 방법 (개발자용)

1. 이 보존 브랜치를 기준으로 새 업무 전용 브랜치를 생성한다. 원본 main 및 종료된 Scribd producer는 재활성화하지 않는다.
2. 새 task_id, 입력 CSV/JSONL, 출력 스키마, 프롬프트 규칙, 검증 규칙, 최종 완료/제외 기준을 확정한다. 데이터·checkpoint·artifact·concurrency group·room prefix를 모두 별도 지정한다.
3. HITEL 서비스 담당자에게 새 task와 승인된 인증 방식을 확인한다. 실제 운영 코드는 scribd-18109만 허용하고 OIDC audience/서버 경로가 고정되어 있다. 새 task는 서버의 producer 정책이 새 업무와 일치해야 한다. 단순 task 문자열 바꾸기로 작동한다고 가정하지 말 것. 공식 AI API를 사용하는 경우에는 별도 transport adapter로 연결한다.
4. hitel_scribd_http_continue.py에서 18109, SOURCE_SHA, OLD_1101, 9134, 11895~11914 등 Scribd 전용 조건과 기존 요청 복구 이력을 분리한다. 일반화는 새 모듈에서 수행하고 기존 checkpoint와 섞지 않는다.
5. prompt/validate/export는 새 도메인으로 변경한다. 원본 ID·입력 해시·schema version·request_id·검증 완료 증거를 유지한다.
6. dry-run 및 오프라인 단위시험: 중복 ID, 누락, 잘못된 enum, 응답 중단, 429/backoff, 연결 실패, 제출 불확실, artifact 누락, 재실행, 취소 및 no-progress 시험. 과거 테스트를 기준으로 새 fixture를 만든다.
7. 새 workflow_dispatch의 smoke 모드에서 5~20건을 승인된 AI 경로로 실제 시험한다. 응답 JSON 및 원본 매핑, checkpoint 업로드, 두 번째 실행의 중복 방지 증거를 확인한다. smoke에서는 후속 자동 실행 금지.
8. full 모드 승인 후, 검증 완료가 늘고 checkpoint 저장에 성공했을 때만 다음 배치를 연결한다. no-progress/보류 대상만 남으면 무한 복구하지 말고 운영자 판단 대기 상태로 정지하도록 새 workflow를 개선한다.
9. 정지 시 후속 dispatch 및 자동 복구를 비활성화하고 실행 중인 작업까지 확인한다. 결과·제외 목록·manifest·코드 버전을 보존한다. 다른 task를 건드리지 않는다.

### 참고: 원본 소스 확인 및 오프라인 시험 명령

```bash
git clone https://github.com/lyonbegin/hitel-scribd-runner.git
cd hitel-scribd-runner
git checkout release/hitel-ai-batch-framework-20261127
cd tools/zocbo
python -m unittest -v test_hitel_scribd_http_continue test_hitel_dispatch_next_verified test_hitel_corpus_recovery20
```

위 테스트 파일은 실제 존재하며 mock 기반 시험으로 설계되었다. 이 인계 작업에서는 새 실행 결과를 생성하지 않았다. 이전 운영 소스의 실서비스 실행 명령은 python3 tools/zocbo/hitel_scribd_http_continue.py --input Raw_Documents_18109.csv --out hitel-ai-batches 였으나 **종료한 Scribd task에 실행하지 말 것**. 신규 업무용 일반화 코드와 테스트를 별도로 개발해야 한다.

### 새 업무 설정 예시 (설계 계약, 현재 엔진의 실행 가능한 CLI 설정 아님)

```json
{
  "task_id": "new-book-catalog-audit-v1",
  "input": "data/new_records.csv",
  "id_field": "record_id",
  "text_field": "title",
  "schema_version": "catalog-audit-v1",
  "prompt_file": "prompts/catalog_audit.md",
  "batch_size": 20,
  "max_concurrent_batches": 1,
  "output_dir": "runs/new-book-catalog-audit-v1",
  "artifact_name": "new-book-catalog-audit-v1-checkpoint",
  "concurrency_group": "new-book-catalog-audit-v1",
  "max_no_progress_runs": 2,
  "approval_required_for_full": true
}
```

## 6. 다른 AI에게 그대로 전달할 개발 지시문

> HITEL GitHub 저장소 lyonbegin/hitel-scribd-runner의 release/hitel-ai-batch-framework-20261127 브랜치와 이 문서를 읽으십시오. 기존 Scribd 작업은 종료되었으므로 main, 기존 task_id, 기존 결과를 변경하거나 다시 실행하지 마십시오. 요청 업무는 [업무 설명]이고 입력은 [파일/필드], 원하는 출력은 [JSON 스키마/CSV 열]입니다. 기존 AI 분류 시스템에서 원본 해시 검사, immutable request_id, 상태 조회, 검증된 결과만 저장, checkpoint 복원, 후속 Actions 연결을 재사용하십시오. Scribd 전용 로직은 복사하지 말고 새 task 설정·프롬프트·검증기·출력기로 분리하십시오. 새 task의 인증·서비스 사용 권한을 확인하고, 서로 다른 작업의 세션·파일·artifact·concurrency를 격리하십시오. 새 전용 브랜치에서 오프라인 테스트, 5~20건 실제 smoke, 결과 매핑 검증, 중복 방지 시험 순으로 수행하십시오. 실서비스 응답과 테스트 결과를 확인하기 전 완료라고 보고하지 마십시오. full 실행은 명시적 승인 후 시작하고 실제 검증 진전 후에만 다음 배치를 연결하십시오. 불확실한 제출은 중복하지 말고 서버 상태 조회로 조정하십시오. 반복 장애는 제한 후 중단하며, 운영자가 제외한 행은 성공과 구분하십시오. 최종 커밋, 실제 Actions ID, 완료/제외/미처리 건수, 결과 artifact 링크 및 SHA를 제출하십시오.

## 7. 운영 점검표 / 장애 대처

| 현상 | 대응 |
|---|---|
| accepted/queued/running | 동일 request_id/job 상태 확인; 새 제출 금지 |
| HTTP 429 | Retry-After 및 backoff 존중; 승인 없는 우회 금지 |
| HTTP 5xx / timeout | 결과 조회와 전달 여부 확인, 불확실 상태 보존 |
| AI JSON 오류 | 검증 실패로 처리, scope 축소 등 승인된 정책 내 재시험 |
| worker 연결 끊김 | 실제 worker 상태와 terminal 여부 확인, 서버 승인 복구만 수행 |
| 중복 후속 Actions | parent handoff token과 실제 run 조회, concurrency 유지 |
| checkpoint 불일치 | fail closed, 이전 검증 checkpoint 조사 |
| 진행률 정체 | 무한 재실행 금지; no-progress 예산 및 운영자 제외/종료 |
| 완료 보고 | verified / 제외 / 미처리 구분, artifact와 로그 근거 제시 |

## 8. 마감 및 남은 한계

- 이번 성과는 AI 분류 18,088건이다. 실제 PDF 다운로드 완료 건수라는 뜻이 아니다.
- main 마감 커밋은 worker_ready, ai, recover job 조건을 false로 고정하였다. 당시 이미 시작된 구버전 복구 작업은 이 변경의 소급 적용 대상이 아니므로 종료 여부를 별도로 확인해야 한다.
- 이 보존 브랜치는 운영 소스와 문서의 고정 인계본이다. 새 업무용 범용화 및 서버 연동 smoke는 별도 개발·검증 대상이다.
- 코드 보존과 데이터 artifact 보관은 별개다. 결과 ZIP의 영구 백업은 아직 확인되지 않았다.
- 다른 task의 권한, 데이터, 사용량 제한 및 운영 정책을 준수할 것.
