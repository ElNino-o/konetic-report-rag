import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Usage } from "@/types";
import { cn } from "@/lib/utils";

interface Props {
  retrieveT: number;
  rerankT: number;
  llmT: number;
  usage: Usage;
  model: string;
  sourceCount: number;
}

// 처리 상세 — 비용·토큰·모델은 개발자용이므로 기본 접힘(옵트인).
// docs/DESIGN.md Information Altitude 원칙.
export default function ProcessDetail({
  retrieveT,
  rerankT,
  llmT,
  usage,
  model,
  sourceCount,
}: Props) {
  const [open, setOpen] = useState(false);
  const total = retrieveT + rerankT + llmT;
  return (
    <div className="mt-6 max-w-[62ch]">
      <div className="flex items-center gap-2.5 text-[13px] text-muted">
        <span>
          <b className="font-mono font-semibold text-ink">{total.toFixed(1)}초</b> 만에 답변
        </span>
        <span className="text-faint">·</span>
        <span>근거 {sourceCount}건</span>
        <span className="text-faint">·</span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center gap-1 text-muted transition-colors hover:text-ink cursor-pointer"
        >
          처리 상세{" "}
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
        </button>
      </div>
      {open && (
        <div className="mt-3 rounded-sm border border-border bg-canvas px-4 py-3.5">
          <div className="grid grid-cols-4 gap-3.5">
            <Stat k="검색" v={`${retrieveT.toFixed(1)}s`} />
            <Stat k="리랭크" v={`${rerankT.toFixed(1)}s`} />
            <Stat k="생성" v={`${llmT.toFixed(1)}s`} />
            <Stat k="토큰" v={`${usage.llm_prompt_tokens}+${usage.llm_completion_tokens}`} />
          </div>
          <div className="mt-3 border-t border-border pt-2.5 text-[11.5px] text-muted">
            모델 <span className="font-mono">{model}</span> · 추정 비용{" "}
            <span className="font-mono">${usage.cost_usd.toFixed(6)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10.5px] text-faint">{k}</div>
      <div className="mt-0.5 font-mono text-[13.5px] font-semibold text-ink">{v}</div>
    </div>
  );
}
