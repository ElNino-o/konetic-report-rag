import { useState } from "react";
import { Upload } from "lucide-react";
import { uploadFiles } from "../api";
import type { DocMeta } from "../types";
import { Button } from "./ui/button";

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
      setMsg(`완료: ${r.documents.length}개 문서 처리`);
    } catch (e) {
      setMsg(`업로드 처리 오류: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-md border border-border bg-canvas px-4 py-3.5">
      <input
        type="file"
        accept="application/pdf"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        className="text-[13px] text-muted file:mr-3 file:cursor-pointer file:rounded-sm file:border file:border-border-strong file:bg-surface file:px-3 file:py-1.5 file:text-[13px] file:font-medium file:text-ink hover:file:bg-bg"
      />
      <Button size="sm" disabled={disabled || !files.length || busy} onClick={process}>
        <Upload className="size-3.5" />
        {busy ? "처리 중…" : "업로드 처리"}
      </Button>
      {current.length > 0 && (
        <span className="text-xs text-muted">현재 세션 문서 {current.length}개</span>
      )}
      {msg && <span className="text-xs text-muted">{msg}</span>}
    </div>
  );
}
