import { useEffect, useMemo, useState } from "react";
import { getDocumentFull } from "../api";
import type { DocFull, DocMeta, Mode } from "../types";

interface Props {
  mode: Mode;
  sessionId: string | null;
  docs: DocMeta[];
  relevant: string[];
}

export default function DocPanel({ mode, sessionId, docs, relevant }: Props) {
  const [showAll, setShowAll] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [full, setFull] = useState<DocFull | null>(null);
  const [loading, setLoading] = useState(false);

  const byFile = useMemo(
    () => Object.fromEntries(docs.map((d) => [d.source_file, d])),
    [docs],
  );
  const rel = relevant.filter((f) => byFile[f]);
  const files = rel.length && !showAll ? rel : docs.map((d) => d.source_file);

  // 표시 목록이 바뀌어 선택이 사라지면 첫 항목으로
  useEffect(() => {
    if (!files.length) {
      setSelected(null);
      return;
    }
    if (!selected || !files.includes(selected)) setSelected(files[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files.join("|")]);

  useEffect(() => {
    if (!selected) {
      setFull(null);
      return;
    }
    setLoading(true);
    getDocumentFull(selected, mode, sessionId)
      .then(setFull)
      .catch(() => setFull(null))
      .finally(() => setLoading(false));
  }, [selected, mode, sessionId]);

  if (!docs.length)
    return <p className="hint">표시할 문서가 없습니다. 질문하면 관련 문서를 보여줍니다.</p>;

  return (
    <div>
      {rel.length > 0 ? (
        <label className="radio">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
          />
          전체 문서 목록 보기 ({docs.length}건)
        </label>
      ) : (
        <p className="hint">전체 문서 {docs.length}건 — 질문하면 관련 문서만 보여줍니다.</p>
      )}
      {rel.length > 0 && !showAll && (
        <p className="hint">🎯 이번 질문에 사용된 문서 {rel.length}건</p>
      )}

      <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
        {files.map((f) => {
          const d = byFile[f];
          return (
            <option key={f} value={f}>
              {d?.title ?? f} · {d?.country}/{d?.year}
            </option>
          );
        })}
      </select>

      <hr />
      {loading && <p className="hint">불러오는 중…</p>}
      {full && <FullDocument full={full} />}
    </div>
  );
}

function FullDocument({ full }: { full: DocFull }) {
  const { meta } = full;
  const [showPdf, setShowPdf] = useState(false);
  const info = [
    meta.country && `국가 ${meta.country}`,
    meta.year && `발행 ${meta.year}`,
    meta.field,
  ].filter(Boolean);

  // 문서가 바뀌면 PDF 미리보기는 다시 닫는다(자동 열림/다운로드 방지).
  useEffect(() => setShowPdf(false), [meta.source_file]);

  return (
    <div className="full-doc">
      <strong>{meta.title}</strong>
      {info.length > 0 && <p className="hint">{info.join(" · ")}</p>}
      {meta.tags && <p className="hint">🏷️ {meta.tags}</p>}
      <p>
        <a href={full.koneticUrl} target="_blank" rel="noreferrer">
          🔗 코네틱(konetic.or.kr)에서 원문 보기
        </a>
      </p>

      {full.hasPdf && full.pdfUrl && (
        <div className="pdf-actions">
          <button className="style-btn" onClick={() => setShowPdf((v) => !v)}>
            {showPdf ? "📄 PDF 미리보기 닫기" : "📄 원본 PDF 미리보기"}
          </button>
          <a className="link" href={full.pdfUrl} target="_blank" rel="noreferrer">
            ↗ 새 탭에서 열기
          </a>
          <a className="link" href={full.pdfUrl} download={meta.source_file}>
            ⬇️ 내려받기
          </a>
        </div>
      )}
      <hr />

      {showPdf && full.pdfUrl ? (
        <>
          <p className="hint">
            ℹ️ 브라우저가 PDF를 화면에 표시하지 않고 다운로드한다면, 브라우저 설정의
            “PDF 파일을 다운로드” 옵션 때문입니다. “새 탭에서 열기”를 이용하세요.
          </p>
          <iframe className="pdf" src={full.pdfUrl} title={meta.title} />
        </>
      ) : (
        <>
          {!full.hasPdf && (
            <p className="hint">
              ℹ️ 원본 PDF가 없어 <b>문서 전문(추출 텍스트)</b>으로 표시합니다.
            </p>
          )}
          <div className="doc-text">
            {full.blocks.map((b, i) => (
              <div key={i}>
                {(i === 0 || b.page !== full.blocks[i - 1].page) && (
                  <h4 className="page-mark">📄 p.{b.page}</h4>
                )}
                {b.table_title && <p className="hint">📊 {b.table_title}</p>}
                <p>{b.text}</p>
                {b.footnotes && b.footnotes.length > 0 && (
                  <p className="hint">각주: {b.footnotes.join(" / ")}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
