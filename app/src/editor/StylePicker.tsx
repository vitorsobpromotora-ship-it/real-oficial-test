/**
 * Seletor VISUAL de estilos de legenda (Ponto 20): cards que demonstram
 * "ESSA É UMA LEGENDA" com o comportamento do preset — nada de <select> cego.
 * Os presets vêm do motor (mesma fonte de verdade do render).
 */
import type { CaptionPreset } from "../api/types";

const AMOSTRA = "ESSA É UMA LEGENDA";

/** Estilo CSS aproximado do preset para o card (escala reduzida do 1080×1920). */
function cardStyle(p: CaptionPreset): React.CSSProperties {
  const esc = 0.2; // o card tem ~1/5 da largura do canvas real
  const fs = Number(p.font_size ?? 70) * esc;
  const outline = Math.max(1, Number(p.outline ?? 3) * esc * 1.6);
  const oc = String(p.outline_color ?? "#000");
  const caixa = Number(p.border_style ?? 1) === 3;
  return {
    fontFamily: `${p.font_family ?? "Montserrat"}, Inter, sans-serif`,
    fontSize: Math.max(9, fs),
    fontWeight: p.bold === false ? 600 : 800,
    letterSpacing: Number(p.letter_spacing ?? 0) * esc,
    color: caixa ? String(p.text_color ?? "#111") : String(p.text_color ?? "#fff"),
    background: caixa ? String(p.back_color ?? "#FFD400") : "transparent",
    padding: caixa ? "2px 7px" : 0,
    borderRadius: caixa ? 4 : 0,
    textShadow: caixa ? "none"
      : `${-outline}px ${-outline}px 0 ${oc}, ${outline}px ${-outline}px 0 ${oc},`
        + `${-outline}px ${outline}px 0 ${oc}, ${outline}px ${outline}px 0 ${oc}`,
    filter: p.anim_word === "glow" ? "drop-shadow(0 0 6px currentColor)" : undefined,
    lineHeight: 1.15,
  };
}

/** Uma palavra por vez? mostramos a palavra "ativa" destacada como no vídeo. */
function amostraDe(p: CaptionPreset): { texto: string; ativa: string | null } {
  if (p.word_mode) return { texto: "", ativa: "LEGENDA" };
  if (p.karaoke) return { texto: "ESSA É UMA ", ativa: "LEGENDA" };
  return { texto: AMOSTRA, ativa: null };
}

interface Props {
  presets: CaptionPreset[];
  valor: string; // id do preset ativo ("" = padrão do kit)
  onChange(id: string): void;
}

export default function StylePicker({ presets, valor, onChange }: Props) {
  const familias = new Map<string, CaptionPreset[]>();
  for (const p of presets) {
    const f = String(p.family ?? "Outros");
    familias.set(f, [...(familias.get(f) ?? []), p]);
  }
  return (
    <div className="sp">
      {[...familias.entries()].map(([familia, lista]) => (
        <div key={familia} className="sp-fam">
          <div className="sp-famname">{familia}</div>
          <div className="sp-grid">
            {lista.map((p) => {
              const a = amostraDe(p);
              return (
                <button
                  key={p.id}
                  data-testid={`preset-${p.id}`}
                  className={`sp-card${valor === p.id ? " on" : ""}`}
                  title={p.word_mode ? "Uma palavra por vez" : "Frase completa"}
                  onClick={() => onChange(p.id)}
                >
                  <span className="sp-demo" style={cardStyle(p)}>
                    {a.texto}
                    {a.ativa ? (
                      <span style={{ color: String(p.highlight_color ?? p.text_color ?? "#fff") }}>
                        {a.ativa}
                      </span>
                    ) : null}
                  </span>
                  <span className="sp-name">{String(p.label ?? p.id)}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <button className={`sp-reset${valor === "" ? " on" : ""}`} onClick={() => onChange("")}>
        Usar o padrão do Kit de Marca
      </button>
    </div>
  );
}
