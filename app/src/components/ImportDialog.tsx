import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, post } from "../api/client";
import type { Agent, Settings, Source } from "../api/types";

interface Props {
  projectId: string;
  onClose(): void;
}

const AGENTES: { id: Agent; nome: string; desc: string }[] = [
  { id: "claude", nome: "Claude", desc: "Análise editorial completa (Anthropic)" },
  { id: "gpt", nome: "GPT", desc: "Análise editorial completa (OpenAI)" },
  { id: "local", nome: "Local", desc: "Sem IA — picos de áudio e heurística" },
];

export default function ImportDialog({ projectId, onClose }: Props) {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/api/v1/settings") });
  const [tab, setTab] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [filePath, setFilePath] = useState("");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [error, setError] = useState("");

  const disponivel: Record<Agent, boolean> = {
    claude: !!settings.data?.has_anthropic_api_key,
    gpt: !!settings.data?.has_openai_api_key,
    local: true,
  };

  // Pré-seleciona o agente padrão das Configurações (rebaixando para um disponível).
  useEffect(() => {
    if (agent || !settings.data) return;
    const padrao = settings.data.default_agent;
    setAgent(disponivel[padrao] ? padrao : "local");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.data]);

  const importar = useMutation({
    mutationFn: (body: { origin: string; url?: string; file_path?: string }) =>
      post<{ source: Source; job_id: string }>(`/api/v1/projects/${projectId}/sources`, {
        ...body,
        auto_process: true,
        agent,
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
      <div className="modal" style={{ width: 600 }} onClick={(e) => e.stopPropagation()}>
        <h2>Importar vídeo</h2>
        <div className="seg">
          <button className={tab === "url" ? "on" : ""} onClick={() => setTab("url")}>
            Por URL
          </button>
          <button className={tab === "file" ? "on" : ""} onClick={() => setTab("file")}>
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

        <label>Quem analisa e escolhe os cortes deste vídeo?</label>
        <div className="agent-picker">
          {AGENTES.map((a) => {
            const off = !disponivel[a.id];
            return (
              <button
                key={a.id}
                className={`agent-opt${agent === a.id ? " on" : ""}`}
                disabled={off}
                title={off ? "Configure a chave de API em Configurações para habilitar" : ""}
                onClick={() => setAgent(a.id)}
              >
                <b>{a.nome}</b>
                <span>{off ? "sem chave — configure em Configurações" : a.desc}</span>
              </button>
            );
          })}
        </div>

        {error ? <div className="err" style={{ marginTop: 10 }}>{error}</div> : null}
        <div className="row" style={{ marginTop: 18 }}>
          <button className="right" onClick={onClose}>Cancelar</button>
          <button
            className="primary"
            disabled={importar.isPending || !agent
              || (tab === "url" ? !url.trim() : !filePath.trim())}
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
