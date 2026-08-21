/**
 * Painel B-roll (v4 FASE H) — biblioteca de mídia do PROJETO e inserção no
 * corte. O arquivo é COPIADO para a biblioteca (apagar a origem não quebra
 * nada) e o efeito vira um bloco na track B-roll, com o áudio principal
 * sempre preservado (b-roll nunca entra no áudio).
 */
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, get, mediaUrl } from "../api/client";
import type { ProjectMedia } from "../api/types";
import type { Draft } from "./model";
import { manifestVazio, novoId, seedDe, type EffectInstance } from "./motion";
import { useEffect } from "react";

interface Props {
  projectId: string;
  draft: Draft;
  upd(patch: Partial<Draft>): void;
  outNow: number;
  onMotion(fxId: string): void;
}

export default function BrollPanel(p: Props) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [erro, setErro] = useState("");
  const [urls, setUrls] = useState<Record<string, string>>({});

  const mediaQ = useQuery({
    queryKey: ["project-media", p.projectId],
    queryFn: () => get<{ media: ProjectMedia[] }>(
      `/api/v1/projects/${p.projectId}/media`),
  });
  const lista = mediaQ.data?.media ?? [];

  useEffect(() => {
    let vivo = true;
    for (const m of lista) {
      if (urls[m.id]) continue;
      mediaUrl(`/api/v1/media/broll/${m.id}`).then((u) => {
        if (vivo) setUrls((x) => ({ ...x, [m.id]: u }));
      });
    }
    return () => { vivo = false; };
  }, [lista]); // eslint-disable-line react-hooks/exhaustive-deps

  const enviar = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api(`/api/v1/projects/${p.projectId}/media`,
        { method: "POST", body: fd });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-media", p.projectId] }),
    onError: (e: Error) => setErro(e.message),
  });

  function inserir(m: ProjectMedia) {
    const id = novoId();
    const inicio = Math.max(0, Math.round(p.outNow * 100) / 100);
    const dur = m.kind === "video" && m.duration_s
      ? Math.min(4, Math.max(1, m.duration_s)) : 2.5;
    const eff: EffectInstance = {
      id, type: "broll", preset: "broll",
      target: { kind: "media", media_id: m.id },
      start: inicio, end: Math.round((inicio + dur) * 100) / 100,
      intensity: "normal", enabled: true, seed: seedDe(id),
      params: { mode: "overlay", x: 0.5, y: 0.28, w: 0.62,
        transition: "fade", transition_s: 0.18 },
    };
    const man = p.draft.motion ?? manifestVazio();
    p.upd({ motion: { ...man, effects: [...man.effects, eff] } });
    p.onMotion(id);
  }

  return (
    <>
      <h3>B-roll</h3>
      <div className="sub" style={{ marginBottom: 8 }}>
        Imagens e vídeos de apoio sobre o corte. O áudio principal continua
        SEMPRE — b-roll não toca no som.
      </div>
      <button data-testid="br-upload"
              onClick={() => fileRef.current?.click()}
              disabled={enviar.isPending}>
        {enviar.isPending ? "Importando…" : "⬆ Importar mídia"}
      </button>
      <input ref={fileRef} type="file" hidden data-testid="br-file"
             accept=".mp4,.mov,.webm,.png,.jpg,.jpeg,.webp"
             onChange={(e) => {
               const f = e.target.files?.[0];
               if (f) { setErro(""); enviar.mutate(f); }
               e.target.value = "";
             }} />
      {erro ? <div className="err" style={{ marginTop: 8 }}>{erro}</div> : null}

      {!lista.length ? (
        <div className="sub" style={{ marginTop: 12 }}>
          Biblioteca vazia — importe MP4, MOV, WebM, PNG, JPEG ou WebP.
          O arquivo é copiado para o projeto.
        </div>
      ) : (
        <div className="br-lista" data-testid="br-lista">
          {lista.map((m) => (
            <div key={m.id} className="br-item" data-testid={`br-item-${m.id}`}>
              {m.kind === "image"
                ? <img src={urls[m.id]} alt="" />
                : <video src={urls[m.id]} muted preload="metadata" />}
              <div className="br-meta">
                <b>{m.filename}</b>
                <span className="sub">
                  {m.kind === "image" ? "imagem"
                    : `vídeo${m.duration_s ? ` · ${m.duration_s.toFixed(1)}s` : ""}`}
                </span>
              </div>
              <button data-testid={`br-add-${m.id}`} title="Inserir no cursor"
                      onClick={() => inserir(m)}>＋ no cursor</button>
            </div>
          ))}
        </div>
      )}
      <div className="sub" style={{ marginTop: 10 }}>
        Depois de inserir, ajuste modo (sobrepor/tela cheia), posição e
        transição no painel Motion — o bloco fica na track B-roll.
      </div>
    </>
  );
}
