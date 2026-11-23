# 최근 2년 조달 공개 웹 화면 1차 실기동 조사 — 2026-11-16

## 범위 / 실행 증거
- 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43862566462
- 추가 교차시험: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43863132538 — service worker 허용, 9.5초 WebSquare 대기 후에도 나라장터/데이터허브/쇼핑몰 및 직접 보고서 113R·112R 모두 빈 DOM, 읽기용 POST 0. OIDC 응답 302 지속. **브라우저 실행 100% 성공과 공개 자료 수집 가능을 동일시하지 않음.**
- 별도 연구 브랜치: `research/procureflow-contract-web-probe-20261116`
- 워크플로: `.github/workflows/procureflow-contract-web-probe.yml`
- 도구: `tools/procureflow/probe_contract_public_ui.py`
- 환경: GitHub-hosted `ubuntu-latest`, Playwright 1.56, Google Chrome GUI + Xvfb, 인증키·사용자 로그인·PC self-hosted Runner 없음.
- 작업: 공개 첫 화면, 계약조회 메뉴, 네트워크 GET/POST 경로, 2개 조달데이터허브 보고서 바로가기 및 SSO 접근 상태의 **읽기 전용 조사**.
- 조달청의 기존 Stage 2 원본 수집기/Release/공고 930,379개 인덱스/미검증 10일/기존 PC Runner **모두 미변경**.

## 실제 확인된 결과

| 사이트 / 대상 URL | HTTP | UI 본문 | 발견된 조회 POST | 인증 상태 |
|---|---:|---|---|---|
| https://www.g2b.go.kr/ | 200 | 비어 있음 | 없음 | `sso.g2b.go.kr/oidc/597b7826dd57ff1f/auth` GET 302 |
| https://data.g2b.go.kr/ | 200 | 비어 있음 | 없음 | 위와 동일한 OIDC GET 302 |
| https://shop.g2b.go.kr/ | 200 | 비어 있음 | 없음 | 위와 동일한 OIDC GET 302 |
| https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-113R | 200 | 비어 있음 | 없음 | OIDC GET 302 |
| https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXFA-112R | 200 | 비어 있음 | 없음 | OIDC GET 302 |

참고: HTTP 200은 사이트 초기 HTML만 내려받았다는 뜻이다. 세 사이트 모두 브라우저에 WebSquare JS 및 공통 스크립트를 로드했으나 렌더링된 버튼/메뉴는 0건이었다. 실행 중 로그인/계약 체결/입찰 제출/구매를 실행하지 않았다. 직접 보고서 링크도 보고서 본문/CSV를 반환하지 않았다. 브라우저가 왜 UI를 표시하지 못했는지 단정하지 말 것. **SSO 인증 요청 존재 = 모든 공개 기능이 로그인 필요하다는 증거는 아님.**

## 검증 상태 매트릭스

| 기능 | 상태 | 근거 |
|---|---|---|
| 기존 2년 공고 인덱스/상세 개찰-업체별 투찰 | 기존 수집 코드 및 보존 Release 존재 | `g2b_bidder_detail_stage2_recovery.py`의 `selectOnbsRsltSbidGods.do` 요청 등 |
| 나라장터 계약/수의계약/공동계약 공개 목록·상세 | **미확보** | 계약 조회 화면/실제 POST 결과를 관측하지 못함 |
| 조달데이터허브 업체별 계약 보고서 | **메타데이터/URL 확인, 실제 데이터 미확보** | 113R/112R 보고서 바로가기 HTTP 200이나 빈 DOM, POST 없음 |
| 종합쇼핑몰 상품·MAS·납품요구 | **메타데이터/사이트 접속 확인, 실제 데이터 미확보** | 쇼핑몰 첫 화면 HTTP 200이나 빈 DOM, 상품 검색 POST 없음 |
| 공개 계약데이터 2년 실데이터 다운로드 | **0건 검증** | 증빙 원본 없음 |
| 계약·수의·납품 DB 테이블 및 JOIN | **미실행** | 실제 원본 확보 후 진행 |

## 다음 조사에서 검증해야 할 내용

1. 나라장터의 *공개* 계약현황·수의계약·공동계약 화면으로 실제 이동할 수 있는 공식 경로와 메뉴 인증 요구를 확정한다. 사용자 계정의 계약실적검색(자기 실적)과 일반 공개 계약현황 화면을 혼동하지 않는다.
2. GitHub-hosted Chrome 최초 WebSquare bootstrap 시 발생하는 SSO 302와 초기 빈 DOM의 원인을 확인한다. 크롬 설정/사이트 JS·HTTP 오류/서비스 상태를 우선 분리하되 로그인·세션·인증 우회는 하지 않는다.
3. 조달데이터허브 보고서별 조회 조건과 공개 다운로드 가능 여부를 검증한다. URI/메타데이터만으로 CSV 수집 성공 판정 금지.
4. 종합쇼핑몰은 상품검색과 구매자 전용 납품요구 업무를 분리하여, 공개상품·계약업체·가격 및 공개 납품실적 여부를 각각 확인한다.
5. 각 화면에 대해 검색 입력 → HTTP 메서드/경로 → 샘플 JSON/HTML → 1·2페이지 → 기간 제한 → 원본 SHA256까지 모두 실제 재현되었을 때만 대량 백필 시작.
6. 최근 2년만 대상으로 하고 투찰·개찰·낙찰·계약·수의계약·납품요구·업체정보 독립 테이블에 원본을 넣은 후 공고집행키/계약키/업체키로 JOIN. 기존 수집기·Release를 무단 수정하지 않음.

**이번 실행이 성립시킨 것은 GitHub-hosted Chrome 조사체계와 실제 인증/빈 화면 증거이다. 신규 계약·쇼핑몰 원본 추출은 아직 성공하지 않았다.**

## 후속 구현·실증 (2026-11-16 21시대)

- `tools/procureflow/schema_2y_core.sql`: 별도 PostgreSQL 스키마 `procureflow_2y`에 원본증빙, 공고차수, 개찰, 업체투찰, 확정낙찰, 계약, 수의계약 속성, 공동수급, 계약변경, 납품요구, 품목, 업체등록이력, 검증된 공고-계약 및 계약-납품 연결 테이블 정의. 기존 `procureflow` 운영 스키마는 변경하지 않음.
- `tests/test_procureflow_2y_schema.sql`: 임시 Postgres 16에 2건 투찰·1건 낙찰·1건 계약·2개 공동수급·2개 납품품목 fixture를 넣어 중복 투찰행 제거, FK, 개찰 1순위와 최종 낙찰자 구별, 1개 계약 금액 중복합산 방지를 검증. GitHub Actions `43865577998`, `43866703946`의 `validate-two-year-schema` 성공.
- WebSquare 진단은 세 사이트 모두 200 응답, `document.readyState=complete` 및 WebSquare 객체 존재하지만 첫 화면의 `body.childElementCount=0` 확인. HTTP 4xx/5xx 관측은 없었음. 조달데이터허브 보고서 직접 URL 중 하나에서 DOM body 요소 6개가 일시 관측되어 동적 초기화/화면 상태 문제를 계속 분리해야 함. OIDC 302만으로 전체 공개 화면의 로그인 필수를 단정하지 않음.
- `tools/procureflow/probe_g2b_public_bundles.py`: 사이트가 제공하는 공개 JS 경로의 HTTP 200·SHA256을 검사하고 노출된 계약 관련 화면단서/읽기 전용 URL만 제한적으로 추출. `43866703946`에서 21개 공개 자바스크립트 응답 HTTP 200, 공통 `bsneComm.js`의 계약법령 조회 팝업 명세 및 데이터허브 `GnbTop.js`의 계약상품 관련 함수 단서를 확인함. 이 소스는 계약 목록/상세조회 자체가 아니므로 실데이터 수집 완료로 간주하지 않음.
- `tools/procureflow/probe_contract_public_ui.py`의 후속 버전은 최초 90건의 정적 파일 로딩에 가려졌던 **후반부 WebSquare 동적 스크립트·POST 경로**를 별도로 수집한다. 결과가 나오는 즉시 실제 읽기 전용 계약조회 엔드포인트 존재 여부를 따로 판정할 것.
- 신규 2년 계약 데이터 행의 실제 다운로드/검증·독립 테이블 적재는 현재 **미완료**. 첫 100건 및 Release의 완전성도 별도 검증 필요. GitHub-hosted 외의 PC Runner는 실행하지 않는다.

## Stage2 원본 저장과 실제 완료 상태 재분리 — 2026-11-16 독립 감사

독립 GitHub-hosted 감사 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868804861

- Release의 ZIP 187개 + 상태 JSON 187개 전부 보존 확인.
- **상태 JSON 187개 실제 바이트를 다운로드하여 GitHub SHA256과 독립 재계산 대조 통과**.
- 각 상태 JSON의 ZIP 크기·SHA256과 대응 ZIP의 GitHub 메타데이터 187개 대조 통과. 이는 ZIP 187개를 전부 실다운로드하여 재해시한 것은 아님.
- 실제 ZIP 0, 93, 186번만 다운로드하여 **바이트 길이, 독립 SHA256, 전체 ZIP CRC 모두 통과**.
- 상태 파일에서 원본 queue 930,379건 중 Stage2 대상 930,279건으로 합계 일치.
- 반면 **완료 상태가 확인된 샤드는 7/187개**이며, 각 샤드의 상태 기록 기준 처리된 공고는 910,279/930,279개. 169~172번 샤드 4개가 `processed=0`으로 총 20,000건 미처리.
- 처리된 공고 가운데 `unknown` 누계 9,509건. 검증된 업체별 투찰행 76,417,810행과 `no_opening_data` 262,222건은 **상태 파일에 기록된 합계**이며, Release의 전체 187 ZIP 원본행을 독립 재집계한 총계는 아직 아님.
- 샘플 93번 ZIP의 상태 5,000건은 `verified_complete=3,614`, `no_opening_data=1,331`, `no_bidder_rows_unverified=55`이고 HTTP 성공 JSON의 `result.successBidInfo=[]` 형태가 관측됨. **성공 응답의 0개 투찰행은 공식적으로 무응찰이 확정되었다는 증거가 아니므로 55건을 0건 낙찰/무응찰로 분류하지 않는다.** `result.bidInfo` 및 `result.etcData` 안의 개찰 진행·상태를 별도 검증해야 한다.
- 최초의 `187개 ZIP 보존=상세 전체 100% 검증`이라는 표현은 부정확하다. 저장 완료 187개와 실데이터 187개 완료는 분리해야 한다.

우선 복구: 연구 브랜치의 `.github/workflows/procureflow-stage2-unprocessed-repair.yml`에서 10-worker Chrome+Xvfb로 기존 공식 큐 중 `processed=0`인 169~172번 샤드 **네 개만** 선택 복구하고 원본 Release는 그대로 두며 지속 보존 Release에는 새 수정 시도 ZIP+상태 JSON을 추가한다. 실제 자동 재개 실행 `43868699164`를 시작했으며, 불완전 샤드 176여 개를 일률적으로 재실행하지 않는다. 외부 요청은 복구 대상의 실패 원본에 한정한다. 9,509건의 미확인 결과는 `no_bidder_rows_unverified`의 공식 상태 의미와 원본을 확인하여 개별적으로 분류·검증한다.

해당 수치는 ZIP 3개만 본문 해시를 확인한 현 단계의 감사 결과이며, 운영 DB 적재·수의계약·최종 낙찰·납품연계 및 엑셀 검증은 완료 근거가 없다. 완료 선언·전체 전수검증 100% 표기를 금지한다.


## 후속 독립 로그 재검증 — 2026-11-20 (원본 재수집 없음)

- 공개 웹 진단 실행 [#44514404481](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44514404481)의 4개 작업이 성공했으며, UI/부트스트랩/공개 JS 아티팩트 3개가 보존되어 있다. **작업 성공은 계약 데이터 수집 성공이 아니다.**
- UI 작업의 `PUBLIC_WEB_EVIDENCE_ONLY` 감사 결과: 나라장터 읽기 전용 응답 1개, 데이터허브 15개, 쇼핑몰 4개, 총 20개 원본 응답 파일의 바이트 재해시 검증 통과. 세 사이트 모두 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`, `status=NOT_VERIFIED`. 테스트 3+11+5+19=38개 통과. **초기 화면/메타데이터 응답은 계약 목록·상세·페이징으로 간주하지 않는다.**
- 부트스트랩 작업은 나라장터, 데이터허브 첫 화면, 112R, 113R, 쇼핑몰 다섯 대상을 모두 `NOT_VERIFIED`로 분류. 각 대상에서 초기 HTTP 200, 빈 DOM, WebSquare 로드 및 OIDC 302 두 건이 관측되었으나, 이 별도 부트스트랩 시험의 `observed_post_count=0`을 UI 작업의 20개 POST와 혼동하지 않는다. SSO 302만으로 공개 조회 전체가 로그인 필수라고 단정하지 않는다.
- 선택 복구 [#43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164) 원본 로그: 169번 5,000건 중 `verified_complete=3385`, `no_opening_data=1512`, `no_bidder_rows_unverified=103`, `verified_bidder_rows=331902`, `complete=false`. 보존된 복구 ZIP 41,473,929바이트의 기록 SHA256은 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`. 당시 `new_shards_remaining=3`; 이는 170~172번의 현재 상태를 입증하지 않는다.
- `HTTP 200 + result.successBidInfo=[]`를 확정 무응찰 0건으로 재분류하지 않는다. 실제 `result.bidInfo`·`result.etcData` 상태 및 공식 낙찰·계약 원본을 개별 검증해야 한다.
- 다음 실증 게이트: 공개 계약조회·112R/113R·쇼핑몰 각각에서 **실제 공개 목록 1건 → 공식 상세 1건 → 페이지 전환 1회**를 HTTP 메서드/원본 URL/응답 바이트 SHA256과 함께 재현하고, 공고차수·분류·집행차수·계약차수·업체 공식키 JOIN을 검증할 것. 공개 접근 불가면 차단 증빙만 보존하고 임의 인증 우회·대량 수집 금지.
- 기존 공고 930,379건, 187쌍 원본 Release, 운영/복구 워크플로, self-hosted PC Runner는 변경하지 않았다. 이 문서 갱신은 **실데이터 적재 또는 전체 완료를 의미하지 않는다.**

## 2026-11-21 원본 작업 로그 교차검증 — 클라이언트 차단과 서버 거절 분리

- GitHub-hosted 공개 웹 실행 [#44793063465](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44793063465)의 `inspect-public-g2b` 작업 로그에서 HTTP 원본 응답 **23개**(g2b 1, data 15, shop 7)의 바이트 재해시를 통과했다. 단위시험 3+5+11+6+19=44개가 통과했다. 그러나 각 사이트 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`, 전체 `complete=false`다.
- 같은 실행의 `diagnose-websquare-bootstrap` 작업에서 **나라장터 초기화 요청 2건은 실제 서버 HTTP 거절이 아니라 클라이언트 안전 가드에 의해 차단**되었다(`failed_post_count=2`, `confirmed_client_guard_post_count=2`, `ambiguous_post_failure_count=0`, `observed_post_count=0`). 이를 '나라장터가 POST를 거절함' 또는 '계약 공개 조회가 불가능함'이라고 해석하지 않는다. 클라이언트 차단으로 실제 응답 상태코드가 존재하지 않으므로 200/403 등으로 임의 기재하지 않는다.
- 같은 부트스트랩 실행에서 데이터허브 첫 화면·112R·113R·쇼핑몰은 각각 `observed_post_count=0`, `dom_empty=true`, `oidc_302_count=2`, `verified_data_rows=0`였다. 나라장터는 `dom_empty=false`이나 계약 목록·상세·페이징은 미확보였다. 이는 사이트별 화면 상태를 동일하게 취급해서는 안 된다는 근거다.
- 선택 복구 [#43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164)의 실제 작업 로그에서 169번 샤드 `processed=5000`, `verified_complete=3385`, `no_opening_data=1512`, `no_bidder_rows_unverified=103`, `complete=false`, `new_shards_remaining=3`를 재확인했다. 후속 샤드 완료 여부는 별도 증빙 없이는 판단하지 않는다.
- **다음 코드 검증의 우선순위:** 차단된 초기화 POST의 메서드·경로·호출 스택·안전 가드 차단 사유를 공개 정적 자산 및 진단 로그로 구분한다. 계약·보고서·쇼핑몰의 실제 조회 요청으로 식별되기 전에는 가드를 해제하거나 임의 POST를 재생하지 않는다. 공식 공개 조회임이 확인된 경우에만 제한된 읽기 전용 시험에서 응답 원본·SHA256·목록/상세/페이징을 검증한다. 기존 공고 930,379건·187쌍 Release·운영/복구 워크플로·PC Runner는 변경하지 않는다.

이 감사는 새 계약 실데이터 적재나 전수 완료를 의미하지 않는다.

## 2026-11-21 23시 재검증 — 홈페이지 POST와 계약 조회를 구분

- [공개 웹 진단 #44793063465](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44793063465)의 `inspect-public-g2b` 원본 작업 로그에서 **실제 서버 응답을 받은 POST** `https://www.g2b.go.kr/fa/faz/fazf/PrtlFtre/selectPrtlFtreMainList.do`를 확인했다. 요청 최상위 키는 `dlSrchParmM`, 응답은 HTTP 200 JSON **120,914바이트**, 원본 SHA256 `93b342272a384773dabe33517bea39519d5063b73cd69580ca8e7c276795ab0c`이고 저장·재해시 검증됨. 이 경로는 **포털 메인 목록**이므로 계약 목록/상세 원본 1건으로 계산하지 않는다.
- 같은 로그의 `/co/coz/coza/util/getSession.do` POST는 `net::ERR_FAILED`로 종료되어 서버 HTTP 상태코드를 확인할 수 없었다. 초기화 진단의 클라이언트 가드 차단 POST와도 별개로 분류한다. 재전송·인증 우회하지 않는다.
- 동일 실행의 나라장터 초기 DOM은 2·5·9초에 자식 0개였지만 **12초에 자식 7개·컨트롤 232개**로 전환되었다. 따라서 '나라장터가 항상 빈 DOM'이라는 진술은 부정확하며, 공개 메뉴 조사에서는 최소 12초 이후 렌더링 상태를 구분해야 한다. 12초 시점의 메뉴 표시도 계약 조회 성공의 증거는 아니다.
- 같은 실행의 부트스트랩은 OIDC GET 302를 관측했지만 이는 공개 조회 전체가 인증 필수임을 입증하지 않는다. 112R/113R 및 쇼핑몰 실데이터 목록·상세·페이징·JOIN은 계속 0건 검증이다.
- [선택 복구 #43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164)의 169번 샤드는 `processed=5000`, `verified_complete=3385`, `no_opening_data=1512`, `no_bidder_rows_unverified=103`, `complete=false`. `new_shards_remaining=3`은 당시의 값으로 170~172의 최신 완료를 증명하지 않는다.
- 이번 보강은 **기존 Actions 원본 로그에 대한 추가 판독**이며 신규 데이터 적재·수집 실행·전체 완료가 아니다. 기존 공고 인덱스·187쌍 Release·운영 및 복구 워크플로·PC Runner는 변경하지 않는다.

## 2026-11-22 공개 UI 차단 요청 계수 보정

- `probe_contract_public_ui.py`에서 비읽기 요청 차단 표본은 최대 40개만 저장되지만 기존 `block_count`도 표본 길이를 반환하던 오류를 수정하였다. 전체 차단 횟수 `blocked_request_count_total`, 표본 수, 잘림 여부를 분리하며 기존 `block_count`는 실제 전체 계수로 보정한다.
- 회귀시험 `tests/test_procureflow_ui_guard_accounting.py`를 추가하고 연구 워크플로의 GitHub-hosted 검사 단계에 연결하였다. 변경 커밋은 `06e9e987`, `262d1b2d`, `2056bc52`이다. **변경 이후 Actions 통과 및 실제 계약 응답 수집은 아직 확인되지 않았다.**
- POST 허용 정책은 변경하지 않았고 인증 우회, 운영 수집기, 기존 930,379개 공고, 187쌍 Release, 선택 복구 워크플로 및 self-hosted PC Runner도 변경하지 않았다. 기존 `no_bidder_rows_unverified`는 그대로 미검증으로 유지한다.
- 이 수정은 진단 계수의 정확성만 개선한다. 계약·112R/113R·MAS·납품요구의 실데이터 목록·상세·페이징·JOIN 검증은 여전히 미완료이다.


## 2026-11-22 09시대 — 최신 실행의 증빙 재검증 (원본 재수집 없음)

- GitHub-hosted 공개 웹 실행 [#44943535368](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44943535368)의 실제 작업 4개가 모두 `completed/success`임을 연결된 GitHub 작업 API로 확인하였다. 이는 진단 코드·테스트 실행 성공이지 계약 원본 수집 성공이 아니다.
- `inspect-public-g2b` 작업의 실제 로그에서 6개 시험군 `3+3+5+11+6+19=47`개가 통과했고, `PUBLIC_WEB_EVIDENCE_ONLY` 결과의 원본 응답 재해시가 나라장터 1개, 데이터허브 15개, 쇼핑몰 4개로 총 20개 통과했다. 세 사이트 모두 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`, `status=NOT_VERIFIED`이다. 공개 초기화 응답을 계약·112R/113R·MAS·납품요구 목록으로 승격하지 않는다.
- 아티팩트 3개가 보존됨: UI `14723185198` (475,505바이트, GitHub 기록 SHA256 `9a74d4c62f3f1ecccb0b70c3464c4bd994dbe6363fc64a131663b96efb6cb9e3`), 부트스트랩 `14722223478` (201,176바이트, `e3afb063484b22f50c43044136c2a3bd574947f501faf3b04410b7b2829a1689`), 공개 JS `14721849230` (2,515바이트, `73b824ff3f52392b5c26c52b71bf261ee97038cc3d160e66e20dad41a35231b3`). 이는 GitHub 메타데이터/업로드 로그의 ZIP 해시이며 **이번 점검에서 ZIP 3개를 별도 다운로드해 재해시한 결과가 아니다.**
- [선택 복구 #43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164)의 두 작업은 성공 종료이나, 169번 샤드 `verified_complete=3385/5000`, `no_opening_data=1512`, `no_bidder_rows_unverified=103`, `complete=false`라는 최신 확인 가능한 원본 상태를 뒤집지 않는다. 170~172번 샤드 완료는 이 실행만으로 증명되지 않는다. `HTTP 200 + successBidInfo=[]`를 확정 무응찰로 재분류하지 않는다.
- 공개 조회 실제 목록 1건·상세 1건·페이지 전환 1회·공식키 JOIN 및 원본 URL/바이트 SHA256의 결합 증빙이 확보될 때까지 독립 테이블 실데이터 적재와 전체 완료 판정을 금지한다. 기존 공고 930,379건, 187쌍 원본 Release, 운영/복구 워크플로, self-hosted PC Runner는 변경하지 않았다.


## 2026-11-23 — HTTP 200 빈 투찰행 증빙 분류 보강

- 공개 읽기 전용 HTTP 응답의 원본 SHA256 증빙에 `semantic_verification`을 추가하였다. `result.successBidInfo=[]`인 HTTP 200 JSON은 `NO_BIDDER_ROWS_UNVERIFIED`로 분류하며, HTTP 오류·비JSON·파싱 오류·그 외 JSON도 자동으로 계약/낙찰 검증 완료로 승격하지 않는다.
- 수정: `tools/procureflow/public_readonly_raw.py`, `tools/procureflow/probe_contract_public_ui.py`; 회귀시험: `tests/test_procureflow_public_response_semantics.py`; 연구용 GitHub-hosted 워크플로에 시험을 연결하였다. 커밋: `3acf6b8b`, `33e62c33`, `0f51f44e`, `ca362444`.
- 이번 변경은 **분류·진단 코드만** 수정하였다. 후속 GitHub Actions 시험 통과, 실제 계약 목록·상세·페이징·JOIN 또는 ZIP 원본의 신규 검증은 아직 확인되지 않았다. 기존 930,379개 공고 인덱스, 187쌍 원본 Release, Stage2 복구 워크플로 및 PC Runner는 수정하지 않았다. 169~172번의 완료 판정과 나머지 샤드 재수집도 실행하지 않았다.


## 2026-11-23 15시 독립 실행 교차검증 — Chrome 90초 변경 후 실증

- 연구 브랜치 HEAD `41e11fa0f859001b538ff495bbb50f8a2bf7864d`의 [공개 웹 실행 #45105197687](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45105197687) 4개 작업 성공 및 순차 진단 [나라장터 #45105197872](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45105197872) → [데이터허브 #45105306966](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45105306966) → [쇼핑몰 #45105585733](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45105585733) 성공을 작업 API·원본 로그로 확인. 직전 Chrome 연결 30초 타임아웃 실행 #45092583315와 달리 신규 나라장터 작업은 Chrome 실행 후 공개 첫 화면 진단을 끝냈다. **Chrome 시작 문제의 이번 실행 재현은 없으나 계약 실데이터 수집 성공을 뜻하지 않는다.**
- 나라장터: 화면 내비게이션 약 10.54초 후 노출. 포털 메인 `POST /fa/faz/fazf/PrtlFtre/selectPrtlFtreMainList.do` HTTP 200, 응답 120,914바이트, SHA256 `93b342272a384773dabe33517bea39519d5063b73cd69580ca8e7c276795ab0c`, 원본 저장·재해시 통과. 이는 **계약 목록이 아닌 포털 메인**이다. `/co/coz/coza/util/getSession.do`는 `net::ERR_FAILED`로 실제 HTTP 응답코드 없음. 화면에 `서버 오류입니다. code : 0` 표시. `contract_labels=[]`.
- 데이터허브: 내비게이션 약 18.985초 후 렌더링. 112R/113R 링크 모두 화면에는 `서버 오류입니다. code : 0`가 표시됨. 초기화/공통 POST 응답 15개를 관측했지만 **112R/113R의 보고서 행·상세·페이지 증거는 없음**. `getSession.do` 요청 실패를 서버 403/200으로 임의 분류하지 않음.
- 쇼핑몰: 공개 첫 화면에서 검색·상세검색 요소와 인증/테마/분류 메인 POST 7개 관측. 이들 응답은 **MAS 상품검색 또는 납품요구 실적 원본이 아님**. 초기 화면의 `서버 오류입니다. code : 0`도 데이터 적재 성공 증거가 아님.
- 위 세 단계의 Actions 성공과 공개 초기화 응답의 바이트 보존은 검증된 계약·수의·공동수급·112R/113R·MAS·납품요구의 목록/상세/페이징/공식키 JOIN을 충족하지 못한다. **실데이터 검증 완료 0건**, 신규 2년 독립 테이블의 실원본 적재는 미완료. 다음 우선순위는 이미 노출된 공개 메뉴의 안전한 상세검색 클릭 가능성, 실제 검색 요청 경로, 화면 `code : 0` 발생 직전 실패 요청의 네트워크/JS 상관관계 증빙이다. 공식 공개 조회가 확정되기 전 임의 POST 재생 금지.
- 선택 복구 #43868699164의 169번 `verified_complete=3385/5000`, `no_bidder_rows_unverified=103`, `complete=false`와 170~172의 완료 미입증 상태를 유지한다. HTTP 200 + `successBidInfo=[]`를 확정 0건으로 재분류하지 않는다. 기존 930,379 공고, 187쌍 Release, 운영/복구 워크플로 및 PC Runner는 변경하거나 재실행하지 않았다.


## 2026-11-23 18시대 — 원본 작업 로그 직접 재검증 및 완료 게이트 재확인

- GitHub 연결로 연구 브랜치 감사 문서, `procureflow-contract-web-probe.yml`, `procureflow-stage2-unprocessed-repair.yml`을 직접 읽고 `lyonbegin/procureflow` 저장소의 존재·접근 권한을 확인하였다. 두 워크플로 모두 GitHub-hosted `ubuntu-latest`를 사용하며 연구용 공개 UI 워크플로는 Chrome/Xvfb·읽기 전용 가드로 구성된다. Stage2 복구 워크플로는 **수정하지 않았다**.
- [공개 UI 실행 #45092583279](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45092583279)의 `inspect-public-g2b` 작업 ID `137425245268` 원본 로그를 다시 읽었다. 7개 시험군 **4+4+3+5+11+7+19=53개 통과**. `audit_public_ui_data_proof.py`의 실제 출력: 나라장터 POST 응답 원본 1개, 데이터허브 15개, 쇼핑몰 7개, **총 23개 응답 파일의 바이트 재해시 통과**. 세 사이트 모두 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`, `status=NOT_VERIFIED`, `complete=false`. 공개 초기화 원본과 실제 계약·MAS·납품요구 데이터 원본을 혼동하지 않는다.
- 위 작업 로그의 UI 증빙 아티팩트 ID는 `14782275633`, GitHub 업로드 ZIP 기록 SHA256은 `df26a57753c6e8a8414af1906176b7f5de13d65e2f74c04364d3779dce9dfce4`이다. **이번 점검에서 ZIP을 별도 다운로드하여 바이트 SHA256·CRC를 독립 재계산한 것은 아니다.** 아티팩트 업로드 해시와 23개 내부 HTTP 원본 파일의 재해시는 서로 다른 검증 단계이다.
- [선택 복구 #43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164)의 작업 ID `133303823234` 원본 로그에서 `DETAIL_FINAL`: `processed=5000`, `verified_complete=3385`, `no_opening_data=1512`, `no_bidder_rows_unverified=103`, `verified_bidder_rows=331902`, `two_year_all_details_complete=false`. `SHARD_CHECKPOINT_VERIFIED`의 `segment=169`, `complete=false`, `unknown=103`, `award_linkage_verified=false`, `excel_integration_verified=false`; `SUPERVISOR_RESULT`의 `new_shards_remaining=3`, `need_continue=true`, `all_stage2_verified=false`도 확인하였다. 작업 성공은 데이터 완료가 아니다. 170~172의 현재 상태는 별도 후속 원본 없이는 미확정이다.
- 복구 169 ZIP의 업로드 로그: 41,473,929바이트, SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`; 대응 상태 JSON 483바이트, SHA256 `4cb4201936d78322681e1ddd50dd1747c1a97fc2d0946a0e6a7d0bc742ed5165`. 두 해시는 실행 로그 및 체크포인트 기록이며 **이번 점검에서 해당 파일의 바이트를 다시 다운로드해 독립 검증한 값은 아니다**.
- `HTTP 200 + result.successBidInfo=[]`는 계속 `no_bidder_rows_unverified`로 유지한다. `no_opening_data` 또한 공식 무응찰 확정으로 승격하지 않는다. 계약·112R/113R·쇼핑몰 MAS/납품요구는 실제 목록→상세→페이지 전환→공식키 JOIN 및 원본 URL·바이트 SHA256 결합 증빙을 확보하기 전까지 0건 검증 상태로 유지한다.
- 이번 회차는 **기존 로그·워크플로의 독립 재판독과 감사 문서 보강만 수행**했다. 신규 Chrome 조사 실행, 실데이터 적재, 169~172 재복구, 나머지 176개 샤드 재수집, 공고목록 930,379건 재수집, 원본 Release 187쌍 변경, 운영/복구 워크플로 수정 및 self-hosted PC Runner 재개는 하지 않았다.


## 2026-11-24 01시 최신 Chrome 실증 — 상세검색 클릭 차단 원인 특정

- 연구 브랜치 HEAD `7c02ef02199401ad1b84ad80ed79c24ba2427615`에서 실행한 [공개 웹 조사 #45201773768](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45201773768) `inspect-public-g2b` 작업 `137788393008`의 **실제 원본 로그**를 확인하였다. 쇼핑몰 `상세검색` 링크는 DOM에 존재하며 `<a href="javascript:void(null);">`로 표시되지만, 클릭 좌표 `(1028.109375,48)` 크기 `54×54`에서 `document.elementFromPoint`는 링크가 아니라 `DIV.w2modal_popup`을 반환했다. 해당 모달의 `z-index=4000`, `pointer-events=auto` 및 `html.w2modalopenedbody` 상태를 확인하였다. 따라서 `trial=True` 클릭 실패는 링크 부재가 아닌 **WebSquare 모달이 클릭을 가로막는 현상**으로 분류한다. 모달이 서버 오류 표시와 동일한 것인지 추가 원본 확인 전 단정하지 않는다. 모달 강제 제거·강제 클릭·인증 우회는 수행하지 않는다.
- 위 실행은 7개 회귀시험군 `4+4+3+5+11+7+19=53`개 통과, 나라장터 1개·데이터허브 15개·쇼핑몰 7개 등 HTTP 응답 원본 23개 바이트 재해시 성공. 세 사이트 모두 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`, `complete=false`. UI 증빙 아티팩트 `14831333880`, 업로드 로그 기록 ZIP SHA256 `f495aef18f1857bc382bbf0d7406f3d2fbe9dff6ba184f2b0128a40eca409308` (ZIP 자체 독립 재다운로드 검증은 미실시).
- 별도 [쇼핑몰 순차 진단 #45202468959](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/45202468959)의 작업 `137789284046`에서는 12초까지 빈 DOM, OIDC 302 왕복, 실제 조회 POST 0건으로 확인되었다. 이는 위의 **장시간 렌더링 후 모달로 막힌 상세검색**과 서로 다른 진단 시점/조건이다. ZIP 아티팩트 `14833185144` 업로드 로그 기록 SHA256 `7c8b298abb5069cf311f19b8645a7c5b60d9ed04895f0781a94ec0c66c15734b` (독립 재해시 미실시).
- 후속 검증은 모달의 표시 문구·발생 직전 HTTP 실패 및 JS 오류의 타임라인을 연결하는 읽기 전용 계측이 우선이다. 모달을 강제로 닫거나 조회 POST를 추정 재생하지 않는다. 계약·112R/113R·MAS·납품요구의 실제 목록/상세/페이징/공식키 JOIN은 0건 검증으로 유지한다. 169번 샤드 `verified_complete=3385/5000`, `no_bidder_rows_unverified=103`, `complete=false`와 170~172 완료 미입증을 유지하며 기존 공고 930,379건·187쌍 Release·운영/복구 워크플로·PC Runner는 변경하지 않는다.


## 2026-11-24 쇼핑몰 모달 관측 후 클릭 보류 패치
- 순차 쇼핑몰 진단 #45202468959의 부트스트랩 로그: 2/5/9/12초 빈 DOM, OIDC GET 302, 최종 홈페이지 HTTP 200. 이는 상품 데이터 확보가 아니다.
- 아티팩트 14833185144: 업로드 로그의 ZIP 119867바이트, SHA256 7c8b298abb5069cf311f19b8645a7c5b60d9ed04895f0781a94ec0c66c15734b. 독립 재다운로드 검증은 하지 않았다.
- 코드 커밋 bc0a21487a696c03ec0103ff982d8045e9055da4: div.w2modal_popup의 가시성·크기·z-index·pointer-events 및 제한된 텍스트를 기록한다. 표시된 모달이 클릭을 막으면 강제 클릭이나 모달 제거 없이 쇼핑몰 상세검색 탐색을 보류한다.
- 변경 후 GitHub-hosted Chrome/Xvfb 재실행 및 회귀시험은 아직 미검증이다. 계약·112R/113R·MAS·납품요구 목록·상세·페이징·JOIN의 실제 검증은 0건으로 유지한다.
- Stage2 #43868699164의 169번 verified_complete=3385/5000, no_bidder_rows_unverified=103, complete=false를 유지한다. 170~172번 완료는 미입증이다. 기존 930379건 공고, 187쌍 Release, 운영·복구 워크플로, PC Runner는 변경하지 않았다.
