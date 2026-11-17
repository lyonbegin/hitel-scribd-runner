# 2년 공개 계약 조사 — POST 관측 누락 교정 (2026-11-17 15:35 KST)

## 확인된 기존 증거
- 감사 기준: `docs/PROCUREFLOW_2Y_PUBLIC_WEB_RECON_20261116.md` (187개 상태 JSON의 독립 SHA256 대조, ZIP 전체 바이트 검증은 3개 샘플만). 기존 169~172 복구 실행 [43868699164](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43868699164)은 작업 성공이지만 전수 원본 완전성 증거가 아니다.
- 공개 웹 조사 실행 [43997169185](https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/43997169185)은 4개 작업 성공 및 3개 진단 아티팩트 생성. 이 성공은 계약/112R/113R/MAS/납품요구 목록·상세·페이징 원본 확보를 뜻하지 않는다.
- 공개 화면 HTTP 200, WebSquare 빈 DOM 및 OIDC 302는 각각 독립 관측값이며 인증 필수 여부나 서버의 계약조회 데이터 유무를 확정하지 않는다.

## 이번 코드 수정
`probe_contract_public_ui.py`는 초기 `MAX_EVENTS=90` 응답을 별도 기록하고, 늦게 도착하는 POST 응답은 `tracked_post_responses`에 최대 40개 보관한다. 종전 출력의 `post_paths`는 초기 90개 `events`만 검사하여 실제 POST 응답이 뒤늦게 관측되어도 빈 목록으로 표시될 수 있었다. 이번에는 `summarize_post_paths()`로 독립 POST 응답 버퍼를 요약하며 관측 건수와 40건 상한 도달 여부를 표시한다. `tests/test_procureflow_bootstrap_evidence.py`에 90개 정적 GET 이후 POST를 재현하는 회귀시험을 추가하였다.

**검증 한계:** 출력 개선은 신규 원본 계약 데이터 확보가 아니다. `tracked_post_responses` 자체도 40개 상한이 있으므로 40건 도달 시 전체 POST 개수로 해석하지 않는다. URL/원본 응답 본문/바이트 SHA256/목록·상세·페이징/공식키 JOIN의 실증이 없는 상태는 미완료로 유지한다. 변경은 연구 브랜치의 공개 웹 진단 코드와 회귀시험에 한정하며 기존 930,379 공고목록, 원본 187쌍 Release, 복구 워크플로, PC Runner는 변경하지 않는다.

## 재검증
연구 브랜치 push가 `procureflow-contract-web-probe.yml`을 실행하도록 구성되어 있다. 실행 로그의 `post_paths`, `tracked_post_responses`, `post_response_sample_truncated`를 확인해야 하며, 작업 성공만으로 실제 POST 성공이나 데이터 확보를 선언하지 않는다.
