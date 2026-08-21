/**
 * Painel Motion (v4 FASE C) — edição das EffectInstances do Motion Manifest.
 *
 * O efeito nasce no editor de palavras (menu da palavra → ✦ Motion) ou pelo
 * clique num bloco da track Motion; aqui ele é ajustado: preset, intensidade,
 * janela, ativo/inativo (A/B sem excluir), variação de seed e exclusão.
 * Tudo passa pelo Draft → undo/redo e autosave como qualquer edição visual.
 */
import type { CaptionCards } from "../api/types";
import { fmtT, type Draft } from "./model";
import {
  hash32, manifestVazio, type EffectInstance, type TextPreset,
} from "./motion";

export const INTENS: [string, string][] = [
  ["suave", "Suave"], ["normal", "Normal"], ["forte", "Forte"],
];

export function rotuloDoEfeito(e: EffectInstance, presets: TextPreset[]): string {
  const nome = presets.find((p) => p.id === e.preset)?.label ?? e.preset;
  const inten = typeof e.intensity === "string" && e.intensity !== "normal"
    ? ` — ${INTENS.find(([i]) => i === e.intensity)?.[1] ?? e.intensity}` : "";
  return `${nome}${inten}`;
}

interface Props {
  draft: Draft;
  upd(patch: Partial<Draft>): void;
  presets: TextPreset[];
  selFx: string | null;
  setSelFx(id: string | null): void;
  captions: CaptionCards | null;
  onSeekOut(t: number): void;
}

export default function MotionPanel(p: Props) {
  const effects = p.draft.motion?.effects ?? [];
  const sel = effects.find((e) => e.id === p.selFx) ?? null;

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

  function alvoLegivel(e: EffectInstance): string {
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

  if (!effects.length) {
    return (
      <>
        <h3>Motion</h3>
        <div className="sub">
          Nenhum efeito de motion neste corte ainda.
          <br /><br />
          Para criar: abra <b>Palavras</b>, clique na palavra que merece o
          destaque e escolha <b>✦ Motion</b>. O efeito aparece como um bloco
          na track Motion da timeline — e é exatamente o que o render final
          vai queimar no vídeo.
        </div>
      </>
    );
  }

  return (
    <>
      <h3>Motion</h3>
      <div className="mo-lista" data-testid="mo-lista">
        {effects.map((e) => (
          <button key={e.id}
                  className={`mo-item${p.selFx === e.id ? " on" : ""}${e.enabled === false ? " off" : ""}`}
                  data-testid={`mo-item-${e.id}`}
                  onClick={() => { p.setSelFx(e.id); p.onSeekOut(e.start + 0.01); }}>
            <b>✦ {rotuloDoEfeito(e, p.presets)}</b>
            <span className="sub">
              {alvoLegivel(e)} · {fmtT(e.start)} → {fmtT(e.end)}
              {e.enabled === false ? " · desativado" : ""}
            </span>
          </button>
        ))}
      </div>

      {sel ? (
        <div className="mo-editor" data-testid="mo-editor">
          <label>Animação</label>
          <select value={sel.preset} data-testid="mo-preset"
                  onChange={(ev) => mudar(sel.id, { preset: ev.target.value })}>
            {[...new Set(p.presets.map((pr) => pr.categoria))].map((cat) => (
              <optgroup key={cat} label={cat}>
                {p.presets.filter((pr) => pr.categoria === cat).map((pr) => (
                  <option key={pr.id} value={pr.id}>{pr.label}</option>
                ))}
              </optgroup>
            ))}
            {!p.presets.some((pr) => pr.id === sel.preset) ? (
              <option value={sel.preset}>{sel.preset}</option>
            ) : null}
          </select>
          <div className="sub" style={{ marginTop: 2 }}>
            {p.presets.find((pr) => pr.id === sel.preset)?.descricao ?? ""}
          </div>

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
            <button className="danger right" data-testid="mo-excluir"
                    onClick={() => excluir(sel.id)}>
              Excluir efeito
            </button>
          </div>
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
