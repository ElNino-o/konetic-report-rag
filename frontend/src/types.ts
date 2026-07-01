// 백엔드(/api)와 주고받는 타입 정의

export interface StyleDef {
  key: string;
  label: string;
  help: string;
}

export interface ConfigInfo {
  publicKey: boolean;
  model: string;
  embedModel: string;
  rerankModel: string;
  vectorBackend: string;
  rerankDefault: "off" | "openai";
  styles: StyleDef[];
  corpus: { docs: number; chunks: number };
}

export interface DocMeta {
  source_file: string;
  title: string;
  country: string;
  year: string;
  field: string;
  tags: string;
  doc_source: string;
  chunks: number;
  has_pdf: boolean;
}

export interface Source {
  chunk_id?: string;
  source_file: string;
  title?: string;
  page?: string | number;
  chunk_type?: string;
  score?: number;
  chapter?: string;
  section?: string;
  subsection?: string;
  doc_source?: string;
  text: string;
  table_title?: string;
  footnotes?: string[];
}

export interface Timings {
  retrieve: number;
  rerank: number;
  llm: number;
  total: number;
}

export interface Usage {
  embed_tokens: number;
  rerank_tokens: number;
  llm_prompt_tokens: number;
  llm_completion_tokens: number;
  cost_usd: number;
  cost_breakdown: { embed: number; rerank: number; llm: number };
}

export interface DocBlock {
  page: string | number;
  text: string;
  table_title?: string;
  footnotes?: string[];
}

export interface DocFull {
  meta: DocMeta;
  blocks: DocBlock[];
  hasPdf: boolean;
  pdfUrl: string | null;
  koneticUrl: string;
}

// 한 형태(style)의 생성 결과
export interface StyleResult {
  answer: string;
  llmT: number;
  usage: Usage;
}

// 한 질문의 상태(여러 형태를 캐시)
export interface QaState {
  query: string;
  sources: Source[];
  retrieveT: number;
  rerankT: number;
  styles: Record<string, StyleResult>;
  selected: string;
}

export type Mode = "keiti" | "upload";
