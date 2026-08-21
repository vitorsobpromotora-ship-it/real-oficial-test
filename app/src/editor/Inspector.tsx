/**
 * Inspector contextual (Pontos 5, 9, 26): mostra SOMENTE os controles da
 * ferramenta selecionada. A seleção também acontece pelo objeto (timeline
 * seleciona trecho → Corte; clique na legenda → Legenda), no espírito do
 * CapCut: selecionou algo → edita aquilo.
 */
import { useEffect, useRef, useState } from "react";
import type {
  BrandKit, CaptionCards, CaptionPreset, Cut, TranscriptWord,
} from "../api/types";
import StylePicker from "./StylePicker";
import {
  fmtSrc, fmtT, srcToOut, type Draft, type InsertedWord, type WordEmphasis,
} from "./model";

// biblioteca de ênfases (Ponto 16) — rótulo e para que serve
export const ENFASES: { id: string; label: string; dica: string }[] = [
  { id: "pop", label: "Pop", dica: "Aumento leve — uso geral" },
  { id: "punch", label: "Punch", dica: "Entrada rápida e grande — frases fortes" },
  { id: "impact", label: "Impact", dica: "Escala + contorno reforçado" },
  { id: "fatality", label: "Fatality", dica: "Golpe: cresce, treme e muda de cor" },
  { id: "color_hit", label: "Color Hit", dica: "Só a cor muda por um instante" },
  { id: "shake", label: "Shake", dica: "Vibração curta" },
  { id: "highlight_box", label: "Highlight Box", dica: "Bloco atrás da palavra" },
  { id: "soft_lift", label: "Soft Lift", dica: "Movimento suave — conteúdo sério" },
  { id: "glow", label: "Glow", dica: "Brilho temporário" },
  { id: "outline_burst", label: "Outline Burst", dica: "Contorno cresce e volta" },
  { id: "flash", label: "Flash", dica: "Estouro de contraste" },
  { id: "bounce", label: "Bounce", dica: "Sobe e assenta" },
];

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
  words: TranscriptWord[]; // transcrição (fonte) — p/ restaurar excluídas
  captions: CaptionCards | null; // cartões resolvidos pelo motor
  outNow: number; // relógio de saída (sincronismo palavra ↔ playhead)
  selCard: number | null;
  onSeekOut(tOut: number): void;
  sel: number | null;
  selFr: number | null; // bloco de enquadramento selecionado na track
  playhead: number;
  onPauses(nivel: "leve" | "normal" | "agressivo"): void;
  onFrSplit(): void;
  safeArea: boolean;
  setSafeArea(v: boolean): void;
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
            {p.selFr != null ? (
              <button style={{ marginBottom: 8 }} onClick={p.onFrSplit}>
                ✂ Dividir o bloco selecionado no cursor
              </button>
            ) : null}
            {d.framing_segments.map((s, i) => (
              <div key={i} className={`row${p.selFr === i ? " insp-frsel" : ""}`}
                   style={{ marginBottom: 6 }}
                   data-testid={`fr-row-${i}`}>
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
          <LegendaPanel draft={d} upd={p.upd} presets={p.presets}
                        efetivo={p.captions?.style ?? {}}
                        safeArea={p.safeArea} setSafeArea={p.setSafeArea} />
        ) : null}

        {p.tool === "palavras" ? (
          <WordsPanel draft={d} upd={p.upd} words={p.words} captions={p.captions}
                      outNow={p.outNow} selCard={p.selCard} onSeekOut={p.onSeekOut} />
        ) : null}

        {p.tool === "estilo" ? (
          <>
            <h3>Estilo da legenda</h3>
            <div className="sub" style={{ marginBottom: 8 }}>
              Clique num card para aplicar — o preview ao lado mostra o estilo
              no vídeo em tempo real.
            </div>
            <StylePicker
              presets={p.presets}
              valor={String(d.caption_style?.preset ?? "")}
              onChange={(preset) => {
                const cs = { ...(d.caption_style ?? {}) };
                if (preset) cs.preset = preset;
                else delete cs.preset;
                p.upd({ caption_style: Object.keys(cs).length ? cs : null });
              }}
            />
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

// ---------- Legenda: posição livre, safe area e cores (Pontos 21–24) ----------
const CORES: [string, string][] = [
  ["text_color", "Cor principal"],
  ["highlight_color", "Palavra ativa"],
  ["outline_color", "Contorno"],
  ["back_color", "Fundo (quando o estilo usa caixa)"],
  ["shadow_color", "Sombra"],
];

function LegendaPanel({ draft, upd, efetivo, safeArea, setSafeArea }: {
  draft: Draft;
  upd(patch: Partial<Draft>): void;
  presets: CaptionPreset[];
  efetivo: Record<string, unknown>;
  safeArea: boolean;
  setSafeArea(v: boolean): void;
}) {
  const cs = (draft.caption_style ?? {}) as Record<string, unknown>;
  // valor mostrado: override do corte › estilo efetivo (kit/preset) — Ponto 24
  const val = (k: string, padrao: unknown) => cs[k] ?? efetivo[k] ?? padrao;
  const set = (patch: Record<string, unknown>) => {
    const novo = { ...cs, ...patch };
    for (const [k, v] of Object.entries(patch)) if (v === undefined) delete novo[k];
    upd({ caption_style: Object.keys(novo).length ? novo : null });
  };
  const posX = Number(val("pos_x", 0.5));
  const posY = cs.pos_y != null ? Number(cs.pos_y)
    : Number(val("anchor_top", 1280)) / 1920;
  const largura = Number(val("max_width_pct", 88));

  return (
    <>
      <h3>Legenda — posição</h3>
      <div className="sub" style={{ marginBottom: 8 }}>
        Arraste a legenda direto no vídeo, ou ajuste aqui. A posição é
        proporcional: o render 1080×1920 fica igual ao que você vê.
      </div>
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>Posição X ({(posX * 100).toFixed(0)}%)</label>
          <input type="range" min={0} max={1} step={0.005} value={posX}
                 data-testid="cap-x"
                 onChange={(e) => set({ pos_x: Number(e.target.value) })} />
        </div>
        <div style={{ flex: 1 }}>
          <label>Posição Y ({(posY * 100).toFixed(0)}%)</label>
          <input type="range" min={0} max={1} step={0.005} value={posY}
                 data-testid="cap-y"
                 onChange={(e) => set({ pos_y: Number(e.target.value) })} />
        </div>
      </div>
      <label>Largura máxima ({largura.toFixed(0)}%)</label>
      <input type="range" min={40} max={100} step={1} value={largura}
             data-testid="cap-w"
             onChange={(e) => set({ max_width_pct: Number(e.target.value) })} />
      <label>Alinhamento</label>
      <div className="row wrap" style={{ marginBottom: 10 }}>
        {([["left", "Esquerda"], ["center", "Centro"], ["right", "Direita"]] as const)
          .map(([id, rotulo]) => (
            <button key={id} className={val("align", "center") === id ? "primary" : ""}
                    onClick={() => set({ align: id })}>{rotulo}</button>
          ))}
      </div>
      <label>Atalhos verticais</label>
      <div className="row wrap">
        {([["Topo", 0.12], ["Centro", 0.46], ["Inferior", 0.68]] as const).map(([r, y]) => (
          <button key={r} className={Math.abs(posY - y) < 0.005 ? "primary" : ""}
                  onClick={() => set({ pos_y: y })}>{r}</button>
        ))}
        <button onClick={() => set({ pos_x: undefined, pos_y: undefined,
                                     max_width_pct: undefined, align: undefined })}>
          Posição padrão do estilo
        </button>
      </div>
      <label className="ed-check" style={{ marginTop: 10 }}>
        <input type="checkbox" checked={safeArea} data-testid="cap-safe"
               onChange={(e) => setSafeArea(e.target.checked)} />
        Mostrar área segura (evita botões e descrição das plataformas)
      </label>

      <h3 style={{ marginTop: 18 }}>Cores</h3>
      <div className="sub" style={{ marginBottom: 8 }}>
        Estas cores valem só para este corte e vencem o Kit e o preset.
      </div>
      <div className="cor-grid">
        {CORES.map(([k, rotulo]) => {
          const atual = String(val(k, k === "text_color" ? "#FFFFFF" : "#000000"));
          return (
            <div key={k} className="cor-item">
              <label>{rotulo}</label>
              <div className="cor-row">
                <input type="color" value={atual} data-testid={`cor-${k}`}
                       onChange={(e) => set({ [k]: e.target.value.toUpperCase() })} />
                <input type="text" value={atual} spellCheck={false}
                       onChange={(e) => {
                         const v = e.target.value.trim().toUpperCase();
                         if (/^#[0-9A-F]{6}$/.test(v)) set({ [k]: v });
                       }} />
              </div>
            </div>
          );
        })}
      </div>
      <button style={{ marginTop: 10 }} data-testid="cor-reset"
              onClick={() => set(Object.fromEntries(CORES.map(([k]) => [k, undefined])))}>
        Restaurar cores padrão
      </button>
    </>
  );
}

// ---------- Palavras (Pontos 13, 27, 28): cartões do motor + 4 operações ----------
interface Chip {
  key: string;
  label: string;
  kind: "word" | "ins";
  idx?: number;
  insId?: string;
  start?: number;
  end?: number;
}

function WordsPanel({ draft, upd, words, captions, outNow, selCard, onSeekOut }: {
  draft: Draft;
  upd(patch: Partial<Draft>): void;
  words: TranscriptWord[];
  captions: CaptionCards | null;
  outNow: number;
  selCard: number | null;
  onSeekOut(t: number): void;
}) {
  const [menu, setMenu] = useState<Chip | null>(null);
  const [editKey, setEditKey] = useState<string | null>(null);
  const [ins, setIns] = useState<{ anchorIdx: number; placement: "before" | "after" } | null>(null);
  const [enfaseAberta, setEnfaseAberta] = useState(false);

  const rotuloEnf = (id: string) => ENFASES.find((e) => e.id === id)?.label ?? id;

  /** Ênfase que cobre este chip, se houver. */
  function enfDe(chip: Chip): WordEmphasis | undefined {
    return draft.word_emphasis.find((e) =>
      (chip.idx != null && (e.idx ?? []).includes(chip.idx))
      || (chip.insId != null && (e.ins_ids ?? []).includes(chip.insId)));
  }

  function semEsteChip(chip: Chip): WordEmphasis[] {
    return draft.word_emphasis
      .map((e) => ({
        ...e,
        idx: (e.idx ?? []).filter((i) => i !== chip.idx),
        ins_ids: (e.ins_ids ?? []).filter((i) => i !== chip.insId),
      }))
      .filter((e) => (e.idx?.length ?? 0) + (e.ins_ids?.length ?? 0) > 0);
  }

  function aplicarEnfase(chip: Chip, effect: string) {
    const atual = enfDe(chip);
    const base = semEsteChip(chip);
    const nova: WordEmphasis = {
      effect,
      intensity: atual?.intensity ?? "normal",
      ...(atual?.color ? { color: atual.color } : {}),
      ...(chip.idx != null ? { idx: [chip.idx] } : {}),
      ...(chip.insId != null ? { ins_ids: [chip.insId] } : {}),
    };
    upd({ word_emphasis: [...base, nova] });
  }

  function mudarEnfase(chip: Chip, patch: Partial<WordEmphasis>) {
    const atual = enfDe(chip);
    if (!atual) return;
    upd({ word_emphasis: [...semEsteChip(chip), { ...atual, ...patch,
      ...(chip.idx != null ? { idx: [chip.idx] } : {}),
      ...(chip.insId != null ? { ins_ids: [chip.insId] } : {}) }] });
  }

  function removerEnfase(chip: Chip) {
    upd({ word_emphasis: semEsteChip(chip) });
  }
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    if (selCard != null) {
      cardRefs.current[selCard]?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    }
  }, [selCard]);

  const cards = captions?.cards ?? [];
  if (!cards.length) {
    return (
      <>
        <h3>Palavras da legenda</h3>
        <div className="sub">Sem legendas neste corte (fonte sem transcrição no trecho).</div>
      </>
    );
  }

  function chipsDe(card: CaptionCards["cards"][number]): Chip[] {
    const noServidor = new Set(card.words.filter((w) => w.ins_id).map((w) => w.ins_id));
    const out: Chip[] = [];
    for (const w of card.words) {
      if (w.idx != null && draft.word_deleted.includes(w.idx)) continue; // excluída agora
      if (w.ins_id) {
        const viva = draft.word_inserted.find((x) => x.id === w.ins_id);
        if (!viva) continue; // inserção removida localmente
        out.push({ key: `s${w.ins_id}`, label: viva.text, kind: "ins", insId: w.ins_id,
                   start: w.start_s, end: w.end_s });
        continue;
      }
      for (const iw of draft.word_inserted) {
        if (iw.anchor_idx === w.idx && iw.placement === "before" && !noServidor.has(iw.id)) {
          out.push({ key: `s${iw.id}`, label: iw.text, kind: "ins", insId: iw.id });
        }
      }
      out.push({ key: `i${w.idx}`, label: draft.word_overrides[String(w.idx)] ?? w.word,
                 kind: "word", idx: w.idx!, start: w.start_s, end: w.end_s });
      for (const iw of draft.word_inserted) {
        if (iw.anchor_idx === w.idx && iw.placement === "after" && !noServidor.has(iw.id)) {
          out.push({ key: `s${iw.id}`, label: iw.text, kind: "ins", insId: iw.id });
        }
      }
    }
    return out;
  }

  function excluir(chip: Chip) {
    if (chip.kind === "word" && chip.idx != null) {
      upd({ word_deleted: [...draft.word_deleted, chip.idx] });
    } else if (chip.insId) {
      upd({ word_inserted: draft.word_inserted.filter((x) => x.id !== chip.insId) });
    }
    setMenu(null);
  }

  function gravarTexto(chip: Chip, texto: string) {
    const novo = texto.trim();
    if (chip.kind === "word" && chip.idx != null) {
      const m = { ...draft.word_overrides };
      const original = words.find((w) => w.idx === chip.idx)?.word;
      if (!novo || novo === original) delete m[String(chip.idx)];
      else m[String(chip.idx)] = novo;
      upd({ word_overrides: m });
    } else if (chip.insId) {
      upd({ word_inserted: draft.word_inserted.map((x) =>
        x.id === chip.insId ? { ...x, text: novo || x.text } : x) });
    }
    setEditKey(null);
    setMenu(null);
  }

  function inserir(texto: string) {
    if (!ins) return;
    const novo = texto.trim();
    if (novo) {
      const nova: InsertedWord = {
        id: `w${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
        anchor_idx: ins.anchorIdx, placement: ins.placement, text: novo,
      };
      upd({ word_inserted: [...draft.word_inserted, nova] });
    }
    setIns(null);
    setMenu(null);
  }

  const excluidas = draft.word_deleted
    .map((idx) => ({ idx, word: words.find((w) => w.idx === idx)?.word ?? `#${idx}` }));

  return (
    <>
      <h3>Palavras da legenda</h3>
      <div className="sub" style={{ marginBottom: 8 }}>
        Clique numa palavra: substituir, excluir ou inserir antes/depois — só na
        legenda deste corte; a transcrição original não muda. A reprodução destaca
        a palavra atual.
      </div>
      {cards.map((card, ci) => {
        const ativo = outNow >= card.start && outNow <= card.end;
        return (
          <div key={ci} ref={(el) => { cardRefs.current[ci] = el; }}
               className={`wp-card${ativo ? " cur" : ""}${selCard === ci ? " sel" : ""}`}
               data-testid={`wp-card-${ci}`}>
            <button className="wp-cardhead" onClick={() => onSeekOut(card.start + 0.01)}
                    title="Levar o cursor até este cartão">
              cartão {ci + 1} · {fmtT(card.start)}
            </button>
            <div className="ed-words">
              {chipsDe(card).map((chip) =>
                editKey === chip.key ? (
                  <input key={chip.key} className="ed-word-input" autoFocus
                         defaultValue={chip.label}
                         onBlur={(e) => gravarTexto(chip, e.target.value)}
                         onKeyDown={(e) => {
                           if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                           if (e.key === "Escape") setEditKey(null);
                         }} />
                ) : (
                  <button key={chip.key}
                          data-testid={`wp-${chip.key}`}
                          className={"ed-word"
                            + (chip.kind === "ins" ? " ins" : "")
                            + (chip.kind === "word" && draft.word_overrides[String(chip.idx)]
                              ? " fixed" : "")
                            + (chip.start != null && outNow >= chip.start && outNow < (chip.end ?? 0)
                              ? " cur" : "")
                            + (enfDe(chip) ? " enf" : "")}
                          onClick={() => {
                            setMenu(menu?.key === chip.key ? null : chip);
                            setIns(null);
                            setEnfaseAberta(false);
                            if (chip.start != null) onSeekOut(chip.start + 0.01);
                          }}>
                    {chip.label}
                  </button>
                ))}
            </div>
            {menu && chipsDe(card).some((c) => c.key === menu.key) ? (
              <div className="wp-menu" data-testid="wp-menu">
                {ins ? (
                  <input className="ed-word-input" autoFocus
                         placeholder={`nova palavra ${ins.placement === "before" ? "antes" : "depois"}…`}
                         onBlur={(e) => inserir(e.target.value)}
                         onKeyDown={(e) => {
                           if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                           if (e.key === "Escape") setIns(null);
                         }} />
                ) : (
                  <>
                    <button onClick={() => setEditKey(menu.key)}>✏ Substituir</button>
                    {menu.kind === "word" ? (
                      <>
                        <button onClick={() => setIns({ anchorIdx: menu.idx!, placement: "before" })}>
                          + antes
                        </button>
                        <button onClick={() => setIns({ anchorIdx: menu.idx!, placement: "after" })}>
                          + depois
                        </button>
                      </>
                    ) : null}
                    <button data-testid="wp-enfase"
                            onClick={() => setEnfaseAberta(!enfaseAberta)}>
                      ✨ Ênfase{enfDe(menu) ? ` · ${rotuloEnf(enfDe(menu)!.effect)}` : ""}
                    </button>
                    <button className="danger" onClick={() => excluir(menu)}>
                      {menu.kind === "ins" ? "Remover inserção" : "Excluir"}
                    </button>
                  </>
                )}
                {enfaseAberta && menu ? (
                  <div className="wp-enf" data-testid="wp-enf-painel">
                    <div className="wp-enfgrid">
                      {ENFASES.map((e) => (
                        <button key={e.id} title={e.dica}
                                data-testid={`enf-${e.id}`}
                                className={enfDe(menu)?.effect === e.id ? "primary" : ""}
                                onClick={() => aplicarEnfase(menu, e.id)}>
                          {e.label}
                        </button>
                      ))}
                    </div>
                    {enfDe(menu) ? (
                      <>
                        <div className="row wrap" style={{ marginTop: 8 }}>
                          {(["suave", "normal", "forte"] as const).map((n) => (
                            <button key={n} data-testid={`enf-int-${n}`}
                                    className={(enfDe(menu)!.intensity ?? "normal") === n
                                      ? "primary" : ""}
                                    onClick={() => mudarEnfase(menu, { intensity: n })}>
                              {n === "suave" ? "Suave" : n === "normal" ? "Normal" : "Forte"}
                            </button>
                          ))}
                        </div>
                        <div className="cor-row" style={{ marginTop: 8 }}>
                          <input type="color" data-testid="enf-cor"
                                 value={enfDe(menu)!.color ?? "#FF2D2D"}
                                 onChange={(ev) => mudarEnfase(menu,
                                   { color: ev.target.value.toUpperCase() })} />
                          <span className="sub">cor desta palavra (vence tudo)</span>
                          <button className="danger" data-testid="enf-remover"
                                  onClick={() => removerEnfase(menu)}>Remover</button>
                        </div>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
      {excluidas.length ? (
        <div style={{ marginTop: 10 }}>
          <label>Palavras excluídas (clique para restaurar)</label>
          <div className="ed-words">
            {excluidas.map((w) => (
              <button key={w.idx} className="ed-word del" data-testid={`wp-del-${w.idx}`}
                      onClick={() => upd({ word_deleted:
                        draft.word_deleted.filter((i) => i !== w.idx) })}>
                {w.word}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </>
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
