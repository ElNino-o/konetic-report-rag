import { useEffect, useState } from "react";
import { streamAnswer, streamQuery } from "@/api";
import type { Mode, QaState, Source, Usage } from "@/types";

const uniqueFiles = (srcs: Source[]) =>
  Array.from(new Set(srcs.map((s) => s.source_file)));

interface Params {
  mode: Mode;
  rerank: string;
  apiKey: string | null;
  sessionId: string | null;
  ready: boolean;
  qaState: QaState | null;
  setQaState: (updater: (p: QaState | null) => QaState | null) => void;
  accountUsage: (u: Usage) => void;
  onRelevant: (files: string[]) => void;
  onSources: (sources: Source[]) => void;
}

// 질의응답 스트리밍 상태머신 (검색+답변 / 근거 재사용 형태전환 / 형태 캐시).
// 프레젠테이션(QnA)에서 분리해 로직만 담당한다.
export function useAnswerStream({
  mode,
  rerank,
  apiKey,
  sessionId,
  ready,
  qaState,
  setQaState,
  accountUsage,
  onRelevant,
  onSources,
}: Params) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [liveStyle, setLiveStyle] = useState<string | null>(null);
  const [liveSources, setLiveSources] = useState<Source[] | null>(null);
  const [error, setError] = useState("");

  async function ask(styleKey: string) {
    const q = question.trim();
    if (!q || busy || !ready) return;
    const same = !!qaState && qaState.query === q;

    // 이미 생성한 형태 → 재생성 없이 선택만 전환
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
        // 근거 재사용 → LLM만 스트리밍 (검색 비용 0)
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

  const showLive = busy && liveStyle !== null;
  const selected = qaState?.selected ?? null;
  const cur = selected ? qaState?.styles[selected] : undefined;
  const shownSources = showLive ? liveSources ?? [] : qaState?.sources ?? [];
  const shownStyleKey = showLive ? liveStyle : selected;
  const answerText = showLive ? liveText : cur?.answer ?? "";

  // 레일에 현재 답변의 근거를 반영
  useEffect(() => {
    onSources(shownSources);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownSources.map((s) => s.chunk_id ?? s.source_file).join("|")]);

  return {
    question,
    setQuestion,
    ask,
    busy,
    error,
    showLive,
    shownStyleKey,
    shownSources,
    answerText,
    cur,
    canAsk: ready && !busy && !!question.trim(),
  };
}
