import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
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
  { id: "bold_karaoke", label: "Karaokê em destaque" },
  { id: "clean", label: "Limpo" },
  { id: "podcast", label: "Podcast" },
  { id: "minimal", label: "Minimalista" },
];

export default function CutReviewModal({ cut, kits, onClose }: Props) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(cut.title);
  const [preset, setPreset] = useState<string>(
    (cut.caption_style?.preset as string) ?? "bold_karaoke");
  const [kitId, setKitId] = useState<string>(cut.brand_kit_id ?? "");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [previewMsg, setPreviewMsg] = useState("Preparando pré-visualização…");
  const marcouRevisao = useRef(false);

  // Marca o início da revisão (métrica dos relatórios) uma única vez.
  useEffect(() => {
    if (!marcouRevisao.current) {
      marcouRevisao.current = true;
      patch(`/api/v1/cuts/${cut.id}`, { review_started: true }).catch(() => undefined);
    }
  }, [cut.id]);

  // Pré-visualização: usa o último render (preview ou final) pronto; senão dispara um preview.
  const renders = useQuery({
    queryKey: ["renders", "cut", cut.id],
    queryFn: () => get<Render[]>(`/api/v1/renders?cut_id=${cut.id}`),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "queued" || r.status === "running")
        ? 1500 : false,
  });
  const solicitouPreview = useRef(false);
  useEffect(() => {
    const lista = renders.data;
    if (!lista) return;
    const pronto = lista.find((r) => r.status === "done");
    if (pronto) {
      mediaUrl(`/api/v1/media/${pronto.id}/file`).then(setVideoUrl);
      return;
    }
    const emAndamento = lista.find((r) => r.status === "queued" || r.status === "running");
    if (emAndamento) {
      setPreviewMsg(`Renderizando pré-visualização… ${Math.round(emAndamento.progress * 100)}%`);
      return;
    }
    if (!solicitouPreview.current) {
      solicitouPreview.current = true;
      post(`/api/v1/cuts/${cut.id}/preview`).then(() =>
        qc.invalidateQueries({ queryKey: ["renders", "cut", cut.id] }));
    }
  }, [renders.data, cut.id, qc]);

  const salvar = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch<Cut>(`/api/v1/cuts/${cut.id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cuts"] });
      qc.invalidateQueries({ queryKey: ["renders", "cut", cut.id] });
    },
  });

  function ajustarTrim(campo: "start_s" | "end_s", delta: number) {
    const atual = campo === "start_s" ? cut.start_s : cut.end_s;
    salvar.mutate({ [campo]: Math.max(0, Math.round((atual + delta) * 10) / 10) });
  }

  function decidir(status: "approved" | "rejected") {
    salvar.mutate({
      status,
      title,
      caption_style: { preset },
      brand_kit_id: kitId || null,
    });
    onClose();
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Revisar corte · score {cut.score.toFixed(1)}</h2>
        <div className="review">
          <div>
            {videoUrl ? (
              <video src={videoUrl} controls autoPlay muted />
            ) : (
              <div className="review" style={{ display: "block" }}>
                <div
                  style={{
                    aspectRatio: "9/16", background: "#000", borderRadius: 10,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "var(--muted)", fontSize: 13, padding: 12, textAlign: "center",
                  }}
                >
                  {previewMsg}
                </div>
              </div>
            )}
            <div className="sub" style={{ marginTop: 8 }}>
              Trecho: {fmtRange(cut.start_s, cut.end_s)}
            </div>
            <div className="row wrap" style={{ marginTop: 8 }}>
              <span className="sub">Início:</span>
              <button onClick={() => ajustarTrim("start_s", -1)}>−1s</button>
              <button onClick={() => ajustarTrim("start_s", +1)}>+1s</button>
              <span className="sub">Fim:</span>
              <button onClick={() => ajustarTrim("end_s", -1)}>−1s</button>
              <button onClick={() => ajustarTrim("end_s", +1)}>+1s</button>
            </div>
            <div className="sub" style={{ marginTop: 4 }}>
              Ajustar o trecho recalcula enquadramento e pré-visualização.
            </div>
          </div>
          <div>
            <label>Título</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
            <div className="row" style={{ gap: 18 }}>
              <div style={{ flex: 1 }}>
                <label>Estilo de legenda</label>
                <select value={preset} onChange={(e) => setPreset(e.target.value)}>
                  {PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label>Kit de marca</label>
                <select value={kitId} onChange={(e) => setKitId(e.target.value)}>
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
            {cut.reason ? (
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
            className="right"
            onClick={() => salvar.mutate({ title, caption_style: { preset }, brand_kit_id: kitId || null })}
          >
            Salvar ajustes
          </button>
          <button className="danger" onClick={() => decidir("rejected")}>Rejeitar</button>
          <button className="ok" onClick={() => decidir("approved")}>Aprovar</button>
        </div>
      </div>
    </div>
  );
}
