"""
프로젝트 전역 설정.

RAGFlow 대응 개념:
- RAGFlow 는 service_conf.yaml + docker/.env 로 엔진/모델을 구성한다.
- 본 프로토타입은 외부 서비스(ES/MySQL/Redis/MinIO) 없이 로컬 디스크 + Chroma 만으로
  동작하도록 축소했다. (드라이브 영속화)
"""
from __future__ import annotations

import os
from pathlib import Path

# ── .env 로드 (API 키 등 비공개 설정) ───────────────────
# python-dotenv 로 같은 폴더의 .env 를 읽어 os.environ 에 주입한다.
# .env 는 .gitignore 에 등록되어 GitHub 에 올라가지 않는다.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# ── 경로 ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent

# 실제 원본 데이터 위치 (사용자가 별도 업로드하지 않고 여기서 자동 로드)
# 환경변수 RAG_DATA_DIR 로 덮어쓸 수 있다.
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", r"C:\Users\jihyun\Desktop\KEITI_AD\ecolab\데이터"))
# 보고서 PDF 가 들어 있는 하위 폴더들 (90건 = country 60 + policy 30)
PDF_SUBDIRS = ["country_report", "policy_report"]
METADATA_XLSX = DATA_DIR / "report_list.xlsx"   # 메타데이터 엑셀 (시트 2개)

STORAGE_DIR = ROOT / "storage"              # 인덱스 영속화 위치 (드라이브)
CHROMA_DIR = STORAGE_DIR / "chroma"         # ⑤ Chroma 벡터DB 파일
CHUNK_DUMP = STORAGE_DIR / "chunks.jsonl"   # ③ 청크 원문 백업 (백엔드 공통)


def pdf_dirs() -> list[Path]:
    """PDF 가 들어 있는 모든 하위 폴더 경로."""
    return [DATA_DIR / d for d in PDF_SUBDIRS]


# ── 임베딩 백엔드별 인덱스 분리 (bge-m3 vs openai 공존·비교) ──
# 같은 청크(chunks.jsonl)에 벡터만 달리 적재해 공정 비교가 가능하다.
# bge-m3 는 기존 인덱스 이름(reports/bm25.pkl)을 유지(재인덱싱 회피).
_COLLECTION = {"bge-m3": "reports", "openai": "reports_openai"}
_BM25 = {"bge-m3": "bm25.pkl", "openai": "bm25_openai.pkl"}


def collection_name() -> str:
    """Chroma 컬렉션 이름 (백엔드별)."""
    return _COLLECTION.get(EMBED_BACKEND, f"reports_{EMBED_BACKEND}")


def bm25_path() -> Path:
    """BM25 피클 경로 (백엔드별)."""
    return STORAGE_DIR / _BM25.get(EMBED_BACKEND, f"bm25_{EMBED_BACKEND}.pkl")


def npz_path() -> Path:
    """인메모리(numpy) 벡터 저장 파일 경로 (임베딩 백엔드별)."""
    return STORAGE_DIR / f"{collection_name()}.npz"


# ── 벡터 저장소 백엔드 (배포 형태 선택) ──────────────────
#   "chroma" : 로컬 영속 Chroma (개발 기본)
#   "memory" : npz + chunks.jsonl 를 메모리에 올려 numpy 코사인 (Streamlit Cloud용·서버리스)
#   "remote" : 로컬에서 띄운 Chroma 서버에 HTTP 접속 (터널로 노출)
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chroma")   # chroma | memory | remote

# remote 접속 정보 (chroma run --host 0.0.0.0 --port 8000 후 터널 노출)
CHROMA_HTTP_HOST = os.getenv("CHROMA_HTTP_HOST", "localhost")
CHROMA_HTTP_PORT = int(os.getenv("CHROMA_HTTP_PORT", "8000"))
CHROMA_HTTP_SSL = os.getenv("CHROMA_HTTP_SSL", "false").lower() == "true"
CHROMA_HTTP_TOKEN = os.getenv("CHROMA_HTTP_TOKEN", "")    # 서버 인증 토큰(선택)


# ── ① 메타데이터 엑셀 스키마 (report_list.xlsx 실제 열) ──
# 시트: ["국가별 보고서", "정책규제보고서"]
# 열  : 번호 · 환경분류 · 국가 · 제목 · 내용 · 태그 · 파일명
META_KEY_COLUMN = "파일명"                  # PDF 파일명 — PDF 파일과 매핑하는 키
META_COLUMNS = {
    "field": "환경분류",   # 분야
    "country": "국가",     # 국가
    "title": "제목",       # PDF 제목
    "summary": "내용",     # 보고서 요약 본문 (PDF 파싱 실패 시 폴백 텍스트로도 사용)
    "tags": "태그",        # 키워드 태그
}
# 엑셀에 없는 항목 → 파생/기본값
#   발행연도: 파일명 접두사 "(25AR-..)" 의 앞 2자리(25) → 2025 로 추론
#   출처    : 시트명(국가별 보고서 / 정책규제보고서) 을 사용

# ── ②/③ 파싱·청킹 파라미터 ──────────────────────────────
OCR_LANG = "kor+eng"        # Tesseract 언어팩
OCR_MIN_CHARS = 50          # 페이지 텍스트가 이보다 적으면 스캔본으로 보고 OCR 시도
CHUNK_TOKEN_NUM = 256       # 청크 목표 토큰수 (RAGFlow naive_merge 기본값 128을 보고서용으로 확대)
CHUNK_OVERLAP = 0.1         # 청크 간 중첩 비율 (10%)
PARA_DELIMITERS = "\n\n"    # 문단 분할 기준 (규칙 기반)

# ── ④ 임베딩 백엔드 (교체형: 로컬 bge-m3 ↔ OpenAI API) ──
#   "bge-m3" : sentence-transformers 로컬(무료·한국어 강함·CPU 느림)
#   "openai" : OpenAI 임베딩 API(빠름·고차원·소액 비용)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "bge-m3")   # "bge-m3" | "openai"

# (A) 로컬 BGE-M3
EMBED_MODEL = "BAAI/bge-m3"   # 오픈 · 한국어 지원 (RAGFlow BuiltinEmbed 와 동일 모델)
EMBED_MAX_TOKENS = 8000       # bge-m3 토큰 한도
EMBED_DIM = 1024              # bge-m3 dense 차원

# (B) OpenAI 임베딩
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
# 차원 축소 지원(3-large=3072, 3-small=1536). 0이면 모델 기본값 사용.
OPENAI_EMBED_DIM = int(os.getenv("OPENAI_EMBED_DIM", "0"))

# ── ③ 리랭커 (선택) — 백엔드 교체형 ─────────────────────
#   "off"    : 리랭킹 생략(하이브리드 점수 순서 그대로) — 가장 빠름
#   "local"  : CrossEncoder(BGE-reranker) 로컬 — 품질↑·CPU 느림(병목)
#   "openai" : OpenAI LLM 리스트와이즈 리랭크(API 1회) — 빠름·소액 비용
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "openai")   # "off" | "local" | "openai"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"                  # local 백엔드용
# OPENAI_RERANK_MODEL 은 LLM 섹션(OPENAI_MODEL 정의) 뒤에서 설정한다.

# ── 💰 가격표 (USD / 1M 토큰) — 비용 추정용 ──────────────
# 주의: gpt-5.4-nano 단가는 추정치이므로 실제 단가에 맞게 조정하세요.
PRICES = {
    "chat": {
        "gpt-5.4-nano": {"in": 0.05, "out": 0.40},
        "default": {"in": 0.15, "out": 0.60},
    },
    "embed": {
        "text-embedding-3-large": 0.13,
        "text-embedding-3-small": 0.02,
        "default": 0.10,
    },
}

# ── 하이브리드 검색 가중치 (RAGFlow rerank 융합식과 동일) ─
#   final = VECTOR_WEIGHT * vector_sim + (1 - VECTOR_WEIGHT) * bm25_sim
VECTOR_WEIGHT = 0.3           # RAGFlow 기본값
TOP_K_RETRIEVE = 20           # 1차 후보 수
TOP_N_RERANK = 5             # 리랭킹/LLM 컨텍스트로 넘길 최종 개수
SIMILARITY_THRESHOLD = 0.1    # 최소 유사도

# ── ④ LLM (답변 생성) ───────────────────────────────────
# 기본 백엔드: OpenAI API. (transformers 4bit 로컬 백엔드도 지원)
LLM_BACKEND = os.getenv("LLM_BACKEND", "openai")   # "openai" | "transformers"

# (A) transformers 백엔드 (로컬 GPU + 4bit 양자화)
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")
LLM_LOAD_4BIT = True

# (B) OpenAI API 백엔드 ───────────────────────────────────
# API 키는 코드에 직접 쓰지 않고 .env 의 OPENAI_API_KEY 에서 불러온다.
# OPENAI_BASE_URL 을 비우면 openai 라이브러리 기본값(https://api.openai.com/v1) 사용.
# 주의: openai 클라이언트는 빈 문자열 OPENAI_BASE_URL 도 직접 읽어 'protocol 누락' 오류를
#       내므로, 비어 있으면 환경변수에서 아예 제거한다.
if not os.environ.get("OPENAI_BASE_URL"):
    os.environ.pop("OPENAI_BASE_URL", None)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None   # None → OpenAI 공식 엔드포인트
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
# openai 리랭크 백엔드가 쓰는 모델(기본=답변 모델과 동일)
OPENAI_RERANK_MODEL = os.getenv("OPENAI_RERANK_MODEL") or OPENAI_MODEL

LLM_MAX_NEW_TOKENS = 1024
LLM_TEMPERATURE = 0.2

# ── 로깅 레벨 (디버깅: LOG_LEVEL=DEBUG) ──────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def summary() -> dict:
    """현재 해석된 설정 요약 (로깅·디버깅용)."""
    return {
        "EMBED_BACKEND": EMBED_BACKEND,
        "RERANK_BACKEND": RERANK_BACKEND,
        "VECTOR_BACKEND": VECTOR_BACKEND,
        "collection": collection_name(),
        "bm25_file": bm25_path().name,
        "npz_file": npz_path().name,
        "npz_exists": npz_path().exists(),
        "chunks_exists": CHUNK_DUMP.exists(),
        "OPENAI_MODEL": OPENAI_MODEL,
        "OPENAI_EMBED_MODEL": OPENAI_EMBED_MODEL,
        "CHROMA_DIR": str(CHROMA_DIR),
        "api_key_set": bool(OPENAI_API_KEY),
    }
