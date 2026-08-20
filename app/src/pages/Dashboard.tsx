import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api/client";
import type { Job, Project } from "../api/types";
import JobProgress from "../components/JobProgress";

const STATUS_JOB: Record<string, string> = {
  queued: "na fila", running: "processando", done: "concluído",
  failed: "falhou", canceled: "cancelado",
};
const TIPO_JOB: Record<string, string> = {
  process_source: "Processamento de vídeo", render_cut: "Renderização",
  model_download: "Download de modelo",
};

export default function Dashboard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [novoNome, setNovoNome] = useState("");
  const [onboardOculto, setOnboardOculto] = useState(
    () => localStorage.getItem("ro_onboarding_ok") === "1");

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => get<Project[]>("/api/v1/projects"),
  });
  const jobs = useQuery({
    queryKey: ["jobs", "ativos"],
    queryFn: () => get<Job[]>("/api/v1/jobs?limit=20"),
    refetchInterval: 4000,
  });

  const criar = useMutation({
    mutationFn: (name: string) => post<Project>("/api/v1/projects", { name }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setNovoNome("");
      navigate(`/projeto/${p.id}`);
    },
  });

  const ativos = (jobs.data ?? []).filter((j) => j.status === "running" || j.status === "queued");

  return (
    <div>
      <div className="pagehead">
        <h1>Painel</h1>
        <div className="row">
          <input
            placeholder="Nome do novo projeto (ex.: Podcast #42)"
            value={novoNome}
            onChange={(e) => setNovoNome(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && novoNome.trim() && criar.mutate(novoNome.trim())}
            style={{ width: 300 }}
          />
          <button
            className="primary"
            disabled={!novoNome.trim() || criar.isPending}
            onClick={() => criar.mutate(novoNome.trim())}
          >
            Criar projeto
          </button>
        </div>
      </div>

      {!onboardOculto ? (
        <div className="card onboard">
          <div className="row" style={{ alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <h3>Como funciona (3 passos)</h3>
              <ol className="onboard-steps">
                <li><b>Importe um vídeo longo</b> (arquivo ou URL) dentro de um projeto —
                  escolha quem analisa (Claude, GPT ou local) e o perfil de quantidade.</li>
                <li><b>Revise os cortes sugeridos</b>: score, veredito e análise por corte.
                  Ajuste fino no <b>Editor</b> (timeline, pausas, fades) e o visual no{" "}
                  <b>Estúdio de Marca</b>.</li>
                <li><b>Renderize em lote</b> — os MP4 9:16 com legendas saem prontos na{" "}
                  <b>Fila de Renderização</b>.</li>
              </ol>
              <div className="sub">
                Dica: configure sua chave de IA em Configurações → IA para ter análise
                editorial de verdade (sem chave, vale a análise local por picos de áudio).
              </div>
            </div>
            <button onClick={() => {
              localStorage.setItem("ro_onboarding_ok", "1");
              setOnboardOculto(true);
            }}>Entendi</button>
          </div>
        </div>
      ) : null}

      {ativos.length > 0 ? (
        <>
          <div className="sub" style={{ margin: "6px 0 10px" }}>Processando agora</div>
          <div className="grid" style={{ marginBottom: 22 }}>
            {ativos.map((j) => <JobProgress key={j.id} job={j} />)}
          </div>
        </>
      ) : null}

      {projects.isLoading ? <div className="empty">Carregando…</div> : null}
      {projects.data?.length === 0 ? (
        <div className="empty">
          Nenhum projeto ainda. Crie um projeto e importe um vídeo longo — o Real Oficial
          encontra os melhores momentos, corta em 9:16, legenda e renderiza.
        </div>
      ) : null}
      <div className="grid">
        {projects.data?.map((p) => (
          <div key={p.id} className="card click" onClick={() => navigate(`/projeto/${p.id}`)}>
            <h3>{p.name}</h3>
            <div className="sub">
              {p.sources_count} vídeo{p.sources_count === 1 ? "" : "s"} ·{" "}
              {p.cuts_count} corte{p.cuts_count === 1 ? "" : "s"}
            </div>
            {p.description ? <div className="sub" style={{ marginTop: 6 }}>{p.description}</div> : null}
          </div>
        ))}
      </div>

      {(jobs.data ?? []).length > 0 ? (
        <div style={{ marginTop: 26 }}>
          <div className="sub" style={{ marginBottom: 8 }}>Atividade recente</div>
          <table className="list">
            <tbody>
              {(jobs.data ?? []).slice(0, 8).map((j) => (
                <tr key={j.id} className={j.project_id ? "click" : ""}
                    onClick={() => j.project_id && navigate(`/projeto/${j.project_id}`)}
                    style={j.project_id ? { cursor: "pointer" } : undefined}>
                  <td>{TIPO_JOB[j.type] ?? j.type}</td>
                  <td className="sub">{j.message?.slice(0, 90) || j.stage}</td>
                  <td style={{ width: 110 }}>
                    <span className={`chip ${j.status === "done" ? "approved"
                      : j.status === "failed" ? "rejected" : ""}`}>
                      {STATUS_JOB[j.status] ?? j.status}
                    </span>
                  </td>
                  <td className="sub" style={{ width: 150 }}>
                    {(j.finished_at ?? j.created_at ?? "").slice(0, 16).replace("T", " ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
