# 동료 온보딩 (git pull 후 처음 실행)

이 저장소를 처음 받은 동료가 **자기 로컬에서 바로 실행**하기 위한 최소 절차.
경로·데이터·키는 사람마다 다르므로, 마지막의 `preflight`로 자기 환경을 실측·확인한다.

> 런타임(앱 실행)은 커밋된 `storage/` 인덱스만 사용한다 → **원본 PDF 없이도, 재인덱싱 없이도 실행된다.**

---

## 0. 사전 요구사항

| 도구 | 용도 | 설치 |
|------|------|------|
| [uv](https://docs.astral.sh/uv/) | Python 패키지·실행 | mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`<br>Windows(PowerShell): `irm https://astral.sh/uv/install.ps1 \| iex` |
| Python 3.10+ | 런타임 | uv 가 자동 관리 |
| Node 22 | React 버전만 | [nodejs.org](https://nodejs.org) 또는 fnm/nvm |
| OpenAI API 키 | 임베딩·LLM | 공용 키가 없으면 앱에서 각자 입력(BYOK) |

> **Windows 사용자**: 아래 명령은 PowerShell 또는 명령 프롬프트에서 실행한다. React 버전은
> `./dev.sh` 대신 **`dev.bat`** 을 더블클릭하거나 `dev.bat` 으로 실행한다(한글 출력을 위해 UTF-8 코드페이지로 자동 전환).

---

## 1. 코드 받기

```bash
git clone <repo-url> && cd konetic-report-rag
# 이미 clone 했다면:
git pull
```

## 2. 환경설정 (.env)

```bash
cp .env.example .env
```

`.env` 를 열어 **`OPENAI_API_KEY`** 를 채운다. 공용 키가 없으면 비워둬도 되고(앱에서 BYOK 입력),
그 외 값은 기본값으로 충분하다.

> ⚠️ 원본 데이터 경로(`RAG_DATA_DIR`)는 **재인덱싱할 때만** 필요하다(아래 5번). 앱 실행에는 불필요.

## 3. 의존성 설치 + 환경 점검

```bash
uv sync                        # 런타임 의존성
uv run python -m rag.preflight # 내 로컬 상태 점검(한국어 안내)
```

`preflight` 가 `결론: 앱 실행 준비 완료 ✅` 를 출력하면 실행 준비 끝이다.
누락된 것이 있으면 무엇을 어떻게 조치할지 한국어로 알려준다.

## 4. 실행

**Streamlit 버전** (단일 프로세스):

```bash
uv run streamlit run app.py     # http://localhost:8501
```

**React + FastAPI 버전** (SSE 스트리밍, 두 서버를 한 스크립트로):

```bash
./dev.sh                        # macOS/Linux — 시작 전 preflight 자동 실행
dev.bat                         # Windows
```

→ 브라우저 http://localhost:5173 접속(`/api` → 8000 프록시). 각 서버는 `Ctrl-C` 로 종료.

| 서버 | 포트 |
|------|------|
| Streamlit | 8501 |
| FastAPI | 8000 |
| Vite(React) | 5173 |

---

## 5. (선택) 재인덱싱 — 원본 PDF 가 있을 때만

코퍼스를 다시 만들 때만 필요하다. **원본 PDF/엑셀은 저작권상 저장소에 없다**(한국환경산업기술원 소유).

```bash
uv sync --extra indexing        # 인덱싱 의존성(pdfplumber/chromadb/kiwipiepy 등)
# .env 에 원본 폴더 지정:  RAG_DATA_DIR=/내/로컬/KEITI/데이터
#   (그 안에 country_report/ · policy_report/ · report_list.xlsx 가 있어야 함)
uv run python -m rag.indexing.index_pipeline
```

---

## 6. 자주 겪는 문제

| 증상 | 조치 |
|------|------|
| `preflight` 가 storage/ 누락 표시 | `git pull` 로 커밋된 `storage/*` 를 받았는지 확인 |
| 질의 시 키 오류 | `.env` 의 `OPENAI_API_KEY` 확인, 또는 앱 사이드바에서 BYOK 입력 |
| 포트 이미 사용 중 | mac/Linux: `lsof -ti:8000 \| xargs kill` · Windows: `netstat -ano \| findstr :8000` 로 PID 확인 후 `taskkill /PID <PID> /F` |
| `chromadb` 미설치 경고 | 정상 — 자동으로 `memory` 백엔드로 폴백된다 |
| PDF 원문이 안 보임 | 배포/동료 로컬엔 원본 PDF 가 없어 **문서 전문(텍스트)** 으로 표시된다(정상) |

---

전체 로드맵·다음 작업은 [PLAN.md](PLAN.md), 아키텍처·설정 상세는 [../README.md](../README.md) 참조.
