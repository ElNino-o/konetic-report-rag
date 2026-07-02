# Design System — 코네틱 보고서 Q&A (RAG)

/ design-consultation 으로 생성 · 리서치 기반(Elicit · gov.uk Design System · Toss). 승인 팔레트: **C · 잉크 & 틸**.
UI/시각 결정 전 이 파일을 먼저 읽는다. 임의 변경 금지 — 변경은 명시 승인 후 Decisions Log에 기록.

## Product Context
- **무엇:** KEITI(코네틱) 환경·정책 보고서 90건을 대상으로 한 한국어 RAG Q&A. 답변마다 출처·페이지를 인용.
- **누구:** 환경/정책 실무자·연구자 (수출기업, 규제 대응, 시장조사).
- **공간:** 인용형 AI 리서치 도구 (peers: Elicit, Perplexity, Consensus) + 공공/연구 신뢰 톤(gov.uk).
- **타입:** 3-zone 리서치 웹앱 (사이드바 · 답변 · 근거 레일).
- **핵심 인상(memorable thing):** **"믿을 수 있다" — 모든 답변에 검증 가능한 출처·페이지.** 모든 디자인 결정은 여기에 복무한다.

## Aesthetic Direction
- **방향:** 차분한 연구 도구 (Calm research instrument).
- **장식 수준:** intentional — 타이포·여백·경계선이 일한다. 그라디언트·그림자 남용·이모지 아이콘 금지.
- **무드:** 조용하고 신뢰감 있는 학술 도구. 관공서스럽지 않게, 프리미엄하게.
- **차별점:** 인용을 각주가 아닌 **1급 시각 요소**로 승격 — 인라인 인용 칩 hover 시 우측 근거 카드 하이라이트.
- **레퍼런스:** elicit.com · design-system.service.gov.uk · toss.im

## Typography
- **본문·UI·제목(한/영):** **Pretendard** — 한국 웹 표준, 중립적·고가독. `Pretendard Variable` CDN.
- **수치 전용:** **IBM Plex Mono** (tabular-nums) — 비용·토큰·시간 등 숫자에만. "계측기" 느낌.
- **금지:** system-ui/맑은 고딕/Segoe UI를 display·body 주 폰트로 사용(기존 Streamlit 잔재).
- **로딩:** Pretendard `https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css` · IBM Plex Mono Google Fonts.
- **스케일(px):** display 38/800 · h1 24/800 · h2 18/700 · h3 15/600 · body 15/400·500 · small 13 · caption 11.5. 자간 제목 -.02em.
- **한국어 줄바꿈(필수):** `word-break: keep-all` + `text-wrap: pretty`. 본문 측정폭 `max-width: 64ch`. 절 중간 orphan 금지.

## Color — Palette C (잉크 & 틸), restrained (뉴트럴 + 단일 틸 액센트)
- **배경:** `#FFFFFF` · 캔버스/근거레일 `#FAFAF9`
- **표면(카드):** `#FFFFFF`
- **Primary(잉크, near-black):** `#16181D` — 버튼·활성. 흰 텍스트. Linear/Vercel식 모던·중립.
- **Primary tint:** `#F0F1EE` — 활성 배경(모드 선택 등)
- **인용/액센트(틸):** `#0F766E` / tint `#E4F1EF` — 인라인 인용 칩·근거 번호·score 바. 근거(핵심 인상)를 또렷하게 살리는 유일한 컬러.
- **잉크(본문):** `#111114` · **뮤트(보조):** `#57575E` (AA 통과) · **faint:** `#8A8A90`
- **경계:** hairline `#E8E8E6` · strong `#DADAD7`
- **시맨틱:** success `#0F766E`(틸) · warning `#9A6B1E`/tint `#FBF2E0` · error `#B4232B` · info = 틸
- **금지:** 빨강을 primary/버튼에(기존 Streamlit `#ff4b4b`), 보라 그라디언트, 그라디언트 버튼, "AI 디폴트 블루".
- **다크 모드:** 표면 재설계 — bg `#141514` surface `#1C1E1C`, 틸 밝혀 `#4FD1C5`, 잉크 `#ECEFEA`.

## Information Altitude (엄밀한 UX 원칙 — 시스템 내부를 사용자 화면에 노출 금지)
- **사용자 컨트롤(1급):** 모드(KEITI/업로드), 질문, 답변 형태(요약/일반/전문가).
- **파워유저(고급, de-emphasize):** 리랭킹 → **"정확도 우선 / 속도 우선"** 사용자 이득 언어로. 모델명(gpt-5.4-nano) 노출 금지.
- **신뢰 신호(맥락 카피):** 코퍼스 크기는 통계 박스가 아니라 문장으로 ("90건의 KEITI 보고서에서 근거를 찾았습니다").
- **제거:** "청크 N" 등 RAG 내부 지표는 사용자 화면에서 삭제.
- **개발자/모니터링(옵트인):** 비용·토큰·타이밍·모델명은 기본 숨김 → 답변 아래 **"처리 상세 ▾"** 접힘. 비용 카운터를 상시 chrome으로 두지 않는다(불안 유발·무의미).

## Spacing
- **기본 단위:** 8px 그리드.
- **밀도:** comfortable (읽기 우선, 대시보드 밀도 아님).
- **스케일:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64).

## Layout
- **접근:** hybrid — 앱은 grid-disciplined 3-zone, 여백은 넉넉히.
- **그리드:** 데스크톱 `사이드바 220 · 답변 1fr · 근거레일 300~310`. `≤920px` 단일 컬럼(사이드바·레일 접힘/스택).
- **최대 콘텐츠 폭:** 답변 본문 64ch. 앱 셸은 풀폭.
- **Border radius:** sm 7px · md 11px · lg 16px · pill 999px.

## Motion
- **접근:** minimal-functional — 답변 토큰 스트리밍 페이드, 인용 hover 하이라이트만. 스크롤 연출·choreography 없음.
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out).
- **Duration:** micro 80ms · short 160ms · medium 240ms.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-02 | 초기 디자인 시스템 생성 | /design-consultation · Elicit/gov.uk/Toss 리서치 |
| 2026-07-02 | 팔레트 C(잉크 & 틸) 확정 | 후보 A/B/C 실측 비교 후 사용자 선택 — 니어블랙 + 틸 인용, "AI 디폴트 블루"·그린 클리셰 회피, 인용 또렷 |
| 2026-07-02 | Information Altitude 원칙 추가 | 사이드바가 청크수·비용·모델명 등 시스템 내부를 노출 → 사용자중심 재구조화(모니터링은 옵트인 접힘) |
| 2026-07-02 | Streamlit 빨강(#ff4b4b)·Windows 폰트·이모지 아이콘 폐기 | "AI/디폴트 느낌" 제거, 근거 1급 승격 |
