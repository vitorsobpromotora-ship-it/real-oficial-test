import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { get, mediaUrl, patch, post } from "../api/client";
import type { Cut, Render } from "../api/types";
import { fmtDur, fmtRange, scoreClass } from "../components/CutCard";
import ScoreBreakdown from "../components/ScoreBreakdown";

const VERDICT_LABEL: Record<string, string> = {
  postar: "✓ Postar", revisar: "− Revisar", descartar: "✗ Descartar",
};

const ANALYSIS_LABELS: Record<string, string> = {
  gancho: "Gancho",
  desenvolvimento: "Desenvolvimento",
  conclusao: "Conclusão / payoff",
  ponto_forte: "Ponto forte",
  ponto_fraco: "Ponto fraco",
  sugestao: "Sugestão",
  publico: "Público",
};

const RENDER_LABEL: Record<Cut["render_state"], string> = {
  not_rendered: "Ainda não renderizado",
  queued: "Na fila de renderização",
  rendering: "Renderizando…",
  rendered: "Renderizado",
  render_failed: "Falha na renderização",
};

/** Tela EXCLUSIVAMENTE editorial: assistir, ler a análise, título/descrição e
 *  decidir (Aprovar / Rejeitar / abrir o Editor). Nenhum controle técnico aqui —
 *  alterar o vídeo é responsabilidade do Editor. */
export default function CutPage() {
  const { projectId = "", cutId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();

  const cutQ = useQuery({
    queryKey: ["cuts", "detail", cutId],
    queryFn: () => get<Cut>(`/api/v1/cuts/${cutId}`),
  });
  const cut = cutQ.data;

  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [verAnalise, setVerAnalise] = useState(false);
  const [rejeitado, setRejeitado] = useState(false);
  const [toast, setToast] = useState("");
  const iniciou = useRef(false);
  const pediuPrevia = useRef(false);
  const timerSaida = useRef<number | null>(null);

  useEffect(() => {
    if (!cut) return;
    setTitulo(cut.title);
    setDescricao(cut.description ?? "");
  }, [cut?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // métrica de revisão: marca o início uma única vez por abertura
  useEffect(() => {
    if (cut && !iniciou.current) {
      iniciou.current = true;
      patch(`/api/v1/cuts/${cutId}`, { review_started: true }).catch(() => undefined);
    }
  }, [cut, cutId]);

  useEffect(() => () => {
    if (timerSaida.current) window.clearTimeout(timerSaida.current);
  }, []);

  const salvar = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      patch<Cut>(`/api/v1/cuts/${cutId}`, body),
    onSuccess: (novo) => {
      qc.setQueryData(["cuts", "detail", cutId], novo);
      qc.invalidateQueries({ queryKey: ["cuts", projectId] });
    },
    onError: (e: Error) => {
      setToast(e.message);
      setTimeout(() => setToast(""), 5000);
    },
  });

  // player: usa o render final concluído se existir; senão a prévia (e pede uma se preciso)
  const renders = useQuery({
    queryKey: ["renders", "cut", cutId],
    queryFn: () => get<Render[]>(`/api/v1/renders?cut_id=${cutId}`),
    refetchInterval: (q) => {
      const lista = q.state.data ?? [];
      const ativo = lista.some((r) => r.status === "queued" || r.status === "running");
      const prontoPreview = lista.some((r) => r.kind === "preview" && r.status === "done");
      const prontoFinal = lista.some((r) => r.kind === "final" && r.status === "done");
      return ativo || (!prontoPreview && !prontoFinal) ? 1500 : false;
    },
  });
  const listaRenders = renders.data ?? [];
  const finalPronto = [...listaRenders].reverse()
    .find((r) => r.kind === "final" && r.status === "done" && r.output_path);
  const previaPronta = listaRenders.find((r) => r.kind === "preview" && r.status === "done");
  const renderAtivo = listaRenders.find((r) => r.status === "queued" || r.status === "running");

  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    const alvo = finalPronto
      ? { p: `/api/v1/media/${finalPronto.id}/file`, v: finalPronto.id }
      : previaPronta
        ? { p: `/api/v1/media/cuts/${cutId}/preview`, v: previaPronta.id }
        : null;
    if (!alvo) {
      setVideoUrl(null);
      return;
    }
    mediaUrl(alvo.p).then((u) => vivo && setVideoUrl(`${u}&v=${alvo.v}`));
    return () => {
      vivo = false;
    };
  }, [finalPronto?.id, previaPronta?.id, cutId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!cut || videoUrl || renderAtivo || pediuPrevia.current || !renders.isSuccess) return;
    pediuPrevia.current = true;
    post(`/api/v1/cuts/${cutId}/preview`, {})
      .then(() => qc.invalidateQueries({ queryKey: ["renders", "cut", cutId] }))
      .catch(() => undefined);
  }, [cut, videoUrl, renderAtivo, renders.isSuccess, cutId, qc]);

  const renderizar = useMutation({
    mutationFn: () => post<Render>("/api/v1/renders", { cut_id: cutId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["renders"] });
      qc.invalidateQueries({ queryKey: ["cuts", "detail", cutId] });
      setToast("Renderização iniciada — acompanhe aqui ou na Fila.");
      setTimeout(() => setToast(""), 3000);
    },
    onError: (e: Error) => {
      setToast(e.message);
      setTimeout(() => setToast(""), 5000);
    },
  });

  function salvarTitulo() {
    if (cut && titulo !== cut.title) salvar.mutate({ title: titulo });
  }
  function salvarDescricao() {
    if (cut && descricao !== (cut.description ?? "")) salvar.mutate({ description: descricao });
  }

  function aprovar() {
    // aprovado: a tela NÃO fecha — o usuário pode querer renderizar já
    salvar.mutate({ status: "approved" });
  }
  function rejeitar() {
    salvar.mutate({ status: "rejected" });
    setRejeitado(true);
    timerSaida.current = window.setTimeout(() => nav(`/projeto/${projectId}`), 2600);
  }
  function desfazerRejeicao() {
    if (timerSaida.current) window.clearTimeout(timerSaida.current);
    setRejeitado(false);
    salvar.mutate({ status: "pending_review" });
  }

  if (cutQ.isError) {
    return (
      <div>
        <div className="pagehead"><h1>Corte não encontrado</h1></div>
        <button onClick={() => nav(`/projeto/${projectId}`)}>← Voltar ao projeto</button>
      </div>
    );
  }
  if (!cut) return <div className="ed-loading">Carregando corte…</div>;

  const analysis = cut.analysis ?? {};
  const temAnalise = Object.values(analysis).some(Boolean);

  return (
    <div className="cutpage">
      <div className="pagehead">
        <div className="row" style={{ gap: 12 }}>
          <button onClick={() => nav(`/projeto/${projectId}`)}>← Voltar</button>
          <div>
            <h1 style={{ display: "flex", alignItems: "center", gap: 10 }}>
              Corte #{cut.rank ?? "—"}
              <span className={`score ${scoreClass(cut.score)} inline`}>{cut.score.toFixed(0)}</span>
            </h1>
            <div className="sub">
              {fmtDur(cut.duration_s)} · origem {fmtRange(cut.start_s, cut.end_s)} ·{" "}
              {cut.origin === "heuristic" ? "análise local" : cut.origin === "gpt" ? "IA GPT" : "IA Claude"}
            </div>
          </div>
        </div>
        <div className="chips" style={{ margin: 0 }}>
          <span className={`chip verdict-${cut.verdict}`}>{VERDICT_LABEL[cut.verdict] ?? cut.verdict}</span>
          {cut.status === "approved" ? <span className="chip approved">✓ Aprovado</span> : null}
          {cut.status === "rejected" ? <span className="chip rejected">Rejeitado</span> : null}
          {cut.edl ? <span className="chip warnc">✂ editado no Editor</span> : null}
        </div>
      </div>

      <div className="cutpage-grid">
        <div className="cutpage-player card">
          {videoUrl ? (
            <video key={videoUrl} src={videoUrl} controls playsInline />
          ) : (
            <div className="cutpage-ph">
              {renderAtivo
                ? `Preparando o vídeo… ${Math.round((renderAtivo.progress ?? 0) * 100)}%`
                : "Preparando o vídeo…"}
            </div>
          )}
          <div className="sub" style={{ marginTop: 8 }}>
            {finalPronto
              ? "Você está assistindo ao render final."
              : "Prévia do corte como ele vai ficar (legendas, enquadramento e kit aplicados)."}
          </div>
        </div>

        <div className="cutpage-side">
          <div className="card">
            <label className="lbl">Título</label>
            <input value={titulo} onChange={(e) => setTitulo(e.target.value)}
                   onBlur={salvarTitulo} placeholder="Título do corte"
                   data-testid="cut-title" />
            <label className="lbl" style={{ marginTop: 12 }}>Descrição</label>
            <textarea value={descricao} onChange={(e) => setDescricao(e.target.value)}
                      onBlur={salvarDescricao} rows={3}
                      placeholder="Descrição para a publicação (TikTok, Reels, Shorts…)"
                      data-testid="cut-description" />
            <div className="sub" style={{ marginTop: 6 }}>
              Título e descrição acompanham o corte e serão usados na publicação futura.
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 8 }}>Análise do corte</h3>
            {cut.hook_text ? (
              <div className="analysis-item">
                <b>{ANALYSIS_LABELS.gancho}</b>
                <span>“{cut.hook_text}”</span>
              </div>
            ) : null}
            {temAnalise ? (
              <>
                {(verAnalise
                  ? Object.entries(ANALYSIS_LABELS)
                  : Object.entries(ANALYSIS_LABELS).slice(1, 4)
                ).map(([k, rotulo]) =>
                  k !== "gancho" && analysis[k as keyof typeof analysis] ? (
                    <div key={k} className="analysis-item">
                      <b>{rotulo}</b>
                      <span>{analysis[k as keyof typeof analysis]}</span>
                    </div>
                  ) : null)}
                <button style={{ marginTop: 8 }} onClick={() => setVerAnalise(!verAnalise)}>
                  {verAnalise ? "Ver menos" : "Ver análise completa (com os 18 parâmetros)"}
                </button>
                {verAnalise ? <ScoreBreakdown breakdown={cut.score_breakdown} /> : null}
              </>
            ) : (
              <div className="sub">{cut.reason || "Sem análise editorial detalhada."}</div>
            )}
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 8 }}>Renderização</h3>
            <div className="chips" style={{ margin: 0 }}>
              <span className={`chip ${cut.render_state === "rendered" ? "approved"
                : cut.render_state === "render_failed" ? "rejected" : ""}`}>
                {RENDER_LABEL[cut.render_state]}
              </span>
              {cut.render_outdated ? (
                <span className="chip warnc" data-testid="render-outdated">
                  ⚠ Render desatualizado — há edições salvas depois dele
                </span>
              ) : null}
            </div>
            {cut.status === "approved" ? (
              <div className="row" style={{ marginTop: 10 }}>
                <button className="primary" disabled={renderizar.isPending || !!renderAtivo}
                        onClick={() => renderizar.mutate()} data-testid="btn-render">
                  {cut.render_outdated ? "Renderizar nova versão"
                    : cut.render_state === "rendered" ? "Re-renderizar" : "Renderizar"}
                </button>
                {finalPronto?.output_path ? (
                  <button onClick={() => window.realOficial?.showInFolder?.(finalPronto.output_path!)}>
                    Mostrar arquivo
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="sub" style={{ marginTop: 8 }}>
                {cut.status === "rejected"
                  ? "Corte rejeitado não renderiza — restaure-o para revisão primeiro."
                  : "Aprove o corte para liberar a renderização."}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="cutpage-actions">
        {cut.status !== "approved" && cut.status !== "rejected" ? (
          <>
            <button className="ok" onClick={aprovar} data-testid="btn-approve">Aprovar</button>
            <button className="danger" onClick={rejeitar} data-testid="btn-reject">Rejeitar</button>
          </>
        ) : cut.status === "approved" ? (
          <span className="chip approved" style={{ fontSize: 14 }}>✓ Aprovado</span>
        ) : (
          <button onClick={desfazerRejeicao}>Restaurar para revisão</button>
        )}
        <button className="primary"
                onClick={() => nav(`/projeto/${projectId}/corte/${cutId}/editor`)}
                data-testid="btn-editor">
          ✂ Editor
        </button>
        <button className="right" onClick={() => nav(`/projeto/${projectId}`)}>Fechar</button>
      </div>

      {rejeitado ? (
        <div className="toast" data-testid="toast-rejected">
          Corte movido para Rejeitados.{" "}
          <button onClick={desfazerRejeicao} style={{ marginLeft: 8 }}>Desfazer</button>
        </div>
      ) : toast ? (
        <div className="toast">{toast}</div>
      ) : null}
    </div>
  );
}
