# scourt 유지보수 계획

## 기획 의도

이 프로젝트는 대법원 보도자료/언론보도해명 목록을 주기적으로 수집하고, 신규 항목의 PDF와 관련 보도 맥락을 Auto-Writer로 넘겨 머니앤로 CMS 미승인 기사 초안을 만드는 운영용 봇이다. 유지보수의 핵심은 신규 보도자료를 놓치지 않는 안정적인 수집, 실패 시 재시도 가능한 상태 저장, 중복 초안 방지, 사실과 출처를 분리하는 편집 기준 유지다.

## 진행 기록

### 2026-04-27 코드 검토 시작

- GitHub 저장소 `coolpint/scourt`를 `/Users/sanghoon/codes/scourt`에 클론했다.
- 프로젝트 구조, 실행 문서, GitHub Actions 워크플로, 핵심 Python 모듈을 검토했다.
- 검토 기준은 운영 중 누락/중복 알림 가능성, 상태 저장 안정성, 외부 서비스 연동 실패 처리, 테스트 가능성으로 잡았다.

### 2026-04-27 코드 검토 결과

- 처리 실패가 있어도 `last_seen_notice_id`가 최신 공지까지 전진해 실패한 신규 공지가 이후 실행에서 누락될 수 있는 위험을 확인했다.
- 대법원 목록 파싱이 빈 결과를 반환해도 정상 실행으로 기록될 수 있어, 사이트 마크업 변경 또는 일시적 파싱 실패를 주간 점검이 놓칠 수 있는 위험을 확인했다.
- 현재 저장소에는 테스트 파일이 없으므로, 상태 워터마크와 빈 수집 결과를 재현하는 단위 테스트를 우선 추가하는 것이 좋다.
- 문법 검증은 AST 파싱으로 12개 Python 파일을 확인했다.

### 2026-04-27 상태 이관 논의

- 기존 운영 상태는 현재 작업 머신이 아니라 네트워크상의 Skyblue 맥북에어에 있을 가능성이 높다.
- GitHub Actions로 운영을 넘길 때는 Skyblue의 `data/scourt_news.db` 전체를 이관하거나, 최소한 `metadata.last_seen_notice_id` 값을 초기 워터마크로 이관해야 한다.
- 단순히 빈 DB로 GitHub Actions를 시작하면 `SCOURT_BOOTSTRAP_SKIP_SEND=true` 때문에 과거 폭주는 막지만, Skyblue의 마지막 실행 이후 GitHub Actions 첫 실행 전까지 생긴 공지는 건너뛸 수 있다.

### 2026-04-27 상태 이관 및 워터마크 안정화 구현

- `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID` 환경 변수를 추가해 Skyblue에서 가져온 마지막 `seqnum`을 새 운영 환경의 초기 워터마크로 주입할 수 있게 했다.
- 파이프라인이 처리 실패가 있는 실행에서는 `last_seen_notice_id`를 전진시키지 않도록 변경했다.
- `--dry-run` 실행도 실제 전송 기준선을 바꾸지 않도록 워터마크 전진 대상에서 제외했다.
- 첫 목록 페이지가 0건이면 사이트 변경 또는 파싱 실패 가능성이 높으므로 정상 실행이 아니라 오류로 처리하도록 했다.
- `tests/test_pipeline.py`에 초기 워터마크 적용, 실패 시 워터마크 보존, dry-run 워터마크 보존, 빈 첫 페이지 오류 테스트를 추가했다.

### 2026-04-27 리뷰 반영

- 리뷰에서 `dry-run` 상태에서 초기 워터마크가 DB에 저장될 수 있는 문제를 확인했고, `dry-run`일 때는 초기 워터마크를 메모리 기준선으로만 사용하도록 수정했다.
- `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID` 값이 잘못되면 조용히 무시하지 않고 설정 오류로 즉시 실패하도록 수정했다.
- `dry-run` + 초기 워터마크 + 빈 DB 테스트와 잘못된 초기 워터마크 환경 변수 테스트를 추가했다.
- 최종 검증으로 단위 테스트 6개와 AST 문법 검증 13개 파일을 통과했다.

### 2026-04-27 테스트 실행

- `.venv/bin/python -m unittest discover -s tests`로 단위 테스트 6개를 통과했다.
- `.venv/bin/python` 기반 AST 문법 검증으로 13개 Python 파일을 통과했다.
- 실제 대법원 사이트 대상 `scourt-bot run --dry-run`을 임시 DB/PDF 경로(`/tmp/scourt-test`)로 실행했고, 1페이지 10건을 수집해 `processed=10 sent=0 failed=0`으로 완료했다.
- dry-run 실행 후 임시 DB의 `metadata`에는 워터마크가 저장되지 않았고, `notices`에는 검증용 기사 10건이 저장됐다.

### 2026-04-27 Teams 실제 전송 테스트

- 사용자가 Webhook 값을 `.env.example`에 넣은 것을 확인했고, 값을 출력하지 않은 채 `.env`로 복사한 뒤 `.env.example`은 샘플 상태로 되돌렸다.
- 임시 DB/PDF 경로(`/tmp/scourt-send-test-1738`)와 `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID=1737`을 사용해 최신 1건만 대상으로 제한했다.
- 실제 전송 결과는 `scanned=10 processed=1 sent=1 skipped=9 failed=0`이었다.
- 전송 대상은 `notice_id=1738`, 제목은 `임금 사건(2024다316599) 보도자료`였다.
- 임시 DB의 `last_seen_notice_id`가 `1738`로 저장되고, 해당 공지의 `sent_at`이 기록된 것을 확인했다.

### 2026-04-28 업데이트 없음 확인

- 대법원 목록 1페이지를 직접 조회해 현재 최신 `notice_id`가 여전히 `1738`임을 확인했다.
- `SCOURT_INITIAL_LAST_SEEN_NOTICE_ID=1738` 기준 dry-run 결과는 `scanned=10 processed=0 sent=0 skipped=10 failed=0`이었다.
- 따라서 Teams에 새 내용이 없는 것은 코드 오류가 아니라, 기준선 이후 신규 공지가 없기 때문으로 판단했다.

### 2026-06-19 커밋 전 최근 변화 점검

- 5월 변경으로 운영 목적이 Teams 요약 알림에서 Auto-Writer CMS 초안 생성 및 선택적 Telegram 알림으로 전환된 것을 확인했다.
- 새 모듈 `auto_writer.py`, `news_research.py`, `telegram.py`와 관련 파이프라인/설정/문서 변경을 검토했다.
- 운영 산출물인 `data/auto_writer_sources/`가 커밋에 섞이지 않도록 `.gitignore`에 추가했다.
- 단위 테스트 8개와 AST 문법 검증 16개 파일을 통과했다.
- 실제 dry-run 결과는 `scanned=10 processed=0 sent=0 skipped=10 failed=0`이며, 현재 운영 DB 기준 `last_seen_notice_id=1762`, 대법원 최신 공지도 `1762`로 신규가 없음을 확인했다.

### 2026-06-19 커밋 전 리뷰 반영

- 리뷰에서 Auto-Writer 성공 후 Telegram 실패가 중복 초안을 만들 수 있는 문제를 확인했다.
- Auto-Writer가 성공하면 먼저 `sent_at`과 `stats.sent`를 기록하고, Telegram 실패는 경고 로그만 남기도록 수정했다.
- `weekly_health.py`가 제거된 `Settings.teams_webhook_url`을 참조해 크래시할 수 있는 문제를 수정했다.
- GitHub Actions 워크플로는 현재 실운영 경로가 아니므로 자동 schedule을 제거하고 수동 dry-run smoke check로 낮췄다.
- GitHub Actions 관련 README 설명도 로컬 Hermes/Auto-Writer 운영 중심으로 고쳤다.
- CMS 초안 생성과 관련 보도 반영 기준을 `constitution.md`로 승격하고, `.agents/constitution.md`와 `.agents/review.md`를 추가했다.
- 최종 검증으로 단위 테스트 10개, AST 문법 검증 17개 파일, 실제 대법원 dry-run, `git diff --check`를 통과했다.

### 2026-07-09 주간점검 Teams 전송 중단

- 주간점검은 Teams 웹훅으로 보내지 않고 Codex 앱 또는 터미널에서 직접 확인하는 방식으로 바꿨다.
- `weekly_health.py`에서 Teams MessageCard payload 생성과 webhook POST 경로를 제거하고, 텍스트/JSON 출력만 지원하도록 변경했다.
- 공개 GitHub Actions run 목록은 `GITHUB_TOKEN` 없이도 조회할 수 있게 했고, 토큰이 없을 때 로그 아티팩트 접근 제한은 오류로 보지 않도록 했다.
- 현재 GitHub Actions는 수동 smoke check 성격이므로 주간점검의 정기 실행 횟수 기대치 비교는 기본 비활성화했다.
- Codex 앱에서 직접 실행한 주간점검 결과는 `워크플로 성공 14회 / 실패 0회`, `최근 정상 실행 2026-07-09 13:48 KST`, `정상 작동중`이었다.

### 2026-07-09 Teams 전송 경로 완전 차단

- 코드 전체에서 Teams 웹훅, MessageCard, Teams POST 경로를 재점검했다.
- 예전 `TeamsNotifier` 모듈이 남아 있어도 실수로 호출하면 전송하지 않고 `RuntimeError`를 내도록 비활성화했다.
- `tests/test_teams.py`를 추가해 Teams 전송이 비활성화되어 있음을 테스트로 고정했다.
- 최종 검증으로 단위 테스트 11개와 AST 문법 검증 18개 파일을 통과했다.

### 2026-05-19 Auto-Writer 연동 복구 및 3시간 모니터 전환

- 이전 수정에서 테스트는 Telegram + Auto-Writer 경로를 기대하지만 실제 `pipeline.py`는 Teams 전송 로직으로 남아 있는 불일치를 확인했다.
- `AutoWriterRunner`를 추가해 신규 대법원 보도자료를 Auto-Writer CLI(`node src/index.js run --mode live --channel scourt --source ...`)로 넘기도록 복구했다.
- Auto-Writer 소스 파일에는 대법원 기사 작성 기준(최신 기사/보도 맥락 확인, 사실 체크리스트, 과장 금지)과 `AUTO_WRITER_IMAGE_STYLE` 펜 카툰 지시를 함께 넣는다.
- 직접 Telegram Bot 설정이 있으면 처리 결과를 알리고, Hermes cron이 stdout을 전달하는 방식도 사용할 수 있게 알림을 선택 사항으로 유지했다.
- 기본 스케줄을 하루 2회에서 3시간마다(`0,3,6,9,12,15,18,21`)로 바꿨다.

### 2026-05-21 Gemini 모델 선택 UI 변경 대응

- 18시 cron 실행에서 신규 3건이 들어왔지만 Auto-Writer가 Gemini 모델 선택 단계에서 `Pro` 메뉴를 찾지 못해 실패했다.
- 실제 Gemini 메뉴가 `3.1 Pro 고급 수학 및 코딩`처럼 버전명이 앞에 붙는 형식으로 바뀐 것을 확인했다.
- `/Users/sanghoon/codes/Auto-Writer/src/lib/services/geminiGem.js`의 모델 옵션 매칭을 수정해 `Pro`가 메뉴 문구 중간에 있어도 선택되도록 했다.
- 누락된 대법원 보도자료 3건(`1754`~`1756`)을 수동 재처리해 Auto-Writer summary 생성 및 DB `last_seen_notice_id=1756` 갱신을 확인했다.
- Hermes no_agent cron 스크립트는 120초 제한으로 live Auto-Writer 1건 처리도 끊길 수 있어, `/Users/sanghoon/.hermes/scripts/scourt_auto_writer_monitor.py`가 백그라운드 worker를 띄우고 다음 주기에 결과를 보고하는 구조로 바꿨다.

## 현재 결정

- 이제 운영 목적은 Teams 요약 알림이 아니라, 신규 대법원 보도자료를 Auto-Writer로 넘겨 머니앤로 CMS 미승인 기사와 펜 카툰 이미지를 만드는 것이다.
- 후속 유지보수에서는 상태 워터마크(`last_seen_notice_id`) 갱신 시점, Gemini UI 변경, Hermes cron의 120초 제한, Auto-Writer 실패 시 재시도 가능성을 가장 우선적으로 점검한다.
- 프로젝트 판단 기준이 더 필요해질 경우 `constitution.md`를 별도로 만들고, 중요한 의사결정은 그 기준에 맞춰 진행한다.

### 2026-09-04 운영 장애 재점검 및 주간점검 신뢰성 보강

- 로컬 Hermes 실행에서 공지 `1794`가 Auto-Writer의 ChatGPT 이미지 캡처 360초 시간 초과로 실패한 것을 확인했다. DB의 `sent_at`은 비어 있고 워터마크는 `1793`에 머물러 있어, 실패 공지는 다음 주기에 재시도된다.
- 주간점검이 수동 실행을 집계만 하고 건강 판정에서는 제외하는 결함과, 최근 1주 실행이 하나도 없어도 정상으로 표시하는 결함을 재현했다.
- 주간점검은 모든 최근 워크플로 실행의 성공·실패를 판정에 포함하고, 최근 실행이 없으면 점검 필요로 표시하도록 수정했다.
- 관련 단위 테스트는 수동 실행 실패, 무실행, 텍스트·JSON 직접 출력까지 검증하도록 보강했다.
- 원격 `main`은 아직 Teams 웹훅을 포함한 이전 워크플로를 사용하고 있다. 로컬의 Teams 차단 변경을 검증·커밋·푸시해 원격에도 반영해야 한다.
- 리뷰에서 실행 중인 워크플로를 실패로 오인할 수 있는 점과 페이지네이션 누락을 발견했다. 진행 중 실행은 별도 집계하고, GitHub Actions 실행 목록은 다음 페이지 링크가 끝날 때까지 조회하도록 보완했다.
- 최종 검증으로 단위 테스트 17개, AST 문법 검사 18개 파일, `git diff --check`, 공개 GitHub Actions 이력 기반 주간점검을 통과했다. 현재 원격 실행이 최근 1주간 없다는 점은 점검 필요로 정확히 표시된다.
