/**
 * Inspector contextual (Pontos 5, 9, 26): mostra SOMENTE os controles da
 * ferramenta selecionada. A seleção também acontece pelo objeto (timeline
 * seleciona trecho → Corte; clique na legenda → Legenda), no espírito do
 * CapCut: selecionou algo → edita aquilo.
 */
import type { BrandKit, CaptionPreset, Cut, TranscriptWord } from "../api/types";
import { fmtSrc, fmtT, srcToOut, type Draft } from "./model";

export type Tool =
  | "corte" | "pausas" | "audio" | "enquadramento" | "punchin"
  | "legenda" | "palavras" | "estilo" | "kit";

export const TOOLS: { id: Tool; label: string; icon: string }[] = [
  { id: "corte", label: "Corte", icon: "✂" },
  { id: "pausas", label: "Pausas", icon: "⏭" },
  { id: "audio", label: "Áudio", icon: "🔊" },
  { id: "enquadramento", label: "Enquadrar", icon: "🎯" },
  { id: "punchin", label: "Punch-in", icon: "🔍" },
  { id: "legenda", label: "Legenda", icon: "💬" },
  { id: "palavras", label: "Palavras", icon: "🔤" },
  { id: "estilo", label: "Estilo", icon: "🎨" },
  { id: "kit", label: "Kit", icon: "🏷" },
];

const FRAMINGS: [string, string][] = [
  ["auto", "Automático (falante ativo)"],
  ["center", "Centro"], ["left", "Esquerda"], ["right", "Direita"],
  ["fit", "Vídeo inteiro (fit)"], ["blur", "Fundo desfocado"],
  ["two", "Duas pessoas"], ["split", "Split screen"],
];

interface Props {
  tool: Tool;
  setTool(t: Tool): void;
  cut: Cut;
  draft: Draft;
  upd(patch: Partial<Draft>): void; // commit com histórico (undo/redo)
  title: string;
  kits: BrandKit[];
  presets: CaptionPreset[];
  words: TranscriptWord[];
  editWord: number | null;
  setEditWord(i: number | null): void;
  sel: number | null;
  playhead: number;
  onPauses(nivel: "leve" | "normal" | "agressivo"): void;
  onOpenStudio(kitId: string): void;
}

export default function Inspector(p: Props) {
  const d = p.draft;
  const segs = d.segments;
  const env0 = segs[0]?.src_start ?? 0;
  const env1 = segs[segs.length - 1]?.src_end ?? 0;

  return (
    <div className="insp">
      <div className="insp-rail" role="tablist">
        {TOOLS.map((t) => (
          <button key={t.id} role="tab" aria-selected={p.tool === t.id}
                  className={`insp-tab${p.tool === t.id ? " on" : ""}`}
                  onClick={() => p.setTool(t.id)} data-testid={`tool-${t.id}`}>
            <span aria-hidden>{t.icon}</span>{t.label}
          </button>
        ))}
      </div>

      <div className="insp-body" data-testid={`panel-${p.tool}`}>
        {p.tool === "corte" ? (
          <>
            <h3>Corte</h3>
            {p.sel != null && segs[p.sel] ? (
              <div className="insp-sel">
                <b>Trecho {p.sel + 1}</b> · {fmtT(srcToOut(segs, segs[p.sel].src_start))} →{" "}
                {fmtT(srcToOut(segs, segs[p.sel].src_end - 0.001) + 0.001)} ·{" "}
                {(segs[p.sel].src_end - segs[p.sel].src_start).toFixed(1)}s
                <div className="sub">Origem: {fmtSrc(segs[p.sel].src_start)} → {fmtSrc(segs[p.sel].src_end)}</div>
              </div>
            ) : (
              <div className="sub" style={{ marginBottom: 8 }}>
                Selecione um trecho na timeline, use ✂ para dividir no cursor e as
                alças para aparar. Trechos removidos ficam sombreados — clique para restaurar.
              </div>
            )}
            <div className="row">
              <div style={{ flex: 1 }}>
                <label>Fade de entrada (s)</label>
                <input type="number" min={0} max={3} step={0.1} value={d.fade_in_s}
                       onChange={(e) => p.upd({ fade_in_s: Math.max(0, Number(e.target.value) || 0) })} />
              </div>
              <div style={{ flex: 1 }}>
                <label>Fade de saída (s)</label>
                <input type="number" min={0} max={3} step={0.1} value={d.fade_out_s}
                       onChange={(e) => p.upd({ fade_out_s: Math.max(0, Number(e.target.value) || 0) })} />
              </div>
            </div>
            <label>Transição nas junções</label>
            <select value={String(d.transition_s)}
                    onChange={(e) => p.upd({ transition_s: Number(e.target.value) })}>
              <option value="0">Corte seco (sem transição)</option>
              <option value="0.12">Suave — 0,12s</option>
              <option value="0.25">Média — 0,25s</option>
              <option value="0.5">Longa — 0,5s</option>
            </select>
          </>
        ) : null}

        {p.tool === "pausas" ? (
          <>
            <h3>Remover pausas</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              Corta silêncios automaticamente — os jump cuts aparecem na timeline e
              nada é aplicado até salvar (Ctrl+Z desfaz). Pausas dramáticas após
              “!”/“?” são preservadas; só o Agressivo corta tudo.
            </div>
            <div className="row wrap">
              {(["leve", "normal", "agressivo"] as const).map((n) => (
                <button key={n} onClick={() => p.onPauses(n)}>
                  {n === "leve" ? "Leve" : n === "normal" ? "Normal" : "Agressivo"}
                </button>
              ))}
            </div>
          </>
        ) : null}

        {p.tool === "audio" ? (
          <>
            <h3>Áudio</h3>
            <label>
              Volume do corte: {d.audio.gain_db > 0 ? "+" : ""}{d.audio.gain_db.toFixed(1)} dB
            </label>
            <input type="range" min={-20} max={10} step={0.5} value={d.audio.gain_db}
                   onChange={(e) => p.upd({ audio: { ...d.audio, gain_db: Number(e.target.value) } })} />
            <label className="ed-check">
              <input type="checkbox" checked={d.audio.mute}
                     onChange={(e) => p.upd({ audio: { ...d.audio, mute: e.target.checked } })} />
              Sem áudio (mudo)
            </label>
            <div className="row">
              <div style={{ flex: 1 }}>
                <label>Fade de áudio — entrada (s)</label>
                <input type="number" min={0} max={3} step={0.1} value={d.audio.fade_in_s}
                       onChange={(e) => p.upd({ audio: { ...d.audio, fade_in_s: Math.max(0, Number(e.target.value) || 0) } })} />
              </div>
              <div style={{ flex: 1 }}>
                <label>Fade de áudio — saída (s)</label>
                <input type="number" min={0} max={3} step={0.1} value={d.audio.fade_out_s}
                       onChange={(e) => p.upd({ audio: { ...d.audio, fade_out_s: Math.max(0, Number(e.target.value) || 0) } })} />
              </div>
            </div>
          </>
        ) : null}

        {p.tool === "enquadramento" ? (
          <>
            <h3>Enquadramento</h3>
            <label>Modo do corte inteiro</label>
            <div className="row wrap" style={{ marginBottom: 10 }}>
              {FRAMINGS.map(([id, rotulo]) => (
                <button key={id} className={d.framing === id ? "primary" : ""}
                        onClick={() => p.upd({ framing: id })}>
                  {rotulo}
                </button>
              ))}
            </div>
            <label>Overrides por trecho (tempos do relógio do corte)</label>
            <div className="sub" style={{ marginBottom: 6 }}>
              Force o foco num intervalo — o resto continua automático. Os blocos
              também aparecem na track “Enquadramento” da timeline.
            </div>
            {d.framing_segments.map((s, i) => (
              <div key={i} className="row" style={{ marginBottom: 6 }}>
                <input type="number" min={0} step={0.5} style={{ width: 74 }}
                       value={Math.round(srcToOut(segs, s.start_s) * 10) / 10}
                       title={`Origem: ${fmtSrc(s.start_s)}`}
                       onChange={(e) => {
                         const t = outToSrcSafe(segs, Number(e.target.value));
                         p.upd({ framing_segments: d.framing_segments.map((x, j) =>
                           j === i ? { ...x, start_s: t } : x) });
                       }} />
                <span className="sub">→</span>
                <input type="number" min={0} step={0.5} style={{ width: 74 }}
                       value={Math.round(srcToOut(segs, s.end_s) * 10) / 10}
                       title={`Origem: ${fmtSrc(s.end_s)}`}
                       onChange={(e) => {
                         const t = outToSrcSafe(segs, Number(e.target.value));
                         p.upd({ framing_segments: d.framing_segments.map((x, j) =>
                           j === i ? { ...x, end_s: t } : x) });
                       }} />
                <select value={s.mode} style={{ flex: 1 }}
                        onChange={(e) => p.upd({ framing_segments: d.framing_segments.map((x, j) =>
                          j === i ? { ...x, mode: e.target.value } : x) })}>
                  <option value="left">Foco à esquerda</option>
                  <option value="center">Foco no centro</option>
                  <option value="right">Foco à direita</option>
                </select>
                <button className="danger" onClick={() =>
                  p.upd({ framing_segments: d.framing_segments.filter((_, j) => j !== i) })}>×</button>
              </div>
            ))}
            <button onClick={() => {
              const a = p.sel != null && segs[p.sel] ? segs[p.sel].src_start
                : Math.max(env0, p.playhead - 3);
              const b = p.sel != null && segs[p.sel] ? segs[p.sel].src_end
                : Math.min(env1, p.playhead + 3);
              p.upd({ framing_segments: [...d.framing_segments,
                { start_s: Math.round(a * 10) / 10, end_s: Math.round(b * 10) / 10, mode: "left" }] });
            }}>
              + Adicionar {p.sel != null ? "no trecho selecionado" : "ao redor do cursor"}
            </button>
          </>
        ) : null}

        {p.tool === "punchin" ? (
          <>
            <h3>Punch-in</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              Zoom sutil que dá energia ao corte. O Dinâmico alterna o zoom a cada
              trecho da edição.
            </div>
            {([["off", "Desligado"], ["leve", "Leve — 105%"],
               ["dinamico", "Dinâmico — alterna 100/110%"]] as const).map(([id, rotulo]) => (
              <button key={id} className={d.punch_in === id ? "primary" : ""}
                      style={{ display: "block", width: "100%", marginBottom: 6 }}
                      onClick={() => p.upd({ punch_in: id })}>
                {rotulo}
              </button>
            ))}
          </>
        ) : null}

        {p.tool === "legenda" ? (
          <>
            <h3>Legenda — posição</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              Atalhos de posição vertical (a âncora fica fixa; o texto cresce para
              baixo sem pular). Clique na legenda no vídeo para selecioná-la.
            </div>
            <div className="row wrap">
              {([["topo", "Topo", 220], ["centro", "Centro", 880],
                 ["inferior", "Inferior", 1320]] as const).map(([id, rotulo, y]) => (
                <button key={id}
                        className={Number(d.caption_style?.anchor_top) === y ? "primary" : ""}
                        onClick={() => p.upd({ caption_style:
                          { ...(d.caption_style ?? {}), anchor_top: y } })}>
                  {rotulo}
                </button>
              ))}
              <button onClick={() => {
                const cs = { ...(d.caption_style ?? {}) };
                delete cs.anchor_top;
                p.upd({ caption_style: Object.keys(cs).length ? cs : null });
              }}>
                Posição padrão do estilo
              </button>
            </div>
          </>
        ) : null}

        {p.tool === "palavras" ? (
          <>
            <h3>Palavras da legenda</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              Clique numa palavra para corrigir o texto — só neste corte; a
              transcrição original não muda.
            </div>
            <div className="ed-words">
              {p.words.length === 0 ? (
                <span className="sub">Sem palavras no trecho mantido.</span>
              ) : (
                p.words.map((w) =>
                  p.editWord === w.idx ? (
                    <input key={w.idx} className="ed-word-input" autoFocus
                           defaultValue={d.word_overrides[String(w.idx)] ?? w.word}
                           onBlur={(e) => {
                             const novo = e.target.value.trim();
                             const m = { ...d.word_overrides };
                             if (!novo || novo === w.word) delete m[String(w.idx)];
                             else m[String(w.idx)] = novo;
                             p.upd({ word_overrides: m });
                             p.setEditWord(null);
                           }}
                           onKeyDown={(e) => {
                             if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                             if (e.key === "Escape") p.setEditWord(null);
                           }} />
                  ) : (
                    <button key={w.idx}
                            className={`ed-word${d.word_overrides[String(w.idx)] ? " fixed" : ""}`}
                            title={d.word_overrides[String(w.idx)]
                              ? `Original: “${w.word}”` : "Clique para corrigir"}
                            onClick={() => p.setEditWord(w.idx)}>
                      {d.word_overrides[String(w.idx)] ?? w.word}
                    </button>
                  ))
              )}
            </div>
          </>
        ) : null}

        {p.tool === "estilo" ? (
          <>
            <h3>Estilo da legenda</h3>
            <label>Preset</label>
            <select value={String(d.caption_style?.preset ?? "")}
                    onChange={(e) => {
                      const preset = e.target.value;
                      p.upd({ caption_style: preset
                        ? { ...(d.caption_style ?? {}), preset }
                        : null });
                    }}>
              <option value="">(padrão do kit / Karaokê Bold)</option>
              {p.presets.map((ps) => (
                <option key={ps.id} value={ps.id}>{ps.label}</option>
              ))}
            </select>
            <div className="sub" style={{ marginTop: 8 }}>
              O preview ao lado mostra o estilo aplicado no vídeo em tempo real.
            </div>
          </>
        ) : null}

        {p.tool === "kit" ? (
          <>
            <h3>Kit de Marca</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              O kit aplica o template (logo, moldura, fundo, textos) a ESTE corte —
              você vê o resultado no canvas imediatamente.
            </div>
            <select value={d.brand_kit_id ?? ""}
                    onChange={(e) => p.upd({ brand_kit_id: e.target.value || null })}>
              <option value="">(nenhum)</option>
              {p.kits.map((k) => (
                <option key={k.id} value={k.id}>{k.name}{k.is_default ? " · padrão" : ""}</option>
              ))}
            </select>
            {d.brand_kit_id ? (
              <button style={{ marginTop: 8 }} onClick={() => p.onOpenStudio(d.brand_kit_id!)}>
                Editar o kit no Estúdio (vale para todos os cortes que o usam)
              </button>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

// entrada numérica no relógio do corte → tempo de fonte (clamp no envelope)
function outToSrcSafe(segs: Draft["segments"], tOut: number): number {
  let acc = 0;
  for (const s of segs) {
    const dd = s.src_end - s.src_start;
    if (tOut < acc + dd) return Math.round((s.src_start + (tOut - acc)) * 100) / 100;
    acc += dd;
  }
  return segs[segs.length - 1]?.src_end ?? 0;
}
