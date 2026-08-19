import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api/client";
import type { Job, Project } from "../api/types";
import JobProgress from "../components/JobProgress";

export default function Dashboard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [novoNome, setNovoNome] = useState("");

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
    </div>
  );
}
