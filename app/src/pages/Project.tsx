import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { get, post } from "../api/client";
import type { BrandKit, Cut, Job, Project, Source } from "../api/types";
import CutCard from "../components/CutCard";
import CutReviewModal from "../components/CutReviewModal";
import ImportDialog from "../components/ImportDialog";
import JobProgress from "../components/JobProgress";

type Filtro = "todos" | "draft" | "approved" | "rejected";

export default function ProjectPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [mostrarImport, setMostrarImport] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [aberto, setAberto] = useState<Cut | null>(null);
  const [toast, setToast] = useState("");

  const project = useQuery({
    queryKey: ["projects", id],
    queryFn: () => get<Project>(`/api/v1/projects/${id}`),
  });
  const sources = useQuery({
    queryKey: ["sources", id],
    queryFn: () => get<Source[]>(`/api/v1/projects/${id}/sources`),
  });
  const cuts = useQuery({
    queryKey: ["cuts", id],
    queryFn: () => get<Cut[]>(`/api/v1/projects/${id}/cuts`),
  });
  const kits = useQuery({
    queryKey: ["brand-kits"],
    queryFn: () => get<BrandKit[]>("/api/v1/brand-kits"),
  });
  const jobs = useQuery({
    queryKey: ["jobs", "projeto", id],
    queryFn: () => get<Job[]>(`/api/v1/jobs?limit=10`),
    refetchInterval: 4000,
  });

  const bulk = useMutation({
    mutationFn: (body: { cut_ids: string[]; patch: Record<string, unknown> }) =>
      post("/api/v1/cuts/bulk", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cuts", id] });
      setToast("Cortes atualizados.");
      setTimeout(() => setToast(""), 2500);
    },
  });
  const renderLote = useMutation({
    mutationFn: (cutIds: string[]) =>
      post("/api/v1/renders/batch", { cut_ids: cutIds }),
    onSuccess: () => {
      setToast("Renderização em lote iniciada — acompanhe na Fila.");
      setSelecionados(new Set());
      setTimeout(() => setToast(""), 3500);
      qc.invalidateQueries({ queryKey: ["renders"] });
    },
  });

  const listaFiltrada = useMemo(() => {
    const lista = cuts.data ?? [];
    return filtro === "todos" ? lista : lista.filter((c) => c.status === filtro);
  }, [cuts.data, filtro]);

  const jobsAtivos = (jobs.data ?? []).filter(
    (j) => (j.status === "running" || j.status === "queued") && j.project_id === id);

  function toggle(cutId: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(cutId)) next.delete(cutId);
      else next.add(cutId);
      return next;
    });
  }

  const idsSel = [...selecionados];
  const kitPadrao = (kits.data ?? []).find((k) => k.is_default);

  return (
    <div>
      <div className="pagehead">
        <div>
          <h1>{project.data?.name ?? "…"}</h1>
          <div className="sub">
            {sources.data?.length ?? 0} vídeo(s) · {cuts.data?.length ?? 0} corte(s)
          </div>
        </div>
        <button className="primary" onClick={() => setMostrarImport(true)}>+ Importar vídeo</button>
      </div>

      {jobsAtivos.length > 0 ? (
        <div className="grid" style={{ marginBottom: 18 }}>
          {jobsAtivos.map((j) => <JobProgress key={j.id} job={j} />)}
        </div>
      ) : null}

      {(sources.data ?? []).some((s) => s.status === "failed") ? (
        <div className="card" style={{ borderColor: "var(--bad)", marginBottom: 16 }}>
          {(sources.data ?? []).filter((s) => s.status === "failed").map((s) => (
            <div key={s.id} className="err">Falha em “{s.title || s.id}”: {s.error}</div>
          ))}
        </div>
      ) : null}

      <div className="row" style={{ marginBottom: 14 }}>
        {(["todos", "draft", "approved", "rejected"] as Filtro[]).map((f) => (
          <button key={f} className={filtro === f ? "primary" : ""} onClick={() => setFiltro(f)}>
            {f === "todos" ? "Todos" : f === "draft" ? "Rascunhos" : f === "approved" ? "Aprovados" : "Rejeitados"}
          </button>
        ))}
        <span className="right sub">ordenado por score</span>
      </div>

      {cuts.isSuccess && listaFiltrada.length === 0 ? (
        <div className="empty">
          {cuts.data.length === 0
            ? "Nenhum corte ainda. Importe um vídeo para a IA sugerir os melhores momentos."
            : "Nenhum corte neste filtro."}
        </div>
      ) : null}

      <div className="cutgrid">
        {listaFiltrada.map((c) => (
          <CutCard
            key={c.id}
            cut={c}
            selected={selecionados.has(c.id)}
            onToggle={() => toggle(c.id)}
            onOpen={() => setAberto(c)}
          />
        ))}
      </div>

      {idsSel.length > 0 ? (
        <div className="bulkbar">
          <b>{idsSel.length} selecionado(s)</b>
          <button onClick={() => bulk.mutate({ cut_ids: idsSel, patch: { status: "approved" } })}>
            Aprovar
          </button>
          <button onClick={() => bulk.mutate({ cut_ids: idsSel, patch: { status: "rejected" } })}>
            Rejeitar
          </button>
          {kitPadrao ? (
            <button
              onClick={() => bulk.mutate({ cut_ids: idsSel, patch: { brand_kit_id: kitPadrao.id } })}
            >
              Aplicar kit “{kitPadrao.name}”
            </button>
          ) : null}
          <button
            className="primary right"
            disabled={renderLote.isPending}
            onClick={() => renderLote.mutate(idsSel)}
          >
            Renderizar selecionados
          </button>
          <button onClick={() => setSelecionados(new Set())}>Limpar</button>
        </div>
      ) : null}

      {mostrarImport ? (
        <ImportDialog projectId={id} onClose={() => setMostrarImport(false)} />
      ) : null}
      {aberto ? (
        <CutReviewModal cut={aberto} kits={kits.data ?? []} onClose={() => setAberto(null)} />
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  );
}
