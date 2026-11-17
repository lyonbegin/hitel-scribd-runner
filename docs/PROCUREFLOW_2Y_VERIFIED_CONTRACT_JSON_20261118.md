# 나라장터 최근 2년 계약현황 공개 JSON 직접 POST 실증 성공 — 2026-11-18 KST

## 실기동 성공 범위와 원본 증거
- 기존 Chrome 방식 재현: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44195810279 (투찰 상세 52행 실제 JSON, 빈 DOM에서도 POST 성공)
- 나라장터 공개 계약 검색 URL 소스 검증: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44199344809
- 공개 계약 JSON 목록 1·2페이지 성공: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44199999122
- 원본 JSON 다운로드(위 실행의 GitHub-hosted 아티팩트): https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44199999122/artifacts/14379794572
- 독립 추가 QA(페이지 중복·날짜조건): https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44200587595
- 소스: `tools/procureflow/test_real_g2b_public_contract_list_json.py`
- 기존 930,379개 공고키·187개 고유 ZIP/상태 쌍 및 운영 크롤러는 **불변**, PC self-hosted runner 사용 금지 유지.

## 실제 공개 계약 조회 경로 (추측 아님)
실제 G2B 컴파일 화면 `/_wpack_/ui/fi/fiu/fiua/CtrtCrstDtlSrchL.js`가 로드하는 `/bsnejs/fi/fiCommonUntySrchLib.js` (171,170 bytes, sha256 `2f672cf5dcecab907f91578e14c4204cb9f199b78bff9b068d5cd8490c51913a`)에서 `FIUA004_01` 검색 유형 `CTRT`의 공식 읽기전용 엔드포인트와 송수신 DataMap 명세 확인.

```text
POST https://www.g2b.go.kr/fi/fiu/fiua/UntySrch/srchCtrtSttus.do
Content-Type: application/json
Referer: https://www.g2b.go.kr/
Body (first successful test):
{"dlSrchParamM":{"startBizYmd":"20261110","endBizYmd":"20261117","currentPage":1,"recordCountPerPage":"100"}}
```

기존 투찰 상세와 마찬가지로 GitHub-hosted Chrome 세션 `ctx.request.post()`로 직접 수신. 홈페이지 `document.body.childElementCount=0`이어도 수집 성공. `Menu-Info` 헤더 없이도 유효 데이터. 응답 JSON은 기존 투찰 상세의 `result.successBidInfo`와 달리 **루트에** `dlTotalSrchL` 배열과 `dlSetParamM` 페이지 맵이 있음.

## 실제 계약 JSON 1·2페이지

| 증거 | HTTP | 실제 dlTotalSrchL 행 | 원본 바이트 | SHA256 |
|---|---:|---:|---:|---|
| 1페이지 | 200 | 100 | 309959 | `8764e41d8d8d992e9e22ca43e832fd042e8dea5945f7843809caf65a5bb48895` |
| 2페이지 | 200 | 100 | 310681 | `35393ed08fcb418938b746efbb9a3336a8e8fbe87e42fe75f9b80b7d0764c24f` |

서버 `ErrorCode=0`, `ErrorMsg="요청이 정상적으로 처리되었습니다."`. 서버의 당시 `dlSetParamM.totalSize=83866`은 **해당 질의에서 발표된 값**이며, 현재·2년 전체 시장 계약 건수라고 단정하지 않음.

실제 1페이지 최초 항목에 `bizNo=2026SCK004000`, `bizNm=26-00사 사업장폐기물 처리용역`, `bizYmd=20261117`, `ctrtAmt=21260300`, `untySrchSeCd=CUC`. 이는 **원본의 실제 필드명**이며 `bizNo`를 공식 계약번호로 오인하지 말 것. 계약번호와 업체공식키 및 상세 JOIN은 별도 확인 필요.

## 추가 QA — 페이징과 날짜 필터 검증
- 실행 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44200587595
- 동일 날짜 범위 `20261110`~`20261117`의 1·2페이지에서 각각 **100개 고유 `(untySrchSeCd,bizNo,bizOrd)` 조합**, 페이지 사이 중복 **0건**, `bizYmd`는 양 페이지 모두 `20261117`로 날짜 범위 내.
- 실행 시점에 발표된 `totalSize`는 **83874**로 기존 83866보다 8 증가했으므로 실시간 갱신됨. 이 총건수를 고정된 역사적 정답으로 취급 금지.
- 날짜를 단 하루 `20261110`~`20261110`로 변경했을 때 **HTTP 200, 100개 실제 JSON 행**, 샘플 `bizYmd=20261110`, `totalSize=17522`, 원본 응답 **311112바이트**, SHA256 `a84709adca43ae8d7afbf70060f2b0e5993bdaf3f9b025677968c7a734534e2e`.
- 따라서 날짜 조건을 무시하는 가짜 고정 응답이 아님을 실증. 단, 전체 건수의 정확한 원본 집계·기간 내 날짜 누락 여부·복합 중복은 전체 페이지 수집과 교차검증이 필요.

## 제한과 다음 작업
- **계약 목록 실제 데이터 JSON 추출 성공**: 1, 2페이지 200개 행 + 1일 좁힌 질의 샘플 100개. 해당 JSON 원본과 해시 보존.
- 실제 계약 상세, 수의계약 사유, 공동수급, 계약변경, 업체 공식 식별키, MAS 납품요구 및 공고-계약 연결은 미검증.
- 입력의 `bizYmd` 의미와 `ctrtSrchItm*`/계약 상세 필드 정확도는 공식 웹 응답 및 실제 UI 기준으로 추가 검증.
- 최근 2년 전체 수집기·일자별 샤드·완료 체크포인트·Release와 독립 데이터 테이블 적재는 **이 실증 범위 밖**. 재수집 없이 단계적으로 확대해야 함.
- 기존 계약관리 `selectLinkCtrtMngList.do`에서 발생한 403을 공개 검색 `srchCtrtSttus.do`의 접근 불가로 잘못 확대 해석하지 않는다.

**판정: 공개 나라장터 계약 LIST JSON·페이지2·날짜 필터 실제 동작 검증 성공, 최근 2년 전수 수집 및 상세 JOIN 미완료.**
