import { isValidElement, cloneElement } from "react";
import type { ReactNode, ReactElement } from "react";
import type { Source } from "@/types";
import { cn } from "@/lib/utils";

// 인용 컨텍스트 — 답변 텍스트의 [n] 을 근거와 연결한다.
export interface CiteCtx {
  sources: Source[];
  hovered: number | null; // 1-based 인용 번호
  onHover: (n: number | null) => void;
  onOpen: (sourceFile: string) => void;
}

// 인용 칩: 클릭 시 원문, hover 시 우측 근거 카드 강조.
function CitePill({ n, ctx }: { n: number; ctx: CiteCtx }) {
  const src = ctx.sources[n - 1];
  if (!src) return <>[{n}]</>;
  return (
    <button
      onMouseEnter={() => ctx.onHover(n)}
      onMouseLeave={() => ctx.onHover(null)}
      onClick={() => ctx.onOpen(src.source_file)}
      className={cn(
        "mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-full px-1.5 align-baseline font-mono text-[11px] font-semibold text-teal transition-colors cursor-pointer",
        ctx.hovered === n
          ? "bg-teal text-white"
          : "bg-teal-tint hover:bg-teal hover:text-white",
      )}
      title={`근거 ${n}: ${src.title ?? src.source_file} p.${src.page}`}
    >
      {n}
    </button>
  );
}

// 문자열에서 [n](인용)과 **굵게**를 함께 처리한다.
// CommonMark 는 한국어 조사 앞(예: `…87.2%**로`)의 닫는 `**` 를 닫지 못해
// `**` 를 그대로 남기므로, 남은 리터럴 `**굵게**` 를 직접 <strong> 으로 렌더한다.
function renderInline(str: string, ctx: CiteCtx, keyBase: string): ReactNode {
  const parts = str.split(/(\*\*[^*\n]+?\*\*|\[\d+\])/g);
  return parts.map((p, j) => {
    const key = `${keyBase}-${j}`;
    const b = /^\*\*([^*\n]+?)\*\*$/.exec(p);
    if (b) return <strong key={key}>{renderInline(b[1], ctx, key)}</strong>;
    const c = /^\[(\d+)\]$/.exec(p);
    if (c) return <CitePill key={key} n={Number(c[1])} ctx={ctx} />;
    // 짝 없는 `**`(스트리밍 중·답변 절단으로 닫히지 못한 굵게)는 리터럴 노출을 막는다.
    return p.includes("**") ? p.replace(/\*\*/g, "") : p;
  });
}

// 마크다운 자식 노드에서 인용 칩·굵게를 처리(재귀).
export function linkifyCitations(
  children: ReactNode,
  ctx: CiteCtx,
  depth = 0,
): ReactNode {
  if (depth > 4) return children;
  const arr = Array.isArray(children) ? children : [children];
  return arr.map((child, i) => {
    if (typeof child === "string") {
      return renderInline(child, ctx, `${i}`);
    }
    if (isValidElement(child)) {
      const el = child as ReactElement<{ children?: ReactNode }>;
      if (el.props?.children != null) {
        return cloneElement(el, {
          ...el.props,
          children: linkifyCitations(el.props.children, ctx, depth + 1),
        });
      }
    }
    return child;
  });
}
