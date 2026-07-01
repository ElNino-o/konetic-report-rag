import { useState } from "react";
import { uploadFiles } from "../api";
import type { DocMeta } from "../types";

interface Props {
  apiKey: string;
  disabled: boolean;
  onUploaded: (sessionId: string, docs: DocMeta[]) => void;
  current: DocMeta[];
}

export default function UploadBar({ apiKey, disabled, onUploaded, current }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function process() {
    if (!files.length || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await uploadFiles(files, apiKey);
      onUploaded(r.sessionId, r.documents);
      setMsg(`완료: ${r.chunks} 청크 임베딩 (${r.documents.length}개 문서)`);
    } catch (e) {
      setMsg(`업로드 처리 오류: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload-bar">
      <input
        type="file"
        accept="application/pdf"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
      />
      <button
        className="style-btn"
        disabled={disabled || !files.length || busy}
        onClick={process}
      >
        {busy ? "처리 중…" : "📥 업로드 처리(파싱·임베딩)"}
      </button>
      {current.length > 0 && (
        <span className="hint">현재 세션 문서 {current.length}개</span>
      )}
      {msg && <span className="hint">{msg}</span>}
    </div>
  );
}
