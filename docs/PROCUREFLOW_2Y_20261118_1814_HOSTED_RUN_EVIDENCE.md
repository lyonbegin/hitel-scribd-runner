# 2026-11-18 18:14 KST — hosted 공개 웹 및 선택 복구 증거 점검

## 범위
- 연구 브랜치 기존 문서 `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md` 및 진단/복구 워크플로를 읽고 확인.
- 원본 공고 930,379건, Stage2 Release 187쌍, 운영/복구 워크플로는 수정하거나 재수집하지 않음. PC runner 사용 안 함.
- 실제 데이터 완전성은 성공한 Actions job과 별개로 판정.

## 새로 확인한 실행 증거
- [실행 44256656901](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44256656901): 2026-11-18 07:09Z 시작, 07:14Z 종료, 전체 success. PostgreSQL 스키마/공개 UI/WebSquare/JS 조사 4개 job 모두 success.
- 해당 실행 공개 UI job 로그: `www.g2b.go.kr` 초기 HTTP 200; visible navigation 20초 이내 true, visible_control_count=56, bodyCount=6, bodyTextLength=601. 즉 과거 '모든 시도에서 빈 DOM'이라는 일반화는 더 이상 성립하지 않음.
- 공개 포털 POST `/fa/faz/fazf/PrtlFtre/selectPrtlFtreMainList.do` 응답 200 JSON, 120914 bytes, SHA256 `93b342272a384773dabe33517bea39519d5063b73cd69580ca8e7c276795ab0c`가 **로그에 기록**됨. 이번 점검에서는 아티팩트 원본 바이트를 별도로 재해시하지 않았으므로 이 해시를 독립 검증 완료로 표기하지 않음. 이 POST는 포털 기본정보로서 계약 상세의 증거가 아님.
- `/co/coz/coza/util/getSession.do` POST는 `net::ERR_FAILED`; 화면에는 서버 오류(code:0) 문구. 이 현상은 공개 계약조회 접근/데이터 확보 성공과 구별.
- [복구 실행 43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164): 선택 복구 및 continue job 모두 success, 상태 아티팩트 `14226304813` 존재. 이는 169~172 전체 완료 및 unknown 9509건 해결의 증거가 아님.

## 엄격한 완료 게이트
- 112R/113R, 수의계약, 공동수급, MAS, 납품요구의 실제 원본 목록·상세·페이지2 및 원본 SHA256 독립 검증 미확인.
- 계약일·납품요구일·공고일은 별도 필드, 공식 공고차수·분류·집행차수·계약차수·업체키 JOIN 결과 확인 전까지 `full_2y_complete=false`.
- `HTTP 200 + successBidInfo=[]`는 `no_bidder_rows_unverified`로 보존; 무응찰 0건 확정으로 변환 금지.
- 기존 Stage1 인덱스/Release를 변경하지 않고 169~172 선별 복구 결과부터 확인; 기타 샤드 무차별 재수집 금지.

이 문서는 실행 로그 기반의 후속 감사 메모이며 신규 계약 실원본 적재나 전체 완료를 주장하지 않는다.
