# 프로젝트 로드맵 (PLAN)

코네틱 보고서 RAG — OpenAI 전용, Streamlit Cloud 배포(PoC).
상세 아키텍처·배포는 [../README.md](../README.md), 다음 작업은 [nextsession.md](nextsession.md).

## 완료
- [x] 구조 인식 청킹(KEITI 보고서) — 챕터/섹션/표/인터뷰/각주
- [x] 하이브리드 검색(벡터+BM25) + 리랭킹(off/openai LLM)
- [x] OpenAI 전용화(임베딩/리랭크/LLM), bge·torch 제거
- [x] 벡터 저장소 교체형(chroma/memory/remote) + chromadb 미설치 자동 memory 폴백
- [x] 토큰/비용 모니터링(서버 로그 + UI)
- [x] 패키지 구조화(`rag/`, `rag/indexing/`), uv/pyproject + cloud requirements.txt
- [x] BYOK + 공용 키 모드(공용 키 시 입력칸 숨김) + APP_PASSWORD 게이트
- [x] 두 모드: KEITI 고정 코퍼스 / 내 문서 업로드(세션 임시)
- [x] 청킹 아티팩트 수정(쪽번호/표 빈셀/중복/파편) + 재인덱싱
- [x] Streamlit Cloud 배포(공용 키, memory)
- [x] **A+C 맥락 단위 청킹**: 의미 분할(semantic_split) + Contextual Retrieval(LLM 1문장 맥락)
      배선·재인덱싱 완료. 길이상한 절단 제거 → 섹션 통째 유지 후 의미 경계 분할,
      `context_text`가 LLM 맥락(`c['context']`) 우선 사용
- [x] 인덱싱 API 비용 합산 로깅(`monitoring.INDEX_COST`) + 빈맥락 청크 카운트
- [x] UI 정리: 내부 단계번호(1.질문/4.답변) 제거, 사이드바 상태·세션비용 가독성/즉시갱신
- [x] 빈맥락 원인규명(429 레이트리밋)·해결: max_completion_tokens 512, reasoning_effort=low,
      백오프 재시도, 동시성 12→6, 2차 보충 패스
- [x] 우측 패널 개편: 질문 후 '관련 문서'만 표시 → 선택 시 전체화면(로컬 PDF 임베드 /
      배포는 문서 전문 텍스트 / 항상 코네틱 원문 검색 링크)

## 진행 중 / 다음

## 백로그 (우선순위 낮음)
- [ ] 크로스-페이지 섹션 병합(현재 페이지 경계에서 본문이 끊김)
- [ ] 표 추출 품질 향상(행라벨 열 누락 케이스), table_title↔table 매칭 정확화
- [ ] 부모-자식(small-to-big) 검색 옵션
- [ ] 한국어 BM25 토크나이저 고도화(형태소 기반)
- [ ] gpt-5.4-nano 실단가 반영(config.PRICES) / OpenAI 사용 한도 설정
- [ ] requirements.txt 를 `uv export` 로 자동 동기화
- [ ] 평가셋(질문-정답)으로 검색/답변 품질 정량 측정(회귀 방지)

## 운영 메모
- 비용 관리: OpenAI 대시보드 월 한도 설정 권장.
- 공개 URL은 APP_PASSWORD 필수(공용 키 남용 방지).
