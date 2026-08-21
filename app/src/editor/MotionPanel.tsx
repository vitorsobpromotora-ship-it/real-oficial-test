/**
 * Painel Motion (v4 FASE C) — edição das EffectInstances do Motion Manifest.
 *
 * O efeito nasce no editor de palavras (menu da palavra → ✦ Motion) ou pelo
 * clique num bloco da track Motion; aqui ele é ajustado: preset, intensidade,
 * janela, ativo/inativo (A/B sem excluir), variação de seed e exclusão.
 * Tudo passa pelo Draft → undo/redo e autosave como qualquer edição visual.
 */
import { useState } from "react";
import { post } from "../api/client";
import type { CaptionCards } from "../api/types";
import { fmtT, type Draft } from "./model";
import MotionGallery from "./MotionGallery";
import {
  expandComposite, hash32, manifestVazio, novoId, seedDe,
  type CalloutPreset, type CompositePreset, type EffectInstance,
  type TextPreset, type VideoPreset,
} from "./motion";

export interface Suggestion {
  start: number;
  end: number;
  target_words: number[];
  semantic_role: string;
  impact_score: number;
  suggested_preset: string;
  kind: "text_emphasis" | "video_fx" | "composite";
  intensity: "suave" | "normal" | "forte";
  reason: string;
  word: string;
}

export const ESTILOS_EDITORIAIS: [string, string][] = [
  ["limpa", "Limpa"], ["dinamica", "Dinâmica"],
  ["batalha", "Batalha"], ["agressiva", "Agressiva"],
];
export const DENSIDADES: [string, string][] = [
  ["desativado", "Desativado"], ["baixa", "Baixa"],
  ["balanceada", "Balanceada"], ["alta", "Alta"],
];

export const INTENS: [string, string][] = [
  ["suave", "Suave"], ["normal", "Normal"], ["forte", "Forte"],
];

export function rotuloDoEfeito(
  e: EffectInstance, presets: { id: string; label: string }[],
): string {
  const nome = e.type === "broll"
    ? (String(e.params?.mode ?? "overlay") === "fullscreen"
      ? "B-roll (tela cheia)" : "B-roll")
    : presets.find((p) => p.id === e.preset)?.label ?? e.preset;
  const inten = typeof e.intensity === "string" && e.intensity !== "normal"
    ? ` — ${INTENS.find(([i]) => i === e.intensity)?.[1] ?? e.intensity}` : "";
  return `${nome}${inten}`;
}

interface Props {
  draft: Draft;
  upd(patch: Partial<Draft>): void;
  presets: TextPreset[];
  videoPresets: VideoPreset[];
  calloutPresets: CalloutPreset[];
  compositePresets: CompositePreset[];
  cutId: string;
  outNow: number; // playhead em tempo de SAÍDA — onde nasce um FX novo
  selFx: string | null;
  setSelFx(id: string | null): void;
  captions: CaptionCards | null;
  onSeekOut(t: number): void;
}

export default function MotionPanel(p: Props) {
  const [estilo, setEstilo] = useState("batalha");
  const [densidade, setDensidade] = useState("balanceada");
  const [sugestoes, setSugestoes] = useState<Suggestion[] | null>(null);
  const [sugerindo, setSugerindo] = useState(false);
  const effects = p.draft.motion?.effects ?? [];
  const sel = effects.find((e) => e.id === p.selFx) ?? null;
  const catalogoDe = (e: EffectInstance) =>
    e.type === "video_fx" ? p.videoPresets
      : e.type === "text_callout" ? p.calloutPresets : p.presets;

  /** Cria um efeito de VÍDEO no cursor (Entrega 17: track FX). */
  function criarVideoFx() {
    const id = novoId();
    const inicio = Math.max(0, Math.round(p.outNow * 100) / 100);
    const eff: EffectInstance = {
      id, type: "video_fx", preset: "punch_zoom", target: { kind: "video" },
      start: inicio, end: Math.round((inicio + 0.6) * 100) / 100,
      intensity: "normal", enabled: true, seed: seedDe(id),
    };
    const m = p.draft.motion ?? manifestVazio();
    p.upd({ motion: { ...m, effects: [...m.effects, eff] } });
    p.setSelFx(id);
  }

  function mudar(id: string, patch: Partial<EffectInstance>) {
    const m = p.draft.motion ?? manifestVazio();
    p.upd({ motion: { ...m,
      effects: m.effects.map((e) => (e.id === id ? { ...e, ...patch } : e)) } });
  }
  function excluir(id: string) {
    const m = p.draft.motion ?? manifestVazio();
    p.upd({ motion: { ...m, effects: m.effects.filter((e) => e.id !== id) } });
    if (p.selFx === id) p.setSelFx(null);
  }
  function excluirGrupo(gid: string) {
    const m = p.draft.motion ?? manifestVazio();
    p.upd({ motion: { ...m, effects: m.effects.filter((e) => e.group !== gid) } });
    p.setSelFx(null);
  }

  const FUNDOS: [string, string][] = [
    ["none", "Vídeo normal"], ["darken", "Escurecido"],
    ["blur", "Desfocado"], ["black", "Tela preta"],
  ];

  function mudarParam(id: string, chave: string, valor: unknown) {
    const e = effects.find((x) => x.id === id);
    if (!e) return;
    mudar(id, { params: { ...(e.params ?? {}), [chave]: valor } });
  }

  async function sugerir() {
    setSugerindo(true);
    try {
      const r = await post<{ suggestions: Suggestion[] }>(
        `/api/v1/cuts/${p.cutId}/motion/suggest`,
        { style: estilo, density: densidade, seed: seedDe(p.cutId) });
      setSugestoes(r.suggestions);
    } finally {
      setSugerindo(false);
    }
  }

  /** Expande UMA sugestão em EffectInstances comuns (origin "auto"). */
  function efeitosDe(su: Suggestion): EffectInstance[] {
    const marca = { origin: "auto", reason: su.reason };
    if (su.kind === "composite") {
      const preset = p.compositePresets.find((c) => c.id === su.suggested_preset);
      if (!preset) return [];
      return expandComposite(preset, {
        tHit: su.start, durWord: Math.max(0.2, su.end - su.start - 0.25),
        target: { kind: "words", idx: su.target_words },
        intensity: su.intensity, seedBase: seedDe(novoId()),
      }).map((e) => ({ ...e, ...marca }));
    }
    const id = novoId();
    return [{
      id, type: su.kind, preset: su.suggested_preset,
      target: su.kind === "video_fx" ? { kind: "video" }
        : { kind: "words", idx: su.target_words },
      start: su.start, end: su.end, intensity: su.intensity,
      enabled: true, seed: seedDe(id), ...marca,
    }];
  }

  function aplicarSugestoes(lista: Suggestion[]) {
    const man = p.draft.motion ?? manifestVazio();
    const ocupados = new Set(man.effects
      .filter((e) => e.type === "text_emphasis")
      .flatMap((e) => e.target.idx ?? []));
    const novos = lista
      .filter((su) => su.kind === "video_fx"
        || !su.target_words.some((i) => ocupados.has(i)))
      .flatMap(efeitosDe);
    if (!novos.length) return;
    p.upd({ motion: { ...man, effects: [...man.effects, ...novos] } });
    setSugestoes(null);
  }

  function alvoLegivel(e: EffectInstance): string {
    if (e.type === "broll") return "mídia da biblioteca";
    if (e.target.kind === "video") return "cena inteira";
    const palavras = (p.captions?.cards ?? []).flatMap((c) => c.words);
    const nomes: string[] = [];
    for (const i of e.target.idx ?? []) {
      const w = palavras.find((x) => x.idx === i);
      if (w) nomes.push(w.word);
    }
    for (const ins of e.target.ins_ids ?? []) {
      const w = palavras.find((x) => x.ins_id === ins);
      if (w) nomes.push(w.word);
    }
    return nomes.length ? `“${nomes.join(" ")}”` : "palavra";
  }

  const smart = (
    <div className="mo-smart" data-testid="mo-smart">
      <label>Smart Motion — sugestões automáticas</label>
      <div className="row">
        <select value={estilo} data-testid="mo-estilo"
                onChange={(e) => setEstilo(e.target.value)}>
          {ESTILOS_EDITORIAIS.map(([id, rotulo]) => (
            <option key={id} value={id}>{rotulo}</option>
          ))}
        </select>
        <select value={densidade} data-testid="mo-densidade"
                onChange={(e) => setDensidade(e.target.value)}>
          {DENSIDADES.map(([id, rotulo]) => (
            <option key={id} value={id}>{rotulo}</option>
          ))}
        </select>
        <button data-testid="mo-sugerir" disabled={sugerindo}
                onClick={() => void sugerir()}>
          {sugerindo ? "Analisando…" : "✨ Sugerir"}
        </button>
      </div>
      {sugestoes !== null ? (
        <div className="mo-sug-lista" data-testid="mo-sug-lista">
          {!sugestoes.length ? (
            <div className="sub">Nada a sugerir com este estilo/densidade.</div>
          ) : (
            <>
              {sugestoes.map((su, i) => (
                <div key={i} className="mo-sug" data-testid={`mo-sug-${i}`}>
                  <b>{su.semantic_role === "fatality" ? "🔥" : "✨"}{" "}
                    “{su.word}” · {su.suggested_preset}</b>
                  <span className="sub">{su.reason}</span>
                </div>
              ))}
              <div className="row" style={{ marginTop: 6 }}>
                <button className="primary" data-testid="mo-aplicar-sug"
                        onClick={() => aplicarSugestoes(sugestoes)}>
                  Aplicar {sugestoes.length} sugestão(ões)
                </button>
                <button onClick={() => setSugestoes(null)}>Descartar</button>
              </div>
              <div className="sub">
                Tudo entra como efeito comum: editável, desativável e com
                Ctrl+Z. Nada é definitivo.
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );


  if (!effects.length) {
    return (
      <>
        <h3>Motion</h3>
        <div className="sub">
          Nenhum efeito de motion neste corte ainda.
          <br /><br />
          Texto: abra <b>Palavras</b>, clique na palavra que merece o destaque
          e escolha <b>✦ Motion</b>.
          <br />
          Vídeo: posicione o cursor e crie um efeito de cena abaixo — zoom,
          shake, flash… O bloco aparece na track FX e é exatamente o que o
          render final aplica.
        </div>
        {smart}
        <div className="row" style={{ marginTop: 12 }}>
          <button data-testid="mo-add-fx" onClick={criarVideoFx}>
            ⚡ Efeito de vídeo no cursor
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <h3>Motion</h3>
      {smart}
      <div className="row" style={{ marginBottom: 10 }}>
        <button data-testid="mo-add-fx" onClick={criarVideoFx}>
          ⚡ Efeito de vídeo no cursor
        </button>
      </div>
      <div className="mo-lista" data-testid="mo-lista">
        {effects.map((e) => (
          <button key={e.id}
                  className={`mo-item${p.selFx === e.id ? " on" : ""}${e.enabled === false ? " off" : ""}`}
                  data-testid={`mo-item-${e.id}`}
                  onClick={() => { p.setSelFx(e.id); p.onSeekOut(e.start + 0.01); }}>
            <b>{e.type === "video_fx" ? "⚡" : e.type === "text_callout" ? "🗯" : "✦"}{" "}
              {rotuloDoEfeito(e, catalogoDe(e))}</b>
            <span className="sub">
              {alvoLegivel(e)} · {fmtT(e.start)} → {fmtT(e.end)}
              {e.origin === "auto" ? " · auto" : ""}
              {e.enabled === false ? " · desativado" : ""}
            </span>
          </button>
        ))}
      </div>

      {sel ? (
        <div className="mo-editor" data-testid="mo-editor">
          <label>{sel.type === "video_fx" ? "Efeito de vídeo" : "Animação"}</label>
          <select value={sel.preset} data-testid="mo-preset"
                  onChange={(ev) => mudar(sel.id, { preset: ev.target.value })}>
            {[...new Set(catalogoDe(sel).map((pr) => pr.categoria))].map((cat) => (
              <optgroup key={cat} label={cat}>
                {catalogoDe(sel).filter((pr) => pr.categoria === cat).map((pr) => (
                  <option key={pr.id} value={pr.id}>{pr.label}</option>
                ))}
              </optgroup>
            ))}
            {!catalogoDe(sel).some((pr) => pr.id === sel.preset) ? (
              <option value={sel.preset}>{sel.preset}</option>
            ) : null}
          </select>
          <div className="sub" style={{ marginTop: 2 }}>
            {catalogoDe(sel).find((pr) => pr.id === sel.preset)?.descricao ?? ""}
          </div>
          {sel.type === "text_emphasis" ? (
            <MotionGallery presets={p.presets} atual={sel.preset}
                           onAplicar={(pid) => mudar(sel.id, { preset: pid })} />
          ) : null}

          <label style={{ marginTop: 10 }}>Intensidade</label>
          <div className="row">
            {INTENS.map(([id, rotulo]) => (
              <button key={id} data-testid={`mo-int-${id}`}
                      className={(sel.intensity ?? "normal") === id ? "primary" : ""}
                      onClick={() => mudar(sel.id, { intensity: id as "suave" })}>
                {rotulo}
              </button>
            ))}
          </div>

          <div className="row" style={{ marginTop: 10 }}>
            <div>
              <label>Início (s)</label>
              <input type="number" step={0.05} min={0} value={sel.start}
                     data-testid="mo-start" className="ed-word-input"
                     onChange={(ev) => {
                       const v = Number(ev.target.value);
                       if (Number.isFinite(v) && v >= 0 && v < sel.end) {
                         mudar(sel.id, { start: v });
                       }
                     }} />
            </div>
            <div>
              <label>Fim (s)</label>
              <input type="number" step={0.05} min={0.05} value={sel.end}
                     data-testid="mo-end" className="ed-word-input"
                     onChange={(ev) => {
                       const v = Number(ev.target.value);
                       if (Number.isFinite(v) && v > sel.start) {
                         mudar(sel.id, { end: v });
                       }
                     }} />
            </div>
          </div>

          {sel.type === "broll" ? (
            <div data-testid="mo-broll-extra">
              <label style={{ marginTop: 10 }}>Modo</label>
              <select data-testid="mo-br-mode"
                      value={String(sel.params?.mode ?? "overlay")}
                      onChange={(ev) => mudarParam(sel.id, "mode", ev.target.value)}>
                <option value="overlay">Sobrepor (caixa)</option>
                <option value="fullscreen">Tela cheia (áudio principal continua)</option>
              </select>
              {String(sel.params?.mode ?? "overlay") === "overlay" ? (
                <div className="row" style={{ marginTop: 8 }}>
                  <div style={{ flex: 1 }}>
                    <label>X</label>
                    <input type="range" min={0.1} max={0.9} step={0.01}
                           data-testid="mo-br-x" style={{ width: "100%" }}
                           value={Number(sel.params?.x ?? 0.5)}
                           onChange={(ev) => mudarParam(sel.id, "x",
                             Number(ev.target.value))} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>Y</label>
                    <input type="range" min={0.05} max={0.9} step={0.01}
                           data-testid="mo-br-y" style={{ width: "100%" }}
                           value={Number(sel.params?.y ?? 0.28)}
                           onChange={(ev) => mudarParam(sel.id, "y",
                             Number(ev.target.value))} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>Largura</label>
                    <input type="range" min={0.2} max={1} step={0.01}
                           data-testid="mo-br-w" style={{ width: "100%" }}
                           value={Number(sel.params?.w ?? 0.62)}
                           onChange={(ev) => mudarParam(sel.id, "w",
                             Number(ev.target.value))} />
                  </div>
                </div>
              ) : null}
              <div className="row" style={{ marginTop: 8 }}>
                <label>Transição</label>
                <select data-testid="mo-br-tr"
                        value={String(sel.params?.transition ?? "fade")}
                        onChange={(ev) => mudarParam(sel.id, "transition",
                          ev.target.value)}>
                  <option value="cut">Corte seco</option>
                  <option value="fade">Fade</option>
                </select>
                <label className="row" style={{ gap: 6 }}>
                  <input type="checkbox" data-testid="mo-br-loop"
                         checked={Boolean(sel.params?.loop)}
                         onChange={(ev) => mudarParam(sel.id, "loop",
                           ev.target.checked)} />
                  Loop
                </label>
              </div>
            </div>
          ) : null}

          {sel.type === "text_callout" ? (
            <div data-testid="mo-callout-extra">
              <label style={{ marginTop: 10 }}>Fundo da cena</label>
              <select data-testid="mo-bg"
                      value={String(sel.params?.bg
                        ?? p.calloutPresets.find((c) => c.id === sel.preset)?.bg
                        ?? "none")}
                      onChange={(ev) => mudarParam(sel.id, "bg", ev.target.value)}>
                {FUNDOS.map(([id, rotulo]) => (
                  <option key={id} value={id}>{rotulo}</option>
                ))}
              </select>
              <div className="row" style={{ marginTop: 8 }}>
                <div style={{ flex: 1 }}>
                  <label>Posição X</label>
                  <input type="range" min={0.1} max={0.9} step={0.01}
                         data-testid="mo-pos-x" style={{ width: "100%" }}
                         value={Number(sel.params?.pos_x ?? 0.5)}
                         onChange={(ev) => mudarParam(sel.id, "pos_x",
                           Number(ev.target.value))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label>Posição Y</label>
                  <input type="range" min={0.1} max={0.9} step={0.01}
                         data-testid="mo-pos-y" style={{ width: "100%" }}
                         value={Number(sel.params?.pos_y ?? 0.5)}
                         onChange={(ev) => mudarParam(sel.id, "pos_y",
                           Number(ev.target.value))} />
                </div>
              </div>
              <div className="sub" style={{ marginTop: 4 }}>
                Também dá para arrastar o destaque direto no vídeo.
              </div>
            </div>
          ) : null}

          <div className="row" style={{ marginTop: 10 }}>
            <label className="row" style={{ gap: 6 }}>
              <input type="checkbox" checked={sel.enabled !== false}
                     data-testid="mo-enabled"
                     onChange={(ev) => mudar(sel.id, { enabled: ev.target.checked })} />
              Ativo
            </label>
            <button data-testid="mo-variacao"
                    title="Troca a semente do movimento — outra variação, igualmente reproduzível"
                    onClick={() => mudar(sel.id,
                      { seed: hash32(((sel.seed ?? 1) + 1) >>> 0) })}>
              🎲 Nova variação
            </button>
            <button data-testid="mo-duplicar" title="Duplica logo à frente"
                    onClick={() => {
                      const id2 = novoId();
                      const dur = sel.end - sel.start;
                      const m = p.draft.motion ?? manifestVazio();
                      p.upd({ motion: { ...m, effects: [...m.effects,
                        { ...sel, id: id2, seed: seedDe(id2),
                          start: Math.round((sel.end + 0.05) * 100) / 100,
                          end: Math.round((sel.end + 0.05 + dur) * 100) / 100 }] } });
                      p.setSelFx(id2);
                    }}>
              ⧉ Duplicar
            </button>
            <button className="danger right" data-testid="mo-excluir"
                    onClick={() => excluir(sel.id)}>
              Excluir efeito
            </button>
          </div>
          {sel.origin === "auto" && sel.reason ? (
            <div className="insp-sel" style={{ marginTop: 10 }}
                 data-testid="mo-reason">
              💡 Por que este efeito: {String(sel.reason)}
            </div>
          ) : null}

          {sel.group ? (
            <div className="insp-sel" style={{ marginTop: 10 }} data-testid="mo-grupo">
              Parte da composição <b>{String(sel.group_label ?? "")}</b> — as
              outras partes (zoom, cena, câmera) estão nas tracks Motion e FX.
              <div className="row" style={{ marginTop: 6 }}>
                <button className="danger" data-testid="mo-excluir-grupo"
                        onClick={() => excluirGrupo(String(sel.group))}>
                  Excluir a composição inteira
                </button>
              </div>
            </div>
          ) : null}
          <div className="sub" style={{ marginTop: 8 }}>
            Desativar mantém o efeito na timeline sem aplicá-lo — bom para
            comparar com/sem (A/B) antes de decidir.
          </div>
        </div>
      ) : (
        <div className="sub">Selecione um efeito na lista ou na track Motion.</div>
      )}
    </>
  );
}
