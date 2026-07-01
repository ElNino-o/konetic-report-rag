import { useEffect, useMemo, useState } from "react";
import { getConfig, getDocuments } from "./api";
import type { ConfigInfo, DocMeta, Mode, QaState, Usage } from "./types";
import Sidebar from "./components/Sidebar";
import QnA from "./components/QnA";
import DocPanel from "./components/DocPanel";
import UploadBar from "./components/UploadBar";

export interface SessionUsage {
  cost: number;
  queries: number;
  tokens: number;
}

export default function App() {
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [err, setErr] = useState("");

  // 사이드바 상태
  const [apiKey, setApiKey] = useState("");
  const [mode, setMode] = useState<Mode>("keiti");
  const [rerank, setRerank] = useState<"off" | "openai">("openai");
  const [usage, setUsage] = useState<SessionUsage>({ cost: 0, queries: 0, tokens: 0 });

  // 코퍼스 문서(KEITI)
  const [keitiDocs, setKeitiDocs] = useState<DocMeta[]>([]);

  // 업로드 세션
  const [uploadSession, setUploadSession] = useState<string | null>(null);
  const [uploadDocs, setUploadDocs] = useState<DocMeta[]>([]);

  // 모드별 질의 상태(전환해도 보존)
  const [qaByMode, setQaByMode] = useState<Record<Mode, QaState | null>>({
    keiti: null,
    upload: null,
  });
  // 모드별 이번 질문에 사용된 문서(우측 패널 강조)
  const [relevant, setRelevant] = useState<Record<Mode, string[]>>({
    keiti: [],
    upload: [],
  });

  useEffect(() => {
    getConfig()
      .then((c) => {
        setConfig(c);
        setRerank(c.rerankDefault);
      })
      .catch((e) => setErr(String(e)));
    getDocuments("keiti")
      .then((d) => setKeitiDocs(d.documents))
      .catch(() => {});
  }, []);

  const effKey = config?.publicKey ? "public" : apiKey.trim();

  function accountUsage(u: Usage) {
    setUsage((s) => ({
      cost: s.cost + u.cost_usd,
      queries: s.queries + 1,
      tokens:
        s.tokens +
        u.embed_tokens +
        u.rerank_tokens +
        u.llm_prompt_tokens +
        u.llm_completion_tokens,
    }));
  }

  const docs = mode === "keiti" ? keitiDocs : uploadDocs;
  const ready =
    mode === "keiti"
      ? keitiDocs.length > 0 && !!effKey
      : !!uploadSession && uploadDocs.length > 0 && !!effKey;

  const sessionId = mode === "upload" ? uploadSession : null;

  const statusCounts = useMemo(() => {
    if (mode === "keiti")
      return { docs: config?.corpus.docs ?? 0, chunks: config?.corpus.chunks ?? 0 };
    return {
      docs: uploadDocs.length,
      chunks: uploadDocs.reduce((a, d) => a + d.chunks, 0),
    };
  }, [mode, config, uploadDocs]);

  if (err)
    return (
      <div className="fatal">
        백엔드에 연결하지 못했습니다. FastAPI(8000)가 실행 중인지 확인하세요.
        <pre>{err}</pre>
      </div>
    );
  if (!config) return <div className="loading">불러오는 중…</div>;

  return (
    <div className="layout">
      <Sidebar
        config={config}
        apiKey={apiKey}
        setApiKey={setApiKey}
        effKey={effKey}
        mode={mode}
        setMode={setMode}
        rerank={rerank}
        setRerank={setRerank}
        statusCounts={statusCounts}
        usage={usage}
      />

      <main className="main">
        <h1>🌏 코네틱 국가별보고서, 규제보고서 Q&A</h1>
        <p className="subtle">
          {mode === "keiti"
            ? `보고서 ${config.corpus.docs}건 · 임베딩/리랭크/LLM 모두 OpenAI`
            : "PDF를 올리면 런타임에 파싱·청킹·임베딩하여(세션) 질의합니다."}
        </p>

        {mode === "upload" && (
          <UploadBar
            apiKey={config.publicKey ? "" : apiKey.trim()}
            disabled={!effKey}
            onUploaded={(sid, ds) => {
              setUploadSession(sid);
              setUploadDocs(ds);
            }}
            current={uploadDocs}
          />
        )}

        <div className="grid">
          <section className="col">
            <QnA
              mode={mode}
              config={config}
              rerank={rerank}
              apiKey={config.publicKey ? null : apiKey.trim() || null}
              sessionId={sessionId}
              ready={ready}
              qaState={qaByMode[mode]}
              setQaState={(updater) =>
                setQaByMode((prev) => ({
                  ...prev,
                  [mode]:
                    typeof updater === "function"
                      ? (updater as (p: QaState | null) => QaState | null)(prev[mode])
                      : updater,
                }))
              }
              accountUsage={accountUsage}
              onRelevant={(files) =>
                setRelevant((prev) => ({ ...prev, [mode]: files }))
              }
            />
          </section>

          <section className="col">
            <h2>📄 문서</h2>
            <DocPanel
              mode={mode}
              sessionId={sessionId}
              docs={docs}
              relevant={relevant[mode]}
            />
          </section>
        </div>
      </main>
    </div>
  );
}
