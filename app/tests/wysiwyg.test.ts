/**
 * Pontos 7 e 49 — o preview do Editor e o render final NÃO podem divergir.
 * O motor gera shared/wysiwyg-cases.json com a geometria de legenda que ele
 * vai queimar; aqui o cálculo do canvas é conferido contra esse contrato.
 */
import { describe, expect, it } from "vitest";
import casos from "../../shared/wysiwyg-cases.json";
import { captionBox } from "../src/editor/model";

interface Caso {
  nome: string;
  style: Record<string, unknown>;
  res: Record<string, { ml: number; mr: number; anchor_top: number }>;
}

// o contrato traz o estilo do CORTE; o canvas recebe o estilo já resolvido
// pelo motor (preset + kit + corte), então replicamos os campos do preset que
// afetam a geometria antes de comparar.
const PRESET_GEO: Record<string, Record<string, unknown>> = {
  bold_karaoke: { anchor_top: 1280, max_width_pct: 88 },
  clean: { anchor_top: 1300, max_width_pct: 84 },
  palavra_pop: { anchor_top: 1180, max_width_pct: 92 },
  subtitle_bar: { anchor_top: 1680, max_width_pct: 90 },
};

describe("contrato WYSIWYG preview × render", () => {
  const lista = (casos as { casos: Caso[] }).casos;

  it("o contrato tem casos suficientes", () => {
    expect(lista.length).toBeGreaterThanOrEqual(6);
  });

  for (const caso of lista) {
    it(`geometria idêntica ao motor — ${caso.nome}`, () => {
      const preset = String(caso.style.preset ?? "bold_karaoke");
      const style = { ...PRESET_GEO[preset], ...caso.style };
      for (const [chave, esperado] of Object.entries(caso.res)) {
        const [w, h] = chave.split("x").map(Number);
        expect(captionBox(style, [w, h])).toEqual(esperado);
      }
    });
  }
});
