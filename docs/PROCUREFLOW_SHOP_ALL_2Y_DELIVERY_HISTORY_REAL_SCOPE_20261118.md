# 종합쇼핑몰 최근 2년 전국 전품목 납품요구 전수수집 — 잘못된 검색방식 폐기 및 실제 경로 검증
실기동 2026-11-18 KST / 연구 브랜치 `research/procureflow-contract-web-probe-20261116`

## 1. 반드시 구분: 현재 등록상품 검색 ≠ 2년간의 실제 납품요구 거래

종전 성공 응답 `/gm/gms/gmsd/newShopUntySrchApi.do`의 `rsltList`는 **쇼핑몰 등록상품 현재 검색**이다. 단어 `의자`를 넣고 1·2페이지 각 30행을 받은 증거는 국가 전체 납품요구 원본 수집이 아니다.

- 검색어를 **완전히 비운** 동일 Chrome 세션 직접 POST 실기동: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44212478993
- 입력 `{"searchVO":{"searchKeyword":"","currentPage":1,"recordCountPerPage":"30"}}`
- HTTP 200, ErrorCode 0, 등록상품 30개 행, 당시 서버 `totalSize=1,107,886`.
- 실제 공식 쇼핑몰의 `dlShopSrchM` 입력 필드 전체 분석 결과 `Ymd` 또는 `Date` 날짜 검색 필드 **0개**. `devyCndt`(인도조건)·`sortCndt`(정렬조건)은 날짜가 아니다.
- 첫 30개 표본의 `ctrtYmd` 값에는 `20250516000000`, `20260625000000`, `20260728000000`, `20260930000000`, `20261118000000` 등 여러 시점 계약상품이 뒤섞여 있었다.
- 원본 `unfiltered_catalogue_page1.json` 7,523,786 bytes, SHA256 `5736b291158bca9a6bc59c35eff821c09da8d06b0fb9afe48018c75914928a5a`.
- **따라서 110만 7천여 현재 상품을 긁어도 전국 과거 2년 납품요구 전체는 완성되지 않는다. 이 목록을 납품요구 거래 테이블에 넣지 않는다.**

## 2. 공식 전품목 납품요구 원본 보고서 찾기: 실기동 성공

공공데이터포털 조달청 공식 데이터 `15053481`:
https://www.data.go.kr/data/15053481/fileData.do

- 데이터명: 나라장터쇼핑몰 납품요구 물품 내역
- 보고서 ID `UI-ADOXAA-038R`, 데이터허브 실제 보고서번호 `00118`.
- 보고서 공식 연결 https://data.g2b.go.kr/link/AISC001_01/?reptNm=UI-ADOXAA-038R
- 조달데이터허브 실제 보고서 카탈로그 `selectReptSrchV2Lst.do` → **HTTP 200, ErrorCode 0, 정확히 1개 일치행**. 실기동: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44211003038
- 보고서 분할 기준: ① 전체기간, ② `2021년 1월 이후 자료(조회속도 향상)`. 둘 중 ②가 최근 2년 전체를 포함하며 더 적합.
- 날짜 기준은 공식 제공정보에 명시된 **결재일자**, 서버 갱신은 **전일(D-1)**. 당일 자료는 아직 완전하지 않음.
- 공식 보고서는 품목, 납품요구번호, 변경차수, 수요기관, 업체사업자등록번호, MAS 여부, 계약번호, 물품순번, 납품수량, 납품금액 등의 필드를 제공하는 것으로 설명됨. *필드가 제공된다는 설명만으로 실제 거래행이 수집된 것은 아니다*.

## 3. 실제 보고서 메타데이터 두 가지 조회 성공 / 거래 행 수신은 미완료

- https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44211426273
- 공식 메타데이터 API: `POST https://data.g2b.go.kr/ai/ais/aisc/ReptDtnr/selectReptBfPritm.do`, 입력 `dlSrchParamM`의 `reptId=00118`, `mstrReptIdVal`은 **공개 보고서 목록에 들어있는 식별값**을 사용함.
- ① 전체기간 / ② 2021년 이후 모두 HTTP 200, `ErrorCode=0`, `result`에 `hubReptNo`, `mstrReptIdVal`, `objectType=3`, `mstrReptFrmtCd` 등 보고서 정의 확인.
- 실제 메타데이터 원본 파일: `metadata_0.json` (3,156 bytes; SHA256 `707f617b3e497e037ffa2fcb020749936f0e37071a3792fd208753d0df32bf8c`), `metadata_1.json` (3,218 bytes; SHA256 `6e06eddf2f7c167ec75af3f9e6f14dffcdb429ce8e8030700eae8d5a806e3394`).
- 실제 데이터는 WebSquare에서 곧바로 JSON으로 내려오는 것이 아니라 **MicroStrategy `mstr.getMstrResult`**로 로딩되고 `mstr.downloadCsv`로 내보내는 별도 경로. 공개 정적 스크립트 `/dtap_com/js/mstr.js` 108,082 bytes, SHA256 `e9c39401bf8720bc0169e67caddb4eafd498abbb0fc2a29f3e0d02404090806b`; 실기동 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44211900751
- 이 스크립트에는 비로그인자 게스트 SSO 키 조회가 있으며, **현재 실행에서 게스트 로그인/키 획득·전달·재사용을 진행하지 않음**.
- 익명 Chrome 공식 보고서 페이지 재현 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44212573143 : HTTP 200이지만 DOM 자식 0, `window.mstr=undefined`. 따라서 **실제 보고서 CSV·납품요구 행 수신은 0건 검증**, 브라우저 초기화/공개 보고서 실행 방식 문제는 미해결.

## 4. 2년 전체 대상 정확한 날짜 분할은 생성·검증 완료

- 기준 시작 `2024-11-18`, 당일 기준 종료 희망 `2026-11-18`.
- 공식 D-1 특성에 따라 **현재 확정 조회 가능 대상은 2024-11-18~2026-11-17**, 총 **730일**.
- 2026-11-18은 **당일 반영 대기**로 보존하고 다음 데이터 갱신 뒤 채움.
- 전체 품목, 전체 업체, 전체 기관, **검색어 NULL**, 단위별 `결재일자`를 반드시 명시.
- 날짜별 730일 무결성 검사 + 수집 상태 `not_collected`로 초기화한 검증된 범위 아티팩트: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44212837007
- **730일 범위 검증**은 **730일 실제 데이터 수집 완료와 다르다**. 미수집 일자는 모두 `not_collected`로 기록되며, 검증된 납품요구 원본은 아직 **0행**.

## 5. 개발 재개를 위한 명확한 진입조건

1. 로그인·암호·세션키 수집/재사용 없이 공개 보고서의 정상 뷰/CSV 데이터 1일치 원본을 실제로 받아, 결재일자·납품요구번호·차수·물품순번을 검증한다. 불가능하면 공식적으로 승인된 별도 공개 납품요구 API/파일 경로를 확보한다.
2. 하루 범위로 `totalSize`·페이지 종료·중복률·정확한 순번 필드를 증명한다.
3. **확인된 그 경로에만** 10개 병렬 작업자·원본 SHA-256·ZIP/Release·체크포인트·즉시 후속 디스패치를 적용하여 **730일 전 품목 수집**. 403/로그인/보안문자는 우회하지 않는다.
4. 납품요구번호 + 변경차수 + 물품순번 등의 **검증된 공식 키**로 수정·차수와 중복을 분리하고 업체·계약 테이블과 정확 JOIN. 단순 상품명 유사도 JOIN 절대 금지.
5. 기존 930,379개 공고 원본 및 투찰 ZIP과 운영 수집기는 변경하지 않는다.

**판정: 종합쇼핑몰 전체 상품검색은 2년 납품요구 원본으로 부적격임을 실증, 실제 전국 전품목 납품요구 공식 보고서 식별 및 메타데이터 조회 성공, 730일 대상 범위 검증 완료. 그러나 2년 납품요구 거래행 실제 수집은 아직 시작하지 못함.**
