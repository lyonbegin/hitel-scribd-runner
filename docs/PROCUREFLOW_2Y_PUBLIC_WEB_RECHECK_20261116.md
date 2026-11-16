# 2026-11-16 후속 검증: GitHub-hosted 실행 43866703946

- 대상: 연구 브랜치 `research/procureflow-contract-web-probe-20261116`, 운영 원본 및 PC Runner 미변경.
- 확인한 세 작업: WebSquare 공개 JS 점검, Chrome/Xvfb UI 점검, 임시 PostgreSQL 스키마 시험 모두 GitHub Actions 성공.
- 증빙: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43866703946
- UI 증빙 ZIP artifact ID 14226281663, SHA256 2690d67a88e1751253f6817a2ec4803210b8d65ef09408719f10c5b20442a544 (ZIP 자체 해시이며 계약 원본 해시가 아님).
- JS 증빙 ZIP artifact ID 14225292859, SHA256 24bd43e3b71166349b7327bb208628461a7cd908f3556a29e0ac967ececaecde (ZIP 자체 해시).
- 쇼핑몰 홈: HTTP 200, WebSquare 객체 존재, document.readyState complete, body.childElementCount 0, UI 컨트롤 0, 조회 POST 0, SSO OIDC GET 302. HTTP 오류 0. 따라서 공개 상품 검색이나 납품요구 자료를 실제로 취득한 것은 아님.
- 조달데이터허브 112R/113R: 이전 검증에서 빈 DOM 및 보고서 데이터 POST 0. HTML 200은 보고서 데이터 성공이 아님.
- 공개 JS: 21개 HTTP 200; `bsneComm.js` 계약 특성 팝업 단서와 `GnbTop.js` 계약상품 검색 관련 함수 단서만 관측. 실제 계약 목록/상세 엔드포인트 재현 전.
- 독립 스키마: Postgres16 fixture에서 2건 투찰, 1건 낙찰, 1건 계약, 2건 공동수급, 2건 납품품목을 통한 FK/중복/집계 테스트 성공. 실제 데이터 적재 검증과 별개.
- 다음 실험: UI 빈 DOM 원인을 JS 초기화 및 네트워크 응답별로 분리; 공개 조회 화면의 실제 목록/상세/2페이지 요청을 확인하기 전까지 계약 실데이터 0건으로 판정. 인증 우회, API 키 가정, 구매/제출 금지.
- 완료 판정: 미완료. 기존 공고 원본 930379키 및 721일/미검증 10일, 187쌍 Release는 건드리지 않음.
