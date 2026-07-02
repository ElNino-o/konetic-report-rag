"""
환경 자가진단(preflight) — 로컬 상태를 실측해 "무엇이 준비됐고 무엇을 조치할지" 한국어로 안내.

동료의 로컬은 경로·데이터·키가 제각각이므로 어떤 것도 가정하지 않는다(하드코딩 경로 사고 재발 방지).
  uv run python -m rag.preflight
런타임(앱 실행) 준비가 되면 exit 0, 아니면 1. dev.sh/dev.bat 가 서버 기동 전 호출(경고만·차단 안 함).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from rag import config

OK, WARN, BAD = "✅", "⚠️", "❌"


def _line(mark: str, msg: str) -> None:
    print(f" {mark} {msg}")


def _count_lines(path: Path) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main() -> int:
    print("\n코네틱 RAG 환경 점검")
    print("─" * 34)
    runtime_ok = True

    # ── 런타임(앱 실행 필수) ─────────────────────────────
    print("[런타임 — 앱 실행에 필수]")
    artifacts = {
        "chunks.jsonl": config.CHUNK_DUMP,
        "reports_openai.npz": config.npz_path(),
        "bm25_openai.pkl": config.bm25_path(),
    }
    missing = [name for name, p in artifacts.items() if not Path(p).exists()]
    if missing:
        runtime_ok = False
        _line(BAD, f"storage/ 아티팩트 누락: {', '.join(missing)}")
        _line(" ", "→ 커밋된 storage/ 를 받았는지 확인하거나 재인덱싱하세요.")
    else:
        _line(OK, f"storage/ 아티팩트 3종 존재  ({_count_lines(config.CHUNK_DUMP)}청크)")

    if config.OPENAI_API_KEY:
        _line(OK, "OpenAI 키: 공용 키 감지")
    else:
        _line(WARN, "OpenAI 키 미설정 → 앱에서 각자 입력(BYOK) 필요")

    has_chromadb = importlib.util.find_spec("chromadb") is not None
    if config.VECTOR_BACKEND == "memory" and not has_chromadb:
        _line(OK, "벡터 백엔드: memory (chromadb 미설치 → 자동 폴백)")
    else:
        _line(OK, f"벡터 백엔드: {config.VECTOR_BACKEND}")

    # ── 재인덱싱(선택 — 원본 PDF 필요) ───────────────────
    print("\n[재인덱싱 — 선택(원본 PDF 필요)]")
    pdfs = [p for d in config.pdf_dirs() if d.exists() for p in d.glob("*.pdf")]
    if config.DATA_DIR.exists() and pdfs:
        _line(OK, f"원본 데이터: {config.DATA_DIR}  (PDF {len(pdfs)}건)")
        has_xlsx = config.METADATA_XLSX.exists()
        _line(OK if has_xlsx else WARN,
              f"메타 엑셀 {config.METADATA_XLSX.name}: {'존재' if has_xlsx else '없음'}")
    else:
        _line(WARN, f"원본 데이터 없음 (기본 경로 {config.DATA_DIR})")
        _line(" ", "→ 재인덱싱하려면 .env 에 RAG_DATA_DIR=/원본/경로 지정 후")
        _line(" ", "  uv run python -m rag.indexing.index_pipeline")

    # ── 프론트(React+FastAPI 버전만) ─────────────────────
    print("\n[프론트 — React+FastAPI 버전만]")
    if (config.ROOT / "frontend" / "node_modules").exists():
        _line(OK, "frontend/node_modules 설치됨")
    else:
        _line(WARN, "frontend/node_modules 없음 → 최초 실행 시 자동 설치(dev.sh)")

    # ── 결론 ─────────────────────────────────────────────
    print("─" * 34)
    if runtime_ok:
        print("결론: 앱 실행 준비 완료 ✅  (uv run streamlit run app.py / ./dev.sh)\n")
        return 0
    print("결론: 런타임 준비 미완 ❌  (위 storage/ 항목 조치 필요)\n")
    return 1


if __name__ == "__main__":
    import sys

    # Windows 콘솔(cp949 등)에서 한글·이모지 출력 시 UnicodeEncodeError 방지
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
