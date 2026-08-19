import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, mediaUrl } from "../api/client";
import type { Project, Source } from "../api/types";

export default function Reports() {
  const [projectId, setProjectId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [reportUrl, setReportUrl] = useState<string | null>(null);

  const projects = useQuery({ queryKey: ["projects"], queryFn: () => get<Project[]>("/api/v1/projects") });
  const sources = useQuery({
    queryKey: ["sources", projectId],
    queryFn: () => get<Source[]>(`/api/v1/projects/${projectId}/sources`),
    enabled: !!projectId,
  });

  useEffect(() => {
    if (!sourceId) {
      setReportUrl(null);
      return;
    }
    mediaUrl(`/api/v1/reports/sources/${sourceId}/html`).then(setReportUrl);
  }, [sourceId]);

  return (
    <div>
      <div className="pagehead">
        <h1>Relatórios</h1>
        {reportUrl && window.realOficial ? (
          <button onClick={() => window.realOficial!.openExternal(reportUrl)}>
            Abrir no navegador
          </button>
        ) : null}
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        <select value={projectId} style={{ width: 280 }}
                onChange={(e) => { setProjectId(e.target.value); setSourceId(""); }}>
          <option value="">Escolha um projeto…</option>
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={sourceId} style={{ width: 340 }} disabled={!projectId}
                onChange={(e) => setSourceId(e.target.value)}>
          <option value="">Escolha um vídeo…</option>
          {sources.data?.map((s) => (
            <option key={s.id} value={s.id}>{s.title || s.id}</option>
          ))}
        </select>
      </div>
      {reportUrl ? (
        <iframe className="report" src={reportUrl} title="Relatório" />
      ) : (
        <div className="empty">
          Selecione um vídeo processado para ver taxa de aproveitamento, tempo economizado,
          correlação do score com a sua avaliação, custo de IA e tempos por estágio.
        </div>
      )}
    </div>
  );
}
