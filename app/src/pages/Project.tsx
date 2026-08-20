import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { get, post } from "../api/client";
import type { BrandKit, Cut, Job, Project, Settings, Source } from "../api/types";
import CutCard, { fmtDur, fmtRange, scoreClass } from "../components/CutCard";
import CutReviewModal from "../components/CutReviewModal";
import ImportDialog from "../components/ImportDialog";
import JobProgress from "../components/JobProgress";
import Thumb from "../components/Thumb";

type Filtro = "todos" | "draft" | "approved" | "rejected";

export default function ProjectPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [mostrarImport, setMostrarImport] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [modo, setModo] = useState<"cards" | "lista">("cards");
  const [ordem, setOrdem] = useState<"score" | "time">("score");
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
    queryKey: ["cuts", id, ordem],
    queryFn: () => get<Cut[]>(`/api/v1/projects/${id}/cuts?sort=${ordem}`),
  });
  const reservas = useQuery({
    queryKey: ["cuts", id, "reservas"],
    queryFn: () => get<Cut[]>(`/api/v1/projects/${id}/cuts?status=reserve`),
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
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => get<Settings>("/api/v1/settings"),
  });

  const reprocessar = useMutation({
    mutationFn: (agente: "claude" | "gpt") => {
      const fonte = (sources.data ?? []).find((s) => s.status === "ready");
      if (!fonte) throw new Error("Nenhum vídeo pronto para reprocessar");
      return post(`/api/v1/sources/${fonte.id}/process`,
        { agent: agente, options: { force_analyze: true } });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setToast("Reprocessando com IA — acompanhe o progresso acima.");
      setTimeout(() => setToast(""), 3500);
    },
    onError: (e: Error) => {
      setToast(e.message);
      setTimeout(() => setToast(""), 6000);
    },
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
  const maisOportunidades = useMutation({
    mutationFn: () => {
      const fonte = (sources.data ?? []).find((s) => s.status === "ready");
      if (!fonte) throw new Error("Nenhuma fonte pronta");
      return post<{ promovidos: number; reservas_restantes: number }>(
        `/api/v1/sources/${fonte.id}/promote-reserves`, { count: 3 });
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["cuts", id] });
      setToast(`${r.promovidos} oportunidade(s) adicionada(s) — sem reanalisar o vídeo. `
        + `${r.reservas_restantes} ainda em reserva.`);
      setTimeout(() => setToast(""), 4000);
    },
    onError: (e: Error) => {
      setToast(e.message);
      setTimeout(() => setToast(""), 4000);
    },
  });

  const listaFiltrada = useMemo(() => {
    const lista = cuts.data ?? [];
    return filtro === "todos" ? lista : lista.filter((c) => c.status === filtro);
  }, [cuts.data, filtro]);

  const jobsAtivos = (jobs.data ?? []).filter(
    (j) => (j.status === "running" || j.status === "queued") && j.project_id === id);
  // transparência do funil: o último processamento concluído explica as contagens
  const jobFunil = (jobs.data ?? []).find(
    (j) => j.project_id === id && j.status === "done" && j.type === "process_source"
      && (j.result as { funil?: unknown } | null)?.funil);
  const funil = (jobFunil?.result as { funil?: Record<string, number> } | undefined)?.funil;

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

      {(cuts.data ?? []).length > 0 &&
       (cuts.data ?? []).filter((c) => c.origin === "heuristic").length >
         (cuts.data ?? []).length / 2 ? (
        <div className="banner">
          <div>
            ⚠️ Estes cortes foram gerados pela <b>análise local</b> (picos de áudio, sem IA) — o
            score e a análise ficam genéricos de propósito. Configure uma chave (Claude ou GPT) em{" "}
            <a href="#/config">Configurações</a> e reprocesse para ter veredito e análise
            editorial de cada corte.
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button disabled={!settings.data?.has_anthropic_api_key || reprocessar.isPending}
                    title={settings.data?.has_anthropic_api_key ? "" : "Configure a chave Anthropic primeiro"}
                    onClick={() => reprocessar.mutate("claude")}>
              Reprocessar com Claude
            </button>
            <button disabled={!settings.data?.has_openai_api_key || reprocessar.isPending}
                    title={settings.data?.has_openai_api_key ? "" : "Configure a chave OpenAI primeiro"}
                    onClick={() => reprocessar.mutate("gpt")}>
              Reprocessar com GPT
            </button>
          </div>
        </div>
      ) : null}

      {(sources.data ?? []).some((s) => s.status === "failed") ? (
        <div className="card" style={{ borderColor: "var(--bad)", marginBottom: 16 }}>
          {(sources.data ?? []).filter((s) => s.status === "failed").map((s) => (
            <div key={s.id} className="err">Falha em “{s.title || s.id}”: {s.error}</div>
          ))}
        </div>
      ) : null}

      {funil ? (
        <div className="sub" style={{ marginBottom: 10 }}>
          Funil da última análise: <b>{funil.brutos ?? "?"}</b> candidatos →{" "}
          <b>{funil.validos ?? "?"}</b> válidos → <b>{funil.apos_dedup ?? "?"}</b> após
          dedup → <b>{funil.finais ?? "?"}</b> recomendados (meta {funil.alvo ?? "?"}
          {typeof funil.reservas === "number" && funil.reservas > 0
            ? ` · ${funil.reservas} em reserva` : ""})
        </div>
      ) : null}

      <div className="row wrap" style={{ marginBottom: 14 }}>
        {(["todos", "draft", "approved", "rejected"] as Filtro[]).map((f) => (
          <button key={f} className={filtro === f ? "primary" : ""} onClick={() => setFiltro(f)}>
            {f === "todos" ? "Todos" : f === "draft" ? "Rascunhos" : f === "approved" ? "Aprovados" : "Rejeitados"}
          </button>
        ))}
        {(reservas.data?.length ?? 0) > 0 ? (
          <button onClick={() => maisOportunidades.mutate()}
                  disabled={maisOportunidades.isPending}
                  title="Promove as melhores reservas da análise já feita — sem custo de IA">
            + Mostrar mais oportunidades ({reservas.data!.length})
          </button>
        ) : null}
        <div className="right row">
          <select value={ordem} onChange={(e) => setOrdem(e.target.value as never)}
                  style={{ width: 150 }}>
            <option value="score">Por score</option>
            <option value="time">Por tempo</option>
          </select>
          <div className="seg" style={{ margin: 0 }}>
            <button className={modo === "cards" ? "on" : ""}
                    onClick={() => setModo("cards")}>Cards</button>
            <button className={modo === "lista" ? "on" : ""}
                    onClick={() => setModo("lista")}>Lista</button>
          </div>
        </div>
      </div>

      {cuts.isSuccess && listaFiltrada.length === 0 ? (
        <div className="empty">
          {cuts.data.length === 0
            ? "Nenhum corte ainda. Importe um vídeo para a IA sugerir os melhores momentos."
            : "Nenhum corte neste filtro."}
        </div>
      ) : null}

      {modo === "cards" ? (
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
      ) : (
        <table className="list">
          <thead>
            <tr>
              <th style={{ width: 30 }} />
              <th>Corte</th><th>Trecho</th><th>Duração</th><th>Score</th>
              <th>Veredito</th><th>Status</th><th style={{ width: 190 }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {listaFiltrada.map((c) => (
              <tr key={c.id}>
                <td>
                  <input type="checkbox" checked={selecionados.has(c.id)}
                         onChange={() => toggle(c.id)} style={{ width: 15 }} />
                </td>
                <td>
                  <div className="row" style={{ gap: 8 }}>
                    <Thumb cutId={c.id} className="row-thumb" />
                    <span>{c.title || "(sem título)"}{c.edl ? " ✂" : ""}</span>
                  </div>
                </td>
                <td className="sub">{fmtRange(c.start_s, c.end_s)}</td>
                <td className="sub">{fmtDur(c.duration_s)}</td>
                <td><span className={`score ${scoreClass(c.score)}`}
                          style={{ position: "static", padding: "2px 8px", fontSize: 13 }}>
                  {c.score.toFixed(0)}</span></td>
                <td><span className={`chip verdict-${c.verdict}`}>{c.verdict}</span></td>
                <td><span className={`chip ${c.status}`}>
                  {c.status === "approved" ? "aprovado"
                    : c.status === "rejected" ? "rejeitado" : "rascunho"}</span></td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    <button onClick={() => setAberto(c)}>Revisar</button>
                    <button onClick={() => nav(`/editor/${c.id}`)}>✂ Editor</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

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
