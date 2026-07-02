import { FileText } from "lucide-react";
import type { Source } from "../types";
import { cn } from "@/lib/utils";

interface Props {
  sources: Source[];
  hovered: number | null;              // 1-based 인용 번호
  onHover: (n: number | null) => void;
  onOpen: (sourceFile: string) => void;
  totalDocs: number;
  onBrowseAll: () => void;
}

// 근거 레일 — 답변이 인용한 문서를 1급 시각 요소로 표시.
// 인용 칩 hover 시 해당 카드가 강조되고, 카드를 누르면 원문(전문/PDF)이 열린다.
export default function SourceRail({
  sources,
  hovered,
  onHover,
  onOpen,
  totalDocs,
  onBrowseAll,
}: Props) {
  return (
    <aside className="w-85 shrink-0 border-l border-border bg-canvas px-5 py-7 overflow-y-auto">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[12.5px] font-semibold uppercase tracking-wide text-ink">
          근거
        </h2>
        {totalDocs > 0 && (
          <button
            onClick={onBrowseAll}
            className="text-xs text-muted hover:text-ink transition-colors cursor-pointer"
          >
            전체 문서 {totalDocs}건 →
          </button>
        )}
      </div>

      {sources.length === 0 ? (
        <p className="mt-4 text-[13px] leading-relaxed text-muted">
          질문하면 답변의 근거가 된 문서·페이지가 여기에 인용됩니다. 모든 문장을
          출처로 확인할 수 있습니다.
        </p>
      ) : (
        <>
          <p className="mt-1 mb-4 text-xs text-muted">
            이번 답변이 인용한 문서 · 출처와 페이지
          </p>
          <div className="space-y-2.5">
            {sources.map((s, i) => {
              const n = i + 1;
              const on = hovered === n;
              const pct = Math.round(Math.min(1, Math.max(0, s.score ?? 0)) * 100);
              return (
                <button
                  key={s.chunk_id ?? i}
                  onMouseEnter={() => onHover(n)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onOpen(s.source_file)}
                  className={cn(
                    "relative block w-full rounded-md border bg-surface p-3.5 text-left shadow-sm transition-all cursor-pointer",
                    on
                      ? "border-teal ring-2 ring-teal-tint"
                      : "border-border hover:border-border-strong",
                  )}
                >
                  <span className="absolute right-3 top-3 grid h-5 min-w-5 place-items-center rounded-full bg-teal-tint px-1.5 font-mono text-[11px] font-semibold text-teal">
                    {n}
                  </span>
                  <div className="pr-8 text-[13px] font-semibold leading-snug">
                    {s.title ?? s.source_file}
                  </div>
                  <div className="mt-1.5 font-mono text-[11px] text-muted">
                    {s.doc_source} · p.{s.page}
                  </div>
                  <div className="mt-2.5 h-1.25 overflow-hidden rounded-full border border-border bg-canvas">
                    <span
                      className="block h-full rounded-full bg-teal"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="mt-2.5 line-clamp-2 text-xs leading-relaxed text-muted">
                    {s.text}
                  </p>
                  <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-teal">
                    <FileText className="size-3" /> 원문 보기
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </aside>
  );
}
