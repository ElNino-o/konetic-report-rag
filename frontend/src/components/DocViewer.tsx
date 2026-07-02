import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Download, FileText } from "lucide-react";
import { getDocumentFull } from "../api";
import type { DocFull, DocMeta, Mode } from "../types";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initialFile: string | null;
  docs: DocMeta[];
  relevant: string[];
  mode: Mode;
  sessionId: string | null;
}

// 근거/문서 원문 뷰어(모달) — 추출 텍스트 전문 · 원본 PDF 임베드(있을 때) · 코네틱 원문 링크.
// 근거 카드나 "전체 문서"에서 열린다.
export default function DocViewer({
  open,
  onOpenChange,
  initialFile,
  docs,
  relevant,
  mode,
  sessionId,
}: Props) {
  const [showAll, setShowAll] = useState(false);
  const [selected, setSelected] = useState<string | null>(initialFile);
  const [full, setFull] = useState<DocFull | null>(null);
  const [loading, setLoading] = useState(false);

  const byFile = useMemo(
    () => Object.fromEntries(docs.map((d) => [d.source_file, d])),
    [docs],
  );
  const rel = relevant.filter((f) => byFile[f]);
  const files = rel.length && !showAll ? rel : docs.map((d) => d.source_file);

  // 모달이 열릴 때 요청한 문서를 선택
  useEffect(() => {
    if (open) setSelected(initialFile ?? files[0] ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFile]);

  useEffect(() => {
    if (!open || !selected) {
      setFull(null);
      return;
    }
    setLoading(true);
    getDocumentFull(selected, mode, sessionId)
      .then(setFull)
      .catch(() => setFull(null))
      .finally(() => setLoading(false));
  }, [open, selected, mode, sessionId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {/* 헤더: 문서 선택 */}
        <div className="border-b border-border px-6 py-4">
          <DialogTitle className="text-base font-bold tracking-tight">
            문서 원문
          </DialogTitle>
          <DialogDescription className="sr-only">
            인용된 문서의 전문과 원본을 확인합니다.
          </DialogDescription>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <select
              value={selected ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="min-w-0 flex-1 rounded-sm border border-border-strong bg-bg px-3 py-2 text-[13.5px] text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/50"
            >
              {files.map((f) => {
                const d = byFile[f];
                return (
                  <option key={f} value={f}>
                    {d?.title ?? f}
                    {d?.country ? ` · ${d.country}/${d.year}` : ""}
                  </option>
                );
              })}
            </select>
            {rel.length > 0 && (
              <label className="flex items-center gap-1.5 text-xs text-muted whitespace-nowrap cursor-pointer">
                <input
                  type="checkbox"
                  checked={showAll}
                  onChange={(e) => setShowAll(e.target.checked)}
                  className="accent-teal"
                />
                전체 문서 {docs.length}건
              </label>
            )}
          </div>
        </div>

        {/* 본문 */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {loading && <p className="text-sm text-muted">불러오는 중…</p>}
          {!loading && full && <FullDocument full={full} />}
        </div>
      </DialogContent>
    </Dialog>
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

  useEffect(() => setShowPdf(false), [meta.source_file]);

  return (
    <div>
      <h3 className="text-[15px] font-bold leading-snug">{meta.title}</h3>
      {info.length > 0 && (
        <p className="mt-1 text-[13px] text-muted">{info.join(" · ")}</p>
      )}
      {meta.tags && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {meta.tags
            .split(/[,\s]+/)
            .filter(Boolean)
            .map((t) => (
              <span
                key={t}
                className="rounded-full bg-canvas px-2.5 py-0.5 text-[11.5px] text-muted"
              >
                {t}
              </span>
            ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        {full.hasPdf && full.pdfUrl && (
          <>
            <Button size="sm" variant="outline" onClick={() => setShowPdf((v) => !v)}>
              <FileText className="size-3.5" />
              {showPdf ? "PDF 닫기" : "원본 PDF 보기"}
            </Button>
            <a
              className="inline-flex items-center gap-1 text-[13px] text-teal hover:underline"
              href={full.pdfUrl}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink className="size-3.5" /> 새 탭
            </a>
            <a
              className="inline-flex items-center gap-1 text-[13px] text-teal hover:underline"
              href={full.pdfUrl}
              download={meta.source_file}
            >
              <Download className="size-3.5" /> 내려받기
            </a>
          </>
        )}
        <a
          className="inline-flex items-center gap-1 text-[13px] text-teal hover:underline"
          href={full.koneticUrl}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink className="size-3.5" /> 코네틱 원문 검색
        </a>
      </div>

      <hr className="my-4 border-border" />

      {showPdf && full.pdfUrl ? (
        <>
          <p className="mb-2 text-xs text-muted">
            브라우저가 PDF를 다운로드한다면 “새 탭”으로 열어주세요.
          </p>
          <iframe
            className="h-[68vh] w-full rounded-md border border-border"
            src={full.pdfUrl}
            title={meta.title}
          />
        </>
      ) : (
        <>
          {!full.hasPdf && (
            <p className="mb-3 rounded-sm border border-border bg-canvas px-3 py-2 text-xs text-muted">
              원본 PDF가 이 서버에 없어 <b className="text-ink">문서 전문(추출
              텍스트)</b>으로 표시합니다.
            </p>
          )}
          <div className="space-y-3 text-[14px] leading-relaxed">
            {full.blocks.map((b, i) => (
              <div key={i}>
                {(i === 0 || b.page !== full.blocks[i - 1].page) && (
                  <div className="mt-4 font-mono text-[11px] font-semibold text-teal">
                    p.{b.page}
                  </div>
                )}
                {b.table_title && (
                  <p className="text-xs font-medium text-muted">📊 {b.table_title}</p>
                )}
                <p className="mt-1 whitespace-pre-wrap">{b.text}</p>
                {b.footnotes && b.footnotes.length > 0 && (
                  <p className="mt-1 text-xs text-faint">각주: {b.footnotes.join(" / ")}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
