# scourt-news-bot

대법원 `보도자료/언론보도해명(gubun=702)`을 주기적으로 수집해서:
1. 신규 보도자료 확인
2. 첨부 PDF 다운로드/텍스트 추출
3. Auto-Writer 입력용 소스 파일 생성
4. Auto-Writer live 실행으로 머니앤로 CMS `미승인` 기사 초안 저장
5. 펜 카툰 스타일 이미지 프롬프트 반영
6. Telegram 또는 Hermes cron 결과 알림

흐름으로 동작하는 Python 프로그램입니다.

## 1) 설치

```bash
cd /path/to/scourt
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
- `AUTO_WRITER_PROJECT_DIR`: Auto-Writer 프로젝트 경로(기본 운영 경로는 `/Users/sanghoon/codes/Auto-Writer`)

선택:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: Auto-Writer 성공 뒤 직접 Telegram 알림을 보낼 때 사용

주요 옵션:
- `SCOURT_MAX_PAGES`: 매 실행 시 확인할 목록 페이지 수(기본 2)
- `SCOURT_TIMEZONE`: 기본 `Asia/Seoul`
- `SCOURT_SCHEDULE_HOURS`: 기본 `0,3,6,9,12,15,18,21` (3시간마다)
- `AUTO_WRITER_MODE`: 기본 `live` (`dry-run`이면 CMS 저장 없이 산출물만 생성)
- `SCOURT_BOOTSTRAP_SKIP_SEND`: 상태 DB가 비어 있을 때 첫 실행 알림 전송을 건너뛰고 기준선만 저장(기본 `true`)
- `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID`: 기존 운영 머신의 마지막 확인 `seqnum`을 새 환경에 1회 이관할 때 사용

## 3) 1회 실행

```bash
source .venv/bin/activate
scourt-bot run
```

전송 없이 동작 검증:

```bash
scourt-bot run --dry-run
```

## 4) 스케줄 실행 (3시간마다)

```bash
source .venv/bin/activate
scourt-bot schedule
```

- 기본 스케줄: `Asia/Seoul` 기준 `00:00`, `03:00`, `06:00`, `09:00`, `12:00`, `15:00`, `18:00`, `21:00`
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
- 기존 운영 머신에서 넘겨받은 `last_seen_notice_id`가 있으면 `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID`로 지정해 첫 실행 기준선으로 사용할 수 있음
- 처리 실패가 발생한 실행에서는 실패한 신규 글을 다음 실행에서 다시 시도할 수 있도록 `last_seen_notice_id`를 전진시키지 않음

Skyblue 등 기존 운영 머신에서 마지막 워터마크를 확인:

```bash
sqlite3 /path/to/scourt/data/scourt_news.db \
  "select key, value, updated_at from metadata where key='last_seen_notice_id';"
```

## 6) 운영 방식

현재 실운영은 로컬 Hermes cron에서 `scourt-bot run`을 3시간마다 실행하는 방식입니다.

GitHub Actions 워크플로는 Auto-Writer 프로젝트와 CMS 인증이 없는 원격 환경에서 실제 기사 생성을 하지 않도록 수동 smoke check로만 유지합니다:
- `.github/workflows/scourt-news-bot.yml`: 수동 실행 시 `scourt-bot run --dry-run`
- `.github/workflows/scourt-weekly-health.yml`: 수동 실행 시 최근 workflow 로그 점검 payload 출력

실제 운영에 필요한 Auto-Writer 프로젝트 경로, Gemini/CMS 인증, Telegram 설정은 로컬 머신의 `.env`와 Hermes 환경에서 관리합니다.

## 7) 크론으로 실행하고 싶을 때(대안)

애플리케이션 내부 스케줄러 대신 크론을 써도 됩니다.

```cron
0 */3 * * * cd /path/to/scourt && . .venv/bin/activate && scourt-bot run >> logs/scourt-bot.log 2>&1
```
