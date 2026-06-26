# 환경 보고서 RAG 프로토타입

RAGFlow 의 인덱싱/검색 아키텍처를 외부 인프라(ES·MySQL·Redis·MinIO) 없이
**로컬 Chroma + BGE-M3 + Streamlit** 으로 축소 재구성한 프로토타입입니다.
요구하신 ①/② 파이프라인 단계가 코드에 **번호 주석**으로 그대로 표시되어 있습니다.

## 파이프라인 ↔ 파일 매핑

### ① 데이터 인덱싱 파이프라인 (오프라인) → `index_pipeline.py`
| 단계 | 내용 | 도구/모델 | 코드 위치 |
|------|------|-----------|-----------|
| ① | 엑셀 메타데이터 읽기 · PDF 매핑 | pandas | `load_metadata()` |
| ② | 본문 추출 · OCR · 노이즈 제거 | PyMuPDF · pdfplumber · Tesseract | `parse_pdf()` |
| ③ | 문단 청킹 + 메타데이터 부착 | 규칙 기반 | `chunk_pages()` |
| ④ | 임베딩 생성 | BGE-M3 | `common.embed_texts()` |
| ⑤ | 벡터DB·BM25 적재(영속화) | Chroma · rank-bm25 | `build_index()` |

### ② 질의응답 파이프라인 (런타임) → `qa_pipeline.py`
| 단계 | 내용 | 도구/모델 | 코드 위치 |
|------|------|-----------|-----------|
| ① | 질의 + 필터(국가·분야) | — | `answer(query, filters)` |
| ② | 하이브리드 검색 | BGE-M3 · BM25 · Chroma | `hybrid_search()` |
| ③ | 리랭킹(선택) | BGE-reranker | `rerank()` |
| ④ | LLM 답변(근거 한정·인용) | 소형 한국어 LLM(4bit) | `generate_answer()` |
| ⑤ | 대국민 화면(좌우 2분할) | Streamlit | `app.py` |

> RAGFlow 원본 대응: 인덱싱은 `rag/flow/pipeline.py`, 검색·인용은 `rag/nlp/search.py`
> (`Dealer.retrieval`, `insert_citations`), 임베딩은 `rag/llm/embedding_model.py`.
> 융합식 `final = 0.3·vector + 0.7·bm25` 는 RAGFlow 기본 가중치를 그대로 사용.

## 사용 순서

```bash
# 0) 의존성
pip install -r requirements.txt
#    OCR 사용 시 Tesseract 엔진 별도 설치 (Windows: UB-Mannheim 빌드, 한국어 언어팩 포함)

# 1) (이미 준비됨) 원본 데이터는 아래 경로에서 자동 로드 — 별도 복사/업로드 불필요
#    C:\Users\jihyun\Desktop\KEITI_AD\ecolab\데이터
#      ├ country_report\  (PDF 60건)
#      ├ policy_report\   (PDF 30건)
#      └ report_list.xlsx (시트 2개 · 열: 번호/환경분류/국가/제목/내용/태그/파일명)
#    다른 경로면 환경변수로 지정:  set RAG_DATA_DIR=...

# 2) 오프라인 인덱싱 (① 파이프라인) — PDF 90건 파싱·청킹·임베딩·적재
python index_pipeline.py

# 3) 런타임 확인 (CLI)
python qa_pipeline.py "인도네시아 신재생에너지 정책의 핵심은?"

# 4) 대국민 UI 실행 (② + ⑤) — storage/ 를 자동 로드
streamlit run app.py
```

## 임베딩 / LLM 백엔드
- **임베딩(④)**: `sentence-transformers` 로 `BAAI/bge-m3` 구동 (torch CPU 휠 권장).
  최초 1회 모델 가중치(~2.3GB)를 내려받고 이후 캐시 사용.
- **LLM(④, `config.py`)**:
  - `LLM_BACKEND="openai"` (기본): Ollama/vLLM 등 OpenAI 호환 엔드포인트
    - 예) `ollama run qwen2.5:3b-instruct` 후 `OPENAI_BASE_URL=http://localhost:11434/v1`
  - `LLM_BACKEND="transformers"`: 로컬 GPU + 4bit 양자화(bitsandbytes)
  - **LLM 미연결 시**: 검색된 근거를 발췌·인용하는 폴백 답변을 자동 표시(앱은 항상 결과를 보여줌).

## 디렉터리
```
rag_prototype/
├── config.py              # 전역 설정(데이터 경로·모델·가중치·xlsx 스키마)
├── common.py              # 임베딩(BGE-M3)/리랭커/Chroma/BM25 공용 로더
├── index_pipeline.py      # ① 오프라인 인덱싱 (①~⑤)
├── qa_pipeline.py         # ② 런타임 질의응답 (①~④, LLM 폴백 포함)
├── app.py                 # ⑤ Streamlit 좌우 2분할 UI (storage 자동 로드)
├── requirements.txt
└── storage/  chroma/ , bm25.pkl , chunks.jsonl   (인덱싱 산출물·영속화)
```
