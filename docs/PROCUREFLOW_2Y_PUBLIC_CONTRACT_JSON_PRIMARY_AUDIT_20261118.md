# 공개 통합검색 JSON 원본 독립 감사 — 2026-11-18

## 원본 출처
- GitHub-hosted Chrome/Xvfb 실행: https://github.com/lyonbegin/hitel-scribd-runner/actions/runs/44200587595
- Actions 아티팩트 ID 14382010011, ZIP 51,451 bytes (GitHub artifact digest sha256:5ff686d46f3792ef3f3f31380180a3481788863aec4e88846719d634e0bdc43f)
- 실제 ZIP을 다운로드하여 내부 `summary.json`, 페이지1, 페이지2, 좁은 날짜 검색 JSON을 열어 각각 바이트 SHA256을 독립 계산.
- 공식 JS: https://www.g2b.go.kr/bsnejs/fi/fiCommonUntySrchLib.js
- 관측한 읽기 전용 POST: https://www.g2b.go.kr/fi/fiu/fiua/UntySrch/srchCtrtSttus.do
- POST JSON: `{"dlSrchParamM":{"startBizYmd":"20261110","endBizYmd":"20261117","currentPage":1,"recordCountPerPage":"100"}}`. 로그인, API키, 인증 우회, 구매/제출 없음.

## 실제 원본 3개
| 응답 | HTTP | JSON 바이트 | 독립 SHA256 | 행 | totalSize |
|---|---:|---:|---|---:|---:|
| page1 `contract_list_0_no_menu.json` | 200 | 309959 | `c70f815d7f7bdee3fd20c0fd49c76a340b36cb84989c231ac4087d6b211665c7` | 100 | 83874 |
| page2 `contract_list_page2.json` | 200 | 310681 | `e6a6f9352e2fb66b7f10eac51eb9bca18c899cc2bbb6257d3088b171f2772d92` | 100 | 83874 |
| narrow `contract_list_narrow_date.json` | 200 | 311112 | `a84709adca43ae8d7afbf70060f2b0e5993bdaf3f9b025677968c7a734534e2e` | 100 | 17522 |

세 원본 모두 JSON `ErrorCode=0`, `dlTotalSrchL` 배열 100개, `dlSetParamM.totalSize` 존재. 페이지 1·2에서 `(untySrchSeCd,bizNo,bizOrd)` 키는 각 100개 유일하고 교집합 0. 페이지 1·2의 `bizYmd`는 모두 20261117, 단일 날짜 요청은 모두 20261110. 좁은 날짜 요청의 totalSize는 17522로 바뀌어 서버 날짜 조건 반영의 강한 증거.

## 주의: 계약 확정 원본으로 오분류 금지
- 이 API는 `UntySrch` 통합검색이며 반환 행의 `untySrchSeCd` 예시는 `CUC`; `bizNo`, `bizOrd`, `bizYmd`, `ctrtAmt`, `ctrtTyCd` 등의 필드가 있으나, **각 행이 실제 계약 체결 내역인지 아직 독립 확인되지 않았다.**
- `bizYmd`는 검색 업무일 필드이며 계약일 `ctrtCntgYmd`로 취급하면 안 된다. 실제 행의 `ctrtCntgYmd` 및 `untyCtrtMngNo`는 확인된 예시에서 없음.
- `totalSize=83874`는 해당 기간 통합검색 응답의 보고치이며 최근 2년 계약 수나 실제 수집 건수가 아니다. 200행은 두 페이지 샘플이지 전체 적재가 아니다.
- 아직 공식 계약 상세 1건의 원본 JSON·계약번호 매칭, 112R/113R, MAS/납품요구 원본, 독립 DB 적재·JOIN은 미검증. 전체 완료 판정 금지.
- 후속 단계는 `untySrchSeCd` 분류별 의미를 공식 화면 코드로 검증하고 실제 계약 상세 조회를 동일한 공식 키로 연결한 다음에만 계약 엔터티에 적재한다.

## 원본 보존 제약
기존 930379 공고목록, 187쌍 원본 Release, 운영/복구 워크플로, self-hosted PC Runner에는 변경을 가하지 않았다. `no_bidder_rows_unverified`는 확정 무응찰로 재분류하지 않는다.
