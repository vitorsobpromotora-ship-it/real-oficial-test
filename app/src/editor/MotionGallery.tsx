/**
 * Galeria ANIMADA de presets (v4 FASE K, Entregas 103–106): cada card
 * DEMONSTRA o efeito — os keyframes CSS são gerados das MESMAS trilhas do
 * render (textPropsAt amostrado), então o card já é uma prévia honesta.
 * Passar o mouse anima; clicar aplica. ⭐ favoritos e recentes primeiro.
 */
import { useMemo, useState } from "react";
import { textPropsAt, type EffectInstance, type TextPreset } from "./motion";

const FAV_KEY = "ro.motion.favoritos";
const REC_KEY = "ro.motion.recentes";

function lerLista(chave: string): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(chave) ?? "[]") as string[];
  } catch {
    return [];
  }
}
function gravarLista(chave: string, lista: string[]) {
  try {
    window.localStorage.setItem(chave, JSON.stringify(lista.slice(0, 12)));
  } catch { /* sem quota: a galeria funciona sem persistir */ }
}
export function marcarRecente(id: string) {
  gravarLista(REC_KEY, [id, ...lerLista(REC_KEY).filter((x) => x !== id)]);
}

/** @keyframes do preset, amostrando as trilhas reais em 9 passos. */
function keyframesDe(preset: TextPreset): string {
  const efeito = { id: "demo", type: "text_emphasis", preset: preset.id,
    target: { kind: "words" }, start: 0, end: 1, intensity: "forte",
    enabled: true, seed: 7 } as EffectInstance;
  const passos: string[] = [];
  for (let i = 0; i <= 8; i++) {
    const u = i / 8;
    const pr = textPropsAt(efeito, preset, Math.min(0.999, u));
    const sx = (pr.scale_x !== 100 ? pr.scale_x : pr.scale) / 100;
    const sy = (pr.scale_y !== 100 ? pr.scale_y : pr.scale) / 100;
    passos.push(`${Math.round(u * 100)}% { transform: scale(${sx.toFixed(3)},`
      + ` ${sy.toFixed(3)}) rotate(${pr.rot.toFixed(2)}deg);`
      + ` opacity: ${(1 - pr.alpha).toFixed(2)};`
      + ` filter: blur(${Math.min(3, pr.blur * 0.4).toFixed(1)}px); }`);
  }
  return `@keyframes mg-${preset.id} { ${passos.join(" ")} }`;
}

interface Props {
  presets: TextPreset[];
  atual: string;
  onAplicar(presetId: string): void;
}

export default function MotionGallery(p: Props) {
  const [favs, setFavs] = useState<string[]>(() => lerLista(FAV_KEY));
  const recentes = useMemo(() => lerLista(REC_KEY), []);
  const css = useMemo(() => p.presets.map(keyframesDe).join("\n"), [p.presets]);

  function alternarFav(id: string) {
    const novo = favs.includes(id) ? favs.filter((x) => x !== id) : [id, ...favs];
    setFavs(novo);
    gravarLista(FAV_KEY, novo);
  }

  const ordenados = [...p.presets].sort((a, b) => {
    const fa = favs.includes(a.id) ? 0 : 1;
    const fb = favs.includes(b.id) ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const ra = recentes.indexOf(a.id);
    const rb = recentes.indexOf(b.id);
    return (ra < 0 ? 99 : ra) - (rb < 0 ? 99 : rb);
  });
  const categorias = [...new Set(ordenados.map((x) => x.categoria))];

  return (
    <div className="mg" data-testid="mo-galeria">
      <style>{css}</style>
      {categorias.map((cat) => (
        <div key={cat}>
          <div className="mg-cat">{cat}</div>
          <div className="mg-grid">
            {ordenados.filter((x) => x.categoria === cat).map((preset) => (
              <button key={preset.id}
                      className={`mg-card${p.atual === preset.id ? " on" : ""}`}
                      data-testid={`mg-${preset.id}`}
                      title={preset.descricao ?? preset.label}
                      onClick={() => { marcarRecente(preset.id); p.onAplicar(preset.id); }}>
                <span className="mg-demo"
                      style={{ animationName: `mg-${preset.id}`,
                        color: preset.color ?? "#FFD400" }}>
                  RIMA
                </span>
                <span className="mg-nome">
                  {favs.includes(preset.id) ? "⭐ " : ""}{preset.label}
                </span>
                <i className="mg-fav" title="Favoritar"
                   onClick={(e) => { e.stopPropagation(); alternarFav(preset.id); }}>
                  {favs.includes(preset.id) ? "★" : "☆"}
                </i>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
