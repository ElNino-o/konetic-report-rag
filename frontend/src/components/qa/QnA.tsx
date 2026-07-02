import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAnswerStream } from "@/hooks/useAnswerStream";
import type { ConfigInfo, Mode, QaState, Source, Usage } from "@/types";
import { cn } from "@/lib/utils";
import { linkifyCitations, type CiteCtx } from "./Citations";
import ProcessDetail from "./ProcessDetail";

interface Props {
  mode: Mode;
  config: ConfigInfo;
  rerank: string;
  apiKey: string | null;
  sessionId: string | null;
  ready: boolean;
  qaState: QaState | null;
  setQaState: (updater: (p: QaState | null) => QaState | null) => void;
  accountUsage: (u: Usage) => void;
  onRelevant: (files: string[]) => void;
  onSources: (sources: Source[]) => void;
  hoveredCite: number | null;
  onHoverCite: (n: number | null) => void;
  onOpenDoc: (sourceFile: string) => void;
}

// 질문 입력 · 답변 형태 버튼 · 스트리밍 답변(인용 칩) · 처리 상세.
// 스트리밍 로직은 useAnswerStream, 인용/상세는 별도 모듈이 담당한다.
export default function QnA(props: Props) {
  const { config, qaState, hoveredCite, onHoverCite, onOpenDoc } = props;
  const s = useAnswerStream(props);

  const styleLabel = (k: string) =>
    (config.styles.find((x) => x.key === k)?.label ?? k).replace(/^[^가-힣a-zA-Z0-9]+/, "");

  const cite: CiteCtx = {
    sources: s.shownSources,
    hovered: hoveredCite,
    onHover: onHoverCite,
    onOpen: onOpenDoc,
  };

  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
        질문
      </div>
      <textarea
        rows={2}
        value={s.question}
        placeholder={
          props.mode === "keiti"
            ? "예) 폴란드 이차전지 시장 동향을 알려줘"
            : "업로드한 문서에 대해 질문하세요"
        }
        onChange={(e) => s.setQuestion(e.target.value)}
        className="w-full resize-y rounded-md border border-border-strong bg-surface px-4 py-3 text-[15px] shadow-sm placeholder:text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40"
      />

      <div className="mt-4 flex flex-wrap gap-2.5">
        {config.styles.map((st) => {
          const active = s.shownStyleKey === st.key;
          return (
            <button
              key={st.key}
              disabled={!s.canAsk && !active}
              title={st.help}
              onClick={() => s.ask(st.key)}
              className={cn(
                "rounded-sm border px-5 py-2.5 text-[13.5px] font-semibold transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-45",
                active
                  ? "border-primary bg-primary text-primary-fg"
                  : "border-border-strong bg-surface text-ink hover:bg-canvas",
              )}
            >
              {styleLabel(st.key)}
            </button>
          );
        })}
      </div>

      {!props.ready && (
        <p className="mt-4 rounded-sm border border-warn/30 bg-warn-tint px-3 py-2 text-[13.5px] text-warn">
          {config.publicKey
            ? props.mode === "upload"
              ? "먼저 PDF를 업로드·처리하세요."
              : "코퍼스를 불러오는 중입니다."
            : "사이드바에 OpenAI 키를 입력하세요."}
        </p>
      )}
      {s.error && (
        <p className="mt-4 text-[13.5px] font-semibold text-danger">처리 중 오류: {s.error}</p>
      )}

      {s.shownStyleKey && (s.shownSources.length > 0 || s.showLive || s.cur) && (
        <div className="mt-7">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-[13px] font-bold">답변</span>
            {s.showLive ? (
              <span className="font-mono text-[11.5px] text-muted">● 스트리밍</span>
            ) : (
              <span className="text-[11.5px] text-faint">· {styleLabel(s.shownStyleKey)}</span>
            )}
          </div>

          <div className="answer-prose max-w-[62ch] text-[15.5px] leading-[1.85] [&_p]:mb-4 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:mb-1 [&_h1]:mb-2 [&_h1]:mt-4 [&_h1]:text-[17px] [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-[16px] [&_h2]:font-bold [&_h3]:mb-1.5 [&_h3]:mt-3 [&_h3]:font-semibold [&_strong]:font-semibold [&_table]:my-3 [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1">
            <Markdown
              remarkPlugins={[[remarkGfm, { singleTilde: false }]]}
              components={{
                p: ({ children }) => <p>{linkifyCitations(children, cite)}</p>,
                li: ({ children }) => <li>{linkifyCitations(children, cite)}</li>,
              }}
            >
              {s.answerText}
            </Markdown>
            {s.showLive && <span className="caret" />}
          </div>

          {!s.showLive && s.cur && qaState && (
            <ProcessDetail
              retrieveT={qaState.retrieveT}
              rerankT={qaState.rerankT}
              llmT={s.cur.llmT}
              usage={s.cur.usage}
              model={config.model}
              sourceCount={s.shownSources.length}
            />
          )}
        </div>
      )}
    </div>
  );
}
