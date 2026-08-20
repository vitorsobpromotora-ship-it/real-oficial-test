// Fila de Renderização operacional: miniatura, corte, etapa, ETA e ações.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, post } from "../api/client";
import type { Render } from "../api/types";
import Thumb from "../components/Thumb";

const STATUS: Record<string, string> = {
  queued: "na fila",
  running: "renderizando",
  done: "concluído",
  failed: "falhou",
  canceled: "cancelado",
};

function eta(r: Render): string {
  if (r.status !== "running" || !r.started_at || r.progress <= 0.02) return "—";
  const inicio = Date.parse(r.started_at);
  if (Number.isNaN(inicio)) return "—";
  const decorrido = (Date.now() - inicio) / 1000;
  const resta = Math.max(0, (decorrido / r.progress) * (1 - r.progress));
  if (resta < 60) return `~${Math.ceil(resta)}s`;
  return `~${Math.ceil(resta / 60)}min`;
}

export default function RenderQueue() {
  const qc = useQueryClient();
  const [toast, setToast] = useState("");
  const renders = useQuery({
    queryKey: ["renders"],
    queryFn: () => get<Render[]>("/api/v1/renders?limit=100"),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "queued" || r.status === "running")
        ? 1500 : 8000,
  });
  const cancelar = useMutation({
    mutationFn: (id: string) => post(`/api/v1/renders/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["renders"] }),
  });
  const denovo = useMutation({
    mutationFn: (cutId: string) => post("/api/v1/renders", { cut_id: cutId, kind: "final" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["renders"] });
      setToast("Render reenfileirado.");
      setTimeout(() => setToast(""), 2500);
    },
  });

  const lista = (renders.data ?? []).filter((r) => r.kind === "final");

  return (
    <div>
      <div className="pagehead">
        <h1>Fila de Renderização</h1>
        <span className="sub">
          {lista.filter((r) => r.status === "running").length} em andamento ·{" "}
          {lista.filter((r) => r.status === "queued").length} na fila ·{" "}
          {lista.filter((r) => r.status === "done").length} concluído(s)
        </span>
      </div>
      {lista.length === 0 ? (
        <div className="empty">Nenhum render ainda. Aprove cortes e use “Renderizar selecionados”.</div>
      ) : (
        <table className="list">
          <thead>
            <tr>
              <th>Corte</th>
              <th style={{ width: 200 }}>Progresso</th>
              <th style={{ width: 110 }}>Etapa</th>
              <th style={{ width: 80 }}>ETA</th>
              <th style={{ width: 210 }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((r) => (
              <tr key={r.id}>
                <td>
                  <div className="row" style={{ gap: 10 }}>
                    <Thumb cutId={r.cut_id} className="row-thumb" />
                    <div style={{ minWidth: 0 }}>
                      <div>{r.cut_title || `corte ${r.cut_id.slice(0, 8)}`}</div>
                      <div className="sub">
                        {r.output_path ? r.output_path.split(/[\\/]/).pop() : "1080×1920 · MP4"}
                      </div>
                      {r.error ? <div className="err">{r.error.slice(0, 140)}</div> : null}
                    </div>
                  </div>
                </td>
                <td>
                  <div className="bar"><i style={{ width: `${Math.round(r.progress * 100)}%` }} /></div>
                  <div className="sub" style={{ marginTop: 3 }}>{Math.round(r.progress * 100)}%</div>
                </td>
                <td>
                  <span className={`chip ${r.status === "done" ? "approved"
                    : r.status === "failed" ? "rejected" : ""}`}>
                    {STATUS[r.status] ?? r.status}
                  </span>
                </td>
                <td className="sub">{eta(r)}</td>
                <td>
                  <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                    {r.status === "done" && r.output_path && window.realOficial ? (
                      <button onClick={() => window.realOficial!.showInFolder(r.output_path!)}>
                        Abrir pasta
                      </button>
                    ) : null}
                    {r.status === "failed" ? (
                      <button onClick={() => denovo.mutate(r.cut_id)}
                              disabled={denovo.isPending}>
                        Tentar de novo
                      </button>
                    ) : null}
                    {r.status === "queued" || r.status === "running" ? (
                      <button className="danger" onClick={() => cancelar.mutate(r.id)}>
                        Cancelar
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  );
}
