# 2026-11-17 17시대 — 공개 조회 POST 응답 총수의 상한 왜곡 수정

## 원본 근거
- 기존 감사: docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md
- 최신 공개 웹 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44032453529
- 선택 복구 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164
- 기존 공개 웹 실행은 세 사이트의 POST 응답이 각각 0건이며 신규 계약 목록·상세·페이징 원본도 0건이다. 성공한 CI 작업을 실제 데이터 검증 완료로 보지 않는다.

## 이번 수정
- probe_contract_public_ui.py에서 tracked_post_responses의 저장 한도 40건과 독립된 post_response_count_total을 모든 POST 응답에 대해 증가시킨다.
- post_response_count_observed는 실제 총수를, post_response_sample_count는 보존한 메타데이터 수를 뜻한다. sample_truncated는 실제 총수가 샘플 수보다 많을 때에만 참이다.
- tests/test_procureflow_post_response_accounting.py를 추가하고 GitHub-hosted 진단 워크플로에 회귀시험을 연결한다.
- 수정 이전에는 POST 응답이 40건 이상이면 40건으로만 보고되고, 정확히 40건이어도 truncation=true로 잘못 표기될 수 있었다. 이 수정은 수집 성공을 뜻하지 않는다.

## 보존 및 완료 경계
- 원본 공고키 930,379개, 기존 187쌍 Release, 기존 Stage2 원본/복구 워크플로, PC Runner는 변경하지 않았다.
- no_bidder_rows_unverified는 무응찰 확정으로 재분류하지 않는다.
- 169~172 샤드 복구의 원본 ZIP 바이트/CRC/SHA256/누락/중복 검증, 신규 계약·수의·공동수급·MAS·납품요구의 실제 원본 확보 및 독립 테이블 JOIN 검증은 아직 완료되지 않았다.
- GitHub-hosted 재실행의 최종 작업 로그·아티팩트 결과가 확인되기 전에는 회귀시험 통과를 선언하지 않는다.
