import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, mediaUrl, patch, post } from "../api/client";
import type { BrandKit, Cut, Render } from "../api/types";
import { fmtRange } from "./CutCard";
import ScoreBreakdown from "./ScoreBreakdown";

interface Props {
  cut: Cut;
  kits: BrandKit[];
  onClose(): void;
}

const PRESETS = [
  { id: "bold_karaoke", label: "Karaokê Bold" },
  { id: "clean", label: "Clean" },
  { id: "podcast", label: "Podcast" },
  { id: "minimal", label: "Minimal" },
  { id: "palavra_pop", label: "Palavra Pop" },
  { id: "highlight_box", label: "Highlight Box" },
  { id: "bounce", label: "Bounce" },
  { id: "subtitle_bar", label: "Subtitle Bar" },
];

const FRAMINGS: { id: string; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "left", label: "Esquerda" },
  { id: "right", label: "Direita" },
  { id: "center", label: "Centro" },
  { id: "blur", label: "Desfocado" },
];

const VERDICT_LABEL: Record<string, string> = {
  postar: "✓ Postar", revisar: "− Revisar", descartar: "✗ Descartar",
};

const ANALYSIS_LABELS: [keyof NonNullable<Cut["analysis"]>, string][] = [
  ["gancho", "Gancho (3 primeiros segundos)"],
  ["desenvolvimento", "Desenvolvimento"],
  ["conclusao", "Conclusão / payoff"],
  ["ponto_forte", "Ponto forte"],
  ["ponto_fraco", "Ponto fraco"],
  ["sugestao", "Sugestão de ajuste"],
  ["publico", "Público ideal"],
];

export default function CutReviewModal({ cut: cutInicial, kits, onClose }: Props) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [title, setTitle] = useState(cutInicial.title);
  const [preset, setPreset] = useState<string>(
    (cutInicial.caption_style?.preset as string) ?? "bold_karaoke");
  const [kitId, setKitId] = useState<string>(cutInicial.brand_kit_id ?? "");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [previewMsg, setPreviewMsg] = useState("Preparando pré-visualização…");
  const [toast, setToast] = useState("");
  const marcouRevisao = useRef(false);
  const solicitouPreview = useRef(false);

  // Estado sempre fresco do corte (o PATCH devolve o corte atualizado).
  const cutQuery = useQuery({
    queryKey: ["cuts", "detail", cutInicial.id],
    queryFn: () => get<Cut>(`/api/v1/cuts/${cutInicial.id}`),
    initialData: cutInicial,
  });
  const cut = cutQuery.data ?? cutInicial;
  const framing = (cut.edits?.framing as string) ?? "auto";

  useEffect(() => {
    if (!marcouRevisao.current) {
      marcouRevisao.current = true;
      patch(`/api/v1/cuts/${cut.id}`, { review_started: true }).catch(() => undefined);
    }
  }, [cut.id]);

  const renders = useQuery({
    queryKey: ["renders", "cut", cut.id],
    queryFn: () => get<Render[]>(`/api/v1/renders?cut_id=${cut.id}`),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "queued" || r.status === "running")
        ? 1500 : false,
  });

  useEffect(() => {
    const lista = renders.data;
    if (!lista) return;
    const pronto = lista.find((r) => r.status === "done");
    if (pronto) {
      mediaUrl(`/api/v1/media/${pronto.id}/file`).then((u) =>
        setVideoUrl(`${u}&v=${pronto.id}`));
      return;
    }
    setVideoUrl(null);
    const emAndamento = lista.find((r) => r.status === "queued" || r.status === "running");
    if (emAndamento) {
      setPreviewMsg(`Renderizando pré-visualização… ${Math.round(emAndamento.progress * 100)}%`);
      return;
    }
    if (!solicitouPreview.current) {
      solicitouPreview.current = true;
      setPreviewMsg("Preparando pré-visualização…");
      post(`/api/v1/cuts/${cut.id}/preview`).then(() =>
        qc.invalidateQueries({ queryKey: ["renders", "cut", cut.id] }));
    }
  }, [renders.data, cut.id, qc]);

  function refreshPreview(msg: string) {
    solicitouPreview.current = false;
    setVideoUrl(null);
    setPreviewMsg(msg);
    qc.invalidateQueries({ queryKey: ["renders", "cut", cut.id] });
  }

  const salvar = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch<Cut>(`/api/v1/cuts/${cut.id}`, body),
    onSuccess: (novo, body) => {
      qc.setQueryData(["cuts", "detail", cut.id], novo);
      qc.invalidateQueries({ queryKey: ["cuts"] });
      const visual = ["start_s", "end_s", "framing", "title", "caption_style", "brand_kit_id"]
        .some((k) => k in body);
      if (visual) {
        refreshPreview("Ajuste salvo — atualizando prévia…");
        setToast("Ajuste salvo. A prévia está sendo atualizada.");
      } else {
        setToast("Salvo.");
      }
      setTimeout(() => setToast(""), 2800);
    },
    onError: (e: Error) => {
      setToast(`Falha ao salvar: ${e.message}`);
      setTimeout(() => setToast(""), 5000);
    },
  });

  function ajustarTrim(campo: "start_s" | "end_s", delta: number) {
    const atual = campo === "start_s" ? cut.start_s : cut.end_s;
    salvar.mutate({ [campo]: Math.max(0, Math.round((atual + delta) * 10) / 10) });
  }

  function decidir(status: "approved" | "rejected") {
    salvar.mutate({ status, title, caption_style: { preset }, brand_kit_id: kitId || null });
    onClose();
  }

  const analysisEntries = ANALYSIS_LABELS
    .map(([key, label]) => ({ key, label, text: cut.analysis?.[key] ?? "" }))
    .filter((e) => e.text);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 14 }}>
          <h2 style={{ margin: 0 }}>Revisar corte · score {cut.score.toFixed(1)}</h2>
          <span className={`chip verdict-${cut.verdict}`}>
            {VERDICT_LABEL[cut.verdict] ?? cut.verdict}
          </span>
          {cut.origin === "heuristic" ? (
            <span className="chip">análise local (sem IA)</span>
          ) : null}
        </div>
        <div className="review">
          <div>
            {videoUrl ? (
              <video key={videoUrl} src={videoUrl} controls autoPlay muted />
            ) : (
              <div
                style={{
                  aspectRatio: "9/16", background: "#000", borderRadius: 10,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--muted)", fontSize: 13, padding: 12, textAlign: "center",
                }}
              >
                {previewMsg}
              </div>
            )}
            <div className="row" style={{ marginTop: 8 }}>
              <span className="sub">Trecho: {fmtRange(cut.start_s, cut.end_s)}</span>
              <button className="right" onClick={() => refreshPreview("Atualizando prévia…")}>
                Atualizar prévia
              </button>
            </div>
            <div className="row wrap" style={{ marginTop: 8 }}>
              <span className="sub">Início:</span>
              <button onClick={() => ajustarTrim("start_s", -1)}>−1s</button>
              <button onClick={() => ajustarTrim("start_s", +1)}>+1s</button>
              <span className="sub">Fim:</span>
              <button onClick={() => ajustarTrim("end_s", -1)}>−1s</button>
              <button onClick={() => ajustarTrim("end_s", +1)}>+1s</button>
            </div>
            {cut.edl ? (
              <div className="sub" style={{ marginTop: 6, color: "var(--warn)" }}>
                Este corte tem edição feita no Editor ({cut.edl.segments.length} trechos).
                O trim rápido acima apara essa edição — para mexer nos detalhes, abra o Editor.
              </div>
            ) : null}
            <label>Enquadramento (quem fica em foco no 9:16)</label>
            <div className="row wrap">
              {FRAMINGS.map((f) => (
                <button
                  key={f.id}
                  className={framing === f.id ? "primary" : ""}
                  onClick={() => salvar.mutate({ framing: f.id })}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="sub" style={{ marginTop: 4 }}>
              Se o Auto focar a pessoa errada, escolha o lado correto — a prévia é refeita.
            </div>
          </div>
          <div>
            <label>Título</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
                   onBlur={() => title !== cut.title && salvar.mutate({ title })} />
            <div className="row" style={{ gap: 18 }}>
              <div style={{ flex: 1 }}>
                <label>Estilo de legenda</label>
                <select value={preset} onChange={(e) => {
                  setPreset(e.target.value);
                  salvar.mutate({ caption_style: { preset: e.target.value } });
                }}>
                  {PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label>Kit de marca</label>
                <select value={kitId} onChange={(e) => {
                  setKitId(e.target.value);
                  salvar.mutate({ brand_kit_id: e.target.value || null });
                }}>
                  <option value="">(nenhum)</option>
                  {kits.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
                </select>
              </div>
            </div>
            {cut.hook_text ? (
              <>
                <label>Gancho detectado</label>
                <div className="sub" style={{ fontStyle: "italic" }}>“{cut.hook_text}”</div>
              </>
            ) : null}
            {analysisEntries.length > 0 ? (
              <>
                <label>Análise editorial</label>
                <div className="analysis">
                  {analysisEntries.map((e) => (
                    <div key={e.key} className="analysis-item">
                      <b>{e.label}</b>
                      <span>{e.text}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : cut.reason ? (
              <>
                <label>Por que a IA escolheu</label>
                <div className="sub">{cut.reason}</div>
              </>
            ) : null}
            <label>Detalhamento do score (18 parâmetros)</label>
            <ScoreBreakdown breakdown={cut.score_breakdown} />
            <label>Sua avaliação do ranking (opcional — alimenta os relatórios)</label>
            <input
              type="number"
              min={1}
              placeholder="ex.: 1 = melhor corte na sua opinião"
              defaultValue={cut.human_rank ?? ""}
              onBlur={(e) => {
                const v = parseInt(e.target.value, 10);
                if (!Number.isNaN(v) && v >= 1) salvar.mutate({ human_rank: v });
              }}
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 18 }}>
          <button onClick={onClose}>Fechar</button>
          <button
            onClick={() => {
              onClose();
              nav(`/editor/${cut.id}`);
            }}
            title="Timeline completa: aparar com precisão, dividir, remover trechos, fades e áudio"
          >
            ✂ Abrir no Editor
          </button>
          {toast ? <span className="sub">{toast}</span> : null}
          <button className="danger right" onClick={() => decidir("rejected")}>Rejeitar</button>
          <button className="ok" onClick={() => decidir("approved")}>Aprovar</button>
        </div>
      </div>
    </div>
  );
}
