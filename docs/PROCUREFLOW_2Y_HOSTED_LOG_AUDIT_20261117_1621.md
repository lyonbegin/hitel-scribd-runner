# GitHub-hosted 공개 조달 웹 조사 최신 실행 독립 로그 대조 — 2026-11-17 16:21 KST

## 실행과 검증 범위
- 연구 브랜치: `research/procureflow-contract-web-probe-20261116`
- 원본 감사 기준: `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md`
- 공개 웹 최신 완료 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44032453529 (2026-11-17 06:36 UTC 시작, 4개 작업 success)
- 선택 복구 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164 (2개 작업 success; ZIP 전수검증과 구분)
- 최신 실행의 GitHub artifact SHA256은 GitHub 제공 메타데이터이며 **ZIP 원본 바이트 독립 SHA256 재계산은 하지 않음**.

## 실제 작업 로그에서 파싱한 공개 UI 증거
| 대상 | HTTP 초기 문서 | readyState | bodyCount | POST 응답 관측 | 데이터 행 검증 |
|---|---:|---|---:|---:|---:|
| 나라장터 www.g2b.go.kr | 200 | complete | 0 | 0 | 0 |
| 조달데이터허브 data.g2b.go.kr | 200 | complete | 0 | 0 | 0 |
| 데이터허브 보고서 113R | 공개 페이지 탐색 | complete | 0 | 0 | 0 |
| 데이터허브 보고서 112R | 공개 페이지 탐색 | complete | 0 | 0 | 0 |
| 종합쇼핑몰 shop.g2b.go.kr | 200 | complete | 0 | 0 | 0 |

실행 44032453529의 `Inspect public G2B contract navigation without login or data modification` 작업 로그에서 `PROCUREFLOW_PUBLIC_WEB_PROBE` JSON을 직접 확인함. 사이트별 응답 총수는 g2b 48, data 64, shop 21이며 `post_paths=[]`, `post_response_count_observed=0`, `post_response_sample_truncated=false`. 세 사이트에서 `webSquareDefined=true`, `websquareObject=true`이지만 화면의 `bodyCount=0`. 데이터허브의 `raonkupload.js` GET 두 번 `net::ERR_ABORTED`는 POST 조회 실패나 계약 데이터 부재로 오인하지 않음. 쇼핑몰 OIDC GET 302는 관측되었으나 공개 자료 전체가 로그인 필수라는 증거가 아님.

## 증빙 아티팩트 (GitHub 메타데이터)
- `procureflow-public-websquare-js-44032453529`: 2,515 bytes, SHA256 `6bc17a10c637b072faef1a8196c703ab1e5392a8a207495bc1015e5bc5b41e5b`
- `procureflow-websquare-bootstrap-44032453529`: 168,217 bytes, SHA256 `3f3d496f008487b8978693c079b1031389a9f7a0d96b4971577bff1891ac2872`
- `procureflow-g2b-public-ui-44032453529`: 6,977 bytes, SHA256 `09a813f0bc7d5da85a631761868781cc08128da8e7c1e32d7eb5394765064c23`

## 엄격한 완료 경계
- 이 실행은 POST 관측 누락을 수정한 이전 실행과 구분되며, **공개 계약·수의계약·공동수급·MAS·납품요구의 목록/상세/페이징 원본 확보가 여전히 0건**임을 확인.
- `no_bidder_rows_unverified`를 무응찰 0건으로 확정하지 않음. 복구 실행 success는 169~172 샤드의 ZIP 바이트·SHA256·중복·누락 전수검증을 뜻하지 않음.
- 기존 공고 930,379건, 원본 187쌍 Release, 기존 운영/복구 워크플로, self-hosted PC Runner는 이번 감사에서 수정·재수집·재개하지 않음.
- 다음 단계는 공개 WebSquare 초기화의 실제 오류 원인과 읽기 전용 조회 엔드포인트를 공식 공개 경로에서 실증하고, 최초 성공한 목록·상세·페이징 바이트/URL/SHA256을 검증한 뒤에만 별도 2년 테이블에 적재하는 것.
