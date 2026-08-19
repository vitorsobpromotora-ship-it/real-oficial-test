import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { post } from "../api/client";
import type { Source } from "../api/types";

interface Props {
  projectId: string;
  onClose(): void;
}

export default function ImportDialog({ projectId, onClose }: Props) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [filePath, setFilePath] = useState("");
  const [error, setError] = useState("");

  const importar = useMutation({
    mutationFn: (body: { origin: string; url?: string; file_path?: string }) =>
      post<{ source: Source; job_id: string }>(`/api/v1/projects/${projectId}/sources`, {
        ...body,
        auto_process: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources", projectId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  async function pickFile() {
    const p = await window.realOficial?.pickVideoFile();
    if (p) setFilePath(p);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <h2>Importar vídeo</h2>
        <div className="row">
          <button className={tab === "url" ? "primary" : ""} onClick={() => setTab("url")}>
            Por URL
          </button>
          <button className={tab === "file" ? "primary" : ""} onClick={() => setTab("file")}>
            Arquivo local
          </button>
        </div>
        {tab === "url" ? (
          <>
            <label>URL do vídeo (YouTube, Google Drive ou .mp4 direto)</label>
            <input
              placeholder="https://www.youtube.com/watch?v=…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </>
        ) : (
          <>
            <label>Arquivo de vídeo</label>
            <div className="row">
              <input
                placeholder="C:\\Videos\\podcast.mp4"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
              />
              {window.realOficial ? <button onClick={pickFile}>Escolher…</button> : null}
            </div>
          </>
        )}
        {error ? <div className="err" style={{ marginTop: 10 }}>{error}</div> : null}
        <div className="row" style={{ marginTop: 18 }}>
          <button className="right" onClick={onClose}>Cancelar</button>
          <button
            className="primary"
            disabled={importar.isPending || (tab === "url" ? !url.trim() : !filePath.trim())}
            onClick={() =>
              importar.mutate(tab === "url"
                ? { origin: "url", url: url.trim() }
                : { origin: "file", file_path: filePath.trim() })
            }
          >
            {importar.isPending ? "Enviando…" : "Importar e processar"}
          </button>
        </div>
      </div>
    </div>
  );
}
