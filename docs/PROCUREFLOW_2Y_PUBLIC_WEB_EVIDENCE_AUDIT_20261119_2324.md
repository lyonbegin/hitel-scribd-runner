# 2026-11-19 23:24 KST — 공개 웹 원본·선택 복구 독립 재감사

## 확인한 원본
- 연구 감사 기준: `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md` (2026-11-16 감사 수치 변경 없음).
- 공개 웹 Actions: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44514404481 (4개 job 성공, 2026-11-19 UTC 11:23~11:26 로그).
- 선택 복구: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164 (2026-11-16 UTC 12:47 로그).
- 기존 `lyonbegin/procureflow`는 별도 프로젝트. 현재 독립 테이블 검증은 연구 저장소의 임시 PostgreSQL에서만 확인됨.

## 동일 실행의 서로 다른 두 관측
1. WebSquare bootstrap 진단은 g2b/data/shop 및 112R/113R 5개 목표 모두 HTTP 200 초기 HTML, body empty, OIDC 302 각 2건, POST 0건, verified_data_rows=0을 보고했다. 이 진단은 2/5/9/12초 시점의 DOM 타임라인이며 로그인 필수 여부의 확정 근거가 아니다.
2. 별도 공개 UI 진단은 지연 로딩 뒤 일부 화면 컨트롤을 관측했다. 공개 POST 원본 바이트 재해시 성공은 data 15, g2b 1, shop 4, 합계 20개다. 그러나 감사 출력은 `verified_list_records=0`, `verified_detail_records=0`, `verified_page_transitions=0`, `verified_join_rows=0`이며 `complete=false`다. 원본 응답 바이트가 유효하다는 것과 실제 계약/납품 레코드가 있다는 것은 별개다.
3. 따라서 빈 DOM 진단과 지연 렌더링 관측은 시간·브라우저 컨텍스트가 다른 결과이며 어느 한쪽을 폐기하거나 인증 우회 근거로 삼지 않는다. 112R/113R 및 쇼핑몰 납품요구의 공개 실원본 성공은 아직 입증되지 않았다.

## 선택 복구 원본의 제한
- 169번 샤드 5,000건 처리, verified_complete=3,385, no_opening_data=1,512, no_bidder_rows_unverified=103, verified_bidder_rows=331,902.
- ZIP `g2b-repair-shard-169-43868699164-1794833218.zip`: 41,473,929 bytes; 로그 SHA256 `a6c35cd037bb84d6b32261a73b1694bda8d402bc0eb3047ff4b4767315f4553d`. 이는 체크포인트 기록이며 이번 감사에서 ZIP 자체를 독립 다운로드·재해시한 것은 아니다.
- `complete=false`, `complete_shards_this_run=0`, `new_shards_remaining=3`, `all_stage2_verified=false`. 성공 종료된 워크플로와 데이터 완료를 구분한다. 후속 170~172 완료 여부는 이 실행만으로 단정하지 않는다.
- `HTTP 200 + successBidInfo=[]` 및 `no_bidder_rows_unverified`는 공식 무응찰/0건으로 변환하지 않는다.

## 미충족 완료 게이트
공개 계약·수의·공동수급·업체·MAS·납품요구 각각에서 최소 1건의 **실제 목록/상세/2페이지** 원본 URL·요청·바이트 SHA256, ZIP 무결성, 원본 증빙과 공식 공고차수·분류·집행차수·계약차수·업체키 JOIN, 중복/누락, 공고일·계약일·납품요구일 분리 검증이 필요하다. 현 상태는 **NOT_VERIFIED**. 930,379건 공고 인덱스, 187쌍 Release, 운영/복구 워크플로, PC Runner는 변경하지 않는다.
