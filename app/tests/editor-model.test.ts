/**
 * Ponto 42 — relógio RELATIVO do Editor: 00:00 no início do corte, origem
 * preservada por baixo; expandir o início recalcula a duração mas o relógio
 * continua começando em 00:00.
 */
import { describe, expect, it } from "vitest";
import { fmtT, outDur, outToSrc, srcToOut } from "../src/editor/model";

describe("relógio relativo (Ponto 42)", () => {
  it("corte 06:20→07:05 vira 0:00→0:45 na interface", () => {
    const segs = [{ src_start: 380, src_end: 425 }];
    expect(srcToOut(segs, 380)).toBe(0);
    expect(srcToOut(segs, 425)).toBe(45);
    expect(outDur(segs)).toBe(45);
    expect(fmtT(srcToOut(segs, 380))).toBe("0:00.0");
    expect(fmtT(outDur(segs))).toBe("0:45.0");
  });

  it("expandir o início em 3s: relógio continua em 0:00 e a duração vira 0:48", () => {
    const segs = [{ src_start: 377, src_end: 425 }]; // usuário arrastou até 06:17
    expect(srcToOut(segs, 377)).toBe(0); // nunca aparece -00:03
    expect(outDur(segs)).toBe(48);
    expect(fmtT(outDur(segs))).toBe("0:48.0");
    expect(outToSrc(segs, 0)).toBe(377); // origem preservada internamente
  });

  it("trechos removidos não avançam o relógio (jump cuts)", () => {
    const segs = [{ src_start: 10, src_end: 20 }, { src_start: 30, src_end: 40 }];
    expect(outDur(segs)).toBe(20);
    expect(srcToOut(segs, 15)).toBe(5);
    expect(srcToOut(segs, 25)).toBe(10); // dentro do buraco: cola no fim do 1º trecho
    expect(srcToOut(segs, 35)).toBe(15);
    expect(outToSrc(segs, 15)).toBe(35); // saída→fonte atravessa o buraco
  });
});
