// REST + SSE 클라이언트. SSE 는 POST 본문이 필요해 fetch + ReadableStream 으로 직접 파싱.
import type {
  ConfigInfo,
  DocFull,
  DocMeta,
  Mode,
  Source,
  Timings,
  Usage,
} from "./types";

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const getConfig = () => jget<ConfigInfo>("/api/config");

export const getDocuments = (mode: Mode, sessionId?: string | null) =>
  jget<{ documents: DocMeta[]; count: number }>(
    `/api/documents?mode=${mode}${sessionId ? `&sessionId=${sessionId}` : ""}`,
  );

export const getDocumentFull = (
  sourceFile: string,
  mode: Mode,
  sessionId?: string | null,
) =>
  jget<DocFull>(
    `/api/documents/full?source_file=${encodeURIComponent(sourceFile)}&mode=${mode}` +
      (sessionId ? `&sessionId=${sessionId}` : ""),
  );

export async function uploadFiles(
  files: File[],
  apiKey: string,
): Promise<{ sessionId: string; chunks: number; documents: DocMeta[] }> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("apiKey", apiKey);
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

// ── SSE 스트림 핸들러 ──────────────────────────────────
export interface StreamHandlers {
  onMeta?: (d: { sources: Source[]; timings: { retrieve: number; rerank: number } }) => void;
  onToken?: (text: string) => void;
  onDone?: (d: { usage: Usage; llm_time: number; timings: Timings }) => void;
  onError?: (message: string) => void;
}

async function streamSSE(
  url: string,
  body: unknown,
  h: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    h.onError?.(`${r.status} ${await r.text()}`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE 프레임은 빈 줄(\n\n)로 구분
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join("\n"));
      if (event === "meta") h.onMeta?.(data);
      else if (event === "token") h.onToken?.(data.text);
      else if (event === "done") h.onDone?.(data);
      else if (event === "error") h.onError?.(data.message);
    }
  }
}

export interface QueryBody {
  query: string;
  mode: Mode;
  rerank: string;
  style: string;
  apiKey?: string | null;
  sessionId?: string | null;
}

export const streamQuery = (body: QueryBody, h: StreamHandlers, signal?: AbortSignal) =>
  streamSSE("/api/query", body, h, signal);

export interface AnswerBody {
  query: string;
  sources: Source[];
  style: string;
  apiKey?: string | null;
}

export const streamAnswer = (body: AnswerBody, h: StreamHandlers, signal?: AbortSignal) =>
  streamSSE("/api/answer", body, h, signal);
