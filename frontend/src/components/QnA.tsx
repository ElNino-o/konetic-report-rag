import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamAnswer, streamQuery } from "../api";
import type { ConfigInfo, Mode, QaState, Source, Timings, Usage } from "../types";

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
}

const uniqueFiles = (srcs: Source[]) =>
  Array.from(new Set(srcs.map((s) => s.source_file)));

export default function QnA({
  mode,
  config,
  rerank,
  apiKey,
  sessionId,
  ready,
  qaState,
  setQaState,
  accountUsage,
  onRelevant,
}: Props) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [liveStyle, setLiveStyle] = useState<string | null>(null);
  const [liveSources, setLiveSources] = useState<Source[] | null>(null);
  const [error, setError] = useState("");

  const styleLabel = (k: string) =>
    config.styles.find((s) => s.key === k)?.label ?? k;

  async function onStyle(styleKey: string) {
    const q = question.trim();
    if (!q || busy || !ready) return;
    const same = !!qaState && qaState.query === q;

    // 이미 생성한 형태 → 재생성 없이 선택만
    if (same && qaState!.styles[styleKey]) {
      setQaState((p) => (p ? { ...p, selected: styleKey } : p));
      return;
    }

    setBusy(true);
    setError("");
    setLiveStyle(styleKey);
    setLiveText("");
    let acc = "";

    const commit = (
      sources: Source[],
      rt: number,
      rrt: number,
      llmT: number,
      usage: Usage,
    ) => {
      setQaState((prev) => {
        const base =
          prev && prev.query === q
            ? prev
            : { query: q, sources, retrieveT: rt, rerankT: rrt, styles: {}, selected: styleKey };
        return {
          ...base,
          query: q,
          sources,
          retrieveT: rt,
          rerankT: rrt,
          selected: styleKey,
          styles: { ...base.styles, [styleKey]: { answer: acc, llmT, usage } },
        };
      });
      accountUsage(usage);
    };

    try {
      if (same) {
        // 근거 재사용 → LLM만 스트리밍
        const { sources, retrieveT, rerankT } = qaState!;
        await streamAnswer(
          { query: q, sources, style: styleKey, apiKey },
          {
            onToken: (t) => {
              acc += t;
              setLiveText(acc);
            },
            onDone: (d) => commit(sources, retrieveT, rerankT, d.timings.llm, d.usage),
            onError: (m) => setError(m),
          },
        );
      } else {
        // 새 질문 → 검색 + 스트리밍
        let srcs: Source[] = [];
        let rt = 0;
        let rrt = 0;
        await streamQuery(
          { query: q, mode, rerank, style: styleKey, apiKey, sessionId },
          {
            onMeta: (m) => {
              srcs = m.sources;
              rt = m.timings.retrieve;
              rrt = m.timings.rerank;
              setLiveSources(srcs);
              onRelevant(uniqueFiles(srcs));
            },
            onToken: (t) => {
              acc += t;
              setLiveText(acc);
            },
            onDone: (d) => commit(srcs, rt, rrt, d.timings.llm, d.usage),
            onError: (m) => setError(m),
          },
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setLiveStyle(null);
      setLiveText("");
      setLiveSources(null);
    }
  }

  // 표시할 내용 결정: 스트리밍 중이면 live, 아니면 캐시된 선택 형태
  const showLive = busy && liveStyle !== null;
  const selected = qaState?.selected ?? null;
  const cur = selected ? qaState?.styles[selected] : undefined;
  const shownSources = showLive ? liveSources ?? [] : qaState?.sources ?? [];
  const shownStyleKey = showLive ? liveStyle! : selected;

  return (
    <div>
      <h2>✍️ 질문</h2>
      <textarea
        rows={4}
        value={question}
        placeholder={
          mode === "keiti"
            ? "예) 폴란드 이차전지 시장 동향을 알려줘"
            : "업로드한 문서에 대해 질문하세요"
        }
        onChange={(e) => setQuestion(e.target.value)}
      />
      <p className="hint">원하는 답변 형태 버튼을 누르면 검색·답변을 시작합니다.</p>

      <div className="style-buttons">
        {config.styles.map((s) => (
          <button
            key={s.key}
            className={`style-btn${shownStyleKey === s.key ? " active" : ""}`}
            disabled={!ready || busy || !question.trim()}
            title={s.help}
            onClick={() => onStyle(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>

      {!ready && (
        <p className="warn">
          {config.publicKey
            ? mode === "upload"
              ? "먼저 PDF를 업로드·처리하세요."
              : "코퍼스를 불러오는 중입니다."
            : "사이드바에 OpenAI 키를 입력하세요."}
        </p>
      )}
      {error && <p className="error">처리 중 오류: {error}</p>}

      {shownStyleKey && (shownSources.length > 0 || showLive || cur) && (
        <>
          <h2 className="answer-head">
            💬 답변 · {styleLabel(shownStyleKey)}
            {showLive && <span className="spinner"> ⏳ 생성 중…</span>}
          </h2>

          <div className="answer markdown">
            <Markdown remarkPlugins={[remarkGfm]}>
              {showLive ? liveText : cur?.answer ?? ""}
            </Markdown>
          </div>

          {!showLive && cur && (
            <Metrics
              timings={{
                retrieve: qaState!.retrieveT,
                rerank: qaState!.rerankT,
                llm: cur.llmT,
                total: qaState!.retrieveT + qaState!.rerankT + cur.llmT,
              }}
              usage={cur.usage}
            />
          )}

          {shownSources.length > 0 && <Sources sources={shownSources} />}
        </>
      )}
    </div>
  );
}

function Metrics({ timings, usage }: { timings: Timings; usage: Usage }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="metrics-row">
      <div className="metrics">
        <Cell label="총 시간" value={`${timings.total.toFixed(1)}s`} />
        <Cell label="검색" value={`${timings.retrieve.toFixed(1)}s`} />
        <Cell label="리랭크" value={`${timings.rerank.toFixed(1)}s`} />
        <Cell label="LLM" value={`${timings.llm.toFixed(1)}s`} />
      </div>
      <button className="link" onClick={() => setOpen((o) => !o)}>
        💰 이번 질의 ${usage.cost_usd.toFixed(6)} · 토큰{" "}
        {usage.llm_prompt_tokens}+{usage.llm_completion_tokens} {open ? "▲" : "▼"}
      </button>
      {open && (
        <pre className="cost-json">
          {JSON.stringify(
            {
              임베딩토큰: usage.embed_tokens,
              리랭크토큰: usage.rerank_tokens,
              "LLM토큰(p/c)": `${usage.llm_prompt_tokens}/${usage.llm_completion_tokens}`,
              "비용(USD)": {
                embed: +usage.cost_breakdown.embed.toFixed(6),
                rerank: +usage.cost_breakdown.rerank.toFixed(6),
                llm: +usage.cost_breakdown.llm.toFixed(6),
              },
            },
            null,
            2,
          )}
        </pre>
      )}
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  const path = (s: Source) =>
    [s.chapter, s.section, s.subsection].filter(Boolean).join(" > ");
  return (
    <div className="sources">
      <h2>📎 근거 (출처 · 페이지)</h2>
      {sources.map((s, i) => (
        <details key={s.chunk_id ?? i} className="source">
          <summary>
            [{i + 1}] {s.title} · p.{s.page} · {s.chunk_type}{" "}
            {s.score != null && <span className="hint">(score={s.score.toFixed(3)})</span>}
          </summary>
          {path(s) && <p className="hint">📑 {path(s)}</p>}
          <p className="source-text">{s.text}</p>
          <p className="hint">
            출처: {s.doc_source} | 파일: {s.source_file}
          </p>
        </details>
      ))}
    </div>
  );
}
