# HITEL 공개 API 묶음별 AI 교재 분류

- 분류 대상: 원본 `Raw_Documents_18109.csv`의 행 순서 전체.
- 전송: HITEL 공개 `POST /integrations/v1/public/chat`에 여러 제목을 함께 전달.
- 판정: **ChatGPT가 제목 하나하나 직접 판단**. Python은 제목의 과목/학년을 정규식으로 분류하지 않음.
- 실행 설정: 기본 묶음 20건, 동시 작업 3개(실서버 처리량을 검증한 이후 조정).
- 수신: `GET /integrations/v1/public/jobs/{job_id}`, `completed` 상태 및 실제 결과가 있어야 완료.
- 상태: `hitel-ai-batches/jobs/`에 접수된 job_id, `completed/`에 성공한 묶음을 보관해 재실행 시 중복 전송 방지.
- 데이터: 원본 ID·제목·URL 보존, AI 판단 결과는 CSV로 누적.
- 연결: 로그인, API 키, VPN, 프록시 모두 사용하지 않음.

## 시작하기

Python 3 (표준 라이브러리만 사용):

```bash
python tools/zocbo/hitel_public_ai_batch_classifier.py --input Raw_Documents_18109.csv --out hitel-ai-batches --batch-size 20 --workers 3 --limit 100 --dry-run
python tools/zocbo/hitel_public_ai_batch_classifier.py --input Raw_Documents_18109.csv --out hitel-ai-batches --batch-size 20 --workers 3 --limit 100
```

100건의 실제 API 회신 결과를 확인한 후 같은 출력 디렉터리로 전체 실행:

```bash
python tools/zocbo/hitel_public_ai_batch_classifier.py --input Raw_Documents_18109.csv --out hitel-ai-batches --batch-size 20 --workers 3
```

중단 후에는 **동일한 명령을 재실행**. 완료된 묶음은 건너뛰고 queued/running 작업의 동일 job_id를 다시 확인함.

### 주의

실행 파일은 사용자의 18,109건 CSV와 네트워크가 가능한 PC/서버에 있어야 함.
이 브랜치에는 해당 18,109건 원본 CSV를 **공개 업로드하지 않았음**.
GitHub Actions 워크플로는 5개 고정 샘플을 한 번에 보내는 **실서비스 연결 시험**임.
ChatGPT 워커가 연결되지 않거나 AI가 JSON·문서 ID를 누락하면 완료로 계산하지 않음.

다운로드 판정은 **교재를 다운로드하였다는 뜻이 아님**: 초·중등은 전부 대상, 고등은 2022 개정 확인 판본만 대상, 고등 2015 전용 제외, 판본 미확인은 보류.
