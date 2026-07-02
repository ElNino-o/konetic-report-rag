import { Moon, Sun, KeyRound } from "lucide-react";
import type { ConfigInfo, Mode } from "../types";
import { cn } from "@/lib/utils";

interface Props {
  config: ConfigInfo;
  apiKey: string;
  setApiKey: (v: string) => void;
  effKey: string;
  mode: Mode;
  setMode: (m: Mode) => void;
  rerank: "off" | "openai";
  setRerank: (r: "off" | "openai") => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
}

// 사이드바 — 사용자 컨트롤만. 시스템 내부(청크·비용·모델명)는 노출하지 않는다(docs/DESIGN.md Information Altitude).
export default function Sidebar({
  config,
  apiKey,
  setApiKey,
  effKey,
  mode,
  setMode,
  rerank,
  setRerank,
  theme,
  toggleTheme,
}: Props) {
  return (
    <aside className="flex w-62 shrink-0 flex-col border-r border-border bg-surface px-5 py-6">
      {/* 브랜드 */}
      <div className="mb-6 flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-[9px] bg-primary text-[15px] font-bold text-primary-fg">
          코
        </div>
        <div>
          <div className="text-[15px] font-bold tracking-tight">코네틱 Q&A</div>
          <div className="text-xs text-muted">환경 보고서 근거 검색</div>
        </div>
      </div>

      {/* BYOK 키 (공용 키 없을 때만) */}
      {config.publicKey ? (
        <p className="mb-1 flex items-center gap-1.5 text-xs text-muted">
          <KeyRound className="size-3.5" /> 공용 OpenAI 키 사용 중
        </p>
      ) : (
        <div className="mb-5">
          <SectionLabel>OpenAI 키 (BYOK)</SectionLabel>
          <input
            type="password"
            placeholder="sk-..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="w-full rounded-sm border border-border-strong bg-bg px-2.5 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/50"
          />
          <p className="mt-1.5 text-[11.5px] text-faint">
            {effKey ? "키 보유 · 세션에만 보관" : "키를 입력해야 질의할 수 있습니다"}
          </p>
        </div>
      )}

      {/* 모드 */}
      <SectionLabel>모드</SectionLabel>
      <div className="flex flex-col gap-1">
        <SegButton on={mode === "keiti"} onClick={() => setMode("keiti")}>
          KEITI 보고서
        </SegButton>
        <SegButton on={mode === "upload"} onClick={() => setMode("upload")}>
          내 문서 업로드
        </SegButton>
      </div>

      {mode === "keiti" && (
        <p className="mt-3 text-[12.5px] leading-relaxed text-muted">
          <b className="font-semibold text-ink">{config.corpus.docs}건</b>의 KEITI
          환경·정책 보고서에서 근거를 찾아 인용합니다.
        </p>
      )}

      {/* 검색 방식 (리랭킹 → 사용자 이득 언어) */}
      <div className="mt-6 border-t border-border pt-4">
        <SectionLabel>검색 방식</SectionLabel>
        <div className="flex gap-1.5">
          <SegPill on={rerank === "openai"} onClick={() => setRerank("openai")}>
            정확도 우선
          </SegPill>
          <SegPill on={rerank === "off"} onClick={() => setRerank("off")}>
            속도 우선
          </SegPill>
        </div>
        <p className="mt-2 text-[11.5px] leading-relaxed text-faint">
          {rerank === "openai"
            ? "찾은 근거를 한 번 더 정렬합니다. 조금 느리지만 관련도가 높아집니다."
            : "리랭크 없이 가장 빠르게 답합니다."}
        </p>
      </div>

      {/* 하단: 테마 */}
      <div className="mt-auto pt-6">
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2 text-[13px] text-muted hover:text-ink transition-colors cursor-pointer"
        >
          {theme === "dark" ? (
            <Sun className="size-4" />
          ) : (
            <Moon className="size-4" />
          )}
          {theme === "dark" ? "라이트 모드" : "다크 모드"}
        </button>
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">
      {children}
    </div>
  );
}

function SegButton({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-sm px-3 py-2 text-left text-[13.5px] transition-colors cursor-pointer",
        on
          ? "bg-primary-tint font-semibold text-ink"
          : "text-muted hover:bg-canvas hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function SegPill({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex-1 rounded-sm border px-2 py-2 text-[12.5px] font-medium transition-colors cursor-pointer",
        on
          ? "border-primary bg-primary text-primary-fg"
          : "border-border-strong bg-surface text-ink hover:bg-canvas",
      )}
    >
      {children}
    </button>
  );
}
