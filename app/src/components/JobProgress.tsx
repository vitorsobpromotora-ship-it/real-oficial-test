import type { Job } from "../api/types";

const STATUS_PTBR: Record<string, string> = {
  queued: "Na fila",
  running: "Processando",
  done: "Concluído",
  failed: "Falhou",
  canceled: "Cancelado",
};

const STAGE_PTBR: Record<string, string> = {
  ingest: "Importando",
  transcribe: "Transcrevendo",
  analyze: "Analisando com IA",
  reframe: "Enquadrando",
  render: "Renderizando",
  finalizado: "Finalizado",
};

export default function JobProgress({ job }: { job: Job }) {
  const pct = Math.round(job.progress * 100);
  return (
    <div className="card" style={{ padding: "10px 14px" }}>
      <div className="row">
        <span style={{ fontSize: 12.5 }}>
          {STAGE_PTBR[job.stage] ?? job.stage ?? job.type} · {STATUS_PTBR[job.status] ?? job.status}
        </span>
        <span className="right sub">{pct}%</span>
      </div>
      <div className="bar" style={{ marginTop: 6 }}>
        <i style={{ width: `${pct}%` }} />
      </div>
      {job.message ? <div className="sub" style={{ marginTop: 5 }}>{job.message}</div> : null}
      {job.error ? <div className="err" style={{ marginTop: 5 }}>{job.error}</div> : null}
    </div>
  );
}
