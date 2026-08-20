// Relatórios internos (F6): componentes React no tema do app, com exportação
// do HTML clássico. Métricas: aproveitamento, tempo economizado, intervenção,
// edição, custo de IA, tempos por estágio e o perfil editorial transparente.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get, mediaUrl } from "../api/client";
import type { Project, Source } from "../api/types";

interface SourceReport {
  source: { id: string; title: string; duration_s: number | null };
  cortes: {
    gerados: number; aprovados: number; rejeitados: number; pendentes: number;
    taxa_aproveitamento: number | null; origem_claude: number;
    origem_heuristica: number; score_medio: number | null; score_maximo: number | null;
  };
  tempo: { baseline_manual_min: number; revisao_investida_min: number;
    economia_min: number; formula: string };
  intervencao: { cortes_revisados: number; media_s: number | null;
    mediana_s: number | null; pct_editados: number | null };
  edicao: { cortes_com_edicao_no_editor: number; palavras_corrigidas: number;
    enquadramento_manual: number };
  score_quality: { spearman_rank_ia_vs_humano: number | null; n_avaliados: number };
  custo_claude: { chamadas: number; input_tokens: number; output_tokens: number;
    total_usd: number };
  timings: { stage: string; seconds: number }[];
  cortes_detalhe: { id: string; rank: number | null; score: number; status: string;
    title: string; start_s: number; end_s: number; origin: string }[];
}

interface ProjectReport {
  totais: { fontes: number; cortes_gerados: number; cortes_aprovados: number;
    taxa_aproveitamento: number | null; economia_min: number; custo_claude_usd: number };
  perfil_editorial: {
    pronto: boolean; amostra: number; nota: string;
    duracao_mediana_aprovados_s?: number | null;
    faixa_duracao_preferida_s?: [number, number] | null;
    taxa_por_faixa_score?: { faixa: string; aprovados: number; total: number; taxa: number }[];
    sugestoes?: string[];
  };
}

const ESTAGIO: Record<string, string> = {
  ingest: "Importação", transcribe: "Transcrição", analyze: "Análise IA",
  candidates: "Candidatos", reframe: "Enquadramento", render: "Render",
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card stat">
      <div className="stat-v">{value}</div>
      <div className="stat-l">{label}</div>
      {hint ? <div className="sub" style={{ marginTop: 4 }}>{hint}</div> : null}
    </div>
  );
}

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v * 100)}%`;
const min = (v: number | null | undefined) =>
  v == null ? "—" : v >= 60 ? `${(v / 60).toFixed(1)}h` : `${Math.round(v)}min`;

export default function Reports() {
  const [projectId, setProjectId] = useState("");
  const [sourceId, setSourceId] = useState("");

  const projects = useQuery({ queryKey: ["projects"], queryFn: () => get<Project[]>("/api/v1/projects") });
  const sources = useQuery({
    queryKey: ["sources", projectId],
    queryFn: () => get<Source[]>(`/api/v1/projects/${projectId}/sources`),
    enabled: !!projectId,
  });
  const projRep = useQuery({
    queryKey: ["report", "project", projectId],
    queryFn: () => get<ProjectReport>(`/api/v1/reports/projects/${projectId}`),
    enabled: !!projectId,
  });
  const srcRep = useQuery({
    queryKey: ["report", "source", sourceId],
    queryFn: () => get<SourceReport>(`/api/v1/reports/sources/${sourceId}`),
    enabled: !!sourceId,
  });

  const r = srcRep.data;
  const p = projRep.data;
  const maxStage = Math.max(1, ...(r?.timings.map((t) => t.seconds) ?? [1]));

  async function exportarHtml() {
    const u = await mediaUrl(`/api/v1/reports/sources/${sourceId}/html`);
    if (window.realOficial) window.realOficial.openExternal(u);
    else window.open(u, "_blank");
  }

  return (
    <div>
      <div className="pagehead">
        <h1>Relatórios</h1>
        {sourceId ? (
          <button onClick={exportarHtml}>Exportar HTML (compartilhável)</button>
        ) : null}
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        <select value={projectId} style={{ width: 280 }}
                onChange={(e) => { setProjectId(e.target.value); setSourceId(""); }}>
          <option value="">Escolha um projeto…</option>
          {projects.data?.map((pr) => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
        </select>
        <select value={sourceId} style={{ width: 340 }} disabled={!projectId}
                onChange={(e) => setSourceId(e.target.value)}>
          <option value="">Todos os vídeos (visão do projeto)</option>
          {sources.data?.map((s) => (
            <option key={s.id} value={s.id}>{s.title || s.id}</option>
          ))}
        </select>
      </div>

      {!projectId ? (
        <div className="empty">
          Selecione um projeto para ver aproveitamento, tempo economizado, edição,
          custo de IA e o perfil editorial aprendido das suas decisões.
        </div>
      ) : null}

      {projectId && !sourceId && p ? (
        <>
          <div className="statgrid">
            <Stat label="Cortes gerados" value={String(p.totais.cortes_gerados)} />
            <Stat label="Taxa de aproveitamento"
                  value={pct(p.totais.taxa_aproveitamento)}
                  hint={`${p.totais.cortes_aprovados} aprovados`} />
            <Stat label="Tempo economizado" value={min(p.totais.economia_min)}
                  hint="vs. cortar manualmente" />
            <Stat label="Custo de IA" value={`US$ ${p.totais.custo_claude_usd.toFixed(2)}`} />
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>Perfil editorial (aprendido das SUAS decisões — transparente)</h3>
            {!p.perfil_editorial.pronto ? (
              <div className="sub">{p.perfil_editorial.nota}</div>
            ) : (
              <>
                <div className="row wrap" style={{ gap: 18, marginTop: 6 }}>
                  <span className="chip">
                    duração mediana aprovada: {p.perfil_editorial.duracao_mediana_aprovados_s ?? "—"}s
                  </span>
                  {p.perfil_editorial.faixa_duracao_preferida_s ? (
                    <span className="chip">
                      faixa preferida: {p.perfil_editorial.faixa_duracao_preferida_s[0]}–
                      {p.perfil_editorial.faixa_duracao_preferida_s[1]}s
                    </span>
                  ) : null}
                  <span className="chip">{p.perfil_editorial.amostra} decisões analisadas</span>
                </div>
                <label>Aprovação por faixa de score</label>
                {(p.perfil_editorial.taxa_por_faixa_score ?? []).map((f) => (
                  <div key={f.faixa} className="row" style={{ marginBottom: 5 }}>
                    <span className="sub" style={{ width: 70 }}>{f.faixa}</span>
                    <div className="bar" style={{ flex: 1 }}>
                      <i style={{ width: `${Math.round(f.taxa * 100)}%` }} />
                    </div>
                    <span className="sub" style={{ width: 110 }}>
                      {f.aprovados}/{f.total} ({Math.round(f.taxa * 100)}%)
                    </span>
                  </div>
                ))}
                {(p.perfil_editorial.sugestoes ?? []).map((sg, i) => (
                  <div key={i} className="analysis-item" style={{ marginTop: 8 }}>
                    <b>Sugestão</b><span>{sg}</span>
                  </div>
                ))}
                <div className="sub" style={{ marginTop: 8 }}>{p.perfil_editorial.nota}</div>
              </>
            )}
          </div>
          <div className="sub" style={{ marginTop: 14 }}>
            Escolha um vídeo acima para o detalhamento por fonte (funil, estágios, cortes).
          </div>
        </>
      ) : null}

      {sourceId && r ? (
        <>
          <div className="statgrid">
            <Stat label="Cortes gerados" value={String(r.cortes.gerados)}
                  hint={`${r.cortes.origem_claude} por IA · ${r.cortes.origem_heuristica} local`} />
            <Stat label="Aproveitamento" value={pct(r.cortes.taxa_aproveitamento)}
                  hint={`${r.cortes.aprovados} aprov. · ${r.cortes.rejeitados} rejeit. · ${r.cortes.pendentes} pend.`} />
            <Stat label="Tempo economizado" value={min(r.tempo.economia_min)}
                  hint={r.tempo.formula} />
            <Stat label="Score IA × sua avaliação"
                  value={r.score_quality.spearman_rank_ia_vs_humano?.toFixed(2) ?? "—"}
                  hint={`${r.score_quality.n_avaliados} cortes ranqueados por você`} />
          </div>
          <div className="statgrid" style={{ marginTop: 14 }}>
            <Stat label="Editados no Editor" value={String(r.edicao.cortes_com_edicao_no_editor)}
                  hint="cortes com EDL própria" />
            <Stat label="Palavras corrigidas" value={String(r.edicao.palavras_corrigidas)} />
            <Stat label="Enquadramento manual" value={String(r.edicao.enquadramento_manual)}
                  hint="modos/overrides forçados" />
            <Stat label="Custo de IA" value={`US$ ${r.custo_claude.total_usd.toFixed(2)}`}
                  hint={`${r.custo_claude.chamadas} chamadas`} />
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>Tempo por estágio</h3>
            {r.timings.map((t, i) => (
              <div key={i} className="row" style={{ marginBottom: 5 }}>
                <span className="sub" style={{ width: 120 }}>{ESTAGIO[t.stage] ?? t.stage}</span>
                <div className="bar" style={{ flex: 1 }}>
                  <i style={{ width: `${Math.round((t.seconds / maxStage) * 100)}%` }} />
                </div>
                <span className="sub" style={{ width: 70 }}>{t.seconds.toFixed(1)}s</span>
              </div>
            ))}
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>Cortes desta fonte</h3>
            <table className="list">
              <thead>
                <tr><th>#</th><th>Título</th><th>Score</th><th>Status</th><th>Origem</th></tr>
              </thead>
              <tbody>
                {r.cortes_detalhe.map((c) => (
                  <tr key={c.id}>
                    <td className="sub">{c.rank ?? "—"}</td>
                    <td>{c.title || "(sem título)"}</td>
                    <td>{c.score.toFixed(0)}</td>
                    <td><span className={`chip ${c.status}`}>
                      {c.status === "approved" ? "aprovado"
                        : c.status === "rejected" ? "rejeitado" : "rascunho"}</span></td>
                    <td className="sub">{c.origin === "heuristic" ? "local" : c.origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
