# scourt-news-bot

대법원 `보도자료/언론보도해명(gubun=702)`을 주기적으로 수집해서:
1. 신규 보도자료 확인
2. 첨부 PDF 다운로드/텍스트 추출
3. 기사형 요약 생성
4. Microsoft Teams 카드(Webhook)로 전송

흐름으로 동작하는 Python 프로그램입니다.

Teams 카드 포맷:
- 헤드라인
- 본문(핵심 내용 1000자 이내)
- 보도자료 상세/PDF 링크 버튼

## 1) 설치

```bash
cd /Users/air/codes/scourt
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

## 2) 환경 변수

`.env.example`을 복사해 `.env`를 만든 뒤 값을 채웁니다.

```bash
cp .env.example .env
```

필수:
- `TEAMS_WEBHOOK_URL`: Teams Incoming Webhook URL

주요 옵션:
- `SCOURT_MAX_PAGES`: 매 실행 시 확인할 목록 페이지 수(기본 2)
- `SCOURT_TIMEZONE`: 기본 `Asia/Seoul`
- `SCOURT_SCHEDULE_HOURS`: 기본 `10,18`
- `SCOURT_BOOTSTRAP_SKIP_SEND`: 상태 DB가 비어 있을 때 첫 실행 알림 전송을 건너뛰고 기준선만 저장(기본 `true`)

## 3) 1회 실행

```bash
source .venv/bin/activate
scourt-bot run
```

전송 없이 동작 검증:

```bash
scourt-bot run --dry-run
```

## 4) 스케줄 실행 (오전 10시, 오후 6시)

```bash
source .venv/bin/activate
scourt-bot schedule
```

- 기본 스케줄: `Asia/Seoul` 기준 `10:00`, `18:00`
- 즉시 1회 테스트 후 스케줄 유지:

```bash
scourt-bot schedule --run-now --dry-run
```

## 5) 상태 저장

- SQLite: `data/scourt_news.db`
- PDF 파일: `data/pdfs/*.pdf`

중복 방지 방식:
- `notice_id(seqnum)` 기준 레코드 관리
- `last_seen_notice_id`(최신으로 확인한 seqnum) 기준으로 신규만 선별
- 제목/본문/PDF 해시로 콘텐츠 해시를 만들어 변경 없는 항목은 재전송하지 않음
- DB가 비어 있는 초기/복구 실행에서는 과거 글 폭주를 막기 위해 알림 전송 없이 상태만 저장(기본 동작)

## 6) GitHub Actions로 상시 운영 (로컬이 꺼져도 실행)

이미 워크플로 파일이 포함되어 있습니다:
- `.github/workflows/scourt-news-bot.yml`
- 실행 시각: 매일 `10:00`, `18:00` KST
- GitHub cron 기준으로는 `01:00`, `09:00` UTC

설정 절차:
1. GitHub 저장소에 코드 푸시
2. 저장소 `Settings > Secrets and variables > Actions`에서 시크릿 추가
   - `TEAMS_WEBHOOK_URL`: Teams Incoming Webhook URL
3. `Actions` 탭에서 `scourt-news-bot` 워크플로 활성화

상태 유지:
- 워크플로가 `data/scourt_news.db`를 GitHub Actions Cache로 복원/저장
- 이전 실행 상태를 이어받아 중복 전송을 방지

## 7) 크론으로 실행하고 싶을 때(대안)

애플리케이션 내부 스케줄러 대신 크론을 써도 됩니다.

```cron
0 10,18 * * * cd /Users/air/codes/scourt && . .venv/bin/activate && scourt-bot run >> logs/scourt-bot.log 2>&1
```
