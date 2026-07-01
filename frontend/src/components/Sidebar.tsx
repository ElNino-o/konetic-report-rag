import type { ConfigInfo, Mode } from "../types";
import type { SessionUsage } from "../App";

interface Props {
  config: ConfigInfo;
  apiKey: string;
  setApiKey: (v: string) => void;
  effKey: string;
  mode: Mode;
  setMode: (m: Mode) => void;
  rerank: "off" | "openai";
  setRerank: (r: "off" | "openai") => void;
  statusCounts: { docs: number; chunks: number };
  usage: SessionUsage;
}

export default function Sidebar({
  config,
  apiKey,
  setApiKey,
  effKey,
  mode,
  setMode,
  rerank,
  setRerank,
  statusCounts,
  usage,
}: Props) {
  return (
    <aside className="sidebar">
      {config.publicKey ? (
        <p className="key-note">🔑 공용 OpenAI 키 사용 중</p>
      ) : (
        <div className="block">
          <h3>🔑 OpenAI 키 (BYOK)</h3>
          <input
            type="password"
            placeholder="sk-..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <p className="hint">
            {effKey ? "키 보유 ✅" : "키를 입력해야 질의할 수 있습니다"} · 세션에만 보관
          </p>
        </div>
      )}

      <hr />
      <div className="block">
        <h3>모드</h3>
        <label className="radio">
          <input
            type="radio"
            checked={mode === "keiti"}
            onChange={() => setMode("keiti")}
          />
          KEITI 보고서
        </label>
        <label className="radio">
          <input
            type="radio"
            checked={mode === "upload"}
            onChange={() => setMode("upload")}
          />
          내 문서 업로드
        </label>
      </div>

      <div className="block">
        <h3>리랭킹</h3>
        <label className="radio">
          <input
            type="radio"
            checked={rerank === "off"}
            onChange={() => setRerank("off")}
          />
          off <span className="hint">끄기 (가장 빠름)</span>
        </label>
        <label className="radio">
          <input
            type="radio"
            checked={rerank === "openai"}
            onChange={() => setRerank("openai")}
          />
          openai <span className="hint">{config.rerankModel}</span>
        </label>
      </div>

      <hr />
      <div className="block">
        <h3>📊 상태</h3>
        <div className="metrics">
          <Metric label="문서" value={String(statusCounts.docs)} />
          <Metric label="청크" value={String(statusCounts.chunks)} />
        </div>
        <p className="hint">
          벡터 <code>{config.vectorBackend}</code> · 임베딩 <code>{config.embedModel}</code>
        </p>
        <p className="hint">
          답변 LLM <code>{config.model}</code>
        </p>
      </div>

      <hr />
      <div className="block">
        <h3>💰 세션 누적</h3>
        <div className="metrics">
          <Metric label="추정 비용" value={`$${usage.cost.toFixed(4)}`} />
          <Metric label="질의 수" value={String(usage.queries)} />
        </div>
        <p className="hint">누적 토큰 {usage.tokens.toLocaleString()}</p>
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
