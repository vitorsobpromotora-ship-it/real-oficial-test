import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "../api/client";
import type { Render } from "../api/types";

const STATUS: Record<string, string> = {
  queued: "na fila",
  running: "renderizando",
  done: "concluído",
  failed: "falhou",
  canceled: "cancelado",
};

export default function RenderQueue() {
  const qc = useQueryClient();
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

  const lista = (renders.data ?? []).filter((r) => r.kind === "final");

  return (
    <div>
      <div className="pagehead">
        <h1>Fila de Renderização</h1>
        <span className="sub">
          {lista.filter((r) => r.status === "running").length} em andamento ·{" "}
          {lista.filter((r) => r.status === "queued").length} na fila
        </span>
      </div>
      {lista.length === 0 ? (
        <div className="empty">Nenhum render ainda. Aprove cortes e use “Renderizar selecionados”.</div>
      ) : (
        <table className="list">
          <thead>
            <tr><th>Arquivo</th><th style={{ width: 220 }}>Progresso</th><th>Status</th><th /></tr>
          </thead>
          <tbody>
            {lista.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.output_path ? r.output_path.split(/[\\/]/).pop() : `corte ${r.cut_id.slice(0, 8)}`}
                  {r.error ? <div className="err">{r.error.slice(0, 160)}</div> : null}
                </td>
                <td>
                  <div className="bar"><i style={{ width: `${Math.round(r.progress * 100)}%` }} /></div>
                </td>
                <td>{STATUS[r.status] ?? r.status}</td>
                <td className="row" style={{ justifyContent: "flex-end" }}>
                  {r.status === "done" && r.output_path && window.realOficial ? (
                    <button onClick={() => window.realOficial!.showInFolder(r.output_path!)}>
                      Abrir pasta
                    </button>
                  ) : null}
                  {r.status === "queued" || r.status === "running" ? (
                    <button className="danger" onClick={() => cancelar.mutate(r.id)}>Cancelar</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
