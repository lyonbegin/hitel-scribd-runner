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
