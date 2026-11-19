# 2026-11-19 공개 웹 진단 독립 재확인 (실데이터 미완료)

## 근거와 구분
- 연구 원문: docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md (기존 2026-11-16 감사 수치는 변경하지 않음)
- 최신 공개 UI 진단: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44493289766 (4개 job 성공)
- 순차 사이트 진단: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44493289765 , https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44493503860 , https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44493929424
- 선택 복구 원본 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164 (작업 성공 != 샤드 complete)
- 실행 환경은 GitHub-hosted ubuntu-latest, Chrome/Xvfb. 로그인/API 키/PC Runner 사용 근거 없음.

## 새로운 관측: 초기 빈 DOM과 지연 렌더링을 분리
같은 실행의 WebSquare bootstrap 진단은 g2b/data/shop 첫 로딩에서 HTTP 200, readyState complete, WebSquare 객체 존재, bodyChildren=0을 기록했다. 그러나 별도의 UI probe는 최대 20초 동안 visible navigation을 기다려 g2b 11.322초/27개, data 15.669초/15개, shop 17.185초/23개 컨트롤을 관측했다. 따라서 '항상 빈 DOM'이나 '공개 화면 전부 로그인 필요'라는 결론은 성립하지 않는다. 각 진단의 관측 시점/페이지/기다림 조건이 다르므로 동일 시점 상태로 취급하지 않는다.

UI probe에서 g2b/data/shop 메인 본문이 나타났으나, 감사 분류는 PUBLIC_WEB_EVIDENCE_ONLY이다. data에서 읽기 전용 POST 응답 10개 및 원본 응답 바이트 검증 10개를 기록했지만 **계약 목록 0건, 상세 0건, 페이지 전환 0건, JOIN 0건**이다. HTTP 200 또는 POST SHA256만으로 계약 레코드 확보를 인정하지 않는다. g2b 계약 목록/상세의 실제 조회 요청과 112R/113R 보고서 레코드, 쇼핑몰 MAS/납품요구 공개 실데이터의 목록/상세/2페이지는 아직 미검증이다.

쇼핑몰 순차 진단의 로그: homepage HTTP 200, observed_pages=1, read_only_post_paths=0, actual_contract_data_verified=false. 진단 자체의 success는 데이터 수집 성공이 아니다.

## 다음 변경의 우선순위
1. 이미 렌더링된 g2b 공개 계약 메뉴의 안전한 이동 경로를 캡처하여, 읽기 전용 요청의 정확한 URL/메서드/응답 원본 바이트를 확인한다. 계약체결/신청/입찰/구매 동작은 금지한다.
2. data 112R/113R 각각의 보고서 목록·상세 및 공개 페이지 전환 여부를 독립적으로 증명한다. 데이터 없는 JSON/SSO 302는 미검증으로 유지한다.
3. shop 공개 상품검색과 구매자 전용 납품요구를 구분하고 공개 검색에서만 실원본을 확보한다.
4. 검증된 원본만 procureflow_2y 독립 엔터티에 적재하고 공고차수/분류/집행차수/계약차수/공식 업체키 JOIN, 공고일·계약일·납품요구일 별도 기간 필터, 중복·누락·SHA256을 검증한다.

## 불변 범위
930,379개 공고키/검증 721일/미검증 10일, 187쌍 Release, 기존 운영·복구 워크플로 및 PC Runner는 변경하거나 재수집하지 않는다. 169~172 복구와 HTTP 200 + successBidInfo=[] 상태를 독립적으로 감사하기 전 다른 샤드 일괄 복구를 금지한다. 이 문서는 **진단 증빙 정리**이며 전체 완료 판정이 아니다.
