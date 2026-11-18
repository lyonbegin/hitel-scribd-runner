# 조달데이터허브 → 종합쇼핑몰 Chrome 직접 POST 실증 (2026-11-18)

## 검증 원칙
- 기존 투찰·나라장터 계약 목록 성공 방식 `Chrome + ctx.request.post(JSON)`을 **두 도메인에 각각 적용**.
- 브라우저 본문이 비어 있어도 실제 DataMap 요청 자체는 성공할 수 있음. HTML 200만으로 데이터 성공 판정 금지.
- GitHub-hosted Ubuntu + Xvfb만 사용, 로그인·세션 우회·PC Runner 재가동 없음. 계약 제출, 주문, 납품요구 접수 등 변경 API는 호출 금지.
- 모든 URL 및 `inData` 매핑은 실제 공개 `/_wpack_/ui/...js`에서 먼저 발견한 뒤 조회.
- 기존 2년 투찰/개찰 Release와 운영 코드는 변경하지 않음.

## ① 조달데이터허브 — 보고서 목록 **실제 JSON 50행**

- 실기동 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44204378250
- 아티팩트 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44204378250/artifacts/14382737405
- 소스 `tools/procureflow/test_real_datahub_report_json.py`
- 실제 공개 화면 `/_wpack_/ui/ai/ais/aisc/ReptLstM.js`에서 조회 API `/ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do` 검증.
- `POST https://data.g2b.go.kr/ai/ais/aisc/ReptLst/selectReptSrchV2Lst.do`
- 입력 `{"dlSrchParamM":{"reptNm":"계약","reptKwSeTy":"","currentPage":1,"recordCountPerPage":"50"}}`
- `HTTP 200`, `ErrorCode=0`, `ErrorMsg="정상적으로 조회되었습니다."`; JSON 루트 `result` **50개 보고서 목록행**.
- 원본 파일 `datahub_report_0_no_menu.json`, **54,789 bytes**, **SHA256 `9b8b421ffbbc2464edaf9c45ef89ab4969c8fb104dad7dd631eadffc6a0df595`**.
- 실제 행 예시: `hubReptNo="00604"`, `reptNm="업무별 구성원별 계약 내역"`; `hubReptNo="00606"`, `reptNm="중앙조달 물품 순번별 계약 내역"` (응답의 목록 중 일부).
- **보고서 카탈로그 메타데이터 50행**이며 개별 보고서의 **계약 금액·계약 구성사 원본 행이나 전체 보고서 출력값이 아님**. 보고서 본문 데이터 추출 미완료.

## ② 종합쇼핑몰 — 실제 계약상품 JSON **30행 + 다음 페이지 30행**

- 실기동 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44205286702
- 상품행/필터행 분리·페이지 간 공식 식별자 중복 QA https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44205491684
- 최종 QA 원본 아티팩트 https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44205491684/artifacts/14382239544
- 소스 `tools/procureflow/test_real_shop_product_json.py`
- 실제 공개 컴파일 화면 `/_wpack_/ui/gl/gla/glab/LomkGdsSrchLst.js`에서 `inData: "searchVO=dlShopSrchM"`, `/gm/gms/gmsd/newShopUntySrchApi.do` 발견.
- `POST https://shop.g2b.go.kr/gm/gms/gmsd/newShopUntySrchApi.do`
- 입력 `{"searchVO":{"searchKeyword":"의자","currentPage":1,"recordCountPerPage":"30"}}`
- `HTTP 200`, `ErrorCode=0`, 응답 루트 `rsltList`의 **실제 상품 30행** 및 `totalSize=68367` (시험 당시 검색어에 대해 반환된 총건수).
- QA 실행의 첫 페이지 **393,271 bytes**, **SHA256 `82ee6a29b4e8291a65c2a4638bca06b0c168c1eec6fde59a3b46f6b09c39a58d`**.
- 다음 페이지 **394,919 bytes**, **SHA256 `00abd8ad7dfa89984a5d3bfe3627caaa41fa45fcd58a1b0a831c185858e52c58`**.
- 페이지별 `(ctrtItemMngNo,itemIdnfNo,ctrtNo)` 고유 30행, **양 페이지 중복 0행**, 두 페이지 합계 60개 상품행.
- `rsltList`와 함께 제공된 업체/분류/품질 필터 목록 `dlGroup...`, `dlGnrlItemEtpsL` 등은 **상품으로 합산하지 않도록 파서 수정 완료**.
- 실제 상품에 `ctrtItemMngNo`, `itemIdnfNo`, `ctrtNo`, `ctrtUprc`, `bzmnRegNo`, `itemCfnm`, `ctrtYmd` 등 원본 필드 존재. 이는 등록 계약물품 검색결과이고 **실제 납품요구 또는 검수 완료 기록은 아님**.

## 남은 작업
1. 데이터허브 `00604` 업무별 구성원별 계약 내역 등 **보고서 내부 계약/공동수급 행**의 실제 데이터 요청과 기간 필터 확인. 보고서 목록 50건만으로 업체별 계약실적 완료 선언 불가.
2. 종합쇼핑몰의 `rsltList` 상세 페이지, 계약변경차수, 상품 등록 이력 및 별도 납품요구번호/차수/품목 원본 조회.
3. 최근 2년 날짜·업무구분별 페이지 완전성 검증, 원본 SHA256/중복/누락/페이징 검증, 별도 테이블 적재 및 공고-계약-상품/납품 공식키 JOIN. 운영 원본 불변 유지.

**판정: 두 서비스에서 읽기 전용 실제 JSON POST 수신 성공. 데이터허브 보고서 실적 본문과 종합쇼핑몰 납품요구 전수수집은 아직 미완료.**
