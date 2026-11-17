# ProcureFlow 2Y — 기존 직접 POST 방식 실기동 A/B 시험 (2026-11-18 KST)

## 실제 실행 증거
- GitHub-hosted Chrome 실기동: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44195810279
- 공개 계약 연결경로 `/link/FIU` 추가 직접 GET: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44196167090
- 원본 ZIP 아티팩트: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44196167090/artifacts/14379281520
- 연구 브랜치: `research/procureflow-contract-web-probe-20261116`
- 스크립트: `tools/procureflow/probe_direct_post_contract.py`
- 기존 투찰 원본 수집기: `tools/procureflow/g2b_bidder_detail_stage2_recovery.py`
- GitHub-hosted Chrome+Xvfb / 기존과 동일한 `ctx.request.post()` 직접 요청 / Chrome 탭 10개 생성. **실제 조회 요청은 공개 공고 3건만 병렬 수행, 10개 공고 요청을 수행한 것은 아님.**
- 사용자 로그인/공공 API키/PC Runner/계약체결/입찰/구매/데이터 수정 없음.

## 테스트 결과: 화면 본문 렌더링과 직접 데이터 요청의 분리 입증

- 홈페이지 HTTP 200, `document.body.childElementCount = 0`
- 기존 상세 엔드포인트 `/pb/pbo/pboc/OnbsRslt/selectOnbsRsltSbidGods.do`, `Menu-Info={"menuNo":"15620","scrnNo":"08542"}`, `dlSrchOnbsRsltBidInM` JSON payload와 기존 헤더를 그대로 사용
- `R25BK01199984`: **HTTP 200, 52개 실제 `successBidInfo` 업체 투찰행**, 전체 `totCnt=52`, 응답 31,835바이트, SHA256 `5e63559b70c5b12e7ef99f9be8c9f73f3135f86e6862b7d2b4ec820d6657b81e`. 원본 `R25BK01199984_p1.json` 보존.
- `R25BK00965123`, `R26BK01795442`: 각각 **HTTP 422**, 메시지 `개찰결과 데이터가 존재하지 않습니다.`, 본문 185바이트. 결과 없음/요청 파라미터의 업무분류 차이 등 원인 미확정. 투찰 0건 또는 무응찰이라고 단정하지 않음.
- **결론:** 화면이 비어도 이전 성공 수집기 방식의 직접 POST로 실제 데이터를 받을 수 있다는 사실을 재현. 따라서 계약 조회에서도 화면 렌더링을 수집 선행조건으로 삼지 말 것.

## 계약 조회 자체 실증 범위
- 공공 계약정보의 URL 항목에 공개된 `https://www.g2b.go.kr/link/FIU`에 동일 Chrome 요청 컨텍스트에서 읽기 전용 GET.
- **HTTP 200, 최종 URL `https://www.g2b.go.kr/link/FIU/`, MIME `text/html`, 523,270바이트, SHA256 `7fe8aa60d1f7381d75199e5b058e0a5deeef919adc2cbda924c9bc8aa693ed85`**.
- 본문 내 계약관련 문자열은 있지만, 개별 계약번호 조건·조회 JSON·계약 목록/상세/페이지별 계약행이 확인되지 않았다. HTML 200/키워드 존재를 계약 데이터 성공으로 판정하지 않는다.
- 공개 공통 JS 2개 `commonGlobal.js`(57,647바이트), `bsneComm.js`(28,748바이트) 직접 HTTP 200. 이 실험에서 계약 전용 `.do` 경로 확인되지 않음. 시도했던 `/_wpack_/layout/` URL 4개는 각각 1,021바이트 HTTP 200이나 JS 파일인지 MIME 미검증이므로 실제 경로라고 단정하지 않는다.
- **계약 데이터 조회 결과: 0건 검증, 실제 계약조회 POST endpoint 및 Menu-Info/payload 미확보.**

## 차후 개발 절차
1. 기존 수집기의 `ctx.request.post`·원본 SHA256·페이징·10-worker/Release checkpoint 구조를 복제한다. 홈 화면이나 메뉴 클릭은 수집을 위한 필수 조건으로 두지 않는다.
2. 공개 계약 조회 화면/공개 자료의 실제 `select*.do` URL, `Menu-Info`, 요청 JSON 구조를 **관측 가능한 근거**로 찾아 1건 계약 목록·상세·2페이지를 재현한다. 조회 화면의 내부 요청을 임의로 가정하거나 상태변경/인증 전용 POST를 실행하지 않는다.
3. 성공한 계약 원본을 기존 투찰과 독립적인 `procureflow_2y.contracts` / `private_contract_details` / `contract_partners` 등의 엔터티로 저장하고 공식 공고집행 복합키·계약번호·차수 등으로 정확 JOIN한다.
4. 기존 930,379개 공고 원본 및 187쌍 ZIP, PC Runner, 운영 수집 워크플로는 변경하지 않는다.

**결론: 기존 성공 방법 재현 성공. 계약 목록/계약 상세 수집은 아직 미완료.**
