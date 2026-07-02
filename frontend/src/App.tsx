import { useEffect, useState } from "react";
import { getConfig, getDocuments } from "./api";
import type { ConfigInfo, DocMeta, Mode, QaState, Source, Usage } from "./types";
import Sidebar from "./components/Sidebar";
import QnA from "./components/qa/QnA";
import SourceRail from "./components/SourceRail";
import DocViewer from "./components/DocViewer";
import UploadBar from "./components/UploadBar";

export interface SessionUsage {
  cost: number;
  queries: number;
  tokens: number;
}

export default function App() {
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [err, setErr] = useState("");

  const [apiKey, setApiKey] = useState("");
  const [mode, setMode] = useState<Mode>("keiti");
  const [rerank, setRerank] = useState<"off" | "openai">("openai");
  const [, setUsage] = useState<SessionUsage>({ cost: 0, queries: 0, tokens: 0 });
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const [keitiDocs, setKeitiDocs] = useState<DocMeta[]>([]);
  const [uploadSession, setUploadSession] = useState<string | null>(null);
  const [uploadDocs, setUploadDocs] = useState<DocMeta[]>([]);

  const [qaByMode, setQaByMode] = useState<Record<Mode, QaState | null>>({
    keiti: null,
    upload: null,
  });
  const [relevant, setRelevant] = useState<Record<Mode, string[]>>({
    keiti: [],
    upload: [],
  });

  // 근거 레일 + 문서 뷰어 상태
  const [railSources, setRailSources] = useState<Source[]>([]);
  const [hoveredCite, setHoveredCite] = useState<number | null>(null);
  const [docOpen, setDocOpen] = useState(false);
  const [docFile, setDocFile] = useState<string | null>(null);

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

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

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

  function openDoc(sourceFile: string) {
    setDocFile(sourceFile);
    setDocOpen(true);
  }

  if (err)
    return (
      <div className="p-10">
        <p className="text-danger font-semibold">
          백엔드에 연결하지 못했습니다. FastAPI(8000)가 실행 중인지 확인하세요.
        </p>
        <pre className="mt-2 whitespace-pre-wrap text-sm text-muted">{err}</pre>
      </div>
    );
  if (!config) return <div className="p-10 text-muted">불러오는 중…</div>;

  return (
    <div className="flex min-h-screen">
      <Sidebar
        config={config}
        apiKey={apiKey}
        setApiKey={setApiKey}
        effKey={effKey}
        mode={mode}
        setMode={setMode}
        rerank={rerank}
        setRerank={setRerank}
        theme={theme}
        toggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />

      <main className="min-w-0 flex-1 px-8 py-8 lg:px-12">
        <h1 className="text-2xl font-extrabold tracking-tight">환경 보고서 질의응답</h1>
        <p className="mt-1.5 mb-7 text-sm text-muted">
          {mode === "keiti"
            ? "질문하면 근거를 찾아 출처·페이지를 인용한 답변을 만듭니다. 모든 문장을 확인할 수 있습니다."
            : "PDF를 올리면 런타임에 파싱·임베딩하여(세션) 질의합니다."}
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
          onRelevant={(files) => setRelevant((prev) => ({ ...prev, [mode]: files }))}
          onSources={setRailSources}
          hoveredCite={hoveredCite}
          onHoverCite={setHoveredCite}
          onOpenDoc={openDoc}
        />
      </main>

      <SourceRail
        sources={railSources}
        hovered={hoveredCite}
        onHover={setHoveredCite}
        onOpen={openDoc}
        totalDocs={docs.length}
        onBrowseAll={() => {
          setDocFile(relevant[mode][0] ?? docs[0]?.source_file ?? null);
          setDocOpen(true);
        }}
      />

      <DocViewer
        open={docOpen}
        onOpenChange={setDocOpen}
        initialFile={docFile}
        docs={docs}
        relevant={relevant[mode]}
        mode={mode}
        sessionId={sessionId}
      />
    </div>
  );
}
