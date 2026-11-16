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
